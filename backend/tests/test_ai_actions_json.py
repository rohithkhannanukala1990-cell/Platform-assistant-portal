"""Phase 3: ACTIONS_JSON parsing, standardized executor results, HITL policy."""

import asyncio
import json
from unittest.mock import AsyncMock, patch

from backend.ai.llm_router import llm_router
from backend.ai.tool_executor import tool_executor
from backend.observability.metrics import (
    AI_ACTIONS_APPROVED_TOTAL,
    AI_ACTIONS_ERROR_TOTAL,
    AI_ACTIONS_REJECTED_TOTAL,
)
from backend.routers.ai_assistant import _parse_actions_json


def auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_system_prompt_documents_actions_json_format():
    prompt = llm_router.build_system_prompt(
        {"workspace_name": "ws", "environment": "production", "tools": []}
    )
    assert "ACTIONS_JSON" in prompt
    assert '"actions"' in prompt


def test_parse_actions_json_extracts_actions_and_prose():
    text = (
        "I recommend restarting the payments service.\n\n"
        'ACTIONS_JSON: {"actions": [{"resource": "service", '
        '"operation": "restart", "environment": "production", '
        '"identifier": "payments", "reason": "OOM crash loop"}]}'
    )
    natural, actions = _parse_actions_json(text)
    assert natural == "I recommend restarting the payments service."
    assert len(actions) == 1
    assert actions[0]["operation"] == "restart"
    assert actions[0]["identifier"] == "payments"


def test_parse_actions_json_invalid_json_counts_error_and_returns_no_actions():
    before = AI_ACTIONS_ERROR_TOTAL._value.get()
    natural, actions = _parse_actions_json(
        'Some advice. ACTIONS_JSON: {"actions": [ this is not valid json }'
    )
    assert actions == []
    assert "Some advice." in natural
    assert AI_ACTIONS_ERROR_TOTAL._value.get() == before + 1


def test_parse_actions_json_without_marker_returns_full_text():
    natural, actions = _parse_actions_json("Just an explanation, no actions.")
    assert natural == "Just an explanation, no actions."
    assert actions == []


def test_requires_hitl_for_production_mutations():
    assert tool_executor.requires_hitl("platform", "deploy_to_production", "production")
    assert tool_executor.requires_hitl("platform", "rotate_secrets", "production")
    assert tool_executor.requires_hitl("platform", "apply_terraform", "production")
    # Unlisted but mutating operation names still require HITL in production.
    assert tool_executor.requires_hitl("platform", "modify_dns_zone", "production")
    assert tool_executor.requires_hitl("platform", "terminate_instance", "production")
    # Read-only operations do not.
    assert not tool_executor.requires_hitl("platform", "list_services", "production")
    # Development stays permissive.
    assert not tool_executor.requires_hitl("platform", "restart_service", "development")


def test_executor_returns_standardized_result_dict():
    execution = asyncio.run(
        tool_executor.execute(
            tool_id="platform",
            action="list_services",
            parameters={"resource": "service", "identifier": "api"},
            environment="development",
            conversation_id="conv-1",
        )
    )
    for key in ("id", "conversation_id", "tool_id", "action", "parameters",
                "requires_hitl", "status", "created_at", "executed_at"):
        assert key in execution
    result = execution["result"]
    assert result["success"] is True
    assert "output" in result
    assert result["metadata"]["identifier"] == "api"


def test_chat_uses_actions_json_for_hitl_execution(client, admin_token):
    llm_response = (
        "Restarting payments is required.\n"
        'ACTIONS_JSON: {"actions": [{"resource": "service", '
        '"operation": "restart", "environment": "production", '
        '"identifier": "payments-svc", "reason": "crash loop"}]}'
    )
    with patch(
        "backend.routers.ai_assistant.llm_router.chat",
        new_callable=AsyncMock,
        return_value=llm_response,
    ):
        response = client.post(
            "/api/ai/chat",
            json={"message": "Fix payments", "environment": "production"},
            headers=auth_headers(admin_token),
        )

    assert response.status_code == 200, response.text
    pending = response.json()["pending_execution"]
    assert pending is not None
    assert pending["action"] == "restart_service"
    assert pending["status"] == "pending_approval"
    assert pending["requires_hitl"] is True
    assert pending["parameters"]["identifier"] == "payments-svc"
    assert pending["parameters"]["reason"] == "crash loop"


def test_hitl_approve_and_reject_increment_metrics(client, admin_token):
    headers = auth_headers(admin_token)
    llm_response = (
        'Do it. ACTIONS_JSON: {"actions": [{"resource": "service", '
        '"operation": "deploy", "environment": "production", '
        '"identifier": "api", "reason": "release"}]}'
    )

    def start_execution():
        with patch(
            "backend.routers.ai_assistant.llm_router.chat",
            new_callable=AsyncMock,
            return_value=llm_response,
        ):
            r = client.post(
                "/api/ai/chat",
                json={"message": "Deploy the api", "environment": "production"},
                headers=headers,
            )
        assert r.status_code == 200, r.text
        return r.json()["pending_execution"]["id"]

    approved_before = AI_ACTIONS_APPROVED_TOTAL._value.get()
    rejected_before = AI_ACTIONS_REJECTED_TOTAL._value.get()

    approve_id = start_execution()
    approve = client.post(
        f"/api/ai/executions/{approve_id}/approve",
        json={"approved_by": "admin"},
        headers=headers,
    )
    assert approve.status_code == 200, approve.text
    assert approve.json()["status"] == "completed"

    reject_id = start_execution()
    reject = client.post(
        f"/api/ai/executions/{reject_id}/reject",
        json={"rejected_by": "admin", "reason": "not now"},
        headers=headers,
    )
    assert reject.status_code == 200, reject.text
    assert reject.json()["status"] == "rejected"

    assert AI_ACTIONS_APPROVED_TOTAL._value.get() == approved_before + 1
    assert AI_ACTIONS_REJECTED_TOTAL._value.get() == rejected_before + 1


def test_chat_without_actions_json_still_falls_back_to_keywords(client, admin_token):
    with patch(
        "backend.routers.ai_assistant.llm_router.chat",
        new_callable=AsyncMock,
        return_value="Recommendation: restart the API pod now.",
    ):
        response = client.post(
            "/api/ai/chat",
            json={"message": "What should we do?", "environment": "production"},
            headers=auth_headers(admin_token),
        )
    assert response.status_code == 200, response.text
    pending = response.json()["pending_execution"]
    assert pending is not None
    assert pending["action"] == "restart_service"
