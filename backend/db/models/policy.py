"""Command policy rules — Guardrails v2 (Phase G1)."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlmodel import Field, SQLModel

EFFECT_ALLOW = "allow"
EFFECT_DENY = "deny"
EFFECT_REQUIRE_APPROVAL = "require_approval"

VALID_EFFECTS = {EFFECT_ALLOW, EFFECT_DENY, EFFECT_REQUIRE_APPROVAL}


class CommandPolicyRule(SQLModel, table=True):
    """One structured guardrail rule evaluated by the command policy engine.

    Match fields are JSON-encoded lists; ``["*"]`` (or empty) matches anything.
    ``tenant_id`` NULL means the rule is a global default visible to all tenants.
    Lower ``priority`` evaluates first; the first matching rule wins per command.
    """

    __tablename__ = "command_policy_rules"

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    name: str = Field(index=True)
    priority: int = Field(default=100, index=True)
    enabled: bool = Field(default=True)
    match_roles: str = Field(default='["*"]')          # JSON list[str]
    match_environments: str = Field(default='["*"]')   # JSON list[str]
    match_tools: str = Field(default='["*"]')          # JSON list[str]
    match_command_prefixes: str = Field(default="[]")  # JSON list[str], argv prefix
    match_regex: Optional[str] = Field(default=None)
    effect: str = Field(default=EFFECT_REQUIRE_APPROVAL)  # allow | deny | require_approval
    max_risk: Optional[str] = Field(default=None)         # low | medium | high (informational)
    description: str = Field(default="")
    tenant_id: Optional[str] = Field(default=None, index=True)  # NULL = global
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
