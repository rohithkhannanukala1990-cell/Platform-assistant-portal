"""Code review agent — open PR hygiene via GitHub."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlmodel import Session

from ..connectors.github_connector import GitHubConnector
from ..context import PlatformContext
from .base import BaseAgent

_ACCOUNT: dict = {}


class CodeReviewAgent(BaseAgent):
    name = "code_review_agent"
    description = "PR and repository code review assistance."
    requires_approval_envs = []
    primary_tools = ["GitHub", "GitLab", "SonarQube"]
    read_only = True

    async def run(self, params: dict, context: PlatformContext, db: Session):
        repo = params.get("repo") or context.tool_accounts.get("github") or "org/service"
        prs: list = []
        try:
            prs = await GitHubConnector(_ACCOUNT).list_pull_requests(repo, state="open")
        except Exception:
            prs = []

        unreviewed = [p for p in prs if not p.get("user") or p.get("review_comments", 0) == 0]
        if not unreviewed:
            unreviewed = prs[:]

        by_author: dict[str, int] = {}
        for pr in unreviewed:
            author = pr.get("user") or "unknown"
            by_author[author] = by_author.get(author, 0) + 1

        oldest_age = 0
        if unreviewed:
            ages = []
            for pr in unreviewed:
                created = pr.get("created_at")
                if created:
                    try:
                        dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
                        ages.append((datetime.now(timezone.utc) - dt).days)
                    except ValueError:
                        pass
            oldest_age = max(ages) if ages else 0

        return self._build_result(
            context,
            status="success",
            summary=f"{len(unreviewed)} unreviewed PRs in {repo}",
            details={
                "total_open_prs": len(prs),
                "unreviewed_prs": len(unreviewed),
                "oldest_pr_age_days": oldest_age,
                "by_author": by_author,
                "prs": unreviewed[:30],
                "repo": repo,
            },
        )


code_review_agent = CodeReviewAgent()
