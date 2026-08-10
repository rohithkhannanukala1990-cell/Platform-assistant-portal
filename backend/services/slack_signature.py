"""Slack request signature verification (Slack's ``v0=`` scheme).

Distinct from ``webhooks/security.py``'s GitHub-style ``sha256=`` scheme — Slack
signs ``v0:{timestamp}:{raw_body}`` with HMAC-SHA256 using the app's signing
secret, and requires the timestamp to be recent to prevent replay. This is
mandatory for every inbound Slack request and cannot be disabled by config.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import time

MAX_REQUEST_AGE_SECONDS = 300  # Slack recommends rejecting anything older than 5 minutes.


def _signing_secret() -> str:
    return (os.getenv("SLACK_SIGNING_SECRET") or "").strip()


def verify_slack_request(
    *,
    timestamp: str,
    body: bytes,
    signature: str,
    now: float | None = None,
) -> bool:
    """Return True only if the timestamp is fresh AND the signature matches.

    ``signature`` is the raw ``X-Slack-Signature`` header value (``v0=...``).
    """
    secret = _signing_secret()
    if not secret:
        return False
    if not timestamp or not signature:
        return False
    try:
        ts = int(timestamp)
    except (TypeError, ValueError):
        return False

    current = now if now is not None else time.time()
    if abs(current - ts) > MAX_REQUEST_AGE_SECONDS:
        return False

    raw = body if isinstance(body, (bytes, bytearray)) else str(body).encode()
    basestring = b"v0:" + str(ts).encode() + b":" + raw
    expected = "v0=" + hmac.new(secret.encode(), basestring, hashlib.sha256).hexdigest()
    try:
        return hmac.compare_digest(expected, signature)
    except (TypeError, ValueError):
        return False
