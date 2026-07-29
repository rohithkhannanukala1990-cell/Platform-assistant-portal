# Production bug backlog

**Phase P0 inventory** (static audit on `899ad44`+). No fixes in that phase.  
**Phase P1:** Fixed all P0 blockers + critical P1 security/data-plane items (SSL, SSRF, demo gates, AuthZ, SafeExecutor defaults, weak admin, CORS, tenant leaks). FE refactors deferred.  
**Phase P2:** API reliability — webhooks idempotency/500s, Celery retries, ready probes, pagination cap, metrics/rate-limit hardening. Agent rewrites deferred to P3.  
**Pytest:** `282 passed` (`pytest backend/tests -q`) after P2.

### Summary counts

| Severity | Count |
|----------|------:|
| P0-blocker | 0 open (7 fixed P1) |
| P1-high | ~8 open (FE/observability deferred) |
| P2-medium | ~24 open |
| P3-low | ~11 open |
| wontfix | 3 |
| **Approx open** | **~46** |

Sources: direct review + [Correctness audit (B)](aba54458-cbee-4bfb-9d1c-d81eeac8e2f0) + [Frontend audit (D)](0d424b4d-2400-46dd-8617-173f20cd0444) + [Agents audit (C)](21d927fe-a93b-424f-8b2f-96d4bf758e50). Security subagent blocked by policy; security items from direct reads.

---

## Blockers (P0)

- [x] **ID-001** Agent approve race — double command execute — Fixed P1: `claim_agent_run` CAS before `safe_executor.execute` (`approval_claim.py` + `agents.py`).
- [x] **ID-002** Scorecard endpoints skip tenant check — Fixed P1: `require_tenant` + `_get_active_entity(..., tenant_id=)`.
- [x] **ID-003** Entity actions skip tenant on entity — Fixed P1: entity/run lookups scoped via `CatalogEntity.tenant_id`.
- [x] **ID-004** Prod frontend image build fails — Fixed P1: added `public/.gitkeep`.
- [x] **ID-005** AI tool approve check-then-act race — Fixed P1: `claim_ai_execution` before `_run_action`.
- [x] **ID-006** Incident approve race — double remediation execute — Fixed P1: `claim_incident_approval` before execute; admin-only.
- [x] **ID-007** MCP HITL approve race — tool runs twice — Fixed P1: `claim_mcp_call` before `_execute` (reject also CAS).

---

## High (P1)

- [x] **ID-010** Argo CD TLS verify disabled — Fixed P1: `_verify_tls()` default True; never insecure when `ENV=production`.
- [x] **ID-011** Outbound webhook SSRF — Fixed P1: `assert_safe_outbound_url` on ping/deliver (`services/ssrf.py`).
- [x] **ID-012** Backend image may bake secrets — Fixed P1: `backend/.dockerignore`.
- [x] **ID-013** API/celery containers run as root — Fixed P1: non-root `USER appuser` in `backend/Dockerfile`.
- [x] **ID-014** Agent reject ignores status — Fixed P1: reject gated on `pending_approval` + CAS to failed.
- [x] **ID-015** EntityAction create is any authenticated user — Fixed P1: `require_admin` on create.
- [x] **ID-016** Local/CI healthchecks use liveness only — Fixed P2: compose + CI poll `/health/ready`; daily health workflow also probes ready.
- [ ] **ID-017** Prod Prometheus scrape target wrong — `prometheus/prometheus.yml:8` → `backend:8000` — Use `api_1`/`api_2` for HA. *(deferred P5)*
- [x] **ID-018** Pending incident approvals leak across tenants — Fixed P1: `get_pending_approvals(..., tenant_id=)`.
- [x] **ID-019** Catalog search ignores tenant — Fixed P1: `apply_tenant_filter` on search.
- [x] **ID-050** Catalog dependencies cross-tenant R/W — Fixed P1: tenant on `_get_active` + scoped list/delete.
- [ ] **ID-051** JWT in Terminal WebSocket query string — `src/components/Terminal.jsx:19-20` — Token lands in proxy/access logs — Send token after `onopen` or via subprotocol. *(deferred P4 FE)*
- [ ] **ID-052** Dashboard data hook bypasses `authFetch` / `API_BASE` — `src/hooks/useDashboardData.js:17-24` (same pattern: `StandardsPage.jsx`, `RBACManager.jsx`, `useCatalogSearch.js`) — Relative `fetch` + legacy `localStorage` token; 401 not logged out; prod multi-origin 404 — Use `authFetch`. *(deferred P4 FE)*
- [ ] **ID-053** Notifications page never loads — `src/components/NotificationsPage.jsx:10-13` — Cookie `fetch` without `Authorization` → silent empty list — Use `authFetch('/api/notifications')`. *(deferred P4 FE)*
- [ ] **ID-054** Sidebar “Run History” dead link — `src/components/Sidebar.jsx:157` (`/agent-history`) vs `App.jsx` (`/history` or missing `AgentRunHistory` route) — Wire route to `AgentRunHistory` **or** point nav to `/history`. *(deferred P6 FE)*
- [x] **ID-057** Non-prod agent commands auto-execute under default-allow — Fixed P1: unmatched commands → `require_approval` when environment or process `ENV` is production (executor refuses without `approved=True`).

---

## Medium (P2)

- [x] **ID-020** CI Python 3.11 vs Dockerfile 3.12 — Fixed P2: CI + pr-check pinned to 3.12.
- [ ] **ID-021** *(superseded by ID-054)* — kept for history; treat as duplicate of ID-054.
- [x] **ID-022** Naive UTC on liveness — Fixed P2: `datetime.now(timezone.utc)`.
- [ ] **ID-023** Long JWT lifetime — `backend/auth.py:260` — Default 480m — Prefer 60–120m in prod example.
- [ ] **ID-024** `.env.production.example` incomplete (webhooks/SSO) — Add placeholders for GitLab/PD/Datadog/SAML/Google.
- [ ] **ID-025** `SECRETS_ENCRYPTION_KEY=` inline `#` comment — `.env.production.example:14` — Move hint off value line.
- [ ] **ID-026** documentation_agent HITL while `read_only=True` — `backend/agents/documentation_agent.py:107-119` — Use `_finalize_with_policy` or success + recommended_actions. *(deferred P3 agents)*
- [x] **ID-027** Daily health workflow ignores readiness — Fixed P2: also probe `/health/ready`.
- [ ] **ID-028** Entity actions workspace TODO — Track with ID-003.
- [ ] **ID-029** Raw `res.text()` in UI errors (systemic) — `ConnectorReadView.jsx:46`, CatalogPage, GitHub*, K8s, PagerDuty, AIAssistant, AgentRunnerPanel, EntityActionsPage, … — Shared `parseApiError(res)` → never render HTML/traceback. *(deferred P4/P6 FE)*
- [x] **ID-030** Agent approve any tenant user — Fixed P1: `require_admin` on approve/reject.
- [x] **ID-031** Celery retry without countdown — Fixed P2: `monitor_cicd_pipelines` uses `_backoff_countdown`; DLQ only on MaxRetriesExceeded.
- [x] **ID-032** Webhook gateway 500 on empty `alerts`/`evalMatches` — Fixed P2: guard empty lists in `_map_to_cloud_event`.
- [ ] **ID-033** HITL catalog action approve is silent no-op — `backend/services/catalog_actions.py:173-182` + `agents.py:252-276` — Propose Deploy pending run has `commands: []`; approve only flips success — Dispatch on `action_type` after HITL. *(deferred P3/P7 agents)*
- [x] **ID-034** Celery webhook retries duplicate incidents — Fixed P2: pass `delivery_id` to task; skip if delivery/event already processed; mark error reclaimable.
- [x] **ID-035** `monitor_cicd_pipelines` DLQ then retry — Fixed P2: DLQ only on MaxRetriesExceeded.
- [x] **ID-036** Tool accounts matrix / category counts unscoped — Fixed P1: tenant + ownership filters on categories/matrix.
- [ ] **ID-037** Dashboard AWS-cost agent toast spam — `src/components/DashboardView.jsx:183-209` + `AuthContext.jsx` agents-run toast — POST `/api/agents/run` every mount — Silent widget fetch or dedicated GET. *(deferred P6 FE)*
- [ ] **ID-038** Unhandled rejections in admin polling — `AuditLogView.jsx:40-53`, `UserManagement.jsx:46-54`, `OpsPortal.jsx:163-165` — try/catch + `.catch` on intervals. *(deferred P6 FE)*
- [ ] **ID-039** AgentApprovalsWidget incidents fetch without auth — `src/components/AgentApprovalsWidget.jsx:570` — Use `authFetch`. *(deferred P4 FE)*
- [ ] **ID-055** IntegrationsPage webhook activity unauthenticated — `src/components/IntegrationsPage.jsx:198-225` — Use `authFetch`; surface errors. *(deferred P4 FE)*
- [x] **ID-056** Webhook claim-before-process can drop events — Fixed P2: `error`/`failed` deliveries reclaimable on provider retry.
- [x] **ID-058** Golden-path agent step missing `tenant_id` on PlatformContext — Fixed P1: thread `tenant_id` from run/inputs into `PlatformContext`.
- [x] **ID-059** `_finalize_with_policy` keeps `details.commands` for read_only — Fixed P1: clear `commands` on read_only return.
- [ ] **ID-060** Incident triage LLM prompts lack GROUNDING_RULES — `backend/ai/ai_utils.py:7-42`, `incidents_service.py` prompt — Can invent commands/paths/evidence — Prepend shared grounding constraint. *(deferred P3/P7)*
- [ ] **ID-061** DB query analyzer fabricates mock EXPLAIN — `backend/routers/platform_misc.py:368-412` — Fake Seq Scan / timings presented as analysis — Return explicit no-live-EXPLAIN state. *(deferred P7)*
- [x] **ID-062** `monitor_cicd_pipelines` invents incidents from demo fixtures — Fixed P1: gated by `demo_data_enabled()`; no-op when false.
- [x] **ID-063** Incident approve lacks Admin/owner authz — Fixed P1: `require_admin` on approve/reject.

---

## Low (P3)

- [x] **ID-040** CORS localhost fallback when origins unset — Fixed P1: production strips `*`, deny-all if origins unset.
- [ ] **ID-041** ErrorBoundary console.error — `src/components/ErrorBoundary.jsx:15`.
- [ ] **ID-042** RBACManager console.error — `src/components/RBACManager.jsx:188`.
- [ ] **ID-043** Dead scorecard AI parse leftovers — `backend/routers/scorecards.py:49+`.
- [ ] **ID-044** `tool_executor.approve_execution` stub payload — `backend/ai/tool_executor.py:141-152`.
- [ ] **ID-045** Smoke scripts use `python` — `scripts/beta_smoke.sh:19` — Prefer `python3`.
- [x] **ID-046** Permanent Celery errors still retry 5× — Fixed P2: ValueError/KeyError/TypeError/JSONDecodeError → DLQ, no retry.
- [ ] **ID-047** Role-filtered incident list truncates at 500 — `backend/routers/incidents.py:122-126` — Filter `owner_role` in SQL.
- [ ] **ID-048** MFA-role DB read swallow — `backend/auth.py:235-242` — Log + consider fail-closed.
- [ ] **ID-049** Frontend P3 polish — GitHub double-fetch repos; clipboard `.then` without `.catch`; index keys on reorderable lists; OncallWidget maps 500→empty — See frontend audit notes.
- [ ] **ID-064** Entity actions simulated success for unwired handlers — `backend/routers/entity_actions.py:152-157` — `generate-cicd` / `generate-infra` / `create-jira-ticket` return `completed` + `simulated: true` — Use `not_implemented` status.
- [ ] **ID-065** `PlatformContext.from_dict` silently defaults `tenant_id=None` — `backend/context.py:86-91` — Log or resolve via `resolve_tenant_id` (call-site bug: ID-058).
- [x] **ID-079** Pagination max page_size too high — Fixed P2: `MAX_PAGE_SIZE=100` (+ Query le=100 on lists).
- [x] **ID-080** Prometheus metrics can throw on bad labels / middleware — Fixed P2: `_safe_label` + try/except around HTTP metrics.
- [x] **ID-081** Rate-limit Redis policy undocumented — Fixed P2: documented fail-open API counters + login memory fallback in `rate_limit.py`.

---

## Prod/CI audit follow-up (Phase P1 addendum)

Source: [Prod/CI audit (E)](0f14541c-161e-4180-b0ba-e85ee1741f3a) after commit `80f63a8`.

- [x] **ID-070** Prod `frontend` nginx crash-loops on `read_only` rootfs — `deploy/docker-compose.prod.yml` frontend service — Fixed P1: added `tmpfs: [/var/cache/nginx, /var/run, /tmp]` + healthcheck.
- [x] **ID-071** Required secrets silently interpolate to empty string — `deploy/docker-compose.prod.yml` (`POSTGRES_PASSWORD`, `REDIS_PASSWORD`, `SECRET_KEY`, `SECRETS_ENCRYPTION_KEY`, `DEFAULT_ADMIN_PASSWORD`) — Fixed P0: `${VAR:?err}` fail-fast + `backend/auth.py` rejects empty `SECRET_KEY`.
- [x] **ID-072** Prod compose omits SAML/Google SSO env passthrough — Fixed P1: SAML_*, GOOGLE_* forwarded in `x-api-env`.
- [x] **ID-073** Prod compose omits LLM + `GITHUB_WEBHOOK_SECRET` (silent webhook HMAC break) — Fixed P1: `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `LLM_DEFAULT_*`, `GITHUB_WEBHOOK_SECRET` forwarded.
- [x] **ID-074** Daily health workflow can’t alert on total outage — `.github/workflows/health.yml` — Fixed P1: `set -eo pipefail`; curl failure → `STATUS=critical`; `unknown` also triggers alert.
- [x] **ID-013** Non-root USER in `backend/Dockerfile` — Audit E flagged as regression; verified present at commit `80f63a8` (`USER appuser`, uid 10001). No action.
- [ ] **ID-075** `/metrics` exposed unauthenticated through prod edge — `deploy/nginx.prod.conf:84-88` — Add `allow`/`deny` block or move scrape to internal network only. *(deferred P5)*
- [ ] **ID-076** `npm ci || npm install` fallback in prod image — `deploy/Dockerfile.frontend:5` — Drop the fallback. *(deferred P3)*
- [ ] **ID-077** LB health check docs point to non-existent `/api/health` — `docs/SCALING.md:96`, `docs/RUNBOOK_BACKUP.md:68` — Change to `/health/ready`. *(deferred P3 docs)*
- [ ] **ID-078** Duplicated grafana provisioning file — `deploy/grafana/provisioning/dashboards.yml` vs `grafana/provisioning/dashboards/dashboards.yml` — Delete the unmounted copy. *(deferred P3)*

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
