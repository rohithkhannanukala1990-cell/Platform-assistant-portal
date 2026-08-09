"""QA / test failure analysis agent (grounded on GitHub CI)."""

from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from collections import Counter

from sqlmodel import Session, select

from ..context import PlatformContext
from ..routers.catalog import CatalogEntity
from .base import AgentResult, BaseAgent

TESTER_SYSTEM_PROMPT = """
You are TesterAgent — analyze test failures and return ONLY valid JSON with:
summary, commands (test retry commands), details, requires_approval (true for production).
"""

TESTER_SOURCES = {
    "cypress", "playwright", "jest", "pytest", "testng",
    "codecov", "sonarqube", "sonar", "testrail", "coverage",
}

TEST_KEYWORDS = ("pytest", "jest", "cypress", "playwright", "testng")

COVERAGE_PATHS = (
    "coverage/coverage-summary.json",
    ".coverage",
    "coverage.xml",
)


def is_tester_source(source: str) -> bool:
    return source.lower() in TESTER_SOURCES or "test" in source.lower()


def _detect_intent(task: str) -> str:
    t = (task or "").lower()
    if any(k in t for k in ("retry", "rerun", "re-run", "run again")):
        return "retry"
    if any(k in t for k in ("coverage", "codecov", "cover percent", "test coverage")):
        return "coverage"
    return "list_failures"


def _is_test_run(name: str) -> bool:
    lower = (name or "").lower()
    return any(kw in lower for kw in TEST_KEYWORDS) or "test" in lower


def _parse_coverage_pct(content: str, path: str) -> float | None:
    if not content:
        return None
    path_lower = path.lower()
    try:
        if path_lower.endswith(".json"):
            data = json.loads(content)
            total = data.get("total") if isinstance(data, dict) else None
            if isinstance(total, dict):
                for key in ("lines", "statements", "branches", "functions"):
                    block = total.get(key)
                    if isinstance(block, dict) and block.get("pct") is not None:
                        return float(block["pct"])
            for val in data.values() if isinstance(data, dict) else []:
                if isinstance(val, dict) and "lines" in val:
                    pct = val["lines"].get("pct")
                    if pct is not None:
                        return float(pct)
        elif path_lower.endswith(".xml"):
            root = ET.fromstring(content)
            rate = root.attrib.get("line-rate")
            if rate is not None:
                return round(float(rate) * 100, 2)
        elif ".coverage" in path_lower:
            for line in content.splitlines():
                if "TOTAL" in line.upper():
                    nums = re.findall(r"(\d+(?:\.\d+)?)\s*%", line)
                    if nums:
                        return float(nums[-1])
    except Exception:
        return None
    return None


class TesterAgent(BaseAgent):
    name = "tester_agent"
    description = "Runs and analyzes test suites via CI pipelines."
    requires_approval_envs = ["production"]
    primary_tools = ["GitHub Actions", "CircleCI", "Jenkins"]

    async def _resolve_repo(
        self,
        task: str,
        params: dict,
        context: PlatformContext,
        db: Session,
    ) -> str | None:
        """Resolve repo from params/catalog only — never invent org/service."""
        if params.get("repo"):
            return str(params["repo"]).strip()

        gh = context.tool_accounts.get("github")
        if isinstance(gh, str) and "/" in gh:
            return gh
        if isinstance(gh, dict) and gh.get("repo"):
            return str(gh["repo"])

        service = None
        for pattern in (
            r"(?:for|of|in|on)\s+([\w.-]+(?:-service|-api|[\w-]+))",
            r"([\w.-]+(?:-service|-api))",
        ):
            m = re.search(pattern, task or "", re.I)
            if m:
                service = m.group(1)
                break

        if service:
            try:
                for ent in db.exec(
                    select(CatalogEntity).where(CatalogEntity.is_active == 1)
                ).all():
                    name = (ent.name or "").lower()
                    url = (ent.repo_url or "").lower()
                    if service.lower() in name or service.lower() in url:
                        rm = re.search(r"github\.com[/:]([\w.-]+/[\w.-]+)", ent.repo_url or "")
                        if rm:
                            return rm.group(1).replace(".git", "")
            except Exception:
                pass

        owner = (params.get("owner") or "").strip()
        name = (params.get("repo_name") or "").strip()
        if owner and name:
            return f"{owner}/{name}"
        return None

    def _run_to_suite(self, run: dict) -> dict:
        return {
            "name": run.get("name") or "unknown",
            "status": run.get("conclusion") or run.get("status") or "failure",
            "branch": run.get("head_branch") or "",
            "failed_at": run.get("created_at") or "",
            "run_url": run.get("html_url") or "",
        }

    async def run(self, params: dict, context: PlatformContext, db: Session) -> AgentResult:
        params = params if isinstance(params, dict) else {}
        task = params.get("task") or params.get("message") or ""
        intent = _detect_intent(task)
        connector = await self._ground_github(context, db)
        if connector is None:
            return self._no_data_result(
                context,
                "GitHub not connected. Connect a GitHub account in Tool Registry.",
                missing_tools=["GitHub Actions", "GitHub"],
            )

        repo = await self._resolve_repo(task, params, context, db)
        if not repo:
            return self._no_data_result(
                context,
                "No repository specified. Pass repo=owner/name (no default org/service).",
                missing_tools=["GitHub Actions"],
            )

        details: dict = {
            "repo": repo,
            "total_failures": 0,
            "test_suites": [],
            "coverage_pct": None,
            "action": intent,
        }
        evidence: list[dict] = [
            self._evidence(
                type="repo",
                title=repo,
                source="github",
                snippet=f"intent={intent}",
            )
        ]

        if intent == "list_failures":
            runs: list[dict] = []
            try:
                runs = await connector.list_workflow_runs(
                    repo=repo,
                    status="failure",
                    per_page=20,
                )
            except Exception as exc:
                return self._result(
                    context,
                    status="failed",
                    summary=f"Failed to list workflow runs for {repo}",
                    details={**details, "error": str(exc)[:200]},
                    grounding="none",
                    confidence=0.0,
                    errors=[str(exc)[:200]],
                    evidence=evidence,
                )

            test_runs = [r for r in runs if _is_test_run(r.get("name") or "")]
            details["total_failures"] = len(test_runs)

            counts = Counter(r.get("name") or "unknown" for r in test_runs)
            latest_by_name: dict[str, dict] = {}
            for run in test_runs:
                name = run.get("name") or "unknown"
                if name not in latest_by_name:
                    latest_by_name[name] = run

            suites = []
            for name, _count in counts.most_common():
                suite = self._run_to_suite(latest_by_name[name])
                suites.append(suite)
                evidence.append(
                    self._evidence(
                        type="workflow_run",
                        title=suite["name"],
                        source="github_actions",
                        url=suite.get("run_url"),
                        snippet=json.dumps(suite, default=str)[:800],
                    )
                )
            details["test_suites"] = suites

            summary = (
                f"{details['total_failures']} failing test workflow runs in {repo}"
                if test_runs
                else f"No failing test workflows found in {repo}"
            )
            if bool(params.get("propose", True)) and test_runs:
                test_content = params.get("proposed_content") or (
                    "def test_uncovered_path():\n"
                    "    # Proposed coverage for previously uncovered path\n"
                    "    assert True\n"
                )
                path = params.get("path") or "tests/test_uncovered_path.py"
                branch = f"test/cover-{repo.replace('/', '-')}"[:40]
                return self._propose_artifact_result(
                    context,
                    connector="github",
                    method="github_dependency_pr",
                    params={
                        "repo": repo,
                        "path": path,
                        "content": test_content,
                        "branch_name": branch,
                        "base": params.get("base") or "main",
                        "title": f"test: cover uncovered path in {repo}",
                        "body": "Proposed test for uncovered code path from tester_agent.",
                    },
                    preview={
                        "type": "github_pr",
                        "repo": repo,
                        "path": path,
                        "branch": branch,
                        "diff_preview": test_content[:4000],
                    },
                    grounding="live",
                    summary=f"Propose test PR for uncovered path in {repo}",
                    details=details,
                    evidence=evidence,
                )
            return self._result(
                context,
                status="success",
                summary=summary,
                details=details,
                evidence=evidence,
                grounding="live",
                confidence=0.85,
            )

        if intent == "coverage":
            coverage_pct: float | None = None
            found_path = None
            for path in COVERAGE_PATHS:
                content = None
                try:
                    content = await connector.get_file_contents(repo, path)
                except Exception:
                    content = None
                if content:
                    coverage_pct = _parse_coverage_pct(content, path)
                    if coverage_pct is not None:
                        found_path = path
                        break

            details["coverage_pct"] = coverage_pct
            if coverage_pct is not None:
                evidence.append(
                    self._evidence(
                        type="coverage",
                        title=f"Coverage {coverage_pct:.1f}%",
                        source="github",
                        snippet=f"path={found_path}",
                    )
                )
                return self._result(
                    context,
                    status="success",
                    summary=f"Test coverage for {repo}: {coverage_pct:.1f}%",
                    details=details,
                    evidence=evidence,
                    grounding="live",
                    confidence=0.8,
                )
            return self._no_data_result(
                context,
                f"Could not find/parse coverage artifacts for {repo}",
                missing_tools=["GitHub"],
                details=details,
            )

        # retry
        target_run: dict | None = None
        try:
            runs = await connector.list_workflow_runs(
                repo=repo,
                status="failure",
                per_page=20,
            )
            test_runs = [r for r in runs if _is_test_run(r.get("name") or "")]
            target_run = test_runs[0] if test_runs else (runs[0] if runs else None)
        except Exception as exc:
            return self._result(
                context,
                status="failed",
                summary=f"Failed to load failed runs for retry in {repo}",
                details={**details, "error": str(exc)[:200]},
                grounding="none",
                confidence=0.0,
                errors=[str(exc)[:200]],
                evidence=evidence,
            )

        if not target_run:
            return self._no_data_result(
                context,
                f"No failed workflow run found to retry in {repo}",
                missing_tools=["GitHub Actions"],
                details=details,
            )

        workflow_id = target_run.get("id")
        details["test_suites"] = [self._run_to_suite(target_run)]
        details["total_failures"] = 1
        evidence.append(
            self._evidence(
                type="workflow_run",
                title=str(target_run.get("name") or workflow_id),
                source="github_actions",
                url=target_run.get("html_url"),
                snippet=json.dumps(self._run_to_suite(target_run), default=str),
            )
        )

        commands = [
            f"gh run rerun {workflow_id} --repo {repo}",
        ]
        return self._finalize_with_policy(
            context,
            summary=f"Retry plan for {target_run.get('name')} in {repo}",
            details=details,
            commands=commands,
            evidence=evidence,
            grounding="live",
            confidence=0.8,
            task=f"retry {repo}",
            recommended_actions=[
                {
                    "title": f"Rerun workflow {workflow_id}",
                    "risk": "medium",
                    "requires_approval": self._should_require_approval(context),
                }
            ],
        )


tester_agent = TesterAgent()
