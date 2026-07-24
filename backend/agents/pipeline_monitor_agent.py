"""Pipeline monitor agent — failed GitHub workflow runs."""

from __future__ import annotations

import re
from collections import defaultdict

from sqlmodel import Session, select

from ..connectors.github_connector import GitHubAPIError
from ..context import PlatformContext
from ..routers.catalog import CatalogEntity
from ..services.demo_fixtures import demo_data_enabled
from ..services.github_access import try_github_connector_from_context
from .base import BaseAgent


class PipelineMonitorAgent(BaseAgent):
    name = "pipeline_monitor_agent"
    description = "Monitors CI/CD pipeline status and failures."
    requires_approval_envs = []
    primary_tools = ["Jenkins", "CircleCI", "GitHub Actions", "ArgoCD"]
    read_only = True

    async def _repos(self, params: dict, db: Session, connector) -> list[str]:
        if params.get("repo"):
            return [str(params["repo"]).strip()]
        repos: list[str] = []
        try:
            for ent in db.exec(
                select(CatalogEntity).where(CatalogEntity.is_active == 1)
            ).all():
                url = ent.repo_url or ""
                m = re.search(r"github\.com[/:]([\w.-]+/[\w.-]+)", url)
                if m:
                    repos.append(m.group(1).replace(".git", ""))
        except Exception:
            pass
        if repos:
            return repos
        try:
            listed = await connector.list_repos(per_page=10)
            return [
                str(r.get("full_name"))
                for r in listed
                if isinstance(r, dict) and r.get("full_name")
            ]
        except Exception:
            return []

    async def run(self, params: dict, context: PlatformContext, db: Session):
        connector = try_github_connector_from_context(context, db=db)
        if connector is None:
            if demo_data_enabled():
                return self._build_result(
                    context,
                    status="success",
                    summary="0 failed workflow runs (demo mode; connect GitHub for live data)",
                    details={
                        "total_failures": 0,
                        "repos_affected": [],
                        "failures": [],
                        "by_workflow": {},
                        "by_repo": {},
                        "source": "demo",
                    },
                )
            return self._build_result(
                context,
                status="skipped",
                summary="GitHub connection is required. Connect a GitHub account in Tool Registry.",
                details={"reason": "github_not_configured", "failures": []},
            )

        repos = await self._repos(params, db, connector)
        if not repos:
            return self._build_result(
                context,
                status="success",
                summary="No repositories available to monitor.",
                details={
                    "total_failures": 0,
                    "repos_affected": [],
                    "failures": [],
                    "by_workflow": {},
                    "by_repo": {},
                },
            )

        failures: list = []
        by_repo: dict[str, list] = defaultdict(list)
        by_workflow: dict[str, int] = defaultdict(int)
        errors: list[dict] = []

        for repo in repos:
            try:
                runs = await connector.list_workflow_runs(
                    repo, status="failure", per_page=20
                )
                for run in runs:
                    run["repo"] = repo
                    failures.append(run)
                    by_repo[repo].append(run)
                    by_workflow[run.get("name") or "unknown"] += 1
            except GitHubAPIError as exc:
                errors.append(
                    {
                        "repo": repo,
                        "error_type": exc.error_type,
                        "message": exc.message,
                    }
                )
            except Exception as exc:
                errors.append({"repo": repo, "message": str(exc)[:200]})

        if not failures and errors and not any(by_repo):
            return self._build_result(
                context,
                status="failed",
                summary="Failed to fetch workflow runs from GitHub.",
                details={"errors": errors[:10], "failures": []},
            )

        return self._build_result(
            context,
            status="success",
            summary=f"{len(failures)} failed workflow runs across {len(by_repo)} repos",
            details={
                "total_failures": len(failures),
                "repos_affected": list(by_repo.keys()),
                "failures": failures[:50],
                "by_workflow": dict(by_workflow),
                "by_repo": {k: len(v) for k, v in by_repo.items()},
                "errors": errors[:10],
                "source": "github",
            },
        )


pipeline_monitor_agent = PipelineMonitorAgent()
