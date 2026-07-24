"""Multi-LLM provider configuration API (/api/llm)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlmodel import Session, col, select

from ..auth import LLMProviderConfig, User, engine, get_current_user, require_admin, write_audit
from ..ai.llm_service import llm_service
from ..ai.providers import LLMNotConfiguredError
from ..services.secrets import encrypt_secret

router = APIRouter(prefix="/api/llm", tags=["llm-config"])


def _mask_row(row: LLMProviderConfig) -> dict[str, Any]:
    return {
        "id": row.id,
        "provider": row.provider,
        "model_name": row.model_name,
        "base_url": row.base_url,
        "has_api_key": bool((row.api_key_vault_ref or "").strip()),
        "fallback_provider": row.fallback_provider,
        "fallback_model": row.fallback_model,
        "monthly_token_budget": row.monthly_token_budget,
        "tokens_used_this_month": row.tokens_used_this_month,
        "is_active": row.is_active,
        "priority": int(row.priority or 0),
        "metadata_json": row.metadata_json or "{}",
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        "updated_by": row.updated_by,
    }


class ProviderCreate(BaseModel):
    provider: str = "openai"
    model_name: str = "gpt-4o-mini"
    base_url: Optional[str] = None
    api_key: Optional[str] = None
    fallback_provider: str = "openai"
    fallback_model: str = "gpt-4o-mini"
    monthly_token_budget: int = 1_000_000
    is_active: bool = True
    priority: int = 100
    metadata_json: Optional[str] = "{}"


class ProviderUpdate(BaseModel):
    provider: Optional[str] = None
    model_name: Optional[str] = None
    base_url: Optional[str] = None
    api_key: Optional[str] = None  # omit / null / "" keeps existing
    fallback_provider: Optional[str] = None
    fallback_model: Optional[str] = None
    monthly_token_budget: Optional[int] = None
    is_active: Optional[bool] = None
    priority: Optional[int] = None
    metadata_json: Optional[str] = None


class TestRequest(BaseModel):
    provider_id: Optional[int] = None
    provider: Optional[str] = None
    model: Optional[str] = None
    prompt: str = Field(default="Reply with exactly: pong")


@router.get("/status")
def llm_status(current_user: User = Depends(get_current_user)):
    _ = current_user
    return llm_service.get_status()


@router.get("/providers")
def list_providers(current_user: User = Depends(get_current_user)):
    _ = current_user
    with Session(engine) as session:
        rows = session.exec(
            select(LLMProviderConfig).order_by(
                col(LLMProviderConfig.priority).desc(),
                col(LLMProviderConfig.updated_at).desc(),
            )
        ).all()
        return [_mask_row(r) for r in rows]


@router.post("/providers", status_code=status.HTTP_201_CREATED)
def create_provider(
    body: ProviderCreate,
    admin: User = Depends(require_admin),
):
    vault_ref = None
    if body.api_key and str(body.api_key).strip():
        vault_ref = encrypt_secret(str(body.api_key).strip())

    meta = body.metadata_json or "{}"
    try:
        json.loads(meta)
    except Exception:
        raise HTTPException(status_code=400, detail="metadata_json must be valid JSON")

    row = LLMProviderConfig(
        provider=(body.provider or "openai").strip().lower(),
        model_name=(body.model_name or "gpt-4o-mini").strip(),
        base_url=(body.base_url or None),
        api_key_vault_ref=vault_ref,
        fallback_provider=(body.fallback_provider or "openai").strip().lower(),
        fallback_model=(body.fallback_model or "gpt-4o-mini").strip(),
        monthly_token_budget=int(body.monthly_token_budget or 1_000_000),
        tokens_used_this_month=0,
        is_active=bool(body.is_active),
        priority=int(body.priority if body.priority is not None else 100),
        metadata_json=meta,
        updated_at=datetime.now(timezone.utc),
        updated_by=admin.username,
    )
    with Session(engine) as session:
        session.add(row)
        session.commit()
        session.refresh(row)
        write_audit(
            actor=admin.username,
            actor_role=admin.role,
            event_type="LLM_PROVIDER_CREATED",
            resource="llm_config",
            detail=f"Created LLM provider id={row.id} provider={row.provider}",
        )
        return _mask_row(row)


@router.put("/providers/{provider_id}")
def update_provider(
    provider_id: int,
    body: ProviderUpdate,
    admin: User = Depends(require_admin),
):
    with Session(engine) as session:
        row = session.get(LLMProviderConfig, provider_id)
        if not row:
            raise HTTPException(status_code=404, detail="Provider not found")

        if body.provider is not None:
            row.provider = body.provider.strip().lower()
        if body.model_name is not None:
            row.model_name = body.model_name.strip()
        if body.base_url is not None:
            row.base_url = body.base_url.strip() or None
        if body.api_key is not None and str(body.api_key).strip():
            row.api_key_vault_ref = encrypt_secret(str(body.api_key).strip())
        if body.fallback_provider is not None:
            row.fallback_provider = body.fallback_provider.strip().lower()
        if body.fallback_model is not None:
            row.fallback_model = body.fallback_model.strip()
        if body.monthly_token_budget is not None:
            row.monthly_token_budget = int(body.monthly_token_budget)
        if body.is_active is not None:
            row.is_active = bool(body.is_active)
        if body.priority is not None:
            row.priority = int(body.priority)
        if body.metadata_json is not None:
            try:
                json.loads(body.metadata_json or "{}")
            except Exception:
                raise HTTPException(status_code=400, detail="metadata_json must be valid JSON")
            row.metadata_json = body.metadata_json or "{}"

        row.updated_at = datetime.now(timezone.utc)
        row.updated_by = admin.username
        session.add(row)
        session.commit()
        session.refresh(row)
        write_audit(
            actor=admin.username,
            actor_role=admin.role,
            event_type="LLM_PROVIDER_UPDATED",
            resource="llm_config",
            detail=f"Updated LLM provider id={row.id}",
        )
        return _mask_row(row)


@router.delete("/providers/{provider_id}")
def delete_provider(
    provider_id: int,
    admin: User = Depends(require_admin),
):
    with Session(engine) as session:
        row = session.get(LLMProviderConfig, provider_id)
        if not row:
            raise HTTPException(status_code=404, detail="Provider not found")
        session.delete(row)
        session.commit()
        write_audit(
            actor=admin.username,
            actor_role=admin.role,
            event_type="LLM_PROVIDER_DELETED",
            resource="llm_config",
            detail=f"Deleted LLM provider id={provider_id}",
        )
        return {"ok": True, "id": provider_id}


@router.post("/test")
async def test_provider(
    body: TestRequest,
    admin: User = Depends(require_admin),
):
    _ = admin
    try:
        if body.provider_id is not None:
            text = await llm_service.chat(
                prompt=body.prompt or "Reply with exactly: pong",
                config_id=body.provider_id,
            )
        else:
            text = await llm_service.chat(
                prompt=body.prompt or "Reply with exactly: pong",
                provider=body.provider,
                model=body.model,
            )
        return {"ok": True, "response": text[:500]}
    except LLMNotConfiguredError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"LLM test failed: {exc}") from exc
