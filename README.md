# AIOps Platform Assistant

An internal developer portal that combines service catalog, incident response, cost, security, and DORA metrics into one place — with AI specialist agents that can investigate and act on your infrastructure, guarded by human-in-the-loop approvals.

## What it does

- **Dashboard & health** — platform-wide KPIs, service health, DORA metrics, AWS cost.
- **Incident response** — triage queue, incident command center, runbooks, log scanning.
- **Service catalog** — services, scorecards, golden paths, standards, entity actions.
- **AI agents** — 17 specialist agents (incident, cost, security, deploy, migration, and more) that run analyses and propose actions. Risky actions in production require explicit human approval before they execute.
- **LLM cost tracking** — every AI call records token usage and estimated USD cost per user; org-wide utilization, per-user/provider breakdowns, and monthly token budgets appear under Reports → Token Utilization.
- **Workspaces & environments** — group tools, accounts, and users per team; agent behavior adapts to the selected environment (local → dev → test → staging → prod → DR).

See [docs/USER_GUIDE.md](docs/USER_GUIDE.md) for how to use the portal day-to-day, and [docs/AGENTS.md](docs/AGENTS.md) for the full agent catalog.

## Tech stack

| Layer | Technology |
|---|---|
| Frontend | React 18, Vite 5, Tailwind CSS 3, React Router 7, TypeScript (incremental) |
| Backend | FastAPI, SQLModel, Celery |
| Data | PostgreSQL 16 (production) / SQLite (local dev), Redis 7 |
| Observability | Prometheus, Grafana, Loki |
| Auth | JWT sessions, optional SAML SSO and Google OAuth |

## Local development

Every path below runs with **zero required configuration** — no `.env` file, no API keys. Agent calls return canned mock responses (`LLM_MOCK=1` by default everywhere except production), and a **"Mock mode"** badge appears in the top bar whenever that's active, so a demo is never confused about whether a response was real.

There are three ways to run it, from fastest to most complete. Pick one; you don't need more than one running at a time (they'd fight over the same ports).

### Path 1 — Fastest: `make dev` (Docker, SQLite, ~30s warm / a few minutes cold)

Prerequisites: Docker with Compose. No CLI tools, no `.env` file, no Postgres/Redis.

```bash
make dev
#  — or, without make:
docker compose -f docker-compose.dev.yml up
```

Open http://localhost:5173 and log in with `admin` / `Admin123!`.

- **First time ever**: the backend image has to compile `lxml`/`xmlsec` from source (a one-time libxml2-version fix — see comments in `backend/Dockerfile`), which takes a few minutes, and the frontend container runs `npm install` fresh, which adds roughly another minute. Both are cached afterward (Docker layer cache for the backend as long as `requirements.txt` doesn't change; a persisted `node_modules` volume for the frontend as long as you don't `docker compose -f docker-compose.dev.yml down -v`).
- **Every time after that**: backend becomes healthy in ~20–30 seconds; frontend reuses its cached `node_modules` and starts in a few more.
- **What works**: login, all 17 agents (mock responses), the code editor (local files — create/save/format), the terminal (shell only), workspaces, dashboard, catalog.
- **What doesn't**: kubectl/helm/terraform/aws-cli aren't in this image — the terminal reports them as "not installed" instead of crashing (`backend/services/terminal_capabilities.py`). No Postgres/Redis/Celery/nginx/Prometheus/Grafana/Loki — background jobs (webhook delivery, scheduled workflows) run in-process instead of via Celery, which is fine for local testing but not how production behaves.

### Path 2 — Full stack: `make up` (Docker, Postgres + Redis + real terminal tools, ~5 minutes first build)

Prerequisites: Docker with Compose.

```bash
# 1. Configure the backend environment
cp backend/.env.example backend/.env
#    Edit backend/.env — at minimum set SECRET_KEY to a random value.

# 2. Start the full stack
make up
#  — or, without make:
docker compose up -d

# 3. Open the portal
#    Frontend:  http://localhost:5173
#    API docs:  http://localhost:8000/docs
#    Grafana:   http://localhost:3002  (admin / admin123 by default)
```

Default admin login is `admin` / `Admin123!` (override with `DEFAULT_ADMIN_USERNAME` / `DEFAULT_ADMIN_PASSWORD`). Change these before exposing the stack to anyone else.

The backend image also bundles kubectl, helm, terraform, and aws-cli v2 (~150MB combined) so the in-app terminal can actually run them — this is what makes the first build slow. `docker build`/`docker compose build` prints a `Downloading <tool> (~<size>)…` line before each one, so a slow build looks like progress, not a hang; see [Troubleshooting](#troubleshooting) below if it still looks stuck.

**What works**: everything, including real terminal CLI execution and Celery-backed background jobs. **Mock LLM is still on by default** here too (`LLM_MOCK` defaults to `1` in `docker-compose.yml`) — set a real `OPENAI_API_KEY`/`ANTHROPIC_API_KEY` in `backend/.env` and `LLM_MOCK=0` to get live model calls.

### Path 3 — No Docker (native Python + Node)

Prerequisites: Python 3.12, Node 20.

Backend — **run this from the repository root**, not from inside `backend/` (the package needs to be importable as `backend.*`, which only resolves one directory up; Docker images work around this with a symlink that a bare checkout doesn't have):

```bash
cd backend && pip install -r requirements.txt && cd ..
LLM_MOCK=1 uvicorn backend.main:app --reload --port 8000
```

No `DATABASE_URL` needed — the backend falls back to a local SQLite file (`backend/incidents.db`) automatically. Redis is optional everywhere in the request path (login lockout, rate limiting, workflow triggers, and Celery task dispatch all have working in-process fallbacks) — `/health/ready` will show `"redis": {"status": "skipped"}` and nothing breaks.

Frontend (separate terminal):

```bash
npm install
npm run dev        # http://localhost:5173, proxies /api, /auth, /ws to :8000
```

Log in with `admin` / `changeme123` (the code-level default when `DEFAULT_ADMIN_PASSWORD` isn't set — different from the `Admin123!` shown on the login screen, which matches the two Docker paths above where it's set explicitly in the compose files). Set `DEFAULT_ADMIN_PASSWORD=Admin123!` before first startup if you want them to match.

**What works**: login, mock agent runs, the editor (local files), the terminal, workspaces. **What doesn't**: the terminal can only run binaries actually on your machine's `PATH` — there's no image bundling kubectl/helm/terraform/aws-cli here, so it's whatever you have installed locally.

Useful scripts: `npm run lint`, `npm run test`, `npm run build`.

Backend tests:

```bash
pytest backend/tests/ -v
```

### Makefile reference

`make` (no target) lists every command with a one-line description. Highlights: `make up`/`make down` (full stack), `make dev`/`make dev-down` (lean stack), `make logs`, `make test-backend`, `make test-frontend`, `make smoke`, `make rebuild`/`make rebuild-lean` (no-cache), `make db-reset`/`make db-reset-dev`.

### Troubleshooting

**Build appears to hang while downloading kubectl/helm/terraform/aws-cli.** It isn't hung — `docker build` prints a `Downloading <tool> (~<size>)…` line before each of the four downloads (~150MB combined), so check `docker compose build backend` output for the most recent one. If you don't need real CLI execution in the terminal, switch to `make dev` (Path 1), which skips these entirely.

**Port already in use (5173 or 8000).** Something else is bound to it — often a leftover container from a previous run, or the *other* Docker path still running (the full stack and the lean dev stack use different Compose project names, `platformasistant` vs `platformasistant-dev`, so they won't collide with each other's containers/images, but they do claim the same host ports). Find and stop it:

```bash
docker ps                        # look for a container publishing :5173 or :8000
docker compose down               # stop the full stack
docker compose -f docker-compose.dev.yml down   # stop the lean stack
```

**Stale database schema.** For Postgres (full stack), run migrations: `alembic -c backend/alembic.ini upgrade head`. For a clean slate on either Docker path, `make db-reset` (full stack) or `make db-reset-dev` (lean stack) drops the volume and restarts.

**Starting over from nothing.** `docker compose down -v && docker compose -f docker-compose.dev.yml down -v` (removes all containers and volumes), then remove `node_modules/` and `backend/incidents.db` if you've also been running the no-Docker path.

### Which features need which connector

Agents and integrations degrade gracefully without a connector configured — the dashboard's setup checklist (visible on first login) tracks how many of the 12 supported connectors are connected, and calls out **GitHub and PagerDuty** as the two most agents depend on. A few concrete examples, pulled from what the code actually checks:

- **Code editor's repo browsing** (as opposed to local scratch files, which always work) needs a GitHub connection — `backend/services/editor_service.py` returns *"GitHub is not connected. Open Settings → Tool Registry and connect a GitHub account."* until one is added.
- Most integrations (GitHub, AWS, Kubernetes, ArgoCD, ServiceNow, Prometheus, Datadog, Okta, and more) are connected **per-account** under Settings → Tool Registry — there's no env var for them.
- Two exceptions are configured via top-level backend env vars instead: **Slack** (`SLACK_WEBHOOK_URL`) and **Jira** (`JIRA_DOMAIN` / `JIRA_EMAIL` / `JIRA_API_TOKEN` / `JIRA_PROJECT_KEY`), both in `backend/.env.example`.

None of this is required to log in, run agents in mock mode, or use the editor/terminal locally — connectors only gate the specific live integrations that need real credentials.

## Database migrations

Schema changes are managed with Alembic (`backend/alembic/`):

```bash
# Apply migrations (fresh production database)
alembic -c backend/alembic.ini upgrade head

# Existing database created before Alembic was introduced? Mark it current once:
alembic -c backend/alembic.ini stamp head

# Create a new migration after changing SQLModel models
alembic -c backend/alembic.ini revision --autogenerate -m "describe the change"
```

Local development still auto-creates tables at startup, so migrations are only required for shared/production databases.

## Configuration

| File | Purpose |
|---|---|
| `backend/.env.example` | Backend settings — secret key, database, LLM providers, SSO |
| `.env.example` | Compose-level overrides (Postgres/Redis passwords, ports) |
| `.env.production.example` | Hardened values for production deployments |

Key environment variables:

- `SECRET_KEY` — JWT signing key. The backend **refuses to start** in non-test environments if this is empty or left at the default.
- `DATABASE_URL` — Postgres connection string; omit for SQLite local dev.
- `ENV` — environment name (`local`, `dev`, `test`, `staging`, `prod`, `dr`). Controls agent guardrails and approval requirements.

## Project layout

```
backend/          FastAPI app
  agents/         17 specialist AI agents + BaseAgent contract
  routers/        HTTP API endpoints
  services/       Business logic
  connectors/     GitHub, AWS, and other tool integrations
  db/             SQLModel models and engine setup
  tests/          Pytest suite (runs in CI)
src/              React frontend
  components/     Pages and shared UI primitives (components/ui)
docs/             Architecture, user guide, threat model, runbooks
deploy/           Production deployment assets
nginx/ grafana/ prometheus/   Infrastructure configs for the compose stack
```

## Safety model

Agents classify every proposed action by risk. In `prod` and `dr` environments, medium/high-risk actions are queued for **human approval** before execution — nothing destructive runs unattended. Command execution passes through an allowlist-based validator (see [docs/COMMAND_POLICY.md](docs/COMMAND_POLICY.md)).

## CI

Every push and pull request runs:

- Backend pytest suite
- Frontend ESLint, unit tests, and production build
- `pip-audit` / `npm audit` dependency scans
- Full docker-compose build with a `/health/ready` smoke check

See `.github/workflows/`.

## Documentation

| Doc | What's inside |
|---|---|
| [USER_GUIDE.md](docs/USER_GUIDE.md) | How to use the portal, agents, environments, workspaces |
| [ARCHITECTURE.md](docs/ARCHITECTURE.md) | System design |
| [AGENTS.md](docs/AGENTS.md) | Agent catalog and contracts |
| [THREAT_MODEL.md](docs/THREAT_MODEL.md) | Security analysis |
| [PRODUCTION_READINESS.md](docs/PRODUCTION_READINESS.md) | Go-live checklist |
