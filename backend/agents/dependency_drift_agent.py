"""Dependency drift agent — package manifest drift from GitHub (grounded)."""

from __future__ import annotations

import json
import re
import uuid

from sqlmodel import Session

from ..context import PlatformContext
from .base import AgentResult, BaseAgent


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

    async def run(self, params: dict, context: PlatformContext, db: Session) -> AgentResult:
        params = params if isinstance(params, dict) else {}
        connector = await self._ground_github(context, db)
        if connector is None:
            return self._no_data_result(
                context,
                "GitHub not connected. Connect a GitHub account to read package manifests.",
                missing_tools=["GitHub"],
            )

        repo = params.get("repo")
        if not repo:
            gh = context.tool_accounts.get("github")
            if isinstance(gh, str) and "/" in gh:
                repo = gh
            elif isinstance(gh, dict) and gh.get("repo"):
                repo = gh.get("repo")
        if not repo:
            owner = (params.get("owner") or "").strip()
            name = (params.get("repo_name") or "").strip()
            if owner and name:
                repo = f"{owner}/{name}"
        if not repo:
            return self._no_data_result(
                context,
                "No repository specified. Pass repo=owner/name (no default org/service).",
                missing_tools=["GitHub"],
            )

        repo = str(repo).strip()
        manifest = params.get("manifest") or "package.json"
        packages: list = []
        total = 0
        evidence: list[dict] = []

        try:
            content = await connector.get_file_contents(repo, manifest)
            used_manifest = manifest
            if not content and manifest == "package.json":
                content = await connector.get_file_contents(repo, "requirements.txt")
                used_manifest = "requirements.txt"

            if not content:
                return self._no_data_result(
                    context,
                    f"No manifest found in {repo} ({manifest} / requirements.txt).",
                    missing_tools=["GitHub"],
                    details={"repo": repo, "manifest": manifest},
                )

            evidence.append(
                self._evidence(
                    type="manifest",
                    title=f"{repo}/{used_manifest}",
                    source="github",
                    snippet=content[:1500],
                )
            )

            deps = _parse_dependencies(content, used_manifest)
            total = len(deps)
            for name, version in deps.items():
                drift = _classify_drift(version)
                packages.append(
                    {
                        "name": name,
                        "version": version,
                        "drift": drift,
                    }
                )
                evidence.append(
                    self._evidence(
                        type="dependency",
                        title=f"{name}@{version}",
                        source="github",
                        snippet=f"drift={drift}",
                    )
                )
        except Exception as exc:
            return self._result(
                context,
                status="failed",
                summary=f"Failed to read manifests from {repo}",
                details={"repo": repo, "manifest": manifest, "error": str(exc)[:300]},
                grounding="none",
                confidence=0.0,
                errors=[str(exc)[:300]],
            )

        critical = [p for p in packages if p["drift"] == "major"]
        outdated = [p for p in packages if p["drift"] in ("major", "minor", "patch")]

        propose = params.get("propose", True)
        if propose and outdated and content:
            if connector is None:
                return self._no_data_result(
                    context,
                    "GitHub not connected — cannot propose dependency bump PR. "
                    "Add GitHub in Settings → Tool Registry.",
                    missing_tools=["GitHub"],
                )
            bumped = content
            branch = f"deps/bump-{uuid.uuid4().hex[:8]}"
            title = f"chore(deps): bump {len(outdated)} outdated packages"
            new_content = str(params.get("proposed_content") or bumped)
            return self._propose_artifact_result(
                context,
                connector="github",
                method="github_dependency_pr",
                params={
                    "repo": repo,
                    "path": used_manifest,
                    "content": new_content,
                    "branch_name": branch,
                    "base": params.get("base") or "main",
                    "title": title,
                    "body": f"Automated dependency bump proposal for {len(outdated)} packages.",
                },
                preview={
                    "type": "github_pr",
                    "repo": repo,
                    "path": used_manifest,
                    "branch": branch,
                    "title": title,
                    "diff_preview": new_content[:4000],
                    "outdated": outdated[:30],
                },
                grounding="live",
                summary=f"Propose PR to bump {len(outdated)} outdated dependencies in {repo}",
                details={
                    "repo": repo,
                    "manifest": used_manifest,
                    "total_deps": total,
                    "outdated": len(outdated),
                    "critical_count": len(critical),
                    "packages": packages[:100],
                },
                evidence=evidence[:80],
            )

        return self._result(
            context,
            status="success",
            summary=f"{len(outdated)} outdated dependencies in {repo}",
            details={
                "repo": repo,
                "manifest": used_manifest,
                "total_deps": total,
                "outdated": len(outdated),
                "critical_count": len(critical),
                "packages": packages[:100],
            },
            evidence=evidence[:80],
            grounding="live",
            confidence=0.85,
        )


dependency_drift_agent = DependencyDriftAgent()
