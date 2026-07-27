"""Phase 16 — Compliance: audit retention, immutable export, secret redaction."""

from __future__ import annotations

import json

from sqlmodel import Session, select

from backend.auth import AuditLog, write_audit
from backend.database import engine
from backend.services.audit_compliance import (
    attach_hash_chain,
    get_audit_retention_days,
    sanitize_audit_detail,
    set_audit_retention_days,
    verify_hash_chain,
)
from backend.tests.conftest import auth_headers


def test_audit_retention_setting_roundtrip(client, admin_token):
    h = auth_headers(admin_token)
    r = client.get("/api/audit/retention", headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["audit_log_retention_days"] >= 1

    updated = client.put(
        "/api/audit/retention",
        headers=h,
        json={"audit_log_retention_days": 120},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["audit_log_retention_days"] == 120
    assert get_audit_retention_days() == 120

    # Also visible via settings
    settings = client.get("/api/settings", headers=h)
    assert settings.status_code == 200
    assert str(settings.json().get("audit_log_retention_days")) == "120"

    # Restore default for other tests
    set_audit_retention_days(90)


def test_immutable_export_hash_chain(client, admin_token):
    h = auth_headers(admin_token)
    write_audit("admin", "Admin", "compliance_probe_a", resource="test", detail="alpha")
    write_audit("admin", "Admin", "compliance_probe_b", resource="test", detail="beta")

    r = client.get(
        "/api/audit/export?format=json&immutable=true&event_types=compliance_probe_a,compliance_probe_b",
        headers=h,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["immutable"] is True
    assert body["algorithm"] == "sha256"
    assert body["count"] >= 2
    assert verify_hash_chain(body) is True

    # Tamper breaks verification
    body["results"][0]["detail"] = "tampered"
    assert verify_hash_chain(body) is False


def test_attach_hash_chain_unit():
    payload = attach_hash_chain(
        [
            {
                "id": 1,
                "timestamp": "2026-01-01T00:00:00+00:00",
                "actor": "a",
                "actor_role": "Admin",
                "event_type": "x",
                "resource": "r",
                "detail": "d1",
                "ip_address": "",
            },
            {
                "id": 2,
                "timestamp": "2026-01-01T00:00:01+00:00",
                "actor": "a",
                "actor_role": "Admin",
                "event_type": "y",
                "resource": "r",
                "detail": "d2",
                "ip_address": "",
            },
        ]
    )
    assert payload["results"][0]["prev_hash"] == "0" * 64
    assert payload["results"][1]["prev_hash"] == payload["results"][0]["entry_hash"]
    assert verify_hash_chain(payload)


def test_tokens_never_persisted_in_audit_detail():
    """Privacy: passwords, PATs, JWTs, and secret keys must be redacted in AuditLog.detail."""
    secret_payload = {
        "password": "Password123!",
        "api_token": "ghp_abcdefghijklmnopqrstuvwxyz0123456789",
        "authorization": "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.aaaa.bbbb",
        "note": "safe text",
    }
    write_audit(
        actor="admin",
        actor_role="Admin",
        event_type="compliance_secret_probe",
        resource="privacy",
        detail=json.dumps(secret_payload),
    )
    # Also free-form text with embedded PAT
    write_audit(
        actor="admin",
        actor_role="Admin",
        event_type="compliance_secret_probe_text",
        resource="privacy",
        detail="connected with ghp_abcdefghijklmnopqrstuvwxyz0123456789 ok",
    )

    with Session(engine) as session:
        rows = session.exec(
            select(AuditLog).where(
                AuditLog.event_type.in_(
                    ["compliance_secret_probe", "compliance_secret_probe_text"]
                )
            )
        ).all()
        assert rows
        for row in rows:
            detail = row.detail or ""
            assert "Password123!" not in detail
            assert "ghp_abcdefghijklmnopqrstuvwxyz0123456789" not in detail
            assert "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9" not in detail
            assert "[REDACTED]" in detail


def test_sanitize_audit_detail_redacts_keys():
    raw = json.dumps({"token": "supersecret", "ok": True})
    cleaned = sanitize_audit_detail(raw)
    data = json.loads(cleaned)
    assert data["token"] == "[REDACTED]"
    assert data["ok"] is True


def test_failed_login_audit_has_no_password(client):
    client.post(
        "/auth/login",
        data={"username": "admin", "password": "WrongPasswordNeverStore!"},
    )
    with Session(engine) as session:
        row = session.exec(
            select(AuditLog)
            .where(AuditLog.event_type == "login_failed")
            .order_by(AuditLog.timestamp.desc())
        ).first()
        assert row is not None
        assert "WrongPasswordNeverStore!" not in (row.detail or "")
        assert "password" not in (row.detail or "").lower() or "[REDACTED]" in (
            row.detail or ""
        )
        # Detail should be outcome metadata only
        assert "outcome=denied" in (row.detail or "")
