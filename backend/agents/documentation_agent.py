"""Documentation agent — README freshness and generation."""

from __future__ import annotations

import re
from datetime import datetime, timezone, timedelta

from sqlmodel import Session, select

from ..connectors.github_connector import GitHubConnector
from ..context import PlatformContext
from ..routers.catalog import CatalogEntity
from .base import BaseAgent

_ACCOUNT: dict = {}


def _detect_doc_action(task: str, params: dict) -> str:
    text = (params.get("task") or params.get("message") or task or "").lower()
    if re.search(r"\bgenerate|write|create\b", text):
        return "generate"
    if re.search(r"\bstale|staleness|outdated\b", text):
        return "check_staleness"
    return "show"


def _repo_from_entity(ent: CatalogEntity) -> str | None:
    url = ent.repo_url or ""
    m = re.search(r"github\.com[/:]([\w.-]+/[\w.-]+)", url)
    return m.group(1).replace(".git", "") if m else None


class DocumentationAgent(BaseAgent):
    name = "documentation_agent"
    description = "Generates and updates service documentation from catalog entities."
    requires_approval_envs = []
    primary_tools = ["Confluence", "GitHub", "Catalog DB"]
    read_only = True

    async def run(self, params: dict, context: PlatformContext, db: Session):
        task = str(params.get("task") or params.get("message") or "")
        action = _detect_doc_action(task, params)
        repo = params.get("repo")
        gh = GitHubConnector(_ACCOUNT)
        stale_repos: list = []
        repos_checked = 0
        cutoff = datetime.now(timezone.utc) - timedelta(days=30)

        if action == "generate":
            return self._build_result(
                context,
                status="pending_approval",
                summary=f"Generate documentation for {repo or 'catalog services'}",
                details={
                    "repos_checked": 0,
                    "stale_count": 0,
                    "stale_repos": [],
                    "action": "generate",
                },
                requires_approval=True,
                approval_payload={"action": "generate_docs", "repo": repo, "task": task},
            )

        entities: list = []
        try:
            entities = list(
                db.exec(select(CatalogEntity).where(CatalogEntity.is_active == 1)).all()
            )
        except Exception:
            entities = []

        target_repos = [repo] if repo else []
        if not target_repos:
            target_repos = [r for e in entities if (r := _repo_from_entity(e))]

        for r in target_repos[:20]:
            repos_checked += 1
            try:
                if action == "show":
                    content = await gh.get_readme(r)
                    if not content:
                        stale_repos.append({"repo": r, "reason": "missing_readme"})
                    continue

                ent = next((e for e in entities if _repo_from_entity(e) == r), None)
                docs_updated = getattr(ent, "updated_at", None) or getattr(ent, "created_at", None)
                if docs_updated and docs_updated.tzinfo is None:
                    docs_updated = docs_updated.replace(tzinfo=timezone.utc)
                readme = await gh.get_readme(r)
                is_stale = not readme
                if docs_updated and docs_updated < cutoff:
                    is_stale = True
                if is_stale:
                    stale_repos.append(
                        {
                            "repo": r,
                            "docs_updated_at": docs_updated.isoformat() if docs_updated else None,
                            "has_readme": bool(readme),
                        }
                    )
            except Exception:
                stale_repos.append({"repo": r, "reason": "check_failed"})

        return self._build_result(
            context,
            status="success",
            summary=f"Documentation {action}: {len(stale_repos)} stale of {repos_checked} repos",
            details={
                "repos_checked": repos_checked,
                "stale_count": len(stale_repos),
                "stale_repos": stale_repos,
                "action": action,
            },
        )


documentation_agent = DocumentationAgent()
