"""Phase 7: auth hardening, expensive-route rate limits."""

from __future__ import annotations

import inspect

from backend.auth import login
from backend.routers.agents import run_agent
from backend.routers.incidents import triage_logs
from backend.routers.platform_misc import platform_chat
from backend.tests.conftest import auth_headers


def _has_limit_decorator(fn) -> bool:
    """SlowAPI wraps the endpoint; look for limit metadata or closure."""
    candidate = fn
    seen: set[int] = set()
    while candidate is not None and id(candidate) not in seen:
        seen.add(id(candidate))
        if getattr(candidate, "_limiters", None) or getattr(
            candidate, "__wrapped__", None
        ):
            # Prefer explicit SlowAPI marker when present.
            if getattr(candidate, "_limiters", None):
                return True
        text = ""
        try:
            text = inspect.getsource(candidate)
        except (OSError, TypeError):
            text = ""
        if "limiter.limit" in text or ".limit(" in text:
            return True
        candidate = getattr(candidate, "__wrapped__", None)
    # Fallback: function name still resolves and Request is first param (SlowAPI pattern)
    try:
        src = inspect.getsource(fn)
    except (OSError, TypeError):
        src = ""
    return "limiter.limit" in src


def test_login_failed_returns_401_not_500(client):
    r = client.post(
        "/auth/login",
        data={"username": "no-such-user-phase7", "password": "wrong-password"},
    )
    assert r.status_code == 401, r.text
    assert r.json().get("detail") == "Invalid credentials"
    # Password must never echo in the response body
    assert "wrong-password" not in r.text


def test_login_route_has_rate_limit_decorator():
    assert _has_limit_decorator(login)


def test_chat_and_triage_have_rate_limit_decorators():
    assert _has_limit_decorator(platform_chat)
    assert _has_limit_decorator(triage_logs)
    assert _has_limit_decorator(run_agent)


def test_failed_login_writes_audit_without_password(client):
    from sqlmodel import Session, select

    from backend.auth import AuditLog, engine

    before = 0
    with Session(engine) as session:
        before = len(
            list(
                session.exec(
                    select(AuditLog).where(AuditLog.event_type == "login_failed")
                ).all()
            )
        )

    client.post(
        "/auth/login",
        data={"username": "audit-phase7-user", "password": "SuperSecretShouldNotAppear"},
    )

    with Session(engine) as session:
        rows = list(
            session.exec(
                select(AuditLog).where(AuditLog.event_type == "login_failed")
            ).all()
        )
    assert len(rows) >= before + 1
    newest = rows[-1]
    assert "outcome=denied" in (newest.detail or "")
    assert "SuperSecretShouldNotAppear" not in (newest.detail or "")
    assert "password" not in (newest.detail or "").lower()


def test_successful_login_still_works(client, admin_token):
    # Sanity: existing admin token fixture proves login path works end-to-end
    assert admin_token
    r = client.get("/api/settings", headers=auth_headers(admin_token))
    assert r.status_code == 200
