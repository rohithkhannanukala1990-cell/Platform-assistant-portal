"""LLM token utilization metering and org cost report."""

from __future__ import annotations

import asyncio
import uuid

from sqlmodel import Session, select

from backend.ai.llm_service import llm_service
from backend.ai.usage_pricing import estimate_cost_usd, estimate_tokens_from_text
from backend.auth import engine
from backend.db.models.ai_models import LLMUsageEvent
from backend.services.llm_usage import record_llm_usage
from backend.tests.conftest import auth_headers


def test_estimate_cost_known_model():
    cost = estimate_cost_usd(model="gpt-4o-mini", prompt_tokens=1_000_000, completion_tokens=1_000_000)
    assert cost == round(0.15 + 0.60, 8)


def test_estimate_tokens_from_text():
    assert estimate_tokens_from_text("abcd") == 1
    assert estimate_tokens_from_text("a" * 40) == 10


def test_record_llm_usage_persists(client):
    _ = client  # ensure tables exist via lifespan
    uid = f"usage-user-{uuid.uuid4().hex[:8]}"
    record_llm_usage(
        provider="openai",
        model="gpt-4o-mini",
        prompt_tokens=100,
        completion_tokens=50,
        total_tokens=150,
        estimated_cost_usd=0.0001,
        user_id=uid,
        tenant_id="default",
        source="test",
    )
    with Session(engine) as session:
        rows = list(
            session.exec(select(LLMUsageEvent).where(LLMUsageEvent.user_id == uid)).all()
        )
    assert len(rows) == 1
    assert rows[0].total_tokens == 150
    assert rows[0].provider == "openai"


def test_chat_records_usage(client, monkeypatch):
    _ = client
    monkeypatch.setenv("LLM_MOCK", "1")
    uid = f"chat-user-{uuid.uuid4().hex[:8]}"
    text = asyncio.run(
        llm_service.chat(
            messages=[{"role": "user", "content": "meter me please"}],
            system_prompt="brief",
            user_id=uid,
            tenant_id="default",
            source="chat",
        )
    )
    assert text
    with Session(engine) as session:
        rows = list(
            session.exec(select(LLMUsageEvent).where(LLMUsageEvent.user_id == uid)).all()
        )
    assert len(rows) >= 1
    assert rows[-1].total_tokens > 0
    assert rows[-1].source == "chat"


def test_llm_usage_report_endpoint(client, admin_token):
    uid = f"report-user-{uuid.uuid4().hex[:8]}"
    record_llm_usage(
        provider="openai",
        model="gpt-4o-mini",
        prompt_tokens=200,
        completion_tokens=100,
        total_tokens=300,
        estimated_cost_usd=0.0002,
        user_id=uid,
        tenant_id="default",
        source="chat",
    )
    res = client.get("/api/reports/llm-usage?days=30", headers=auth_headers(admin_token))
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["calls"] >= 1
    assert data["total_tokens"] >= 300
    assert any(u["user_id"] == uid for u in data["by_user"])
    assert isinstance(data["by_provider"], list)
    assert isinstance(data["budget"], list)
