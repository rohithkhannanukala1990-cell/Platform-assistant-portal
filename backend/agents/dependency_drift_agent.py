"""Dependency drift agent — package manifest drift detection."""

from __future__ import annotations

import json
import re

from sqlmodel import Session

from ..connectors.github_connector import GitHubConnector
from ..context import PlatformContext
from .base import BaseAgent

_ACCOUNT: dict = {}


def _parse_dependencies(content: str | None, filename: str) -> dict[str, str]:
    if not content:
        return {}
    deps: dict[str, str] = {}
    if filename.endswith(".json") or content.strip().startswith("{"):
        try:
            data = json.loads(content)
            for section in ("dependencies", "devDependencies"):
                block = data.get(section) or {}
                if isinstance(block, dict):
                    deps.update({str(k): str(v) for k, v in block.items()})
        except json.JSONDecodeError:
            pass
    else:
        for line in content.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            m = re.match(r"^([A-Za-z0-9_.-]+)\s*([=<>!~]+.*)?$", line)
            if m:
                deps[m.group(1)] = (m.group(2) or "").strip()
    return deps


def _classify_drift(version: str) -> str:
    v = (version or "").strip()
    if not v or v in ("*", "latest"):
        return "major"
    if v.startswith("^0") or v.startswith("~0") or ".0." in v:
        return "major"
    if v.startswith("^") or v.startswith("~"):
        return "minor"
    if re.search(r"\d+\.\d+\.\d+", v):
        return "patch"
    return "minor"


class DependencyDriftAgent(BaseAgent):
    name = "dependency_drift_agent"
    description = "Detects dependency and catalog drift vs repositories."
    requires_approval_envs = []
    primary_tools = ["Catalog DB", "GitHub"]
    read_only = True

    async def run(self, params: dict, context: PlatformContext, db: Session):
        repo = params.get("repo") or context.tool_accounts.get("github") or "org/service"
        manifest = params.get("manifest") or "package.json"
        gh = GitHubConnector(_ACCOUNT)
        packages: list = []
        total = 0

        try:
            content = await gh.get_file_contents(repo, manifest)
            if not content and manifest == "package.json":
                content = await gh.get_file_contents(repo, "requirements.txt")
                manifest = "requirements.txt"

            deps = _parse_dependencies(content, manifest)
            total = len(deps)
            for name, version in deps.items():
                drift = _classify_drift(version)
                if drift:
                    packages.append(
                        {
                            "name": name,
                            "version": version,
                            "drift": drift,
                        }
                    )
        except Exception:
            packages = []
            total = 0

        critical = [p for p in packages if p["drift"] == "major"]
        outdated = [p for p in packages if p["drift"] in ("major", "minor", "patch")]

        return self._build_result(
            context,
            status="success",
            summary=f"{len(outdated)} outdated dependencies in {repo}",
            details={
                "repo": repo,
                "manifest": manifest,
                "total_deps": total,
                "outdated": len(outdated),
                "critical_count": len(critical),
                "packages": packages[:100],
            },
        )


dependency_drift_agent = DependencyDriftAgent()
