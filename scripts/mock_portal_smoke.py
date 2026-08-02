#!/usr/bin/env python3
"""Smoke a locally running mock portal API (no real LLM/connectors required)."""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

BASE = (os.getenv("BASE_URL") or "http://127.0.0.1:8000").rstrip("/")
USER = os.getenv("DEFAULT_ADMIN_USERNAME") or "admin"
PASS = os.getenv("DEFAULT_ADMIN_PASSWORD") or "Admin123!"
WS = os.getenv("SMOKE_WORKSPACE_ID") or "mock-ws"


def req(method: str, path: str, token: str | None = None, body: dict | None = None, form: dict | None = None):
    url = f"{BASE}{path}"
    headers = {"Accept": "application/json", "X-Workspace-Id": WS}
    data = None
    if form is not None:
        data = urllib.parse.urlencode(form).encode()
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    elif body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=60) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            try:
                parsed = json.loads(raw) if raw else {}
            except json.JSONDecodeError:
                parsed = raw
            return resp.status, parsed
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(raw) if raw else {"detail": str(exc)}
        except json.JSONDecodeError:
            parsed = raw
        return exc.code, parsed


def ok(label: str, code: int, expect=(200,), body=None):
    status = "PASS" if code in expect else "FAIL"
    print(f"[{status}] {label} -> HTTP {code}")
    if status == "FAIL":
        print(f"       body={body!r}"[:500])
    return status == "PASS"


def main() -> int:
    failed = 0

    code, live = req("GET", "/health/live")
    if not ok("health/live", code, body=live):
        failed += 1

    code, ready = req("GET", "/health/ready")
    # SQLite mock: redis may be skipped → still ready
    if not ok("health/ready", code, body=ready):
        failed += 1
    else:
        print(f"       status={ready.get('status') if isinstance(ready, dict) else ready}")

    code, login = req("POST", "/auth/login", form={"username": USER, "password": PASS})
    if not ok("login", code, body=login):
        print("Cannot continue without token")
        return 1
    token = login.get("access_token") if isinstance(login, dict) else None
    if not token:
        print("FAIL: no access_token")
        return 1

    code, llm = req("GET", "/api/llm/status", token=token)
    if not ok("llm/status", code, body=llm):
        failed += 1

    code, agents = req("GET", "/api/agents/", token=token)
    if not ok("agents list", code, body=agents):
        failed += 1
    else:
        n = len(agents) if isinstance(agents, list) else 0
        print(f"       agents={n}")

    code, pol = req(
        "POST",
        "/api/policies/commands/evaluate",
        token=token,
        body={"command": "kubectl get pods -n default", "environment": "production", "tool": "shell"},
    )
    if not ok("policy evaluate", code, body=pol):
        failed += 1
    else:
        print(f"       effect={pol.get('effect') if isinstance(pol, dict) else pol}")

    code, run = req(
        "POST",
        "/api/agents/run",
        token=token,
        body={
            "task": "catalog health overview",
            "context": {
                "environment": "development",
                "workspace_id": WS,
                "user_id": USER,
            },
            "override_agents": ["catalog_health_agent"],
        },
    )
    if not ok("agent run catalog_health", code, body=run):
        failed += 1
    else:
        print(
            f"       status={run.get('status')} grounding={run.get('grounding')} "
            f"summary={(run.get('summary') or '')[:120]!r}"
        )

    code, gh = req("GET", "/api/github/repos", token=token)
    # 400 without account is expected in mock
    if not ok("github/repos (expect 400 without account)", code, expect=(400, 200), body=gh):
        failed += 1

    code, tools = req("GET", "/api/tools", token=token)
    if not ok("tools registry", code, expect=(200, 404), body=tools):
        # try alternate path
        code2, tools2 = req("GET", "/api/tools/", token=token)
        if not ok("tools registry /", code2, expect=(200,), body=tools2):
            failed += 1
        else:
            failed = max(0, failed - 1) if code >= 400 else failed

    print()
    if failed:
        print(f"RESULT: {failed} check(s) failed")
        return 1
    print("RESULT: mock portal smoke OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
