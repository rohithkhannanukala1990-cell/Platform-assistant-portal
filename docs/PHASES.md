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

# Phase 8 — Secrets + tool account scoping
- [x] Fernet encrypt-at-rest (`SECRETS_ENCRYPTION_KEY`) for ToolAccount credentials
- [x] GET APIs expose `has_credentials` only (no raw/decrypted secrets)
- [x] GitHub account resolution scoped to user/workspace — no global active-account fallback
- [x] `owner_user_id` / `workspace_id` on ToolAccount; agents stamp PlatformContext from auth + UserContext
