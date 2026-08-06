"""Bulk import (CSV / JSON / cloud discovery / service discovery) preview + confirm."""

import uuid
from datetime import datetime, timezone
from typing import Literal, Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from ..auth import User, get_current_user
from ..database import engine as db_engine
from ..database import ImportHistory, Tool, ToolAccount, Workspace, WorkspaceTool
from ..importers.cloud_discovery import cloud_discovery
from ..importers.csv_importer import csv_importer
from ..importers.json_importer import json_importer
from ..importers.service_discovery import service_discovery
from ..services.secrets import encrypt_secret

router = APIRouter(tags=["imports"])


def _serialize_preview_row(r: dict) -> dict:
    d = dict(r)
    ca = d.get("created_at")
    if isinstance(ca, datetime):
        d["created_at"] = ca.isoformat()
    return d


def _import_preview_payload(rows: list, errors: list) -> dict:
    preview = [_serialize_preview_row(x) for x in rows[:5]]
    all_rows = [_serialize_preview_row(x) for x in rows]
    total = len(rows)
    ready = total > 0 and len(errors) == 0
    return {
        "preview": preview,
        "rows": all_rows,
        "total_rows": total,
        "errors": errors,
        "ready_to_import": ready,
    }


def _parse_import_created_at(val) -> datetime:
    if val is None:
        return datetime.now(timezone.utc)
    if isinstance(val, datetime):
        if val.tzinfo is None:
            return val.replace(tzinfo=timezone.utc)
        return val
    if isinstance(val, str):
        try:
            s = val.replace("Z", "+00:00")
            return datetime.fromisoformat(s)
        except ValueError:
            return datetime.now(timezone.utc)
    return datetime.now(timezone.utc)


def _normalize_requires_hitl(val) -> int:
    if val in (True, 1, "1", "true", "True", "yes", "YES"):
        return 1
    return 0


def _bulk_insert_tool_accounts(
    rows: list[dict],
    actor_username: str,
    workspace_id: str | None = None,
    owner_user_id: str | None = None,
) -> dict:
    imported = 0
    skipped = 0
    failed = 0
    details: list[dict] = []
    linked = 0
    allowed = {
        "id",
        "tool_id",
        "account_name",
        "account_identifier",
        "instance_url",
        "environment",
        "region",
        "auth_type",
        "credentials_vault_ref",
        "status",
        "is_active",
        "requires_hitl",
        "created_by",
        "created_at",
        "tenant_id",
        "owner_user_id",
        "workspace_id",
    }
    with Session(db_engine) as session:
        ws = None
        if workspace_id:
            ws = session.get(Workspace, workspace_id)
            if not ws or not ws.is_active:
                raise HTTPException(status_code=404, detail="Workspace not found")
        for raw in rows:
            if not isinstance(raw, dict):
                failed += 1
                details.append({"status": "failed", "reason": "row is not an object"})
                continue
            row = {k: v for k, v in raw.items() if k in allowed}
            tool_id = (row.get("tool_id") or "").strip()
            account_name = (row.get("account_name") or "").strip()
            if not tool_id or not account_name:
                failed += 1
                details.append(
                    {"status": "failed", "reason": "missing tool_id or account_name", "tool_id": tool_id}
                )
                continue
            if not session.get(Tool, tool_id):
                failed += 1
                details.append({"status": "failed", "tool_id": tool_id, "reason": "unknown tool"})
                continue
            dup = session.exec(
                select(ToolAccount).where(
                    ToolAccount.tool_id == tool_id,
                    ToolAccount.account_name == account_name,
                    ToolAccount.is_active == 1,
                )
            ).first()
            if dup:
                skipped += 1
                details.append(
                    {
                        "status": "skipped",
                        "tool_id": tool_id,
                        "account_name": account_name,
                        "reason": "duplicate tool_id + account_name",
                    }
                )
                aid = dup.id
            else:
                aid = (row.get("id") or "").strip() or str(uuid.uuid4())
                if session.get(ToolAccount, aid):
                    aid = str(uuid.uuid4())
                from ..importers.environment_infer import (
                    normalize_environment,
                    requires_hitl_for_env,
                )

                env = normalize_environment(row.get("environment") or "development")
                auth_type = (row.get("auth_type") or "api_key").strip()
                hitl = _normalize_requires_hitl(row.get("requires_hitl"))
                if row.get("requires_hitl") is None:
                    hitl = 1 if requires_hitl_for_env(env) else 0
                created_by = (row.get("created_by") or "import").strip() or actor_username
                try:
                    raw_cred = (row.get("credentials_vault_ref") or "").strip() or None
                    stored_cred = encrypt_secret(raw_cred) if raw_cred else None
                    ta = ToolAccount(
                        id=aid,
                        tool_id=tool_id,
                        account_name=account_name,
                        account_identifier=(row.get("account_identifier") or None)
                        if row.get("account_identifier")
                        else None,
                        instance_url=(row.get("instance_url") or None) if row.get("instance_url") else None,
                        environment=env,
                        region=(row.get("region") or None) if row.get("region") else None,
                        auth_type=auth_type,
                        credentials_vault_ref=stored_cred,
                        status=str(row.get("status") or "unknown"),
                        is_active=int(row.get("is_active", 1) or 1),
                        requires_hitl=hitl,
                        created_by=created_by,
                        owner_user_id=(
                            str(row.get("owner_user_id") or owner_user_id or "").strip()
                            or None
                        ),
                        workspace_id=workspace_id or (str(row.get("workspace_id") or "").strip() or None),
                        tenant_id=(row.get("tenant_id") or getattr(ws, "tenant_id", None) or "default"),
                    )
                    ta.created_at = _parse_import_created_at(row.get("created_at"))
                    session.add(ta)
                    imported += 1
                    details.append(
                        {"status": "imported", "id": aid, "tool_id": tool_id, "account_name": account_name}
                    )
                except Exception as exc:
                    failed += 1
                    details.append({"status": "failed", "tool_id": tool_id, "reason": str(exc)})
                    continue

            if ws is not None and aid:
                exists = session.exec(
                    select(WorkspaceTool).where(
                        WorkspaceTool.workspace_id == ws.id,
                        WorkspaceTool.tool_id == tool_id,
                        WorkspaceTool.account_id == aid,
                    )
                ).first()
                if not exists:
                    session.add(
                        WorkspaceTool(
                            id=str(uuid.uuid4()),
                            workspace_id=ws.id,
                            tool_id=tool_id,
                            account_id=aid,
                            display_order=0,
                            is_primary=0,
                            added_at=datetime.now(timezone.utc),
                        )
                    )
                    linked += 1
        session.commit()
    return {
        "imported": imported,
        "skipped": skipped,
        "failed": failed,
        "linked_to_workspace": linked,
        "workspace_id": workspace_id,
        "details": details,
    }


def _tool_account_to_discovery_dict(a: ToolAccount) -> dict:
    return {
        "id": a.id,
        "tool_id": a.tool_id,
        "account_name": a.account_name,
        "account_identifier": a.account_identifier,
        "instance_url": a.instance_url,
        "environment": a.environment,
        "region": a.region,
        "auth_type": a.auth_type,
        "status": a.status,
        "is_active": a.is_active,
    }


def _record_import_history(
    import_type: str,
    source: str,
    total_rows: int,
    summary: dict,
    created_by: str,
) -> None:
    with Session(db_engine) as session:
        session.add(
            ImportHistory(
                id=str(uuid.uuid4()),
                import_type=import_type,
                source=source or "",
                total_rows=int(total_rows),
                imported=int(summary.get("imported", 0)),
                skipped=int(summary.get("skipped", 0)),
                failed=int(summary.get("failed", 0)),
                created_by=created_by,
            )
        )
        session.commit()


def _strip_discovery_metadata(rows: list[dict]) -> list[dict]:
    skip = {
        "metadata",
        "discovered_services",
        "discovered_repos",
        "environment_source",
        "environment_confidence",
    }
    out: list[dict] = []
    for a in rows:
        if not isinstance(a, dict):
            continue
        out.append({k: v for k, v in a.items() if k not in skip})
    return out


def _service_discovery_preview_payload(accounts: list) -> dict:
    serialized = [_serialize_preview_row(a) for a in accounts]
    return {
        "preview": serialized[:5],
        "rows": serialized,
        "total_rows": len(serialized),
        "errors": [],
        "ready_to_import": len(serialized) > 0,
    }


class ImportConfirmBody(BaseModel):
    rows: list[dict]
    workspace_id: Optional[str] = None


class ImportJsonBody(BaseModel):
    content: str


class ImportDiscoverBody(BaseModel):
    provider: Literal["aws", "gcp", "azure", "github"]
    credentials: dict = Field(default_factory=dict)


class ImportDiscoverConfirmBody(BaseModel):
    accounts: list[dict]
    workspace_id: Optional[str] = None


@router.get("/api/import/template/csv")
def api_import_template_csv(current_user: User = Depends(get_current_user)):
    from starlette.responses import Response

    body = csv_importer.generate_template()
    return Response(
        content=body,
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="accounts-template.csv"'},
    )


@router.post("/api/import/csv")
async def api_import_csv(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
):
    raw = await file.read()
    try:
        content = raw.decode("utf-8")
    except UnicodeDecodeError:
        content = raw.decode("utf-8", errors="replace")
    parsed = csv_importer.parse_csv(content)
    return _import_preview_payload(parsed["rows"], parsed["errors"])


@router.post("/api/import/csv/confirm")
def api_import_csv_confirm(
    body: ImportConfirmBody,
    current_user: User = Depends(get_current_user),
):
    if not body.rows:
        raise HTTPException(status_code=400, detail="rows is required")
    summary = _bulk_insert_tool_accounts(
        body.rows,
        current_user.username,
        workspace_id=body.workspace_id,
        owner_user_id=str(current_user.id) if current_user.id is not None else None,
    )
    _record_import_history("csv", "upload", len(body.rows), summary, current_user.username)
    return summary


@router.post("/api/import/json")
def api_import_json(
    body: ImportJsonBody,
    current_user: User = Depends(get_current_user),
):
    parsed = json_importer.parse_json(body.content or "")
    return _import_preview_payload(parsed["rows"], parsed["errors"])


@router.post("/api/import/json/confirm")
def api_import_json_confirm(
    body: ImportConfirmBody,
    current_user: User = Depends(get_current_user),
):
    if not body.rows:
        raise HTTPException(status_code=400, detail="rows is required")
    summary = _bulk_insert_tool_accounts(
        body.rows,
        current_user.username,
        workspace_id=body.workspace_id,
        owner_user_id=str(current_user.id) if current_user.id is not None else None,
    )
    _record_import_history("json", "upload", len(body.rows), summary, current_user.username)
    return summary


@router.post("/api/import/discover")
async def api_import_discover(
    body: ImportDiscoverBody,
    current_user: User = Depends(get_current_user),
):
    creds = body.credentials or {}
    if body.provider == "aws":
        out = await cloud_discovery.discover_aws(creds)
    elif body.provider == "gcp":
        out = await cloud_discovery.discover_gcp(creds)
    elif body.provider == "azure":
        out = await cloud_discovery.discover_azure(creds)
    elif body.provider == "github":
        out = await cloud_discovery.discover_github_org(creds)
    else:
        raise HTTPException(status_code=400, detail="invalid provider")
    accts = out.get("accounts") or []
    serialized = [_serialize_preview_row(a) for a in accts]
    return {
        "preview": serialized[:5],
        "rows": serialized,
        "total_rows": len(accts),
        "errors": [],
        "ready_to_import": len(accts) > 0,
        "provider": out.get("provider"),
        "discovered_count": out.get("discovered_count"),
        "accounts": serialized,
    }


@router.post("/api/import/discover/confirm")
def api_import_discover_confirm(
    body: ImportDiscoverConfirmBody,
    current_user: User = Depends(get_current_user),
):
    if not body.accounts:
        raise HTTPException(status_code=400, detail="accounts is required")
    rows = _strip_discovery_metadata(body.accounts)
    summary = _bulk_insert_tool_accounts(
        rows,
        current_user.username,
        workspace_id=body.workspace_id,
        owner_user_id=str(current_user.id) if current_user.id is not None else None,
    )
    _record_import_history("cloud_discover", "provider_stub", len(body.accounts), summary, current_user.username)
    return summary


@router.get("/api/discover/all")
async def api_discover_all(current_user: User = Depends(get_current_user)):
    with Session(db_engine) as session:
        connected = session.exec(
            select(ToolAccount).where(
                ToolAccount.status == "connected",
                ToolAccount.is_active == 1,
            )
        ).all()
        account_dicts = [_tool_account_to_discovery_dict(a) for a in connected]
    out = await service_discovery.discover_all_from_connected(account_dicts)
    accts = out.get("accounts") or []
    payload = _service_discovery_preview_payload(accts)
    payload["total_discovered"] = out.get("total_discovered", len(accts))
    payload["sources_scanned"] = out.get("sources_scanned", 0)
    return payload


@router.post("/api/discover/confirm")
def api_discover_confirm(
    body: ImportDiscoverConfirmBody,
    current_user: User = Depends(get_current_user),
):
    if not body.accounts:
        raise HTTPException(status_code=400, detail="accounts is required")
    rows = _strip_discovery_metadata(body.accounts)
    summary = _bulk_insert_tool_accounts(
        rows,
        current_user.username,
        workspace_id=body.workspace_id,
        owner_user_id=str(current_user.id) if current_user.id is not None else None,
    )
    _record_import_history("service_discovery", "connected_scan", len(body.accounts), summary, current_user.username)
    return summary


@router.post("/api/discover/{tool_id}/{account_id}")
async def api_discover_one_account(
    tool_id: str,
    account_id: str,
    current_user: User = Depends(get_current_user),
):
    with Session(db_engine) as session:
        acc = session.get(ToolAccount, account_id)
        if not acc or acc.tool_id != tool_id:
            raise HTTPException(status_code=404, detail="Account not found")
        if acc.status != "connected" or acc.is_active != 1:
            raise HTTPException(
                status_code=400,
                detail="Account must be connected and active for service discovery",
            )
        d = _tool_account_to_discovery_dict(acc)
    tid = tool_id.strip().lower()
    if tid == "github":
        out = await service_discovery.discover_from_github(d)
    elif tid == "jira":
        out = await service_discovery.discover_from_jira(d)
    elif tid == "slack":
        out = await service_discovery.discover_from_slack(d)
    elif tid == "kubernetes":
        out = await service_discovery.discover_from_kubernetes(d)
    elif tid == "datadog":
        out = await service_discovery.discover_from_datadog(d)
    else:
        raise HTTPException(status_code=400, detail=f"Service discovery not implemented for tool '{tool_id}'")
    disc = out.get("discovered") or []
    payload = _service_discovery_preview_payload(disc)
    payload["source"] = out.get("source")
    payload["source_account"] = out.get("source_account")
    return payload


@router.get("/api/import/history")
def api_import_history(current_user: User = Depends(get_current_user)):
    with Session(db_engine) as session:
        rows = session.exec(
            select(ImportHistory).order_by(ImportHistory.created_at.desc()).limit(50)
        ).all()
    return [
        {
            "id": r.id,
            "import_type": r.import_type,
            "source": r.source,
            "total_rows": r.total_rows,
            "imported": r.imported,
            "skipped": r.skipped,
            "failed": r.failed,
            "created_by": r.created_by,
            "created_at": r.created_at.isoformat(),
        }
        for r in rows
    ]
