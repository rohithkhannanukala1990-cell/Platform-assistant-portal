"""Editor persistence, GitHub browse, PR proposals, agent actions."""

from __future__ import annotations

import difflib
import hashlib
import json
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import HTTPException
from sqlmodel import Session, col, select

from ..auth import User, write_audit
from ..context import DEFAULT_TENANT_ID, PlatformContext
from ..db.core import engine
from ..db.models.ai_models import AgentRun
from ..db.models.editor import VALID_SOURCE_TYPES, EditorFile, EditorPRApproval
from ..services.audit_compliance import redact_secrets, redact_secret_text
from ..services.github_access import try_github_connector_from_context

GITHUB_NOT_CONNECTED = (
    "GitHub is not connected. Open Settings → Tool Registry and connect a GitHub account."
)


def detect_language(filename: str) -> str:
    ext = (filename or "").rsplit(".", 1)[-1].lower() if filename else ""
    return {
        "yml": "yaml",
        "yaml": "yaml",
        "json": "json",
        "py": "python",
        "js": "javascript",
        "jsx": "javascript",
        "ts": "typescript",
        "tsx": "typescript",
        "sh": "bash",
        "bash": "bash",
        "dockerfile": "dockerfile",
        "tf": "hcl",
        "hcl": "hcl",
        "sql": "sql",
        "md": "markdown",
    }.get(ext, "yaml")


def serialize_file(row: EditorFile) -> dict[str, Any]:
    return redact_secrets(
        {
            "id": row.id,
            "tenant_id": row.tenant_id,
            "workspace_id": row.workspace_id,
            "owner_username": row.owner_username,
            "filename": row.filename,
            "language": row.language,
            "content": row.content,
            "source_type": row.source_type,
            "source_repo": row.source_repo,
            "source_path": row.source_path,
            "source_ref": row.source_ref,
            "source_sha": row.source_sha,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        }
    )


def get_owned_file(session: Session, file_id: str, *, tenant_id: str, username: str) -> EditorFile:
    row = session.get(EditorFile, file_id)
    if not row or row.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Not found")
    if (row.owner_username or "") != username:
        raise HTTPException(status_code=404, detail="Not found")
    return row


def list_files(*, tenant_id: str, username: str) -> list[dict[str, Any]]:
    with Session(engine) as session:
        rows = session.exec(
            select(EditorFile)
            .where(
                EditorFile.tenant_id == tenant_id,
                EditorFile.owner_username == username,
            )
            .order_by(col(EditorFile.updated_at).desc())
        ).all()
        return [serialize_file(r) for r in rows]


def create_file(
    *,
    tenant_id: str,
    username: str,
    filename: str,
    content: str = "",
    language: str | None = None,
    workspace_id: str | None = None,
    source_type: str = "scratch",
    source_repo: str | None = None,
    source_path: str | None = None,
    source_ref: str | None = None,
    source_sha: str | None = None,
) -> dict[str, Any]:
    st = (source_type or "scratch").strip().lower()
    if st not in VALID_SOURCE_TYPES:
        raise HTTPException(status_code=400, detail=f"source_type must be one of {sorted(VALID_SOURCE_TYPES)}")
    name = (filename or "untitled.yaml").strip() or "untitled.yaml"
    now = datetime.now(timezone.utc)
    row = EditorFile(
        id=str(uuid.uuid4()),
        tenant_id=tenant_id or DEFAULT_TENANT_ID,
        workspace_id=workspace_id,
        owner_username=username,
        filename=name,
        language=(language or detect_language(name)).strip() or "yaml",
        content=content or "",
        source_type=st,
        source_repo=source_repo,
        source_path=source_path,
        source_ref=source_ref,
        source_sha=source_sha,
        created_at=now,
        updated_at=now,
    )
    with Session(engine) as session:
        session.add(row)
        session.commit()
        session.refresh(row)
        out = serialize_file(row)
    write_audit(username, "User", "editor_file_created", resource=f"editor:{out['id']}", detail=name)
    return out


def update_file(
    *,
    file_id: str,
    tenant_id: str,
    username: str,
    content: str | None = None,
    filename: str | None = None,
    language: str | None = None,
) -> dict[str, Any]:
    with Session(engine) as session:
        row = get_owned_file(session, file_id, tenant_id=tenant_id, username=username)
        if content is not None:
            row.content = content
        if filename is not None and filename.strip():
            row.filename = filename.strip()
            if language is None:
                row.language = detect_language(row.filename)
        if language is not None and language.strip():
            row.language = language.strip()
        row.updated_at = datetime.now(timezone.utc)
        session.add(row)
        session.commit()
        session.refresh(row)
        return serialize_file(row)


def delete_file(*, file_id: str, tenant_id: str, username: str) -> None:
    with Session(engine) as session:
        row = get_owned_file(session, file_id, tenant_id=tenant_id, username=username)
        session.delete(row)
        session.commit()
    write_audit(username, "User", "editor_file_deleted", resource=f"editor:{file_id}", detail="")


def validate_content(language: str, content: str) -> dict[str, Any]:
    lang = (language or "").lower()
    problems: list[dict[str, Any]] = []
    if lang == "json":
        try:
            json.loads(content or "")
        except json.JSONDecodeError as exc:
            problems.append(
                {
                    "severity": "error",
                    "message": str(exc.msg),
                    "line": exc.lineno,
                    "column": exc.colno,
                }
            )
    elif lang in {"yaml", "yml"}:
        try:
            import yaml  # type: ignore

            yaml.safe_load(content or "")
        except Exception as exc:
            line = getattr(exc, "problem_mark", None)
            problems.append(
                {
                    "severity": "error",
                    "message": str(exc),
                    "line": getattr(line, "line", None),
                    "column": getattr(line, "column", None),
                }
            )
    elif lang in {"hcl", "tf"}:
        # Lightweight brace/quote balance check — no terraform binary required
        if (content or "").count("{") != (content or "").count("}"):
            problems.append({"severity": "error", "message": "Unbalanced { } braces", "line": None})
        if (content or "").count("[") != (content or "").count("]"):
            problems.append({"severity": "error", "message": "Unbalanced [ ] brackets", "line": None})
    elif lang == "sql":
        # Soft check: unmatched quotes
        s = content or ""
        if s.count("'") % 2 != 0:
            problems.append({"severity": "warning", "message": "Unmatched single quote", "line": None})
    return {"ok": len(problems) == 0, "problems": problems, "language": lang}


def format_content(language: str, content: str) -> dict[str, Any]:
    lang = (language or "").lower()
    text = content or ""
    if lang == "json":
        try:
            parsed = json.loads(text)
            return {"ok": True, "content": json.dumps(parsed, indent=2, ensure_ascii=False) + "\n"}
        except json.JSONDecodeError as exc:
            return {"ok": False, "error": str(exc), "content": text}
    if lang in {"yaml", "yml"}:
        try:
            import yaml  # type: ignore

            parsed = yaml.safe_load(text)
            return {
                "ok": True,
                "content": yaml.safe_dump(parsed, sort_keys=False, allow_unicode=True),
            }
        except Exception as exc:
            return {"ok": False, "error": str(exc), "content": text}
    # Default: normalize newlines / trim trailing spaces
    lines = [ln.rstrip() for ln in text.replace("\r\n", "\n").split("\n")]
    return {"ok": True, "content": "\n".join(lines).rstrip() + "\n"}


def _github_ctx(user: User, tenant_id: str) -> PlatformContext:
    return PlatformContext(
        user_id=str(user.id) if getattr(user, "id", None) is not None else user.username,
        user_role=user.role or "User",
        tenant_id=tenant_id,
        workspace_id=getattr(user, "workspace_id", None) or "",
        environment=PlatformContext.current_env() or "development",
    )


def require_github(user: User, tenant_id: str):
    with Session(engine) as session:
        conn = try_github_connector_from_context(
            _github_ctx(user, tenant_id), db=session, user=user
        )
        if conn is None:
            raise HTTPException(status_code=400, detail=GITHUB_NOT_CONNECTED)
        return conn


def compute_diff(old: str, new: str, *, fromfile: str = "a", tofile: str = "b") -> str:
    return "".join(
        difflib.unified_diff(
            (old or "").splitlines(keepends=True),
            (new or "").splitlines(keepends=True),
            fromfile=fromfile,
            tofile=tofile,
        )
    )


def make_idempotency_key(*parts: str) -> str:
    blob = "|".join(str(p) for p in parts)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:32]


async def propose_pr(
    *,
    file_id: str,
    tenant_id: str,
    user: User,
    title: str,
    body: str,
    branch_name: str,
    base_branch: str,
    force: bool = False,
) -> dict[str, Any]:
    with Session(engine) as session:
        row = get_owned_file(session, file_id, tenant_id=tenant_id, username=user.username)
        session.expunge(row)

    if row.source_type != "github" or not row.source_repo or not row.source_path:
        raise HTTPException(status_code=400, detail="File is not linked to a GitHub source")

    conn = require_github(user, tenant_id)
    ref = row.source_ref or base_branch or "main"
    try:
        meta = await conn.get_file_meta(row.source_repo, row.source_path, ref=ref)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Failed to fetch upstream file: {exc}") from exc

    upstream_sha = meta.get("sha")
    upstream_content = meta.get("content") or ""
    if not force and row.source_sha and upstream_sha and row.source_sha != upstream_sha:
        raise HTTPException(
            status_code=409,
            detail=(
                "This file changed upstream since you opened it. Reload or force. "
                f"(local_sha={row.source_sha}, upstream_sha={upstream_sha})"
            ),
        )

    branch = (branch_name or "").strip() or f"editor/{user.username}-{uuid.uuid4().hex[:8]}"
    base = (base_branch or ref or "main").strip()
    content_to_commit = row.content  # freeze current editor content
    idem = make_idempotency_key(
        tenant_id, user.username, row.source_repo, row.source_path, branch, content_to_commit
    )

    # Reuse pending/approved approval with same idempotency key
    with Session(engine) as session:
        existing = session.exec(
            select(EditorPRApproval).where(
                EditorPRApproval.idempotency_key == idem,
                EditorPRApproval.tenant_id == tenant_id,
            )
        ).first()
        if existing and existing.status in {"pending", "approved"} and existing.pr_url:
            return {
                "approval_id": existing.id,
                "status": existing.status,
                "diff": compute_diff(upstream_content, existing.content, fromfile=row.source_path, tofile=row.source_path),
                "pr_url": existing.pr_url,
                "idempotent": True,
            }
        if existing and existing.status == "pending":
            return {
                "approval_id": existing.id,
                "status": "pending",
                "diff": compute_diff(upstream_content, existing.content, fromfile=row.source_path, tofile=row.source_path),
                "idempotent": True,
            }

    now = datetime.now(timezone.utc)
    approval_id = str(uuid.uuid4())
    run_id = str(uuid.uuid4())
    with Session(engine) as session:
        run = AgentRun(
            id=run_id,
            agent="editor_pr",
            status="pending_approval",
            summary=f"Editor PR: {title[:120]}",
            details_json=json.dumps(
                {
                    "source": "editor",
                    "editor_approval_id": approval_id,
                    "repo": row.source_repo,
                    "path": row.source_path,
                    "branch_name": branch,
                    "base_branch": base,
                },
                default=str,
            ),
            requires_approval=True,
            approval_payload_json=json.dumps(
                {
                    "source": "editor",
                    "editor_approval_id": approval_id,
                    "commands": [
                        f"github create_branch {branch}",
                        f"github commit_file {row.source_path}",
                        f"github create_pull_request {title}",
                    ],
                },
                default=str,
            ),
            triggered_by=user.username,
            user_id=user.username,
            tenant_id=tenant_id,
            environment=PlatformContext.current_env() or "development",
            task=title[:500],
            created_at=now,
            updated_at=now,
        )
        approval = EditorPRApproval(
            id=approval_id,
            tenant_id=tenant_id,
            username=user.username,
            file_id=row.id,
            repo=row.source_repo,
            path=row.source_path,
            branch_name=branch,
            base_branch=base,
            title=title.strip() or f"Update {row.source_path}",
            body=body or "",
            content=content_to_commit,
            base_sha=upstream_sha,
            idempotency_key=idem,
            status="pending",
            agent_run_id=run_id,
            created_at=now,
        )
        session.add(run)
        session.add(approval)
        session.commit()
        session.refresh(approval)
        session.expunge(approval)

    write_audit(
        user.username,
        user.role,
        "editor_pr_proposed",
        resource=f"editor_pr:{approval_id}",
        detail=redact_secret_text(f"{row.source_repo}:{row.source_path}") or "",
    )
    return {
        "approval_id": approval.id,
        "status": "pending",
        "diff": compute_diff(
            upstream_content,
            content_to_commit,
            fromfile=f"a/{row.source_path}",
            tofile=f"b/{row.source_path}",
        ),
        "branch_name": branch,
        "base_branch": base,
        "title": approval.title,
        "idempotent": False,
    }


async def fulfill_editor_pr_approval(
    *,
    approval_id: str,
    tenant_id: str,
    decided_by: str,
    user: User,
) -> dict[str, Any]:
    """Execute create_branch → commit_file → create_pull_request using DB content."""
    with Session(engine) as session:
        row = session.get(EditorPRApproval, approval_id)
        if not row or row.tenant_id != tenant_id:
            raise HTTPException(status_code=404, detail="Not found")
        if row.status == "approved" and row.pr_url:
            return {
                "ok": True,
                "pr_url": row.pr_url,
                "pr_number": row.pr_number,
                "idempotent": True,
            }
        if row.status not in {"pending", "approved"}:
            raise HTTPException(status_code=409, detail=f"Approval status is {row.status}")
        # Freeze values from DB
        repo = row.repo
        path = row.path
        branch = row.branch_name
        base = row.base_branch
        title = row.title
        body = row.body
        content = row.content  # CRITICAL: from DB only
        base_sha = row.base_sha
        idem = row.idempotency_key
        session.expunge(row)

    conn = require_github(user, tenant_id)
    try:
        await conn.create_branch(
            repo, branch_name=branch, from_ref=base, idempotency_key=f"{idem}:branch"
        )
        await conn.commit_file(
            repo,
            path=path,
            content=content,
            message=title,
            branch=branch,
            base_sha=base_sha,
            idempotency_key=f"{idem}:commit",
        )
        pr = await conn.create_pull_request(
            repo,
            title=title,
            body=body,
            head=branch,
            base=base,
            idempotency_key=f"{idem}:pr",
        )
    except Exception as exc:
        with Session(engine) as session:
            row = session.get(EditorPRApproval, approval_id)
            if row:
                row.status = "failed"
                row.error = str(exc)[:1000]
                row.decided_by = decided_by
                row.decided_at = datetime.now(timezone.utc)
                session.add(row)
                session.commit()
        raise HTTPException(status_code=502, detail=f"GitHub write failed: {exc}") from exc

    pr_url = pr.get("html_url")
    pr_number = pr.get("number")
    with Session(engine) as session:
        row = session.get(EditorPRApproval, approval_id)
        if row:
            row.status = "approved"
            row.pr_url = pr_url
            row.pr_number = pr_number
            row.decided_by = decided_by
            row.decided_at = datetime.now(timezone.utc)
            session.add(row)
            session.commit()

    write_audit(
        decided_by,
        "Admin",
        "editor_pr_fulfilled",
        resource=f"editor_pr:{approval_id}",
        detail=pr_url or "",
    )
    return {"ok": True, "pr_url": pr_url, "pr_number": pr_number, "idempotent": bool(pr.get("reused"))}


ACTION_AGENT_MAP = {
    "review": "code_review_agent",
    "explain": "documentation_agent",
    "generate_tests": "tester_agent",
    "security": "security_agent",
    "validate_terraform": "infra_agent",
    "optimise_query": None,  # handled specially via platform_misc
}


async def run_editor_agent_action(
    *,
    file_id: str,
    tenant_id: str,
    user: User,
    agent: str | None,
    action: str | None,
    selection_start: int | None,
    selection_end: int | None,
    instruction: str | None,
) -> dict[str, Any]:
    from ..pipeline.orchestrator import run_agent_for_workflow

    with Session(engine) as session:
        row = get_owned_file(session, file_id, tenant_id=tenant_id, username=user.username)
        session.expunge(row)

    content = row.content or ""
    start = max(0, int(selection_start or 0))
    end = max(start, int(selection_end if selection_end is not None else len(content)))
    selection = content[start:end]
    act = (action or "").strip().lower()
    agent_name = (agent or "").strip() or ACTION_AGENT_MAP.get(act) or ""

    if act == "optimise_query" or agent_name in {"db_analyser", "query_analyzer"}:
        problems = validate_content("sql", selection or content)
        return {
            "agent": "query_analyzer",
            "status": "success",
            "summary": "SQL checked for basic syntax issues"
            if problems.get("ok")
            else "SQL validation found issues",
            "grounding": "partial",
            "details": problems,
            "evidence": [],
            "suggested_edits": [],
        }
    if not agent_name:
        raise HTTPException(status_code=400, detail="Unknown agent action")

    ctx = _github_ctx(user, tenant_id)
    task = (
        instruction
        or f"{act or 'review'} the selected code in {row.filename}"
    )
    payload = {
        "task": task,
        "filename": row.filename,
        "language": row.language,
        "selection": selection,
        "file_content": content[:50_000],
        "selection_start": start,
        "selection_end": end,
    }
    result = await run_agent_for_workflow(agent_name, payload, ctx)
    suggested = _extract_suggested_edits(result, content, start, end)
    return {
        "agent": result.agent,
        "status": result.status,
        "summary": result.summary,
        "grounding": result.grounding or "none",
        "details": redact_secrets(result.details or {}),
        "evidence": result.evidence or [],
        "requires_approval": bool(result.requires_approval),
        "run_id": result.run_id,
        "suggested_edits": suggested,
        "connect_hint": (result.details or {}).get("connect_hint"),
    }


def _extract_suggested_edits(result: Any, content: str, start: int, end: int) -> list[dict[str, Any]]:
    details = getattr(result, "details", None) or {}
    edits = details.get("suggested_edits") or details.get("edits") or []
    out: list[dict[str, Any]] = []
    if isinstance(edits, list):
        for i, e in enumerate(edits):
            if not isinstance(e, dict):
                continue
            out.append(
                {
                    "id": e.get("id") or f"edit-{i}",
                    "start_line": e.get("start_line"),
                    "end_line": e.get("end_line"),
                    "original": e.get("original") or "",
                    "proposed": e.get("proposed") or e.get("replacement") or "",
                    "rationale": e.get("rationale") or e.get("reason") or "",
                }
            )
    # If agent returned a single replacement for the selection
    replacement = details.get("replacement") or details.get("rewritten")
    if replacement and not out and start < end:
        out.append(
            {
                "id": "selection-rewrite",
                "start_offset": start,
                "end_offset": end,
                "original": content[start:end],
                "proposed": str(replacement),
                "rationale": "Agent suggested replacement for selection",
            }
        )
    return out


def parse_github_repo_url(url: str) -> Optional[str]:
    """Return owner/repo from a GitHub URL or None."""
    if not url:
        return None
    m = re.search(r"github\.com[:/](?P<owner>[^/]+)/(?P<repo>[^/.]+)", url)
    if not m:
        return None
    return f"{m.group('owner')}/{m.group('repo')}"
