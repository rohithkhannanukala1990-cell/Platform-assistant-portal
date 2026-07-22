import logging
import json
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Any, Optional

_request_id_var: ContextVar[Optional[str]] = ContextVar("request_id", default=None)
_workspace_id_var: ContextVar[Optional[str]] = ContextVar("workspace_id", default=None)

# TODO(S3-P3.1): Ensure health and connector logs include request_id, workspace_id, and connector name
_STRUCTURED_KEYS = (
    "incident_id",
    "severity",
    "provider",
    "user",
    "source",
    "confidence",
    "task_id",
    "method",
    "path",
    "status_code",
    "duration_ms",
    "user_id",
    "workspace_id",
    "request_id",
    "connector",
    "probe_name",
    "error_type",
    "status",
    "latency_ms",
)


def set_request_context(
    *,
    request_id: Optional[str] = None,
    workspace_id: Optional[str] = None,
) -> None:
    """Bind correlation fields for the current request (used by health/connectors)."""
    if request_id is not None:
        _request_id_var.set(request_id or None)
    if workspace_id is not None:
        _workspace_id_var.set(workspace_id or None)


def clear_request_context() -> None:
    _request_id_var.set(None)
    _workspace_id_var.set(None)


def get_request_context() -> dict[str, Any]:
    return {
        "request_id": _request_id_var.get(),
        "workspace_id": _workspace_id_var.get(),
    }


class JSONFormatter(logging.Formatter):
    def format(self, record):
        data = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "service": "aiops-portal",
            "component": record.name,
            "message": record.getMessage(),
        }
        for key in _STRUCTURED_KEYS:
            if hasattr(record, key):
                data[key] = getattr(record, key)

        # Fall back to request-scoped contextvars when extras omitted.
        if not data.get("request_id"):
            rid = _request_id_var.get()
            if rid:
                data["request_id"] = rid
        if not data.get("workspace_id"):
            wid = _workspace_id_var.get()
            if wid:
                data["workspace_id"] = wid

        if record.exc_info:
            data["exception"] = self.formatException(record.exc_info)

        return json.dumps(data, default=str)


def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(JSONFormatter())
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logger.propagate = False
    return logger


logger = get_logger("aiops")
