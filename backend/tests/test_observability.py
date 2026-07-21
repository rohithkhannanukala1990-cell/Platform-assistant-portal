"""Error handling, request correlation, and structured logging tests."""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from unittest.mock import patch

from starlette.requests import Request

from backend.context import PlatformContext
from backend.main import global_exception_handler
from backend.observability.logger import JSONFormatter


def test_request_id_header_and_structured_request_log(client):
    with patch("backend.main.logger.info") as log_info:
        response = client.get("/health")

    request_id = response.headers["X-Request-ID"]
    assert str(uuid.UUID(request_id)) == request_id

    request_logs = [
        call
        for call in log_info.call_args_list
        if call.args and call.args[0] == "HTTP request"
    ]
    assert request_logs
    extra = request_logs[-1].kwargs["extra"]
    assert extra["request_id"] == request_id
    assert extra["method"] == "GET"
    assert extra["path"] == "/health"
    assert extra["status_code"] == 200
    assert extra["duration_ms"] >= 0


def test_global_exception_handler_hides_exception_detail():
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/explode",
            "headers": [],
            "query_string": b"",
            "server": ("testserver", 80),
            "client": ("testclient", 123),
            "scheme": "http",
        }
    )
    request.state.request_id = "request-123"

    with patch("backend.main.logger.exception") as log_exception:
        response = asyncio.run(
            global_exception_handler(request, RuntimeError("sensitive detail"))
        )

    body = json.loads(response.body)
    assert response.status_code == 500
    assert body["error"] == "Internal server error"
    assert body["detail"] == "An unexpected error occurred."
    assert "sensitive detail" not in response.body.decode()
    log_exception.assert_called_once_with(
        "Unhandled error",
        extra={
            "path": "/explode",
            "method": "GET",
            "request_id": "request-123",
        },
    )


def test_json_formatter_includes_request_id_and_structured_http_fields():
    record = logging.LogRecord(
        name="aiops",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="HTTP request",
        args=(),
        exc_info=None,
    )
    record.request_id = "request-456"
    record.method = "POST"
    record.path = "/api/example"
    record.status_code = 201
    record.duration_ms = 12.5

    data = json.loads(JSONFormatter().format(record))
    assert data["request_id"] == "request-456"
    assert data["method"] == "POST"
    assert data["path"] == "/api/example"
    assert data["status_code"] == 201
    assert data["duration_ms"] == 12.5


def test_platform_context_preserves_request_id():
    context = PlatformContext.from_dict(
        {"request_id": "request-789", "workspace_id": "workspace-1"}
    )
    assert context.request_id == "request-789"
    assert context.to_dict()["request_id"] == "request-789"
