"""Documentation agent — README freshness via GitHub connector (grounded)."""

from __future__ import annotations

import re
from datetime import datetime, timezone, timedelta

from sqlmodel import Session, select

from ..context import PlatformContext
from ..routers.catalog import CatalogEntity
from .base import AgentResult, BaseAgent


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

    async def run(self, params: dict, context: PlatformContext, db: Session) -> AgentResult:
        task = str(params.get("task") or params.get("message") or "")
        action = _detect_doc_action(task, params)
        repo = params.get("repo")
        evidence: list[dict] = []
        stale_repos: list = []
        repos_checked = 0
        cutoff = datetime.now(timezone.utc) - timedelta(days=30)

        connector = await self._ground_github(context, db)

        entities: list = []
        try:
            entities = list(
                db.exec(select(CatalogEntity).where(CatalogEntity.is_active == 1)).all()
            )
            for ent in entities[:30]:
                evidence.append(
                    self._evidence(
                        type="catalog_entity",
                        title=ent.name,
                        source="catalog_db",
                        snippet=f"repo_url={ent.repo_url or ''}",
                    )
                )
        except Exception as exc:
            return self._result(
                context,
                status="failed",
                summary="Catalog DB query failed for documentation agent",
                details={"error": str(exc)[:300]},
                grounding="none",
                confidence=0.0,
                errors=[str(exc)[:300]],
            )

        if action == "generate":
            if not repo and not entities:
                return self._no_data_result(
                    context,
                    "No repo or catalog entities available to generate documentation.",
                    missing_tools=["GitHub", "Catalog DB"],
                )
            grounding = "partial" if entities else "none"
            if connector and repo:
                try:
                    readme = await connector.get_readme(str(repo))
                    if readme:
                        evidence.append(
                            self._evidence(
                                type="readme",
                                title=f"README {repo}",
                                source="github",
                                snippet=str(readme)[:1500],
                            )
                        )
                        grounding = "live"
                except Exception:
                    pass
            draft = None
            if evidence:
                try:
                    raw = await self._call_llm(
                        "Generate documentation outline from evidence only.",
                        context,
                        evidence=evidence,
                    )
                    draft = self._parse_llm_json(raw)
                except Exception:
                    draft = None
            return self._result(
                context,
                status="pending_approval",
                summary=f"Generate documentation for {repo or 'catalog services'}",
                details={
                    "repos_checked": 0,
                    "stale_count": 0,
                    "stale_repos": [],
                    "action": "generate",
                    "draft": draft,
                },
                requires_approval=True,
                approval_payload={"action": "generate_docs", "repo": repo, "task": task},
                evidence=evidence,
                grounding=grounding,
                confidence=0.55,
            )

        # Need GitHub for README checks when repos are known.
        target_repos = [repo] if repo else []
        if not target_repos:
            target_repos = [r for e in entities if (r := _repo_from_entity(e))]

        if not target_repos:
            if entities:
                return self._result(
                    context,
                    status="success",
                    summary="Catalog entities found but no GitHub repo URLs to check READMEs",
                    details={
                        "repos_checked": 0,
                        "stale_count": 0,
                        "stale_repos": [],
                        "action": action,
                        "catalog_only": True,
                    },
                    evidence=evidence,
                    grounding="partial",
                    confidence=0.6,
                )
            return self._no_data_result(
                context,
                "No repository known for documentation check. Pass repo= or populate catalog.",
                missing_tools=["GitHub", "Catalog DB"],
            )

        if connector is None:
            return self._result(
                context,
                status="success",
                summary=(
                    f"GitHub not connected; returning catalog-only doc status "
                    f"for {len(target_repos)} repo URL(s)"
                ),
                details={
                    "repos_checked": 0,
                    "stale_count": 0,
                    "stale_repos": [{"repo": r, "reason": "github_not_connected"} for r in target_repos[:20]],
                    "action": action,
                    "catalog_only": True,
                },
                evidence=evidence,
                grounding="partial",
                confidence=0.5,
                recommended_actions=[
                    {
                        "title": "Connect GitHub in Tool Registry",
                        "risk": "low",
                        "requires_approval": False,
                    }
                ],
            )

        for r in target_repos[:20]:
            repos_checked += 1
            try:
                if action == "show":
                    content = await connector.get_readme(r)
                    evidence.append(
                        self._evidence(
                            type="readme",
                            title=f"README {r}",
                            source="github",
                            snippet=(content or "")[:1500] or "missing_readme",
                        )
                    )
                    if not content:
                        stale_repos.append({"repo": r, "reason": "missing_readme"})
                    continue

                ent = next((e for e in entities if _repo_from_entity(e) == r), None)
                docs_updated = getattr(ent, "updated_at", None) or getattr(ent, "created_at", None)
                if docs_updated and docs_updated.tzinfo is None:
                    docs_updated = docs_updated.replace(tzinfo=timezone.utc)
                readme = await connector.get_readme(r)
                evidence.append(
                    self._evidence(
                        type="readme",
                        title=f"README {r}",
                        source="github",
                        snippet=(readme or "")[:1000] or "missing_readme",
                    )
                )
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
            except Exception as exc:
                stale_repos.append({"repo": r, "reason": "check_failed", "error": str(exc)[:100]})

        return self._result(
            context,
            status="success",
            summary=f"Documentation {action}: {len(stale_repos)} stale of {repos_checked} repos",
            details={
                "repos_checked": repos_checked,
                "stale_count": len(stale_repos),
                "stale_repos": stale_repos,
                "action": action,
            },
            evidence=evidence,
            grounding="live",
            confidence=0.8,
        )


documentation_agent = DocumentationAgent()
