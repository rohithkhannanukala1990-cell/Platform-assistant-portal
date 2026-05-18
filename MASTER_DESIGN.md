# Platform Assistant Portal — MASTER DESIGN DOCUMENT
> **Single source of truth. Read this file at the start of EVERY sprint prompt.**
> Last updated: Sprint 12 complete / Sprint 13 starting

---

## 1. WHAT THIS PLATFORM IS

An open-source Internal Developer Portal (IDP) competing with Backstage, Port, and Cortex.

- **License:** AGPLv3 dual-license with commercial SaaS offering
- **Target market:** Enterprise teams — initially Indian market, then global
- **Key differentiators:**
  - Agentic AIOps with Human-in-the-Loop (HITL)
  - 4-layer context switching (workspace → tool → account → environment)
  - Multi-account tool connections per workspace
  - Drag-and-drop workspace canvas
  - Built-in Terminal + Code Editor as workspace tools
  - 16 purpose-built AI agents

---

## 2. TECH STACK

### Frontend
- React + Vite
- Tailwind CSS
- Monaco Editor (Code Editor — Sprint 15)
- xterm.js (Terminal — Sprint 15)
- React DnD (drag-and-drop workspace canvas)

### Backend
- FastAPI (Python)
- SQLAlchemy + PostgreSQL
- Redis (task queue / WebSocket pub-sub)
- Celery worker (background agent tasks)

### AI / Agent Runtime
- `LLMRouter` → routes to Gemini, OpenAI, or Ollama
- `SafeExecutor` → validates + executes all commands with HITL + rollback
- `CommandValidator` → safety-checks every command before execution

### Confirmed Key Backend Files
| File | Size | Role |
|------|------|------|
| `backend/ai/llm_router.py` | 5,191 B | LLM routing — all agents call this |
| `backend/executor/safe_executor.py` | 4,746 B | Safe command execution with HITL |
| `backend/command_validator.py` | 6,594 B | Command safety validation |
| `backend/connectors/registry.py` | 8,736 B | Tool connector registry |
| `backend/tasks.py` | 7,102 B | Async task queue |
| `backend/auto_heal.py` | 3,160 B | Auto-heal logic — move to `agents/` |

### LLMRouter API (confirmed)
```python
llm_router.chat(messages, model, system_prompt) → str
llm_router.build_system_prompt(context: dict) → str
# context keys: workspace_name, environment, tools,
#               tool_statuses_line, production_operating
```

### SafeExecutor API (confirmed)
```python
safe_executor.execute(commands, incident_id, approved_by) → dict
safe_executor.dry_run(commands) → dict
```

---

## 3. USER ROLES — EXACTLY 2 ROLES ONLY

| Role | Access |
|------|--------|
| **admin** | AdminDashboard, UserManagement, AuditLog, AgentApprovals, all features |
| **user** | WorkspaceBuilder canvas, tool connections, agent invocation (scoped by permissions) |

**CRITICAL RULES:**
- No personas. No 4-role model. Admin and User ONLY.
- `RoleContext.jsx` must reflect exactly these 2 roles
- `PersonaSwitcher.jsx` → DELETE in Sprint 14
- `RBACManager.jsx` → rescope to agent permissions per user only in Sprint 14

---

## 4. CONTEXT SWITCHING — 4 LAYERS

Every agent action, terminal command, and tool call executes inside a fully resolved 4-layer context.

```
Layer 1 — WORKSPACE     "Which workspace am I in?"
  └── Layer 2 — TOOL    "Which tool am I using?"
        └── Layer 3 — ACCOUNT    "Which account of that tool?"
              └── Layer 4 — ENVIRONMENT  "Which env within that account?"
```

### PlatformContext Object
```python
class PlatformContext:
    workspace_id:    str    # "platform-team-q3"
    workspace_name:  str    # "Platform Team — Q3 Sprint"
    environment:     str    # "production" | "staging" | "dev"
    tool_accounts:   dict   # {"aws": "aws-production", "kubernetes": "prod-gke", ...}
    user_id:         str
    user_role:       str    # "admin" | "user"
    active_tool:     str | None
    active_account:  str | None
```

### 3 Types of Context Switch
1. **Soft switch** — same workspace, different account for one tool only
2. **Environment switch** — same workspace, ALL tools flip env simultaneously
3. **Hard switch** — full workspace change, full context reset

### TopBar Breadcrumb (Sprint 16)
```
[Platform Team Q3 ▾] › [AWS: Production ▾] › [production ▾]
   workspace              tool + account        environment
```

---

## 5. MULTI-ACCOUNT TOOL MODEL

One tool can have multiple connected accounts per workspace.

**Examples:**
- AWS: "AWS Production", "AWS Staging", "AWS Dev"
- GitHub: "Frontend Org", "Backend Org", "GitHub Enterprise"
- Kubernetes: "Prod GKE Cluster", "Staging EKS", "Dev k3s"

### Database Table: tool_connections
```sql
id               UUID        PRIMARY KEY
workspace_id     UUID        FK → workspaces.id
tool_id          VARCHAR     -- "aws", "github", "kubernetes"
account_name     VARCHAR     -- "AWS Production" (user-given label)
account_alias    VARCHAR     -- "prod", "staging", "dev"
auth_type        VARCHAR     -- "iam_role", "pat", "api_key"
credentials      JSONB       -- encrypted at rest (AES-256 / Vault)
config           JSONB       -- {region, project_id, instance_url, ...}
status           VARCHAR     -- connected | disconnected | error
last_tested_at   TIMESTAMP
connected_by     UUID        FK → users.id
workspace_scoped BOOLEAN     -- True = only this workspace can use it
created_at       TIMESTAMP
updated_at       TIMESTAMP
UNIQUE (workspace_id, tool_id, account_alias)
```

### Agent Invocation with Multi-Account
```python
await deploy_agent.run(
    service_name="api-service",
    image_tag="v2.1.0",
    target_env="production",
    tool_accounts={
        "kubernetes": "prod-gke-cluster",
        "argocd":     "prod-argocd",
        "github":     "backend-org"
    },
    context=platform_context
)
```

### Connector Registry Pattern
```python
# registry.py must support:
get_connector(tool_id, workspace_id, account_alias) → BaseConnector
list_accounts(tool_id, workspace_id) → list[dict]
get_default_account(tool_id, workspace_id) → dict
```

---

## 6. THE 16 AGENTS

### Standard AgentResult Schema (ALL agents must return this)
```python
{
    "agent":             str,        # agent name e.g. "deploy_agent"
    "status":            str,        # "success"|"failed"|"pending_approval"|"dry_run"
    "summary":           str,        # 1-2 sentence human-readable summary
    "details":           dict,       # agent-specific results
    "requires_approval": bool,       # True = HITL gate before execution
    "approval_payload":  dict|None,  # what the admin will approve
    "execution_log":     str|None,   # from safe_executor logs
    "timestamp":         str,        # UTC ISO format
    "triggered_by":      str,        # user_id
    "workspace":         str,
    "environment":       str,
}
```

### All 16 Agents
| # | Agent | File | Approval Required | Primary Tools |
|---|-------|------|-------------------|---------------|
| 1 | Deploy Agent | `deploy_agent.py` | ✅ Production only | GitHub Actions, ArgoCD, Kubernetes, Helm |
| 2 | Security Agent | `security_agent.py` | ❌ Read-only | Snyk, SonarQube, Wiz, Checkov, GuardDuty |
| 3 | Tester Agent | `tester_agent.py` | ✅ Execution | GitHub Actions, CircleCI, Jenkins |
| 4 | Infra Agent | `infra_agent.py` | ✅ Always | Terraform, Pulumi, AWS, GCP, Azure |
| 5 | Incident Agent | `incident_agent.py` | ✅ Always | PagerDuty, OpsGenie, Kubernetes |
| 6 | Cost Agent | `cost_agent.py` | ❌ Read-only | AWS, GCP, Azure billing |
| 7 | Code Review Agent | `code_review_agent.py` | ❌ Read-only | GitHub, GitLab, SonarQube |
| 8 | Runbook Agent | `runbook_agent.py` | ✅ Always | Confluence, Kubernetes, Ansible |
| 9 | Catalog Health Agent | `catalog_health_agent.py` | ❌ Read-only | Catalog DB (internal) |
| 10 | Pipeline Monitor Agent | `pipeline_monitor_agent.py` | ❌ Read-only | Jenkins, CircleCI, GitHub Actions, ArgoCD |
| 11 | Auto-Heal Agent | `auto_heal_agent.py` | ✅ Production | Kubernetes, ArgoCD |
| 12 | Onboarding Agent | `onboarding_agent.py` | ✅ Scaffold | GitHub, Jira, GoldenPaths DB |
| 13 | Documentation Agent | `documentation_agent.py` | ❌ Read-only | Confluence, GitHub, Catalog DB |
| 14 | Scorecard Agent | `scorecard_agent.py` | ✅ On failure | Scorecards DB, Jira |
| 15 | Dependency Drift Agent | `dependency_drift_agent.py` | ❌ Read-only | Catalog DB, GitHub |
| 16 | Alert Noise Agent | `alert_noise_agent.py` | ❌ Read-only | PagerDuty, Datadog, Grafana, Prometheus |

### Agent Import Pattern (use in every agent)
```python
from ..ai.llm_router import llm_router
from ..executor.safe_executor import safe_executor
from ..database import get_db
from sqlalchemy.orm import Session
from datetime import datetime
import json
```

### Future — Sprint 17
| Agent | Reason Deferred |
|-------|-----------------|
| Migration Agent | Needs deep multi-cloud connector work first |

---

## 7. TOOL CATALOG (110+ tools from tools.txt)

Every tool has: connector auth type + agent actions.

### Tool Categories
| Category | Key Tools |
|----------|-----------|
| Source Control & PM | GitHub, GitLab, Bitbucket, Jira, Linear, Confluence |
| CI/CD | Kubernetes, ArgoCD, Helm, Terraform, Jenkins, GitHub Actions, CircleCI |
| Monitoring | PagerDuty, OpsGenie, Datadog, Grafana, Prometheus, Splunk, New Relic |
| Cloud | AWS, GCP, Azure |
| Secrets & Config | Vault, AWS Secrets Manager, Ansible, Puppet |
| Networking | Cloudflare, Nginx, Istio, HAProxy, Cisco Meraki |
| Databases | PostgreSQL, MySQL, MongoDB, Redis, Snowflake, BigQuery, DynamoDB |
| Data Pipelines | Airflow, Kafka, Databricks, dbt, Fivetran, Airbyte, Dagster |
| ML/AI | MLflow, Vertex AI, SageMaker, Ollama, OpenAI, Gemini, Hugging Face |
| Security | Snyk, Wiz, Checkov, GuardDuty, SonarQube, OWASP ZAP, Prisma Cloud |

### Priority Connectors to Build in Sprint 13
Build full connector classes (not BaseConnector stubs) for:
1. GitHub / GitLab
2. Kubernetes
3. AWS / GCP / Azure
4. PagerDuty / Datadog
5. Jira / Confluence

---

## 8. FRONTEND COMPONENT INVENTORY

### Confirmed Existing (repo scan — main branch)
| Component | Size | Sprint Action |
|-----------|------|---------------|
| AIAssistant.jsx | 33,771 B | ✅ Keep |
| AccountImportView.jsx | 46,737 B | ✅ Keep |
| AccountSwitcher.jsx | 14,856 B | ✅ Keep — Layer 3 context |
| AgentApprovalsWidget.jsx | 26,080 B | ✅ Keep — wire to AdminDashboard Sprint 14 |
| CICDView.jsx | 15,964 B | ✅ Keep |
| CatalogCopilotPanel.jsx | 10,538 B | ⚠️ Fix Sprint 16 |
| CatalogPage.jsx | 38,754 B | ✅ Keep — add tool search Sprint 15 |
| ChatBot.jsx | 8,546 B | ✅ Keep |
| CommandPalette.jsx | 15,193 B | ✅ Keep |
| DORAPage.jsx | 13,443 B | ⚠️ Fix team table Sprint 16 |
| DashboardView.jsx | 29,930 B | ✅ Keep |
| DataEngineerPortal.jsx | 17,400 B | ✅ Keep |
| DataLineageView.jsx | 11,036 B | ✅ Keep |
| DatabasePortal.jsx | 13,443 B | ✅ Keep |
| DependencyGraph.jsx | 20,977 B | ✅ Keep — Dependency Drift Agent connects here |
| DeploymentsView.jsx | 13,868 B | ✅ Keep |
| DeveloperPortal.jsx | 9,366 B | ✅ Keep |
| EntityActionsPage.jsx | 14,216 B | ✅ Keep |
| EnvironmentSwitcher.jsx | 10,353 B | ✅ Keep — Layer 4 context |
| ErrorBoundary.jsx | 1,944 B | ✅ Keep |
| GoldenPathsPage.jsx | 33,494 B | ✅ Keep — Onboarding Agent connects here |
| Header.jsx | 4,029 B | ✅ Keep |
| HealthDashboard.jsx | 22,499 B | ✅ Keep |
| HistoryPanel.jsx | 11,280 B | ✅ Keep |
| IncidentHistory.jsx | 6,363 B | ✅ Keep |
| IncidentReportCard.jsx | 17,097 B | ✅ Keep |
| InfraBuilderView.jsx | 15,543 B | ✅ Keep |
| IntegrationsPage.jsx | 18,964 B | ✅ Keep |
| Layout.jsx | 4,558 B | ✅ Keep |
| LivePipelinesView.jsx | 14,181 B | ✅ Keep |
| LoginPage.jsx | 5,960 B | ✅ Keep |
| NotificationDropdown.jsx | 11,050 B | ✅ Keep |
| OpsPortal.jsx | 17,180 B | ✅ Keep |
| PermissionGate.jsx | 2,958 B | ✅ Keep |
| PersonaSwitcher.jsx | 2,651 B | ❌ DELETE Sprint 14 |
| QueryAnalyzerView.jsx | 11,432 B | ✅ Keep — add to Sidebar Sprint 16 |
| RBACManager.jsx | 39,104 B | ⚠️ Rescope to agent permissions Sprint 14 |
| ReportsPage.jsx | 19,214 B | ✅ Keep |
| RunbooksView.jsx | 13,270 B | ✅ Keep — Runbook + Doc Agent connect here |
| SchemaBrowserView.jsx | 13,900 B | ✅ Keep |
| ScorecardsPage.jsx | 23,192 B | ✅ Keep — Scorecard Agent connects here |
| SettingsModal.jsx | 12,939 B | ✅ Keep |
| Sidebar.jsx | 9,506 B | ⚠️ Clean role-based filtering Sprint 14 |
| StandardsPage.jsx | 13,654 B | ✅ Keep |
| StorageView.jsx | 9,414 B | ✅ Keep — add to Sidebar Sprint 16 |
| TemplateGallery.jsx | 53,332 B | ✅ Keep |
| ToastNotification.jsx | 153 B | ❌ Regression — full rebuild Sprint 16 |
| ToolRegistryView.jsx | 41,324 B | ⚠️ Wire multi-account + catalog search Sprint 15 |
| TopBar.jsx | 9,144 B | ⚠️ Add context breadcrumb Sprint 16 |
| TriageView.jsx | 9,418 B | ✅ Keep — Alert Noise Agent connects here |
| UserMenu.jsx | 3,734 B | ✅ Keep |
| WorkspaceBuilder.jsx | 44,789 B | ⚠️ Verify + fix multi-account canvas Sprint 15 |
| WorkspaceSwitcher.jsx | 6,561 B | ✅ Keep — Layer 1 context |
| entityActionsShared.jsx | 11,119 B | ✅ Keep |

### Missing — Must Be Built
| Component | Sprint | Purpose |
|-----------|--------|---------|
| `PlatformContext.jsx` | 13 | React Context provider for all 4 context layers |
| `UserManagement.jsx` | 14 | Admin user CRUD + agent permission grants |
| `AdminDashboard.jsx` | 14 | Admin home — approvals + audit + user summary |
| `AuditLogView.jsx` | 14 | Real-time WebSocket audit log feed |
| `CodeEditor.jsx` | 15 | Monaco Editor as draggable workspace tool |
| `Terminal.jsx` | 15 | xterm.js + WebSocket → SafeExecutor |

---

## 9. SPRINT MAP WITH PROGRESS CHECKS

### Sprint 13 — The Agent Sprint ← CURRENT
**Goal:** 16 real agents live, multi-account aware, PlatformContext defined
**Definition of Done:** `POST /api/agents/run` works for all 16 agents

**Deliverables:**
- 9 new agent files in `backend/agents/`
- 2 existing stubs rebuilt: `security_agent.py`, `tester_agent.py`
- Agent registry: `backend/agents/__init__.py`
- Agents REST router: `backend/routers/agents.py`
- 5 priority connector files in `backend/connectors/`
- `tool_connections` DB table with `account_alias` column
- `PlatformContext` class in backend + `PlatformContext.jsx` in frontend

**Progress Check:**
```
□ GET  /api/agents/              → returns 16 agents
□ POST /api/agents/run           → deploy_agent returns pending_approval for production
□ POST /api/agents/run           → cost_agent returns status: success (no approval)
□ POST /api/agents/run           → infra_agent returns requires_approval: true
□ backend/connectors/            → 5+ connector files (not just registry.py + __init__.py)
□ backend/agents/                → 11+ agent files (not just 2 stubs)
□ tool_connections table         → has account_alias column
□ PlatformContext                → defined in backend and frontend
□ Every agent                    → accepts tool_accounts dict param
□ AgentApprovalsWidget           → can call GET /api/agents/ and list them
□ No agent                       → returns status: failed due to import errors
```

---

### Sprint 14 — The Admin & Users Sprint
**Goal:** Admin dashboard, user management, audit log, role cleanup
**Definition of Done:** Admin login → dashboard → manage users → audit log live

**Deliverables:**
- `src/components/UserManagement.jsx` (NEW)
- `src/components/AdminDashboard.jsx` (NEW)
- `src/components/AuditLogView.jsx` (NEW)
- `backend/routers/audit_log.py` (NEW)
- `backend/routers/users.py` (NEW)
- Collapse RoleContext to Admin/User only
- Rescope RBACManager to agent permissions only
- Delete PersonaSwitcher.jsx
- Wire every AgentResult → audit_log table entry

**Progress Check:**
```
□ Admin login  → AdminDashboard (not regular user dashboard)
□ User login   → WorkspaceBuilder (not admin dashboard)
□ GET  /api/users/                      → returns user list (admin only, 403 for users)
□ POST /api/users/{id}/agent-permissions → grants agent permission to user
□ GET  /api/audit-log/                  → returns paginated audit entries
□ WS   /ws/audit-log                    → streams real-time audit events
□ RoleContext                           → exactly 2 roles: "admin" and "user"
□ PersonaSwitcher.jsx                   → does NOT exist in repo
□ Every agent run                       → writes 1 entry to audit_log table
□ AuditLogView                          → shows live entries as agents run
□ Context switch events                 → logged to audit_log (who switched what when)
```

---

### Sprint 15 — The Workspace Sprint
**Goal:** Drag-drop canvas with multi-account tool cards, Code Editor, Terminal
**Definition of Done:** User drags 3 tools onto canvas, invokes agent, sees result

**Deliverables:**
- `WorkspaceBuilder.jsx` — verified + multi-account canvas fixed
- `src/components/CodeEditor.jsx` (NEW — Monaco)
- `src/components/Terminal.jsx` (NEW — xterm.js + WebSocket → SafeExecutor)
- `ToolRegistryView.jsx` — wired to full tools.txt catalog with multi-account support
- Tool search wired into CatalogPage
- Tool drag from ToolRegistry → WorkspaceBuilder canvas
- Agent invocation from canvas tool card
- Workspace state persisted per user

**Canvas Tool Card Design:**
```
┌──────────────────────────────┐
│ ☁️  AWS                       │
│ Account:  Production          │
│ Region:   us-east-1           │
│ Status:   Connected ✅        │
│ [Switch Account ▾]            │
│ [Run Agent ▶]                 │
└──────────────────────────────┘
```

**Progress Check:**
```
□ User drags GitHub from registry → canvas
□ Dragging AWS → prompts account selector (multi-account)
□ Canvas card → shows tool name, account name, status, Switch Account button
□ "Run Agent" on card → agent selector opens → agent runs → result in right panel
□ Code Editor → Monaco opens with syntax highlighting
□ Terminal → routes commands through SafeExecutor
□ Terminal → blocks dangerous commands (CommandValidator fires)
□ Workspace state → persists on browser refresh
□ WorkspaceSwitcher → switches between saved workspaces without page reload
□ GET /api/tools/  → returns full 110+ tool list from registry
□ CatalogPage search → returns tools alongside catalog entities
```

---

### Sprint 16 — The Hardening Sprint
**Goal:** Zero broken states, no regressions, demo-ready
**Definition of Done:** 10-minute demo walkthrough passes completely

**Deliverables:**
- ToastNotification.jsx full rebuild (currently 153 B — broken)
- IncidentHistory wired into TriageView tabs
- StorageView + QueryAnalyzerView added to Sidebar
- CatalogCopilotPanel fixed
- DORAPage team table completed
- All pages load real backend data (no static/mock)
- Error boundaries on every major page
- Empty states on every list/table
- Loading skeletons on every data fetch
- TopBar context breadcrumb: Workspace › Tool:Account › Environment

**Admin Demo (5 min):**
```
□ Login as admin → AdminDashboard loads with real data
□ User Management → see user list → grant "Deploy Agent" to test user
□ Audit Log → see permission grant logged in real-time
□ Agent Approvals → approve a pending deploy
□ Audit log → updates with approval event immediately
```

**User Demo (5 min):**
```
□ Login as user → WorkspaceBuilder loads
□ Search "github" → GitHub card appears → drag to canvas
□ Card shows "Connected ✅" with account name
□ Click "Run Agent" → Code Review Agent runs → result in right panel
□ Open Terminal → type: kubectl get pods → SafeExecutor validates
□ Open Code Editor → paste code → syntax highlights correctly
□ Logout → workspace saved → Login → workspace restored exactly
```

---

### Sprint 17 — Enterprise Features
- Migration Agent (deferred from Sprint 13)
- SSO / SAML integration
- Multi-tenancy workspace isolation
- Billing / license enforcement
- Mobile responsive pass on all views

---

## 10. AGENT-TO-FRONTEND WIRING

| Agent | Frontend View It Powers |
|-------|------------------------|
| Deploy Agent | DeploymentsView, CICDView |
| Security Agent | CatalogPage, ScorecardsPage |
| Tester Agent | CICDView, LivePipelinesView |
| Infra Agent | InfraBuilderView |
| Incident Agent | TriageView |
| Cost Agent | InfraBuilderView, DashboardView |
| Code Review Agent | CatalogPage, EntityActionsPage |
| Runbook Agent | RunbooksView |
| Catalog Health Agent | CatalogCopilotPanel |
| Pipeline Monitor Agent | LivePipelinesView |
| Auto-Heal Agent | TriageView, HealthDashboard |
| Onboarding Agent | GoldenPathsPage |
| Documentation Agent | RunbooksView, CatalogPage |
| Scorecard Agent | ScorecardsPage |
| Dependency Drift Agent | DependencyGraph |
| Alert Noise Agent | TriageView |

---

## 11. COMPETITIVE POSITIONING

| Feature | Backstage | Port | Cortex | This Platform |
|---------|-----------|------|--------|---------------|
| Agentic AI with HITL | ❌ | ❌ | ❌ | ✅ |
| Multi-account tool connections | ❌ | ⚠️ | ❌ | ✅ |
| 4-layer context switching | ❌ | ❌ | ❌ | ✅ |
| Drag-drop workspace canvas | ❌ | ✅ | ❌ | ✅ |
| Built-in Terminal + Code Editor | ❌ | ❌ | ❌ | ✅ |
| 16 purpose-built agents | ❌ | ❌ | ❌ | ✅ |
| Open source (AGPLv3) | ✅ | ❌ | ❌ | ✅ |
| DORA metrics built-in | ⚠️ | ⚠️ | ✅ | ✅ |
| Alert noise reduction | ❌ | ❌ | ❌ | ✅ |
| Scorecard enforcement agent | ❌ | ⚠️ | ✅ | ✅ |

---

## 12. RULES — NEVER BREAK THESE

Every sprint prompt must follow these rules:

1. **Read this file FIRST** before writing any code
2. **Read the actual backend files** listed in Section 2 before designing agents
3. **Every agent uses `llm_router`** for all reasoning
4. **Every agent uses `safe_executor`** for ANY command execution — never raw subprocess
5. **Every production action** sets `requires_approval=True`
6. **Every agent returns** the standard `AgentResult` schema from Section 6
7. **Every agent accepts** `tool_accounts: dict` for multi-account context
8. **Every agent accepts** `context: PlatformContext` for full 4-layer context
9. **Exactly 2 roles** — Admin and User. Never add a 3rd role.
10. **Never remove HITL** from any production-targeting action
11. **Check `registry.py`** before building new connectors — extend don't duplicate
12. **Check component sizes** in Section 8 before rebuilding existing components
13. **Context switch events** must always be written to the audit log
14. **Tool connections** always use the `tool_connections` table — never hardcode credentials
