"""Phase P6 — production compose config + env example safety (no live stack)."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PROD_COMPOSE = ROOT / "deploy" / "docker-compose.prod.yml"
ENV_EXAMPLE = ROOT / ".env.production.example"
PILOT_SMOKE = ROOT / "scripts" / "pilot_smoke.sh"
REALWORLD = ROOT / "scripts" / "agent_realworld_checklist.md"


def _load_compose() -> dict:
    raw = PROD_COMPOSE.read_text(encoding="utf-8")
    try:
        import yaml  # type: ignore
    except ImportError:
        # Fallback: structural string checks when PyYAML unavailable in CI
        return {"_raw": raw}
    return yaml.safe_load(raw)


def test_prod_compose_has_ha_services_and_ready_healthchecks():
    assert PROD_COMPOSE.is_file()
    data = _load_compose()
    if "_raw" in data:
        raw = data["_raw"]
        for name in ("api_1:", "api_2:", "celery_worker_1:", "celery_worker_2:"):
            assert name in raw
        assert "/health/ready" in raw
        assert 'ENABLE_DEMO_DATA: "false"' in raw
        assert 'ENFORCE_WORKSPACE_ISOLATION: "true"' in raw
        assert "condition: service_healthy" in raw
        return

    services = data.get("services") or {}
    for name in ("api_1", "api_2", "celery_worker_1", "celery_worker_2", "postgres", "redis", "nginx"):
        assert name in services, f"missing service {name}"

    # Anchored env defaults live on x-api-env
    x_env = data.get("x-api-env") or {}
    assert str(x_env.get("ENABLE_DEMO_DATA")) == "false"
    assert str(x_env.get("ENFORCE_WORKSPACE_ISOLATION")) == "true"
    assert x_env.get("ENV") == "production"
    db_url = str(x_env.get("DATABASE_URL", ""))
    assert db_url.startswith("postgresql://")
    assert "sqlite" not in db_url.lower()

    # Merged healthchecks on API replicas (via <<: *api-common)
    for api in ("api_1", "api_2"):
        hc = services[api].get("healthcheck") or {}
        test = hc.get("test") or []
        joined = " ".join(test) if isinstance(test, list) else str(test)
        assert "/health/ready" in joined

    deps = (services.get("nginx") or {}).get("depends_on") or {}
    for key in ("api_1", "api_2", "frontend"):
        assert key in deps
        cond = deps[key]
        if isinstance(cond, dict):
            assert cond.get("condition") == "service_healthy"


def test_env_production_example_defaults_and_secrets():
    assert ENV_EXAMPLE.is_file()
    text = ENV_EXAMPLE.read_text(encoding="utf-8")
    lines = [
        ln.strip()
        for ln in text.splitlines()
        if ln.strip() and not ln.strip().startswith("#")
    ]
    kv = {}
    for ln in lines:
        if "=" not in ln:
            continue
        k, _, v = ln.partition("=")
        kv[k.strip()] = v.strip()

    assert kv.get("ENABLE_DEMO_DATA", "").lower() == "false"
    assert "SECRETS_ENCRYPTION_KEY" in kv
    # Value line must not embed an inline # comment.
    for ln in text.splitlines():
        if ln.strip().startswith("SECRETS_ENCRYPTION_KEY="):
            assert "#" not in ln, f"inline comment on SECRETS_ENCRYPTION_KEY line: {ln!r}"
            break
    else:
        raise AssertionError("SECRETS_ENCRYPTION_KEY= line missing")

    assert "ENFORCE_WORKSPACE_ISOLATION" in kv
    assert kv.get("ENFORCE_WORKSPACE_ISOLATION", "").lower() == "true"
    assert kv.get("ENV", "").lower() == "production"


def test_pilot_smoke_and_realworld_checklist_exist():
    assert PILOT_SMOKE.is_file()
    smoke = PILOT_SMOKE.read_text(encoding="utf-8")
    assert "/health/ready" in smoke
    assert "/api/llm/status" in smoke
    assert "/api/agents/" in smoke
    assert "/api/policies/commands/evaluate" in smoke
    assert "access_token" in smoke

    assert REALWORLD.is_file()
    checklist = REALWORLD.read_text(encoding="utf-8")
    for needle in (
        ".env.production",
        "code_review",
        "pipeline_monitor",
        "postmortem",
        "audit",
        "User B",
    ):
        assert needle.lower() in checklist.lower(), f"checklist missing {needle}"
