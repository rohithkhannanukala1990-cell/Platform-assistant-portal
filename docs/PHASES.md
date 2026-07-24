# Platform phases (0–7)

Short checklist of what each hardening/refactor phase changed.

## Phase 0 — Security baseline
- [x] Remove placeholder users / unsafe defaults where applicable
- [x] Webhook HMAC over raw request body
- [x] CORS tightened for real deployments
- [x] `ENABLE_DEMO_DATA` / `ENV` gates for demo fixtures

## Phase 1 — Extract ops routers
- [x] Incidents, webhooks, notifications moved out of a fat `main.py`

## Phase 2 — Extract tools / imports / context
- [x] Tool Registry, import APIs, user context routers

## Phase 3 — Thin composition root
- [x] `main.py` as app factory + router includes
- [x] Infra/CI/CD, health, platform misc + `demo_fixtures`

## Phase 4 — Database split
- [x] `backend/db/` models + repositories
- [x] Compatibility shim in `database.py`

## Phase 5 — UX empty states & connectors
- [x] Lazy frontend routes, `no_data` empty states
- [x] WorkspaceBuilder split; GitHub connector error mapping / health probes

## Phase 6 — Real GitHub (read-only)
- [x] Connector: repos, PRs, files, workflow runs/jobs
- [x] `/api/github/*` routes + Tool Registry repos panel
- [x] Agents grounded on live GitHub (no invented data when disconnected)
- [x] Active CI runs prefer GitHub, then demo, else `no_data`

## Phase 7 — Hardening
- [x] Login rate limit (`5/minute`), failed-login audit (`login_failed` / outcome denied), per-process lockout
- [x] Chat / triage / agent run limits (`10/minute`); webhooks stay `5/minute`
- [x] Metrics: webhook signature failures, demo data served, GitHub API requests
- [x] Docs: `ARCHITECTURE.md`, this file
- [x] Final verification: pytest, npm test, npm build
