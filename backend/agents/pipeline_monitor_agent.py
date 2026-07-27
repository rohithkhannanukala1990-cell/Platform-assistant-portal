"""Pipeline monitor agent — failed GitHub workflow runs."""

from __future__ import annotations

import json
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

    async def _repos(self, params: dict, db: Session, connector, context: PlatformContext) -> list[str]:
        if params.get("repo"):
            repo = str(params["repo"]).strip()
            owner = (params.get("owner") or "").strip()
            if owner and "/" not in repo:
                return [f"{owner}/{repo}"]
            return [repo]
        task = str(params.get("task") or "")
        m = re.search(r"([\w.-]+)/([\w.-]+)", task)
        if m:
            return [f"{m.group(1)}/{m.group(2)}"]
        repos: list[str] = []
        try:
            for ent in db.exec(
                select(CatalogEntity).where(CatalogEntity.is_active == 1)
            ).all():
                url = ent.repo_url or ""
                match = re.search(r"github\.com[/:]([\w.-]+/[\w.-]+)", url)
                if match:
                    repos.append(match.group(1).replace(".git", ""))
        except Exception:
            pass
        if repos:
            return repos

        from ..mcp.agent_mcp import list_github_repos_prefer_mcp, mcp_enabled

        if mcp_enabled() or connector is not None:
            listed, _source = await list_github_repos_prefer_mcp(context, db, per_page=10)
            if listed:
                return [
                    str(r.get("full_name"))
                    for r in listed
                    if isinstance(r, dict) and r.get("full_name")
                ]
        if connector is not None:
            try:
                listed = await connector.list_repos(per_page=10)
                return [
                    str(r.get("full_name"))
                    for r in listed
                    if isinstance(r, dict) and r.get("full_name")
                ]
            except Exception:
                return []
        return []

    def _run_id(self, params: dict) -> int | None:
        raw = params.get("run_id") or params.get("workflow_run_id")
        if raw is not None and str(raw).strip():
            try:
                return int(raw)
            except (TypeError, ValueError):
                pass
        task = str(params.get("task") or "")
        m = re.search(r"\brun(?:_id)?\s*[#:]?\s*(\d+)", task, re.I)
        if m:
            return int(m.group(1))
        return None

    async def run(self, params: dict, context: PlatformContext, db: Session):
        connector = try_github_connector_from_context(context, db=db)
        if connector is None:
            if demo_data_enabled():
                return self._build_result(
                    context,
                    status="skipped",
                    summary="GitHub not connected. Connect a GitHub account in Tool Registry.",
                    details={
                        "reason": "github_not_configured",
                        "total_failures": 0,
                        "failures": [],
                        "source": "not_connected",
                    },
                )
            return self._build_result(
                context,
                status="skipped",
                summary="GitHub not connected. Connect a GitHub account in Tool Registry.",
                details={"reason": "github_not_configured", "failures": []},
            )

        repos = await self._repos(params, db, connector, context)
        run_id = self._run_id(params)

        # Single failed-run triage with jobs
        if run_id and repos:
            full = repos[0]
            owner, _, repo_name = full.partition("/")
            if not owner or not repo_name:
                return self._build_result(
                    context,
                    status="failed",
                    summary="Repository must be owner/repo to load workflow jobs.",
                    details={"reason": "bad_repo"},
                )
            try:
                run = await connector.get_workflow_run(owner, repo_name, run_id)
                jobs = await connector.list_workflow_run_jobs(owner, repo_name, run_id)
            except GitHubAPIError as exc:
                return self._build_result(
                    context,
                    status="failed",
                    summary=f"GitHub API error: {exc.message}",
                    details={"error_type": exc.error_type},
                )
            except Exception as exc:
                return self._build_result(
                    context,
                    status="failed",
                    summary="Failed to load workflow run jobs from GitHub.",
                    details={"error": str(exc)[:200]},
                )

            failed_jobs = [
                j
                for j in jobs
                if str(j.get("conclusion") or "").lower() == "failure"
                or str(j.get("status") or "").lower() == "failure"
            ]
            facts = {
                "mode": "single_run",
                "repo": full,
                "run": run,
                "jobs": jobs[:40],
                "failed_jobs": failed_jobs[:20],
            }
            prompt = (
                "You are a CI triage assistant. Ground analysis ONLY on these GitHub "
                "Actions facts (do not invent jobs or logs):\n"
                f"{json.dumps(facts, default=str)[:6000]}\n"
                "Return JSON with keys: summary (string), findings (list of strings), "
                "details (object)."
            )
            try:
                raw = await self._call_llm(prompt, context)
                parsed = self._parse_llm_json(raw)
                summary = str(
                    parsed.get("summary")
                    or f"Triage for Actions run {run_id} on {full}"
                )
                findings = parsed.get("findings") or []
            except Exception:
                summary = f"Run {run_id} on {full}: {len(failed_jobs)} failed jobs"
                findings = [f"{j.get('name')}: {j.get('conclusion')}" for j in failed_jobs[:10]]

            return self._build_result(
                context,
                status="success",
                summary=summary,
                details={
                    "github_facts": facts,
                    "findings": findings,
                    "failed_job_count": len(failed_jobs),
                    "source": "github",
                },
            )

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
