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
| `github_ops` | Read-only GitHub repos / PRs / Actions |
| `incidents` / `webhooks_api` / `notifications` | Triage, inbound webhooks, alerts |
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
- Providers: `openai` and `openai_compatible` (OpenAI chat completions via `OPENAI_BASE_URL`), plus `anthropic`.
- Gemini and Ollama SDKs are removed. Local models use an OpenAI-compatible base URL.
- Resolution: explicit args → `LLM_DEFAULT_PROVIDER` / `LLM_DEFAULT_MODEL` → `OPENAI_API_KEY` → `ANTHROPIC_API_KEY` → `LLM_MOCK=1` → error.
- `llm_router` is a thin shim for existing call sites; do not add provider branches there.
- Status (no secrets): `GET /api/ai/llm/status` and `llm_service.get_status()`.
