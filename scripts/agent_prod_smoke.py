#!/usr/bin/env python3
"""Optional prod smoke against a running API.

Reads BASE_URL + TOKEN from the environment (TOKEN may be obtained via login).
Lists agents, runs a read-only agent, prints grounding, exits non-zero on HTTP 500.

Examples:
  export BASE_URL=https://api.example.com
  export TOKEN=$(curl -fsS -X POST "$BASE_URL/auth/login" ... | jq -r .access_token)
  python scripts/agent_prod_smoke.py
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request


def _req(method: str, url: str, token: str | None = None, body: dict | None = None) -> tuple[int, dict | list | str]:
    data = None
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=60) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            try:
                parsed: dict | list | str = json.loads(raw) if raw else {}
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


def main() -> int:
    base = (os.getenv("BASE_URL") or "http://localhost:8000").rstrip("/")
    token = (os.getenv("TOKEN") or "").strip()
    if not token:
        print("TOKEN env var is required", file=sys.stderr)
        return 2

    print(f"==> list agents @ {base}")
    code, agents = _req("GET", f"{base}/api/agents/", token=token)
    if code >= 500:
        print(f"FAIL list agents HTTP {code}: {agents}", file=sys.stderr)
        return 1
    if code != 200:
        print(f"FAIL list agents HTTP {code}: {agents}", file=sys.stderr)
        return 1
    names = [a.get("name") for a in agents] if isinstance(agents, list) else []
    print(f"agents={len(names)} sample={names[:5]}")

    print("==> run read-only catalog_health_agent")
    code, result = _req(
        "POST",
        f"{base}/api/agents/run",
        token=token,
        body={
            "task": "score catalog health",
            "context": {"environment": os.getenv("SMOKE_ENV") or "production"},
            "override_agents": ["catalog_health_agent"],
        },
    )
    if code >= 500:
        print(f"FAIL agent run HTTP {code}: {result}", file=sys.stderr)
        return 1
    if code != 200 or not isinstance(result, dict):
        print(f"FAIL agent run HTTP {code}: {result}", file=sys.stderr)
        return 1

    grounding = result.get("grounding")
    status = result.get("status")
    print(f"status={status} grounding={grounding} summary={str(result.get('summary') or '')[:160]}")
    if grounding not in {"live", "partial", "none", "demo"}:
        print(f"FAIL unexpected grounding={grounding!r}", file=sys.stderr)
        return 1

    print("OK — agent prod smoke passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
