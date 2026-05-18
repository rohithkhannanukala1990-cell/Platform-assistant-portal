"""Merge multiple AgentResult payloads."""

from __future__ import annotations

from datetime import datetime, timezone

from ..agents.base import AgentResult


class ResultAggregator:
    def aggregate(self, results: list[AgentResult]) -> AgentResult:
        if not results:
            return AgentResult(
                agent="orchestrator",
                status="failed",
                summary="No agent results",
                details={},
                timestamp=datetime.now(timezone.utc).isoformat(),
                triggered_by="",
                workspace="",
                environment="",
            )
        if len(results) == 1:
            return results[0]

        requires = any(r.requires_approval for r in results)
        status = "pending_approval" if requires else "success"
        if any(r.status == "failed" for r in results):
            status = "failed" if not requires else "pending_approval"

        summaries = [f"[{r.agent}] {r.summary}" for r in results]
        details: dict = {}
        logs: list[str] = []
        for r in results:
            details[r.agent] = r.details
            if r.execution_log:
                logs.append(f"--- {r.agent} ---\n{r.execution_log}")

        base = results[0]
        return AgentResult(
            agent="orchestrator",
            status=status,
            summary=" | ".join(summaries),
            details=details,
            requires_approval=requires,
            approval_payload={"agents": [r.model_dump() for r in results]} if requires else None,
            execution_log="\n\n".join(logs) if logs else None,
            timestamp=datetime.now(timezone.utc).isoformat(),
            triggered_by=base.triggered_by,
            workspace=base.workspace,
            environment=base.environment,
        )


result_aggregator = ResultAggregator()
