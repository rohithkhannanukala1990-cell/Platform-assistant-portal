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

## Quickstart (Docker, ~5 minutes)

Prerequisites: Docker with Compose.

```bash
# 1. Configure the backend environment
cp backend/.env.example backend/.env
#    Edit backend/.env — at minimum set SECRET_KEY to a random value.

# 2. Start the full stack
docker compose up -d

# 3. Open the portal
#    Frontend:  http://localhost:5173
#    API docs:  http://localhost:8000/docs
#    Grafana:   http://localhost:3002  (admin / admin123 by default)
```

Default admin login is `admin` / `Admin123!` (override with `DEFAULT_ADMIN_USERNAME` / `DEFAULT_ADMIN_PASSWORD`). Change these before exposing the stack to anyone else.

## Local development (without Docker)

Backend (Python 3.12):

```bash
cd backend
pip install -r requirements.txt
uvicorn backend.main:app --reload --port 8000
```

The backend falls back to a local SQLite database (`incidents.db`) when `DATABASE_URL` is not set, so it starts with zero configuration.

Frontend (Node 20):

```bash
npm install
npm run dev        # http://localhost:5173
```

Useful scripts: `npm run lint`, `npm run test`, `npm run build`.

Backend tests:

```bash
pytest backend/tests/ -v
```

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
