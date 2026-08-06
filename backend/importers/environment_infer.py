"""Infer portal environments from account names, IDs, and discovery metadata.

Canonical environments match CSV/JSON import validation:
local | development | test | staging | production | dr
"""

from __future__ import annotations

import re
from typing import Any, Iterable

VALID_ENVIRONMENTS = (
    "local",
    "development",
    "test",
    "staging",
    "production",
    "dr",
)

# Ordered from most specific / highest severity so early matches win.
_ENV_PATTERNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "dr",
        (
            r"\bdr\b",
            r"disaster[-_ ]?recovery",
            r"\bfailover\b",
        ),
    ),
    (
        "production",
        (
            r"\bprod(?:uction)?\b",
            r"\bprd\b",
            r"\blive\b",
            r"\bmain\b",
        ),
    ),
    (
        "staging",
        (
            r"\bstag(?:e|ing)?\b",
            r"\bstg\b",
            r"\bpre[-_]?prod(?:uction)?\b",
            r"\buat\b",
            r"\bpreview\b",
        ),
    ),
    (
        "test",
        (
            r"\btest(?:ing)?\b",
            r"\bqa\b",
            r"\bquality\b",
            r"\bint(?:egration)?\b",
        ),
    ),
    (
        "development",
        (
            r"\bdev(?:el(?:op(?:ment)?)?)?\b",
            r"\bdevel\b",
            r"\bnon[-_]?prod\b",
        ),
    ),
    (
        "local",
        (
            r"\blocal(?:host)?\b",
            r"\bsandbox\b",
            r"\bsbx\b",
            r"\blaptop\b",
        ),
    ),
)

_COMPILED = tuple(
    (env, tuple(re.compile(pat, re.IGNORECASE) for pat in pats))
    for env, pats in _ENV_PATTERNS
)


def normalize_environment(value: str | None, *, default: str = "development") -> str:
    """Map aliases / free text onto a canonical environment id."""
    raw = (value or "").strip().lower()
    if not raw:
        return default if default in VALID_ENVIRONMENTS else "development"
    if raw in VALID_ENVIRONMENTS:
        return raw
    # Common aliases
    aliases = {
        "prod": "production",
        "prd": "production",
        "live": "production",
        "stage": "staging",
        "stg": "staging",
        "preprod": "staging",
        "pre-prod": "staging",
        "uat": "staging",
        "qa": "test",
        "testing": "test",
        "dev": "development",
        "develop": "development",
        "devel": "development",
        "sbx": "local",
        "sandbox": "local",
    }
    if raw in aliases:
        return aliases[raw]
    inferred, _, _ = infer_environment(raw, default=default)
    return inferred


def _join_hints(parts: Iterable[Any]) -> str:
    bits: list[str] = []
    for p in parts:
        if p is None:
            continue
        s = str(p).strip()
        if s:
            bits.append(s)
    return " ".join(bits)


def infer_environment(
    *hints: Any,
    explicit: str | None = None,
    default: str = "development",
) -> tuple[str, str, str]:
    """Return (environment, source, confidence).

    source: explicit | inferred | default
    confidence: high | medium | low
    """
    if explicit and str(explicit).strip():
        env = normalize_environment(str(explicit), default=default)
        return env, "explicit", "high"

    text = _join_hints(hints)
    if not text:
        env = default if default in VALID_ENVIRONMENTS else "development"
        return env, "default", "low"

    # Prefer whole-token / word-boundary matches in order of severity.
    for env, patterns in _COMPILED:
        for pat in patterns:
            if pat.search(text):
                # Exact canonical token in the string → high; otherwise medium.
                conf = "high" if re.search(rf"\b{re.escape(env)}\b", text, re.I) else "medium"
                return env, "inferred", conf

    # Fallback: hyphen/underscore segments like my-prod-account
    tokens = re.split(r"[^a-z0-9]+", text.lower())
    token_map = {
        "prod": "production",
        "prd": "production",
        "production": "production",
        "live": "production",
        "stage": "staging",
        "stg": "staging",
        "staging": "staging",
        "preprod": "staging",
        "uat": "staging",
        "test": "test",
        "qa": "test",
        "dev": "development",
        "development": "development",
        "local": "local",
        "sandbox": "local",
        "sbx": "local",
        "dr": "dr",
    }
    for tok in tokens:
        if tok in token_map:
            return token_map[tok], "inferred", "medium"

    env = default if default in VALID_ENVIRONMENTS else "development"
    return env, "default", "low"


def requires_hitl_for_env(environment: str | None) -> bool:
    return normalize_environment(environment) in {"production", "dr"}


def apply_environment_to_account(
    account: dict[str, Any],
    *extra_hints: Any,
    explicit: str | None = None,
    default: str = "development",
) -> dict[str, Any]:
    """Mutate/copy an account dict with inferred environment + metadata."""
    out = dict(account)
    hints = [
        out.get("account_name"),
        out.get("account_identifier"),
        out.get("instance_url"),
        out.get("region"),
        out.get("tool_id"),
        *(extra_hints or ()),
    ]
    meta = out.get("metadata") if isinstance(out.get("metadata"), dict) else {}
    if meta:
        hints.extend(
            [
                meta.get("namespace"),
                meta.get("project_key"),
                meta.get("name"),
                meta.get("org"),
            ]
        )

    # Prefer an already-valid environment on the row as explicit only when
    # caller did not pass a stronger override.
    row_env = out.get("environment")
    env_override = explicit
    if not env_override and row_env and str(row_env).strip().lower() in VALID_ENVIRONMENTS:
        # Keep only if it wasn't a hard-coded discovery default we want to re-evaluate.
        # Callers should clear environment before calling when they want re-inference.
        env_override = str(row_env)

    env, source, confidence = infer_environment(
        *hints,
        explicit=env_override,
        default=default,
    )
    out["environment"] = env
    out["environment_source"] = source
    out["environment_confidence"] = confidence
    out["requires_hitl"] = bool(out.get("requires_hitl")) or requires_hitl_for_env(env)
    return out
