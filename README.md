# 🛡️ AIOps Platform Engineering Assistant

> **An enterprise-grade, AI-powered operations portal** that unifies alert triage, multi-cloud infrastructure generation, CI/CD pipeline automation, and real-time analytics into a single dark-mode dashboard — built to demonstrate the intersection of traditional infrastructure expertise and modern AI/software engineering.

This project is a **full-stack production-ready system** that runs a local LLM (Gemma 3 via Ollama) or a cloud model (Google Gemini) to perform intelligent DevOps work in real time, complete with database persistence, Slack ChatOps, Jira ticketing, and automated webhook log ingestion.

---

## ✨ Feature Overview

| Phase | Features |
|---|---|
| **Phase 1** | Analytics Dashboard, AI Alert Triage, Infra Builder, CI/CD Generator, History Sidebar, Settings |
| **Phase 2** | Slack ChatOps alerts, Jira ticket generation, Notification bell with unread badge |
| **Phase 3** | Automated webhook log ingestion, 202 background triage, source-tagged incidents |
| **Phase 4** | Recharts analytics dashboard — severity donut, source bar, 7-day trend line, module activity |

---

## 🧰 Tech Stack

### Frontend
| Technology | Purpose |
|---|---|
| **React 18** + **Vite** | Fast, component-driven SPA with HMR |
| **Tailwind CSS** | Utility-first dark-mode design system with custom tokens |
| **Recharts** | Responsive analytics charts (Bar, Line, Donut/Pie) |
| **Lucide React** | Consistent iconography |

### Backend
| Technology | Purpose |
|---|---|
| **FastAPI** | High-performance async Python API with automatic OpenAPI docs |
| **Uvicorn** | ASGI server with hot-reload |
| **SQLModel + SQLite** | Type-safe ORM with zero-config local persistence |
| **Pydantic v2** | Request/response validation and serialisation |
| **httpx** | Async HTTP client for Slack and Jira API calls |

### AI / LLM
| Technology | Purpose |
|---|---|
| **Ollama + Gemma 3 4B** | Local, offline-capable LLM inference (privacy-first) |
| **Google Gemini (gemma-3-27b-it)** | Cloud fallback for higher-quality analysis |
| **Structured JSON prompting** | Deterministic AI output with robust fallback parsing |

---

## 🧩 Core Modules

### 📊 Analytics Dashboard
- Real-time aggregated metrics fetched from `GET /api/analytics`
- **Summary cards**: Total Incidents, Critical Alerts, MTTR proxy, Unread Notifications
- **Donut chart** — Incidents by Severity (Critical/High/Medium/Low, colour-coded)
- **Bar chart** — Incidents by Source (identifies noisiest systems)
- **Line chart** — Incidents over the last 7 days (trend detection)
- **Horizontal bar** — Module activity (Alerts vs Infra vs CI/CD usage)

### ⚡ AI Alert Triage
- Paste raw logs → Gemma/Gemini performs senior SRE-level analysis
- Structured output: **Severity**, **Summary**, **Root Cause**, **Evidence**, **Action Plan**, **Shell Commands**, **Files to Check**, **Validation Steps**
- Every analysis is persisted to SQLite with a unique ID and timestamp
- Results are instantly loadable from the History sidebar

### 🏗️ Multi-Cloud Infra Builder
- Supports **AWS**, **GCP**, **Azure**, and **DigitalOcean**
- Natural language prompt → production-ready **Terraform HCL** + **Cloud CLI commands**
- AI acts as a Senior Multi-Cloud Architect, targeting free-tier resources with cost estimates
- Split-pane display with per-command copy buttons

### 🚀 CI/CD Pipeline Generator
- Supports **GitHub Actions**, **GitLab CI**, and **Jenkins (Groovy)**
- Prompt → complete pipeline YAML/Groovy with **explanation** and **security checks**
- AI acts as a Senior Release Engineer, embedding security scanning and quality gates
- One-click copy for the entire pipeline file

---

## 🔗 Enterprise Integrations

### 🔔 Notification Engine
- Every AI triage automatically creates a `Notification` record (type: `critical` / `warning` / `info`)
- Live bell icon in the navbar with real-time **unread badge** (polls every 30 s)
- Clicking a notification navigates directly to the linked incident

### 💬 Slack ChatOps
- Automatic Slack alert fired for every **Critical** or **High** severity incident
- Rich message attachment with severity colour, summary, and root cause
- Webhook URL configured in Settings — zero code changes required

### 🎫 Jira Ticket Generation
- Per-incident **"Create Jira Ticket"** button on every Incident Report Card
- Gemma formats the incident into a Jira-structured **Title**, **Description (ADF)**, **Priority**, and **Steps to Reproduce**
- Creates the issue via **Jira REST API v3** (Basic Auth) and returns a clickable ticket URL
- Jira credentials (domain, email, API token, project key) managed in the Settings modal

### 📡 Automated Log Ingestion Webhook
- `POST /api/webhooks/logs` — accepts `{"source": "server-name", "log_text": "..."}` from any external system
- Returns **202 Accepted** instantly; runs full AI triage as a **FastAPI BackgroundTask**
- Supports logs from CI/CD pipelines, cron jobs, monitoring agents, or shell scripts
- Webhook-sourced incidents are badged in the History panel with a `⚡ source-name` label
- Ready-to-use **cURL** and **Python** snippets displayed in Settings

---

## 🗄️ Database Schema

All data is persisted in a local **SQLite** database (`backend/incidents.db`) managed by **SQLModel**. The schema auto-migrates on startup.

| Table | Key Columns |
|---|---|
| `incident` | `id`, `timestamp`, `severity`, `summary`, `root_cause`, `evidence_json`, `action_plan_json`, `commands_json`, `model_used`, `source` |
| `infrageneration` | `id`, `timestamp`, `prompt`, `provider_used`, `terraform_code`, `cli_commands_json`, `cost_estimate` |
| `cicdpipeline` | `id`, `timestamp`, `prompt`, `tool_name`, `yaml_code`, `explanation`, `security_checks_json` |
| `notification` | `id`, `timestamp`, `message`, `type`, `is_read`, `incident_id` |
| `usersetting` | `id`, `key`, `value` |

---

## 🚀 Local Setup

### Prerequisites

| Tool | Version | Install |
|---|---|---|
| Python | 3.11+ | [python.org](https://python.org) |
| Node.js | 18+ | [nodejs.org](https://nodejs.org) |
| Ollama | Latest | [ollama.com](https://ollama.com) |
| Git | Any | [git-scm.com](https://git-scm.com) |

---

### 1. Clone the repository

```bash
git clone https://github.com/YOUR_USERNAME/aiops-portal.git
cd aiops-portal
```

---

### 2. Pull the local AI model

```bash
ollama pull gemma3:4b
```

> This downloads the ~3 GB Gemma 3 4B model. Run `ollama serve` if the Ollama desktop app is not already running.

---

### 3. Configure the backend

```bash
cd backend
```

Create `backend/.env`:

```env
# AI provider: "ollama" (local) or "gemini" (cloud)
AI_PROVIDER=ollama

# Only required when AI_PROVIDER=gemini
GEMINI_API_KEY=your_gemini_api_key_here

# Ollama settings
OLLAMA_URL=http://localhost:11434
OLLAMA_MODEL=gemma3:4b
```

---

### 4. Install backend dependencies

```bash
# Windows PowerShell
python -m pip install -r requirements.txt

# macOS / Linux
pip install -r requirements.txt
```

---

### 5. Start the backend

```bash
# Windows PowerShell
python -m uvicorn main:app --reload

# macOS / Linux
uvicorn main:app --reload
```

The API is now live at `http://127.0.0.1:8000`. Visit `http://127.0.0.1:8000/docs` for the auto-generated OpenAPI documentation.

---

### 6. Install and start the frontend

Open a **second terminal** in the project root:

```bash
npm install
npm run dev
```

Open `http://localhost:5173` in your browser.

---

### 7. Test the webhook endpoint (optional)

```bash
# macOS / Linux
curl -X POST http://127.0.0.1:8000/api/webhooks/logs \
  -H "Content-Type: application/json" \
  -d '{"source": "prod-server", "log_text": "CRITICAL: OOM killer invoked, pod crashed"}'

# Windows PowerShell
Invoke-RestMethod -Method POST -Uri http://127.0.0.1:8000/api/webhooks/logs \
  -ContentType "application/json" \
  -Body '{"source": "prod-server", "log_text": "CRITICAL: OOM killer invoked, pod crashed"}'
```

The API returns `202 Accepted` immediately. The bell icon in the portal will badge with a new notification once Gemma finishes processing (~15–30 seconds).

---

## 📡 API Reference

| Method | Route | Description |
|---|---|---|
| `POST` | `/api/triage` | Run AI triage on raw logs |
| `GET` | `/api/incidents` | List all triaged incidents |
| `POST` | `/api/infra/generate` | Generate Terraform + CLI for a cloud provider |
| `GET` | `/api/infra/history` | List all infra generations |
| `POST` | `/api/cicd/generate` | Generate a CI/CD pipeline |
| `GET` | `/api/cicd/history` | List all pipeline generations |
| `POST` | `/api/webhooks/logs` | Ingest logs via webhook (202, background triage) |
| `POST` | `/api/incidents/{id}/jira` | Create a Jira ticket for an incident |
| `GET` | `/api/notifications` | List all notifications |
| `PUT` | `/api/notifications/{id}/read` | Mark a notification as read |
| `GET` | `/api/settings` | Fetch user preferences |
| `POST` | `/api/settings` | Update user preferences |
| `GET` | `/api/analytics` | Aggregated platform metrics for the dashboard |
| `GET` | `/health` | Service health check |

---

## 🏗️ Project Structure

```
aiops-portal/
├── backend/
│   ├── main.py           # FastAPI app, all routes, AI orchestration
│   ├── database.py       # SQLModel schema, migrations, CRUD helpers
│   ├── requirements.txt  # Python dependencies
│   └── .env              # Local secrets (not committed)
│
└── src/
    ├── App.jsx                        # Root layout, routing, state
    └── components/
        ├── Sidebar.jsx                # Navigation sidebar
        ├── DashboardView.jsx          # Analytics dashboard with Recharts
        ├── TriageView.jsx             # AI log triage interface
        ├── IncidentReportCard.jsx     # Structured incident display + Jira button
        ├── InfraBuilderView.jsx       # Multi-cloud Terraform generator
        ├── CICDView.jsx               # CI/CD pipeline generator
        ├── HistoryPanel.jsx           # Universal history sidebar (3 tabs)
        ├── NotificationDropdown.jsx   # Bell icon with live notification feed
        └── SettingsModal.jsx          # Preferences, credentials, webhook docs
```

---

## 🔐 Security Notes

- API keys and credentials are stored in `backend/.env` — **never commit this file**
- Jira API tokens and Slack webhook URLs are stored in the local SQLite `usersetting` table
- The backend runs with CORS restricted to `localhost` origins only
- No authentication layer is implemented in this MVP — intended for local/internal use

---

## 🗺️ Roadmap

- [ ] **Phase 5** — Role-based access control (RBAC) with JWT authentication
- [ ] **Phase 6** — Kubernetes operator integration for live cluster event ingestion
- [ ] **Phase 7** — PagerDuty and OpsGenie alert routing
- [ ] **Phase 8** — Multi-tenant support with per-team dashboards

---

## 👨‍💻 About

Built by a **Sysadmin / Storage Engineer** actively transitioning into **SRE and AI Platform Engineering**. This project demonstrates practical command of the full modern SRE toolchain: infrastructure-as-code, CI/CD, observability, AI-assisted operations, and API-first backend design — implemented from scratch as a working, production-pattern application.

---

*Built with FastAPI · React · Ollama · SQLite · Recharts · Tailwind CSS*
