"""Pipeline monitor agent — failed GitHub workflow runs."""

from __future__ import annotations

import re
from collections import defaultdict

from sqlmodel import Session, select

from ..connectors.github_connector import GitHubConnector
from ..context import PlatformContext
from ..routers.catalog import CatalogEntity
from .base import BaseAgent

_ACCOUNT: dict = {}


class PipelineMonitorAgent(BaseAgent):
    name = "pipeline_monitor_agent"
    description = "Monitors CI/CD pipeline status and failures."
    requires_approval_envs = []
    primary_tools = ["Jenkins", "CircleCI", "GitHub Actions", "ArgoCD"]
    read_only = True

    async def _repos(self, params: dict, db: Session) -> list[str]:
        if params.get("repo"):
            return [params["repo"]]
        repos = []
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
        return repos or ["org/service"]

    async def run(self, params: dict, context: PlatformContext, db: Session):
        gh = GitHubConnector(_ACCOUNT)
        repos = await self._repos(params, db)
        failures: list = []
        by_repo: dict[str, list] = defaultdict(list)
        by_workflow: dict[str, int] = defaultdict(int)

        for repo in repos:
            try:
                runs = await gh.list_workflow_runs(repo, status="failure")
                for run in runs:
                    run["repo"] = repo
                    failures.append(run)
                    by_repo[repo].append(run)
                    by_workflow[run.get("name") or "unknown"] += 1
            except Exception:
                continue

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
            },
        )


pipeline_monitor_agent = PipelineMonitorAgent()
