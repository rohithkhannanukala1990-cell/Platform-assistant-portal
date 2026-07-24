"""Code review agent — open PR hygiene via GitHub."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from sqlmodel import Session

from ..connectors.github_connector import GitHubAPIError
from ..context import PlatformContext
from ..services.github_access import try_github_connector_from_context
from .base import BaseAgent


class CodeReviewAgent(BaseAgent):
    name = "code_review_agent"
    description = "PR and repository code review assistance."
    requires_approval_envs = []
    primary_tools = ["GitHub", "GitLab", "SonarQube"]
    read_only = True

    async def run(self, params: dict, context: PlatformContext, db: Session):
        connector = try_github_connector_from_context(
            getattr(context, "tool_accounts", None) or {},
            db=db,
        )
        if connector is None:
            return self._build_result(
                context,
                status="skipped",
                summary="GitHub connection is required. Connect a GitHub account in Tool Registry.",
                details={"reason": "github_not_configured"},
            )

        repo = (params.get("repo") or "").strip()
        pr_number = params.get("pr_number") or params.get("number")
        owner = (params.get("owner") or "").strip()

        try:
            if pr_number and owner and repo and "/" not in repo:
                pr = await connector.get_pull_request(owner, repo, int(pr_number))
                files = await connector.list_pull_request_files(
                    owner, repo, int(pr_number)
                )
                facts = {
                    "mode": "single_pr",
                    "repo": f"{owner}/{repo}",
                    "pr": pr,
                    "files": files[:40],
                    "file_count": len(files),
                }
                prompt = (
                    f"You are a code review assistant. Ground your analysis ONLY on these "
                    f"GitHub facts (do not invent files or diffs):\n"
                    f"{json.dumps(facts, default=str)[:6000]}\n"
                    "Return JSON with keys: summary (string), findings (list of strings), "
                    "risk_level (low|medium|high), details (object)."
                )
                raw = await self._call_llm(prompt, context)
                parsed = self._parse_llm_json(raw)
                return self._build_result(
                    context,
                    status="success",
                    summary=str(
                        parsed.get("summary")
                        or f"Reviewed PR #{pr_number} in {owner}/{repo}"
                    ),
                    details={
                        "github_facts": facts,
                        "findings": parsed.get("findings") or [],
                        "risk_level": parsed.get("risk_level"),
                        "llm": parsed.get("details")
                        if isinstance(parsed.get("details"), dict)
                        else {},
                    },
                )

            if not repo:
                # Prefer account org repos when no explicit repo
                repos = await connector.list_repos(per_page=5)
                if repos:
                    repo = str(repos[0].get("full_name") or "")
            if not repo:
                return self._build_result(
                    context,
                    status="failed",
                    summary="No repository specified and none available from GitHub.",
                    details={"reason": "no_repo"},
                )

            prs = await connector.list_pull_requests(repo, state="open", per_page=20)
        except GitHubAPIError as exc:
            return self._build_result(
                context,
                status="failed",
                summary=f"GitHub API error: {exc.message}",
                details={"error_type": exc.error_type, "repo": repo},
            )
        except Exception as exc:
            return self._build_result(
                context,
                status="failed",
                summary="Failed to fetch pull requests from GitHub.",
                details={"error": str(exc)[:200], "repo": repo},
            )

        by_author: dict[str, int] = {}
        oldest_age = 0
        ages: list[int] = []
        for pr in prs:
            author = pr.get("user") or "unknown"
            by_author[author] = by_author.get(author, 0) + 1
            created = pr.get("created_at")
            if created:
                try:
                    dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
                    ages.append((datetime.now(timezone.utc) - dt).days)
                except ValueError:
                    pass
        oldest_age = max(ages) if ages else 0

        facts = {
            "mode": "pr_list",
            "repo": repo,
            "total_open_prs": len(prs),
            "by_author": by_author,
            "oldest_pr_age_days": oldest_age,
            "prs": prs[:20],
        }
        prompt = (
            f"You are a code review hygiene assistant. Ground your analysis ONLY on these "
            f"open PR facts from GitHub (do not invent PRs):\n"
            f"{json.dumps(facts, default=str)[:6000]}\n"
            "Return JSON with keys: summary (string), findings (list of strings), "
            "details (object)."
        )
        try:
            raw = await self._call_llm(prompt, context)
            parsed = self._parse_llm_json(raw)
            summary = str(
                parsed.get("summary") or f"{len(prs)} open PRs in {repo}"
            )
            llm_details = (
                parsed.get("details")
                if isinstance(parsed.get("details"), dict)
                else {}
            )
            findings = parsed.get("findings") or []
        except Exception:
            summary = f"{len(prs)} open PRs in {repo}"
            llm_details = {}
            findings = []

        return self._build_result(
            context,
            status="success",
            summary=summary,
            details={
                "github_facts": facts,
                "findings": findings,
                "llm": llm_details,
                "total_open_prs": len(prs),
                "oldest_pr_age_days": oldest_age,
                "by_author": by_author,
                "prs": prs[:30],
                "repo": repo,
            },
        )


code_review_agent = CodeReviewAgent()
