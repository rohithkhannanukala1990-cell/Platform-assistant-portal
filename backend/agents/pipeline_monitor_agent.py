"""Pipeline monitor agent — failed GitHub workflow runs (grounded)."""

from __future__ import annotations

import json
import re
from collections import defaultdict

from sqlmodel import Session, select

from ..connectors.github_connector import GitHubAPIError
from ..context import PlatformContext
from ..routers.catalog import CatalogEntity
from .base import AgentResult, BaseAgent


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

    async def run(self, params: dict, context: PlatformContext, db: Session) -> AgentResult:
        connector = await self._ground_github(context, db)
        if connector is None:
            return self._no_data_result(
                context,
                "GitHub not connected. Connect a GitHub account in Tool Registry.",
                missing_tools=["GitHub Actions", "GitHub"],
            )

        repos = await self._repos(params, db, connector, context)
        run_id = self._run_id(params)
        evidence: list[dict] = []

        if run_id and repos:
            full = repos[0]
            owner, _, repo_name = full.partition("/")
            if not owner or not repo_name:
                return self._result(
                    context,
                    status="failed",
                    summary="Repository must be owner/repo to load workflow jobs.",
                    details={"reason": "bad_repo"},
                    grounding="none",
                    confidence=0.0,
                    errors=["bad_repo"],
                )
            try:
                run = await connector.get_workflow_run(owner, repo_name, run_id)
                jobs = await connector.list_workflow_run_jobs(owner, repo_name, run_id)
            except GitHubAPIError as exc:
                return self._result(
                    context,
                    status="failed",
                    summary=f"GitHub API error: {exc.message}",
                    details={"error_type": exc.error_type},
                    grounding="none",
                    confidence=0.0,
                    errors=[exc.message],
                )
            except Exception as exc:
                return self._result(
                    context,
                    status="failed",
                    summary="Failed to load workflow run jobs from GitHub.",
                    details={"error": str(exc)[:200]},
                    grounding="none",
                    confidence=0.0,
                    errors=[str(exc)[:200]],
                )

            failed_jobs = [
                j
                for j in jobs
                if str(j.get("conclusion") or "").lower() == "failure"
                or str(j.get("status") or "").lower() == "failure"
            ]
            evidence.append(
                self._evidence(
                    type="workflow_run",
                    title=f"Run {run_id}: {run.get('name') or ''}",
                    source="github_actions",
                    url=run.get("html_url"),
                    snippet=json.dumps(
                        {
                            "run_id": run_id,
                            "conclusion": run.get("conclusion"),
                            "status": run.get("status"),
                            "html_url": run.get("html_url"),
                        },
                        default=str,
                    )[:1200],
                )
            )
            for job in failed_jobs[:15]:
                steps = job.get("steps") or []
                failed_steps = [
                    s
                    for s in steps
                    if str(s.get("conclusion") or "").lower() == "failure"
                ]
                excerpt = failed_steps[0] if failed_steps else (steps[-1] if steps else {})
                evidence.append(
                    self._evidence(
                        type="failed_job",
                        title=str(job.get("name") or "job"),
                        source="github_actions",
                        url=job.get("html_url") or run.get("html_url"),
                        snippet=json.dumps(
                            {
                                "job": job.get("name"),
                                "conclusion": job.get("conclusion"),
                                "failed_step": excerpt.get("name") if isinstance(excerpt, dict) else None,
                                "step_conclusion": excerpt.get("conclusion")
                                if isinstance(excerpt, dict)
                                else None,
                                "html_url": job.get("html_url"),
                            },
                            default=str,
                        )[:1500],
                    )
                )

            facts = {
                "mode": "single_run",
                "repo": full,
                "run": run,
                "jobs": jobs[:40],
                "failed_jobs": failed_jobs[:20],
            }
            try:
                raw = await self._call_llm(
                    "Triage this CI run from evidence only. "
                    "Return JSON: summary, findings (list), details.",
                    context,
                    evidence=evidence,
                )
                parsed = self._parse_llm_json(raw)
                summary = str(
                    parsed.get("summary")
                    or f"Triage for Actions run {run_id} on {full}"
                )
                findings = parsed.get("findings") or []
            except Exception:
                summary = f"Run {run_id} on {full}: {len(failed_jobs)} failed jobs"
                findings = [f"{j.get('name')}: {j.get('conclusion')}" for j in failed_jobs[:10]]

            return self._result(
                context,
                status="success",
                summary=summary,
                details={
                    "github_facts": facts,
                    "findings": findings,
                    "failed_job_count": len(failed_jobs),
                    "source": "github",
                },
                evidence=evidence,
                grounding="live",
                confidence=0.85,
            )

        if not repos:
            return self._no_data_result(
                context,
                "No repositories available to monitor. Pass repo=owner/name or connect catalog/GitHub.",
                missing_tools=["GitHub Actions"],
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
                    evidence.append(
                        self._evidence(
                            type="workflow_run",
                            title=f"{repo}: {run.get('name') or 'run'} #{run.get('id')}",
                            source="github_actions",
                            url=run.get("html_url"),
                            snippet=json.dumps(
                                {
                                    "run_id": run.get("id"),
                                    "conclusion": run.get("conclusion"),
                                    "html_url": run.get("html_url"),
                                    "head_branch": run.get("head_branch"),
                                },
                                default=str,
                            )[:1000],
                        )
                    )
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
            return self._result(
                context,
                status="failed",
                summary="Failed to fetch workflow runs from GitHub.",
                details={"errors": errors[:10], "failures": []},
                grounding="none",
                confidence=0.0,
                errors=[e.get("message") or e.get("error_type") or "error" for e in errors[:5]],
            )

        grounding = "live" if failures or not errors else "partial"
        return self._result(
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
            evidence=evidence,
            grounding=grounding,
            confidence=0.8 if failures else 0.65,
            errors=[e.get("message") or "" for e in errors[:5] if e.get("message")],
        )


pipeline_monitor_agent = PipelineMonitorAgent()
