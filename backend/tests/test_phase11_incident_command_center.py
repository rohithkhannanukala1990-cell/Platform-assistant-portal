"""Phase 11 — Incident command center + HITL UX."""

from __future__ import annotations

import json

from backend.database import save_incident, update_incident_status
from backend.services.incident_timeline import (
    append_timeline_event,
    enrich_incident_detail,
    synthesize_timeline,
)
from backend.tests.conftest import auth_headers
from backend.tests.test_phase9_isolation import _login, _make_user


def test_approve_without_auth_returns_401(client):
    inc = save_incident(
        {
            "severity": "High",
            "summary": "unauth approve",
            "root_cause": "n/a",
            "evidence": [],
            "action_plan": [],
            "commands": [],
            "raw_logs": "boom",
            "model_used": "test",
            "raw_response": "{}",
            "tenant_id": "default",
        }
    )
    update_incident_status(
        inc.id,
        status="AWAITING_APPROVAL",
        proposed_remediation_plan=json.dumps(["restart service"]),
    )
    r = client.post(f"/api/incidents/{inc.id}/approve", json={"approved_by_role": "Admin"})
    assert r.status_code == 401


def test_cross_tenant_approve_returns_404(client):
    _make_user("phase11-owner", tenant_id="tenant-owner", role="Admin")
    _make_user("phase11-other", tenant_id="tenant-other", role="Admin")
    token_other = _login(client, "phase11-other")

    inc = save_incident(
        {
            "severity": "High",
            "summary": "owner tenant only",
            "root_cause": "n/a",
            "evidence": [],
            "action_plan": [],
            "commands": ["kubectl get pods"],
            "raw_logs": "err",
            "model_used": "test",
            "raw_response": "{}",
            "tenant_id": "tenant-owner",
        }
    )
    update_incident_status(
        inc.id,
        status="AWAITING_APPROVAL",
        proposed_remediation_plan=json.dumps(["Run: kubectl get pods"]),
    )

    r = client.post(
        f"/api/incidents/{inc.id}/approve",
        headers=auth_headers(token_other),
        json={"approved_by_role": "Admin"},
    )
    assert r.status_code == 404


def test_incident_detail_includes_timeline_and_pending(client, admin_token):
    inc = save_incident(
        {
            "severity": "Medium",
            "summary": "detail payload",
            "root_cause": "oom",
            "evidence": ["log line"],
            "action_plan": ["scale up"],
            "commands": ["kubectl scale deploy/api --replicas=3"],
            "raw_logs": json.dumps(
                {"repo": "acme/api", "pr_number": 42, "html_url": "https://github.com/acme/api/pull/42"}
            ),
            "model_used": "test",
            "raw_response": "{}",
            "tenant_id": "default",
        }
    )
    update_incident_status(
        inc.id,
        status="AWAITING_APPROVAL",
        proposed_remediation_plan=json.dumps(["Run: kubectl scale deploy/api --replicas=3"]),
    )

    r = client.get(f"/api/incidents/{inc.id}", headers=auth_headers(admin_token))
    assert r.status_code == 200, r.text
    body = r.json()
    assert "timeline" in body and isinstance(body["timeline"], list)
    assert len(body["timeline"]) >= 2
    assert body["timeline"][0]["type"] in {"detected", "triaged"}
    assert body.get("github_refs", {}).get("repo") == "acme/api"
    assert body.get("github_refs", {}).get("pr_number") == 42
    assert body.get("pending_approval") is not None
    assert body["pending_approval"]["requires_approval"] is True
    assert "execution_log" in body


def test_timeline_ordering_unit():
    """Stored events are returned sorted by `at` ascending."""
    incident = {
        "timestamp": "2026-01-01T12:00:00+00:00",
        "severity": "Low",
        "summary": "order check",
        "source": "manual",
        "status": "OPEN",
        "timeline": [
            {"type": "executed", "at": "2026-01-01T12:02:00+00:00", "actor": "a", "detail": "last"},
            {"type": "detected", "at": "2026-01-01T12:00:00+00:00", "actor": "s", "detail": "first"},
            {"type": "triaged", "at": "2026-01-01T12:01:00+00:00", "actor": "ai", "detail": "mid"},
        ],
    }
    ordered = synthesize_timeline(incident)
    assert [e["type"] for e in ordered] == ["detected", "triaged", "executed"]
    assert ordered[0]["at"] <= ordered[1]["at"] <= ordered[2]["at"]

    enriched = enrich_incident_detail(incident)
    assert [e["type"] for e in enriched["timeline"]] == ["detected", "triaged", "executed"]


def test_append_timeline_preserves_order(client, admin_token):
    inc = save_incident(
        {
            "severity": "Low",
            "summary": "append order",
            "root_cause": "n/a",
            "evidence": [],
            "action_plan": [],
            "commands": [],
            "raw_logs": "x",
            "model_used": "test",
            "raw_response": "{}",
            "tenant_id": "default",
        }
    )
    append_timeline_event(inc.id, event_type="actions_proposed", detail="plan", actor="agent")
    append_timeline_event(inc.id, event_type="dry_run", detail="safe", actor="admin")

    r = client.get(f"/api/incidents/{inc.id}", headers=auth_headers(admin_token))
    assert r.status_code == 200
    types = [e["type"] for e in r.json()["timeline"]]
    assert "detected" in types
    assert "triaged" in types
    assert "actions_proposed" in types
    assert "dry_run" in types
    # Chronological: detected/triaged before later appends
    assert types.index("detected") < types.index("actions_proposed")
    assert types.index("actions_proposed") < types.index("dry_run")
