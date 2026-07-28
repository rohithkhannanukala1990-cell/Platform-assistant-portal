# Architecture

## Stack overview

| Layer | Technology |
|-------|------------|
| API | FastAPI (Python), SlowAPI rate limits, JWT auth |
| UI | React (Vite), role-aware portals |
| Database | PostgreSQL in Docker; SQLite acceptable for local/pytest |
| Queue | Redis + Celery (webhook triage, CI/CD monitor) |
| Observability | Prometheus metrics (`/metrics`), Grafana (compose), structured logs |
| AI | Multi-provider `LLMService` (`openai`, `openai_compatible`, `anthropic`) |

## Request flow

```
UI (authFetch)
  → FastAPI routers (auth, catalog, tools, github_ops, agents, …)
    → PlatformContext / workspace middleware
      → Agents + connectors (GitHub, …)
        → DB (SQLModel) / external APIs
```

1. Browser calls `/auth/login`, stores JWT.
2. Authenticated calls hit routers under `/api/*`.
3. `WorkspaceIsolationMiddleware` attaches workspace/tenant on `request.state`.
4. Expensive work (chat, triage, agents) is rate-limited.
5. Connectors call third-party APIs with ToolAccount credentials; agents ground prompts on live data when connected.

## Routers (responsibilities)

| Router | Role |
|--------|------|
| `auth` | Login, MFA, JWT, audit helper |
| `workspaces` / `rbac` / `users` | Tenancy, roles, user admin |
| `catalog` / `scorecards` / `standards` / `golden_paths` | Service catalog & platform paths |
| `tools` / `imports_api` / `user_context` | Tool Registry, CSV import, active accounts |
| `github_ops` | Read-only GitHub repos / PRs / Actions (+ PR/run detail & jobs) |
| `k8s_ops` / `pagerduty_ops` / `oncall` | Kubernetes + PagerDuty + on-call now |
| `slack_ops` / `prometheus_ops` / `argocd_ops` / `outbound_webhook_ops` | Phase G5 first-class connectors |
| `servicenow_ops` | Optional ServiceNow incident create (HITL) |
| `incidents` / `webhooks_api` / `notifications` | Triage, inbound + native GitHub webhooks, alerts |
| `infra_cicd` | Infra generator, CI/CD generate, active runs, DORA |
| `agents` | Agent run / approve / reject |
| `platform_misc` | Settings, chat, search, anomaly scan |
| `health_api` | Liveness, readiness, full health + connector probes |
| `ai_assistant` | Catalog copilot / AI assistant APIs |

## PlatformContext & workspace isolation

- `PlatformContext` carries `workspace_id`, `tenant_id`, `environment`, `tool_accounts`, and user identity into agents.
- Middleware prefers `X-Workspace-Id`, then the user’s default `workspace_id`.
- **Tenant trust:** if the authenticated user has `tenant_id`, that value always wins. Client `X-Tenant-Id` cannot escalate privileges.
- Sensitive list/get paths filter by `tenant_id` (and ownership for tool accounts). Cross-tenant reads return **404** (not 403) via `assert_same_tenant`.
- `ENFORCE_WORKSPACE_ISOLATION=true` hard-rejects authenticated non-public API calls without a workspace (allowlist: health/auth/settings/LLM status).
- `UserContext` rows are keyed by authenticated numeric user id only.
- Demo / single-tenant setups may run with `DEFAULT_TENANT_ID=default`.
- Active tool accounts are pinned per user in `UserContext.active_accounts` (JSON map `tool_id → account_id`).
- Helpers live in `backend/services/isolation.py` (`require_tenant`, `require_workspace`, `apply_tenant_filter`, `assert_same_tenant`).

## `ENABLE_DEMO_DATA` and `ENV`

- `demo_data_enabled()` in `backend/services/demo_fixtures.py`:
  - Explicit `ENABLE_DEMO_DATA=1|0` wins.
  - Otherwise demo fixtures are allowed when `ENV` is a dev-like value (`dev`, `development`, `test`, `local`).
- When demo is off and no live connector data exists, APIs return `{status: "no_data", ...}` instead of inventing data.

## Connect a GitHub PAT (Tool Registry)

1. Sign in as Admin → **Tool Registry**.
2. Open **GitHub** → add account (auth type PAT, paste token into credentials).
3. Optionally set org in account identifier.
4. **Test Connection** (hits GitHub `/rate_limit`).
5. On success, the UI loads `/api/github/repos` and shows repository links.
6. Set the account active in user/workspace context so agents and `/api/cicd/active-runs` can use it.

Never commit PATs. Tokens are stored as `credentials_vault_ref` and must not appear in logs or API error bodies.

## Celery queues

Workers should listen to all application queues (see `docker-compose.yml` `celery_worker`):

| Queue | Tasks | Purpose |
|-------|-------|---------|
| `triage` | `tasks.process_inbound_webhook`, `tasks.process_webhook_log` | Webhook → AI triage (retries with exponential backoff) |
| `notify` | `tasks.notify_incident` | Durable notification fan-out |
| `celery` | `tasks.monitor_cicd_pipelines` (default) | Background monitors / default queue |

Config lives in `backend/worker.py` (`task_routes`). After max retries, failures are written to `celery_task_failure` for manual replay and counted on `celery_task_failures_total`.

Webhook idempotency: `webhook_delivery.delivery_id` (PK) is claimed **after** HMAC verify; duplicates return HTTP **200** with `status=duplicate`.

Login lockout counters use Redis (`CELERY_BROKER_URL` / `REDIS_URL`) when available, otherwise an in-process fallback (logged warning).

Backup steps: see [`RUNBOOK_BACKUP.md`](./RUNBOOK_BACKUP.md).

## Observability (Phase 15)

- Prometheus scrapes backend `/metrics` (`prometheus/prometheus.yml`).
- Grafana provisions datasources from `grafana/provisioning/` and dashboards from `deploy/grafana/dashboards/`.
- Alert recipes: [`deploy/grafana/ALERT_RULES.md`](../deploy/grafana/ALERT_RULES.md).
- Beta go/no-go: [`BETA_GONOGO.md`](./BETA_GONOGO.md); pilot: [`PILOT_PLAYBOOK.md`](./PILOT_PLAYBOOK.md); smoke via `scripts/pilot_smoke.sh` / `beta_smoke.sh` or `pytest -m smoke`.
- Honest capability ~ vs ✓: [`product_comparison.md`](./product_comparison.md). HA compose: `deploy/docker-compose.prod.yml`.

## First-class connectors vs MCP (Phase G5)

**First-class connectors** live in Tool Registry with scoped `*_access.py` (owner / workspace / tenant — **no global env fallback** on API paths), real `*_connector.py` modules, and authenticated `*_ops` routers:

| Connector | Read | Write |
|-----------|------|-------|
| Slack | channels | notify (Admin or HITL `approved=true`; webhook URL in SecretBox) |
| Prometheus | alerts / PromQL query | — |
| Outbound Webhook | status | deliver events (Admin or HITL) |
| Argo CD | applications health | — |
| ServiceNow (optional) | status | create incident via webhook (HITL) |
| GitHub / K8s / PagerDuty | existing Phase 12 panels | HITL where applicable |

**MCP** is the long-tail edge protocol for tools we do not first-class. It does **not** replace Tool Registry connectors.

## MCP (Phases M1–M2)

Full guide: [`MCP.md`](./MCP.md).

- **Client (M1):** connect out to external MCP servers via `/api/mcp/*` + `hitl_bridge`. Secrets masked; write tools need approval.
- **Server (M2):** `python -m backend.mcp.server_app` exposes portal tools over stdio. Requires `MCP_ENABLED=true` and `PORTAL_MCP_TOKEN`.
- Read tools query incidents/catalog/health/GitHub; write tools (`portal_propose_remediation`, `portal_run_agent`) only create HITL-pending portal work.
- Agents optionally inject the MCP tool catalog; GitHub agents prefer MCP repo tools when configured.

## Compliance (Phase 16)

- Audit retention: setting / env `audit_log_retention_days` (default 90); admin API `/api/audit/retention`.
- Immutable export: `GET /api/audit/export?immutable=true&format=json` (SHA-256 hash chain).
- Control mapping: [`COMPLIANCE.md`](./COMPLIANCE.md); STRIDE: [`THREAT_MODEL.md`](./THREAT_MODEL.md).
- CI dependency scans: `pip-audit` + `npm audit` (and `safety` in `ci.yml`).

## Scaling / HA (Phase 17)

See [`SCALING.md`](./SCALING.md): multi-replica API + shared Redis for lockout/rate limits, JWT (no sticky sessions), Celery worker scale-out, list pagination defaults, and load smoke notes.

## Command guardrails (Phase G1)

See [`COMMAND_POLICY.md`](./COMMAND_POLICY.md). Execution guardrails are a structured policy engine (v1), not regex-only: a baseline regex blocklist runs first (unconditional deny), then DB-backed `CommandPolicyRule` rows decide allow / deny / require_approval per role, environment, tool, and tenant. SafeExecutor re-evaluates per step; denies and approval requirements are audited.

## Agents (Phase G2)

See [`AGENTS.md`](./AGENTS.md). Every specialist returns structured `evidence` + `grounding` (`live`/`partial`/`none`/`demo`), never invents connector data, and routes mutating commands through the G1 policy engine + HITL.

## Run docker-compose locally

```bash
# From repo root — set secrets in .env / backend/.env as needed
docker compose up --build
```

Typical services: `postgres`, `redis`, `backend` (:8000), `celery_worker`, frontend (if defined in compose), Prometheus/Grafana when included.

Quick local API without full stack:

```bash
# SQLite / local Postgres + Redis optional
uvicorn backend.main:app --reload --port 8000
```

UI: `npm install && npm run dev` (point `VITE_*` / `API_BASE` at the API).

## AI / LLM

- All chat goes through `backend/ai/llm_service.py` (`llm_service.chat`).
- Providers: `openai` and `openai_compatible` (OpenAI chat completions via `OPENAI_BASE_URL` / DB `base_url`), plus `anthropic`.
- DB rows in `LLMProviderConfig` store encrypted `api_key_vault_ref` (Phase 8 secrets); multiple active rows allowed, ordered by `priority`.
- Admin API: `/api/llm/status`, `/api/llm/providers`, `/api/llm/test` — GET responses never include raw API keys.
- Resolution: explicit args → `LLM_DEFAULT_*` env → highest-priority active DB row → env API keys → `LLM_MOCK=1` → error.
- `llm_router` is a thin shim for existing call sites.
- UI: Settings → LLM providers; AIAssistant / TopBar read `/api/llm/status`.
