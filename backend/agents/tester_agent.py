"""QA / test failure analysis agent."""

from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from collections import Counter

from sqlmodel import Session, select

from ..connectors.github_connector import GitHubConnector
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

_ACCOUNT: dict = {}


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
    ) -> str:
        if params.get("repo"):
            return str(params["repo"])

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
            return f"org/{service}"

        return "org/service"

    def _run_to_suite(self, run: dict) -> dict:
        return {
            "name": run.get("name") or "unknown",
            "status": run.get("conclusion") or run.get("status") or "failure",
            "branch": run.get("head_branch") or "",
            "failed_at": run.get("created_at") or "",
            "run_url": run.get("html_url") or "",
        }

    async def run(self, params: dict, context: PlatformContext, db: Session) -> AgentResult:
        task = params.get("task") or params.get("message") or ""
        intent = _detect_intent(task)
        repo = await self._resolve_repo(task, params, context, db)
        gh = GitHubConnector(_ACCOUNT)

        details: dict = {
            "repo": repo,
            "total_failures": 0,
            "test_suites": [],
            "coverage_pct": None,
            "action": intent,
        }

        if intent == "list_failures":
            runs: list[dict] = []
            try:
                runs = await gh.list_workflow_runs(
                    repo=repo,
                    status="failure",
                    per_page=20,
                )
            except Exception:
                runs = []

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
                suites.append(self._run_to_suite(latest_by_name[name]))
            details["test_suites"] = suites

            summary = (
                f"{details['total_failures']} failing test workflow runs in {repo}"
                if test_runs
                else f"No failing test workflows found in {repo}"
            )
            return self._build_result(
                context,
                status="success",
                summary=summary,
                details=details,
            )

        if intent == "coverage":
            coverage_pct: float | None = None
            for path in COVERAGE_PATHS:
                content = None
                try:
                    content = await gh.get_file_contents(repo, path)
                except Exception:
                    content = None
                if content:
                    coverage_pct = _parse_coverage_pct(content, path)
                    if coverage_pct is not None:
                        break

            details["coverage_pct"] = coverage_pct
            if coverage_pct is not None:
                summary = f"Test coverage for {repo}: {coverage_pct:.1f}%"
                status = "success"
            else:
                summary = f"Could not parse coverage data for {repo}"
                status = "failed"

            return self._build_result(
                context,
                status=status,
                summary=summary,
                details=details,
            )

        # retry
        target_run: dict | None = None
        try:
            runs = await gh.list_workflow_runs(
                repo=repo,
                status="failure",
                per_page=20,
            )
            test_runs = [r for r in runs if _is_test_run(r.get("name") or "")]
            target_run = test_runs[0] if test_runs else (runs[0] if runs else None)
        except Exception:
            target_run = None

        if not target_run:
            return self._build_result(
                context,
                status="failed",
                summary=f"No failed workflow run found to retry in {repo}",
                details=details,
            )

        workflow_id = target_run.get("id")
        details["test_suites"] = [self._run_to_suite(target_run)]
        details["total_failures"] = 1

        approval_payload = {
            "repo": repo,
            "workflow_id": workflow_id,
            "action": "rerun",
        }

        needs_approval = self._should_require_approval(context)
        if needs_approval:
            return self._build_result(
                context,
                status="pending_approval",
                summary=f"Retry approval required for {target_run.get('name')} in {repo}",
                details=details,
                requires_approval=True,
                approval_payload=approval_payload,
            )

        return self._build_result(
            context,
            status="success",
            summary=f"Retry queued for {target_run.get('name')} in {repo} (non-production)",
            details={**details, "approval_payload": approval_payload},
        )


tester_agent = TesterAgent()
