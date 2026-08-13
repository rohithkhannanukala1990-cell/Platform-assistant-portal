# Platform phases (0–17 + L1–L2 + M1–M2 + G1–G7 + P0…)

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

## Phase G3 — Postmortem generation (incident.io / PD Scribe gap)
- [x] `IncidentPostmortem` model — versioned markdown per incident + tenant
- [x] `POST /api/incidents/{id}/postmortem/generate` — auth + tenant-scoped; builds context from incident fields, timeline, triage, commands, agent-run evidence
- [x] LLM via `llm_service` only; `LLM_MOCK` returns deterministic section markdown (Summary, Impact, Detection, Root cause, What went well, What went wrong, Action items, Timeline)
- [x] Timeline section grounded — only events from stored/synthesized timeline data
- [x] `GET /api/incidents/{id}/postmortem` — latest version; `PUT` edit; `GET .../download` markdown attachment
- [x] Audit event `postmortem_generated`
- [x] Incident Command Center UI — Generate / Regenerate, Edit, Download
- [x] `backend/tests/test_phase_g3_postmortem.py` — mock LLM sections, cross-tenant 404, version + audit

## Phase G4 — On-call visibility + rules-based alert correlation
- [x] `pagerduty_access` + connector `list_oncalls` with schedule/service filters
- [x] `GET /api/oncall/now?service=&schedule_id=` — tenant-scoped on-call now
- [x] Ops dashboard + PagerDuty view: **Who is on-call** widget + link to PagerDuty (`docs/ONCALL.md` — scheduling stays in PD)
- [x] `AlertRule` model: match service/severity/title_regex, `group_window_sec`, actions (`create_incident` | `suppress` | `attach_existing`), priority, enabled
- [x] Rules applied on webhook ingest (`ingest_webhook_alert` / Celery tasks) before triage
- [x] Metrics: `alerts_suppressed_total`, `alerts_grouped_total`
- [x] Admin CRUD: `/api/alert-rules` + Settings **Alert rules (v1)** table
- [x] `alert_noise_agent` uses configured rules; UI label **Rules-based correlation** (never ML)
- [x] `backend/tests/test_phase_g4_oncall_alerts.py` — suppress, group window, oncall mock, tenant scope

## Phase G5 — Connector pack (first-class vs MCP long-tail)
- [x] Slack — scoped access, channels read, notify (Admin/HITL), webhook in SecretBox
- [x] Prometheus — scoped access, alerts + query (read-only)
- [x] Outbound Webhook — customer URL for portal events (deliver = Admin/HITL)
- [x] Argo CD — scoped access, applications health (read-only)
- [x] Optional ServiceNow — incident create via webhook HITL
- [x] Registry `get_connector` + health probes; UI empty states + Integrations banner
- [x] `docs/ARCHITECTURE.md` first-class vs MCP; `backend/tests/test_phase_g5_connectors.py`

## Phase G6 — Catalog self-service actions + evidence-based scorecards
- [x] `CatalogAction` model — name, entity_kind, action_type, payload_template, risk, require_hitl, tenant_id
- [x] API list/execute (`/api/catalog-actions`, `/api/catalog/{id}/catalog-actions`, execute); HITL → AgentRun `pending_approval`
- [x] Built-ins: `run_golden_path`, `request_scorecard_refresh`, `open_incident`, `propose_deploy` (HITL)
- [x] Catalog entity Actions panel — Self-service execute + legacy entity actions
- [x] Scorecards v2 checks: has_owner, has_repo, has_runbook_url, ci_green, oncall_link, tier_set (weights + `last_evidence_json`)
- [x] Optional AI narrative via `scorecard_agent` from checks only; UI pass/fail evidence breakdown
- [x] `backend/tests/test_phase_g6_catalog_scorecards.py` — no network; HITL on propose_deploy
- [x] Honest ~ vs ✓ for Port/Backstage-style scorecards/actions — see `docs/product_comparison.md`

## Phase G7 — Production HA compose baseline + pilot readiness
- [x] `deploy/docker-compose.prod.yml` — api×2, celery×2, postgres, redis, nginx upstream (no SQLite)
- [x] Prod defaults: `ENABLE_DEMO_DATA=false`, `ENFORCE_WORKSPACE_ISOLATION=true`, `ENV=production`
- [x] `/health/live` + `/health/ready` (db + redis); `/ready` alias
- [x] `docs/PILOT_PLAYBOOK.md` — 2-week design partner, metrics, feedback
- [x] `scripts/pilot_smoke.sh` HA smoke (expanded in P6: agents + policy evaluate)
- [x] `docs/BETA_GONOGO.md` G1–G6 + G7 checkboxes; `docs/product_comparison.md`
- [x] `backend/tests/test_phase_g7_ha_pilot.py` — ready logic + compose/config defaults

## Phase P0 — Full repo audit inventory (no fixes)
- [x] Full-repo audit inventory — P0–P3 + wontfix issues with file:line, invariants, P1–P8 mapping
- [x] Pytest collect-only green (258); no code behavior changes in P0

## Phase P1 — P0 blockers + critical P1 security/data-plane
- [x] Approval races — CAS claim for agents, incidents, MCP HITL, AI executions (`services/approval_claim.py`)
- [x] Tenant isolation — scorecards, entity actions, catalog search/deps, incident approvals, tools matrix/categories
- [x] AuthZ — admin-only agent/incident approve+reject; entity action create admin-only
- [x] SSL — Argo CD `verify=True` by default; never insecure in production ENV
- [x] SSRF — outbound webhook URL allowlist (http/https) + block private/link-local/metadata/`file://`
- [x] SafeExecutor / policy — production unmatched → `require_approval`; refuse execute without `approved=True`
- [x] Demo gate — `monitor_cicd_pipelines` no-op when `ENABLE_DEMO_DATA=false`
- [x] Weak admin — refuse `seed_default_admin` in production for weak `DEFAULT_ADMIN_PASSWORD`
- [x] CORS — no `*` in production; deny-all if origins unset
- [x] Container hygiene — `.dockerignore`, non-root `USER`, `public/.gitkeep`
- [x] Latent policy holes — golden-path `tenant_id`; clear read_only `commands`
- [x] `backend/tests/test_phase_p1_production_blockers.py` — SSL, SSRF, demo, executor, weak admin, CORS
- [x] Pytest green (268); backlog P0 + critical P1 marked `[x]`; no P2 feature work
- [x] Prod/CI audit follow-up: frontend tmpfs; secrets fail-fast (`${VAR:?err}` + reject empty `SECRET_KEY`); SAML/Google/LLM/webhook env passthrough; daily health workflow `pipefail` + treat curl failure as critical

## Phase P2 — API correctness, reliability, observability (non-agent)
- [x] Webhooks — empty alerts/evalMatches no longer 500; invalid HMAC stays 403; duplicate `delivery_id` → 200; failed deliveries reclaimable
- [x] Celery — `delivery_id` idempotency on inbound webhook; permanent errors no retry; monitor_cicd DLQ only after max retries + backoff
- [x] Approvals — double-approve covered by CAS (agents/incidents) + regression tests
- [x] `/health/ready` — 503 when DB down; compose/CI/daily health prefer ready
- [x] Pagination — `MAX_PAGE_SIZE=100`; Query `le=100` on list endpoints
- [x] Rate limit — Redis when URL set; documented fail-open API / login memory fallback
- [x] Metrics — `_safe_label` + HTTP middleware never throws on bad labels
- [x] CI Python 3.12; liveness UTC timezone-aware
- [x] `backend/tests/test_phase_p2_reliability.py` — duplicate webhook, double approve, ready db-down, page_size cap
- [x] Pytest green (282); backlog marked

## Phase P3 — Agent production-safety + eval harness
- [x] `BaseAgent` — `finalize_result`, command policy/deny strip, prod HITL, cap 25, secret redact, evidence truncate, `_call_llm` + `GROUNDING_RULES`
- [x] Orchestrator — reject missing `user_id`; reject missing `tenant_id` when `ENFORCE_WORKSPACE_ISOLATION`; re-validate commands; persist grounding/evidence; audit `agent_run_*`; 30s timeout; agent exceptions → failed result
- [x] Per-agent contract — mutating paths via finalize; read-only empty commands; cost/security no_data without cloud; alert_noise rules-based (no ML claims); scorecard uses `scorecard_evidence`; documentation no HITL shell while read_only
- [x] Eval harness — `backend/tests/fixtures/agents/*.json` (12 scenarios) + `test_agent_eval_harness.py`
- [x] Docs — `AGENTS.md` Production verification; agent production-contract bugs closed
- [x] Pytest green (`295 passed`)

## Phase P4 — Prod-like agent E2E + HITL loop
- [x] Prod-like test env — `ENV=production`, `ENABLE_DEMO_DATA=false`, `ENFORCE_WORKSPACE_ISOLATION=true`, `LLM_MOCK=1`, Fernet `SECRETS_ENCRYPTION_KEY`
- [x] `backend/tests/test_phase_p4_agents_prod_e2e.py` — incident no-PD, PD account isolation, code_review mock, deploy HITL + approve dry-run/deny, double approve CAS, MCP dangerous pending, kubectl delete require_approval, demo off → no_data
- [x] Approve path dry-runs commands before execute; policy deny never reaches subprocess
- [x] `scripts/agent_prod_smoke.py` — list agents + read-only run; exit non-zero on HTTP 500
- [x] pytest marker `prod_e2e`
- [x] Pytest green (`303 passed`)

## Phase P5 — Competitor gap closures (important only)
- [x] Scorecards — optional live GitHub Actions CI on default branch; metadata fallback; UI live vs metadata badge
- [x] Postmortems — SEV1/SEV2 templates, copy markdown API, action_items checklist JSON, no invented timeline tests
- [x] Self-service — builtins + propose_deploy HITL; Actions empty/loading states
- [x] Alert correlation — dry-run API + admin counters; rules-based (not ML)
- [x] On-call — multi-schedule list + PD deep links; scheduling stays in PD
- [x] Golden paths — clearer invalid template/entity errors; steps_json validate on create
- [x] `backend/tests/test_phase_p5_competitor_gaps.py`; `docs/product_comparison.md` symbols updated
- [x] Pytest green (`311 passed`)

## Phase P6 — Production compose + real-life smoke
- [x] Harden `deploy/docker-compose.prod.yml` — ready healthchecks, healthy `depends_on` (api×2 + frontend), optional resource limits
- [x] Expand `scripts/pilot_smoke.sh` — `/health/ready`, `/api/llm/status`, login + `/api/agents/`, policy evaluate sample; fail on HTTP 500
- [x] `scripts/agent_realworld_checklist.md` — operator steps with real keys (env → tools → agents → HITL → postmortem → audit → isolation)
- [x] `.env.production.example` — `ENABLE_DEMO_DATA=false`, `SECRETS_ENCRYPTION_KEY` (no inline `#`), `ENFORCE_WORKSPACE_ISOLATION`
- [x] `backend/tests/test_phase_p6_compose_config.py`
- [x] Pytest green (`314 passed`)

## Phase P7 — Frontend production bugs + agent/HITL UX
- [x] AgentRunnerPanel — grounding/evidence/policy, disable Run without workspace/task, Reset always available, safe API errors, HITL double-submit guard
- [x] AgentRunHistory — grounding column + drawer evidence/policy/errors; `/agent-history` route
- [x] IncidentCommandCenter — busy guards, safe detail errors, clipboard catch
- [x] Tool Registry — mapped connection errors; never echo raw token/HTML
- [x] CommandPolicy evaluate + AlertRules dry-run loading/errors
- [x] OncallWidget empty/error → Tool Registry link
- [x] Auth login — MFA only on enrollment code; production-safe messages; silentToast for dashboard cost widget
- [x] `src/utils/parseApiError.js` + vitest for GroundingBadge / approve disabled
- [x] npm test (`17 passed`) / lint

## Phase P8 — Release readiness (Production candidate)
- [x] Backlog — all P0 closed; remaining P1 accepted as known pilot risk
- [x] `docs/BETA_GONOGO.md` — automation checkboxes marked; human/ops items left open
- [x] `docs/product_comparison.md` — honest ✓ / ~ / ✗ after P5–P7
- [x] `docs/PRODUCTION_READINESS.md` — one-pager (ready / gaps / pilot / agent checklist)
- [x] Prometheus HA scrape targets (`api_1`/`api_2`); `.env.production.example` JWT 120 + connector placeholders
- [x] Full `pytest backend/tests -q` green (`314 passed`)
- [x] **Production candidate** — design-partner pilot ready

---

## Production candidate

Ship label after P8: **Production candidate** for HA compose + agent HITL pilot.  
Not Port/Backstage/incident.io parity. Use `docs/PRODUCTION_READINESS.md` + `docs/BETA_GONOGO.md` before customer go-live.

