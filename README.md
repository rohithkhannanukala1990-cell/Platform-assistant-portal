# AIOps Platform Assistant

[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)

Licensed under the [Apache License 2.0](LICENSE) — self-hosted, and your data stays on your infrastructure.

It's 3am and you're paged. Before you can start fixing anything, you spend twenty minutes gathering context: which service owns this, what changed recently, what the runbook says, who else needs to know. You fix it, the page clears, and by morning there's no record of what you actually decided or why — just a resolved alert and a fuzzy memory.

This portal's answer: an alert arrives, an AI agent gathers the real context (recent deploys, related incidents, runbook matches, live infrastructure state), proposes a specific remediation with the exact commands it would run, a human approves it from the web UI, Slack, or a terminal, it executes, and every step is logged.

Every AI-ops tool promises automation. The hard problem was never getting a model to suggest `kubectl rollout restart` — it's being confident enough to let it run. This portal's answer is that it never does, unattended, in production. That constraint shapes almost everything described below.

## Current status

This has never run in production. There are no deployments, no track record, no customer using it today. A technical evaluator will work that out in about ten minutes from a repository with no release history — better to say it plainly up front than have it discovered. The honest framing is: **production-candidate, pilot-ready, track record empty.** The [pilot playbook](docs/PILOT_PLAYBOOK.md) is built around that gap — a two-week structured evaluation designed to find what breaks before it matters, not a sales pitch dressed as documentation.

## The shape of it

- **21 AI agents**, grouped by area, each grounded in real tool data — never inventing a metric, PR number, or pod name it can't cite evidence for (see [Safety model](#safety-model)).
- **12 connectors** — GitHub, AWS, Kubernetes, PagerDuty, Slack, Jira, ServiceNow, Okta, ArgoCD, Prometheus, Confluence, and generic outbound webhooks.
- **A workflow engine** that chains agent and connector steps behind cron, event, or manual triggers — with rate limits, concurrency caps, a forced first dry-run, and a global kill switch.
- **One approval inbox** for everything awaiting a human decision — agent runs, workflow steps, access requests, change records — reachable from the web UI, Slack, or the terminal, with the same permission checks everywhere.
- **A terminal** that runs real shell commands (and `@agent`-prefixed AI tasks) through the same two-layer policy engine and approval gate as everything else.
- **A code editor** with autosave, GitHub-aware repo browsing, agent actions on a text selection, and an approval-gated propose-PR flow.
- **Compliance evidence collection** mapped to six concrete SOC 2 controls, with gap scanning that surfaces things like a production change with no matching change record — before an auditor finds it.

### Agents by area

| Area | Agents |
|---|---|
| **Incidents** | `incident`, `alert_noise`, `auto_heal`, `oncall`, `runbook` |
| **Delivery** | `deploy`, `pipeline_monitor`, `code_review`, `tester`, `dependency_drift`, `documentation` |
| **Platform** | `infra`, `migration`, `cost`, `catalog_health`, `scorecard`, `onboarding` |
| **Governance** | `security`, `compliance`, `access`, `change` |

Full descriptions, connectors each one grounds against, and read-only vs. mutating status: [docs/AGENTS.md](docs/AGENTS.md). Day-to-day usage: [docs/USER_GUIDE.md](docs/USER_GUIDE.md).

### Workflows

A workflow chains steps — agent calls, connector calls, conditional branches — behind one of three triggers: **manual**, **schedule** (cron), or **event**. Guardrails apply regardless of who or what triggered it:

- **Rate limits** — `max_runs_per_hour` (default 12) rejects further runs with a 429 once hit.
- **Concurrency caps** — `max_concurrent_runs` (default 1) either queues or drops an over-limit run, depending on configuration.
- **Forced first dry-run** — the first time an automatic (schedule or event) trigger would fire, it's forced into a dry run regardless of the workflow's own setting. It only executes live after an admin explicitly calls `approve-live`.
- **Re-approval after edits** — changing a workflow's steps clears that live approval. It goes back to forced-dry-run until someone re-approves.
- **Global kill switch** — one flag suspends every automatic trigger platform-wide without touching individual workflow definitions.

### Approvals — one inbox, three surfaces

Every pending decision — an agent run, a workflow step, an access request, a change record — lands in one inbox, backed by the same approve/reject functions whether it's opened from the web UI, a Slack message, or a terminal `@agent` command. Approving is a database compare-and-swap (`UPDATE ... WHERE status = 'pending_approval'`, checked by row count), not a check-then-update — two people racing to approve the same item can't both win.

What gets approved is frozen at proposal time: the exact command, file content, or Terraform plan a reviewer looked at is what executes. It is never re-read or re-planned after approval, so there's no window where the world changes between "looks safe" and "runs."

Two categories are deliberately harder than a button click:
- **Destroying Terraform resources** requires typing the workspace name back exactly.
- **Destructive migrations** require two distinct approvers.

Neither of these gets Slack Approve/Reject buttons — Slack only gets a link back to the portal, because a thumb can hit the wrong button on a phone and these two categories are the ones you can't undo.

### Terminal

Real shell execution, running the same commands a developer would type — passed through the identical two-layer command policy described below. `@agent <task>` invokes an AI agent inline instead of a shell command (`@incident`, `@security`, `@deploy`, `@cost`, and others; `@help` lists them all). A command that needs approval doesn't dead-end the session — it waits inline and runs the moment someone approves it.

### Code editor

Local scratch files always work, with autosave. Browsing and editing files from an actual repository needs a GitHub connection. Selecting text exposes agent actions (review, explain, fix) — suggestions always come back as an accept/reject diff, never applied automatically. Proposing a pull request checks whether the file changed upstream since it was opened; if it has, the proposal is blocked with an explicit "this file changed upstream, reload or force" message rather than silently overwriting someone else's edit.

### Compliance

Evidence collection is mapped to six SOC 2 controls: logical access (CC6.1), timely access removal (CC6.2), least privilege (CC6.3), system monitoring (CC7.2), change management (CC8.1), and incident response (CC7.4). The genuinely useful part isn't the evidence export — it's the gap scan, which flags things like a production change with no matching change record, before an auditor asks about it.

## Safety model

Two layers sit between any agent-proposed command and execution.

1. **A baseline blocklist** (`backend/command_validator.py`) — a fixed regex list of catastrophic patterns (`rm -rf`, `DROP TABLE`, `kubectl delete namespace`, credential exfiltration via `curl | bash`, and similar). It always runs, first, and cannot be overridden by any policy rule. A match is an unconditional deny.
2. **A database-backed policy engine** (`backend/services/command_policy.py`) — rules scoped by role, environment, tool, and command prefix/regex, evaluated in priority order, each resolving to `allow`, `deny`, or `require_approval`.

Evaluating a list of commands takes the worst outcome across all of them — one `deny` denies the batch, one `require_approval` (with no denies) queues the batch. A command the policy engine can't even parse becomes `require_approval` rather than silently passing: it fails closed. The same fail-closed default applies to production generally — anything with no matching rule in a production environment defaults to `require_approval`, not `allow`.

Approvals are race-safe by construction (the compare-and-swap pattern above) and frozen at proposal time (nothing is re-read or re-planned after approval) — both described in the Approvals section above, because they're inbox mechanics as much as policy mechanics.

Underneath all of it is a grounding contract every agent's result carries: `live`, `partial`, `none`, or `demo`. Agents are instructed to reason only over an EVIDENCE block assembled from real connector calls — never to invent a metric, PR number, pod name, or ticket ID. When a required tool isn't connected, an agent returns `grounding=none` and says so explicitly, instead of returning an empty result that reads like a clean scan.

## Local development

Every path below runs with **zero required configuration** — no `.env` file, no API keys. Agent calls return canned mock responses (`LLM_MOCK=1` by default everywhere except production), and a **"Mock mode"** badge appears in the top bar whenever that's active, so a demo is never confused about whether a response was real.

| | Path 1 — `make dev` | Path 2 — `make up` | Path 3 — No Docker |
|---|---|---|---|
| **Time (warm)** | ~20–30s | already-built: seconds | seconds |
| **Time (first ever)** | a few minutes (one-time compile + `npm install`) | ~5 minutes (CLI tool downloads) | seconds (after `pip install`/`npm install`) |
| **Database** | SQLite | PostgreSQL | SQLite |
| **Redis / Celery** | in-process fallback | real | in-process fallback |
| **Terminal CLI tools** | not installed (reports "not installed") | kubectl/helm/terraform/aws-cli bundled | whatever's on your `PATH` |
| **Observability stack** | none | Prometheus/Grafana/Loki | none |
| **Good for** | trying it out, UI/frontend work | anything touching real terminal execution or background jobs | backend/frontend code changes with fast iteration |

Pick one; you don't need more than one running at a time (they'd fight over the same ports).

### Path 1 — Fastest: `make dev` (Docker, SQLite, ~30s warm / a few minutes cold)

Prerequisites: Docker with Compose. No CLI tools, no `.env` file, no Postgres/Redis. `make` is optional — it ships with macOS and most Linux distributions but **not** with Windows; every `make` command below is followed by the raw equivalent.

```bash
make dev
#  — or, without make:
docker compose -f docker-compose.dev.yml up
```

Open http://localhost:5173 and log in with `admin` / `Admin123!`.

- **First time ever**: the backend image has to compile `lxml`/`xmlsec` from source (a one-time libxml2-version fix — see comments in `backend/Dockerfile`), which takes a few minutes, and the frontend container runs `npm install` fresh, which adds roughly another minute. Both are cached afterward (Docker layer cache for the backend as long as `requirements.txt` doesn't change; a persisted `node_modules` volume for the frontend as long as you don't `docker compose -f docker-compose.dev.yml down -v`).
- **Every time after that**: backend becomes healthy in ~20–30 seconds; frontend reuses its cached `node_modules` and starts in a few more.
- **What works**: login, all 21 agents (mock responses), the workflow engine, the approval inbox, the code editor (local files — create/save/format), the terminal (shell + `@agent` syntax), workspaces, dashboard, catalog.
- **What doesn't**: kubectl/helm/terraform/aws-cli aren't in this image — the terminal reports them as "not installed" instead of crashing (`backend/services/terminal_capabilities.py`). No Postgres/Redis/Celery/nginx/Prometheus/Grafana/Loki — background jobs (webhook delivery, scheduled workflows) run in-process instead of via Celery, which is fine for local testing but not how production behaves.

### Path 2 — Full stack: `make up` (Docker, Postgres + Redis + real terminal tools, ~5 minutes first build)

Prerequisites: Docker with Compose. `make` optional, as above.

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
LLM_MOCK=1 SECRET_KEY=dev-only-not-for-production uvicorn backend.main:app --reload --port 8000
```

`SECRET_KEY` is **required** — the backend deliberately refuses to start without one outside test environments (`RuntimeError: SECRET_KEY must be set to a non-empty non-default value`). The Docker paths supply it from the compose files, so this is the only path where you pass it yourself. Any non-empty, non-default value works locally; use a real random secret anywhere that isn't your laptop.

No `DATABASE_URL` needed — the backend falls back to a local SQLite file (`backend/incidents.db`) automatically. Redis is optional everywhere in the request path (login lockout, rate limiting, workflow triggers, and Celery task dispatch all have working in-process fallbacks) — `/health/ready` will show `"redis": {"status": "skipped"}` and nothing breaks.

Frontend (separate terminal):

```bash
npm install
npm run dev        # http://localhost:5173, proxies /api, /auth, /ws to :8000
```

Log in with `admin` / `changeme123` (the code-level default when `DEFAULT_ADMIN_PASSWORD` isn't set — different from the `Admin123!` shown on the login screen, which matches the two Docker paths above where it's set explicitly in the compose files). Set `DEFAULT_ADMIN_PASSWORD=Admin123!` before first startup if you want them to match.

**What works**: login, mock agent runs, the editor (local files), the terminal, workspaces. **What doesn't**: the terminal can only run binaries actually on your machine's `PATH` — there's no image bundling kubectl/helm/terraform/aws-cli here, so it's whatever you have installed locally.

Backend tests:

```bash
pytest backend/tests/ -v
```

### Why `npm run dev` alone isn't "running the app"

This confuses people every time, so it's worth being explicit. The portal is **two processes**: a FastAPI backend on port 8000, and a Vite frontend on port 5173. `npm run dev` starts only the frontend. On its own, you get a UI that loads and then fails every single API call — login included.

`vite.config.js` proxies `/api`, `/auth`, and `/ws` from port 5173 to port 8000, so the browser only ever talks to 5173, and Vite quietly forwards backend calls behind the scenes. That's what makes the frontend *look* like the whole app right up until the backend isn't running, at which point every request just fails.

- **`make dev`** runs both processes in Docker — including `npm run dev`, inside a container — so this never comes up.
- **`npm run dev` on its own** is for frontend-only work. It needs `uvicorn` running separately in another terminal (Path 3, above).

**Diagnostic**: if the page loads but login fails, or spinners never resolve, the backend isn't running. Check:

```bash
curl http://localhost:8000/health/live
```

Other npm scripts, for reference:

| Script | What it does |
|---|---|
| `npm run dev` | Frontend dev server only (see above — needs the backend running separately) |
| `npm run build` | Type-checks, then produces a static production bundle. **Not how you run the app locally** — it's the deployment artifact. |
| `npm run test` | Frontend unit tests (Vitest) |
| `npm run lint` | ESLint |
| `npm run typecheck` | `tsc --noEmit` |
| `npm run preview` | Serves the `build` output locally, for sanity-checking a production build |

### Makefile reference

`make` (no target) lists every command with a one-line description. 13 targets: `up`/`down` (full stack), `dev`/`dev-down` (lean stack), `logs`, `test-backend`, `test-frontend`, `smoke`, `rebuild`/`rebuild-lean` (no-cache), `db-reset`/`db-reset-dev`, plus `help`.

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

## Which features need which connector

Agents and integrations degrade gracefully without a connector configured — the dashboard's setup checklist (visible on first login) tracks how many of the 12 supported connectors are connected, and calls out **GitHub and PagerDuty** as the two most agents depend on. A few concrete examples, pulled from what the code actually checks:

- **Code editor's repo browsing** (as opposed to local scratch files, which always work) needs a GitHub connection — `backend/services/editor_service.py` returns *"GitHub is not connected. Open Settings → Tool Registry and connect a GitHub account."* until one is added.
- Most integrations (GitHub, AWS, Kubernetes, ArgoCD, ServiceNow, Prometheus, Okta, and more) are connected **per-account** under Settings → Tool Registry — there's no env var for them.
- Two exceptions are configured via top-level backend env vars instead: **Slack** (`SLACK_WEBHOOK_URL`, plus `SLACK_SIGNING_SECRET` — mandatory for verifying inbound Slack requests, not optional) and **Jira** (`JIRA_DOMAIN` / `JIRA_EMAIL` / `JIRA_API_TOKEN` / `JIRA_PROJECT_KEY`), both in `backend/.env.example`.

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
- `LLM_MOCK` — `1` for canned agent responses (the default everywhere except production), `0` for live model calls (requires `OPENAI_API_KEY` or `ANTHROPIC_API_KEY`).

## Testing

```bash
# Backend: 57 test files
pytest backend/tests/ -v
#  — or, via Docker:
docker compose run --rm -e DATABASE_URL=sqlite:////tmp/test.db backend python -m pytest backend/tests/ -q

# Frontend
npm run test

# End-to-end smoke test (needs a server running on :8000)
python3 scripts/mock_portal_smoke.py    # Windows: use `python` — `python3` hits the Microsoft Store stub
make smoke
```

## Tech stack

| Layer | Technology |
|---|---|
| Frontend | React 18, Vite 5, Tailwind CSS 3, React Router 7, TypeScript (incremental) |
| Backend | FastAPI, SQLModel, Celery |
| Data | PostgreSQL 16 (production) / SQLite (local dev), Redis 7 |
| Observability | Prometheus, Grafana, Loki |
| Auth | JWT sessions, optional SAML SSO and Google OAuth |

## Project layout

```
backend/          FastAPI app
  agents/         21 specialist AI agents + BaseAgent contract
  routers/        47 files of HTTP API endpoints
  services/       Business logic — policy engine, approvals, workflows, connectors access
  connectors/     12 external tool integrations (GitHub, AWS, Kubernetes, Slack, and more)
  db/             SQLModel models and engine setup
  tests/          57 pytest files (runs in CI)
src/              React frontend
  components/     Pages and shared UI primitives (components/ui)
docs/             Architecture, user guide, threat model, runbooks, pilot playbook
deploy/           Production deployment assets
nginx/ grafana/ prometheus/   Infrastructure configs for the compose stack
```

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
| [USER_GUIDE.md](docs/USER_GUIDE.md) | How to use the portal day-to-day — agents, terminal, editor, workflows, approvals, environments, workspaces |
| [PILOT_PLAYBOOK.md](docs/PILOT_PLAYBOOK.md) | Two-week structured evaluation plan for a team deciding whether to adopt this |
| [ARCHITECTURE.md](docs/ARCHITECTURE.md) | System design |
| [AGENTS.md](docs/AGENTS.md) | Agent catalog, contracts, and the grounding/HITL rules every agent follows |
| [COMMAND_POLICY.md](docs/COMMAND_POLICY.md) | The two-layer command policy engine, in depth |
| [THREAT_MODEL.md](docs/THREAT_MODEL.md) | Security analysis |
| [COMPLIANCE.md](docs/COMPLIANCE.md) | Control-to-feature mapping (SOC 2 and general enterprise controls) |
| [PRODUCTION_READINESS.md](docs/PRODUCTION_READINESS.md) | Go-live checklist |
| [SCALING.md](docs/SCALING.md) | Capacity planning and load-testing notes |
| [RUNBOOK_BACKUP.md](docs/RUNBOOK_BACKUP.md) | Database backup and restore procedure |
| [MCP.md](docs/MCP.md) | Model Context Protocol client and server, including HITL for mutating tools |
| [ONCALL.md](docs/ONCALL.md) | On-call visibility via PagerDuty — scheduling stays in PagerDuty |
| [product_comparison.md](docs/product_comparison.md) | Honest comparison against adjacent tools |
| [CONTRIBUTING.md](CONTRIBUTING.md) | How to set up, test, and the safety invariants not to break |
| [SECURITY.md](SECURITY.md) | How to report a vulnerability |

## License

Apache License 2.0 — see [LICENSE](LICENSE) for the full text.

Apache 2.0 rather than MIT deliberately: it carries an express patent grant and a
patent-retaliation clause. This project ships a command policy engine, an approval
model, and a compliance evidence collector — the areas most likely to attract
patent questions in enterprise procurement, where MIT's silence on patents gets
noticed.

Contributions are accepted under the same license (Apache 2.0 §5). There are no
per-file license headers; the LICENSE file and package metadata carry it.
