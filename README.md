# Platform Assistant Portal (AIOps)

An internal AIOps / Platform Engineering portal that combines **alert triage**, **HITL agent approvals**, **infra + CI/CD generation**, **webhook ingestion**, and **observability** (Prometheus/Grafana/Loki) in a single React SPA backed by FastAPI.

## Architecture (current codebase)

### Runtime components

- **Frontend**: React (Vite) SPA served by Vite dev server in Docker (`frontend` service).
- **Backend API**: FastAPI (`backend/main.py`) with JWT auth + RBAC + security headers.
- **Database**: PostgreSQL via SQLModel (`backend/database.py`).
- **Queue**: Celery + Redis (`backend/worker.py`, `backend/tasks.py`) for webhook processing and scheduled monitoring.
- **Observability**: Prometheus scrapes backend `/metrics`, Grafana provisioned with Prometheus+Loki datasources, Loki for log aggregation.

### Data flow overview

1. **User logs in** (JWT; optional TOTP MFA).
2. UI calls the API via **`authFetch`** (adds Bearer token).
3. Backend triages logs via **LLM provider** (Ollama or Gemini), parses structured JSON, writes incidents to Postgres.
4. For High/Critical incidents, backend routes to **HITL** and surfaces approval cards in the UI.
5. Webhooks can enqueue work via Celery, persisting **webhook events** and producing incidents/notifications.
6. Backend exports **Prometheus metrics** and structured logs (Loki-ready).

### High-level diagram

```
┌──────────────────────────┐      HTTP (JWT)       ┌──────────────────────────┐
│  React (Vite) SPA         │  ───────────────────▶ │  FastAPI Backend          │
│  src/*                    │                       │  backend/main.py          │
│  - AuthContext/authFetch  │                       │  - RBAC + MFA             │
│  - Approvals (HITL)       │                       │  - Webhooks               │
└─────────────┬────────────┘                       └───────┬──────────────────┘
              │                                              │
              │                                              │ SQLModel
              │                                              ▼
              │                                       ┌───────────────┐
              │                                       │ PostgreSQL      │
              │                                       └───────────────┘
              │
              │ enqueue async tasks                    ┌───────────────┐
              └──────────────────────────────────────▶ │ Redis + Celery  │
                                                       │ backend/tasks.py│
                                                       └───────────────┘

                       metrics (/metrics)    ┌───────────────┐
                 ┌──────────────────────────▶│ Prometheus      │
                 │                           └───────┬────────┘
                 │                                   ▼
                 │                           ┌───────────────┐
                 └──────────────────────────▶│ Grafana         │
                                             └───────────────┘

                       logs (JSON)           ┌───────────────┐
                 ┌──────────────────────────▶│ Loki            │
                 └───────────────────────────└───────────────┘
```

## Key backend modules

- **Auth + RBAC + MFA**: `backend/auth.py`
  - JWT (HS256 by default; RS256 if keys are provided)
  - TOTP MFA endpoints (`/auth/mfa/setup`, `/auth/mfa/verify`)
  - Seed admin via env vars (`DEFAULT_ADMIN_USERNAME`, `DEFAULT_ADMIN_PASSWORD`)
- **API + orchestration**: `backend/main.py`
  - Triage flow and HITL decisioning
  - Webhook ingestion + signature verification (`backend/webhooks/security.py`)
  - Prometheus metrics + security headers middleware
- **Persistence**: `backend/database.py`
  - Incidents, notifications, webhook events, infra generations, CI/CD pipelines
- **Async tasks**: `backend/worker.py`, `backend/tasks.py`
  - Webhook processing and monitoring jobs
- **Safety**: `backend/command_validator.py`, `backend/executor/safe_executor.py`
  - Guardrail blocks dangerous commands; dry-run + rollback inference
- **Observability**: `backend/observability/metrics.py`, `backend/observability/logger.py`
  - Prometheus metrics and structured JSON logs

## Getting started (Docker Compose)

### Prerequisites

- Docker Desktop

### Run the stack

From repo root:

```bash
docker compose up --build
```

### Services (defaults)

- **Frontend**: `http://localhost:5173`
- **Backend**: `http://localhost:8000`
- **Grafana**: `http://localhost:${GRAFANA_PORT:-3002}`
- **Prometheus**: `http://localhost:9090`
- **Loki**: `http://localhost:3100`

### Default credentials

The backend seeds an admin user if missing:

- **Username**: `${DEFAULT_ADMIN_USERNAME:-admin}`
- **Password**: `${DEFAULT_ADMIN_PASSWORD:-Admin123!}`

Set strong values in `backend/.env` (or your environment) before running in any shared environment.

## Environment configuration

Key variables (see `docker-compose.yml` and `backend/.env.example`):

- **Database**
  - `DATABASE_URL` (Postgres in Docker; SQLite fallback in dev)
- **JWT**
  - `JWT_SECRET_KEY`
  - `JWT_EXPIRE_MINUTES`
  - Optional: `JWT_PRIVATE_KEY`, `JWT_PUBLIC_KEY` for RS256
- **Admin seed**
  - `DEFAULT_ADMIN_USERNAME`
  - `DEFAULT_ADMIN_PASSWORD`
- **Redis/Celery**
  - `REDIS_PASSWORD`
  - `CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND`
- **Webhook secrets**
  - `GITHUB_WEBHOOK_SECRET`, `GITLAB_WEBHOOK_SECRET`, `PAGERDUTY_WEBHOOK_SECRET`, `DATADOG_WEBHOOK_SECRET`, `AIRFLOW_WEBHOOK_SECRET`

## Implementation steps (how the system works)

Use this as a “read the codebase in order” guide.

1. **Boot + middleware**
   - FastAPI app init and middleware live in `backend/main.py` (CORS, rate limiting, security headers).
2. **Auth foundation**
   - JWT issuance + validation in `backend/auth.py`
   - UI stores token + uses `authFetch` in `src/contexts/AuthContext.jsx`
3. **Triage pipeline**
   - `_run_triage(...)` in `backend/main.py` calls the LLM, parses JSON, persists incident, increments metrics, and creates notifications.
4. **HITL approvals**
   - High/Critical routes to `AWAITING_APPROVAL`
   - UI uses `src/components/AgentApprovalsWidget.jsx` to approve/reject and view execution logs
5. **Webhook ingestion**
   - Webhook routes accept payloads and verify signatures using `backend/webhooks/security.py`
   - Events are persisted (`WebhookEvent`) and processed asynchronously via Celery (`backend/tasks.py`)
6. **Safety + execution**
   - Command validation in `backend/command_validator.py`
   - Dry-run and rollback in `backend/executor/safe_executor.py`
7. **Observability**
   - Metrics defined in `backend/observability/metrics.py` and exposed at `/metrics`
   - Prometheus config in `prometheus/prometheus.yml`
   - Grafana datasources provisioned in `grafana/provisioning/datasources/datasources.yml`
   - Structured logging in `backend/observability/logger.py` (Loki-ready)

## Common endpoints

- **Auth**
  - `POST /auth/login` (supports `totp_code` form field for MFA)
  - `GET /auth/me`
- **Incidents**
  - `GET /api/incidents`
  - `GET /api/incidents/approvals`
  - `POST /api/incidents/{id}/approve`
  - `POST /api/incidents/{id}/reject`
  - `POST /api/incidents/{id}/dry-run`
- **Notifications**
  - `GET /api/notifications`
  - `POST /api/notifications/{id}/read`
- **Webhooks**
  - `POST /api/webhooks/logs`
  - `GET /api/webhooks/activity`
- **Observability**
  - `GET /metrics`
  - `GET /health`

## Development notes

- If you run services outside Docker, ensure the frontend uses `VITE_API_BASE_URL` pointing at the backend.
- Celery worker entrypoint is `backend.worker.celery_app` (see `backend/worker.py`).

