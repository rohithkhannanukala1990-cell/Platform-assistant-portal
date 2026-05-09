# AIOps Platform Engineering Assistant

> An enterprise-grade, AI-powered Internal Developer Portal (IDP) that unifies alert triage, infrastructure generation, CI/CD automation, agentic remediation workflows, and real-time analytics — all in a single dark-mode dashboard.

Built to demonstrate production-grade platform engineering: local/cloud LLM orchestration, role-based access control, Human-in-the-Loop agent flows, AI safety guardrails, async task queues, and a fully containerised PostgreSQL + Redis + Celery stack.

---

## Contents

| Section | Description |
|---------|-------------|
| [Feature Overview](#feature-overview) | All 23 phases at a glance |
| [Tech Stack](#tech-stack) | Frontend, backend, AI, infra |
| [Architecture](#architecture) | Full system diagram with all layers |
| [Security Hardening](#security-hardening) | Auth, headers, guardrails, Docker hardening |
| [Role-Based Portals](#role-based-portals) | Routes and modules per persona |
| [HITL Agentic Flow](#hitl-agentic-flow) | Approval vs auto-resolve |
| [AI Safety Guardrail](#ai-safety-guardrail) | `CommandValidator` blocklist |
| [Project Structure](#project-structure) | Repo layout |
| [Getting Started](#getting-started) | Docker Compose & local dev |
| [Implementation Steps](#implementation-steps) | Step-by-step checklist (Phases 1–23) |
| [Key API Endpoints](#key-api-endpoints) | REST reference |
| [Webhook Gateway](#webhook-gateway) | Sources, routing, curl examples |

---

## Feature Overview

| Phase | What Was Built |
|---|---|
| 1 | Core AI Alert Triage engine with structured JSON output |
| 2 | SQLite persistence, universal History sidebar, Settings modal |
| 3 | Infra Builder (multi-cloud Terraform), CI/CD Pipeline Generator |
| 4 | Slack ChatOps, Jira ticket creation, Notification bell |
| 5 | Automated webhook log ingestion (`POST /api/webhooks/logs`) |
| 6 | Recharts Analytics Dashboard (severity donut, source bar, trend line) |
| 7 | Automated Runbooks — simulate execution, save terminal logs |
| 8 | Platform Assistant Chatbot (context-aware SRE assistant) |
| 9 | Persona-based role portals with React Router + RBAC |
| 10 | Log Anomaly Detection (`POST /api/logs/scan-anomalies`) |
| 11 | Asynchronous Webhook Gateway with auto-routing by source |
| 12 | Human-in-the-Loop (HITL) Agentic Execution Flow |
| 13 | DatabaseDeveloper role + Database Health portal |
| 14 | AI Safety Guardrail (`CommandValidator` — 35+ blocklist patterns) |
| 15 | PostgreSQL migration (from SQLite) + Docker Compose stack |
| 16 | Celery + Redis async task queue for webhook processing |
| 17 | Deployments view — history table, trigger deploy, rollback, live logs |
| 18 | Runbooks view — categorised executable playbooks with step animation |
| 19 | Storage view — bucket usage, cost breakdown, MoM trends |
| 20 | Data Lineage view — interactive SVG DAG (Sources → Transforms → Destinations → Consumers) |
| 21 | Query Analyzer — AI-powered SQL EXPLAIN, index recommendations, rewrite |
| 22 | Schema Browser — table explorer with columns, types, PK/FK badges, DDL copy |
| 23 | Active CI/CD monitoring — live pipeline DAG, DORA KPIs, Celery monitor task, stage-based HITL routing |

---

## Tech Stack

### Frontend
| Technology | Purpose |
|---|---|
| React 18 + Vite | Fast component-driven SPA with HMR |
| Tailwind CSS | Utility-first dark-mode design system |
| Recharts | Responsive analytics charts (Bar, Line, Donut) |
| React Router v6 | Client-side routing, persona-based portals |
| Lucide React | Consistent icon set |

### Backend
| Technology | Purpose |
|---|---|
| FastAPI | Async Python API with automatic OpenAPI docs |
| Uvicorn | ASGI server with hot-reload |
| SQLModel + SQLAlchemy | Type-safe ORM |
| PostgreSQL 16 | Production-ready relational database |
| psycopg2-binary | PostgreSQL driver |
| Celery 5 + Redis 7 | Distributed async task queue |
| slowapi | Per-IP rate limiting middleware |
| Pydantic v2 | Request/response validation |
| httpx | Async HTTP client (Slack, Jira, ServiceNow) |
| python-jose + passlib | JWT auth + bcrypt password hashing |

### AI / LLM
| Technology | Purpose |
|---|---|
| Google Gemini (gemma-3-27b-it) | Cloud LLM via `google-genai` |
| Ollama + Gemma 3 4B | Local LLM — fully offline, privacy-preserving |
| Structured JSON prompting | Deterministic, parseable AI output |

### Infrastructure
| Technology | Purpose |
|---|---|
| Docker Compose | 5-service local stack (frontend, backend, worker, postgres, redis) |
| PostgreSQL 16 | Primary database with health checks |
| Redis 7 | Celery broker + result backend |
| Celery 5 | Distributed task queue with retry logic |
| Prometheus (via `prometheus-fastapi-instrumentator`) | Metrics export at `/metrics` |

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                     React Frontend (Vite · Tailwind · React Router)  │
│                                                                       │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌────────┐  ┌────────┐  │
│  │Dashboard │  │ Triage   │  │  Infra   │  │ CI/CD  │  │  Chat  │  │
│  │Analytics │  │(AI+HITL) │  │ Builder  │  │  Gen   │  │  Bot   │  │
│  └──────────┘  └──────────┘  └──────────┘  └────────┘  └────────┘  │
│                                                                       │
│  Role Portals:  /ops · /developer · /data · /database                │
│  AuthContext:   JWT stored in localStorage, auto-logout on 401       │
└─────────────────────────────┬───────────────────────────────────────┘
                              │  HTTP / REST  (Bearer JWT)
┌─────────────────────────────▼───────────────────────────────────────┐
│                         FastAPI Backend                               │
│                                                                       │
│  Middleware stack (top → bottom):                                     │
│  ① CORSMiddleware  (origin allowlist + regex for localhost dev)      │
│  ② SecurityHeadersMiddleware  (CSP · HSTS · X-Frame · XSS)          │
│  ③ slowapi RateLimiter  (per-IP, 429 on breach)                      │
│                                                                       │
│  Auth layer:  /api/auth/login → JWT  │  Depends(get_current_user)   │
│               on every protected route                               │
│                                                                       │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │  Routes                                                        │   │
│  │  /api/triage   /api/incidents   /api/infra/generate           │   │
│  │  /api/cicd/generate   /api/cicd/active-runs   /api/cicd/dora  │   │
│  │  /api/cicd/monitor    /api/webhooks/inbound                   │   │
│  │  /api/webhooks/logs   /api/webhooks/activity                  │   │
│  │  /api/analytics  /api/chat  /api/logs/scan-anomalies          │   │
│  │  /api/db/analyze-query  /api/notifications  /api/settings     │   │
│  │  /api/incidents/{id}/approve|reject|dry-run|jira|remediate    │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                                                                       │
│  ┌──────────────────────┐   ┌─────────────────────────────────────┐ │
│  │  CommandValidator     │   │  _hitl_evaluate()  (asyncio task)   │ │
│  │  AI Safety Guardrail  │   │  LOW/WARN/MED → RESOLVED_BY_AGENT  │ │
│  │  35+ blocklist rules  │   │  HIGH/CRIT    → AWAITING_APPROVAL  │ │
│  │  Fires on any plan    │   │  GUARDRAIL    → ESCALATED_SECURITY │ │
│  └──────────────────────┘   └─────────────────────────────────────┘ │
│                                                                       │
│  AI Providers (runtime switchable via AI_PROVIDER env var):          │
│  ┌────────────────────────┐   ┌───────────────────────────────────┐ │
│  │  Ollama (local)        │   │  Google Gemini (cloud)            │ │
│  │  gemma3:4b             │   │  gemma-3-27b-it                   │ │
│  │  Fully offline         │   │  Requires GEMINI_API_KEY          │ │
│  └────────────────────────┘   └───────────────────────────────────┘ │
└──────┬──────────────────────────────────┬────────────────────────────┘
       │  SQLModel ORM                    │  .delay()  (Celery)
┌──────▼──────────┐             ┌─────────▼──────────────────────────┐
│  PostgreSQL 16   │             │  Celery Worker                      │
│                  │             │  ┌──────────────────────────────┐  │
│  Incident        │◄────────────│  │ process_inbound_webhook()    │  │
│  InfraRecord     │             │  │ process_webhook_log()        │  │
│  CICDPipeline    │             │  │ monitor_cicd_pipelines()     │  │
│  Notification    │             │  └──────────────────────────────┘  │
│  WebhookEvent    │             │  Fallback: asyncio.create_task()   │
│  UserSetting     │             │  (when Redis unavailable — dev)    │
│  AuditLog        │             └─────────────┬──────────────────────┘
└─────────────────┘                           │
                                   ┌───────────▼──────────┐
                                   │  Redis 7              │
                                   │  Celery broker        │
                                   │  + result backend     │
                                   └──────────────────────┘

External Integrations (optional, configured in Settings):
  Slack Webhook  →  Critical/High alert notifications + HITL approval alerts
  Jira REST API  →  Auto-create Bug tickets from incidents
  ServiceNow     →  Mock ticket-close webhook on agent approval
  Prometheus     →  Metrics at /metrics (INCIDENTS_TOTAL, LLM_LATENCY, ACTIVE_APPROVALS)
```

---

## Security Hardening

All security fixes are applied and committed as of **May 9 2026**.

### Authentication
- Every API route except `/health` and `/api/auth/*` requires a valid JWT via `Depends(get_current_user)`
- `POST /api/webhooks/logs` — JWT required ✅
- `GET /api/webhooks/activity` — JWT required ✅
- `/health` — returns `{"status": "ok"}` only, no provider/model info leaked ✅

### HTTP Security Headers (applied to every response)
| Header | Value |
|---|---|
| `X-Content-Type-Options` | `nosniff` |
| `X-Frame-Options` | `DENY` |
| `X-XSS-Protection` | `1; mode=block` |
| `Strict-Transport-Security` | `max-age=31536000; includeSubDomains` |
| `Content-Security-Policy` | `default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; connect-src 'self' ws: wss:; img-src 'self' data:; font-src 'self' data:` |
| `Referrer-Policy` | `strict-origin-when-cross-origin` |

### Rate Limiting
- `slowapi` enforces per-IP rate limits; returns `429 Too Many Requests` on breach

### Docker Hardening (`docker-compose.yml`)
- All services: `read_only: true`, `security_opt: [no-new-privileges:true]`
- `tmpfs` scoped to `/tmp` only (not `/app`) on backend and celery_worker
- PostgreSQL and Redis have health checks; backend/worker use `depends_on: condition: service_healthy`

### CORS
- Allowlist: `http://frontend:5173` (Docker) + `localhost:517x` regex (dev only)
- Production: disable `allow_origin_regex` via environment variable

### AI Safety Guardrail
- `CommandValidator` scans all AI-generated commands before any plan is queued — see [AI Safety Guardrail](#ai-safety-guardrail)

---

## Role-Based Portals

| Role | Portal Route | Modules |
|---|---|---|
| Admin | `/ops` | Full access to all portals + Persona Switcher + Integrations |
| Network Engineer | `/ops` | Dashboard · Alert Triage · Infra Builder · CI/CD Pipeline |
| Developer | `/developer` | Software Catalog · Deployments · Live Pipelines · Runbooks |
| Data Engineer | `/data` | Pipeline Health · Storage · Data Lineage |
| Database Developer | `/database` | DB Health · Query Analyzer · Schema Browser |

---

## HITL Agentic Flow

```
New Incident (webhook or manual triage)
        │
        ▼
  _hitl_evaluate()
        │
  Security source? ──YES──► force severity = "High"
        │
        ▼
  CommandValidator.validate(commands + action_plan)
        │
   ┌────┴────┐
 SAFE      UNSAFE
   │          │
   │     ESCALATED_SECURITY_RISK
   │     (plan cleared, CRITICAL notification, audit log)
   │
   ├── severity in {Low, Warning, Medium}
   │       └─► Auto-simulate fix
   │           RESOLVED_BY_AGENT + agent_execution_logs
   │
   └── severity in {High, Critical}
           │
           ▼
     Build remediation plan
     (DB role → SQL/CLI plan, others → action_plan + commands)
           │
     CommandValidator.validate(final_plan)   ← second guardrail pass
           │
     AWAITING_APPROVAL
     Slack HITL notification → owner_role team
           │
      [Human reviews in portal]
           │
      ┌────┴────┐
   Approve    Reject
      │          │
  RESOLVED_    REJECTED
  BY_AGENT     (audit logged)
  (audit logged)
```

---

## AI Safety Guardrail

`CommandValidator` scans every AI-generated command and remediation plan **before** it can be queued for execution or shown to an approver.

| Category | Blocked Patterns |
|---|---|
| Filesystem destruction | `rm -rf`, `mkfs`, `dd if=`, `shred`, `wipefs` |
| Permission escalation | `chmod 777`, `sudo su`, `sudo -i`, `chown root` |
| Destructive SQL | `DROP TABLE`, `TRUNCATE`, `DELETE FROM` (no WHERE), `DROP DATABASE` |
| Firewall nukes | `iptables -F`, `ufw disable`, `firewall-cmd --panic` |
| Credential exfiltration | `curl \| bash`, `cat /etc/shadow`, `cat /etc/passwd` |
| Container/cluster nukes | `kubectl delete namespace`, `docker system prune -a`, `helm uninstall` |
| Cloud nukes | `aws s3 rm --recursive`, `az group delete`, `gcloud projects delete` |

On violation → status: `ESCALATED_SECURITY_RISK`, plan cleared, CRITICAL notification, audit log entry saved.

---

## Project Structure

```
Platform-assistant-portal/
├── backend/
│   ├── main.py                    # FastAPI app, all routes, AI orchestration, HITL logic
│   ├── database.py                # SQLModel tables, CRUD helpers, DB migrations
│   ├── auth.py                    # JWT auth, RBAC, audit log, user seed
│   ├── worker.py                  # Celery app factory
│   ├── tasks.py                   # Celery tasks: webhooks + monitor_cicd_pipelines
│   ├── command_validator.py       # AI Safety Guardrail (35+ blocklist patterns)
│   ├── executor/
│   │   └── safe_executor.py       # Dry-run command executor
│   ├── agents/
│   │   ├── security_agent.py      # Security-specific system prompt + source detection
│   │   └── tester_agent.py        # Test/QA-specific system prompt + source detection
│   ├── webhooks/
│   │   └── security.py            # HMAC signature validation for inbound webhooks
│   ├── observability/
│   │   ├── metrics.py             # Prometheus counters/histograms (INCIDENTS_TOTAL, etc.)
│   │   └── logger.py              # Structured JSON logger
│   ├── requirements.txt
│   ├── Dockerfile
│   └── .env.example               # Template — copy to .env and fill in secrets
├── src/
│   ├── App.jsx                    # React Router setup, layout, notification nav
│   ├── contexts/
│   │   ├── AuthContext.jsx        # JWT auth state, authFetch, auto-logout on 401
│   │   └── RoleContext.jsx        # Global role state (RBAC)
│   └── components/
│       ├── DashboardView.jsx
│       ├── TriageView.jsx
│       ├── InfraBuilderView.jsx
│       ├── CICDView.jsx
│       ├── OpsPortal.jsx
│       ├── DeveloperPortal.jsx
│       ├── DeploymentsView.jsx
│       ├── LivePipelinesView.jsx
│       ├── RunbooksView.jsx
│       ├── DataEngineerPortal.jsx
│       ├── StorageView.jsx
│       ├── DataLineageView.jsx
│       ├── DatabasePortal.jsx
│       ├── QueryAnalyzerView.jsx
│       ├── SchemaBrowserView.jsx
│       ├── AgentApprovalsWidget.jsx
│       ├── IntegrationsPage.jsx
│       ├── IncidentReportCard.jsx
│       ├── HistoryPanel.jsx
│       ├── Sidebar.jsx
│       ├── ChatBot.jsx
│       ├── PersonaSwitcher.jsx
│       ├── UserMenu.jsx
│       ├── NotificationDropdown.jsx
│       └── SettingsModal.jsx
├── docker-compose.yml
├── package.json
├── vite.config.js
└── .gitignore
```

---

## Getting Started

### Prerequisites
- Docker Desktop (recommended) **or** Python 3.12+, Node 20+, PostgreSQL 16, Redis 7

### Option A — Docker Compose (recommended)

```bash
# 1. Clone the repo
git clone https://github.com/rohithkhannanukala1990-cell/Platform-assistant-portal.git
cd Platform-assistant-portal

# 2. Copy and fill in secrets
cp backend/.env.example backend/.env
# Edit backend/.env — add GEMINI_API_KEY or set AI_PROVIDER=ollama

# 3. Start everything (5 services)
docker compose up --build
```

Services started:

| Service | URL |
|---|---|
| React frontend | http://localhost:5173 |
| FastAPI backend | http://localhost:8000 |
| API docs (Swagger) | http://localhost:8000/docs |
| Prometheus metrics | http://localhost:8000/metrics |
| PostgreSQL | localhost:5432 |
| Redis | localhost:6379 |

### Option B — Local Development

```bash
# 1. Backend
cd backend
pip install -r requirements.txt
cp .env.example .env          # fill in secrets
uvicorn main:app --reload     # Terminal 1

# 2. Celery worker (requires Redis running locally)
celery -A worker.celery_app worker --loglevel=info --concurrency=2   # Terminal 2

# 3. Frontend
cd ..
npm install
npm run dev                   # Terminal 3
```

### Environment Variables (`backend/.env`)

```env
# AI provider — "gemini" (cloud) or "ollama" (local, default)
AI_PROVIDER=ollama
GEMINI_API_KEY=your_key_here

# Ollama (local LLM)
OLLAMA_URL=http://localhost:11434
OLLAMA_MODEL=gemma3:4b

# JWT
SECRET_KEY=change-me-to-a-long-random-string
ACCESS_TOKEN_EXPIRE_MINUTES=60

# Database
DATABASE_URL=postgresql://postgres:password@localhost:5432/aiops

# Celery / Redis
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/0

# Optional integrations
SLACK_WEBHOOK_URL=
JIRA_DOMAIN=
JIRA_EMAIL=
JIRA_API_TOKEN=
JIRA_PROJECT_KEY=
```

### Default Login

| Username | Password | Role |
|---|---|---|
| `admin` | Set via `ADMIN_PASSWORD` env var | Admin |

---

## Implementation Steps

Use this as an end-to-end verification checklist after completing [Getting Started](#getting-started). Each step maps to the [Feature Overview](#feature-overview) phases.

### Step 1 — Bootstrap & health check

1. Copy `backend/.env.example` → `backend/.env`; set `AI_PROVIDER=gemini` + `GEMINI_API_KEY` **or** `AI_PROVIDER=ollama` with Ollama running locally.
2. Start the stack (`docker compose up --build` or local Option B).
3. Confirm **http://localhost:8000/docs** (OpenAPI) and **http://localhost:5173** (React) both load.
4. Smoke test: `GET http://localhost:8000/health` → `{"status": "ok"}`.

### Step 2 — Login & JWT auth

1. `POST /api/auth/login` with `{"username": "admin", "password": "<ADMIN_PASSWORD>"}`.
2. Copy the returned `access_token` — all subsequent API calls need `Authorization: Bearer <token>`.
3. In the UI, log in via the **Login** screen; confirm the dashboard loads and the user menu shows the active role.

### Step 3 — AI alert triage & persistence (Phases 1–2)

1. `POST /api/triage` with a sample log payload (or use the **Alert Triage** UI).
2. Confirm a structured JSON response: `severity`, `summary`, `root_cause`, `evidence`, `action_plan`, `commands`, `files_to_check`, `validation_steps`.
3. Check **History → Alerts** sidebar; click an entry and confirm the Incident Report Card reloads it.

### Step 4 — Infra Builder & CI/CD Generator (Phase 3)

1. Use **Infra Builder** — enter a prompt and select provider (AWS / GCP / Azure / DigitalOcean).
2. Confirm Terraform HCL + CLI commands in the response; check **History → Infra**.
3. Use **CI/CD Pipeline** — enter app description, choose tool (GitHub Actions / GitLab CI / Jenkins).
4. Confirm YAML + security checks in the response; check **History → CI/CD**.

### Step 5 — Notifications, Slack & Jira (Phase 4)

1. Create a **Critical** or **High** incident; confirm the **notification bell** shows an unread badge.
2. If `SLACK_WEBHOOK_URL` is set, confirm the Slack message fires in your channel.
3. With Jira env vars configured, click **Create Jira Ticket** on an incident and confirm the ticket URL in the response.

### Step 6 — Webhook log ingestion (Phases 5, 16)

```bash
# Requires auth header
curl -X POST http://localhost:8000/api/webhooks/logs \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"source": "prod-server", "log_text": "CRITICAL: OOMKiller activated on auth-service"}'
```

Expect `202 Accepted` + `task_id`. A new incident should appear within seconds.

### Step 7 — Analytics dashboard (Phase 6)

1. Navigate to **Dashboard** (default Ops landing).
2. Confirm severity donut, top sources bar chart, and 7-day trend line match `GET /api/analytics`.
3. Create more incidents and refresh — aggregates update.

### Step 8 — Automated Runbooks (Phase 7)

1. Select an **OPEN** incident → click **Execute Automated Runbook**.
2. After `POST /api/incidents/{id}/remediate` completes, confirm status changes to **RESOLVED** and terminal-style `execution_logs` appear on the card.

### Step 9 — Platform Assistant chatbot (Phase 8)

1. Click the floating chat button (bottom-right FAB).
2. Ask "How many open incidents are there?" — confirm the answer references live data from `_build_context()`.

### Step 10 — RBAC & persona portals (Phase 9)

1. As **Admin**, use **Persona Switcher** to visit `/ops`, `/developer`, `/data`, `/database`.
2. Confirm sidebar modules differ per role.
3. `GET /api/incidents?role=Developer` — confirm only Developer-owned incidents are returned.

### Step 11 — Log anomaly detection (Phase 10)

1. On **Dashboard**, click **Run Predictive Log Scan**.
2. After `POST /api/logs/scan-anomalies` (~3s delay), confirm a new **WARNING** incident appears with memory-leak evidence and action plan.

### Step 12 — Inbound webhook gateway (Phase 11)

```bash
# GitHub → Developer role
curl -X POST http://localhost:8000/api/webhooks/inbound \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"source": "github", "payload": {"action": "push", "message": "Deploy failed on main"}}'

# PostgreSQL → DatabaseDeveloper role
curl -X POST http://localhost:8000/api/webhooks/inbound \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"source": "postgresql", "payload": {"message": "deadlock detected on table orders"}}'
```

Confirm `202` + `routed_to` field reflects correct role. Check `GET /api/webhooks/activity` for the event log.

### Step 13 — HITL agentic approvals (Phase 12)

1. Trigger a **High** or **Critical** incident — HITL evaluator sets status to `AWAITING_APPROVAL`.
2. Open **Agent Pending Approvals** widget on the matching role portal.
3. **Approve** → status becomes `RESOLVED_BY_AGENT` with `agent_execution_logs`.
4. **Reject** → status becomes `REJECTED`; audit log entry created.
5. **Dry Run** → returns command preview without execution.

### Step 14 — DatabaseDeveloper portal (Phase 13)

1. Switch to **Database Developer** persona → `/database`.
2. Confirm **DB Health** metrics card renders.
3. Ingest a PostgreSQL webhook — confirm HITL plan uses SQL/CLI commands (`pg_stat_activity`, `pg_terminate_backend`, etc.) instead of generic action steps.

### Step 15 — AI Safety Guardrail (Phase 14)

1. Manually construct an incident whose `commands` array includes a blocklisted pattern (e.g. `rm -rf /`).
2. Confirm backend sets status to `ESCALATED_SECURITY_RISK`, clears the plan, and raises a `CRITICAL` notification.
3. In the UI, confirm the red **SECURITY RISK** banner and hidden approve/reject controls on that incident.

### Step 16 — PostgreSQL + Docker Compose (Phase 15)

1. With `DATABASE_URL` pointing at Postgres (via Compose or local), restart the backend.
2. Confirm the lifespan event polls until Postgres is ready (`_wait_for_db`), then runs migrations.
3. Omit `DATABASE_URL` to fall back to SQLite for offline dev.

### Step 17 — Celery + Redis (Phase 16)

1. Start Redis and a Celery worker.
2. Fire webhook endpoints — confirm tasks appear in worker stdout.
3. Stop Redis — confirm FastAPI falls back to `asyncio.create_task()` (dev resilience).

### Step 18 — Developer portal: Deployments & Runbooks (Phases 17–18)

1. **Deployments** — filter by environment, trigger a deploy, open the log drawer, try rollback.
2. **Runbooks** — filter by category, run a playbook, watch the step-by-step terminal animation.

### Step 19 — Data Engineer portal: Storage & Lineage (Phases 19–20)

1. **Storage** — review bucket cards, cost bars, and MoM trend sparklines.
2. **Data Lineage** — click DAG nodes; confirm upstream/downstream highlight on the SVG graph.

### Step 20 — Database portal: Query Analyzer & Schema Browser (Phases 21–22)

1. **Query Analyzer** — paste a SQL query, choose database, click **Analyze**.
   - Confirm `is_valid`, `issues`, `index_recommendations`, `estimated_cost`, `rewritten_query`, `explain_plan`.
2. **Schema Browser** — search table names, inspect columns, copy DDL to clipboard.

### Step 21 — Active CI/CD monitoring & DORA (Phase 23)

```bash
# View live pipeline runs
curl -H "Authorization: Bearer <token>" http://localhost:8000/api/cicd/active-runs

# View DORA metrics
curl -H "Authorization: Bearer <token>" http://localhost:8000/api/cicd/dora-metrics

# Trigger monitor scan
curl -X POST -H "Authorization: Bearer <token>" http://localhost:8000/api/cicd/monitor
```

Frontend verification:

| Persona | Location | What to check |
|---|---|---|
| Developer | Sidebar → **Live Pipelines** | DAG Build→Test→Security Scan→Deploy with stage spinners |
| Admin / Ops | **Dashboard** | DORA KPI row (Deployment Freq, Lead Time, CFR, MTTR) |
| Data Engineer | **Pipeline Health** | dbt / Airflow CI widget with Live tab |

RBAC for CI/CD-generated incidents:

| Failed Stage | `owner_role` (approval queue) |
|---|---|
| Security Scan | Network Engineer |
| Test | Developer |
| Deploy | Developer |

---

## Key API Endpoints

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| POST | `/api/auth/login` | ❌ | Get JWT token |
| GET | `/health` | ❌ | Service liveness check |
| POST | `/api/triage` | ✅ | Run AI log triage |
| GET | `/api/incidents` | ✅ | List incidents (RBAC-filtered) |
| GET | `/api/incidents/approvals` | ✅ | HITL approval queue |
| POST | `/api/incidents/{id}/approve` | ✅ | Approve agent execution |
| POST | `/api/incidents/{id}/reject` | ✅ | Reject agent plan |
| POST | `/api/incidents/{id}/dry-run` | ✅ | Preview commands without execution |
| POST | `/api/incidents/{id}/remediate` | ✅ | Execute automated runbook |
| POST | `/api/incidents/{id}/jira` | ✅ | Create Jira ticket |
| POST | `/api/infra/generate` | ✅ | Generate Terraform + CLI commands |
| GET | `/api/infra/history` | ✅ | Infra generation history |
| POST | `/api/cicd/generate` | ✅ | Generate CI/CD pipeline YAML |
| GET | `/api/cicd/history` | ✅ | Pipeline generation history |
| GET | `/api/cicd/active-runs` | ✅ | Live pipeline run statuses |
| GET | `/api/cicd/dora-metrics` | ✅ | DORA KPIs |
| POST | `/api/cicd/monitor` | ✅ | Dispatch CI/CD monitor scan |
| GET | `/api/analytics` | ✅ | Aggregated dashboard metrics |
| POST | `/api/webhooks/inbound` | ✅ | Inbound webhook gateway |
| POST | `/api/webhooks/logs` | ✅ | Raw log ingestion |
| GET | `/api/webhooks/activity` | ✅ | Recent webhook event feed |
| POST | `/api/logs/scan-anomalies` | ✅ | Predictive anomaly detection |
| POST | `/api/db/analyze-query` | ✅ | AI SQL EXPLAIN + index + rewrite |
| POST | `/api/chat` | ✅ | Context-aware SRE chatbot |
| GET | `/api/notifications` | ✅ | All notifications |
| PUT | `/api/notifications/{id}/read` | ✅ | Mark notification read |
| GET/POST | `/api/settings` | ✅ | User preferences |
| GET | `/metrics` | ❌ | Prometheus metrics scrape endpoint |

---

## Webhook Gateway

Send events from any tool — the gateway auto-normalises the payload and routes to the correct role.

```bash
# GitHub → Developer
curl -X POST http://localhost:8000/api/webhooks/inbound \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"source": "github", "payload": {"action": "push", "message": "Deploy failed on main"}}'

# PostgreSQL → DatabaseDeveloper
curl -X POST http://localhost:8000/api/webhooks/inbound \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"source": "postgresql", "payload": {"message": "deadlock detected on table orders"}}'

# Prometheus AlertManager → NetworkEngineer
curl -X POST http://localhost:8000/api/webhooks/inbound \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"source": "prometheus", "payload": {"alerts": [{"annotations": {"summary": "High memory usage on node-01"}}]}}'

# Raw log ingestion
curl -X POST http://localhost:8000/api/webhooks/logs \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"source": "prod-server", "log_text": "CRITICAL: OOMKiller activated on auth-service"}'
```

Source → Role routing table:

| Source | Routed To |
|---|---|
| github, gitlab, jira, cypress, sonarqube, snyk, sentry | Developer |
| airflow, snowflake, dbt, kafka | DataEngineer |
| aws, datadog, pagerduty, cloudwatch, prometheus, alertmanager, grafana, kubernetes | NetworkEngineer |
| rds, mongodb, postgresql, mysql, redis, clickhouse, elasticsearch | DatabaseDeveloper |

---

## What's Next

| Priority | Item |
|---|---|
| 🔴 High | Add `pytest` unit + integration tests (`parse_json_response`, `CommandValidator`, auth endpoints) |
| 🔴 High | Add `@limiter.limit(...)` to `POST /api/auth/login` (brute-force protection) |
| 🟠 Medium | GitHub Actions CI workflow (lint → type-check → test on every PR) |
| 🟠 Medium | Nginx reverse proxy container with TLS termination |
| 🟠 Medium | Wire `GET /api/cicd/dora-metrics` to live GitHub Actions / GitLab CI data |
| 🟡 Low | Grafana dashboard container (visualise Prometheus metrics already at `/metrics`) |
| 🟡 Low | Kubernetes Helm chart / GCP Cloud Run deployment |
| 🟡 Low | Secret rotation via HashiCorp Vault or AWS Secrets Manager |
