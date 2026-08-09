"""Workflow engine: DAG advance, HITL resume, templating, grounding.

Mirrors catalog_actions execute-then-fulfill-after-approval split:
  start → advance until HITL → CAS approve → resume_after_approval → advance.
"""

from __future__ import annotations

import ast
import json
import logging
import os
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from fastapi import HTTPException
from sqlmodel import Session, col, select
from sqlalchemy import update

from ..auth import write_audit
from ..context import PlatformContext
from ..db.core import engine
from ..db.models.workflows import (
    VALID_GROUNDING,
    VALID_STEP_TYPES,
    WorkflowDefinition,
    WorkflowRun,
    is_connector_write_method,
)
from .approval_claim import claim_workflow_run

logger = logging.getLogger(__name__)

_TEMPLATE_RE = re.compile(r"\{\{\s*([a-zA-Z_][a-zA-Z0-9_.]*)\s*\}\}")
_GROUNDING_RANK = {"none": 0, "demo": 1, "partial": 2, "live": 3}


class WorkflowValidationError(ValueError):
    """Raised when a workflow DAG fails structural validation."""

    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("; ".join(errors))


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_json(raw: str | None, default: Any) -> Any:
    try:
        data = json.loads(raw or "")
        return data if data is not None else default
    except (json.JSONDecodeError, TypeError, ValueError):
        return default


def _dumps(value: Any) -> str:
    return json.dumps(value, default=str)


def workflow_timeout_minutes() -> int:
    raw = (os.environ.get("WORKFLOW_RUN_TIMEOUT_MINUTES") or "30").strip()
    try:
        return max(1, int(raw))
    except (TypeError, ValueError):
        return 30


def worst_grounding(*values: str | None) -> str:
    """Run-level grounding is the worst across steps: none > demo > partial > live."""
    worst = "live"
    worst_rank = _GROUNDING_RANK["live"]
    saw = False
    for v in values:
        g = (v or "none").strip().lower()
        if g not in VALID_GROUNDING:
            g = "none"
        rank = _GROUNDING_RANK.get(g, 0)
        if not saw or rank < worst_rank:
            worst = g
            worst_rank = rank
            saw = True
    return worst if saw else "none"


def _lookup_path(root: Any, path: str) -> Any:
    cur = root
    for part in path.split("."):
        if cur is None:
            return None
        if isinstance(cur, dict):
            cur = cur.get(part)
        else:
            return None
    return cur


def resolve_templates(value: Any, context: dict[str, Any]) -> Any:
    """Resolve {{trigger.x}} / {{steps.s1.output.y}} without Jinja2 or eval."""
    if isinstance(value, dict):
        return {k: resolve_templates(v, context) for k, v in value.items()}
    if isinstance(value, list):
        return [resolve_templates(v, context) for v in value]
    if not isinstance(value, str):
        return value

    full = _TEMPLATE_RE.fullmatch(value.strip())
    if full:
        return _lookup_path(context, full.group(1))

    def _repl(match: re.Match[str]) -> str:
        found = _lookup_path(context, match.group(1))
        if found is None:
            return ""
        if isinstance(found, (dict, list)):
            return json.dumps(found, default=str)
        return str(found)

    return _TEMPLATE_RE.sub(_repl, value)


def _safe_literal(node: ast.AST) -> Any:
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.List):
        return [_safe_literal(elt) for elt in node.elts]
    if isinstance(node, ast.Tuple):
        return tuple(_safe_literal(elt) for elt in node.elts)
    if isinstance(node, ast.Dict):
        return {
            _safe_literal(k): _safe_literal(v)
            for k, v in zip(node.keys, node.values)
            if k is not None
        }
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub) and isinstance(node.operand, ast.Constant):
        if isinstance(node.operand.value, (int, float)):
            return -node.operand.value
    raise ValueError("unsupported literal")


def _eval_condition_node(node: ast.AST, context: dict[str, Any]) -> Any:
    if isinstance(node, ast.Expression):
        return _eval_condition_node(node.body, context)
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Name):
        return _lookup_path(context, node.id)
    if isinstance(node, ast.Attribute):
        parts: list[str] = []
        cur: ast.AST = node
        while isinstance(cur, ast.Attribute):
            parts.append(cur.attr)
            cur = cur.value
        if isinstance(cur, ast.Name):
            parts.append(cur.id)
            path = ".".join(reversed(parts))
            return _lookup_path(context, path)
        raise ValueError("unsupported attribute path")
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
        return not bool(_eval_condition_node(node.operand, context))
    if isinstance(node, ast.BoolOp):
        if isinstance(node.op, ast.And):
            return all(bool(_eval_condition_node(v, context)) for v in node.values)
        if isinstance(node.op, ast.Or):
            return any(bool(_eval_condition_node(v, context)) for v in node.values)
        raise ValueError("unsupported boolean op")
    if isinstance(node, ast.Compare):
        left = _eval_condition_node(node.left, context)
        for op, comparator in zip(node.ops, node.comparators):
            right = _eval_condition_node(comparator, context)
            if isinstance(op, ast.Eq):
                ok = left == right
            elif isinstance(op, ast.NotEq):
                ok = left != right
            elif isinstance(op, ast.In):
                ok = left in right if right is not None else False
            elif isinstance(op, ast.NotIn):
                ok = left not in right if right is not None else True
            elif isinstance(op, ast.Gt):
                ok = left > right
            elif isinstance(op, ast.GtE):
                ok = left >= right
            elif isinstance(op, ast.Lt):
                ok = left < right
            elif isinstance(op, ast.LtE):
                ok = left <= right
            else:
                raise ValueError("unsupported comparison")
            if not ok:
                return False
            left = right
        return True
    if isinstance(node, (ast.List, ast.Tuple, ast.Dict)):
        return _safe_literal(node)
    raise ValueError(f"unsupported expression node: {type(node).__name__}")


def evaluate_condition(expression: str, context: dict[str, Any]) -> bool:
    """Safe boolean expression evaluator — no eval()/exec()."""
    expr = (expression or "").strip()
    if not expr:
        return False
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError as exc:
        raise ValueError(f"invalid condition expression: {exc}") from exc
    # Reject anything that isn't a pure expression of allowed nodes.
    for n in ast.walk(tree):
        if isinstance(
            n,
            (
                ast.Call,
                ast.Lambda,
                ast.ListComp,
                ast.SetComp,
                ast.DictComp,
                ast.GeneratorExp,
                ast.Await,
                ast.Yield,
                ast.YieldFrom,
                ast.Import,
                ast.ImportFrom,
                ast.Attribute,
                ast.Subscript,
                ast.Name,
                ast.Constant,
                ast.Expression,
                ast.BoolOp,
                ast.UnaryOp,
                ast.Compare,
                ast.And,
                ast.Or,
                ast.Not,
                ast.Eq,
                ast.NotEq,
                ast.In,
                ast.NotIn,
                ast.Gt,
                ast.GtE,
                ast.Lt,
                ast.LtE,
                ast.Load,
                ast.List,
                ast.Tuple,
                ast.Dict,
                ast.USub,
                ast.UAdd,
            ),
        ):
            continue
        raise ValueError(f"disallowed expression node: {type(n).__name__}")
    return bool(_eval_condition_node(tree, context))


def parse_steps(steps_json: str | list | None) -> list[dict[str, Any]]:
    if isinstance(steps_json, list):
        return [s for s in steps_json if isinstance(s, dict)]
    data = _parse_json(steps_json if isinstance(steps_json, str) else None, [])
    if not isinstance(data, list):
        return []
    return [s for s in data if isinstance(s, dict)]


def _step_map(steps: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for s in steps:
        sid = str(s.get("id") or "").strip()
        if sid:
            out[sid] = s
    return out


def _ancestors(step_id: str, steps_by_id: dict[str, dict[str, Any]]) -> set[str]:
    seen: set[str] = set()
    stack = list(steps_by_id.get(step_id, {}).get("depends_on") or [])
    while stack:
        cur = str(stack.pop())
        if cur in seen:
            continue
        seen.add(cur)
        deps = steps_by_id.get(cur, {}).get("depends_on") or []
        stack.extend(str(d) for d in deps)
    return seen


def _has_cycle(steps: list[dict[str, Any]]) -> bool:
    by_id = _step_map(steps)
    WHITE, GRAY, BLACK = 0, 1, 2
    color = {sid: WHITE for sid in by_id}

    def dfs(sid: str) -> bool:
        color[sid] = GRAY
        for dep in by_id[sid].get("depends_on") or []:
            d = str(dep)
            if d not in by_id:
                continue
            if color[d] == GRAY:
                return True
            if color[d] == WHITE and dfs(d):
                return True
        # Also walk dependents: edge is depends_on → dependency, so cycle via deps is enough.
        color[sid] = BLACK
        return False

    # Detect cycles by treating depends_on as edges from step → dependency,
    # and also check reverse: if A depends on B and B eventually depends on A.
    # Standard approach: edge step → dep means "step waits on dep"; cycle if dfs finds gray.
    # But we need edges from dep → step for topological readiness. For cycle, either works
    # if we also reverse: check for cycle in "depends_on" graph where edge is step→dep.
    # Actually step→dep cannot cycle unless mutual. Better: edge dep→step (produces).
    color = {sid: WHITE for sid in by_id}

    def dfs_prod(sid: str) -> bool:
        color[sid] = GRAY
        for other, meta in by_id.items():
            deps = [str(d) for d in (meta.get("depends_on") or [])]
            if sid not in deps:
                continue
            if color[other] == GRAY:
                return True
            if color[other] == WHITE and dfs_prod(other):
                return True
        color[sid] = BLACK
        return False

    return any(color[s] == WHITE and dfs_prod(s) for s in by_id)


def _template_step_refs(value: Any) -> set[str]:
    refs: set[str] = set()
    if isinstance(value, dict):
        for v in value.values():
            refs |= _template_step_refs(v)
    elif isinstance(value, list):
        for v in value:
            refs |= _template_step_refs(v)
    elif isinstance(value, str):
        for m in _TEMPLATE_RE.finditer(value):
            path = m.group(1)
            parts = path.split(".")
            if len(parts) >= 2 and parts[0] == "steps":
                refs.add(parts[1])
    return refs


def validate_workflow_steps(steps: list[dict[str, Any]]) -> list[str]:
    """Return list of validation errors (empty = ok)."""
    errors: list[str] = []
    if not steps:
        errors.append("steps must be a non-empty array")
        return errors

    by_id = _step_map(steps)
    if len(by_id) != len(steps):
        errors.append("each step must have a unique non-empty id")

    for s in steps:
        sid = str(s.get("id") or "").strip()
        stype = str(s.get("type") or "").strip()
        if stype not in VALID_STEP_TYPES:
            errors.append(f"step {sid or '?'}: type must be one of {sorted(VALID_STEP_TYPES)}")
        deps = s.get("depends_on") or []
        if not isinstance(deps, list):
            errors.append(f"step {sid}: depends_on must be a list")
            continue
        for d in deps:
            if str(d) not in by_id:
                errors.append(f"step {sid}: depends_on references unknown step '{d}'")

        if stype == "agent" and not str(s.get("agent") or "").strip():
            errors.append(f"step {sid}: agent steps require 'agent'")
        if stype == "connector":
            if not str(s.get("connector") or "").strip():
                errors.append(f"step {sid}: connector steps require 'connector'")
            if not str(s.get("method") or "").strip():
                errors.append(f"step {sid}: connector steps require 'method'")
        if stype == "hitl" and not str(s.get("prompt") or "").strip():
            errors.append(f"step {sid}: hitl steps require 'prompt'")
        if stype == "condition" and not str(s.get("expression") or s.get("when") or "").strip():
            errors.append(f"step {sid}: condition steps require 'expression'")

    if by_id and _has_cycle(steps):
        errors.append("step graph contains a cycle")

    for s in steps:
        sid = str(s.get("id") or "").strip()
        ancestors = _ancestors(sid, by_id)
        refs = _template_step_refs(s.get("input")) | _template_step_refs(s.get("args"))
        refs |= _template_step_refs(s.get("expression") or s.get("when") or "")
        refs |= _template_step_refs(s.get("prompt") or "")
        for ref in refs:
            if ref == sid:
                errors.append(f"step {sid}: template references itself")
            elif ref not in by_id:
                errors.append(f"step {sid}: template references unknown step '{ref}'")
            elif ref not in ancestors:
                errors.append(
                    f"step {sid}: template {{{{steps.{ref}...}}}} references a step that does not run before it"
                )

        if str(s.get("type") or "") == "connector" and is_connector_write_method(str(s.get("method") or "")):
            # Require a hitl (or requires_approval) ancestor in the dependency chain.
            has_gate = False
            for anc in ancestors:
                meta = by_id.get(anc) or {}
                if str(meta.get("type") or "") == "hitl":
                    has_gate = True
                    break
                if bool(meta.get("requires_approval")):
                    has_gate = True
                    break
            if not has_gate:
                errors.append(
                    f"step {sid}: write connector method '{s.get('method')}' requires a preceding hitl gate"
                )

    return errors


def serialize_definition(row: WorkflowDefinition) -> dict[str, Any]:
    return {
        "id": row.id,
        "tenant_id": row.tenant_id,
        "workspace_id": row.workspace_id,
        "name": row.name,
        "description": row.description or "",
        "steps": parse_steps(row.steps_json),
        "trigger_type": row.trigger_type,
        "trigger_config": _parse_json(row.trigger_config_json, {}),
        "enabled": bool(row.enabled),
        "risk": row.risk,
        "max_runs_per_hour": row.max_runs_per_hour,
        "max_concurrent_runs": row.max_concurrent_runs,
        "created_by": row.created_by,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def serialize_run(row: WorkflowRun, *, include_definition: bool = False) -> dict[str, Any]:
    out: dict[str, Any] = {
        "id": row.id,
        "tenant_id": row.tenant_id,
        "workflow_id": row.workflow_id,
        "status": row.status,
        "current_step_id": row.current_step_id,
        "context": _parse_json(row.context_json, {}),
        "steps_state": _parse_json(row.steps_state_json, {}),
        "triggered_by": row.triggered_by,
        "grounding": row.grounding,
        "dry_run": bool(row.dry_run),
        "started_at": row.started_at.isoformat() if row.started_at else None,
        "completed_at": row.completed_at.isoformat() if row.completed_at else None,
        "error": row.error,
    }
    if include_definition:
        with Session(engine) as session:
            wf = session.get(WorkflowDefinition, row.workflow_id)
            if wf:
                out["workflow"] = serialize_definition(wf)
    return out


def _audit(
    *,
    actor: str,
    event_type: str,
    resource: str,
    detail: str,
    tenant_id: str,
    step_id: str | None = None,
    status: str | None = None,
) -> None:
    bits = [detail]
    if step_id:
        bits.append(f"step={step_id}")
    if status:
        bits.append(f"status={status}")
    bits.append(f"tenant_id={tenant_id}")
    write_audit(
        actor=actor or "system",
        actor_role="system",
        event_type=event_type,
        resource=resource,
        detail="; ".join(bits)[:800],
    )


def _load_run(session: Session, run_id: str, tenant_id: str) -> WorkflowRun:
    row = session.get(WorkflowRun, run_id)
    if not row or row.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Not found")
    return row


def _load_definition(session: Session, workflow_id: str, tenant_id: str) -> WorkflowDefinition:
    row = session.get(WorkflowDefinition, workflow_id)
    if not row or row.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Not found")
    return row


def _persist_run_fields(run_id: str, **fields: Any) -> WorkflowRun:
    with Session(engine) as session:
        row = session.get(WorkflowRun, run_id)
        if not row:
            raise HTTPException(status_code=404, detail="Not found")
        for k, v in fields.items():
            setattr(row, k, v)
        session.add(row)
        session.commit()
        session.refresh(row)
        session.expunge(row)
        return row


def _mark_timed_out(run: WorkflowRun) -> WorkflowRun:
    return _persist_run_fields(
        run.id,
        status="failed",
        error=f"Workflow run timed out after {workflow_timeout_minutes()} minutes",
        completed_at=_now(),
        current_step_id=None,
    )


def _check_timeout(run: WorkflowRun) -> WorkflowRun | None:
    if run.status in {"completed", "failed", "rejected", "cancelled"}:
        return None
    started = run.started_at
    if started is None:
        return None
    if started.tzinfo is None:
        started = started.replace(tzinfo=timezone.utc)
    if _now() - started > timedelta(minutes=workflow_timeout_minutes()):
        failed = _mark_timed_out(run)
        _audit(
            actor="system",
            event_type="workflow_run_timeout",
            resource=f"workflow_run:{run.id}",
            detail=failed.error or "timeout",
            tenant_id=run.tenant_id,
            status="failed",
        )
        return failed
    return None


def _deps_completed(step: dict[str, Any], steps_state: dict[str, Any]) -> bool:
    for d in step.get("depends_on") or []:
        st = (steps_state.get(str(d)) or {}).get("status")
        if st not in {"completed", "skipped", "approved"}:
            return False
    return True


def _is_approval_gate(step: dict[str, Any]) -> bool:
    if str(step.get("type") or "") == "hitl":
        return True
    return bool(step.get("requires_approval"))


async def _execute_agent_step(
    step: dict[str, Any],
    *,
    context: dict[str, Any],
    platform_ctx: PlatformContext,
    dry_run: bool,
) -> dict[str, Any]:
    from ..pipeline.orchestrator import run_agent_for_workflow

    raw_input = step.get("input") if isinstance(step.get("input"), dict) else {}
    resolved = resolve_templates(raw_input, context)
    if not isinstance(resolved, dict):
        resolved = {"task": str(resolved)}
    if dry_run:
        resolved = {**resolved, "dry_run": True}
    agent_name = str(step.get("agent") or "").strip()
    result = await run_agent_for_workflow(agent_name, resolved, platform_ctx)
    details = dict(result.details or {})
    output = {
        "summary": result.summary,
        "status": result.status,
        "details": details,
        "evidence": list(result.evidence or []),
        "recommended_actions": list(result.recommended_actions or []),
        **{k: v for k, v in details.items() if k not in {"commands"}},
    }
    # Prefer explicit output.summary for templates
    if "summary" not in output:
        output["summary"] = result.summary
    return {
        "status": "completed" if result.status in {"success", "dry_run", "skipped"} else result.status,
        "output": output,
        "grounding": (result.grounding or "none"),
        "agent_status": result.status,
    }


async def _execute_connector_step(
    step: dict[str, Any],
    *,
    context: dict[str, Any],
    dry_run: bool,
) -> dict[str, Any]:
    connector_id = str(step.get("connector") or "").strip()
    method = str(step.get("method") or "").strip()
    raw_args = step.get("args") if isinstance(step.get("args"), dict) else {}
    args = resolve_templates(raw_args, context)
    if not isinstance(args, dict):
        args = {}

    if dry_run:
        logger.info(
            "workflow dry_run connector call skipped connector=%s method=%s args_keys=%s",
            connector_id,
            method,
            sorted(args.keys()),
        )
        return {
            "status": "completed",
            "output": {
                "dry_run": True,
                "would_call": {"connector": connector_id, "method": method, "args": args},
            },
            "grounding": "none",
        }

    from ..connectors.registry import get_connector

    account = {"tool_id": connector_id, **(step.get("account") if isinstance(step.get("account"), dict) else {})}
    connector = get_connector(connector_id, account)
    result = await connector.execute_action(method, args)
    ok = bool(isinstance(result, dict) and result.get("ok", True))
    return {
        "status": "completed" if ok else "failed",
        "output": result if isinstance(result, dict) else {"result": result},
        "grounding": "live" if ok else "none",
    }


def _execute_condition_step(step: dict[str, Any], *, context: dict[str, Any]) -> dict[str, Any]:
    expr = str(step.get("expression") or step.get("when") or "")
    expr = resolve_templates(expr, context) if "{{" in expr else expr
    matched = evaluate_condition(str(expr), context)
    return {
        "status": "completed" if matched else "skipped",
        "output": {"matched": matched, "expression": expr},
        "grounding": "live",
    }


async def start_workflow(
    workflow_id: str,
    tenant_id: str,
    triggered_by: str,
    initial_context: dict[str, Any] | None = None,
    dry_run: bool = False,
) -> WorkflowRun:
    with Session(engine) as session:
        wf = _load_definition(session, workflow_id, tenant_id)
        if not wf.enabled and not dry_run:
            raise HTTPException(status_code=400, detail="Workflow is disabled")

        errors = validate_workflow_steps(parse_steps(wf.steps_json))
        if errors:
            raise HTTPException(status_code=422, detail=errors)

        hour_ago = _now() - timedelta(hours=1)
        recent = session.exec(
            select(WorkflowRun).where(
                WorkflowRun.workflow_id == workflow_id,
                WorkflowRun.tenant_id == tenant_id,
                WorkflowRun.started_at >= hour_ago,
            )
        ).all()
        if len(recent) >= int(wf.max_runs_per_hour or 12):
            raise HTTPException(status_code=429, detail="max_runs_per_hour exceeded")

        active = session.exec(
            select(WorkflowRun).where(
                WorkflowRun.workflow_id == workflow_id,
                WorkflowRun.tenant_id == tenant_id,
                col(WorkflowRun.status).in_(["pending", "running", "pending_approval"]),
            )
        ).all()
        if len(active) >= int(wf.max_concurrent_runs or 1):
            raise HTTPException(status_code=429, detail="max_concurrent_runs exceeded")

        trigger = dict(initial_context or {})
        ctx = {"trigger": trigger, "steps": {}}
        run = WorkflowRun(
            id=str(uuid.uuid4()),
            tenant_id=tenant_id,
            workflow_id=workflow_id,
            status="pending",
            context_json=_dumps(ctx),
            steps_state_json="{}",
            triggered_by=triggered_by or "system",
            grounding="live",
            dry_run=bool(dry_run),
            started_at=_now(),
        )
        session.add(run)
        session.commit()
        session.refresh(run)
        run_id = run.id
        session.expunge(run)

    _audit(
        actor=triggered_by,
        event_type="workflow_run_started",
        resource=f"workflow_run:{run_id}",
        detail=f"workflow_id={workflow_id} dry_run={dry_run}",
        tenant_id=tenant_id,
        status="pending",
    )
    return await advance_workflow(run_id, tenant_id)


async def advance_workflow(run_id: str, tenant_id: str) -> WorkflowRun:
    with Session(engine) as session:
        run = _load_run(session, run_id, tenant_id)
        session.expunge(run)
        wf = _load_definition(session, run.workflow_id, tenant_id)
        session.expunge(wf)

    timed = _check_timeout(run)
    if timed is not None:
        return timed

    if run.status in {"completed", "failed", "rejected", "cancelled"}:
        return run

    steps = parse_steps(wf.steps_json)
    steps_state: dict[str, Any] = _parse_json(run.steps_state_json, {})
    context: dict[str, Any] = _parse_json(run.context_json, {"trigger": {}, "steps": {}})
    if "steps" not in context or not isinstance(context["steps"], dict):
        context["steps"] = {}
    if "trigger" not in context or not isinstance(context["trigger"], dict):
        context["trigger"] = {}

    platform_ctx = PlatformContext(
        user_id=run.triggered_by or "workflow",
        user_role="Admin",
        tenant_id=tenant_id,
        workspace_id=wf.workspace_id or "",
        environment="development",
    )

    # Mark run running
    run = _persist_run_fields(run_id, status="running")

    progressed = True
    while progressed:
        progressed = False
        timed = _check_timeout(run)
        if timed is not None:
            return timed

        for step in steps:
            sid = str(step.get("id") or "")
            state = steps_state.get(sid) or {}
            if state.get("status") in {
                "completed",
                "failed",
                "skipped",
                "approved",
                "pending_approval",
                "rejected",
            }:
                continue
            if not _deps_completed(step, steps_state):
                continue

            # Stop at approval gates before executing side effects.
            # Pure hitl steps complete on approve; agent/connector with requires_approval
            # re-enter this loop after approve with _approval_granted set.
            if _is_approval_gate(step) and not state.get("_approval_granted"):
                prompt = step.get("prompt") or (
                    f"Approve {step.get('type')} step '{sid}'?"
                    if str(step.get("type") or "") != "hitl"
                    else "Approve this step?"
                )
                steps_state[sid] = {
                    "status": "pending_approval",
                    "type": step.get("type"),
                    "prompt": resolve_templates(prompt, context),
                    "requires_approval": True,
                    "awaiting_execution": str(step.get("type") or "") != "hitl",
                    "started_at": _now().isoformat(),
                }
                run = _persist_run_fields(
                    run_id,
                    status="pending_approval",
                    current_step_id=sid,
                    steps_state_json=_dumps(steps_state),
                    context_json=_dumps(context),
                    grounding=worst_grounding(
                        run.grounding,
                        *[
                            (steps_state[k].get("grounding") if isinstance(steps_state.get(k), dict) else None)
                            for k in steps_state
                        ],
                    ),
                )
                _audit(
                    actor=run.triggered_by,
                    event_type="workflow_step_pending_approval",
                    resource=f"workflow_run:{run_id}",
                    detail=f"awaiting approval",
                    tenant_id=tenant_id,
                    step_id=sid,
                    status="pending_approval",
                )
                return run

            # Execute step
            steps_state[sid] = {
                "status": "running",
                "type": step.get("type"),
                "started_at": _now().isoformat(),
            }
            _persist_run_fields(
                run_id,
                current_step_id=sid,
                steps_state_json=_dumps(steps_state),
                context_json=_dumps(context),
                status="running",
            )

            stype = str(step.get("type") or "")
            try:
                if stype == "hitl":
                    # Should have been handled as a gate; treat as no-op approved.
                    result = {
                        "status": "completed",
                        "output": {"approved": True},
                        "grounding": "live",
                    }
                elif stype == "agent":
                    result = await _execute_agent_step(
                        step, context=context, platform_ctx=platform_ctx, dry_run=bool(run.dry_run)
                    )
                elif stype == "connector":
                    result = await _execute_connector_step(
                        step, context=context, dry_run=bool(run.dry_run)
                    )
                elif stype == "condition":
                    result = _execute_condition_step(step, context=context)
                else:
                    result = {
                        "status": "failed",
                        "output": {"error": f"unknown step type {stype}"},
                        "grounding": "none",
                    }
            except Exception as exc:
                logger.exception("workflow step failed run=%s step=%s", run_id, sid)
                result = {
                    "status": "failed",
                    "output": {"error": str(exc)[:500]},
                    "grounding": "none",
                }

            step_status = str(result.get("status") or "failed")
            if step_status in {"success", "dry_run", "pending_approval"}:
                step_status = "completed"
            grounding = str(result.get("grounding") or "none")
            output = result.get("output") if isinstance(result.get("output"), dict) else {"value": result.get("output")}
            steps_state[sid] = {
                "status": step_status if step_status in {"completed", "skipped", "failed"} else "failed",
                "type": stype,
                "output": output,
                "grounding": grounding,
                "started_at": steps_state[sid].get("started_at"),
                "completed_at": _now().isoformat(),
            }
            context["steps"][sid] = {"output": output, "grounding": grounding, "status": steps_state[sid]["status"]}
            run_grounding = worst_grounding(
                run.grounding,
                grounding,
                *[
                    (steps_state[k].get("grounding") if isinstance(steps_state.get(k), dict) else None)
                    for k in steps_state
                ],
            )

            _audit(
                actor=run.triggered_by,
                event_type="workflow_step_completed",
                resource=f"workflow_run:{run_id}",
                detail=f"type={stype}",
                tenant_id=tenant_id,
                step_id=sid,
                status=steps_state[sid]["status"],
            )

            if steps_state[sid]["status"] == "failed":
                run = _persist_run_fields(
                    run_id,
                    status="failed",
                    error=str((output or {}).get("error") or f"Step {sid} failed"),
                    completed_at=_now(),
                    current_step_id=sid,
                    steps_state_json=_dumps(steps_state),
                    context_json=_dumps(context),
                    grounding=run_grounding,
                )
                return run

            run = _persist_run_fields(
                run_id,
                status="running",
                current_step_id=sid,
                steps_state_json=_dumps(steps_state),
                context_json=_dumps(context),
                grounding=run_grounding,
            )
            progressed = True
            break  # restart scan after each completion

    # No more ready steps — completed if all terminal, else still running (blocked?)
    terminal = {"completed", "skipped", "approved"}
    all_done = all(
        (steps_state.get(str(s.get("id"))) or {}).get("status") in terminal for s in steps
    )
    if all_done:
        run = _persist_run_fields(
            run_id,
            status="completed",
            completed_at=_now(),
            current_step_id=None,
            steps_state_json=_dumps(steps_state),
            context_json=_dumps(context),
            grounding=worst_grounding(
                run.grounding,
                *[
                    (steps_state[k].get("grounding") if isinstance(steps_state.get(k), dict) else None)
                    for k in steps_state
                ],
            ),
        )
        _audit(
            actor=run.triggered_by,
            event_type="workflow_run_completed",
            resource=f"workflow_run:{run_id}",
            detail="all steps finished",
            tenant_id=tenant_id,
            status="completed",
        )
        return run

    # Should not hang without pending_approval — mark failed if stuck
    run = _persist_run_fields(
        run_id,
        status="failed",
        error="Workflow stalled with no runnable steps",
        completed_at=_now(),
        steps_state_json=_dumps(steps_state),
        context_json=_dumps(context),
    )
    return run


async def resume_after_approval(
    run_id: str,
    step_id: str,
    approved_by: str,
    tenant_id: str,
) -> WorkflowRun:
    """CAS claim pending_approval → running, mark step approved, then advance."""
    with Session(engine) as session:
        run = _load_run(session, run_id, tenant_id)
        if run.status != "pending_approval":
            raise HTTPException(status_code=409, detail="Run is not awaiting approval")
        current = run.current_step_id or step_id
        if step_id and current and step_id != current:
            raise HTTPException(status_code=409, detail="Step is not the current approval gate")
        step_id = current or step_id
        if not claim_workflow_run(session, run_id, from_status="pending_approval", to_status="running"):
            raise HTTPException(status_code=409, detail="Approval already claimed")

        # Re-load after claim
        run = session.get(WorkflowRun, run_id)
        if not run:
            raise HTTPException(status_code=404, detail="Not found")
        steps_state = _parse_json(run.steps_state_json, {})
        context = _parse_json(run.context_json, {"trigger": {}, "steps": {}})
        gate = dict(steps_state.get(step_id) or {})
        awaiting_execution = bool(gate.get("awaiting_execution"))
        if awaiting_execution:
            # Clear gate so advance executes the underlying agent/connector step.
            steps_state[step_id] = {
                "_approval_granted": True,
                "approved_by": approved_by,
                "approved_at": _now().isoformat(),
                "type": gate.get("type"),
            }
        else:
            gate.update(
                {
                    "status": "approved",
                    "approved_by": approved_by,
                    "approved_at": _now().isoformat(),
                    "output": {"approved": True, "approved_by": approved_by},
                    "grounding": gate.get("grounding") or "live",
                    "completed_at": _now().isoformat(),
                }
            )
            steps_state[step_id] = gate
            if "steps" not in context or not isinstance(context["steps"], dict):
                context["steps"] = {}
            context["steps"][step_id] = {
                "output": gate["output"],
                "grounding": gate.get("grounding") or "live",
                "status": "approved",
            }
        run.steps_state_json = _dumps(steps_state)
        run.context_json = _dumps(context)
        run.current_step_id = step_id
        session.add(run)
        session.commit()

    _audit(
        actor=approved_by,
        event_type="workflow_step_approved",
        resource=f"workflow_run:{run_id}",
        detail="approved",
        tenant_id=tenant_id,
        step_id=step_id,
        status="approved",
    )
    return await advance_workflow(run_id, tenant_id)


async def reject_workflow(
    run_id: str,
    step_id: str,
    rejected_by: str,
    reason: str,
    tenant_id: str,
) -> WorkflowRun:
    with Session(engine) as session:
        run = _load_run(session, run_id, tenant_id)
        if run.status != "pending_approval":
            raise HTTPException(status_code=409, detail="Run is not awaiting approval")
        current = run.current_step_id or step_id
        if step_id and current and step_id != current:
            raise HTTPException(status_code=409, detail="Step is not the current approval gate")
        step_id = current or step_id

        # CAS: only one of approve/reject can win
        result = session.execute(
            update(WorkflowRun)
            .where(WorkflowRun.id == run_id, WorkflowRun.status == "pending_approval")
            .values(
                status="rejected",
                completed_at=_now(),
                error=(reason or "Rejected")[:1000],
                current_step_id=step_id,
            )
        )
        session.commit()
        if not (getattr(result, "rowcount", None) or 0):
            raise HTTPException(status_code=409, detail="Reject already claimed")

        run = session.get(WorkflowRun, run_id)
        assert run is not None
        steps_state = _parse_json(run.steps_state_json, {})
        steps_state[step_id] = {
            **(steps_state.get(step_id) or {}),
            "status": "rejected",
            "rejected_by": rejected_by,
            "reason": reason,
            "completed_at": _now().isoformat(),
        }
        run.steps_state_json = _dumps(steps_state)
        session.add(run)
        session.commit()
        session.refresh(run)
        session.expunge(run)

    _audit(
        actor=rejected_by,
        event_type="workflow_step_rejected",
        resource=f"workflow_run:{run_id}",
        detail=(reason or "rejected")[:500],
        tenant_id=tenant_id,
        step_id=step_id,
        status="rejected",
    )
    return run


async def cancel_workflow(
    run_id: str,
    cancelled_by: str,
    tenant_id: str,
) -> WorkflowRun:
    with Session(engine) as session:
        run = _load_run(session, run_id, tenant_id)
        if run.status in {"completed", "failed", "rejected", "cancelled"}:
            raise HTTPException(status_code=409, detail=f"Cannot cancel run in status {run.status}")
        result = session.execute(
            update(WorkflowRun)
            .where(
                WorkflowRun.id == run_id,
                WorkflowRun.status.in_(["pending", "running", "pending_approval"]),
            )
            .values(
                status="cancelled",
                completed_at=_now(),
                error=f"Cancelled by {cancelled_by}",
            )
        )
        session.commit()
        if not (getattr(result, "rowcount", None) or 0):
            raise HTTPException(status_code=409, detail="Cancel race lost")
        run = session.get(WorkflowRun, run_id)
        assert run is not None
        session.expunge(run)

    _audit(
        actor=cancelled_by,
        event_type="workflow_run_cancelled",
        resource=f"workflow_run:{run_id}",
        detail="cancelled",
        tenant_id=tenant_id,
        status="cancelled",
    )
    return run


def list_definitions(tenant_id: str) -> list[dict[str, Any]]:
    with Session(engine) as session:
        rows = session.exec(
            select(WorkflowDefinition)
            .where(WorkflowDefinition.tenant_id == tenant_id)
            .order_by(col(WorkflowDefinition.updated_at).desc())
        ).all()
        return [serialize_definition(r) for r in rows]


def list_runs(
    tenant_id: str,
    *,
    status: str | None = None,
    workflow_id: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    with Session(engine) as session:
        q = select(WorkflowRun).where(WorkflowRun.tenant_id == tenant_id)
        if status:
            q = q.where(WorkflowRun.status == status)
        if workflow_id:
            q = q.where(WorkflowRun.workflow_id == workflow_id)
        rows = session.exec(q.order_by(col(WorkflowRun.started_at).desc()).limit(min(limit, 500))).all()
        return [serialize_run(r) for r in rows]
