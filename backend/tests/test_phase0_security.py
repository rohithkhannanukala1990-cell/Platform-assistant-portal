"""Phase 0: placeholder user removal, webhook HMAC raw body, demo data gates."""

from __future__ import annotations

import hashlib
import hmac
from pathlib import Path

import pytest

from backend.tests.conftest import auth_headers


def test_context_placeholder_constant_removed():
    main_src = Path(__file__).resolve().parents[1] / "main.py"
    text = main_src.read_text(encoding="utf-8")
    assert "CONTEXT_PLACEHOLDER_USER_ID" not in text
    assert "str(inbound.payload).encode" not in text


def test_context_get_uses_numeric_user_id(client, admin_token):
    response = client.get("/api/context", headers=auth_headers(admin_token))
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["user_id"] != "admin" or data["user_id"].isdigit()
    # Seeded admin has a numeric PK; context key must be that id string.
    assert str(data["user_id"]).isdigit()


def test_inbound_webhook_hmac_over_raw_bytes(client, monkeypatch):
    secret = "phase0-test-webhook-secret"
    monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", secret)
    monkeypatch.setenv("ENV", "test")

    body = b'{"source":"github","payload":{"ok":true}}'
    good_sig = "sha256=" + hmac.new(
        secret.encode(), body, hashlib.sha256
    ).hexdigest()

    ok = client.post(
        "/api/webhooks/inbound",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Hub-Signature-256": good_sig,
        },
    )
    assert ok.status_code == 202, ok.text
    assert ok.json().get("status") == "accepted"

    bad = client.post(
        "/api/webhooks/inbound",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Hub-Signature-256": "sha256=" + ("0" * 64),
        },
    )
    assert bad.status_code == 403

    # Signing str(dict) must NOT match the raw-body signature check.
    wrong_material = str({"ok": True}).encode()
    wrong_sig = "sha256=" + hmac.new(
        secret.encode(), wrong_material, hashlib.sha256
    ).hexdigest()
    mismatched = client.post(
        "/api/webhooks/inbound",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Hub-Signature-256": wrong_sig,
        },
    )
    assert mismatched.status_code == 403


def test_dora_metrics_demo_gate_off(client, admin_token, monkeypatch):
    monkeypatch.setenv("ENV", "production")
    monkeypatch.setenv("ENABLE_DEMO_DATA", "false")
    response = client.get(
        "/api/cicd/dora-metrics",
        headers=auth_headers(admin_token),
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data.get("status") == "no_data"
    assert data.get("deployment_frequency") is None


def test_dora_metrics_demo_gate_on(client, admin_token, monkeypatch):
    monkeypatch.setenv("ENABLE_DEMO_DATA", "true")
    response = client.get(
        "/api/cicd/dora-metrics",
        headers=auth_headers(admin_token),
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data.get("status") != "no_data"
    assert "deployment_frequency" in data
    assert data["deployment_frequency"] is not None


def test_active_runs_demo_gate_off(client, admin_token, monkeypatch):
    monkeypatch.setenv("ENV", "production")
    monkeypatch.setenv("ENABLE_DEMO_DATA", "0")
    response = client.get(
        "/api/cicd/active-runs",
        headers=auth_headers(admin_token),
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data.get("status") == "no_data"
    assert data.get("runs") == []
