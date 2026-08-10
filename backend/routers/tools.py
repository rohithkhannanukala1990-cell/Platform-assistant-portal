"""Tool registry: tools, accounts, connection logs."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlmodel import Session, select

from ..auth import User, get_current_user
from ..connectors.registry import get_auth_types, get_connector, get_required_fields
from ..database import engine as db_engine
from ..database import Tool, ToolAccount, ToolConnectionLog
from ..services.secrets import decrypt_secret, encrypt_secret
from ..services.isolation import apply_tenant_filter, assert_same_tenant, require_tenant
from sqlalchemy import or_

router = APIRouter(tags=["tools"])

_REGISTRY_CATEGORY_ORDER = (
    "cloud",
    "source_control",
    "project_mgmt",
    "comms",
    "monitoring",
    "databases",
    "kubernetes",
    "secrets",
    "cicd",
)

_REGISTRY_CATEGORY_META: dict[str, tuple[str, str]] = {
    "cloud": ("Cloud", "☁️"),
    "source_control": ("Source control", "🐙"),
    "project_mgmt": ("Project management", "📋"),
    "comms": ("Communications", "💬"),
    "monitoring": ("Monitoring", "📊"),
    "databases": ("Databases", "🐘"),
    "kubernetes": ("Kubernetes", "🐳"),
    "secrets": ("Secrets", "🔐"),
    "cicd": ("CI/CD", "⚙️"),
}


def _tool_to_dict(t: Tool) -> dict:
    return {
        "id": t.id,
        "name": t.name,
        "category": t.category,
        "description": t.description,
        "icon": t.icon,
        "created_at": t.created_at.isoformat(),
    }


def _latest_connection_for_account(session: Session, account_id: str) -> ToolConnectionLog | None:
    return session.exec(
        select(ToolConnectionLog)
        .where(ToolConnectionLog.account_id == account_id)
        .order_by(ToolConnectionLog.tested_at.desc())
    ).first()


def _account_to_dict(session: Session, a: ToolAccount) -> dict:
    log = _latest_connection_for_account(session, a.id)
    has_creds = bool((a.credentials_vault_ref or "").strip())
    return {
        "id": a.id,
        "tool_id": a.tool_id,
        "account_name": a.account_name,
        "account_identifier": a.account_identifier,
        "instance_url": a.instance_url,
        "environment": a.environment,
        "region": a.region,
        "auth_type": a.auth_type,
        # Never return decrypted or raw secrets to the client.
        "has_credentials": has_creds,
        "status": a.status,
        "is_active": bool(a.is_active),
        "requires_hitl": bool(a.requires_hitl),
        "created_by": a.created_by,
        "owner_user_id": getattr(a, "owner_user_id", None),
        "workspace_id": getattr(a, "workspace_id", None),
        "tenant_id": getattr(a, "tenant_id", None),
        "created_at": a.created_at.isoformat(),
        "last_connection_status": log.status if log else None,
        "last_connection_latency_ms": log.latency_ms if log else None,
        "last_tested_at": log.tested_at.isoformat() if log else None,
    }


_CONTEXT_MATRIX_ENVS = (
    "local",
    "development",
    "test",
    "staging",
    "production",
    "dr",
)


def _norm_env_key(s: str | None) -> str:
    return (s or "").strip().lower()


def _matrix_cell_for_account(session: Session, acc: ToolAccount, env_key: str) -> dict | None:
    if _norm_env_key(acc.environment) != env_key:
        return None
    log = _latest_connection_for_account(session, acc.id)
    st = (acc.status or "unknown").lower()
    latency_ms = int(log.latency_ms) if log and log.latency_ms is not None else None
    return {"status": st, "latency_ms": latency_ms}


class ToolCreateBody(BaseModel):
    name: str
    category: str
    description: str | None = None
    icon: str | None = None


class ToolUpdateBody(BaseModel):
    name: str | None = None
    description: str | None = None
    icon: str | None = None


class ToolAccountCreateBody(BaseModel):
    account_name: str
    account_identifier: str | None = None
    instance_url: str | None = None
    environment: str
    region: str | None = None
    auth_type: str
    credentials_vault_ref: str | None = None
    requires_hitl: int | None = None


class ToolAccountUpdateBody(BaseModel):
    account_name: str | None = None
    account_identifier: str | None = None
    instance_url: str | None = None
    environment: str | None = None
    region: str | None = None
    auth_type: str | None = None
    credentials_vault_ref: str | None = None
    status: str | None = None
    requires_hitl: int | None = None


@router.get("/api/connectors")
def api_list_connectors(current_user: User = Depends(get_current_user)):
    """Connector ids + auth metadata — powers the workflow builder's connector
    step palette. No per-connector write-method catalog exists yet, so the
    builder leaves the method field free text."""
    from ..connectors.registry import CONNECTOR_MAP

    return [
        {
            "id": connector_id,
            "auth_types": meta.get("auth_types", []),
            "required_fields": meta.get("required_fields", []),
        }
        for connector_id, meta in sorted(CONNECTOR_MAP.items())
    ]


@router.get("/api/tools/categories")
def api_tools_categories(
    request: Request,
    current_user: User = Depends(get_current_user),
):
    tenant_id = require_tenant(request)
    with Session(db_engine) as session:
        out: list[dict] = []
        for cat_id in _REGISTRY_CATEGORY_ORDER:
            label, cicon = _REGISTRY_CATEGORY_META.get(cat_id, (cat_id.replace("_", " ").title(), "📦"))
            tools_rows = session.exec(select(Tool).where(Tool.category == cat_id)).all()
            tool_count = len(tools_rows)
            tids = [t.id for t in tools_rows]
            if not tids:
                account_count = 0
            else:
                aq = select(ToolAccount).where(
                    ToolAccount.tool_id.in_(tids),
                    ToolAccount.is_active == 1,
                )
                aq = apply_tenant_filter(aq, ToolAccount, tenant_id)
                role = (current_user.role or "").strip().lower()
                if role not in {"admin", "superadmin", "platformadmin"}:
                    uid = str(current_user.id) if current_user.id is not None else None
                    ownership = []
                    if uid:
                        ownership.append(ToolAccount.owner_user_id == uid)
                    ownership.append(ToolAccount.created_by == current_user.username)
                    aq = aq.where(or_(*ownership))
                accounts = session.exec(aq).all()
                account_count = len(accounts)
            out.append(
                {
                    "id": cat_id,
                    "label": label,
                    "icon": cicon,
                    "tool_count": tool_count,
                    "account_count": account_count,
                }
            )
    return out


@router.get("/api/tools")
def api_tools_grouped(current_user: User = Depends(get_current_user)):
    grouped: dict[str, list[dict]] = {c: [] for c in _REGISTRY_CATEGORY_ORDER}
    with Session(db_engine) as session:
        rows = session.exec(select(Tool).order_by(Tool.category, Tool.name)).all()
        for t in rows:
            key = t.category
            if key not in grouped:
                grouped[key] = []
            grouped[key].append(_tool_to_dict(t))
    return grouped


@router.post("/api/tools")
def api_tools_create(
    body: ToolCreateBody,
    current_user: User = Depends(get_current_user),
):
    if not body.name.strip() or not body.category.strip():
        raise HTTPException(status_code=400, detail="name and category are required")
    tid = str(uuid.uuid4())
    row = Tool(
        id=tid,
        name=body.name.strip(),
        category=body.category.strip(),
        description=(body.description or "").strip() or None,
        icon=body.icon,
    )
    with Session(db_engine) as session:
        session.add(row)
        session.commit()
        session.refresh(row)
    return _tool_to_dict(row)


@router.put("/api/tools/{tool_id}")
def api_tools_update(
    tool_id: str,
    body: ToolUpdateBody,
    current_user: User = Depends(get_current_user),
):
    data = body.model_dump(exclude_unset=True)
    with Session(db_engine) as session:
        row = session.get(Tool, tool_id)
        if not row:
            raise HTTPException(status_code=404, detail="Tool not found")
        if "name" in data and data["name"] is not None:
            nm = str(data["name"]).strip()
            if not nm:
                raise HTTPException(status_code=400, detail="name cannot be empty")
            row.name = nm
        if "description" in data:
            row.description = (data["description"] or "").strip() or None
        if "icon" in data:
            row.icon = data["icon"]
        session.add(row)
        session.commit()
        session.refresh(row)
    return _tool_to_dict(row)


@router.delete("/api/tools/{tool_id}")
def api_tools_delete(tool_id: str, current_user: User = Depends(get_current_user)):
    with Session(db_engine) as session:
        row = session.get(Tool, tool_id)
        if not row:
            raise HTTPException(status_code=404, detail="Tool not found")
        active = session.exec(
            select(ToolAccount).where(
                ToolAccount.tool_id == tool_id,
                ToolAccount.is_active == 1,
            )
        ).first()
        if active:
            raise HTTPException(
                status_code=400,
                detail="Cannot delete tool with active accounts",
            )
        session.delete(row)
        session.commit()
    return {"ok": True}


@router.get("/api/tools/{tool_id}/auth-types")
def api_tool_auth_types(tool_id: str, current_user: User = Depends(get_current_user)):
    with Session(db_engine) as session:
        if not session.get(Tool, tool_id):
            raise HTTPException(status_code=404, detail="Tool not found")
    return get_auth_types(tool_id)


@router.get("/api/tools/{tool_id}/required-fields")
def api_tool_required_fields(tool_id: str, current_user: User = Depends(get_current_user)):
    with Session(db_engine) as session:
        if not session.get(Tool, tool_id):
            raise HTTPException(status_code=404, detail="Tool not found")
    return get_required_fields(tool_id)


@router.get("/api/tools/{tool_id}/accounts/matrix")
def api_tool_accounts_matrix(
    tool_id: str,
    request: Request,
    current_user: User = Depends(get_current_user),
):
    """Per-account × environment matrix (connection status for the account's environment)."""
    tenant_id = require_tenant(request)
    with Session(db_engine) as session:
        if not session.get(Tool, tool_id):
            raise HTTPException(status_code=404, detail="Tool not found")
        q = select(ToolAccount).where(
            ToolAccount.tool_id == tool_id, ToolAccount.is_active == 1
        )
        q = apply_tenant_filter(q, ToolAccount, tenant_id)
        role = (current_user.role or "").strip().lower()
        if role not in {"admin", "superadmin", "platformadmin"}:
            uid = str(current_user.id) if current_user.id is not None else None
            ownership = []
            if uid:
                ownership.append(ToolAccount.owner_user_id == uid)
            ownership.append(ToolAccount.created_by == current_user.username)
            q = q.where(or_(*ownership))
        rows = session.exec(q.order_by(ToolAccount.created_at.desc())).all()
        accounts_out: list[dict] = []
        for acc in rows:
            matrix: dict[str, dict | None] = {}
            for env_key in _CONTEXT_MATRIX_ENVS:
                matrix[env_key] = _matrix_cell_for_account(session, acc, env_key)
            accounts_out.append({"id": acc.id, "name": acc.account_name, "matrix": matrix})
    return {
        "tool_id": tool_id,
        "environments": list(_CONTEXT_MATRIX_ENVS),
        "accounts": accounts_out,
    }


@router.get("/api/tools/{tool_id}/accounts")
def api_tool_accounts_list(
    tool_id: str,
    request: Request,
    environment: str | None = None,
    status: str | None = None,
    current_user: User = Depends(get_current_user),
):
    tenant_id = require_tenant(request)
    with Session(db_engine) as session:
        tool = session.get(Tool, tool_id)
        if not tool:
            raise HTTPException(status_code=404, detail="Tool not found")
        q = select(ToolAccount).where(ToolAccount.tool_id == tool_id)
        q = apply_tenant_filter(q, ToolAccount, tenant_id)
        # Non-admins only see accounts they own (or created).
        role = (current_user.role or "").strip().lower()
        if role not in {"admin", "superadmin", "platformadmin"}:
            uid = str(current_user.id) if current_user.id is not None else None
            ownership = []
            if uid:
                ownership.append(ToolAccount.owner_user_id == uid)
            ownership.append(ToolAccount.created_by == current_user.username)
            q = q.where(or_(*ownership))
        if environment:
            q = q.where(ToolAccount.environment == environment)
        if status:
            q = q.where(ToolAccount.status == status)
        rows = session.exec(q.order_by(ToolAccount.created_at.desc())).all()
        return [_account_to_dict(session, a) for a in rows]


@router.post("/api/tools/{tool_id}/accounts")
def api_tool_accounts_create(
    tool_id: str,
    body: ToolAccountCreateBody,
    request: Request,
    current_user: User = Depends(get_current_user),
):
    if not body.account_name.strip() or not body.environment.strip() or not body.auth_type.strip():
        raise HTTPException(
            status_code=400,
            detail="account_name, environment, and auth_type are required",
        )
    aid = str(uuid.uuid4())
    rh = body.requires_hitl
    hitl = 1 if rh is not None and int(rh) != 0 else 0
    raw_secret = (body.credentials_vault_ref or "").strip()
    stored_secret = encrypt_secret(raw_secret) if raw_secret else None
    ws = getattr(request.state, "workspace_id", None) or getattr(
        current_user, "workspace_id", None
    )
    tid = getattr(request.state, "tenant_id", None) or getattr(
        current_user, "tenant_id", None
    ) or "default"
    row = ToolAccount(
        id=aid,
        tool_id=tool_id,
        account_name=body.account_name.strip(),
        account_identifier=(body.account_identifier or "").strip() or None,
        instance_url=(body.instance_url or "").strip() or None,
        environment=body.environment.strip(),
        region=(body.region or "").strip() or None,
        auth_type=body.auth_type.strip(),
        credentials_vault_ref=stored_secret,
        requires_hitl=hitl,
        created_by=current_user.username,
        owner_user_id=str(current_user.id) if current_user.id is not None else None,
        workspace_id=(str(ws).strip() if ws else None) or None,
        tenant_id=(str(tid).strip() if tid else "default"),
    )
    with Session(db_engine) as session:
        tool = session.get(Tool, tool_id)
        if not tool:
            raise HTTPException(status_code=404, detail="Tool not found")
        session.add(row)
        session.commit()
        session.refresh(row)
        return _account_to_dict(session, row)


@router.put("/api/tools/{tool_id}/accounts/{account_id}")
def api_tool_accounts_update(
    tool_id: str,
    account_id: str,
    body: ToolAccountUpdateBody,
    request: Request,
    current_user: User = Depends(get_current_user),
):
    data = body.model_dump(exclude_unset=True)
    tenant_id = require_tenant(request)
    with Session(db_engine) as session:
        row = session.get(ToolAccount, account_id)
        if not row or row.tool_id != tool_id:
            raise HTTPException(status_code=404, detail="Account not found")
        assert_same_tenant(getattr(row, "tenant_id", None), tenant_id)
        for key in (
            "account_name",
            "account_identifier",
            "instance_url",
            "environment",
            "region",
            "auth_type",
            "status",
        ):
            if key in data and data[key] is not None:
                val = data[key]
                setattr(row, key, str(val).strip() if isinstance(val, str) else val)
        if "credentials_vault_ref" in data and data["credentials_vault_ref"] is not None:
            raw = str(data["credentials_vault_ref"]).strip()
            # Empty string means "leave existing secret unchanged".
            if raw:
                row.credentials_vault_ref = encrypt_secret(raw)
        if "requires_hitl" in data and data["requires_hitl"] is not None:
            row.requires_hitl = 1 if int(data["requires_hitl"]) else 0
        if not getattr(row, "owner_user_id", None) and current_user.id is not None:
            row.owner_user_id = str(current_user.id)
        session.add(row)
        session.commit()
        session.refresh(row)
        return _account_to_dict(session, row)


@router.delete("/api/tools/{tool_id}/accounts/{account_id}")
def api_tool_accounts_delete(
    tool_id: str,
    account_id: str,
    current_user: User = Depends(get_current_user),
):
    with Session(db_engine) as session:
        row = session.get(ToolAccount, account_id)
        if not row or row.tool_id != tool_id:
            raise HTTPException(status_code=404, detail="Account not found")
        row.is_active = 0
        session.add(row)
        session.commit()
    return {"ok": True, "message": "Account deactivated"}


@router.post("/api/tools/{tool_id}/accounts/{account_id}/test")
async def api_tool_accounts_test(
    tool_id: str,
    account_id: str,
    request: Request,
    current_user: User = Depends(get_current_user),
):
    tenant_id = require_tenant(request)
    with Session(db_engine) as session:
        acc = session.get(ToolAccount, account_id)
        if not acc or acc.tool_id != tool_id:
            raise HTTPException(status_code=404, detail="Account not found")
        assert_same_tenant(getattr(acc, "tenant_id", None), tenant_id)
        plain = decrypt_secret(acc.credentials_vault_ref or "")
        account_dict = {
            "tool_id": acc.tool_id,
            "account_name": acc.account_name,
            "account_identifier": acc.account_identifier,
            "instance_url": acc.instance_url,
            "environment": acc.environment,
            "region": acc.region,
            "auth_type": acc.auth_type,
            "credentials_vault_ref": plain,
            "token": plain,
            "api_token": plain,
        }
    connector = get_connector(account_dict["tool_id"], account_dict)
    result = await connector.test_connection()
    connected = bool(result.get("connected"))
    latency_ms = result.get("latency_ms")
    err = result.get("error")
    log_status = "connected" if connected else "failed"
    with Session(db_engine) as session:
        acc2 = session.get(ToolAccount, account_id)
        if not acc2 or acc2.tool_id != tool_id:
            raise HTTPException(status_code=404, detail="Account not found")
        log = ToolConnectionLog(
            id=str(uuid.uuid4()),
            account_id=account_id,
            status=log_status,
            latency_ms=int(latency_ms) if latency_ms is not None else None,
            error_message=str(err) if err else None,
        )
        session.add(log)
        acc2.status = "connected" if connected else "failed"
        session.add(acc2)
        session.commit()
    return result
