import os
from datetime import datetime, timedelta, timezone
from typing import Optional, Callable

import pyotp
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.backends import default_backend
from fastapi import APIRouter, Depends, HTTPException, status, Request, Form
from fastapi.security import OAuth2PasswordBearer
from slowapi import Limiter
from slowapi.util import get_remote_address
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel
from dotenv import load_dotenv
from sqlmodel import SQLModel, Field, Session, select
from sqlalchemy import Column, String

from .database import engine

load_dotenv()


VALID_ROLES = {"Admin", "User", "ReadOnly"}
CANONICAL_ROLE_TO_RBAC_ROLE_ID = {
    "Admin": "role-admin",
    "User": "role-operator",
    "ReadOnly": "role-viewer",
}


# TODO: Normalize roles into a single canonical set (e.g. Admin, Operator, Viewer) used across auth, users, RBAC, and SSO
def normalize_role(role: str | None) -> str:
    """Normalize legacy and RBAC role names to Admin, User, or ReadOnly."""
    value = str(role or "").strip().lower().replace("_", "").replace("-", "")
    if value in {"admin", "superadmin", "platformadmin"}:
        return "Admin"
    if value in {"readonly", "viewer", "read only"}:
        return "ReadOnly"
    return "User"


limiter = Limiter(key_func=get_remote_address)

def get_session():
    with Session(engine) as session:
        yield session


# ── MODELS ────────────────────────────────────────────────────────────────────

class User(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    username: str = Field(
        sa_column=Column(String, unique=True, index=True, nullable=False)
    )
    email: str = Field(default="")
    hashed_password: str
    role: str = Field(default="User")
    is_active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    last_login: datetime | None = Field(default=None)
    mfa_secret: str | None = Field(default=None)
    mfa_enabled: bool = Field(default=False)
    # TODO(S2-P2.1): Add tenant_id/org_id fields to support multi-tenant isolation
    tenant_id: Optional[str] = Field(default="default", index=True)
    workspace_id: Optional[str] = Field(default=None, index=True)


class AuditLog(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    actor: str
    actor_role: str
    event_type: str
    resource: str = Field(default="")
    detail: str = Field(default="")
    ip_address: str = Field(default="")


class LLMProviderConfig(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    provider: str = Field(default="ollama")
    model_name: str = Field(default="llama3.2")
    fallback_provider: str = Field(default="ollama")
    fallback_model: str = Field(default="llama3.2")
    monthly_token_budget: int = Field(default=1_000_000)
    tokens_used_this_month: int = Field(default=0)
    is_active: bool = Field(default=True)
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_by: str = Field(default="system")


# ── PASSWORD HELPERS ──────────────────────────────────────────────────────────

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(plain: str) -> str:
    return pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def verify_mfa_code(secret: str | None, totp_code: str) -> bool:
    if not secret or not totp_code:
        return False
    return bool(pyotp.TOTP(secret).verify(totp_code))


# ── JWT CONFIG ────────────────────────────────────────────────────────────────

# TODO: Read SECRET_KEY from environment and refuse insecure defaults in non-test environments
SECRET_KEY = os.getenv("SECRET_KEY", "CHANGE_ME_IN_PRODUCTION")
if SECRET_KEY == "CHANGE_ME_IN_PRODUCTION" and os.getenv("ENV", "dev") != "test":
    raise RuntimeError("SECRET_KEY must be set for non-test environments")
ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRE_MINUTES", "480"))
JWT_PRIVATE_KEY_PEM = os.getenv("JWT_PRIVATE_KEY", "")
JWT_PUBLIC_KEY_PEM = os.getenv("JWT_PUBLIC_KEY", "")

_private_key = None
_public_key = None
if JWT_PRIVATE_KEY_PEM and JWT_PUBLIC_KEY_PEM:
    _private_key = serialization.load_pem_private_key(
        JWT_PRIVATE_KEY_PEM.encode(),
        password=None,
        backend=default_backend(),
    )
    _public_key = serialization.load_pem_public_key(
        JWT_PUBLIC_KEY_PEM.encode(),
        backend=default_backend(),
    )
    ALGORITHM = "RS256"


def create_access_token(username: str, role: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode = {"sub": username, "role": role, "exp": expire}
    if _private_key:
        return jwt.encode(to_encode, _private_key, algorithm=ALGORITHM)
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> dict:
    try:
        key = _public_key if _public_key else SECRET_KEY
        payload = jwt.decode(token, key, algorithms=[ALGORITHM])
        username = payload.get("sub")
        role = payload.get("role")
        if not username or not role:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
        return payload
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        )


# ── PYDANTIC SCHEMAS ──────────────────────────────────────────────────────────

class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str
    username: str


class LoginRequest(BaseModel):
    username: str
    password: str
    totp_code: str | None = None

    @classmethod
    def as_form(
        cls,
        username: str = Form(...),
        password: str = Form(...),
        totp_code: str | None = Form(None),
    ) -> "LoginRequest":
        return cls(username=username, password=password, totp_code=totp_code)


class UserCreate(BaseModel):
    username: str
    password: str
    email: str = ""
    role: str = "User"


class UserRead(BaseModel):
    id: int
    username: str
    email: str
    role: str
    is_active: bool
    tenant_id: Optional[str] = None
    workspace_id: Optional[str] = None


class LLMConfigUpdate(BaseModel):
    provider: Optional[str] = None
    model_name: Optional[str] = None
    fallback_provider: Optional[str] = None
    fallback_model: Optional[str] = None
    monthly_token_budget: Optional[int] = None
    is_active: Optional[bool] = None


# ── FASTAPI DEPENDENCIES ──────────────────────────────────────────────────────

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


def get_current_user(
    request: Request,
    token: str = Depends(oauth2_scheme),
) -> User:
    payload = decode_token(token)
    username = str(payload.get("sub"))
    with Session(engine) as session:
        user = session.exec(select(User).where(User.username == username)).first()
        if not user or not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid credentials",
                headers={"WWW-Authenticate": "Bearer"},
            )
        request.state.user = user
        return user


def require_role(*roles: str) -> Callable:
    def _dep(user: User = Depends(get_current_user)) -> User:
        allowed_roles = {normalize_role(role) for role in roles}
        if normalize_role(user.role) not in allowed_roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
        return user

    return _dep


def require_admin(user: User = Depends(get_current_user)) -> User:
    if normalize_role(user.role) != "Admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
    return user


# ── AUDIT HELPER ──────────────────────────────────────────────────────────────

def write_audit(
    actor: str,
    actor_role: str,
    event_type: str,
    resource: str = "",
    detail: str = "",
    ip_address: str = "",
) -> None:
    try:
        with Session(engine) as session:
            session.add(
                AuditLog(
                    timestamp=datetime.now(timezone.utc),
                    actor=actor,
                    actor_role=actor_role,
                    event_type=event_type,
                    resource=resource,
                    detail=detail,
                    ip_address=ip_address,
                )
            )
            session.commit()
    except Exception as exc:
        print(f"[audit] WARNING: failed to write audit log: {exc}")


def sync_user_rbac_role(
    session: Session,
    user: User,
    *,
    granted_by: str = "system",
) -> None:
    """Keep a user's canonical auth role aligned with its global system RBAC role."""
    from .database import Role, UserRole

    if user.id is None:
        session.flush()
    canonical_role = normalize_role(user.role)
    user.role = canonical_role
    role_id = CANONICAL_ROLE_TO_RBAC_ROLE_ID[canonical_role]
    if not session.get(Role, role_id):
        return

    user_id = str(user.id)
    system_role_ids = set(CANONICAL_ROLE_TO_RBAC_ROLE_ID.values())
    assignments = session.exec(
        select(UserRole).where(
            UserRole.user_id == user_id,
            UserRole.scope_type == "global",
            UserRole.scope_id == "",
        )
    ).all()
    for assignment in assignments:
        if assignment.role_id in system_role_ids and assignment.role_id != role_id:
            session.delete(assignment)

    if not any(assignment.role_id == role_id for assignment in assignments):
        session.add(
            UserRole(
                id=f"ur-system-{user_id}-{role_id.removeprefix('role-')}",
                user_id=user_id,
                role_id=role_id,
                scope_type="global",
                scope_id="",
                granted_by=granted_by,
                granted_at=datetime.now(timezone.utc),
            )
        )


# ── SEED FUNCTIONS ────────────────────────────────────────────────────────────

def seed_default_admin() -> None:
    username = os.getenv("DEFAULT_ADMIN_USERNAME", "admin")
    password = os.getenv("DEFAULT_ADMIN_PASSWORD", "changeme123")
    with Session(engine) as session:
        existing_admin = session.exec(
            select(User).where(User.username == username)
        ).first()
        if existing_admin:
            admin = existing_admin
        else:
            admin = User(
                username=username,
                email="",
                hashed_password=hash_password(password),
                role="Admin",
                is_active=True,
                created_at=datetime.now(timezone.utc),
                tenant_id=os.getenv("DEFAULT_TENANT_ID", "default"),
                workspace_id=None,
            )
            session.add(admin)
            session.flush()
        # Keep demo / single-tenant admins on the default tenant.
        if not getattr(admin, "tenant_id", None):
            admin.tenant_id = os.getenv("DEFAULT_TENANT_ID", "default")
            session.add(admin)
        sync_user_rbac_role(session, admin)
        session.commit()
    if not existing_admin:
        print(
            f"[auth] WARNING: seeded default admin user ({username}). "
            "Set strong credentials via DEFAULT_ADMIN_USERNAME / DEFAULT_ADMIN_PASSWORD."
        )


def seed_default_llm_config() -> None:
    with Session(engine) as session:
        exists = session.exec(select(LLMProviderConfig).limit(1)).first()
        if exists:
            return
        session.add(
            LLMProviderConfig(
                provider="ollama",
                model_name="llama3.2",
                fallback_provider="ollama",
                fallback_model="llama3.2",
                monthly_token_budget=1_000_000,
                tokens_used_this_month=0,
                is_active=True,
                updated_at=datetime.now(timezone.utc),
                updated_by="system",
            )
        )
        session.commit()


# ── AUTH ROUTER ───────────────────────────────────────────────────────────────

auth_router = APIRouter(prefix="/auth", tags=["auth"])


# TODO: Enforce MFA when user.mfa_enabled is True:
# - Extend login request model with totp_code
# - Verify TOTP code before issuing JWT
@limiter.limit("5/15minutes")
@auth_router.post("/login", response_model=Token)
def login(
    request: Request,
    login_request: LoginRequest = Depends(LoginRequest.as_form),
):
    with Session(engine) as session:
        user = session.exec(
            select(User).where(User.username == login_request.username)
        ).first()
        if (
            not user
            or not user.is_active
            or not verify_password(login_request.password, user.hashed_password)
        ):
            write_audit(
                actor=login_request.username,
                actor_role="unknown",
                event_type="LOGIN_FAILED",
                detail="Invalid credentials attempt",
            )
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    if user.mfa_enabled:
        if not login_request.totp_code:
            raise HTTPException(status_code=401, detail="MFA code required")
        if not verify_mfa_code(user.mfa_secret, login_request.totp_code):
            write_audit(
                actor=user.username,
                actor_role=normalize_role(user.role),
                event_type="LOGIN_FAILED_MFA",
                resource="auth",
                detail="Invalid MFA code",
                ip_address=(request.client.host if request.client else ""),
            )
            raise HTTPException(status_code=401, detail="Invalid MFA code")

    norm_role = normalize_role(user.role)
    with Session(engine) as session:
        db_user = session.get(User, user.id)
        if db_user:
            db_user.last_login = datetime.now(timezone.utc)
            if db_user.role != norm_role and db_user.role not in VALID_ROLES:
                db_user.role = norm_role
            sync_user_rbac_role(session, db_user, granted_by=db_user.username)
            session.add(db_user)
            session.commit()

    token = create_access_token(username=user.username, role=norm_role)
    write_audit(
        actor=user.username,
        actor_role=norm_role,
        event_type="LOGIN",
        resource="auth",
        detail="User logged in",
        ip_address=(request.client.host if request.client else ""),
    )
    return Token(access_token=token, role=norm_role, username=user.username)


@auth_router.post("/mfa/setup")
def setup_mfa(current_user: User = Depends(get_current_user)):
    secret = pyotp.random_base32()
    # Re-fetch and update within a single session to avoid detached instance errors
    with Session(engine) as session:
        user = session.get(User, current_user.id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        user.mfa_secret = secret
        user.mfa_enabled = True
        session.add(user)
        session.commit()
    totp = pyotp.TOTP(secret)
    return {
        "secret": secret,
        "qr_url": totp.provisioning_uri(current_user.username, issuer_name="AIOps Portal"),
        "message": "Scan QR code with Google Authenticator"
    }


@auth_router.post("/mfa/verify")
def verify_mfa(totp_code: str, current_user: User = Depends(get_current_user)):
    if not current_user.mfa_enabled or not current_user.mfa_secret:
        raise HTTPException(400, "MFA not configured")
    if not pyotp.TOTP(current_user.mfa_secret).verify(totp_code):
        raise HTTPException(401, "Invalid MFA code")
    return {"message": "MFA verified successfully"}


@auth_router.get("/me", response_model=UserRead)
def me(user: User = Depends(get_current_user)):
    return UserRead(
        id=user.id,
        username=user.username,
        email=user.email,
        role=normalize_role(user.role),
        is_active=user.is_active,
    )


@auth_router.post("/users", response_model=UserRead)
def create_user(
    request: Request,
    body: UserCreate,
    admin: User = Depends(require_admin),
):
    norm_role = normalize_role(body.role)
    if norm_role not in VALID_ROLES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid role")
    with Session(engine) as session:
        existing = session.exec(select(User).where(User.username == body.username)).first()
        if existing:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Username already exists")
        user = User(
            username=body.username,
            email=body.email,
            hashed_password=hash_password(body.password),
            role=norm_role,
            is_active=True,
            created_at=datetime.now(timezone.utc),
        )
        session.add(user)
        session.flush()
        sync_user_rbac_role(session, user, granted_by=admin.username)
        session.commit()
        session.refresh(user)

    write_audit(
        actor=admin.username,
        actor_role=admin.role,
        event_type="USER_CREATED",
        resource=f"user:{user.username}",
        detail=f"Created user {user.username} with role {user.role}",
        ip_address=(request.client.host if request.client else ""),
    )
    return UserRead(id=user.id, username=user.username, email=user.email, role=user.role, is_active=user.is_active)


@auth_router.get("/audit")
def get_audit(admin: User = Depends(require_admin)):
    with Session(engine) as session:
        rows = session.exec(
            select(AuditLog).order_by(AuditLog.timestamp.desc()).limit(100)
        ).all()
        return [r.model_dump() for r in rows]


@auth_router.get("/llm-config")
def get_llm_config(admin: User = Depends(require_admin)):
    with Session(engine) as session:
        cfg = session.exec(
            select(LLMProviderConfig)
            .where(LLMProviderConfig.is_active == True)  # noqa: E712
            .order_by(LLMProviderConfig.updated_at.desc())
            .limit(1)
        ).first()
        if not cfg:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No active LLM config")
        return cfg.model_dump()


@auth_router.put("/llm-config")
def update_llm_config(
    request: Request,
    body: LLMConfigUpdate,
    admin: User = Depends(require_admin),
):
    with Session(engine) as session:
        cfg = session.exec(
            select(LLMProviderConfig)
            .where(LLMProviderConfig.is_active == True)  # noqa: E712
            .order_by(LLMProviderConfig.updated_at.desc())
            .limit(1)
        ).first()

        if not cfg:
            cfg = LLMProviderConfig()
            session.add(cfg)
            session.flush()

        if body.provider is not None:
            cfg.provider = body.provider
        if body.model_name is not None:
            cfg.model_name = body.model_name
        if body.fallback_provider is not None:
            cfg.fallback_provider = body.fallback_provider
        if body.fallback_model is not None:
            cfg.fallback_model = body.fallback_model
        if body.monthly_token_budget is not None:
            cfg.monthly_token_budget = int(body.monthly_token_budget)
        if body.is_active is not None:
            cfg.is_active = bool(body.is_active)

        cfg.updated_at = datetime.now(timezone.utc)
        cfg.updated_by = admin.username

        session.add(cfg)
        session.commit()
        session.refresh(cfg)

    write_audit(
        actor=admin.username,
        actor_role=admin.role,
        event_type="LLM_CONFIG_UPDATED",
        resource="llm_config",
        detail="Updated LLM provider configuration",
        ip_address=(request.client.host if request.client else ""),
    )
    return cfg.model_dump()

