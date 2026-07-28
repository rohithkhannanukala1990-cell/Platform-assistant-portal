"""Phase G3 — Postmortem generation (incident.io / PD Scribe gap)."""

from __future__ import annotations

import json

from backend.database import save_incident
from backend.services.incident_timeline import append_timeline_event
from backend.services.postmortem_service import POSTMORTEM_SECTIONS
from backend.tests.conftest import auth_headers
from backend.tests.test_phase9_isolation import _login, _make_user


def _seed_incident(**kwargs):
    data = {
        "severity": "High",
        "summary": "API latency spike on checkout",
        "root_cause": "Connection pool exhausted under load.",
        "evidence": ["p99 latency > 2s", "pool wait timeout in logs"],
        "action_plan": ["Scale replicas", "Increase pool size"],
        "commands": ["kubectl scale deploy checkout --replicas=5"],
        "raw_logs": "ERROR pool timeout",
        "model_used": "test",
        "raw_response": "{}",
        "tenant_id": "default",
    }
    data.update(kwargs)
    return save_incident(data)


def test_generate_postmortem_requires_auth(client):
    inc = _seed_incident()
    r = client.post(f"/api/incidents/{inc.id}/postmortem/generate")
    assert r.status_code == 401


def test_cross_tenant_postmortem_generate_returns_404(client):
    _make_user("g3-owner", tenant_id="tenant-owner", role="Admin")
    _make_user("g3-other", tenant_id="tenant-other", role="Admin")
    token_other = _login(client, "g3-other")

    inc = _seed_incident(tenant_id="tenant-owner", summary="owner only")
    r = client.post(
        f"/api/incidents/{inc.id}/postmortem/generate",
        headers=auth_headers(token_other),
    )
    assert r.status_code == 404


def test_cross_tenant_postmortem_get_returns_404(client, admin_token):
    _make_user("g3-get-owner", tenant_id="tenant-get-owner", role="Admin")
    _make_user("g3-get-other", tenant_id="tenant-get-other", role="Admin")
    token_owner = _login(client, "g3-get-owner")
    token_other = _login(client, "g3-get-other")

    inc = _seed_incident(tenant_id="tenant-get-owner")
    gen = client.post(
        f"/api/incidents/{inc.id}/postmortem/generate",
        headers=auth_headers(token_owner),
    )
    assert gen.status_code == 200

    r = client.get(
        f"/api/incidents/{inc.id}/postmortem",
        headers=auth_headers(token_other),
    )
    assert r.status_code == 404


def test_generate_postmortem_mock_llm_has_all_sections(client, admin_token):
    inc = _seed_incident()
    append_timeline_event(
        inc.id,
        event_type="dry_run",
        detail="Dry-run of 1 command(s)",
        actor="admin",
    )

    r = client.post(
        f"/api/incidents/{inc.id}/postmortem/generate",
        headers=auth_headers(admin_token),
    )
    assert r.status_code == 200
    body = r.json()
    assert body["incident_id"] == inc.id
    assert body["version"] == 1
    markdown = body["markdown"]
    for section in POSTMORTEM_SECTIONS:
        assert f"## {section}" in markdown, f"missing section: {section}"

    # Timeline must include stored event detail, not invented events
    assert "Dry-run of 1 command(s)" in markdown
    assert "dry_run" in markdown.lower()


def test_get_put_and_download_postmortem(client, admin_token):
    inc = _seed_incident(summary="download test")
    gen = client.post(
        f"/api/incidents/{inc.id}/postmortem/generate",
        headers=auth_headers(admin_token),
    )
    assert gen.status_code == 200

    get_r = client.get(
        f"/api/incidents/{inc.id}/postmortem",
        headers=auth_headers(admin_token),
    )
    assert get_r.status_code == 200
    assert get_r.json()["version"] == 1

    edited = gen.json()["markdown"] + "\n\n## Notes\n\nEdited by operator."
    put_r = client.put(
        f"/api/incidents/{inc.id}/postmortem",
        headers=auth_headers(admin_token),
        json={"markdown": edited},
    )
    assert put_r.status_code == 200
    assert "Edited by operator" in put_r.json()["markdown"]

    dl = client.get(
        f"/api/incidents/{inc.id}/postmortem/download",
        headers=auth_headers(admin_token),
    )
    assert dl.status_code == 200
    assert "text/markdown" in dl.headers.get("content-type", "")
    assert b"Edited by operator" in dl.content


def test_regenerate_increments_version(client, admin_token):
    inc = _seed_incident()
    h = auth_headers(admin_token)
    r1 = client.post(f"/api/incidents/{inc.id}/postmortem/generate", headers=h)
    r2 = client.post(f"/api/incidents/{inc.id}/postmortem/generate", headers=h)
    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r1.json()["version"] == 1
    assert r2.json()["version"] == 2


def test_postmortem_generated_audit_event(client, admin_token):
    from sqlmodel import Session, select

    from backend.auth import AuditLog, engine

    inc = _seed_incident()
    client.post(
        f"/api/incidents/{inc.id}/postmortem/generate",
        headers=auth_headers(admin_token),
    )
    with Session(engine) as session:
        rows = session.exec(
            select(AuditLog).where(AuditLog.event_type == "postmortem_generated")
        ).all()
    assert any(f"incident:{inc.id}" in (row.resource or "") for row in rows)
