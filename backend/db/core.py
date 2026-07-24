"""Engine, session dependency, migrate, and bootstrap seeds."""
from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone

from sqlalchemy import text as sa_text
from sqlmodel import Session, SQLModel, create_engine, select

# Use DATABASE_URL from env.
# - Docker / production: set to postgresql://...
# - Local dev without Docker: defaults to SQLite so the server starts immediately
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./incidents.db")

# Normalise PostgreSQL scheme so psycopg2 driver is used
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+psycopg2://", 1)
elif DATABASE_URL.startswith("postgresql://") and "+psycopg2" not in DATABASE_URL:
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg2://", 1)

_is_postgres = DATABASE_URL.startswith("postgresql")
_is_sqlite = DATABASE_URL.startswith("sqlite")

_engine_kwargs: dict = {"echo": False, "pool_pre_ping": True}
if _is_postgres:
    _engine_kwargs.update(
        {
            "pool_size": 10,
            "max_overflow": 20,
            "connect_args": {"connect_timeout": 10},
        }
    )
elif _is_sqlite:
    _engine_kwargs.update(
        {
            "connect_args": {"check_same_thread": False},
        }
    )

engine = create_engine(DATABASE_URL, **_engine_kwargs)


def get_db():
    """FastAPI dependency — yields a SQLModel session and closes it when done."""
    with Session(engine) as session:
        yield session


def _import_models():
    from backend.db.models import (  # noqa: F401
        ai_models,
        context_models,
        ops,
        rbac_tables,
        tools,
        workspace,
    )

    # User / AuditLog live in auth — ensure auth models registered:
    from backend import auth as _auth  # noqa: F401


DEFAULT_SETTINGS = {
    "slack_webhook_url": "",
    "auto_triage_enabled": "false",
    "theme": "dark",
    "default_cloud": "GCP",
    "default_cicd_tool": "GitHub Actions",
    "jira_domain": "",
    "jira_email": "",
    "jira_api_token": "",
    "jira_project_key": "",
}


def create_db_and_tables():
    _import_models()
    SQLModel.metadata.create_all(engine)
    _migrate()
    _seed_settings()
    _seed_tools()
    _seed_workspaces()
    _seed_templates()
    _seed_rbac()
    with Session(engine) as session:
        from backend.routers.standards import seed_production_readiness_standard

        seed_production_readiness_standard(session)
        from backend.routers.entity_actions import seed_default_actions

        seed_default_actions(session)
        from backend.routers.golden_paths import seed_golden_path_templates

        seed_golden_path_templates(session)


def _seed_tools() -> None:
    """Idempotent seed of built-in tool catalog rows."""
    from backend.db.models.tools import Tool

    rows: list[tuple[str, str, str, str, str]] = [
        ("aws", "AWS", "cloud", "Amazon Web Services", "☁️"),
        ("gcp", "GCP", "cloud", "Google Cloud Platform", "☁️"),
        ("azure", "Azure", "cloud", "Microsoft Azure", "☁️"),
        ("oci", "OCI", "cloud", "Oracle Cloud Infrastructure", "☁️"),
        ("github", "GitHub", "source_control", "GitHub Repositories", "🐙"),
        ("gitlab", "GitLab", "source_control", "GitLab Repositories", "🦊"),
        ("bitbucket", "Bitbucket", "source_control", "Bitbucket Repositories", "🪣"),
        ("jira", "Jira", "project_mgmt", "Jira Project Management", "📋"),
        ("confluence", "Confluence", "project_mgmt", "Atlassian Confluence", "📘"),
        ("linear", "Linear", "project_mgmt", "Linear Issue Tracking", "📐"),
        ("servicenow", "ServiceNow", "project_mgmt", "ServiceNow ITSM", "🔧"),
        ("slack", "Slack", "comms", "Slack Messaging", "💬"),
        ("teams", "Teams", "comms", "Microsoft Teams", "💬"),
        ("pagerduty", "PagerDuty", "comms", "PagerDuty Alerting", "🚨"),
        ("prometheus", "Prometheus", "monitoring", "Prometheus Metrics", "📊"),
        ("datadog", "Datadog", "monitoring", "Datadog Monitoring", "🐶"),
        ("grafana", "Grafana", "monitoring", "Grafana Dashboards", "📈"),
        ("newrelic", "New Relic", "monitoring", "New Relic Observability", "🔵"),
        ("postgres", "PostgreSQL", "databases", "PostgreSQL Database", "🐘"),
        ("mysql", "MySQL", "databases", "MySQL Database", "🐬"),
        ("mongodb", "MongoDB", "databases", "MongoDB NoSQL", "🍃"),
        ("redis", "Redis", "databases", "Redis Cache", "⚡"),
        ("kubernetes", "Kubernetes", "kubernetes", "Kubernetes Clusters", "🐳"),
        ("vault", "HashiCorp Vault", "secrets", "HashiCorp Vault", "🔐"),
        ("aws_sm", "AWS Secrets Manager", "secrets", "AWS Secrets Manager", "🔑"),
        ("jenkins", "Jenkins", "cicd", "Jenkins CI/CD", "⚙️"),
        ("argocd", "ArgoCD", "cicd", "ArgoCD GitOps", "🐙"),
    ]
    with Session(engine) as session:
        for tid, name, cat, desc, icon in rows:
            if session.get(Tool, tid):
                continue
            session.add(Tool(id=tid, name=name, category=cat, description=desc, icon=icon))
        session.commit()


def _seed_workspaces() -> None:
    """Idempotent seed of default workspaces."""
    from backend.db.models.workspace import Workspace

    defaults: list[dict] = [
        {
            "id": "ws-incident",
            "name": "Incident Response",
            "slug": "incident-response",
            "description": None,
            "icon": "🚨",
            "color": "#ef4444",
            "environment": "production",
            "tags": json.dumps(["oncall", "sre", "production"]),
            "is_pinned": 1,
        },
        {
            "id": "ws-deploy",
            "name": "Deploy Pipeline",
            "slug": "deploy-pipeline",
            "description": None,
            "icon": "🚀",
            "color": "#8b5cf6",
            "environment": "production",
            "tags": json.dumps(["ci", "cd", "kubernetes"]),
            "is_pinned": 1,
        },
        {
            "id": "ws-cost",
            "name": "Cost & Audit",
            "slug": "cost-audit",
            "description": None,
            "icon": "💰",
            "color": "#f59e0b",
            "environment": "production",
            "tags": json.dumps(["finops", "billing", "audit"]),
            "is_pinned": 0,
        },
        {
            "id": "ws-dev",
            "name": "Developer Tools",
            "slug": "developer-tools",
            "description": None,
            "icon": "🛠️",
            "color": "#10b981",
            "environment": "development",
            "tags": json.dumps(["dev", "local", "testing"]),
            "is_pinned": 0,
        },
        {
            "id": "ws-security",
            "name": "Security & Compliance",
            "slug": "security-compliance",
            "description": None,
            "icon": "🔒",
            "color": "#06b6d4",
            "environment": "production",
            "tags": json.dumps(["security", "compliance", "soc2"]),
            "is_pinned": 0,
        },
    ]
    now = datetime.now(timezone.utc)
    with Session(engine) as session:
        for row in defaults:
            if session.get(Workspace, row["id"]):
                continue
            session.add(
                Workspace(
                    id=row["id"],
                    name=row["name"],
                    slug=row["slug"],
                    description=row["description"],
                    icon=row["icon"],
                    color=row["color"],
                    environment=row["environment"],
                    tags=row["tags"],
                    is_active=1,
                    is_pinned=row["is_pinned"],
                    created_by="admin",
                    created_at=now,
                    updated_at=now,
                )
            )
        session.commit()


def _seed_templates() -> None:
    """Idempotent seed of default workspace templates."""
    from backend.db.models.tools import Tool
    from backend.db.models.workspace import Template, TemplateTool

    specs: list[dict] = [
        {
            "id": "tmpl-incident",
            "name": "Incident Response Team",
            "slug": "incident-response-team",
            "description": None,
            "icon": "🚨",
            "color": "#ef4444",
            "category": "operations",
            "environment": "production",
            "tags": json.dumps(["sre", "oncall", "production"]),
            "is_published": 1,
            "tools": ["aws", "kubernetes", "datadog", "pagerduty", "slack"],
        },
        {
            "id": "tmpl-deploy",
            "name": "Deploy Pipeline",
            "slug": "deploy-pipeline",
            "description": None,
            "icon": "🚀",
            "color": "#8b5cf6",
            "category": "engineering",
            "environment": "production",
            "tags": json.dumps(["ci", "cd", "devops"]),
            "is_published": 1,
            "tools": ["github", "kubernetes", "argocd", "datadog"],
        },
        {
            "id": "tmpl-new-team",
            "name": "New Team Onboarding",
            "slug": "new-team-onboarding",
            "description": None,
            "icon": "👥",
            "color": "#10b981",
            "category": "onboarding",
            "environment": "development",
            "tags": json.dumps(["onboarding", "new-team", "setup"]),
            "is_published": 1,
            "tools": ["github", "jira", "slack", "confluence"],
        },
        {
            "id": "tmpl-cost",
            "name": "FinOps & Cost Review",
            "slug": "finops-cost-review",
            "description": None,
            "icon": "💰",
            "color": "#f59e0b",
            "category": "finops",
            "environment": "production",
            "tags": json.dumps(["finops", "billing", "cloud-cost"]),
            "is_published": 1,
            "tools": ["aws", "gcp", "azure", "datadog"],
        },
    ]
    now = datetime.now(timezone.utc)
    with Session(engine) as session:
        for spec in specs:
            tid = spec["id"]
            if session.get(Template, tid):
                continue
            session.add(
                Template(
                    id=tid,
                    name=spec["name"],
                    slug=spec["slug"],
                    description=spec["description"],
                    icon=spec["icon"],
                    color=spec["color"],
                    category=spec["category"],
                    environment=spec["environment"],
                    tags=spec["tags"],
                    is_active=1,
                    is_published=spec["is_published"],
                    use_count=0,
                    created_by="admin",
                    created_at=now,
                    updated_at=now,
                )
            )
            for order, tool_id in enumerate(spec["tools"]):
                if not session.get(Tool, tool_id):
                    continue
                session.add(
                    TemplateTool(
                        id=str(uuid.uuid4()),
                        template_id=tid,
                        tool_id=tool_id,
                        account_id=None,
                        display_order=order,
                        is_required=1,
                        config_hints="{}",
                    )
                )
        session.commit()


def _seed_rbac() -> None:
    """Idempotent seed of RBAC permissions and system roles."""
    from backend.db.models.rbac_tables import Permission, Role, RolePermission

    matrix: dict[str, list[str]] = {
        "workspaces": ["read", "create", "update", "delete", "manage"],
        "tools": ["read", "create", "update", "delete", "manage"],
        "tool_accounts": ["read", "create", "update", "delete", "test", "manage"],
        "templates": ["read", "create", "update", "delete", "apply", "manage"],
        "golden_paths": ["read", "create", "update", "delete", "run", "manage"],
        "entity_actions": ["read", "trigger", "manage"],
        "catalog": ["read", "write", "manage"],
        "ai_tools": ["read", "execute", "approve", "manage"],
        "import": ["read", "create", "update", "delete", "export", "manage"],
        "roles": ["read", "create", "update", "delete", "manage"],
        "user_roles": ["read", "create", "update", "delete", "manage"],
        "health": ["read", "manage"],
        "audit_logs": ["read", "export", "manage"],
    }
    now = datetime.now(timezone.utc)

    def pid(resource: str, action: str) -> str:
        return f"perm-{resource}-{action}"

    with Session(engine) as session:
        for resource, actions in matrix.items():
            for action in actions:
                rid = pid(resource, action)
                if session.get(Permission, rid):
                    continue
                session.add(
                    Permission(
                        id=rid,
                        resource=resource,
                        action=action,
                        description=f"{action.title()} on {resource}",
                    )
                )
        session.commit()

        def all_perm_ids() -> list[str]:
            return [p.id for p in session.exec(select(Permission)).all()]

        def link_role(role_id: str, perm_ids: list[str]) -> None:
            for p in perm_ids:
                exists = session.exec(
                    select(RolePermission).where(
                        RolePermission.role_id == role_id,
                        RolePermission.permission_id == p,
                    )
                ).first()
                if exists:
                    continue
                session.add(
                    RolePermission(
                        id=f"rp-{uuid.uuid4().hex[:12]}",
                        role_id=role_id,
                        permission_id=p,
                    )
                )

        roles_spec = [
            {
                "id": "role-superadmin",
                "name": "Super Admin",
                "slug": "superadmin",
                "description": "Full platform access",
                "is_system": 1,
                "perm_filter": None,
            },
            {
                "id": "role-admin",
                "name": "Admin",
                "slug": "admin",
                "description": "Administrative access except destructive RBAC deletes",
                "is_system": 1,
                "perm_filter": "exclude",
                "exclude": {pid("user_roles", "delete"), pid("roles", "delete")},
            },
            {
                "id": "role-operator",
                "name": "Operator",
                "slug": "operator",
                "description": "Day-2 operations",
                "is_system": 1,
                "perm_filter": "include",
                "include": [
                    pid("workspaces", "read"),
                    pid("workspaces", "create"),
                    pid("workspaces", "update"),
                    pid("tools", "read"),
                    pid("tool_accounts", "read"),
                    pid("tool_accounts", "test"),
                    pid("templates", "read"),
                    pid("templates", "apply"),
                    pid("golden_paths", "read"),
                    pid("golden_paths", "run"),
                    pid("health", "read"),
                    pid("entity_actions", "read"),
                    pid("entity_actions", "trigger"),
                    pid("catalog", "read"),
                    pid("catalog", "write"),
                    pid("ai_tools", "read"),
                    pid("ai_tools", "execute"),
                    pid("import", "read"),
                ],
            },
            {
                "id": "role-viewer",
                "name": "Viewer",
                "slug": "viewer",
                "description": "Read-only access",
                "is_system": 1,
                "perm_filter": "include",
                "include": [
                    pid("workspaces", "read"),
                    pid("tools", "read"),
                    pid("templates", "read"),
                    pid("golden_paths", "read"),
                    pid("health", "read"),
                    pid("entity_actions", "read"),
                    pid("catalog", "read"),
                    pid("ai_tools", "read"),
                ],
            },
        ]

        for spec in roles_spec:
            rid = spec["id"]
            if not session.get(Role, rid):
                session.add(
                    Role(
                        id=rid,
                        name=spec["name"],
                        slug=spec["slug"],
                        description=spec.get("description"),
                        is_system=spec["is_system"],
                        is_active=1,
                        created_at=now,
                    )
                )
        session.commit()

        all_ids = all_perm_ids()
        for spec in roles_spec:
            rid = spec["id"]
            flt = spec.get("perm_filter")
            if flt is None:
                chosen = all_ids
            elif flt == "exclude":
                ex = spec.get("exclude") or set()
                chosen = [p for p in all_ids if p not in ex]
            else:
                chosen = list(spec.get("include") or [])
            link_role(rid, chosen)
        session.commit()


def _column_exists(session: Session, table: str, column: str) -> bool:
    """Works for both PostgreSQL (information_schema) and SQLite (PRAGMA)."""
    if _is_postgres:
        row = session.exec(
            sa_text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = :t AND column_name = :c"
            ).bindparams(t=table, c=column)
        ).first()
        return row is not None
    else:
        rows = session.exec(sa_text(f"PRAGMA table_info({table})")).all()
        return any(r[1] == column for r in rows)


def _migrate():
    """
    Idempotently add columns introduced after the initial schema.
    Uses information_schema on PostgreSQL, PRAGMA on SQLite.
    """
    migrations = [
        ("incident", "source", "TEXT", "'manual'"),
        ("incident", "status", "TEXT", "'OPEN'"),
        ("incident", "execution_logs", "TEXT", "NULL"),
        ("incident", "owner_role", "TEXT", "'Admin'"),
        ("incident", "proposed_remediation_plan", "TEXT", "NULL"),
        ("incident", "agent_execution_logs", "TEXT", "NULL"),
        ("notification", "incident_id", "INTEGER", "NULL"),
        ("user", "last_login", "TIMESTAMP", "NULL"),
        ("user", "tenant_id", "TEXT", "'default'"),
        ("user", "workspace_id", "TEXT", "NULL"),
        ("workspaces", "canvas_json", "TEXT", "'{}'"),
        ("workspaces", "tenant_id", "TEXT", "'default'"),
        ("workspaces", "settings_json", "TEXT", "'{}'"),
        ("tool_accounts", "tenant_id", "TEXT", "'default'"),
        ("tool_accounts", "owner_user_id", "TEXT", "NULL"),
        ("tool_accounts", "workspace_id", "TEXT", "NULL"),
        ("user_context", "workspace_id", "TEXT", "NULL"),
        ("user_context", "tenant_id", "TEXT", "'default'"),
        ("templates", "recommended_golden_path_keys", "TEXT", "'[]'"),
        ("incident", "tenant_id", "TEXT", "'default'"),
        ("incident", "workspace_id", "TEXT", "NULL"),
        ("agent_runs", "tenant_id", "TEXT", "'default'"),
        ("agent_runs", "user_id", "TEXT", "NULL"),
        ("catalog_entities", "tenant_id", "TEXT", "'default'"),
        ("llmproviderconfig", "base_url", "TEXT", "NULL"),
        ("llmproviderconfig", "api_key_vault_ref", "TEXT", "NULL"),
        ("llmproviderconfig", "priority", "INTEGER", "100"),
        ("llmproviderconfig", "metadata_json", "TEXT", "'{}'"),
    ]
    with Session(engine) as session:
        for table, col, col_type, default in migrations:
            try:
                if not _column_exists(session, table, col):
                    default_clause = f"DEFAULT {default}" if default != "NULL" else ""
                    session.exec(
                        sa_text(
                            f'ALTER TABLE "{table}" ADD COLUMN "{col}" {col_type} {default_clause}'
                        )
                    )
                    session.commit()
                    print(f"[migrate] added {table}.{col}")
            except Exception as exc:
                session.rollback()
                print(f"[migrate] {table}.{col}: {exc}")

        if _is_postgres:
            try:
                entity_id_type = session.exec(
                    sa_text(
                        "SELECT data_type FROM information_schema.columns "
                        "WHERE table_name = 'golden_path_runs' "
                        "AND column_name = 'entity_id'"
                    )
                ).first()
                type_name = str(entity_id_type[0]) if entity_id_type is not None else ""
                if type_name and type_name not in {"text", "character varying"}:
                    session.exec(
                        sa_text(
                            "ALTER TABLE golden_path_runs "
                            "ALTER COLUMN entity_id TYPE TEXT "
                            "USING entity_id::text"
                        )
                    )
                    session.commit()
                    print("[migrate] changed golden_path_runs.entity_id to TEXT")
            except Exception as exc:
                session.rollback()
                print(f"[migrate] golden_path_runs.entity_id type: {exc}")


def _seed_settings():
    """Insert default settings only if they don't already exist."""
    from backend.db.models.ops import UserSetting

    with Session(engine) as session:
        for key, value in DEFAULT_SETTINGS.items():
            exists = session.exec(select(UserSetting).where(UserSetting.key == key)).first()
            if not exists:
                session.add(UserSetting(key=key, value=value))
        session.commit()
