import hmac
import hashlib
import os
from fastapi import HTTPException

WEBHOOK_SECRETS = {
    "github":     os.getenv("GITHUB_WEBHOOK_SECRET", ""),
    "gitlab":     os.getenv("GITLAB_WEBHOOK_SECRET", ""),
    "pagerduty":  os.getenv("PAGERDUTY_WEBHOOK_SECRET", ""),
    "datadog":    os.getenv("DATADOG_WEBHOOK_SECRET", ""),
    "airflow":    os.getenv("AIRFLOW_WEBHOOK_SECRET", ""),
}


def verify_webhook_signature(source: str, payload: bytes, signature: str) -> bool:
    secret = WEBHOOK_SECRETS.get(source.lower(), "")
    if not secret:
        return True  # skip verification for unconfigured sources
    expected = "sha256=" + hmac.new(
        secret.encode() if isinstance(secret, str) else secret,
        payload if isinstance(payload, bytes) else payload.encode(),
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


def require_valid_signature(source: str, payload: bytes, request_headers: dict):
    sig = request_headers.get("x-hub-signature-256", "") or \
          request_headers.get("x-webhook-signature", "")
    if not verify_webhook_signature(source, payload, sig):
        raise HTTPException(status_code=403, detail="Invalid webhook signature")

