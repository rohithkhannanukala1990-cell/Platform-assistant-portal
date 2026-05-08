import os
from datetime import datetime, timedelta, timezone
from typing import Optional, Callable

from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel
from sqlmodel import SQLModel, Field, Session, select
from sqlalchemy import Column, String

from database import engine


VALID_ROLES = {"Admin", "Developer", "DataEngineer", "NetworkEngineer", "DatabaseDeveloper"}


# ── MODELS ────────────────────────────────────────────────────────────────────

class User(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    username: str = Field(
        sa_column=Column(String, unique=True, index=True, nullable=False)
    )
    email: str = Field(default="")
    hashed_password: str
    role: str = Field(default="Developer")
    is_active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


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


# ── JWT CONFIG ────────────────────────────────────────────────────────────────

SECRET_KEY = os.getenv("JWT_SECRET_KEY", "CHANGE_ME_IN_PRODUCTION")
ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRE_MINUTES", "480"))


def create_access_token(username: str, role: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode = {"sub": username, "role": role, "exp": expire}
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> dict:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
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


class UserCreate(BaseModel):
    username: str
    password: str
    email: str = ""
    role: str = "Developer"


class UserRead(BaseModel):
    id: int
    username: str
    email: str
    role: str
    is_active: bool


class LLMConfigUpdate(BaseModel):
    provider: Optional[str] = None
    model_name: Optional[str] = None
    fallback_provider: Optional[str] = None
    fallback_model: Optional[str] = None
    monthly_token_budget: Optional[int] = None
    is_active: Optional[bool] = None


# ── FASTAPI DEPENDENCIES ──────────────────────────────────────────────────────

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


def get_current_user(token: str = Depends(oauth2_scheme)) -> User:
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
        return user


def require_role(*roles: str) -> Callable:
    def _dep(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
        return user

    return _dep


def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != "Admin":
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


# ── SEED FUNCTIONS ────────────────────────────────────────────────────────────

def seed_default_admin() -> None:
    username = os.getenv("DEFAULT_ADMIN_USERNAME", "admin")
    password = os.getenv("DEFAULT_ADMIN_PASSWORD", "changeme123")
    with Session(engine) as session:
        exists = session.exec(select(User).limit(1)).first()
        if exists:
            return
        session.add(
            User(
                username=username,
                email="",
                hashed_password=hash_password(password),
                role="Admin",
                is_active=True,
                created_at=datetime.now(timezone.utc),
            )
        )
        session.commit()
    print("[auth] WARNING: seeded default admin user. Change DEFAULT_ADMIN_PASSWORD immediately.")


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


@auth_router.post("/login", response_model=Token)
def login(
    request: Request,
    form: OAuth2PasswordRequestForm = Depends(),
):
    with Session(engine) as session:
        user = session.exec(select(User).where(User.username == form.username)).first()
        if not user or not user.is_active or not verify_password(form.password, user.hashed_password):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    token = create_access_token(username=user.username, role=user.role)
    write_audit(
        actor=user.username,
        actor_role=user.role,
        event_type="LOGIN",
        resource="auth",
        detail="User logged in",
        ip_address=(request.client.host if request.client else ""),
    )
    return Token(access_token=token, role=user.role, username=user.username)


@auth_router.get("/me", response_model=UserRead)
def me(user: User = Depends(get_current_user)):
    return UserRead(id=user.id, username=user.username, email=user.email, role=user.role, is_active=user.is_active)


@auth_router.post("/users", response_model=UserRead)
def create_user(
    request: Request,
    body: UserCreate,
    admin: User = Depends(require_admin),
):
    if body.role not in VALID_ROLES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid role")
    with Session(engine) as session:
        existing = session.exec(select(User).where(User.username == body.username)).first()
        if existing:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Username already exists")
        user = User(
            username=body.username,
            email=body.email,
            hashed_password=hash_password(body.password),
            role=body.role,
            is_active=True,
            created_at=datetime.now(timezone.utc),
        )
        session.add(user)
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

