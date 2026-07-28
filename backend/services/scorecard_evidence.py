"""Evidence-based scorecard evaluation (Phase G6 v2)."""

from __future__ import annotations

import json
from typing import Any

from ..routers.catalog import CatalogEntity

# Weights for overall score (sum = 1.0)
CHECK_WEIGHTS: dict[str, float] = {
    "has_owner": 0.20,
    "has_repo": 0.20,
    "has_runbook_url": 0.15,
    "ci_green": 0.15,
    "oncall_link": 0.15,
    "tier_set": 0.15,
}


def parse_entity_meta(entity: CatalogEntity) -> dict[str, Any]:
    """Extract optional runbook/oncall/tier from tags JSON or key=value tags."""
    meta: dict[str, Any] = {
        "runbook_url": None,
        "oncall_link": None,
        "tier": None,
    }
    raw = (entity.tags or "").strip()
    if not raw:
        return meta
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError, ValueError):
        data = None

    if isinstance(data, dict):
        meta["runbook_url"] = data.get("runbook_url") or data.get("runbook")
        meta["oncall_link"] = data.get("oncall_link") or data.get("oncall")
        meta["tier"] = data.get("tier") or data.get("service_tier")
        return meta

    items = data if isinstance(data, list) else [p.strip() for p in raw.split(",") if p.strip()]
    for item in items:
        text = str(item)
        low = text.lower()
        if low.startswith("runbook:") or low.startswith("runbook_url:"):
            meta["runbook_url"] = text.split(":", 1)[1].strip()
        elif low.startswith("oncall:") or low.startswith("oncall_link:"):
            meta["oncall_link"] = text.split(":", 1)[1].strip()
        elif low.startswith("tier:"):
            meta["tier"] = text.split(":", 1)[1].strip()
    return meta


def _check(
    *,
    check_id: str,
    category: str,
    check_name: str,
    passed: bool,
    evidence: dict[str, Any],
    pass_rationale: str,
    fail_rationale: str,
) -> dict[str, Any]:
    return {
        "check_id": check_id,
        "category": category,
        "check_name": check_name,
        "status": "pass" if passed else "fail",
        "score": 100 if passed else 0,
        "rationale": pass_rationale if passed else fail_rationale,
        "evidence": evidence,
        "weight": CHECK_WEIGHTS.get(check_id, 0.0),
    }


def _ci_green_from_entity(entity: CatalogEntity, meta: dict[str, Any]) -> tuple[bool, dict[str, Any]]:
    """
    Offline-safe CI check: pass when repo looks like GitHub and health is not degraded,
    or when tags explicitly mark ci=green. Never calls the network.
    """
    evidence: dict[str, Any] = {
        "source": "entity_metadata",
        "repo_url": entity.repo_url,
        "health_status": entity.health_status,
    }
    raw_tags = (entity.tags or "").lower()
    if "ci:green" in raw_tags or '"ci": "green"' in raw_tags or "ci=green" in raw_tags:
        evidence["marker"] = "ci:green"
        return True, evidence
    if meta.get("ci") in ("green", "passing", "pass"):
        evidence["marker"] = str(meta.get("ci"))
        return True, evidence
    repo = (entity.repo_url or "").lower()
    health = (entity.health_status or "unknown").lower()
    if "github.com" in repo and health in ("healthy", "ok"):
        evidence["inferred"] = "github_repo_and_healthy"
        return True, evidence
    if not repo:
        evidence["reason"] = "no_repo"
        return False, evidence
    evidence["reason"] = "ci_status_unknown"
    return False, evidence


def build_evidence_checks(entity: CatalogEntity) -> list[dict[str, Any]]:
    """Deterministic Port/Backstage-style checks with pass/fail evidence."""
    meta = parse_entity_meta(entity)
    owner = (entity.owner_team or "").strip()
    repo = (entity.repo_url or "").strip()
    runbook = (meta.get("runbook_url") or "").strip()
    oncall = (meta.get("oncall_link") or "").strip()
    tier = (meta.get("tier") or "").strip()
    ci_ok, ci_evidence = _ci_green_from_entity(entity, meta)

    return [
        _check(
            check_id="has_owner",
            category="Ownership",
            check_name="has_owner",
            passed=bool(owner),
            evidence={"owner_team": owner or None},
            pass_rationale=f"Owner team is '{owner}'.",
            fail_rationale="Owner team is missing.",
        ),
        _check(
            check_id="has_repo",
            category="Documentation",
            check_name="has_repo",
            passed=bool(repo),
            evidence={"repo_url": repo or None},
            pass_rationale="Repository URL is set.",
            fail_rationale="Repository URL is missing.",
        ),
        _check(
            check_id="has_runbook_url",
            category="Documentation",
            check_name="has_runbook_url",
            passed=bool(runbook),
            evidence={"runbook_url": runbook or None, "tags": entity.tags},
            pass_rationale=f"Runbook URL present ({runbook}).",
            fail_rationale="No runbook_url in entity tags metadata.",
        ),
        _check(
            check_id="ci_green",
            category="Reliability",
            check_name="ci_green",
            passed=ci_ok,
            evidence=ci_evidence,
            pass_rationale="CI appears green from connected metadata.",
            fail_rationale="CI green status not evidenced (connect GitHub or set ci:green tag).",
        ),
        _check(
            check_id="oncall_link",
            category="Reliability",
            check_name="oncall_link",
            passed=bool(oncall),
            evidence={"oncall_link": oncall or None},
            pass_rationale=f"On-call link present ({oncall}).",
            fail_rationale="No oncall_link in entity tags metadata.",
        ),
        _check(
            check_id="tier_set",
            category="Ownership",
            check_name="tier_set",
            passed=bool(tier),
            evidence={"tier": tier or None},
            pass_rationale=f"Service tier is '{tier}'.",
            fail_rationale="Service tier is not set in tags metadata.",
        ),
    ]


def weighted_overall_score(checks: list[dict[str, Any]]) -> int:
    total_w = 0.0
    earned = 0.0
    for c in checks:
        w = float(c.get("weight") or CHECK_WEIGHTS.get(c.get("check_name") or "", 0) or 0)
        if w <= 0:
            continue
        total_w += w
        if (c.get("status") or "").lower() == "pass":
            earned += w
    if total_w <= 0:
        return 0
    return int(round(100 * earned / total_w))
