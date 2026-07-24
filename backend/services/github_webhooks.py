"""Normalize GitHub webhook events into incidents / notifications."""

from __future__ import annotations

import json
import os
from typing import Any, Optional

from sqlmodel import Session, select

from ..database import create_notification, engine, save_incident, save_webhook_event
from ..db.models.ops import WebhookEvent
from ..observability.logger import logger


def _default_tenant() -> str:
    return (os.getenv("DEFAULT_TENANT_ID") or "default").strip() or "default"


def _default_workspace() -> Optional[str]:
    raw = (os.getenv("GITHUB_WEBHOOK_WORKSPACE_ID") or "").strip()
    return raw or None


def find_webhook_by_delivery_id(delivery_id: str) -> WebhookEvent | None:
    if not (delivery_id or "").strip():
        return None
    with Session(engine) as session:
        return session.exec(
            select(WebhookEvent).where(WebhookEvent.cloud_event_id == delivery_id.strip())
        ).first()


def _repo_full_name(payload: dict) -> str:
    repo = payload.get("repository") if isinstance(payload.get("repository"), dict) else {}
    return str(repo.get("full_name") or "").strip()


def should_handle_github_event(event_name: str, payload: dict) -> bool:
    name = (event_name or "").strip().lower()
    action = str(payload.get("action") or "").strip().lower()
    if name == "workflow_run":
        wr = payload.get("workflow_run") if isinstance(payload.get("workflow_run"), dict) else {}
        conclusion = str(wr.get("conclusion") or "").strip().lower()
        status = str(wr.get("status") or "").strip().lower()
        return status == "completed" and conclusion == "failure"
    if name == "pull_request":
        return action in {"opened", "synchronize", "reopened"}
    return False


def build_github_incident_fields(
    event_name: str,
    payload: dict,
    *,
    delivery_id: str = "",
) -> dict[str, Any] | None:
    """Return save_incident kwargs, or None if event should be ignored."""
    if not should_handle_github_event(event_name, payload):
        return None

    name = (event_name or "").strip().lower()
    repo = _repo_full_name(payload)
    tenant_id = (
        str(payload.get("tenant_id") or "").strip()
        or _default_tenant()
    )
    workspace_id = (
        str(payload.get("workspace_id") or "").strip()
        or _default_workspace()
    )

    if name == "workflow_run":
        wr = payload.get("workflow_run") if isinstance(payload.get("workflow_run"), dict) else {}
        run_id = wr.get("id")
        run_name = wr.get("name") or wr.get("display_title") or "workflow"
        html_url = wr.get("html_url") or ""
        branch = wr.get("head_branch") or ""
        summary = f"GitHub Actions failed: {run_name} on {repo or 'unknown repo'}"
        root_cause = (
            f"Workflow run `{run_name}` concluded failure"
            + (f" on branch `{branch}`" if branch else "")
            + (f" (run id {run_id})." if run_id else ".")
        )
        evidence = [
            f"repo={repo}",
            f"run_id={run_id}",
            f"conclusion={wr.get('conclusion')}",
        ]
        if html_url:
            evidence.append(f"url={html_url}")
        action_plan = [
            "Immediate: Open the failed Actions run and inspect failed jobs.",
            "Fix: Address the failing step; re-run the workflow.",
            "Harden: Add branch protection / required checks if missing.",
        ]
        return {
            "severity": "High",
            "summary": summary,
            "root_cause": root_cause,
            "evidence": evidence,
            "action_plan": action_plan,
            "commands": [],
            "files_to_check": [repo] if repo else [],
            "validation_steps": ["Confirm the workflow run succeeds after the fix."],
            "raw_logs": json.dumps(
                {
                    "github_event": name,
                    "delivery_id": delivery_id,
                    "repo": repo,
                    "run_id": run_id,
                    "html_url": html_url,
                },
                indent=2,
            ),
            "model_used": "github-webhook",
            "raw_response": "",
            "source": "github",
            "owner_role": "Developer",
            "tenant_id": tenant_id,
            "workspace_id": workspace_id,
        }

    # pull_request opened / synchronize / reopened
    pr = payload.get("pull_request") if isinstance(payload.get("pull_request"), dict) else {}
    number = pr.get("number")
    title = pr.get("title") or "untitled"
    html_url = pr.get("html_url") or ""
    action = str(payload.get("action") or "").strip().lower()
    summary = f"GitHub PR #{number}: {title}" if number else f"GitHub PR: {title}"
    root_cause = (
        f"Pull request {action} on {repo or 'unknown repo'}"
        + (f" by {(pr.get('user') or {}).get('login')}" if isinstance(pr.get("user"), dict) else "")
        + "."
    )
    evidence = [f"repo={repo}", f"pr={number}", f"action={action}"]
    if html_url:
        evidence.append(f"url={html_url}")
    return {
        "severity": "Medium",
        "summary": summary[:240],
        "root_cause": root_cause,
        "evidence": evidence,
        "action_plan": [
            "Immediate: Review the PR diff and CI status.",
            "Fix: Address review findings before merge.",
            "Harden: Ensure required status checks are enabled.",
        ],
        "commands": [],
        "files_to_check": [repo] if repo else [],
        "validation_steps": ["Confirm CI is green and review is complete."],
        "raw_logs": json.dumps(
            {
                "github_event": "pull_request",
                "delivery_id": delivery_id,
                "repo": repo,
                "pr_number": number,
                "action": action,
                "html_url": html_url,
            },
            indent=2,
        ),
        "model_used": "github-webhook",
        "raw_response": "",
        "source": "github",
        "owner_role": "Developer",
        "tenant_id": tenant_id,
        "workspace_id": workspace_id,
    }


def process_github_webhook_event(
    *,
    event_name: str,
    payload: dict,
    delivery_id: str = "",
) -> dict[str, Any]:
    """
    Idempotent by delivery_id (stored as WebhookEvent.cloud_event_id).
    Creates an incident + notification for actionable events.
    """
    delivery_id = (delivery_id or "").strip()
    if delivery_id:
        existing = find_webhook_by_delivery_id(delivery_id)
        if existing:
            return {
                "status": "duplicate",
                "delivery_id": delivery_id,
                "webhook_event_id": existing.id,
                "incident_id": existing.incident_id,
            }

    fields = build_github_incident_fields(event_name, payload, delivery_id=delivery_id)
    if not fields:
        ev = save_webhook_event(
            {
                "source": "github",
                "event_type": event_name or "github",
                "owner_role": "Developer",
                "status": "ignored",
                "raw_payload": json.dumps(payload)[:20000],
                "cloud_event_id": delivery_id or "",
            }
        )
        return {
            "status": "ignored",
            "delivery_id": delivery_id or None,
            "webhook_event_id": ev.id,
            "reason": "event_not_actionable",
        }

    incident = save_incident(fields)
    create_notification(
        message=fields["summary"],
        type="warning" if fields.get("severity") == "High" else "info",
        incident_id=incident.id,
    )
    ev = save_webhook_event(
        {
            "source": "github",
            "event_type": event_name or "github",
            "owner_role": "Developer",
            "status": "processed",
            "incident_id": incident.id,
            "raw_payload": json.dumps(payload)[:20000],
            "cloud_event_id": delivery_id or f"inc-{incident.id}",
        }
    )
    logger.info(
        "GitHub webhook created incident",
        extra={
            "incident_id": incident.id,
            "event": event_name,
            "delivery_id": delivery_id,
        },
    )
    return {
        "status": "processed",
        "delivery_id": delivery_id or None,
        "webhook_event_id": ev.id,
        "incident_id": incident.id,
    }
