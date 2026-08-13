"""RBAC permission evaluation (used by API routes and middleware)."""

from __future__ import annotations

from typing import Optional, Tuple

from sqlmodel import Session, select

from .database import Permission, Role, RolePermission, UserRole



def perm_key(resource: str, action: str) -> str:
    return f"{resource}:{action}"


def load_role_permission_keys(session: Session, role_id: str) -> set[str]:
    rows = session.exec(
        select(Permission.resource, Permission.action)
        .join(RolePermission, RolePermission.permission_id == Permission.id)
        .where(RolePermission.role_id == role_id)
    ).all()
    return {perm_key(r, a) for r, a in rows}


def is_action_allowed(granted: set[str], resource: str, action: str) -> bool:
    if perm_key(resource, action) in granted:
        return True
    if perm_key(resource, "manage") in granted:
        return True
    return False


def _candidate_user_ids(session: Session, user_id: str | int) -> set[str]:
    """Bridge numeric auth IDs and legacy username-based RBAC assignments."""
    from .auth import User

    value = str(user_id)
    candidates = {value}
    user = None
    if value.isdigit():
        user = session.get(User, int(value))
    if user is None:
        user = session.exec(select(User).where(User.username == value)).first()
    if user:
        candidates.add(user.username)
        if user.id is not None:
            candidates.add(str(user.id))
    return candidates


def collect_grants_for_check(
    session: Session,
    user_id: str | int,
    check_scope_type: str,
    check_scope_id: str,
) -> set[str]:
    """Merge permission keys from global assignments and matching scoped assignments."""
    check_scope_type = (check_scope_type or "global").strip() or "global"
    check_scope_id = (check_scope_id or "").strip()

    out: set[str] = set()
    candidate_user_ids = _candidate_user_ids(session, user_id)
    ur_rows = session.exec(
        select(UserRole).where(UserRole.user_id.in_(candidate_user_ids))  # type: ignore[attr-defined]
    ).all()
    for ur in ur_rows:
        role = session.get(Role, ur.role_id)
        if not role or not role.is_active:
            continue
        perms = load_role_permission_keys(session, role.id)
        st = (ur.scope_type or "global").strip() or "global"
        sid = (ur.scope_id or "").strip()
        applies = False
        if st == "global" or (st == "" and sid == ""):
            applies = True
        elif check_scope_type == "global" and not check_scope_id:
            # Workspace-only role does not grant global portal actions
            applies = False
        elif st == check_scope_type and sid == check_scope_id:
            applies = True
        if applies:
            out.update(perms)
    return out


def collect_all_grants_for_user(
    session: Session, user_id: str | int
) -> tuple[set[str], list[str]]:
    """Union of all permission keys from all assignments + role slugs (for listing)."""
    out: set[str] = set()
    slugs: list[str] = []
    seen_slug: set[str] = set()
    candidate_user_ids = _candidate_user_ids(session, user_id)
    ur_rows = session.exec(
        select(UserRole).where(UserRole.user_id.in_(candidate_user_ids))  # type: ignore[attr-defined]
    ).all()
    for ur in ur_rows:
        role = session.get(Role, ur.role_id)
        if not role or not role.is_active:
            continue
        if role.slug not in seen_slug:
            seen_slug.add(role.slug)
            slugs.append(role.slug)
        out.update(load_role_permission_keys(session, role.id))
    return out, sorted(slugs)


def check_user_permission(
    session: Session,
    user_id: str | int,
    resource: str,
    action: str,
    scope_type: str,
    scope_id: Optional[str],
) -> Tuple[bool, str]:
    if not user_id:
        return False, "Missing user_id"
    resource = (resource or "").strip()
    action = (action or "").strip()
    if not resource or not action:
        return False, "resource and action are required"

    granted = collect_grants_for_check(session, user_id, scope_type, scope_id or "")
    if is_action_allowed(granted, resource, action):
        return True, "allowed"
    return False, f"Missing permission {resource}:{action}"
