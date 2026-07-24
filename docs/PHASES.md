# Platform phases (0–9 + L1–L2)

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

## Phase 8 — Secrets + tool account scoping
- [x] Fernet encrypt-at-rest (`SECRETS_ENCRYPTION_KEY`) for ToolAccount credentials
- [x] GET APIs expose `has_credentials` only (no raw/decrypted secrets)
- [x] GitHub account resolution scoped to user/workspace — no global active-account fallback
- [x] `owner_user_id` / `workspace_id` on ToolAccount; agents stamp PlatformContext from auth + UserContext

## Phase 9 — Tenant + workspace isolation hard-fail
- [x] `backend/services/isolation.py` helpers; 404 on tenant mismatch
- [x] Middleware forces user `tenant_id`; `ENFORCE_WORKSPACE_ISOLATION` documented
- [x] Incidents, tool accounts, agent runs, catalog, user_context scoped
- [x] Agent runs persist `user_id` / `tenant_id` / `workspace_id`
- [x] Cross-tenant tests in `test_phase9_isolation.py`

## Phase L1 — Multi-provider LLMService (no Gemini/Ollama SDKs)
- [x] `backend/ai/providers/` — OpenAI-compatible + Anthropic
- [x] `backend/ai/llm_service.py` as sole chat entry; `llm_router` thin shim
- [x] Removed `ollama` / `google.genai` production imports and packages
- [x] Defaults: `LLM_DEFAULT_PROVIDER=openai`, `LLM_DEFAULT_MODEL=gpt-4o-mini`
- [x] UI labels use model from API / `LLM`; tests cover `LLM_MOCK=1`

## Phase L2 — Multi-LLM DB config + API + UI
- [x] Expanded `LLMProviderConfig` (base_url, api_key_vault_ref, priority, metadata_json, …)
- [x] `/api/llm` status/providers CRUD/test; keys encrypted; GET masked
- [x] `LLMService` resolution: explicit → env → DB priority → env keys → mock
- [x] Settings LLM providers panel; AIAssistant/TopBar use `/api/llm/status`
