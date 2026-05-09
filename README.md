# AIOps Platform Engineering Assistant

> An enterprise-grade, AI-powered Internal Developer Portal (IDP) that unifies alert triage, infrastructure generation, CI/CD automation, agentic remediation workflows, and real-time observability — all in a single dark-mode dashboard.

Built with FastAPI + React 18 + PostgreSQL + Celery + Redis + Ollama/Gemini. Demonstrates production-grade platform engineering: JWT auth, RBAC, Human-in-the-Loop agent flows, AI safety guardrails, async task queues, Prometheus metrics, Grafana dashboards, and structured JSON LLM orchestration.

---

## Contents

| Section | Description |
|---|---|
| [Architecture](#architecture) | Full system diagram — all 8 layers |
| [Tech Stack](#tech-stack) | Every technology and its purpose |
| [Docker Services](#docker-services) | All 8 services in docker-compose.yml |
| [File-by-File Guide](#file-by-file-guide) | What every file does |
| [Getting Started](#getting-started) | Run in 3 commands |
| [Environment Variables](#environment-variables) | Full .env reference |
| [Implementation Steps](#implementation-steps) | 21 end-to-end verification steps |
| [API Reference](#api-reference) | All endpoints with auth requirements |
| [Webhook Gateway](#webhook-gateway) | Sources, routing, curl examples |
| [HITL Agentic Flow](#hitl-agentic-flow) | Full approval decision tree |
| [AI Safety Guardrail](#ai-safety-guardrail) | CommandValidator blocklist |
| [Role-Based Portals](#role-based-portals) | Personas, routes, modules |
| [What's Next](#whats-next) | Prioritised roadmap |

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    BROWSER — React 18 SPA (Vite + Tailwind)             │
│                                                                         │
│  AuthContext.jsx          RoleContext.jsx                               │
│  ├─ parseJWT()            └─ active persona (Admin/Developer/…)        │
│  ├─ isTokenExpired()                                                    │
│  ├─ authFetch()  ──── injects Bearer token on every API call           │
│  └─ auto-logout on 401                                                  │
│                                                                         │
│  React Router v6 Portals:                                              │
│  /ops          OpsPortal.jsx        (Admin + NetworkEngineer)          │
│  /developer    DeveloperPortal.jsx  (Developer)                        │
│  /data         DataEngineerPortal.jsx (DataEngineer)                   │
│  /database     DatabasePortal.jsx   (DatabaseDeveloper)                │
└───────────────────────────┬─────────────────────────────────────────────┘
                            │  HTTP REST  —  Authorization: Bearer <JWT>
┌───────────────────────────▼─────────────────────────────────────────────┐
│                    FASTAPI BACKEND  (port 8000)                         │
│                                                                         │
│  Middleware stack (applied to EVERY request, top → bottom):            │
│  ① CORSMiddleware       allow_origins=[frontend:5173] + localhost regex │
│  ② add_security_headers  CSP · HSTS · X-Frame-Options · XSS-Protection │
│  ③ slowapi RateLimiter   per-IP rate limit → 429 on breach             │
│                                                                         │
│  Auth gate:  Depends(get_current_user) on every route except           │
│              GET /health  and  POST /api/auth/login                    │
│                                                                         │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │  ROUTES  (backend/main.py — 86KB, ~2100 lines)                  │   │
│  │                                                                  │   │
│  │  Auth      POST /api/auth/login  GET /api/auth/me               │   │
│  │  Triage    POST /api/triage                                      │   │
│  │  Incidents GET|PATCH /api/incidents   GET /api/incidents/{id}   │   │
│  │            POST /api/incidents/{id}/approve|reject|dry-run      │   │
│  │            POST /api/incidents/{id}/remediate|jira              │   │
│  │            GET  /api/incidents/approvals                        │   │
│  │  Infra     POST /api/infra/generate   GET /api/infra/history    │   │
│  │  CI/CD     POST /api/cicd/generate    GET /api/cicd/history     │   │
│  │            GET  /api/cicd/active-runs  GET /api/cicd/dora-metrics│  │
│  │            POST /api/cicd/monitor                               │   │
│  │  Webhooks  POST /api/webhooks/inbound  POST /api/webhooks/logs  │   │
│  │            GET  /api/webhooks/activity                          │   │
│  │  Analytics GET  /api/analytics                                  │   │
│  │  Chat      POST /api/chat                                       │   │
│  │  Logs      POST /api/logs/scan-anomalies                        │   │
│  │  DB        POST /api/db/analyze-query                           │   │
│  │  Notif     GET  /api/notifications                              │   │
│  │            PUT  /api/notifications/{id}/read                    │   │
│  │  Settings  GET|POST /api/settings                               │   │
│  │  Health    GET  /health                                         │   │
│  │  Metrics   GET  /metrics  (Prometheus scrape)                   │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                         │
│  ┌──────────────────────────┐  ┌──────────────────────────────────┐   │
│  │  CommandValidator        │  │  _hitl_evaluate()  asyncio task  │   │
│  │  (command_validator.py)  │  │                                  │   │
│  │  35+ blocklist patterns  │  │  LOW/WARN/MED → auto-resolve     │   │
│  │  Runs twice per incident │  │  HIGH/CRIT   → AWAITING_APPROVAL │   │
│  │  on raw AI output AND    │  │  GUARDRAIL   → ESCALATED_SECURITY│   │
│  │  on final built plan     │  └──────────────────────────────────┘   │
│  └──────────────────────────┘                                          │
│                                                                         │
│  AI Providers (runtime-switchable via AI_PROVIDER env var):            │
│  ┌──────────────────────────┐  ┌──────────────────────────────────┐   │
│  │  Ollama  (local)         │  │  Google Gemini  (cloud)          │   │
│  │  model: gemma3:4b        │  │  model: gemma-3-27b-it           │   │
│  │  AI_PROVIDER=ollama      │  │  AI_PROVIDER=gemini              │   │
│  │  Fully offline           │  │  Needs GEMINI_API_KEY            │   │
│  └──────────────────────────┘  └──────────────────────────────────┘   │
│                                                                         │
│  Specialised Agents:                                                    │
│  security_agent.py → SECURITY_SYSTEM_PROMPT  (Falco, Snyk, Trivy…)   │
│  tester_agent.py   → TESTER_SYSTEM_PROMPT    (Cypress, Jest…)         │
│  main.py default   → SRE_SYSTEM_PROMPT       (all other sources)      │
└───────────┬──────────────────────────────────┬──────────────────────────┘
            │  SQLModel ORM                    │  .delay() via Redis
┌───────────▼─────────────┐        ┌───────────▼──────────────────────────┐
│  PostgreSQL 16           │        │  Celery Worker (celery_worker svc)   │
│  (port 5432)             │        │                                      │
│                          │        │  process_inbound_webhook()           │
│  Tables:                 │◄───────│  process_webhook_log()               │
│  Incident                │        │  monitor_cicd_pipelines()            │
│  InfraRecord             │        │                                      │
│  CICDPipeline            │        │  Fallback: asyncio.create_task()     │
│  Notification            │        │  (when Redis unavailable — dev mode) │
│  WebhookEvent            │        └───────────┬──────────────────────────┘
│  UserSetting             │                    │
│  AuditLog                │        ┌───────────▼──────────────────────────┐
│  User                    │        │  Redis 7  (port 6379)                │
│  LLMConfig               │        │  Celery broker + result backend      │
└─────────────────────────┘        │  Password protected                  │
                                    └──────────────────────────────────────┘

Observability Stack:
┌────────────────────┐    scrapes /metrics    ┌──────────────────┐
│  Prometheus        │◄───────────────────────│  FastAPI backend │
│  (port 9090)       │                        │  INCIDENTS_TOTAL │
└────────┬───────────┘                        │  LLM_LATENCY     │
         │ datasource                         │  ACTIVE_APPROVALS│
┌────────▼───────────┐                        │  GUARDRAIL_BLOCKS│
│  Grafana           │    ┌─────────────────┐ │  HITL_SECONDS    │
│  (port 3002)       │    │  Loki (port3100)│ └──────────────────┘
│  auto-provisioned  │◄───│  log aggregation│
└────────────────────┘    └─────────────────┘

External Integrations (optional, via Settings UI):
  Slack Webhook URL  →  Critical/High alerts + HITL approval notifications
  Jira REST API v3   →  Auto-create Bug tickets from incidents (ADF format)
  ServiceNow         →  Mock ticket-close webhook on agent approval
```

---

## Tech Stack

### Frontend
| Technology | Version | Purpose |
|---|---|---|
| React | 18 | Component-driven SPA |
| Vite | 5 | Build tool with HMR |
| Tailwind CSS | 3 | Utility-first dark-mode design |
| React Router | v6 | Client-side routing, persona portals |
| Recharts | 2 | Bar, Line, Donut analytics charts |
| Lucide React | latest | Consistent icon set |

### Backend
| Technology | Version | Purpose |
|---|---|---|
| FastAPI | 0.110+ | Async Python API + OpenAPI docs |
| Uvicorn | latest | ASGI server |
| SQLModel + SQLAlchemy | latest | Type-safe ORM |
| Pydantic | v2 | Request/response validation |
| python-jose | latest | JWT encoding/decoding |
| passlib + bcrypt | latest | Password hashing |
| slowapi | latest | Per-IP rate limiting |
| httpx | latest | Async HTTP (Slack, Jira) |
| Celery | 5 | Distributed async task queue |
| redis-py | latest | Redis client |
| prometheus-client | latest | Metrics export |

### AI / LLM
| Technology | Purpose |
|---|---|
| Ollama (gemma3:4b) | Local LLM — offline, privacy-preserving |
| Google Gemini (gemma-3-27b-it) | Cloud LLM via `google-genai` |
| Structured JSON prompting | Deterministic, parseable AI output |

### Infrastructure
| Service | Image | Purpose |
|---|---|---|
| PostgreSQL | postgres:16-alpine | Primary relational database |
| Redis | redis:7-alpine | Celery broker + result backend |
| Prometheus | prom/prometheus:v2.52.0 | Metrics collection |
| Grafana | grafana/grafana:11.0.0 | Metrics visualisation |
| Loki | grafana/loki:3.0.0 | Log aggregation |

---

## Docker Services

All 8 services defined in `docker-compose.yml`. All share `app-network` (bridge). [cite:313]

| Service | Port | Image | Depends On | Purpose |
|---|---|---|---|---|
| `postgres` | 5432 | postgres:16-alpine | — | Primary DB with SCRAM-SHA-256 auth |
| `redis` | 6379 | redis:7-alpine | — | Celery broker, password-protected |
| `backend` | 8000 | ./backend Dockerfile | postgres ✅, redis ✅ | FastAPI API server |
| `celery_worker` | — | ./backend Dockerfile | postgres ✅, redis ✅ | Async task processor |
| `frontend` | 5173 | node:20-alpine | backend | Vite dev server |
| `prometheus` | 9090 | prom/prometheus:v2.52.0 | backend | Scrapes /metrics every 15s |
| `grafana` | 3002 | grafana/grafana:11.0.0 | prometheus | Dashboard UI |
| `loki` | 3100 | grafana/loki:3.0.0 | — | Log shipping |

**Security applied to all services:**
- `security_opt: [no-new-privileges:true]`
- `read_only: true` filesystem
- `tmpfs: [/tmp]` only (no `/app`)
- Health checks on postgres and redis with `condition: service_healthy`

---

## File-by-File Guide

### Backend

#### `backend/main.py` (86 KB — core of the entire system)
The FastAPI application entry point. Contains:
- App factory, lifespan event (DB readiness polling + migrations + admin seed)
- All 3 middleware registrations (CORS, security headers, rate limiter)
- Every API route handler (~40 endpoints)
- `_run_triage()` — AI call → parse → save → notify → spawn HITL task
- `_hitl_evaluate()` — async agent brain: auto-resolve vs approval routing
- `_build_db_remediation_plan()` — SQL/CLI plans for database incidents
- `parse_json_response()` — strips markdown fences, extracts JSON, normalises fields
- `call_ollama()` / `call_gemini()` — AI provider wrappers
- `SYSTEM_PROMPT` — main SRE/DevOps triage prompt (8 structured JSON fields)
- Slack alert sender, ServiceNow mock closer, Jira ticket creator

#### `backend/auth.py` (16 KB)
All authentication and authorisation logic:
- `create_access_token()` / `verify_token()` — JWT encode/decode with python-jose
- `get_current_user()` — FastAPI dependency injected on every protected route
- `get_password_hash()` / `verify_password()` — bcrypt via passlib
- `write_audit()` — writes AuditLog entry on every approve/reject/escalation
- `seed_default_admin()` — creates admin user from env vars on first boot
- `seed_default_llm_config()` — seeds default LLM settings row
- `auth_router` — mounts `/api/auth/login`, `/api/auth/me`, user management routes

#### `backend/database.py` (19 KB)
SQLModel table definitions and all CRUD helpers:
- **Tables:** `Incident`, `InfraRecord`, `CICDPipeline`, `Notification`, `WebhookEvent`, `UserSetting`, `AuditLog`, `User`, `LLMConfig`
- `create_db_and_tables()` — runs migrations on startup
- `save_incident()` / `get_all_incidents()` / `update_incident_status()` / `serialize_incident()`
- `save_infra()` / `save_cicd()` / `get_settings()` / `update_settings()`
- `create_notification()` / `get_all_notifications()` / `mark_notification_read()`
- `save_webhook_event()` / `update_webhook_event()` / `get_recent_webhook_events()`
- `get_pending_approvals()` — returns AWAITING_APPROVAL + ESCALATED incidents
- `_is_sqlite` flag — enables zero-config local dev without PostgreSQL

#### `backend/tasks.py` (7 KB)
Celery task definitions:
- `process_inbound_webhook(payload, source, event_id)` — normalises any vendor payload, calls `_run_triage()`, updates webhook event status
- `process_webhook_log(log_text, source)` — direct log ingestion → triage
- `monitor_cicd_pipelines()` — scans mock active pipelines, creates incidents on failures, routes by stage to owner_role

#### `backend/worker.py` (1.4 KB)
Celery app factory:
- Creates `celery_app` with Redis broker and result backend from env vars
- Sets `task_serializer=json`, `result_expires=3600`
- Autodiscovers tasks from `backend.tasks`

#### `backend/command_validator.py` (6.6 KB)
AI Safety Guardrail:
- `CommandValidator.validate(items: list[str])` — iterates every string against 35+ regex blocklist patterns
- Returns `ValidationResult(safe: bool, violations: list[str])`
- Called twice per incident: once on raw AI output, once on the final remediation plan
- Categories: filesystem destruction, permission escalation, destructive SQL, firewall nukes, credential exfiltration, container/cluster nukes, cloud nukes

#### `backend/agents/security_agent.py`
- `SECURITY_SYSTEM_PROMPT` — specialised prompt for security events (CVEs, intrusions, secrets exposure)
- `is_security_source(source)` — returns True for: falco, snyk, trivy, semgrep, waf, siem, crowdstrike, etc.
- Forces severity to minimum "High" for all security-sourced incidents

#### `backend/agents/tester_agent.py`
- `TESTER_SYSTEM_PROMPT` — specialised prompt for test failures (flaky tests, coverage drops, regression)
- `is_tester_source(source)` — returns True for: cypress, playwright, jest, testRail, selenium, etc.

#### `backend/executor/safe_executor.py`
- `safe_executor.dry_run(commands)` — simulates command execution without running anything
- Returns mock terminal output for the approve/dry-run UI flow

#### `backend/observability/metrics.py`
Prometheus counters and histograms:
- `INCIDENTS_TOTAL` — Counter, labels: severity, source, outcome
- `LLM_LATENCY_SECONDS` — Histogram, labels: provider
- `AGENT_CONFIDENCE` — Histogram (0.0–1.0)
- `GUARDRAIL_BLOCKS_TOTAL` — Counter
- `ACTIVE_APPROVALS` — Gauge (increments on AWAITING, decrements on approve/reject)
- `HITL_APPROVAL_SECONDS` — Histogram (time from incident creation to decision)
- `make_asgi_app()` — mounts Prometheus ASGI app at `/metrics`

#### `backend/observability/logger.py`
- Structured JSON logger using Python `logging`
- All log lines include timestamp, level, message, and extra dict fields

#### `backend/webhooks/security.py`
- `require_valid_signature(request)` — FastAPI dependency
- Validates HMAC-SHA256 `X-Hub-Signature-256` header on inbound webhooks
- Returns 401 if secret configured but signature missing/invalid

#### `backend/requirements.txt`
Core dependencies: `fastapi`, `uvicorn`, `sqlmodel`, `psycopg2-binary`, `celery[redis]`, `redis`, `python-jose[cryptography]`, `passlib[bcrypt]`, `slowapi`, `httpx`, `google-genai`, `ollama`, `prometheus-client`, `python-dotenv`, `pydantic`

#### `backend/Dockerfile`
- Base: `python:3.12-slim`
- Installs requirements, copies backend package, exposes 8000
- CMD: `uvicorn backend.main:app --host 0.0.0.0 --port 8000`

---

### Frontend

#### `src/main.jsx`
React app entry point. Wraps `<App>` with `<AuthProvider>` and `<RoleProvider>` context providers.

#### `src/App.jsx` (10 KB)
Top-level routing and layout:
- React Router `<Routes>` — maps `/`, `/ops`, `/developer`, `/data`, `/database`
- `<ProtectedRoute>` — redirects to `/login` if no valid JWT
- Notification navigation: fetches incident by ID and navigates to correct portal on bell click
- Error logging: `.catch((err) => console.error('Failed to navigate to incident:', err))`

#### `src/contexts/AuthContext.jsx`
Global auth state:
- Stores `token`, `user` in localStorage
- `authFetch(url, options)` — wraps `fetch()` with Bearer token injection, calls `logout()` on 401
- `login(username, password)` — POSTs to `/api/auth/login`, stores JWT
- `logout()` — clears localStorage, redirects to `/login`
- `isTokenExpired(token)` — decodes JWT payload, checks `exp` field

#### `src/contexts/RoleContext.jsx`
Global RBAC state:
- Stores `currentRole` (defaults to user's assigned role)
- `setRole(role)` — allows Admin to switch persona via PersonaSwitcher
- Consumed by portals, sidebars, and approval widgets for conditional rendering

#### `src/components/LoginPage.jsx`
- Login form — username + password
- Calls `authFetch` on submit, stores token via `AuthContext.login()`
- Redirects to `/ops` on success

#### `src/components/OpsPortal.jsx`
Admin + NetworkEngineer landing. Renders:
- `DashboardView` (default)
- `TriageView`, `InfraBuilderView`, `CICDView`
- `IntegrationsPage`, `AgentApprovalsWidget`

#### `src/components/DeveloperPortal.jsx`
Developer landing. Renders:
- `DeploymentsView`, `LivePipelinesView`, `RunbooksView`
- `AgentApprovalsWidget` (filters to Developer role)

#### `src/components/DataEngineerPortal.jsx`
DataEngineer landing. Renders:
- `DashboardView` (pipeline health variant)
- `StorageView`, `DataLineageView`

#### `src/components/DatabasePortal.jsx`
DatabaseDeveloper landing. Renders:
- Database health metrics card
- `QueryAnalyzerView`, `SchemaBrowserView`
- `AgentApprovalsWidget` (filters to DatabaseDeveloper role)

#### `src/components/DashboardView.jsx`
Main analytics dashboard:
- Fetches `GET /api/analytics` — severity donut, source bar chart, 7-day trend line
- DORA KPI cards (Deployment Freq, Lead Time, CFR, MTTR)
- Run Predictive Log Scan button → `POST /api/logs/scan-anomalies`

#### `src/components/TriageView.jsx`
AI alert triage interface:
- Textarea for raw log input
- Calls `POST /api/triage`
- Renders `IncidentReportCard` with structured results

#### `src/components/IncidentReportCard.jsx`
Full incident display card:
- Shows severity badge, summary, root cause, evidence, action plan, commands, files, validation steps
- Approve / Reject / Dry Run buttons (shown only when `currentRole === incident.owner_role`)
- Red ESCALATED_SECURITY_RISK banner when guardrail triggered
- Create Jira Ticket button → `POST /api/incidents/{id}/jira`

#### `src/components/AgentApprovalsWidget.jsx`
HITL approval queue:
- Fetches `GET /api/incidents/approvals`
- Filters by `currentRole === incident.owner_role` (canAct check)
- Approve → `POST /api/incidents/{id}/approve`
- Reject → `POST /api/incidents/{id}/reject`
- Dry Run → `POST /api/incidents/{id}/dry-run` → shows command preview modal

#### `src/components/InfraBuilderView.jsx`
Terraform + CLI generator:
- `POST /api/infra/generate` with provider (AWS/GCP/Azure/DigitalOcean) + prompt
- Renders HCL + CLI commands with syntax highlighting

#### `src/components/CICDView.jsx`
CI/CD pipeline YAML generator:
- `POST /api/cicd/generate` with tool (GitHub Actions/GitLab CI/Jenkins) + description
- Auth: uses `authFetch` (fixed in commit `adcd8556`)

#### `src/components/LivePipelinesView.jsx`
Real-time CI/CD monitoring:
- Fetches `GET /api/cicd/active-runs` (polls every 30s)
- Renders pipeline DAG: Build → Test → Security Scan → Deploy
- Stage spinners on active stages
- Run Monitor Scan button → `POST /api/cicd/monitor`

#### `src/components/DeploymentsView.jsx`
Deployment history for Developer role:
- Filter by environment (prod/staging/dev)
- Trigger deploy, view logs drawer, rollback button (mock)

#### `src/components/RunbooksView.jsx`
Executable runbook library:
- Filter by category (Incident Response, Security, Database, Infra)
- Step-by-step terminal simulation on run

#### `src/components/StorageView.jsx`
Storage analytics for DataEngineer:
- Bucket usage cards, cost breakdown bar chart, MoM trend sparklines

#### `src/components/DataLineageView.jsx`
Interactive data lineage graph:
- SVG DAG: Sources → Transforms → Destinations → Consumers
- Click nodes to highlight upstream/downstream dependencies

#### `src/components/QueryAnalyzerView.jsx`
AI-powered SQL analyzer:
- `POST /api/db/analyze-query` with SQL + database type
- Returns: `is_valid`, `issues`, `index_recommendations`, `estimated_cost`, `rewritten_query`, `explain_plan`

#### `src/components/SchemaBrowserView.jsx`
Database schema explorer:
- Table list with search, column details, PK/FK badges
- Copy DDL to clipboard

#### `src/components/ChatBot.jsx`
Floating SRE assistant (FAB button):
- `POST /api/chat` with message + context (live incident counts, recent activity)
- Grounded on real-time data from `_build_context()`

#### `src/components/HistoryPanel.jsx`
Slide-out history sidebar:
- Tabs: Alerts, Infra, CI/CD
- Click any row → reloads full record by ID into main view

#### `src/components/NotificationDropdown.jsx`
Bell icon with unread badge:
- Fetches `GET /api/notifications`
- `PUT /api/notifications/{id}/read` on click
- Click incident notification → navigates to correct portal + loads incident

#### `src/components/PersonaSwitcher.jsx`
Admin-only persona switcher:
- Dropdown of all 5 roles
- Updates `RoleContext` → sidebar and approval widgets re-render
- Fixed in commit `91793842`

#### `src/components/Sidebar.jsx`
Role-aware navigation sidebar:
- Reads `currentRole` from RoleContext
- Renders only the modules available for the active persona

#### `src/components/SettingsModal.jsx`
Settings gear modal:
- `GET/POST /api/settings` — Slack webhook URL, Jira config, theme preferences

#### `src/components/IntegrationsPage.jsx`
Integrations management (Admin only):
- Webhook URL display for each source
- Recent Webhook Activity table from `GET /api/webhooks/activity`

#### `src/components/UserMenu.jsx`
Avatar dropdown — shows username, role badge, logout button.

---

### Infrastructure

#### `docker-compose.yml` (5 KB)
Defines all 8 services. Key patterns:
- `x-backend-env` YAML anchor — shared env block reused by `backend` and `celery_worker`
- All backend-facing services use `depends_on: condition: service_healthy`
- PostgreSQL uses SCRAM-SHA-256 auth (`--auth-host=scram-sha-256`)
- Redis password-protected with `requirepass`
- Grafana auto-provisioned from `./grafana/provisioning`

#### `prometheus/prometheus.yml`
Prometheus scrape config:
- Scrapes `backend:8000/metrics` every 15 seconds
- Retention: 15 days (`--storage.tsdb.retention.time=15d`)

#### `grafana/provisioning/`
Grafana auto-provisioning:
- Datasource: Prometheus + Loki pre-configured
- Dashboard JSONs auto-loaded on container start

#### `backend/.env.example`
Template for all required environment variables (copy to `backend/.env`).

#### `.gitignore`
Ignores: `node_modules/`, `dist/`, `*.pyc`, `__pycache__/`, `backend/.env`, `.env`, `*.db`

---

## Getting Started

### Prerequisites
- Docker Desktop (recommended) **or** Python 3.12+, Node 20+, PostgreSQL 16, Redis 7

### Option A — Docker Compose (recommended, 3 commands)

```bash
git clone https://github.com/rohithkhannanukala1990-cell/Platform-assistant-portal.git
cd Platform-assistant-portal
cp backend/.env.example backend/.env
# Edit backend/.env — set AI_PROVIDER + credentials
docker compose up --build
```

**All 8 services start automatically.**

### Service URLs

| Service | URL | Credentials |
|---|---|---|
| React Frontend | http://localhost:5173 | — |
| FastAPI Backend | http://localhost:8000 | — |
| API Docs (Swagger) | http://localhost:8000/docs | — |
| Prometheus Metrics | http://localhost:8000/metrics | — |
| Prometheus UI | http://localhost:9090 | — |
| Grafana | http://localhost:3002 | admin / `GRAFANA_PASSWORD` |
| Loki | http://localhost:3100 | — |
| PostgreSQL | localhost:5432 | postgres / `POSTGRES_PASSWORD` |
| Redis | localhost:6379 | password: `REDIS_PASSWORD` |

### Option B — Local Development

```bash
# Terminal 1 — Backend
cd backend && pip install -r requirements.txt
cp .env.example .env   # fill in secrets
uvicorn backend.main:app --reload

# Terminal 2 — Celery Worker
cd backend
celery -A backend.worker.celery_app worker --loglevel=info --concurrency=2

# Terminal 3 — Frontend
npm install && npm run dev
```

---

## Environment Variables

Full `backend/.env` reference:

```env
# ── AI Provider ─────────────────────────────────
AI_PROVIDER=ollama            # "ollama" (local) or "gemini" (cloud)
GEMINI_API_KEY=               # Required if AI_PROVIDER=gemini
OLLAMA_URL=http://localhost:11434
OLLAMA_MODEL=gemma3:4b

# ── JWT Auth ────────────────────────────────────
JWT_SECRET_KEY=change-me-to-a-long-random-string
JWT_EXPIRE_MINUTES=480

# ── Admin User ──────────────────────────────────
DEFAULT_ADMIN_USERNAME=admin
DEFAULT_ADMIN_PASSWORD=Admin123!   # Change in production!

# ── Database ────────────────────────────────────
DATABASE_URL=postgresql://postgres:postgres123@localhost:5432/aiops
POSTGRES_PASSWORD=postgres123

# ── Celery / Redis ──────────────────────────────
CELERY_BROKER_URL=redis://:redis123@localhost:6379/0
CELERY_RESULT_BACKEND=redis://:redis123@localhost:6379/0
REDIS_PASSWORD=redis123

# ── Observability ───────────────────────────────
GRAFANA_PORT=3002
GRAFANA_PASSWORD=admin123

# ── Optional Integrations ───────────────────────
SLACK_WEBHOOK_URL=
JIRA_DOMAIN=
JIRA_EMAIL=
JIRA_API_TOKEN=
JIRA_PROJECT_KEY=
```

---

## Implementation Steps

Complete end-to-end verification. Run after `docker compose up --build`.

### Step 1 — Health check
```bash
curl http://localhost:8000/health
# Expected: {"status": "ok"}
```
Confirm http://localhost:5173 loads the Login page.

### Step 2 — Login and get JWT
```bash
curl -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "Admin123!"}'
# Expected: {"access_token": "eyJ...", "token_type": "bearer"}
```
Save the token — all steps below require it. In the UI, log in at http://localhost:5173.

### Step 3 — Verify auth protection
```bash
# Without token → 401
curl http://localhost:8000/api/incidents

# With token → 200
curl -H "Authorization: Bearer YOUR_TOKEN" http://localhost:8000/api/incidents
```

### Step 4 — AI Alert Triage
```bash
curl -X POST http://localhost:8000/api/triage \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"logs": "FATAL: PostgreSQL max_connections reached. Active: 500/500. New connections rejected."}'
```
Confirm response has all 8 fields: `severity`, `summary`, `root_cause`, `evidence`, `action_plan`, `commands`, `files_to_check`, `validation_steps`.

### Step 5 — Webhook log ingestion
```bash
curl -X POST http://localhost:8000/api/webhooks/logs \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"source": "prod-server", "log_text": "CRITICAL: OOMKiller activated on auth-service pod"}'
# Expected: 202 Accepted + task_id
```
Check Celery worker logs: `docker compose logs celery_worker`

### Step 6 — Inbound webhook routing
```bash
# GitHub → Developer role
curl -X POST http://localhost:8000/api/webhooks/inbound \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"source": "github", "payload": {"message": "Deploy failed on main — build exit 1"}}'

# PostgreSQL → DatabaseDeveloper role
curl -X POST http://localhost:8000/api/webhooks/inbound \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"source": "postgresql", "payload": {"message": "deadlock detected on table orders"}}'
```
Check `GET /api/webhooks/activity` to confirm routing.

### Step 7 — HITL approval flow
1. Create a Critical incident via triage (use a multi-service crash log)
2. `GET /api/incidents/approvals` — confirms `AWAITING_APPROVAL` status
3. In UI: Switch persona to **Developer** → open **Agent Pending Approvals**
4. Approve → `RESOLVED_BY_AGENT` + `agent_execution_logs`
5. Reject → `REJECTED` + audit log entry

### Step 8 — AI Safety Guardrail
Create an incident where AI would generate destructive commands. Confirm:
- Status: `ESCALATED_SECURITY_RISK`
- Remediation plan cleared (empty array)
- CRITICAL notification in bell
- Red banner in UI, no approve/reject buttons

### Step 9 — Persona switching (Admin)
1. Login as admin → http://localhost:5173/ops
2. Click avatar → **Switch Persona**
3. Cycle through: Developer → `/developer`, DataEngineer → `/data`, DatabaseDeveloper → `/database`
4. Confirm sidebar modules change per persona (fixed in commit `91793842`)

### Step 10 — Analytics dashboard
```bash
curl -H "Authorization: Bearer YOUR_TOKEN" http://localhost:8000/api/analytics
```
In UI: Dashboard shows severity donut, top sources bar, 7-day trend. Create more incidents → refresh → charts update.

### Step 11 — Infra Builder
In UI: **Infra Builder** → select AWS → enter "Redis cluster with 3 nodes". Confirm Terraform HCL + AWS CLI commands in response. Check History → Infra tab.

### Step 12 — CI/CD Generator
In UI: **CI/CD Pipeline** → select GitHub Actions → enter "Node.js API with Docker build and staging deploy". Confirm YAML with build/test/deploy stages. (Auth fixed in commit `adcd8556`)

### Step 13 — Live Pipelines + CI/CD Monitor
```bash
curl -H "Authorization: Bearer YOUR_TOKEN" http://localhost:8000/api/cicd/active-runs
curl -X POST -H "Authorization: Bearer YOUR_TOKEN" http://localhost:8000/api/cicd/monitor
```
In UI (Developer portal → **Live Pipelines**): pipeline DAG with stage spinners. DORA KPI row on Dashboard.

### Step 14 — Database portal
Switch to **DatabaseDeveloper** → `/database`:
1. DB Health metrics card renders
2. **Query Analyzer** → paste `SELECT * FROM orders WHERE created_at > '2024-01-01'` → Analyze
3. Confirm `index_recommendations` suggests index on `created_at`
4. **Schema Browser** → search "orders" → inspect columns

### Step 15 — Platform Assistant Chatbot
Click the floating chat button → ask "How many open incidents are there?" Confirm answer references live count from `_build_context()`.

### Step 16 — Notifications
1. Create a High or Critical incident
2. Bell icon shows unread badge
3. Click notification → navigates to correct portal + loads incident
4. Badge clears after read

### Step 17 — Predictive anomaly scan
In Dashboard: **Run Predictive Log Scan** → waits ~3s → new WARNING incident with memory-leak evidence and action plan.

### Step 18 — Data Engineer portal
Switch to **DataEngineer** → `/data`:
1. **Storage** — bucket cards, cost breakdown, MoM trends
2. **Data Lineage** — click DAG nodes, confirm upstream highlight

### Step 19 — Prometheus metrics
```bash
curl http://localhost:8000/metrics | grep -E '(incidents_total|active_approvals|llm_latency|guardrail)'
```
Open http://localhost:9090 → query `incidents_total` → see counters.

### Step 20 — Grafana dashboards
Open http://localhost:3002 → login (admin / `GRAFANA_PASSWORD`). Confirm Prometheus datasource auto-configured. View pre-provisioned AIOps dashboard.

### Step 21 — Celery resilience test
```bash
docker compose stop redis
# Fire a webhook — should fall back to asyncio.create_task()
curl -X POST http://localhost:8000/api/webhooks/logs \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"source": "test", "log_text": "disk full on /var/log"}'
# Expect: 202 with task_id, incident still created
docker compose start redis
```

---

## API Reference

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| POST | `/api/auth/login` | ❌ | Get JWT token |
| GET | `/api/auth/me` | ✅ | Get current user info |
| GET | `/health` | ❌ | Liveness check — `{"status":"ok"}` |
| GET | `/metrics` | ❌ | Prometheus scrape endpoint |
| POST | `/api/triage` | ✅ | Run AI log triage |
| GET | `/api/incidents` | ✅ | List incidents (RBAC-filtered by role param) |
| GET | `/api/incidents/{id}` | ✅ | Get single incident |
| GET | `/api/incidents/approvals` | ✅ | HITL queue (AWAITING + ESCALATED) |
| POST | `/api/incidents/{id}/approve` | ✅ | Approve agent execution |
| POST | `/api/incidents/{id}/reject` | ✅ | Reject agent plan |
| POST | `/api/incidents/{id}/dry-run` | ✅ | Preview commands (no execution) |
| POST | `/api/incidents/{id}/remediate` | ✅ | Execute automated runbook |
| POST | `/api/incidents/{id}/jira` | ✅ | Create Jira Bug ticket |
| POST | `/api/infra/generate` | ✅ | Generate Terraform + CLI |
| GET | `/api/infra/history` | ✅ | Infra generation history |
| POST | `/api/cicd/generate` | ✅ | Generate CI/CD pipeline YAML |
| GET | `/api/cicd/history` | ✅ | Pipeline generation history |
| GET | `/api/cicd/active-runs` | ✅ | Live pipeline run statuses |
| GET | `/api/cicd/dora-metrics` | ✅ | DORA KPIs (mock — live integration pending) |
| POST | `/api/cicd/monitor` | ✅ | Dispatch CI/CD monitor Celery task |
| GET | `/api/analytics` | ✅ | Aggregated dashboard metrics |
| POST | `/api/webhooks/inbound` | ✅ | Inbound webhook gateway (202 + Celery) |
| POST | `/api/webhooks/logs` | ✅ | Raw log ingestion (202 + Celery) |
| GET | `/api/webhooks/activity` | ✅ | Recent webhook event feed |
| POST | `/api/logs/scan-anomalies` | ✅ | Predictive anomaly detection |
| POST | `/api/db/analyze-query` | ✅ | AI SQL EXPLAIN + index + rewrite |
| POST | `/api/chat` | ✅ | Context-aware SRE chatbot |
| GET | `/api/notifications` | ✅ | All notifications |
| PUT | `/api/notifications/{id}/read` | ✅ | Mark notification as read |
| GET | `/api/settings` | ✅ | Get user preferences |
| POST | `/api/settings` | ✅ | Update user preferences |

---

## Webhook Gateway

Send events from any tool — the gateway normalises the payload and routes to the correct role automatically.

### Source → Role Routing

| Source Keywords | Routed To |
|---|---|
| github, gitlab, jira, cypress, playwright, jest, sentry, sonarqube, snyk | Developer |
| airflow, snowflake, dbt, kafka, spark, fivetran | DataEngineer |
| aws, datadog, pagerduty, cloudwatch, prometheus, alertmanager, grafana, kubernetes, falco | NetworkEngineer |
| rds, mongodb, postgresql, mysql, redis, clickhouse, elasticsearch, sqlite | DatabaseDeveloper |

### curl Examples

```bash
# GitHub CI failure → Developer
curl -X POST http://localhost:8000/api/webhooks/inbound \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"source": "github", "payload": {"message": "Build failed on main — exit code 1"}}'

# PostgreSQL deadlock → DatabaseDeveloper
curl -X POST http://localhost:8000/api/webhooks/inbound \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"source": "postgresql", "payload": {"message": "deadlock detected on table orders"}}'

# Prometheus alert → NetworkEngineer
curl -X POST http://localhost:8000/api/webhooks/inbound \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"source": "prometheus", "payload": {"alerts": [{"annotations": {"summary": "High CPU on node-01"}}]}}'

# Raw log ingestion
curl -X POST http://localhost:8000/api/webhooks/logs \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"source": "prod-server", "log_text": "CRITICAL: OOMKiller activated on auth-service"}'
```

---

## HITL Agentic Flow

```
New Incident created (manual triage OR webhook OR anomaly scan)
    │
    ▼
_run_triage() → AI call → parse_json_response() → save_incident()
    │
    └── asyncio.create_task(_hitl_evaluate())
                │
         Security source?
         YES → force severity = "High"
                │
                ▼
         CommandValidator.validate(raw AI commands + action_plan)
                │
         ┌──────┴──────┐
       SAFE          UNSAFE
         │               │
         │        ESCALATED_SECURITY_RISK
         │        ├─ plan cleared (empty arrays)
         │        ├─ CRITICAL notification
         │        ├─ write_audit("ESCALATED")
         │        └─ GUARDRAIL_BLOCKS_TOTAL.inc()
         │
    severity LOW / WARN / MEDIUM
         │
         ├── safe_executor.dry_run(commands)
         ├── update status → RESOLVED_BY_AGENT
         ├── save agent_execution_logs
         └── INCIDENTS_TOTAL.labels(outcome="auto_resolved").inc()
         │
    severity HIGH / CRITICAL
         │
         ├── _build_db_remediation_plan()   (if DatabaseDeveloper source)
         │   OR action_plan + commands from AI (other roles)
         │
         ├── CommandValidator.validate(final_plan)  ← second guardrail pass
         │
         ├── update status → AWAITING_APPROVAL
         ├── ACTIVE_APPROVALS.inc()
         ├── create_notification(type="critical", HITL alert)
         └── _mock_hitl_slack_notify() → Slack to owner_role team
                │
         Human reviews in AgentApprovalsWidget
                │
         ┌──────┴──────┐
      Approve        Reject
         │               │
   RESOLVED_BY_AGENT   REJECTED
   agent_execution_logs write_audit("REJECTED")
   write_audit("APPROVED") ACTIVE_APPROVALS.dec()
   HITL_APPROVAL_SECONDS.observe()
   ACTIVE_APPROVALS.dec()
   _close_servicenow_ticket() (background task)
```

---

## AI Safety Guardrail

`CommandValidator` (in `backend/command_validator.py`) scans every AI-generated string before any plan reaches a human approver or executor.

| Category | Blocked Patterns (examples) |
|---|---|
| Filesystem destruction | `rm -rf`, `mkfs`, `dd if=`, `shred`, `wipefs` |
| Permission escalation | `chmod 777`, `sudo su`, `sudo -i`, `chown root` |
| Destructive SQL | `DROP TABLE`, `TRUNCATE`, `DELETE FROM` (no WHERE), `DROP DATABASE` |
| Firewall nukes | `iptables -F`, `ufw disable`, `firewall-cmd --panic` |
| Credential exfiltration | `curl \| bash`, `cat /etc/shadow`, `wget \| sh` |
| Container/cluster nukes | `kubectl delete namespace`, `docker system prune -a`, `helm uninstall` |
| Cloud nukes | `aws s3 rm --recursive`, `az group delete`, `gcloud projects delete` |

On violation: status → `ESCALATED_SECURITY_RISK`, plan wiped, CRITICAL notification, audit log written, `GUARDRAIL_BLOCKS_TOTAL` Prometheus counter incremented.

---

## Role-Based Portals

| Role | Route | Portal Component | Modules Available |
|---|---|---|---|
| Admin | `/ops` | OpsPortal | ALL modules + PersonaSwitcher |
| Network Engineer | `/ops` | OpsPortal | Dashboard, Triage, Infra Builder, CI/CD, Integrations |
| Developer | `/developer` | DeveloperPortal | Deployments, Live Pipelines, Runbooks, Approvals |
| Data Engineer | `/data` | DataEngineerPortal | Pipeline Health, Storage, Data Lineage |
| Database Developer | `/database` | DatabasePortal | DB Health, Query Analyzer, Schema Browser, Approvals |

RBAC is enforced at **two layers**:
1. Backend: `GET /api/incidents?role=Developer` filters `owner_role` server-side
2. Frontend: `canAct = currentRole === incident.owner_role` controls approve/reject visibility in `AgentApprovalsWidget`

---

## What's Next

| Priority | Item | Effort |
|---|---|---|
| 🔴 Critical | `pytest` unit + integration tests (CommandValidator, parse_json_response, auth endpoints) | 4–6 hrs |
| 🔴 Critical | GitHub Actions CI workflow (lint → type-check → test on every PR) | 2 hrs |
| 🟠 High | Rate limit `POST /api/auth/login` (brute-force protection) | 30 min |
| 🟠 High | Nginx reverse proxy container with TLS/HTTPS termination | 4 hrs |
| 🟠 High | Wire `GET /api/cicd/dora-metrics` to live GitHub Actions API | 6 hrs |
| 🟡 Medium | Real command execution (Docker-in-Docker sandbox) replacing mock dry-run | 1–2 days |
| 🟡 Medium | Kubernetes Helm chart for staging/production cluster deployment | 1 day |
| 🟡 Medium | GCP Cloud Run + Cloud SQL + Upstash Redis production deployment | 1 day |
| 🟡 Medium | Secret rotation via HashiCorp Vault or AWS Secrets Manager | 4 hrs |
| 🟢 Low | Multi-tenant RBAC (org-level incident scoping) | 2 days |
| 🟢 Low | Audit log viewer UI (write_audit entries are saved, no frontend yet) | 4 hrs |
| 🟢 Low | Webhook replay endpoint (re-triage failed events without re-sending) | 2 hrs |
