"""Code review agent — open PR hygiene via GitHub (grounded)."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone

from sqlmodel import Session

from ..connectors.github_connector import GitHubAPIError
from ..context import PlatformContext
from .base import AgentResult, BaseAgent


def _parse_repo_parts(params: dict) -> tuple[str, str, str]:
    """Return (owner, repo_name, full_name). Never invents a default org/repo."""
    owner = (params.get("owner") or "").strip()
    repo = (params.get("repo") or "").strip()
    if owner and repo and "/" not in repo:
        return owner, repo, f"{owner}/{repo}"
    if "/" in repo:
        parts = repo.split("/", 1)
        return parts[0], parts[1], repo
    task = str(params.get("task") or "")
    m = re.search(r"([\w.-]+)/([\w.-]+)", task)
    if m:
        return m.group(1), m.group(2), f"{m.group(1)}/{m.group(2)}"
    return owner, repo, repo


def _parse_pr_number(params: dict) -> int | None:
    raw = params.get("pr_number") or params.get("number")
    if raw is not None and str(raw).strip():
        try:
            return int(raw)
        except (TypeError, ValueError):
            pass
    task = str(params.get("task") or "")
    m = re.search(r"(?:PR|pr|#)\s*#?(\d+)", task)
    if m:
        return int(m.group(1))
    return None


class CodeReviewAgent(BaseAgent):
    name = "code_review_agent"
    description = "PR and repository code review assistance."
    requires_approval_envs = []
    primary_tools = ["GitHub", "GitLab", "SonarQube"]
    read_only = True

    async def run(self, params: dict, context: PlatformContext, db: Session) -> AgentResult:
        params = params if isinstance(params, dict) else {}
        from ..mcp.agent_mcp import list_github_repos_prefer_mcp, mcp_enabled

        connector = await self._ground_github(context, db)
        mcp_repos = None
        github_source = "connector"
        if mcp_enabled() or connector is None:
            mcp_repos, github_source = await list_github_repos_prefer_mcp(context, db, per_page=5)

        if connector is None and not mcp_repos:
            return self._no_data_result(
                context,
                "GitHub not connected. Connect a GitHub account in Tool Registry.",
                missing_tools=["GitHub"],
            )

        owner, repo_name, full = _parse_repo_parts(params)
        pr_number = _parse_pr_number(params)
        evidence: list[dict] = []
        grounding = "live" if connector is not None else "partial"

        try:
            if pr_number and owner and repo_name:
                if connector is None:
                    return self._no_data_result(
                        context,
                        "GitHub connector required for PR detail; MCP repo list alone is not enough.",
                        missing_tools=["GitHub"],
                        details={"github_source": github_source},
                    )
                pr = await connector.get_pull_request(owner, repo_name, int(pr_number))
                files = await connector.list_pull_request_files(
                    owner, repo_name, int(pr_number)
                )
                if not pr:
                    return self._result(
                        context,
                        status="failed",
                        summary=f"PR #{pr_number} not found in {owner}/{repo_name}.",
                        details={"reason": "pr_not_found"},
                        grounding="live",
                        confidence=0.9,
                        errors=["pr_not_found"],
                        evidence=[
                            self._evidence(
                                type="github_pr",
                                title=f"PR #{pr_number} missing",
                                source="github",
                                snippet=f"{owner}/{repo_name}",
                            )
                        ],
                    )
                evidence.append(
                    self._evidence(
                        type="github_pr",
                        title=f"PR #{pr_number}: {pr.get('title') or ''}",
                        source="github",
                        url=pr.get("html_url"),
                        snippet=json.dumps(
                            {
                                "number": pr_number,
                                "state": pr.get("state"),
                                "user": pr.get("user"),
                                "additions": pr.get("additions"),
                                "deletions": pr.get("deletions"),
                            },
                            default=str,
                        )[:1500],
                    )
                )
                for f in files[:20]:
                    evidence.append(
                        self._evidence(
                            type="github_file",
                            title=str(f.get("filename") or "file"),
                            source="github",
                            snippet=json.dumps(
                                {
                                    "status": f.get("status"),
                                    "changes": f.get("changes"),
                                    "additions": f.get("additions"),
                                    "deletions": f.get("deletions"),
                                },
                                default=str,
                            )[:800],
                        )
                    )
                facts = {
                    "mode": "single_pr",
                    "repo": f"{owner}/{repo_name}",
                    "pr": pr,
                    "files": files[:40],
                    "file_count": len(files),
                    "github_source": github_source,
                }
                raw = await self._call_llm(
                    "Summarize this PR review from evidence only. "
                    "Return JSON: summary, findings (list of strings), risk_level, details.",
                    context,
                    evidence=evidence,
                )
                parsed = self._parse_llm_json(raw)
                findings = parsed.get("findings") or []
                for finding in findings[:15]:
                    evidence.append(
                        self._evidence(
                            type="finding",
                            title=str(finding)[:200],
                            source="llm_from_evidence",
                            snippet=str(finding)[:500],
                        )
                    )
                review_body = str(
                    parsed.get("summary")
                    or f"Automated review for PR #{pr_number}"
                )
                if findings:
                    review_body += "\n\nFindings:\n" + "\n".join(
                        f"- {f}" for f in findings[:20]
                    )
                if bool(params.get("propose", True)):
                    return self._propose_artifact_result(
                        context,
                        connector="github",
                        method="add_pr_review",
                        params={
                            "repo": f"{owner}/{repo_name}",
                            "pr_number": int(pr_number),
                            "body": review_body,
                            "event": params.get("review_event") or "COMMENT",
                        },
                        preview={
                            "type": "github_pr_review",
                            "repo": f"{owner}/{repo_name}",
                            "pr_number": int(pr_number),
                            "body": review_body[:4000],
                            "event": params.get("review_event") or "COMMENT",
                        },
                        grounding="live",
                        summary=f"Propose PR review comments on #{pr_number} ({owner}/{repo_name})",
                        details={
                            "github_facts": facts,
                            "findings": findings,
                            "pr_number": pr_number,
                            "repo": f"{owner}/{repo_name}",
                        },
                        evidence=evidence,
                    )
                return self._result(
                    context,
                    status="success",
                    summary=str(
                        parsed.get("summary")
                        or f"Reviewed PR #{pr_number} in {owner}/{repo_name}"
                    ),
                    details={
                        "github_facts": facts,
                        "findings": findings,
                        "risk_level": parsed.get("risk_level"),
                        "llm": parsed.get("details")
                        if isinstance(parsed.get("details"), dict)
                        else {},
                    },
                    evidence=evidence,
                    grounding="live",
                    confidence=0.85,
                )

            repo = full
            if not repo:
                # Only use repos returned from live MCP/connector — never invent names.
                if mcp_repos:
                    repo = str(mcp_repos[0].get("full_name") or "")
                    grounding = "partial"
                elif connector is not None:
                    repos = await connector.list_repos(per_page=5)
                    if repos:
                        repo = str(repos[0].get("full_name") or "")
            if not repo:
                return self._no_data_result(
                    context,
                    "No repository specified and none available from GitHub. "
                    "Pass owner/repo or connect GitHub with visible repos.",
                    missing_tools=["GitHub"],
                )

            if connector is None:
                return self._no_data_result(
                    context,
                    "GitHub connector required to list pull requests.",
                    missing_tools=["GitHub"],
                )

            prs = await connector.list_pull_requests(repo, state="open", per_page=20)
        except GitHubAPIError as exc:
            return self._result(
                context,
                status="failed",
                summary=f"GitHub API error: {exc.message}",
                details={"error_type": exc.error_type, "repo": full or repo_name},
                grounding="none",
                confidence=0.0,
                errors=[exc.message],
            )
        except Exception as exc:
            return self._result(
                context,
                status="failed",
                summary="Failed to fetch pull requests from GitHub.",
                details={"error": str(exc)[:200], "repo": full or repo_name},
                grounding="none",
                confidence=0.0,
                errors=[str(exc)[:200]],
            )

        by_author: dict[str, int] = {}
        ages: list[int] = []
        for pr in prs:
            author = pr.get("user") or "unknown"
            by_author[author] = by_author.get(author, 0) + 1
            created = pr.get("created_at")
            if created:
                try:
                    dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
                    ages.append((datetime.now(timezone.utc) - dt).days)
                except ValueError:
                    pass
            evidence.append(
                self._evidence(
                    type="github_pr",
                    title=f"PR #{pr.get('number')}: {pr.get('title') or ''}",
                    source="github",
                    url=pr.get("html_url"),
                    snippet=json.dumps(
                        {
                            "user": pr.get("user"),
                            "created_at": pr.get("created_at"),
                            "draft": pr.get("draft"),
                        },
                        default=str,
                    )[:800],
                )
            )
        oldest_age = max(ages) if ages else 0

        facts = {
            "mode": "pr_list",
            "repo": repo,
            "total_open_prs": len(prs),
            "by_author": by_author,
            "oldest_pr_age_days": oldest_age,
            "prs": prs[:20],
        }
        try:
            raw = await self._call_llm(
                "Summarize open PR hygiene from evidence only. "
                "Return JSON: summary, findings (list), details.",
                context,
                evidence=evidence,
            )
            parsed = self._parse_llm_json(raw)
            summary = str(parsed.get("summary") or f"{len(prs)} open PRs in {repo}")
            llm_details = (
                parsed.get("details")
                if isinstance(parsed.get("details"), dict)
                else {}
            )
            findings = parsed.get("findings") or []
        except Exception:
            summary = f"{len(prs)} open PRs in {repo}"
            llm_details = {}
            findings = []

        for finding in findings[:15]:
            evidence.append(
                self._evidence(
                    type="finding",
                    title=str(finding)[:200],
                    source="llm_from_evidence",
                    snippet=str(finding)[:500],
                )
            )

        return self._result(
            context,
            status="success",
            summary=summary,
            details={
                "github_facts": facts,
                "findings": findings,
                "llm": llm_details,
                "total_open_prs": len(prs),
                "oldest_pr_age_days": oldest_age,
                "by_author": by_author,
                "prs": prs[:30],
                "repo": repo,
            },
            evidence=evidence,
            grounding=grounding,
            confidence=0.8 if prs else 0.6,
        )


code_review_agent = CodeReviewAgent()
