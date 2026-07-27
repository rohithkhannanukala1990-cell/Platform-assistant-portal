"""Compliance helpers: audit retention, secret redaction, immutable hash chain."""

from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlmodel import Session, delete, select

from ..auth import AuditLog
from ..database import engine

# Keys / substrings that must never appear as plaintext values in audit details.
_SECRET_KEY_MARKERS = (
    "secret",
    "token",
    "password",
    "passwd",
    "api_key",
    "apikey",
    "credential",
    "private_key",
    "authorization",
    "bearer",
    "vault_ref",
)

# Inline value patterns (JWT-ish, GitHub PAT, long hex/base64 secrets).
_SECRET_VALUE_PATTERNS = [
    re.compile(r"\bghp_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b"),  # JWT
    re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._\-+/=]{16,}"),
    re.compile(r"(?i)(password|passwd|token|secret|api[_-]?key)\s*[=:]\s*\S+"),
]

DEFAULT_AUDIT_RETENTION_DAYS = 90
GENESIS_HASH = "0" * 64


def redact_secrets(value: Any) -> Any:
    """Recursively redact secret-looking keys and inline secret values."""
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for k, v in value.items():
            if any(m in str(k).lower() for m in _SECRET_KEY_MARKERS):
                out[k] = "[REDACTED]"
            else:
                out[k] = redact_secrets(v)
        return out
    if isinstance(value, list):
        return [redact_secrets(v) for v in value]
    if isinstance(value, str):
        return redact_secret_text(value)
    return value


def redact_secret_text(text: str) -> str:
    if not text:
        return text
    out = text
    for pattern in _SECRET_VALUE_PATTERNS:
        out = pattern.sub(lambda m: (m.group(1) + "[REDACTED]") if m.lastindex else "[REDACTED]", out)
    return out


def sanitize_audit_detail(detail: str) -> str:
    """Best-effort redact of free-form audit detail before persistence."""
    raw = detail if detail is not None else ""
    if not str(raw).strip():
        return ""
    try:
        parsed = json.loads(raw)
        return json.dumps(redact_secrets(parsed), ensure_ascii=False, default=str)
    except (TypeError, json.JSONDecodeError):
        return redact_secret_text(str(raw))


def get_audit_retention_days() -> int:
    """Read retention from settings, then env, then default."""
    try:
        from ..database import get_settings

        settings = get_settings() or {}
        raw = settings.get("audit_log_retention_days")
        if raw is not None and str(raw).strip():
            days = int(str(raw).strip())
            return max(1, min(days, 3650))
    except Exception:
        pass
    env_raw = (os.getenv("AUDIT_LOG_RETENTION_DAYS") or "").strip()
    if env_raw:
        try:
            return max(1, min(int(env_raw), 3650))
        except ValueError:
            pass
    return DEFAULT_AUDIT_RETENTION_DAYS


def set_audit_retention_days(days: int) -> int:
    days = max(1, min(int(days), 3650))
    from ..database import update_settings

    update_settings({"audit_log_retention_days": str(days)})
    return days


def prune_audit_logs(*, retention_days: Optional[int] = None) -> int:
    """Delete audit rows older than retention. Returns deleted count (best-effort)."""
    days = retention_days if retention_days is not None else get_audit_retention_days()
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    with Session(engine) as session:
        before = len(session.exec(select(AuditLog)).all())
        session.exec(delete(AuditLog).where(AuditLog.timestamp < cutoff))
        session.commit()
        after = len(session.exec(select(AuditLog)).all())
    return max(0, before - after)


def _canonical_record(record: dict[str, Any]) -> str:
    # Stable subset for chaining — ignore ephemeral presentation fields.
    payload = {
        "id": record.get("id"),
        "timestamp": record.get("timestamp"),
        "actor": record.get("actor") or record.get("user_id"),
        "actor_role": record.get("actor_role") or record.get("role"),
        "event_type": record.get("event_type") or record.get("action"),
        "resource": record.get("resource") or record.get("resource_id"),
        "detail": record.get("detail") or "",
        "ip_address": record.get("ip_address") or "",
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def attach_hash_chain(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Attach a simple SHA-256 hash chain for immutable export verification.

    Records should be chronological (oldest first) for a meaningful chain.
    """
    prev = GENESIS_HASH
    chained: list[dict[str, Any]] = []
    for row in records:
        entry = dict(row)
        digest = hashlib.sha256((_canonical_record(entry) + prev).encode("utf-8")).hexdigest()
        entry["prev_hash"] = prev
        entry["entry_hash"] = digest
        chained.append(entry)
        prev = digest
    return {
        "immutable": True,
        "algorithm": "sha256",
        "genesis": GENESIS_HASH,
        "chain_tip": prev if chained else GENESIS_HASH,
        "count": len(chained),
        "results": chained,
    }


def verify_hash_chain(payload: dict[str, Any]) -> bool:
    """Verify an immutable export payload's hash chain."""
    results = payload.get("results") or []
    if not isinstance(results, list):
        return False
    prev = GENESIS_HASH
    for row in results:
        if not isinstance(row, dict):
            return False
        if row.get("prev_hash") != prev:
            return False
        expected = hashlib.sha256((_canonical_record(row) + prev).encode("utf-8")).hexdigest()
        if row.get("entry_hash") != expected:
            return False
        prev = expected
    tip = payload.get("chain_tip") or GENESIS_HASH
    return tip == prev
