# AIOps Platform Engineering Assistant

> An enterprise-grade, AI-powered Internal Developer Portal (IDP) that unifies alert triage, infrastructure generation, CI/CD automation, agentic remediation workflows, and real-time analytics — all in a single dark-mode dashboard.

Built to demonstrate production-grade platform engineering: local/cloud LLM orchestration, role-based access control, Human-in-the-Loop agent flows, AI safety guardrails, async task queues, and a fully containerised PostgreSQL + Redis + Celery stack.

### Contents

| Section | Description |
|---------|-------------|
| [Feature Overview](#feature-overview) | All 23 phases at a glance |
| [Tech Stack](#tech-stack) | Frontend, backend, AI, infra |
| [Architecture](#architecture) | High-level system diagram |
| [Role-Based Portals](#role-based-portals) | Routes and modules per persona |
| [HITL Agentic Flow](#hitl-agentic-flow) | Approval vs auto-resolve |
| [AI Safety Guardrail](#ai-safety-guardrail) | `CommandValidator` |
| [Project Structure](#project-structure) | Repo layout |
| [Getting Started](#getting-started) | Docker Compose & local dev |
| [**Whole project implementation & verification**](#whole-project-implementation--verification) | **Step-by-step checklist (Phases 1–23)** |
| [Key API Endpoints](#key-api-endpoints) | REST reference |
| [Webhook Gateway](#webhook-gateway) | Sources & routing examples |

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
| 21 | Query Analyzer — AI-powered SQL EXPLAIN, index recommendations, rewrite (`POST /api/db/analyze-query`) |
| 22 | Schema Browser — table explorer with columns, types, PK/FK badges, DDL copy |
| 23 | Active CI/CD monitoring — live pipeline DAG, DORA KPIs, Celery `monitor_cicd_pipelines`, stage-based HITL routing |

**Full implementation & verification** for all phases (1–23): see [Whole project implementation & verification](#whole-project-implementation--verification) (after Getting Started).

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
| PostgreSQL | Production-ready relational database |
| psycopg2-binary | PostgreSQL driver |
| Celery + Redis | Distributed async task queue |
| Pydantic v2 | Request/response validation |
| httpx | Async HTTP client (Slack, Jira, ServiceNow) |

### AI / LLM
| Technology | Purpose |
|---|---|
| Google Gemini | Cloud LLM (via `google-genai`) |
| Ollama + Gemma 3 4B | Local LLM — fully offline, privacy-preserving |
| Structured JSON prompting | Deterministic, parseable AI output |

### Infrastructure
| Technology | Purpose |
|---|---|
| Docker Compose | 5-service local stack |
| PostgreSQL 16 | Primary database |
| Redis 7 | Celery broker + result backend |
| Celery 5 | Distributed task queue with retry logic |

---

## Architecture

```
┌──────────────────────────────────────────────────────┐
│  React Frontend  (Vite · Tailwind · React Router)    │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌────────┐  │
│  │Dashboard │ │ Triage   │ │  Infra   │ │ CI/CD  │  │
│  │Analytics │ │(AI+HITL) │ │ Builder  │ │ Gen    │  │
│  └──────────┘ └──────────┘ └──────────┘ └────────┘  │
│  Role Portals: Ops · Developer · DataEngineer        │
│               NetworkEngineer · DatabaseDeveloper    │
└──────────────────────┬───────────────────────────────┘
                       │ HTTP / REST
┌──────────────────────▼───────────────────────────────┐
│  FastAPI Backend                                      │
│  ┌────────────────────────────────────────────────┐  │
│  │  Routes: triage · infra · cicd · chat · cicd/active · dora · monitor    │  │
│  │          analytics · incidents · webhooks       │  │
│  │          notifications · settings · approvals  │  │
│  └────────────────────────────────────────────────┘  │
│  ┌───────────────┐  ┌──────────────────────────────┐ │
│  │ CommandValidator│  │ HITL Evaluator (asyncio task)│ │
│  │ (AI Guardrail) │  │ AUTO: LOW/WARN → resolved    │ │
│  └───────────────┘  │ HITL: HIGH/CRIT → approval   │ │
│                     └──────────────────────────────┘ │
└──────┬───────────────────────────┬────────────────────┘
       │                           │ .delay()
┌──────▼──────┐          ┌─────────▼──────────┐
│ PostgreSQL  │          │  Celery Worker      │
│  (SQLModel) │          │  ┌───────────────┐  │
│             │◄─────────│  │process_inbound│  │
│  Incident   │          │  │process_log    │  │
│  Infra      │          │  │monitor_cicd   │  │
│  CICDPipeline│          │  └───────────────┘  │
│  Notification│          └─────────┬──────────┘
│  WebhookEvent│                   │
│  UserSetting │          ┌─────────▼──────────┐
└─────────────┘          │  Redis (broker)     │
                         └────────────────────┘
```

---

## Role-Based Portals

| Role | Portal Route | Modules |
|---|---|---|
| Admin | `/ops` | Full access to all portals + Persona Switcher + Integrations page |
| Network Engineer | `/ops` | Dashboard · Alert Triage · Infra Builder · CI/CD Pipeline · Integrations |
| Developer | `/developer` | Software Catalog · **Deployments** · **Live Pipelines** · **Runbooks** |
| Data Engineer | `/data` | Pipeline Health (+ **dbt / Airflow CI widget**) · **Storage** · **Data Lineage** |
| Database Developer | `/database` | DB Health · **Query Analyzer** · **Schema Browser** |

---

## HITL Agentic Flow

```
New Incident (webhook or manual triage)
        │
        ▼
  _hitl_evaluate()
        │
  ┌─────┴─────┐
  │           │
LOW/WARN   HIGH/CRIT
MEDIUM       │
  │      CommandValidator (35+ blocklist patterns)
  │          │
  │     ┌────┴────┐
  │   SAFE      UNSAFE
  │     │          │
  │  AWAITING   ESCALATED_
  │  APPROVAL   SECURITY_RISK
  │     │       (plan cleared,
  │  [Approve]   manual review)
  │     │
  ▼     ▼
RESOLVED_BY_AGENT
```

---

## AI Safety Guardrail

The `CommandValidator` class scans every AI-generated command and remediation plan **before** it can be queued for execution. Blocklist categories:

| Category | Examples |
|---|---|
| Filesystem destruction | `rm -rf`, `mkfs`, `dd if=`, `shred` |
| Permission escalation | `chmod 777`, `sudo su`, `sudo -i` |
| Destructive SQL | `DROP TABLE`, `TRUNCATE`, `DELETE FROM` (no WHERE) |
| Firewall nukes | `iptables -F`, `ufw disable` |
| Credential exfiltration | `curl \| bash`, `cat /etc/shadow` |
| Container/cluster nukes | `kubectl delete namespace`, `docker system prune -a` |
| Cloud nukes | `aws s3 rm --recursive`, `az group delete` |

If a violation is detected → status becomes `ESCALATED_SECURITY_RISK`, the plan is cleared, a CRITICAL notification fires, and an audit log is saved.

---

## Project Structure

```
Platform asistant/
├── backend/
│   ├── main.py               # FastAPI app, all routes, AI orchestration
│   ├── database.py           # SQLModel tables, CRUD helpers, migrations
│   ├── worker.py             # Celery app factory
│   ├── tasks.py              # Celery: webhooks + monitor_cicd_pipelines
│   ├── command_validator.py  # AI Safety Guardrail
│   ├── requirements.txt
│   ├── Dockerfile
│   └── .env                  # (gitignored — copy from .env.example)
├── src/
│   ├── App.jsx               # React Router setup, layout, sub-view state
│   ├── contexts/
│   │   └── RoleContext.jsx   # Global role state (RBAC)
│   └── components/
│       ├── DashboardView.jsx
│       ├── TriageView.jsx
│       ├── InfraBuilderView.jsx
│       ├── CICDView.jsx
│       ├── OpsPortal.jsx
│       ├── DeveloperPortal.jsx
│       ├── DeploymentsView.jsx      # Deployment history, trigger, rollback
│       ├── LivePipelinesView.jsx    # Live CI/CD DAG (Build→Test→Scan→Deploy)
│       ├── RunbooksView.jsx         # Executable runbook library
│       ├── DataEngineerPortal.jsx
│       ├── StorageView.jsx          # Bucket usage, cost, MoM trends
│       ├── DataLineageView.jsx      # Interactive SVG DAG
│       ├── DatabasePortal.jsx
│       ├── QueryAnalyzerView.jsx    # AI-powered SQL analyzer
│       ├── SchemaBrowserView.jsx    # Table/column/DDL explorer
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
└── .gitignore
```

---

## Getting Started

### Prerequisites
- Docker Desktop (recommended) **or** Python 3.12+, Node 20+, PostgreSQL 16, Redis 7

### Option A — Docker Compose (recommended)

```bash
# Clone the repo (replace with your fork/path if different)
git clone https://github.com/rohithkhannanukala1990-cell/Platform-assistant-portal.git
cd Platform-assistant-portal

# Copy and fill in secrets
cp backend/.env.example backend/.env
# Edit backend/.env — add GEMINI_API_KEY or set AI_PROVIDER=ollama

# Start everything
docker compose up --build
```

Services started:
| Service | URL |
|---|---|
| React frontend | http://localhost:5173 |
| FastAPI backend | http://localhost:8000 |
| API docs | http://localhost:8000/docs |
| PostgreSQL | localhost:5432 |
| Redis | localhost:6379 |

### Option B — Local Development

```bash
# 1. Backend
cd backend
pip install -r requirements.txt
uvicorn main:app --reload          # Terminal 1

# 2. Celery worker (requires Redis running)
celery -A worker.celery_app worker --loglevel=info --concurrency=2   # Terminal 2

# 3. Frontend
cd ..
npm install
npm run dev                        # Terminal 3
```

### Environment Variables (`backend/.env`)

```env
# AI provider — "gemini" (cloud) or "ollama" (local)
AI_PROVIDER=ollama
GEMINI_API_KEY=your_key_here

# Ollama (local LLM)
OLLAMA_URL=http://localhost:11434
OLLAMA_MODEL=gemma3:4b

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

---

## Whole project implementation & verification

Use this as an **end-to-end checklist** after [Getting Started](#getting-started). Each block maps to the [Feature Overview](#feature-overview) phases.

### Step 1 — Bootstrap and health check

1. Copy `backend/.env.example` → `backend/.env` and set **either** `GEMINI_API_KEY` with `AI_PROVIDER=gemini` **or** local **Ollama** (`AI_PROVIDER=ollama`, `OLLAMA_URL`, `OLLAMA_MODEL`).
2. Start the stack (**Docker Compose** or **local** backend + optional Celery + frontend).
3. Confirm **http://localhost:8000/docs** (FastAPI OpenAPI) and **http://localhost:5173** (React) load.
4. Smoke test the API: **GET http://localhost:8000/health** (or **GET /api/analytics**).

### Step 2 — AI alert triage and persistence (Phases 1–2)

1. Call **POST /api/triage** with sample log text **or** use the UI **Alert Triage** flow.
2. Confirm structured fields (severity, summary, action items) in the response and on the **Incident Report** card.
3. Open the **History** sidebar → **Alerts** tab; click an item and confirm the main view reloads saved incident data by ID.
4. Open **Settings** (gear): adjust preferences (e.g. theme); confirm **GET/POST `/api/settings`** persists values (optional Slack webhook for Phase 4).

### Step 3 — Universal history, infra, and CI/CD artifacts (Phases 2–3)

1. Generate infra from **Infra Builder**; confirm **History → Infra** lists the new record.
2. Generate a pipeline from **CI/CD Pipeline**; confirm **History → CI/CD** lists the saved YAML/metadata.

### Step 4 — Slack, Jira, and notifications (Phase 4)

1. Open **Settings** (gear) and optionally set **Slack Webhook URL**.
2. Create or ingest a **HIGH** / **CRITICAL** incident; confirm **notification bell** updates (unread count).
3. With Jira env vars set, use **Create Jira Ticket** on an incident and confirm API success (see backend logs if needed).

### Step 5 — Automated log webhooks (Phases 5, 16)

1. **POST /api/webhooks/logs** with JSON `{ "source": "...", "log_text": "..." }`.
2. Expect **202 Accepted** and `task_id` when Celery is available; processing continues in worker or in-process fallback.
3. Confirm a new incident appears and notifications behave as configured.

### Step 6 — Analytics dashboard (Phase 6)

1. Navigate to **Dashboard** (Ops default landing).
2. Confirm cards and Recharts (severity donut, sources bar, trends) match **GET /api/analytics**.
3. Trigger new incidents and **Refresh** — aggregates should change.

### Step 7 — Automated runbooks (Phase 7)

1. Select an **OPEN** incident; click **Execute Automated Runbook**.
2. After **POST /api/incidents/{id}/remediate** completes, confirm status **RESOLVED** and terminal-style **execution_logs** on the card.
3. **View Internal Runbooks** opens the configured wiki URL (mock).

### Step 8 — Platform Assistant chatbot (Phase 8)

1. Click the floating chat (**FAB**).
2. Send a question; confirm **POST /api/chat** returns an answer grounded on live counts (open incidents, recent resolved, module activity).

### Step 9 — RBAC, routing, and personas (Phase 9)

1. As **Admin**, use **Persona Switcher** to visit `/ops`, `/developer`, `/data`, `/database`.
2. Confirm sidebar modules change per role and **GET /api/incidents** returns role-filtered incidents for non-Admin roles.
3. Optional: use **Login** / **Logout** and profile dropdown (mock auth) — logout returns focus to dashboard/home routing.

### Step 10 — Log anomaly detection (Phase 10)

1. On **Dashboard**, click **Run Predictive Log Scan**.
2. After **POST /api/logs/scan-anomalies** (~3s delay), confirm a new **WARNING** incident and amber styling in lists/cards.

### Step 11 — Inbound webhook gateway (Phase 11)

1. **POST /api/webhooks/inbound** with a JSON body including `source` (e.g. `github`, `airflow`, `postgresql`).
2. Expect **202** + Celery dispatch; confirm routing to `owner_role` per source table in [Webhook Gateway](#webhook-gateway).
3. As **Admin**, open **Integrations** — copy URLs and inspect **Recent Webhook Activity** (**GET /api/webhooks/activity**).

### Step 12 — HITL agentic approvals (Phase 12)

1. Create **HIGH**/**CRITICAL** incidents (triage or webhook) so `_hitl_evaluate` proposes a plan.
2. On the role dashboard (**Developer**, **Data Engineer**, **Database**, **Ops**), open **Agent Pending Approvals**.
3. **Approve** or **Reject** only when the active role matches incident `owner_role`; confirm status transitions (**AWAITING_APPROVAL** → **RESOLVED_BY_AGENT** / **REJECTED**).

### Step 13 — Database Developer portal (Phase 13)

1. Switch persona to **Database Developer** → `/database`.
2. Confirm **Database Health** metrics (connections, slow queries, storage).

### Step 14 — AI safety guardrail (Phase 14)

1. When AI output contains blocklisted commands/SQL, backend sets **ESCALATED_SECURITY_RISK**, clears the plan, and raises a critical notification.
2. UI: red **SECURITY RISK** banner; approve/reject controls hidden on affected incidents.

### Step 15 — PostgreSQL and Docker Compose (Phase 15)

1. With **DATABASE_URL** pointing at Postgres (Compose or local), restart backend — migrations apply via `database.py`.
2. For SQLite-only dev, omit `DATABASE_URL` (see `backend/database.py` defaults).
3. Confirm FastAPI **lifespan** waits for DB when using Postgres.

### Step 16 — Celery and Redis (Phase 16)

1. Start **Redis** and run `celery -A worker.celery_app worker --loglevel=info` from `backend/`.
2. Fire **POST /api/webhooks/inbound** and **POST /api/webhooks/logs** — tasks should appear in worker logs.
3. Stop Redis temporarily — FastAPI should fall back to in-process async processing (development resilience).

### Step 17 — Developer portal: deployments and runbooks (Phases 17–18)

1. **Deployments** — filter env, trigger deploy, open log drawer, try rollback (mock).
2. **Runbooks** — filter category, run a playbook and watch step-by-step terminal simulation.

### Step 18 — Data Engineer portal: storage and lineage (Phases 19–20)

1. **Storage** — bucket cards, cost bars, team breakdown.
2. **Data Lineage** — click nodes; confirm upstream/downstream highlight on the SVG DAG.

### Step 19 — Database portal: query analyzer and schema browser (Phases 21–22)

1. **Query Analyzer** — paste SQL, choose DB, **Analyze Query** (**POST /api/db/analyze-query**).
2. **Schema Browser** — search tables, inspect columns/indexes, copy DDL.

### Step 20 — Active CI/CD monitoring and DORA (Phase 23)

**Backend**

1. **GET /api/cicd/active-runs** — mock pipelines with `current_stage`, `status`, `elapsed_time`, `stage_statuses`.
2. **GET /api/cicd/dora-metrics** — mock DORA KPIs for the Ops dashboard.
3. **POST /api/cicd/monitor** — returns **202** + `task_id`; runs Celery task `monitor_cicd_pipelines` (or in-process fallback if broker unavailable):

```bash
curl http://127.0.0.1:8000/api/cicd/active-runs
curl http://127.0.0.1:8000/api/cicd/dora-metrics
curl -X POST http://127.0.0.1:8000/api/cicd/monitor
```

The monitor creates an incident with `source: cicd-monitor` and routes **owner_role** by failed stage for HITL.

**Celery**

```bash
cd backend
celery -A worker.celery_app worker --loglevel=info --concurrency=2
```

**Frontend**

| Persona | Where | What to verify |
|---------|--------|----------------|
| Developer | Sidebar → **Live Pipelines** | DAG **Build → Test → Security Scan → Deploy**, spinners on active stages, **Run Monitor Scan**, auto-refresh |
| Admin / Ops | **Dashboard** | **DORA Metrics** row (four KPI cards from `/api/cicd/dora-metrics`) |
| Data Engineer | **Pipeline Health** | **dbt / Airflow CI Pipeline Runs** widget (dbt / Airflow / **Live** tabs) |

**RBAC for CI/CD-generated approvals**

| Failed stage | Incident `owner_role` (approval queue) |
|--------------|----------------------------------------|
| Security Scan | Network Engineer |
| Test | Developer |
| Deploy | Developer |

---

## Key API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| POST | `/api/triage` | Run AI log analysis |
| GET | `/api/incidents` | List incidents (RBAC-filtered) |
| GET | `/api/incidents/approvals` | HITL approval queue (AWAITING + ESCALATED) |
| POST | `/api/incidents/{id}/approve` | Approve agent execution |
| POST | `/api/incidents/{id}/reject` | Reject agent plan |
| POST | `/api/incidents/{id}/remediate` | Execute automated runbook |
| POST | `/api/incidents/{id}/jira` | Create Jira ticket |
| POST | `/api/infra/generate` | Generate Terraform + CLI |
| POST | `/api/cicd/generate` | Generate pipeline YAML |
| GET | `/api/cicd/active-runs` | Mock active pipeline runs + per-stage statuses |
| GET | `/api/cicd/dora-metrics` | Mock DORA KPIs (frequency, lead time, CFR, MTTR) |
| POST | `/api/cicd/monitor` | Dispatch Celery `monitor_cicd_pipelines` (202 + task id) |
| GET | `/api/analytics` | Aggregated dashboard metrics |
| POST | `/api/webhooks/inbound` | Inbound webhook gateway (202 + Celery) |
| POST | `/api/webhooks/logs` | Raw log ingestion (202 + Celery) |
| GET | `/api/webhooks/activity` | Recent webhook event feed |
| POST | `/api/logs/scan-anomalies` | Predictive anomaly detection |
| POST | `/api/db/analyze-query` | AI SQL EXPLAIN + index recommendations + rewrite |
| POST | `/api/chat` | Context-aware SRE chatbot |
| GET | `/api/notifications` | All notifications |
| GET/POST | `/api/settings` | User preferences |

---

## Webhook Gateway

Send events from any tool — the gateway auto-routes to the correct role:

```bash
# GitHub → Developer
curl -X POST http://localhost:8000/api/webhooks/inbound \
  -H "Content-Type: application/json" \
  -d '{"source": "github", "payload": {"action": "push", "message": "Deploy failed"}}'

# PostgreSQL → DatabaseDeveloper
curl -X POST http://localhost:8000/api/webhooks/inbound \
  -H "Content-Type: application/json" \
  -d '{"source": "postgresql", "payload": {"message": "deadlock detected on table orders"}}'

# Raw log ingestion
curl -X POST http://localhost:8000/api/webhooks/logs \
  -H "Content-Type: application/json" \
  -d '{"source": "prod-server", "log_text": "CRITICAL: OOMKiller activated on auth-service"}'
```

Source → Role routing:

| Source | Routed To |
|---|---|
| github, gitlab, jira | Developer |
| airflow, snowflake, dbt, kafka | DataEngineer |
| aws, datadog, pagerduty, cloudwatch | NetworkEngineer |
| rds, mongodb, postgresql, mysql, redis | DatabaseDeveloper |

---

