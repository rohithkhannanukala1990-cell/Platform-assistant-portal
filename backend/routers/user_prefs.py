"""Per-user dismissible-hint / onboarding-flag storage. Generic key/value —
used by the editor hint strip, workspace walkthrough, and dashboard setup
checklist so each can be dismissed once and stay dismissed for that user.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ..auth import User, get_current_user
from ..services.user_prefs import get_pref, set_pref

router = APIRouter(prefix="/api/user-prefs", tags=["user-prefs"])


class SetPrefBody(BaseModel):
    value: str


@router.get("/{key}")
def read_pref(key: str, current_user: User = Depends(get_current_user)):
    return {"key": key, "value": get_pref(current_user.username, key)}


@router.put("/{key}")
def write_pref(key: str, body: SetPrefBody, current_user: User = Depends(get_current_user)):
    set_pref(current_user.username, key, body.value)
    return {"key": key, "value": body.value}
