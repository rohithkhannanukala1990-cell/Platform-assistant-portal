"""Engineering reports — aggregated views over catalog, scorecards, standards, and actions."""

from __future__ import annotations

from collections import Counter
from typing import Any

from fastapi import APIRouter, Depends
from sqlmodel import Session, select

from ..auth import User, get_current_user, get_session
from .catalog import CatalogEntity
from .entity_actions import EntityActionRun
from .scorecards import ScorecardCheck
from .standards import EntityStandardEvaluation

router = APIRouter(prefix="/api/reports", tags=["reports"])


def _active_entities(session: Session) -> list[CatalogEntity]:
    return list(
        session.exec(select(CatalogEntity).where(CatalogEntity.is_active == 1)).all()
    )


def _std_bucket(status: str | None) -> str:
    s = (status or "").lower()
    if s == "pass":
        return "passed"
    if s in ("fail", "failed"):
        return "failed"
    if s in ("warn", "warning"):
        return "warnings"
    return "warnings"


@router.get("/catalog-overview")
def catalog_overview(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    entities = _active_entities(session)

    by_kind = Counter(e.kind or "Unknown" for e in entities)
    by_lifecycle = Counter(e.lifecycle or "Unknown" for e in entities)
    missing_owner = sum(1 for e in entities if not (e.owner_team or "").strip())
    unknown_health = sum(
        1
        for e in entities
        if not e.health_status or e.health_status == "unknown"
    )

    return {
        "total_entities": len(entities),
        "by_kind": dict(by_kind),
        "by_lifecycle": dict(by_lifecycle),
        "missing_owner": missing_owner,
        "unknown_health": unknown_health,
    }


@router.get("/scorecards-overview")
def scorecards_overview(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    checks = session.exec(select(ScorecardCheck)).all()
    entities_map = {e.id: e for e in _active_entities(session)}

    entity_scores: dict[str, list[float]] = {}
    entity_pass_fail: dict[str, dict[str, int]] = {}

    for check in checks:
        eid = check.entity_id
        if eid not in entities_map:
            continue
        if eid not in entity_scores:
            entity_scores[eid] = []
            entity_pass_fail[eid] = {"pass": 0, "fail": 0}

        if check.score is not None:
            entity_scores[eid].append(float(check.score))

        if check.status == "pass":
            entity_pass_fail[eid]["pass"] += 1
        elif check.status in ("fail", "failed", "error"):
            entity_pass_fail[eid]["fail"] += 1

    entity_avg: dict[str, float] = {
        eid: (sum(scores) / len(scores) if scores else 0.0)
        for eid, scores in entity_scores.items()
    }

    team_data: dict[str, dict[str, Any]] = {}
    for eid, avg in entity_avg.items():
        entity = entities_map.get(eid)
        team = (entity.owner_team if entity else None) or "Unassigned"
        if team not in team_data:
            team_data[team] = {"scores": [], "pass": 0, "fail": 0}
        team_data[team]["scores"].append(avg)
        pf = entity_pass_fail.get(eid, {"pass": 0, "fail": 0})
        team_data[team]["pass"] += pf["pass"]
        team_data[team]["fail"] += pf["fail"]

    by_team = [
        {
            "team": team,
            "avg_score": round(sum(d["scores"]) / len(d["scores"]), 1) if d["scores"] else 0,
            "pass": d["pass"],
            "fail": d["fail"],
        }
        for team, d in team_data.items()
    ]
    by_team.sort(key=lambda x: x["avg_score"], reverse=True)

    lowest = sorted(
        [
            {
                "id": eid,
                "name": entities_map[eid].name if eid in entities_map else f"Entity {eid}",
                "score": round(avg, 1),
            }
            for eid, avg in entity_avg.items()
        ],
        key=lambda x: x["score"],
    )[:5]

    overall_avg = (
        round(sum(entity_avg.values()) / len(entity_avg), 1) if entity_avg else 0
    )

    return {
        "avg_score": overall_avg,
        "by_team": by_team,
        "lowest_scoring_services": lowest,
    }


@router.get("/standards-overview")
def standards_overview(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    evals = session.exec(select(EntityStandardEvaluation)).all()
    entities = {e.id: e for e in _active_entities(session)}

    total = len(evals)
    passed = sum(1 for e in evals if _std_bucket(e.status) == "passed")
    failed = sum(1 for e in evals if _std_bucket(e.status) == "failed")
    warnings = sum(1 for e in evals if _std_bucket(e.status) == "warnings")

    team_evals: dict[str, dict[str, int]] = {}
    for ev in evals:
        entity = entities.get(ev.entity_id)
        team = (entity.owner_team if entity else None) or "Unassigned"
        if team not in team_evals:
            team_evals[team] = {"passed": 0, "failed": 0, "warnings": 0}
        bucket = _std_bucket(ev.status)
        team_evals[team][bucket] = team_evals[team].get(bucket, 0) + 1

    by_team = []
    for team, counts in team_evals.items():
        total_team = counts["passed"] + counts["failed"] + counts["warnings"]
        by_team.append(
            {
                "team": team,
                "passed": counts["passed"],
                "failed": counts["failed"],
                "warnings": counts["warnings"],
                "pass_rate": round(counts["passed"] / total_team, 2) if total_team > 0 else 0,
            }
        )

    return {
        "total_evaluated": total,
        "passed": passed,
        "failed": failed,
        "warnings": warnings,
        "pass_rate_pct": round((passed / total * 100), 1) if total > 0 else 0,
        "by_team": by_team,
    }


@router.get("/team-overview")
def team_overview(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    entities = _active_entities(session)
    sc_checks = session.exec(select(ScorecardCheck)).all()
    std_evals = session.exec(select(EntityStandardEvaluation)).all()
    all_runs = session.exec(select(EntityActionRun)).all()
    action_runs = [r for r in all_runs if r.status in ("pending", "running")]

    team_entities: dict[str, list[CatalogEntity]] = {}
    for e in entities:
        team = (e.owner_team or "").strip() or "Unassigned"
        team_entities.setdefault(team, []).append(e)

    entity_scores: dict[str, list[float]] = {}
    for check in sc_checks:
        if check.score is not None:
            entity_scores.setdefault(check.entity_id, []).append(float(check.score))

    entity_std_pass: dict[str, dict[str, int]] = {}
    for ev in std_evals:
        entity_std_pass.setdefault(ev.entity_id, {"passed": 0, "total": 0})
        entity_std_pass[ev.entity_id]["total"] += 1
        if _std_bucket(ev.status) == "passed":
            entity_std_pass[ev.entity_id]["passed"] += 1

    entity_open_actions: dict[str, int] = {}
    for run in action_runs:
        if run.entity_id:
            entity_open_actions[run.entity_id] = entity_open_actions.get(run.entity_id, 0) + 1

    teams = []
    for team, team_ents in team_entities.items():
        eids = [e.id for e in team_ents]

        all_scores = [s for eid in eids for s in entity_scores.get(eid, [])]
        avg_score = round(sum(all_scores) / len(all_scores), 1) if all_scores else 0

        ready_count = sum(
            1
            for eid in eids
            if (
                entity_std_pass.get(eid, {}).get("total", 0) > 0
                and entity_std_pass[eid]["passed"] / entity_std_pass[eid]["total"] >= 0.7
            )
        )
        readiness_pct = round(ready_count / len(eids) * 100) if eids else 0

        open_actions = sum(entity_open_actions.get(eid, 0) for eid in eids)

        teams.append(
            {
                "name": team,
                "services_owned": len(team_ents),
                "avg_score": avg_score,
                "readiness_pct": readiness_pct,
                "open_actions": open_actions,
            }
        )

    teams.sort(key=lambda t: t["services_owned"], reverse=True)
    return {"teams": teams}
