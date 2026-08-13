import hashlib
import hmac
import os

from fastapi import HTTPException

from ..context import PlatformContext
from ..observability.logger import logger

_SECRET_ENV_KEYS = {
    "github": "GITHUB_WEBHOOK_SECRET",
    "gitlab": "GITLAB_WEBHOOK_SECRET",
    "pagerduty": "PAGERDUTY_WEBHOOK_SECRET",
    "datadog": "DATADOG_WEBHOOK_SECRET",
    "airflow": "AIRFLOW_WEBHOOK_SECRET",
}


def _load_webhook_secrets() -> dict[str, str]:
    return {
        source: os.getenv(env_key, "") or ""
        for source, env_key in _SECRET_ENV_KEYS.items()
    }


# Kept for backwards compatibility with importers; prefer `_load_webhook_secrets()`.
WEBHOOK_SECRETS = _load_webhook_secrets()


def _secret_for(source: str) -> str:
    key = (source or "").strip().lower()
    secrets = _load_webhook_secrets()
    WEBHOOK_SECRETS.clear()
    WEBHOOK_SECRETS.update(secrets)
    return secrets.get(key, "")


def verify_webhook_signature(source: str, payload: bytes, signature: str) -> bool:
    secret = _secret_for(source)
    if not secret:
        # Missing secrets are handled by require_valid_signature (env-aware).
        return True
    if not signature:
        return False
    raw = payload if isinstance(payload, (bytes, bytearray)) else str(payload).encode()
    expected = "sha256=" + hmac.new(
        secret.encode() if isinstance(secret, str) else secret,
        raw,
        hashlib.sha256,
    ).hexdigest()
    try:
        return hmac.compare_digest(expected, signature)
    except (TypeError, ValueError):
        return False


def require_valid_signature(source: str, payload: bytes, request_headers: dict):
    source_key = (source or "").strip().lower()
    secret = _secret_for(source_key)
    if not secret and not PlatformContext.is_dev_environment():
        logger.critical(
            "Webhook secret not configured for non-dev environment",
            extra={
                "source": source_key or "unknown",
                "env": PlatformContext.current_env(),
            },
        )
        raise HTTPException(
            status_code=500,
            detail="Webhook secret not configured",
        )

    headers = {str(k).lower(): v for k, v in (request_headers or {}).items()}
    sig = headers.get("x-hub-signature-256", "") or headers.get(
        "x-webhook-signature", ""
    )
    if not verify_webhook_signature(source_key, payload, sig):
        try:
            from ..observability.metrics import record_webhook_signature_failure

            record_webhook_signature_failure()
        except Exception:
            pass
        raise HTTPException(status_code=403, detail="Invalid webhook signature")
