"""AI Assistant API tests (Sprint 6 part 1)."""

from unittest.mock import AsyncMock, patch


def auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_ai_chat_creates_conversation(client, admin_token):
    h = auth_headers(admin_token)
    r = client.post(
        "/api/ai/chat",
        json={"message": "Hello assistant"},
        headers=h,
    )
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["conversation_id"].startswith("ai-conv-")
    assert j["message_id"]
    assert "response" in j
    assert j.get("pending_execution") is None


def test_ai_chat_second_message_loads_history(client, admin_token):
    h = auth_headers(admin_token)
    r1 = client.post(
        "/api/ai/chat",
        json={"message": "First message"},
        headers=h,
    )
    assert r1.status_code == 200, r1.text
    cid = r1.json()["conversation_id"]

    r2 = client.post(
        "/api/ai/chat",
        json={"message": "Second message", "conversation_id": cid},
        headers=h,
    )
    assert r2.status_code == 200, r2.text

    r3 = client.get(f"/api/ai/conversations/{cid}", headers=h)
    assert r3.status_code == 200, r3.text
    data = r3.json()
    assert len(data["messages"]) == 4


def test_ai_models_returns_correct_availability(monkeypatch, client, admin_token):
    h = auth_headers(admin_token)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("LLM_MOCK", "0")
    r = client.get("/api/ai/models", headers=h)
    assert r.status_code == 200
    models = {m["id"]: m for m in r.json()}
    assert models["gpt-4o"]["available"] is False
    assert models["gpt-4o-mini"]["available"] is False
    assert models["claude-3-5-haiku-latest"]["available"] is False

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    r2 = client.get("/api/ai/models", headers=h)
    assert r2.status_code == 200
    m2 = {m["id"]: m for m in r2.json()}
    assert m2["gpt-4o"]["available"] is True
    assert m2["claude-3-5-haiku-latest"]["available"] is True


def test_ai_execution_approve_updates_status(client, admin_token):
    h = auth_headers(admin_token)
    with patch(
        "backend.routers.ai_assistant.llm_router.chat",
        new_callable=AsyncMock,
        return_value="Recommendation: restart the API pod now.",
    ):
        r = client.post(
            "/api/ai/chat",
            json={"message": "What should we do?", "environment": "production"},
            headers=h,
        )
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["pending_execution"] is not None
    assert j["pending_execution"]["status"] == "pending_approval"
    eid = j["pending_execution"]["id"]

    r2 = client.post(
        f"/api/ai/executions/{eid}/approve",
        json={"approved_by": "admin"},
        headers=h,
    )
    assert r2.status_code == 200, r2.text
    body = r2.json()
    assert body["status"] == "completed"
