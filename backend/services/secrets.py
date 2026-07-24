"""Encrypt-at-rest helpers for ToolAccount credentials."""

from __future__ import annotations

import os
import threading
from typing import Optional

from fastapi import HTTPException

_warned_passthrough = False
_warn_lock = threading.Lock()


def _env_name() -> str:
    return (os.getenv("ENV") or "dev").strip().lower()


def _is_dev_like() -> bool:
    env = _env_name()
    if env in {"dev", "development", "test", "local"}:
        return True
    if (os.getenv("LLM_MOCK") or "").strip().lower() in {"1", "true", "yes", "on"}:
        return True
    return False


def _is_production() -> bool:
    return _env_name() in {"production", "prod", "dr"}


class SecretBox:
    """Fernet encrypt/decrypt with optional passthrough in non-production."""

    def __init__(self, key: Optional[str] = None):
        raw = (key if key is not None else os.getenv("SECRETS_ENCRYPTION_KEY") or "").strip()
        self._fernet = None
        if raw:
            try:
                from cryptography.fernet import Fernet

                self._fernet = Fernet(raw.encode() if isinstance(raw, str) else raw)
            except Exception:
                self._fernet = None

    @property
    def encryption_enabled(self) -> bool:
        return self._fernet is not None

    def _warn_passthrough_once(self) -> None:
        global _warned_passthrough
        with _warn_lock:
            if _warned_passthrough:
                return
            _warned_passthrough = True
        try:
            from ..observability.logger import logger

            logger.warning(
                "SECRETS_ENCRYPTION_KEY unset — storing credentials in passthrough mode (dev/test only)"
            )
        except Exception:
            pass

    def encrypt(self, plaintext: str) -> str:
        text = plaintext if plaintext is not None else ""
        if not str(text).strip():
            return ""
        if self._fernet is not None:
            return self._fernet.encrypt(str(text).encode("utf-8")).decode("utf-8")
        if _is_production():
            raise HTTPException(
                status_code=503,
                detail="Secrets encryption is not configured (SECRETS_ENCRYPTION_KEY)",
            )
        self._warn_passthrough_once()
        return str(text)

    def decrypt(self, token: str) -> str:
        raw = token if token is not None else ""
        if not str(raw).strip():
            return ""
        if self._fernet is None:
            return str(raw)
        try:
            return self._fernet.decrypt(str(raw).encode("utf-8")).decode("utf-8")
        except Exception:
            # Legacy plaintext rows written before encryption was enabled.
            return str(raw)


_box: SecretBox | None = None
_box_lock = threading.Lock()


def get_secret_box() -> SecretBox:
    global _box
    with _box_lock:
        if _box is None:
            _box = SecretBox()
        return _box


def reset_secret_box_for_tests() -> None:
    """Clear cached box so tests can change SECRETS_ENCRYPTION_KEY."""
    global _box, _warned_passthrough
    with _box_lock:
        _box = None
        _warned_passthrough = False


def encrypt_secret(plaintext: str) -> str:
    return get_secret_box().encrypt(plaintext)


def decrypt_secret(token: str) -> str:
    return get_secret_box().decrypt(token)
