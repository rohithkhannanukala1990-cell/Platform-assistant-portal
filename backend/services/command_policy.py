"""Structured command policy engine — Guardrails v2 (Phase G1).

Evaluates commands against DB-backed ``CommandPolicyRule`` rows in priority
order (lower first). The baseline regex blocklist in ``command_validator``
always runs FIRST; a baseline hit is an unconditional deny.

Fail-closed behavior:
- A command that cannot be parsed by ``shlex.split`` → ``require_approval``.
- ``evaluate_commands`` aggregates with worst-effect-wins:
  deny > require_approval > allow.
"""

from __future__ import annotations

import json
import re
import shlex
from dataclasses import dataclass, field

from sqlmodel import Session, select

from ..db.core import engine
from ..db.models.policy import (
    EFFECT_ALLOW,
    EFFECT_DENY,
    EFFECT_REQUIRE_APPROVAL,
    CommandPolicyRule,
)

_EFFECT_SEVERITY = {EFFECT_ALLOW: 0, EFFECT_REQUIRE_APPROVAL: 1, EFFECT_DENY: 2}

_PROD_ALIASES = {"production", "prod", "dr"}


@dataclass
class PolicyDecision:
    effect: str = EFFECT_ALLOW
    reasons: list[str] = field(default_factory=list)
    matched_rule_ids: list[str] = field(default_factory=list)

    @property
    def safe_for_auto(self) -> bool:
        return self.effect == EFFECT_ALLOW

    def to_dict(self) -> dict:
        return {
            "effect": self.effect,
            "reasons": self.reasons,
            "matched_rule_ids": self.matched_rule_ids,
            "safe_for_auto": self.safe_for_auto,
        }


def _norm(value: str | None) -> str:
    return (value or "").strip().lower()


def _norm_environment(env: str | None) -> str:
    e = _norm(env)
    if e in _PROD_ALIASES:
        return "production"
    return e or "development"


def _json_list(raw: str | None) -> list[str]:
    try:
        data = json.loads(raw or "[]")
    except (json.JSONDecodeError, TypeError):
        return []
    if not isinstance(data, list):
        return []
    return [str(item) for item in data]


def _list_matches(rule_values: list[str], candidate: str) -> bool:
    """True when the rule list is empty / wildcard or contains the candidate."""
    if not rule_values:
        return True
    lowered = {_norm(v) for v in rule_values}
    if "*" in lowered:
        return True
    if candidate in lowered:
        return True
    # Environments: treat prod aliases as one bucket
    if candidate == "production" and lowered & _PROD_ALIASES:
        return True
    return False


def _prefix_matches(prefix: str, argv: list[str]) -> bool:
    try:
        prefix_argv = shlex.split(prefix)
    except ValueError:
        return False
    if not prefix_argv or len(prefix_argv) > len(argv):
        return False
    for i, token in enumerate(prefix_argv):
        expected = token.lower()
        actual = argv[i].lower()
        # Tokens like "if=" match "if=/dev/zero"; otherwise exact match.
        if expected.endswith("="):
            if not actual.startswith(expected):
                return False
        elif actual != expected:
            return False
    return True


def _command_condition_matches(rule: CommandPolicyRule, command: str, argv: list[str]) -> bool:
    prefixes = _json_list(rule.match_command_prefixes)
    regex = (rule.match_regex or "").strip()

    if not prefixes and not regex:
        return True  # rule matches any command (context-only rule)

    if prefixes and any(_prefix_matches(p, argv) for p in prefixes):
        return True
    if regex:
        try:
            if re.search(regex, command, re.IGNORECASE):
                return True
        except re.error:
            return False
    return False


def _load_rules(tenant_id: str | None) -> list[CommandPolicyRule]:
    with Session(engine) as session:
        q = select(CommandPolicyRule).where(CommandPolicyRule.enabled == True)  # noqa: E712
        rows = session.exec(q).all()
    tenant = _norm(tenant_id)
    visible = [
        r for r in rows
        if r.tenant_id is None or _norm(r.tenant_id) == tenant
    ]
    return sorted(visible, key=lambda r: (r.priority, r.created_at.isoformat() if r.created_at else ""))


def evaluate_command(
    command: str,
    *,
    role: str = "User",
    environment: str = "development",
    tool: str = "shell",
    tenant_id: str | None = None,
) -> PolicyDecision:
    """Evaluate one command. Baseline blocklist runs first, then DB rules."""
    from ..command_validator import CommandValidator

    text = (command or "").strip()
    if not text:
        return PolicyDecision(effect=EFFECT_ALLOW, reasons=["empty command"])

    baseline = CommandValidator.validate([text])
    if not baseline.safe:
        return PolicyDecision(
            effect=EFFECT_DENY,
            reasons=[f"baseline_blocklist: {v}" for v in baseline.violations],
            matched_rule_ids=["baseline_blocklist"],
        )

    try:
        argv = shlex.split(text)
    except ValueError as exc:
        return PolicyDecision(
            effect=EFFECT_REQUIRE_APPROVAL,
            reasons=[f"unparseable command (fail closed): {exc}"],
            matched_rule_ids=["parse_failure"],
        )
    if not argv:
        return PolicyDecision(effect=EFFECT_ALLOW, reasons=["empty command"])

    role_n = _norm(role) or "user"
    env_n = _norm_environment(environment)
    tool_n = _norm(tool) or "shell"

    for rule in _load_rules(tenant_id):
        if not _list_matches(_json_list(rule.match_roles), role_n):
            continue
        if not _list_matches(_json_list(rule.match_environments), env_n):
            continue
        if not _list_matches(_json_list(rule.match_tools), tool_n):
            continue
        if not _command_condition_matches(rule, text, argv):
            continue
        effect = rule.effect if rule.effect in _EFFECT_SEVERITY else EFFECT_REQUIRE_APPROVAL
        return PolicyDecision(
            effect=effect,
            reasons=[f"rule '{rule.name}': {rule.description or effect}"],
            matched_rule_ids=[rule.id],
        )

    return PolicyDecision(effect=EFFECT_ALLOW, reasons=["no matching rule (default allow)"])


def evaluate_commands(
    commands: list[str],
    *,
    role: str = "User",
    environment: str = "development",
    tool: str = "shell",
    tenant_id: str | None = None,
) -> PolicyDecision:
    """Evaluate a list of commands; worst effect wins (deny > require_approval > allow)."""
    worst = PolicyDecision(effect=EFFECT_ALLOW)
    reasons: list[str] = []
    matched: list[str] = []
    for cmd in commands or []:
        decision = evaluate_command(
            cmd, role=role, environment=environment, tool=tool, tenant_id=tenant_id
        )
        if decision.effect != EFFECT_ALLOW:
            reasons.extend(f"{cmd!r} → {r}" for r in decision.reasons)
            matched.extend(m for m in decision.matched_rule_ids if m not in matched)
        if _EFFECT_SEVERITY[decision.effect] > _EFFECT_SEVERITY[worst.effect]:
            worst = decision
    return PolicyDecision(effect=worst.effect, reasons=reasons, matched_rule_ids=matched)
