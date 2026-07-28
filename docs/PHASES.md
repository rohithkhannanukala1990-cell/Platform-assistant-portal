# Platform phases (0–17 + L1–L2 + M1–M2 + G1–G2)

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

## Phase 10 — GitHub product loop
- [x] PR/run/jobs detail routes under `/api/github`
- [x] Native + inbound GitHub webhooks → incidents (HMAC, delivery-id idempotency)
- [x] `code_review_agent` / `pipeline_monitor_agent` grounded via scoped connector
- [x] UI: GitHub PRs + Actions views with empty states when disconnected

## Phase 11 — Incident command center + HITL UX
- [x] Incident detail API: timeline, github_refs, pending_approval, execution_log
- [x] Approve / reject require auth + tenant scope; dry-run before execute; audit actor
- [x] No fake Slack/ServiceNow success when demo data disabled
- [x] UI: `/incidents/:id` command center (timeline, plan, commands, Approve/Reject/Re-triage/Run agent)
- [x] `POST .../run-agent` stamps PlatformContext from current user; results append to timeline

## Phase 12 — K8s + PagerDuty connector parity
- [x] `k8s_access` / `pagerduty_access`: scoped ToolAccount resolve + SecretBox decrypt (no global fallback)
- [x] Read-only `/api/k8s/*` and `/api/pagerduty/*` (auth required; 400 when not connected)
- [x] Agents (`infra_agent`, `incident_agent`, `auto_heal`) use `try_*_connector`; skip when disconnected
- [x] Health probes: configured flag + optional ping via connectors
- [x] UI: `/k8s` and `/pagerduty` panels with empty states

## Phase 13 — Enterprise identity
- [x] `MFA_REQUIRED_ROLES` / settings: admins without MFA get 403 `mfa_enrollment_required`
- [x] SSO status + clear "not configured"; `/auth/callback` handoff; no fake SSO success
- [x] JWT `jti` session registry: `GET/POST /api/auth/sessions`, `/api/auth/logout`
- [x] `GET /api/audit/export?from=&to=` admin CSV/JSON (login/mfa/approve events)

## Phase 14 — Reliability
- [x] `WebhookDelivery` ledger: claim delivery_id after HMAC; duplicates → HTTP 200
- [x] Celery triage/notify retries with backoff; failures → `celery_task_failure` + metrics
- [x] Queues documented (`celery`, `triage`, `notify`) in ARCHITECTURE.md
- [x] Login lockout counters in Redis when available (in-process fallback)
- [x] `docs/RUNBOOK_BACKUP.md` (pg_dump/restore, exclusions, secret-key warning)

## Phase 15 — Observability + enterprise beta go/no-go
- [x] Metrics: HTTP, LLM latency, connector errors, webhook failures, GitHub API, login failures, Celery queue depth
- [x] Grafana dashboard JSON under `deploy/grafana` + compose provisioning
- [x] Alert rule docs: API 5xx rate, webhook sig failures, Celery queue depth
- [x] Production sample env (`.env.production.example`): demo off, isolation on, required secrets listed
- [x] `docs/BETA_GONOGO.md` checklist
- [x] Smoke: `scripts/beta_smoke.sh` + `pytest -m smoke`

## Phase M1 — MCP client (external servers)
- [x] `backend/mcp/`: types, client (JSON-RPC stdio|sse), registry, hitl_bridge
- [x] `MCPServer` / `MCPToolCall` tables; env encrypted; secrets masked on GET
- [x] `/api/mcp/servers` CRUD + test; `/api/mcp/tools` catalog; `/api/mcp/tools/call` → HITL
- [x] Read tools may auto-run; write/dangerous → `pending_approval`
- [x] `chat_with_tools` max_rounds=3; optional `use_mcp` on chat
- [x] Settings UI: MCP servers panel + read-only tools catalog
- [x] Tests mock tools/list + tools/call; dangerous tool never executes until approved

## Phase M2 — Portal as MCP server + agent integration
- [x] `python -m backend.mcp.server_app` — stdio MCP server, `PORTAL_MCP_TOKEN` auth
- [x] Read tools: incidents, catalog, search, health, GitHub repos (scoped)
- [x] Write tools (HITL only): `portal_propose_remediation`, `portal_run_agent`
- [x] Agents: MCP catalog in context when `MCP_ENABLED`; GitHub agents prefer MCP then connector
- [x] `docs/MCP.md` + ARCHITECTURE / `.env.example` updates

## Phase 16 — Compliance pack
- [x] Audit retention setting (`audit_log_retention_days`) + prune job uses it
- [x] Immutable audit export with simple SHA-256 hash chain (`?immutable=true`)
- [x] `docs/THREAT_MODEL.md` (STRIDE) + `docs/COMPLIANCE.md` control mapping
- [x] CI: `pip-audit` + `npm audit` on ci.yml and pr-check.yml
- [x] Dependency pin review noted in COMPLIANCE.md / requirements
- [x] Privacy: audit detail redaction; tests assert tokens/passwords never stored

## Phase 17 — HA / scale hardening
- [x] Login lockout + SlowAPI rate limits Redis-backed when Redis URL set (`RATELIMIT_STORAGE_URL` / `CELERY_BROKER_URL` / `REDIS_URL`)
- [x] DB indexes: tenant_id, workspace_id, incident timestamp, webhook delivery_id (+ related hot columns)
- [x] Pagination defaults (`page`/`page_size`, default 50) on large list endpoints
- [x] `docs/SCALING.md` — multi-replica API, JWT (no sticky sessions), Celery workers, load smoke notes

## Phase G1 — Guardrails v2: command policy engine
- [x] `CommandPolicyRule` table + seeded defaults (deny / allow / require_approval, production catch-all)
- [x] `backend/services/command_policy.py` — allow | deny | require_approval with reasons + matched_rule_ids; shlex prefix matching; parse failure fails closed
- [x] Baseline regex blocklist still runs first (unconditional deny)
- [x] `CommandValidator.validate_with_context`; SafeExecutor re-evaluates per step with audit (`command_policy_denied` / `command_policy_approval_required`)
- [x] Orchestrator: deny → failed run; require_approval → forced `requires_approval`
- [x] Incident + agent-run approval endpoints pass `approved=True` (HITL); ws terminal refuses approval-gated commands
- [x] `/api/policies/commands` CRUD (admin) + `/evaluate` (any user); Settings → Command policy panel
- [x] `docs/COMMAND_POLICY.md`

## Phase G2 — Agent platform v2 (grounding + evidence + guardrails)
- [x] `AgentResult` extended: evidence, confidence, grounding, policy, errors, recommended_actions
- [x] BaseAgent helpers: `_no_data_result`, `_evidence`, `_ground_github/_k8s/_pd`, `_apply_command_policy`, `_finalize_with_policy`, `GROUNDING_RULES`
- [x] All 17 agents upgraded — missing tools → no_data; live data → evidence; no invented connector facts
- [x] Orchestrator: require user_id, persist evidence/grounding, command cap 25, secret redaction, audit started/completed/denied_policy
- [x] UI: grounding badge, evidence list, policy summary, Tool Registry link on none
- [x] `docs/AGENTS.md` catalog + HITL matrix
