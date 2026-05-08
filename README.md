# AIOps Platform Engineering Assistant

> An enterprise-grade, AI-powered Internal Developer Portal (IDP) that unifies alert triage, infrastructure generation, CI/CD automation, agentic remediation workflows, and real-time analytics — all in a single dark-mode dashboard.

Built to demonstrate production-grade platform engineering: local/cloud LLM orchestration, role-based access control, Human-in-the-Loop agent flows, AI safety guardrails, async task queues, and a fully containerised PostgreSQL + Redis + Celery stack.

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

---

## Implementation Steps (Phase 23 — CI/CD Monitoring & DORA)

Follow these steps to verify or reproduce Phase 23 locally.

### 1. Backend routes

1. Ensure the backend is running (`uvicorn` or Docker Compose).
2. **Mock active pipelines** — returns builds with per-stage status (`Build`, `Test`, `Security Scan`, `Deploy`):
   ```bash
   curl http://127.0.0.1:8000/api/cicd/active-runs
   ```
3. **DORA metrics** — organizational KPI strings for the Ops dashboard:
   ```bash
   curl http://127.0.0.1:8000/api/cicd/dora-metrics
   ```
4. **Trigger CI/CD monitor** — queues Celery task `monitor_cicd_pipelines` (or in-process fallback if Redis is down):
   ```bash
   curl -X POST http://127.0.0.1:8000/api/cicd/monitor
   ```
   Response is `202` with `task_id`. The worker picks a random scenario (stuck security scan, flaky tests, failed deploy), creates an `Incident` with `source: cicd-monitor`, sets `owner_role` by failed stage, and runs HITL evaluation.

### 2. Celery worker

Include `monitor_cicd_pipelines` when running workers (same app as webhooks):

```bash
cd backend
celery -A worker.celery_app worker --loglevel=info --concurrency=2
```

Without Redis/Celery, `POST /api/cicd/monitor` falls back to `asyncio.create_task` inside FastAPI.

### 3. Frontend — where to click

| Persona | Location | What you see |
|---------|----------|----------------|
| **Developer** | Sidebar → **Live Pipelines** | DAG rows per repo (Build → Test → Security Scan → Deploy), spinners on active stages, **Run Monitor Scan**, polling refresh |
| **Admin / Ops** | **Dashboard** (first sidebar item) | **DORA Metrics** row: Deploy Frequency, Lead Time, Change Failure Rate, MTTR (from `/api/cicd/dora-metrics`) |
| **Data Engineer** | **Pipeline Health** | **dbt / Airflow CI Pipeline Runs** widget (dbt models, Airflow CI DAGs, **Live** tab from `/api/cicd/active-runs`) |

### 4. RBAC — approvals by pipeline stage

Incidents created by the CI/CD monitor set `owner_role` from the failing stage so **Agent Pending Approvals** only surface for the owning persona:

| Failed stage | `owner_role` (approver queue) |
|--------------|-------------------------------|
| Security Scan | Network Engineer |
| Test | Developer |
| Deploy | Developer |

HIGH-severity scenarios enter **AWAITING_APPROVAL** (after `CommandValidator`); MEDIUM may auto-resolve per existing HITL rules.

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
│  UserSetting │          │  Redis (broker)     │
└─────────────┘          └────────────────────┘
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
# Clone the repo
git clone https://github.com/rohithkhannanukala1990-cell/platform-engineering-assistant.git
cd platform-engineering-assistant

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

## License

MIT
