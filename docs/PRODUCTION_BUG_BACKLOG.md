# Production bug backlog

**Phase P0 inventory** (static audit on `899ad44`+). No fixes in this phase.  
**Pytest:** `258` tests collected successfully (`pytest backend/tests --collect-only -q`). Full suite last green at G7 (258 passed).

### Summary counts

| Severity | Count |
|----------|------:|
| P0-blocker | 7 |
| P1-high | 16 |
| P2-medium | 27 |
| P3-low | 12 |
| wontfix | 3 |
| **Total open** | **65** |

Sources: direct review + [Correctness audit (B)](aba54458-cbee-4bfb-9d1c-d81eeac8e2f0) + [Frontend audit (D)](0d424b4d-2400-46dd-8617-173f20cd0444) + [Agents audit (C)](21d927fe-a93b-424f-8b2f-96d4bf758e50). Security subagent blocked by policy; security items from direct reads.

---

## Blockers (P0)

- [ ] **ID-001** Agent approve race — double command execute — `backend/routers/agents.py:244-282` — Two concurrent `POST /api/agents/{id}/approve` both see `status == pending_approval`, both call `safe_executor.execute` before either commits the status flip — Use atomic CAS (`UPDATE … WHERE status='pending_approval'`) or lock row before execute; only the winner runs commands.
- [ ] **ID-002** Scorecard endpoints skip tenant check — `backend/routers/scorecards.py:42-46`, `194-209` — `_get_active_entity` returns any active entity by id; `GET/POST …/scorecard` never calls `require_tenant` / `assert_same_tenant` — Cross-tenant read/eval/overwrite — Pass `require_tenant(request)` into `_get_active_entity` and 404 on mismatch.
- [ ] **ID-003** Entity actions skip tenant on entity — `backend/routers/entity_actions.py:72`, `286-309` — List/run/get runs without tenant filter; models lack `tenant_id` — Cross-tenant action trigger + run leakage — Scope entity lookup + filter runs via `CatalogEntity.tenant_id`.
- [ ] **ID-004** Prod frontend image build fails — `deploy/Dockerfile.frontend:7` — `COPY public ./public` but repo has **no** `public/` directory — Prod compose frontend build fails — Remove COPY or add empty `public/` + `.gitkeep`.
- [ ] **ID-005** AI tool approve check-then-act race — `backend/routers/ai_assistant.py:997-1021` + `backend/ai/tool_executor.py:141-152` — Status checked, then `approve_execution` runs without claiming the row — CAS status to `executing` before `_run_action`.
- [ ] **ID-006** Incident approve race — double remediation execute — `backend/routers/incidents.py:247-313` — Checks `AWAITING_APPROVAL` then `safe_executor.execute` then updates status in separate sessions; approve+reject also racy — Atomic claim before execute.
- [ ] **ID-007** MCP HITL approve race — tool runs twice — `backend/mcp/hitl_bridge.py:197-224` (`POST /api/mcp/calls/{id}/approve`) — Pending check then `_execute` then status update in new session — CAS claim before `_execute`.

---

## High (P1)

- [ ] **ID-010** Argo CD TLS verify disabled — `backend/connectors/argocd_connector.py:48`, `78` — `verify=False` — Default `verify=True`; optional lab insecure flag + audit.
- [ ] **ID-011** Outbound webhook SSRF — `backend/connectors/outbound_webhook_connector.py:47-63` — POST to any URL; no private/metadata IP block — Scheme allowlist + resolve-and-block private IPs.
- [ ] **ID-012** Backend image may bake secrets — `backend/Dockerfile:13` + **no** `.dockerignore` — Add `.dockerignore` excluding `.env*`, `*.db`, `.git`, `node_modules`.
- [ ] **ID-013** API/celery containers run as root — `backend/Dockerfile` (no `USER`) — Add non-root `USER`.
- [ ] **ID-014** Agent reject ignores status — `backend/routers/agents.py:294-319` — Can rewrite completed runs to failed — Gate on `pending_approval` only.
- [ ] **ID-015** EntityAction create is any authenticated user — `backend/routers/entity_actions.py:248-283` — Require admin / capability.
- [ ] **ID-016** Local/CI healthchecks use liveness only — `docker-compose.yml:101`, `.github/workflows/ci.yml:77` — Prefer `/health/ready` where Redis exists.
- [ ] **ID-017** Prod Prometheus scrape target wrong — `prometheus/prometheus.yml:8` → `backend:8000` — Use `api_1`/`api_2` for HA.
- [ ] **ID-018** Pending incident approvals leak across tenants — `backend/routers/incidents.py:130-137` + `backend/db/repositories/incidents.py:181-197` — `get_pending_approvals` has no tenant filter — Pass `tenant_id` and filter.
- [ ] **ID-019** Catalog search ignores tenant — `backend/routers/catalog.py:256-273` — `/api/catalog/search` returns all tenants’ entities — Apply `apply_tenant_filter`.
- [ ] **ID-050** Catalog dependencies cross-tenant R/W — `backend/routers/catalog.py:213-253` — List all deps; create/delete without tenant on `_get_active` — Pass `tenant_id` to `_get_active`; scope list/delete.
- [ ] **ID-051** JWT in Terminal WebSocket query string — `src/components/Terminal.jsx:19-20` — Token lands in proxy/access logs — Send token after `onopen` or via subprotocol.
- [ ] **ID-052** Dashboard data hook bypasses `authFetch` / `API_BASE` — `src/hooks/useDashboardData.js:17-24` (same pattern: `StandardsPage.jsx`, `RBACManager.jsx`, `useCatalogSearch.js`) — Relative `fetch` + legacy `localStorage` token; 401 not logged out; prod multi-origin 404 — Use `authFetch`.
- [ ] **ID-053** Notifications page never loads — `src/components/NotificationsPage.jsx:10-13` — Cookie `fetch` without `Authorization` → silent empty list — Use `authFetch('/api/notifications')`.
- [ ] **ID-054** Sidebar “Run History” dead link — `src/components/Sidebar.jsx:157` (`/agent-history`) vs `App.jsx` (`/history` or missing `AgentRunHistory` route) — Wire route to `AgentRunHistory` **or** point nav to `/history`.
- [ ] **ID-057** Non-prod agent commands auto-execute under default-allow — `backend/pipeline/orchestrator.py:445-457` + `command_policy.py` (no match → allow) — Seeded require_approval catch-all is prod-only; unmatched mutating cmds in dev/staging run with `approved=False` if not on baseline blocklist — Add non-prod catch-all `require_approval` or default-deny for mutating verbs.

---

## Medium (P2)

- [ ] **ID-020** CI Python 3.11 vs Dockerfile 3.12 — `.github/workflows/ci.yml:21` — Pin CI to 3.12.
- [ ] **ID-021** *(superseded by ID-054)* — kept for history; treat as duplicate of ID-054.
- [ ] **ID-022** Naive UTC on liveness — `backend/routers/health_api.py:144` — Use `datetime.now(timezone.utc)`.
- [ ] **ID-023** Long JWT lifetime — `backend/auth.py:260` — Default 480m — Prefer 60–120m in prod example.
- [ ] **ID-024** `.env.production.example` incomplete (webhooks/SSO) — Add placeholders for GitLab/PD/Datadog/SAML/Google.
- [ ] **ID-025** `SECRETS_ENCRYPTION_KEY=` inline `#` comment — `.env.production.example:14` — Move hint off value line.
- [ ] **ID-026** documentation_agent HITL while `read_only=True` — `backend/agents/documentation_agent.py:107-119` — Use `_finalize_with_policy` or success + recommended_actions.
- [ ] **ID-027** Daily health workflow ignores readiness — `.github/workflows/health.yml:28` — Also probe `/health/ready`.
- [ ] **ID-028** Entity actions workspace TODO — Track with ID-003.
- [ ] **ID-029** Raw `res.text()` in UI errors (systemic) — `ConnectorReadView.jsx:46`, CatalogPage, GitHub*, K8s, PagerDuty, AIAssistant, AgentRunnerPanel, EntityActionsPage, … — Shared `parseApiError(res)` → never render HTML/traceback.
- [ ] **ID-030** Agent approve any tenant user — `backend/routers/agents.py:239-242` — Require Admin/approver capability.
- [ ] **ID-031** Celery retry without countdown — `backend/tasks.py:288` — Use `_backoff_countdown`; only DLQ on MaxRetriesExceeded.
- [ ] **ID-032** Webhook gateway 500 on empty `alerts`/`evalMatches` — `backend/routers/webhooks_api.py:179-180` — `[]` passes `isinstance(list)` then `[0]` → IndexError — Guard `and payload["alerts"]`.
- [ ] **ID-033** HITL catalog action approve is silent no-op — `backend/services/catalog_actions.py:173-182` + `agents.py:252-276` — Propose Deploy pending run has `commands: []`; approve only flips success — Dispatch on `action_type` after HITL.
- [ ] **ID-034** Celery webhook retries duplicate incidents — `backend/tasks.py:88-139` — Retry after `ingest_webhook_alert` recreates incident; `delivery_id` not passed to task — Idempotent ingest on delivery_id.
- [ ] **ID-035** `monitor_cicd_pipelines` DLQ then retry — `backend/tasks.py:282-288` — `_dead_letter` before `retry` → phantom DLQ + duplicate incident risk — DLQ only on MaxRetriesExceeded.
- [ ] **ID-036** Tool accounts matrix / category counts unscoped — `backend/routers/tools.py:150-178`, `280-301` — Cross-tenant names/status leak — Apply tenant + ownership filters.
- [ ] **ID-037** Dashboard AWS-cost agent toast spam — `src/components/DashboardView.jsx:183-209` + `AuthContext.jsx` agents-run toast — POST `/api/agents/run` every mount — Silent widget fetch or dedicated GET.
- [ ] **ID-038** Unhandled rejections in admin polling — `AuditLogView.jsx:40-53`, `UserManagement.jsx:46-54`, `OpsPortal.jsx:163-165` — try/catch + `.catch` on intervals.
- [ ] **ID-039** AgentApprovalsWidget incidents fetch without auth — `src/components/AgentApprovalsWidget.jsx:570` — Use `authFetch`.
- [ ] **ID-055** IntegrationsPage webhook activity unauthenticated — `src/components/IntegrationsPage.jsx:198-225` — Use `authFetch`; surface errors.
- [ ] **ID-056** Webhook claim-before-process can drop events — `backend/routers/webhooks_api.py:238+` — Failed process still returns duplicate on provider retry — Mark failed claimable.
- [ ] **ID-058** Golden-path agent step missing `tenant_id` on PlatformContext — `backend/routers/golden_paths.py:350-356` — Tenant-scoped command policies skipped; agents run without tenant — Thread tenant/role from run/entity into context.
- [ ] **ID-059** `_finalize_with_policy` keeps `details.commands` for read_only — `backend/agents/base.py:320-335` — Orchestrator auto-executes `details.commands` on success; latent if a read_only agent passes cmds — Clear `commands` on read_only return.
- [ ] **ID-060** Incident triage LLM prompts lack GROUNDING_RULES — `backend/ai/ai_utils.py:7-42`, `incidents_service.py` prompt — Can invent commands/paths/evidence — Prepend shared grounding constraint.
- [ ] **ID-061** DB query analyzer fabricates mock EXPLAIN — `backend/routers/platform_misc.py:368-412` — Fake Seq Scan / timings presented as analysis — Return explicit no-live-EXPLAIN state.
- [ ] **ID-062** `monitor_cicd_pipelines` invents incidents from demo fixtures — `backend/tasks.py:220-252` — Not gated by `demo_data_enabled()`; injects fake incidents/commands if scheduled in prod — Gate on demo flag or real connector data.
- [ ] **ID-063** Incident approve lacks Admin/owner authz — `backend/routers/incidents.py:235-294` — Any authenticated user; live exec when `ENABLE_LIVE_EXECUTION` — Require admin/owner/`incidents:approve` (related to ID-030).

---

## Low (P3)

- [ ] **ID-040** CORS localhost fallback when origins unset — `backend/main.py:212-225` — Fail closed in production if unset.
- [ ] **ID-041** ErrorBoundary console.error — `src/components/ErrorBoundary.jsx:15`.
- [ ] **ID-042** RBACManager console.error — `src/components/RBACManager.jsx:188`.
- [ ] **ID-043** Dead scorecard AI parse leftovers — `backend/routers/scorecards.py:49+`.
- [ ] **ID-044** `tool_executor.approve_execution` stub payload — `backend/ai/tool_executor.py:141-152`.
- [ ] **ID-045** Smoke scripts use `python` — `scripts/beta_smoke.sh:19` — Prefer `python3`.
- [ ] **ID-046** Permanent Celery errors still retry 5× — `backend/tasks.py:123-139` — Don’t retry ValueError/KeyError/JSONDecodeError.
- [ ] **ID-047** Role-filtered incident list truncates at 500 — `backend/routers/incidents.py:122-126` — Filter `owner_role` in SQL.
- [ ] **ID-048** MFA-role DB read swallow — `backend/auth.py:235-242` — Log + consider fail-closed.
- [ ] **ID-049** Frontend P3 polish — GitHub double-fetch repos; clipboard `.then` without `.catch`; index keys on reorderable lists; OncallWidget maps 500→empty — See frontend audit notes.
- [ ] **ID-064** Entity actions simulated success for unwired handlers — `backend/routers/entity_actions.py:152-157` — `generate-cicd` / `generate-infra` / `create-jira-ticket` return `completed` + `simulated: true` — Use `not_implemented` status.
- [ ] **ID-065** `PlatformContext.from_dict` silently defaults `tenant_id=None` — `backend/context.py:86-91` — Log or resolve via `resolve_tenant_id` (call-site bug: ID-058).

---

## wontfix

- [ ] **WF-001** Local compose weak defaults — `docker-compose.yml` — Intentional DX; blocked by go/no-go.
- [ ] **WF-002** Pytest SQLite + optional Redis on ready — Keep for offline tests.
- [ ] **WF-003** Argo lab self-signed TLS — Opt-in after ID-010 default-secure.

---

## Agent gaps

| Gap | Severity | Notes |
|-----|----------|-------|
| Live GitHub Checks for `ci_green` | P2 product | Offline/metadata only |
| Non-prod default-allow auto-exec | P1 | ID-057 |
| Deploy/HITL in prod | OK | `base.py` + `requires_approval_envs` |
| Read-only agents no shell execute | Partial | Contract OK today; latent ID-059 |
| documentation_agent approval UX | P2 | ID-026 |
| AGENT_REGISTRY 17 agents | Verified pass | `__init__.py` |
| MCP dangerous → HITL | Verified pass | `hitl_bridge.py` (race = ID-007) |
| Baseline deny not overridable by approval | Verified pass | `safe_executor.py` |
| Catalog HITL action post-approve no-op | P2 | ID-033 |
| Golden-path agent context tenant | P2 | ID-058 |
| Triage / EXPLAIN / cicd-monitor fabrication | P2 | ID-060, ID-061, ID-062 |
| Agent LLM calls include GROUNDING_RULES | Verified pass | `BaseAgent._call_llm`; postmortem/copilot/assistant also grounded |
| G6 entity/catalog actions no shell bypass | Verified pass | Internal DB ops; HITL creates AgentRun |
| `subprocess` only in SafeExecutor (+ health/MCP stdio) | Verified pass | No agent bypass of policy for shell |

---

## Competitor gaps still open

| Capability | Status | Track |
|------------|--------|-------|
| Scorecards vs Port | ~ | Live CI, richer checks |
| Self-service actions vs Port | ~ | Marketplace / more builtins |
| Golden paths vs Backstage | ~ | Template depth |
| On-call scheduling | ✗ / ~ | Stays in PagerDuty |
| Alert correlation vs incident.io | ~ | Rules-only |
| Postmortems vs PD Scribe | ~ | Draft quality |
| Multi-region Postgres HA | ✗ | Out of G7 |

---

## Invariants

**These MUST NOT regress in P1–P8 fixes:**

1. **No global ToolAccount fallback** — user / workspace / tenant only (`scoped_tool_access.py`).
2. **GET never returns decrypted secrets** — `has_credentials` on list; decrypt in-process for tests only.
3. **`ENABLE_DEMO_DATA=false` ⇒ no fake success** for Slack/Jira/PD/GitHub.
4. **Command baseline blocklist cannot be overridden by approval**.
5. **Command policy worst-effect wins; shlex failure → `require_approval`**.
6. **MCP dangerous tools → HITL** (fix race ID-007 without removing HITL).
7. **Agents: grounding none + no_data when connector missing**.
8. **Cross-tenant access → 404** (exceptions: ID-002, ID-003, ID-018, ID-019, ID-050, ID-036).
9. **Webhook HMAC on raw body; `delivery_id` idempotent** (claim race/drop: ID-056; keep PK dedupe).
10. **Production compose:** dual API/workers, Postgres, Redis, demo off, isolation on.

### Verified-pass (audit sampling)

- JWT refuses insecure default outside test (`auth.py:255-258`).
- CORS no `*` + credentials combo.
- Webhook HMAC on raw body; missing secret fails closed in non-dev.
- No global ToolAccount env fallback on API paths.
- G5 connector 400 → Tool Registry empty state (all connector views).
- Zero `dangerouslySetInnerHTML` in `src/` (XSS check pass).
- `authFetch` central 401 → logout (when callers use it).
- Webhook delivery PK claim is atomic (`webhook_delivery.py`).
- Pagination clamps + Session context managers generally correct.
- Prod `/health/ready` on API containers.
- Token not logged in console (only ErrorBoundary/RBACManager generic errors).

---

## Suggested phase mapping (P1–P8)

| Phase | Focus | Backlog IDs |
|-------|--------|-------------|
| **P1** | Approval races + tenant isolation + auto-exec | ID-001, ID-002, ID-003, ID-005, ID-006, ID-007, ID-014, ID-018, ID-019, ID-050, ID-030, ID-036, ID-057, ID-063 |
| **P2** | Connector / SSRF / TLS | ID-010, ID-011 |
| **P3** | Container hygiene | ID-004, ID-012, ID-013 |
| **P4** | AuthZ + auth plumbing (FE+BE) | ID-015, ID-051, ID-052, ID-053, ID-039, ID-055 |
| **P5** | Observability + CI/probes + Celery | ID-016, ID-017, ID-020, ID-027, ID-031, ID-034, ID-035, ID-046, ID-062 |
| **P6** | Frontend nav + errors + toasts | ID-054, ID-029, ID-037, ID-038, ID-041, ID-042, ID-049 |
| **P7** | Agent/HITL/catalog/grounding | ID-026, ID-033, ID-044, ID-058, ID-059, ID-060, ID-061, ID-064, ID-065 |
| **P8** | Config polish + webhook edge cases | ID-022–025, ID-032, ID-040, ID-043, ID-045, ID-047, ID-048, ID-056; competitor ~ epics |

---

## Audit method notes

- Static grep + targeted reads; correctness + frontend + agents subagents merged into this doc.
- Security-focused automated subagent blocked by policy; security items from direct review.
- No behavior changes in P0 except this document (+ PHASES checklist note).
- Do not push from P0.
