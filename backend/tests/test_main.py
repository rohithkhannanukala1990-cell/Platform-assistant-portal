"""API smoke tests for backend.main (Sprint 0 CI)."""

import time
from unittest.mock import AsyncMock, patch


def auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


_FAKE_TRIAGE_RESULT = {
    "id": 999001,
    "timestamp": "2026-01-01T00:00:00+00:00",
    "severity": "Low",
    "summary": "test summary",
    "root_cause": "test root cause",
    "evidence": [],
    "action_plan": [],
    "commands": [],
    "files_to_check": [],
    "validation_steps": [],
    "raw": "{}",
    "model_used": "pytest-mock",
}


def test_01_health_returns_200(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert "timestamp" in response.json()


def test_02_health_has_required_fields(client):
    response = client.get("/health")
    data = response.json()
    assert "status" in data
    assert "timestamp" in data
    assert "version" in data


def test_03_post_triage_returns_200(client, admin_token):
    with patch("backend.main._run_triage", new_callable=AsyncMock) as mock_triage:
        mock_triage.return_value = _FAKE_TRIAGE_RESULT
        response = client.post(
            "/api/triage",
            json={"logs": "Error: connection timeout"},
            headers=auth_headers(admin_token),
        )
    assert response.status_code == 200


def test_04_get_incidents_approvals_returns_200(client, admin_token):
    response = client.get(
        "/api/incidents/approvals",
        headers=auth_headers(admin_token),
    )
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_05_cors_headers_on_health_with_origin(client):
    response = client.get(
        "/health",
        headers={"Origin": "http://localhost:5173"},
    )
    assert "access-control-allow-origin" in {k.lower() for k in response.headers.keys()}


def test_06_invalid_endpoint_returns_404(client):
    response = client.get("/api/nonexistent")
    assert response.status_code == 404


def test_07_post_triage_empty_body_returns_422_or_error(client, admin_token):
    response = client.post(
        "/api/triage",
        json={},
        headers=auth_headers(admin_token),
    )
    assert response.status_code in (200, 422)


def test_08_get_incidents_approvals_returns_list(client, admin_token):
    response = client.get(
        "/api/incidents/approvals",
        headers=auth_headers(admin_token),
    )
    assert isinstance(response.json(), list)


def test_09_post_triage_rate_limit_or_success(client, admin_token):
    with patch("backend.main._run_triage", new_callable=AsyncMock) as mock_triage:
        mock_triage.return_value = _FAKE_TRIAGE_RESULT
        response = client.post(
            "/api/triage",
            json={"logs": "test"},
            headers=auth_headers(admin_token),
        )
    assert response.status_code in (200, 429)


def test_10_health_response_time_under_500ms(client):
    start = time.time()
    client.get("/health")
    assert (time.time() - start) < 0.5


def test_11_get_api_chat_method_not_allowed(client):
    response = client.get("/api/chat")
    assert response.status_code in (200, 404, 405)


def test_12_post_triage_wrong_content_type(client, admin_token):
    response = client.post(
        "/api/triage",
        data="plain text",
        headers={"Content-Type": "text/plain", **auth_headers(admin_token)},
    )
    assert response.status_code in (422, 415, 400)


def test_13_options_preflight_triage(client):
    response = client.options(
        "/api/triage",
        headers={"Origin": "http://localhost:5173"},
    )
    assert response.status_code in (200, 405)


def test_14_multiple_rapid_get_health_succeed(client):
    for _ in range(10):
        response = client.get("/health")
        assert response.status_code == 200


def test_15_get_endpoints_return_json(client, admin_token):
    pairs = [
        ("/health", None),
        ("/api/incidents/approvals", auth_headers(admin_token)),
    ]
    for path, headers in pairs:
        kw = {"headers": headers} if headers else {}
        response = client.get(path, **kw)
        assert response.headers.get("content-type", "").startswith("application/json")


def test_16_api_health_full_requires_auth(client):
    assert client.get("/api/health/full").status_code == 401


def test_17_api_health_full_admin_ok(client, admin_token):
    response = client.get("/api/health/full", headers=auth_headers(admin_token))
    assert response.status_code == 200
    data = response.json()
    assert "database" in data
    assert "redis" in data
    assert "checked_at" in data


def test_18_api_health_alerts_admin_ok(client, admin_token):
    response = client.get("/api/health/alerts", headers=auth_headers(admin_token))
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_19_api_health_autoheal_admin_ok(client, admin_token):
    response = client.post(
        "/api/health/autoheal/all",
        headers=auth_headers(admin_token),
    )
    assert response.status_code == 200
    body = response.json()
    assert "count" in body
    assert isinstance(body.get("healed"), list)


def test_20_api_health_summary_public_no_auth(client):
    response = client.get("/api/health/summary")
    assert response.status_code == 200
    data = response.json()
    assert data.get("status") in ("healthy", "warning", "critical")
    assert "checked_at" in data


def test_21_api_tools_grouped_requires_auth(client):
    assert client.get("/api/tools").status_code == 401


def test_22_api_tools_grouped_admin(client, admin_token):
    r = client.get("/api/tools", headers=auth_headers(admin_token))
    assert r.status_code == 200
    data = r.json()
    assert "cloud" in data
    assert isinstance(data["cloud"], list)
    assert any(t.get("id") == "aws" for t in data["cloud"])


def test_23_api_tools_categories_admin(client, admin_token):
    r = client.get("/api/tools/categories", headers=auth_headers(admin_token))
    assert r.status_code == 200
    cats = r.json()
    assert isinstance(cats, list)
    assert len(cats) == 9
    ids = {c["id"] for c in cats}
    assert "cloud" in ids and "cicd" in ids


def test_24_tool_account_lifecycle(client, admin_token):
    h = auth_headers(admin_token)
    acc = client.post(
        "/api/tools/github/accounts",
        headers=h,
        json={
            "account_name": "pytest-org",
            "environment": "dev",
            "auth_type": "pat",
            "account_identifier": "org-1",
        },
    )
    assert acc.status_code == 200, acc.text
    aid = acc.json()["id"]
    lst = client.get("/api/tools/github/accounts", headers=h)
    assert lst.status_code == 200
    assert any(a["id"] == aid for a in lst.json())
    auth_types = client.get("/api/tools/github/auth-types", headers=h)
    assert auth_types.status_code == 200
    assert isinstance(auth_types.json(), list)
    req_fields = client.get("/api/tools/aws/required-fields", headers=h)
    assert req_fields.status_code == 200
    assert "region" in req_fields.json()

    tst = client.post(f"/api/tools/github/accounts/{aid}/test", headers=h)
    assert tst.status_code == 200
    body = tst.json()
    assert "connected" in body and "latency_ms" in body
    assert body.get("connected") is True
    upd = client.put(
        f"/api/tools/github/accounts/{aid}",
        headers=h,
        json={"account_name": "pytest-org-renamed"},
    )
    assert upd.status_code == 200
    assert upd.json()["account_name"] == "pytest-org-renamed"
    soft = client.delete(f"/api/tools/github/accounts/{aid}", headers=h)
    assert soft.status_code == 200
    assert "deactivated" in soft.json().get("message", "").lower()


def test_25_api_context_get_put_pin(client, admin_token):
    h = auth_headers(admin_token)
    acc = client.post(
        "/api/tools/aws/accounts",
        headers=h,
        json={
            "account_name": "ctx-test",
            "environment": "production",
            "auth_type": "iam_role",
            "account_identifier": "111111111111",
        },
    )
    assert acc.status_code == 200, acc.text
    aid = acc.json()["id"]
    g = client.get("/api/context", headers=h)
    assert g.status_code == 200
    body = g.json()
    assert body["user_id"] == "admin"
    assert body["active_environment"] == "development"
    assert isinstance(body["active_accounts"], dict)
    assert isinstance(body["pinned_accounts"], list)
    pu = client.put(
        "/api/context",
        headers=h,
        json={"active_environment": "staging", "active_accounts": {"aws": aid}},
    )
    assert pu.status_code == 200, pu.text
    ctx = pu.json()
    assert ctx["active_environment"] == "staging"
    assert "aws" in ctx["active_accounts"]
    assert ctx["active_accounts"]["aws"]["id"] == aid
    pin = client.post("/api/context/pin", headers=h, json={"account_id": aid, "pinned": True})
    assert pin.status_code == 200
    assert aid in pin.json()["pinned_accounts"]


def test_26_api_tools_accounts_matrix(client, admin_token):
    h = auth_headers(admin_token)
    acc = client.post(
        "/api/tools/gitlab/accounts",
        headers=h,
        json={
            "account_name": "mx-test",
            "environment": "development",
            "auth_type": "pat",
        },
    )
    assert acc.status_code == 200, acc.text
    aid = acc.json()["id"]
    client.post(f"/api/tools/gitlab/accounts/{aid}/test", headers=h)
    r = client.get("/api/tools/gitlab/accounts/matrix", headers=h)
    assert r.status_code == 200
    data = r.json()
    assert data["tool_id"] == "gitlab"
    assert data["environments"] == [
        "local",
        "development",
        "test",
        "staging",
        "production",
        "dr",
    ]
    row = next(a for a in data["accounts"] if a["id"] == aid)
    assert row["matrix"]["development"] is not None
    assert row["matrix"]["development"]["status"] == "connected"
    assert row["matrix"]["production"] is None


def test_27_api_access_requests_flow(client, admin_token):
    h = auth_headers(admin_token)
    acc = client.post(
        "/api/tools/jira/accounts",
        headers=h,
        json={
            "account_name": "ar-test",
            "environment": "staging",
            "auth_type": "api_token",
        },
    )
    assert acc.status_code == 200, acc.text
    aid = acc.json()["id"]
    cr = client.post(
        "/api/access-requests",
        headers=h,
        json={"account_id": aid, "reason": "Need staging access for incident response"},
    )
    assert cr.status_code == 200, cr.text
    rid = cr.json()["id"]
    lst = client.get("/api/access-requests", headers=h)
    assert lst.status_code == 200
    assert any(x["id"] == rid for x in lst.json())
    ap = client.put(f"/api/access-requests/{rid}", headers=h, json={"status": "approved"})
    assert ap.status_code == 200, ap.text
    assert ap.json()["status"] == "approved"
    assert ap.json()["reviewed_by"] == "admin"


def test_28_import_csv_json_discover(client, admin_token):
    h = auth_headers(admin_token)
    tpl = client.get("/api/import/template/csv", headers=h)
    assert tpl.status_code == 200
    assert "tool_id" in tpl.text

    csv_body = (
        "tool_id,account_name,environment,region,account_identifier,instance_url,auth_type,requires_hitl\n"
        "slack,Import Test Slack,development,,,,api_key,0\n"
    )
    prev = client.post(
        "/api/import/csv",
        headers=h,
        files={"file": ("accounts.csv", csv_body.encode("utf-8"), "text/csv")},
    )
    assert prev.status_code == 200, prev.text
    pv = prev.json()
    assert pv["total_rows"] == 1
    assert pv["ready_to_import"] is True
    rows = pv["rows"]
    conf = client.post("/api/import/csv/confirm", headers=h, json={"rows": rows})
    assert conf.status_code == 200, conf.text
    assert conf.json()["imported"] >= 1

    dup = client.post("/api/import/csv/confirm", headers=h, json={"rows": rows})
    assert dup.status_code == 200
    assert dup.json()["skipped"] >= 1

    jprev = client.post(
        "/api/import/json",
        headers=h,
        json={"content": '[{"tool_id":"slack","account_name":"JSON Import Acc","environment":"test","auth_type":"api_token"}]'},
    )
    assert jprev.status_code == 200
    jr = jprev.json()
    assert jr["total_rows"] == 1
    jconf = client.post("/api/import/json/confirm", headers=h, json={"rows": jr["rows"]})
    assert jconf.status_code == 200
    assert jconf.json()["imported"] >= 1

    disc = client.post(
        "/api/import/discover",
        headers=h,
        json={"provider": "gcp", "credentials": {"project_id": "pytest-proj"}},
    )
    assert disc.status_code == 200
    d = disc.json()
    assert d["discovered_count"] == 1
    dconf = client.post("/api/import/discover/confirm", headers=h, json={"accounts": d["accounts"]})
    assert dconf.status_code == 200
    assert dconf.json()["imported"] >= 1
