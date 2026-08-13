# Production bug backlog

**Phase P0 inventory** (static audit). No fixes in that phase.  
**P1–P7:** Security/data-plane, reliability, agent contract, prod E2E, competitor gaps, compose smoke, FE HITL/UX.  
**Phase P8:** Release readiness — P0 closed; remaining P1 accepted risk with owner; go/no-go + readiness doc.  
**Pytest:** `314 passed` (`pytest backend/tests -q`) after P8.

### Summary counts (P8)

| Severity | Count |
|----------|------:|
| P0-blocker | **0 open** (7 fixed) |
| P1-high | **0 open blockers** — remaining FE/ops items = **accepted risk** (owner below) |
| P2-medium | ~18 open (post-pilot) |
| P3-low | ~15 open (polish) — includes ID-082…085 from the inline TODO sweep |
| wontfix | 3 |
| **Pilot blockers** | **0** |

Sources: direct review + prior audits. Security items from direct reads.

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
- [x] **ID-017** Prod Prometheus scrape target wrong — Fixed P8: `prometheus/prometheus.yml` targets `api_1:8000` / `api_2:8000` for HA compose.
- [x] **ID-018** Pending incident approvals leak across tenants — Fixed P1: `get_pending_approvals(..., tenant_id=)`.
- [x] **ID-019** Catalog search ignores tenant — Fixed P1: `apply_tenant_filter` on search.
- [x] **ID-050** Catalog dependencies cross-tenant R/W — Fixed P1: tenant on `_get_active` + scoped list/delete.
- [x] **ID-051** JWT in Terminal WebSocket query string — **Fixed**: WS auth via first JSON `{token}` message on `/ws/portal`, `/ws/agent-run/{id}`, `/ws/terminal` (no query-param JWT).
- [x] **ID-052** Dashboard data hook bypasses `authFetch` / `API_BASE` — **Fixed**: dashboard/notifications and related hooks use `authFetch`.
- [x] **ID-053** Notifications page never loads — **Fixed**: `authFetch('/api/notifications')`.
- [x] **ID-054** Sidebar “Run History” dead link — Fixed P7: `/agent-history` route → AgentRunnerPanel history tab.
- [x] **ID-057** Non-prod agent commands auto-execute under default-allow — Fixed P1: unmatched commands → `require_approval` when environment or process `ENV` is production (executor refuses without `approved=True`).

---

## Medium (P2)

- [x] **ID-020** CI Python 3.11 vs Dockerfile 3.12 — Fixed P2: CI + pr-check pinned to 3.12.
- [x] **ID-021** *(superseded by ID-054)* — duplicate closed with ID-054.
- [x] **ID-022** Naive UTC on liveness — Fixed P2: `datetime.now(timezone.utc)`.
- [x] **ID-023** Long JWT lifetime — `backend/auth.py` already reads `JWT_EXPIRE_MINUTES`; `.env.production.example` set to **60**. **Owner: ops** — confirm pilot `.env.production`.
- [x] **ID-024** `.env.production.example` incomplete (webhooks/SSO) — Fixed P8: SSO + webhook + connector placeholders documented.
- [x] **ID-025** `SECRETS_ENCRYPTION_KEY=` inline `#` comment — Fixed P6: hint moved above value line in `.env.production.example`.
- [x] **ID-026** documentation_agent HITL while `read_only=True` — Fixed P3: success + `recommended_actions`, never pending shell while read_only.
- [x] **ID-027** Daily health workflow ignores readiness — Fixed P2: also probe `/health/ready`.
- [ ] **ID-028** Entity actions workspace TODO — Track with ID-003 (tenant fixed); residual workspace UX. **Owner: backend** post-pilot.
- [x] **ID-029** Raw `res.text()` in UI errors (systemic) — Fixed P7 for agents/HITL/tools/policy/alerts/login via `parseApiError` / `formatErrorDetail` (remaining surfaces can migrate incrementally).
- [x] **ID-030** Agent approve any tenant user — Fixed P1: `require_admin` on approve/reject.
- [x] **ID-031** Celery retry without countdown — Fixed P2: `monitor_cicd_pipelines` uses `_backoff_countdown`; DLQ only on MaxRetriesExceeded.
- [x] **ID-032** Webhook gateway 500 on empty `alerts`/`evalMatches` — Fixed P2: guard empty lists in `_map_to_cloud_event`.
- [x] **ID-033** HITL catalog action approve is silent no-op — **Fixed**: entity-action approve re-dispatches; catalog_self_service AgentRun approve calls `fulfill_catalog_action_after_hitl`.
- [x] **ID-034** Celery webhook retries duplicate incidents — Fixed P2: pass `delivery_id` to task; skip if delivery/event already processed; mark error reclaimable.
- [x] **ID-035** `monitor_cicd_pipelines` DLQ then retry — Fixed P2: DLQ only on MaxRetriesExceeded.
- [x] **ID-036** Tool accounts matrix / category counts unscoped — Fixed P1: tenant + ownership filters on categories/matrix.
- [x] **ID-037** Dashboard AWS-cost agent toast spam — Fixed P7: `silentToast: true` on dashboard cost fetch + AgentRunner self-toasts.
- [x] **ID-038** Unhandled rejections in admin polling — **Fixed**: AuditLog/AdminOverview/UserManagement wrap polls in try/catch + reconnect banner.
- [x] **ID-039** AgentApprovalsWidget incidents fetch without auth — **Fixed**: uses `authFetch`.
- [x] **ID-055** IntegrationsPage webhook activity unauthenticated — **Fixed**: uses `authFetch`.
- [x] **ID-044** `tool_executor.approve_execution` stub payload — **Fixed**: pending executions stored and replayed on approve.
- [x] **ID-043** Dead scorecard AI parse leftovers — **Fixed**: removed unused `_parse_scorecard_json`.
- [x] **ID-061** DB query analyzer fabricates mock EXPLAIN — **Fixed**: `explain_plan=null` + `explain_note`; no invented plans.
- [x] **ID-064** Entity actions simulated success for unwired handlers — **Fixed**: return `not_implemented` instead of green `completed` + `simulated`.
- [x] **ID-065** `PlatformContext` silent `tenant_id=None` → default — **Fixed**: `_require_tenant_id` in orchestrator (prod raises).
- [x] **ID-058** Golden-path agent step missing `tenant_id` on PlatformContext — Fixed P1: thread `tenant_id` from run/inputs into `PlatformContext`.
- [x] **ID-059** `_finalize_with_policy` keeps `details.commands` for read_only — Fixed P1: clear `commands` on read_only return.
- [x] **ID-060** Incident triage LLM prompts lack GROUNDING_RULES — **Fixed**: `run_triage` injects `GROUNDING_RULES` + EVIDENCE into the user prompt.
- [x] **ID-061** DB query analyzer fabricates mock EXPLAIN — **Fixed**: `explain_plan=null` + `explain_note`; no invented plans.
- [x] **ID-062** `monitor_cicd_pipelines` invents incidents from demo fixtures — Fixed P1: gated by `demo_data_enabled()`; no-op when false.
- [x] **ID-063** Incident approve lacks Admin/owner authz — Fixed P1: `require_admin` on approve/reject.
- [x] **ID-056** Webhook claim-before-process can drop events — Fixed P2: `error`/`failed` deliveries reclaimable on provider retry.

---

## Low (P3)

- [x] **ID-040** CORS localhost fallback when origins unset — Fixed P1: production strips `*`, deny-all if origins unset.
- [ ] **ID-041** ErrorBoundary console.error — `src/components/ErrorBoundary.jsx:15`. **Owner: frontend**
- [ ] **ID-042** RBACManager console.error — `src/components/RBACManager.jsx:188`. **Owner: frontend**
- [x] **ID-043** Dead scorecard AI parse leftovers — **Fixed**: removed unused `_parse_scorecard_json`.
- [x] **ID-044** `tool_executor.approve_execution` stub payload — **Fixed**: pending executions stored and replayed on approve.
- [ ] **ID-045** Smoke scripts use `python` — Prefer `python3` where available. **Owner: ops**
- [x] **ID-046** Permanent Celery errors still retry 5× — Fixed P2: ValueError/KeyError/TypeError/JSONDecodeError → DLQ, no retry.
- [ ] **ID-047** Role-filtered incident list truncates at 500 — **Owner: backend**
- [ ] **ID-048** MFA-role DB read swallow — **Owner: backend** — Log + consider fail-closed.
- [ ] **ID-049** Frontend P3 polish — GitHub double-fetch; index keys; residual clipboard. **Owner: frontend** (OncallWidget 500→empty fixed P7)
- [x] **ID-064** Entity actions simulated success for unwired handlers — **Fixed**: return `not_implemented` instead of green `completed` + `simulated`.
- [x] **ID-065** `PlatformContext` silent `tenant_id=None` → default — **Fixed**: `_require_tenant_id` in orchestrator (prod raises).
- [x] **ID-079** Pagination max page_size too high — Fixed P2: `MAX_PAGE_SIZE=100` (+ Query le=100 on lists).
- [x] **ID-080** Prometheus metrics can throw on bad labels / middleware — Fixed P2: `_safe_label` + try/except around HTTP metrics.
- [x] **ID-081** Rate-limit Redis policy undocumented — Fixed P2: documented fail-open API counters + login memory fallback in `rate_limit.py`.

---

## Inline TODO sweep (external-sharing prep)

All 81 inline `TODO`/`FIXME` markers were removed from `backend/` and `src/` and
each was verified against the implementation beneath it. The overwhelming
majority described work that was already finished — they read as a
pre-implementation checklist nobody deleted afterwards, and several implied
security weaknesses that do not exist (see the commit for the full accounting).
The four items below were the only genuinely-outstanding ones, tracked here
instead of as scattered comments.

- [ ] **ID-082** GitHub connector has no `ping` action — `backend/connectors/github_connector.py`. Every other connector (ArgoCD, Kubernetes, PagerDuty, Prometheus, ServiceNow, Slack, outbound webhook) exposes `ping` for health probes; GitHub is probed indirectly via `list_repos`. **Owner: backend** post-pilot.
- [ ] **ID-083** Workspace-membership enforcement deferred — `backend/routers/golden_paths.py:907`, `backend/routers/standards.py:383`, `backend/routers/standards.py:478`. `CatalogEntity` carries `tenant_id` but not `workspace_id`, so these paths enforce tenant isolation only. Cross-tenant access is already blocked (404); this is intra-tenant, cross-workspace narrowing. Requires a schema change. **Owner: backend** post-pilot.
- [ ] **ID-084** Template category/slug validation is local, not registry-backed — `backend/routers/templates.py:118`, `:135`. Category is checked against a local list and `golden_path_slug` is not cross-checked against `GoldenPathTemplate.slug`. **Owner: backend** P3 polish.
- [ ] **ID-085** `tool_executor` results not on a common schema — `backend/ai/tool_executor.py`. Agent results use `AgentResult`; direct tool-executor returns are a looser dict. Cosmetic for callers today. **Owner: backend** P3 polish.

---

## Prod/CI audit follow-up (Phase P1 addendum)

- [x] **ID-070** Prod `frontend` nginx crash-loops on `read_only` rootfs — Fixed P1: tmpfs + healthcheck.
- [x] **ID-071** Required secrets silently interpolate to empty string — Fixed: `${VAR:?err}` + reject empty `SECRET_KEY`.
- [x] **ID-072** Prod compose omits SAML/Google SSO env passthrough — Fixed P1.
- [x] **ID-073** Prod compose omits LLM + `GITHUB_WEBHOOK_SECRET` — Fixed P1.
- [x] **ID-074** Daily health workflow can’t alert on total outage — Fixed P1.
- [x] **ID-013** Non-root USER — Verified present. No action.
- [x] **ID-075** `/metrics` exposed unauthenticated through prod edge — **Fixed**: nginx denies `/metrics` on the public edge; Prometheus scrapes `api_1`/`api_2` on the Docker network.
- [ ] **ID-076** `npm ci || npm install` fallback in prod image — **Owner: ops** post-pilot.
- [ ] **ID-077** LB health check docs point to non-existent `/api/health` — **Owner: docs** — Prefer `/health/ready`. Post-pilot.
- [ ] **ID-078** Duplicated grafana provisioning file — **Owner: ops** post-pilot.

---

## wontfix

- [x] **WF-001** Local compose weak defaults — Intentional DX; blocked by go/no-go for prod.
- [x] **WF-002** Pytest SQLite + optional Redis on ready — Keep for offline tests.
- [x] **WF-003** Argo lab self-signed TLS — Opt-in after ID-010 default-secure.

---

## Agent gaps

| Gap | Severity | Notes |
|-----|----------|-------|
| Live GitHub Checks for `ci_green` | OK / ~ | P5: live Actions when connector present; metadata fallback |
| Non-prod default-allow auto-exec | OK | ID-057 fixed for production ENV |
| Deploy/HITL in prod | OK | `base.py` + `requires_approval_envs` |
| Read-only agents no shell execute | OK | Fixed P1/P3 |
| documentation_agent approval UX | OK | Fixed P3: ID-026 |
| AGENT_REGISTRY 21 agents | Verified pass | Count re-verified against `backend/agents/*.py` |
| MCP dangerous → HITL | Verified pass | Race fixed ID-007 |
| Baseline deny not overridable by approval | Verified pass | |
| Golden-path agent context tenant | OK | ID-058 |
| Triage / EXPLAIN fabrication | OK | ID-060, ID-061 fixed |
| Agent LLM calls include GROUNDING_RULES | Verified pass | BaseAgent + triage |
| Catalog HITL action post-approve | OK | ID-033 fixed |
| G6 entity/catalog actions no shell bypass | Verified pass | |
| `subprocess` only in SafeExecutor (+ health/MCP stdio) | Verified pass | |

---

## Competitor gaps still open

| Capability | Status | Track |
|------------|--------|-------|
| Scorecards vs Port | ✓ / ~ | Live CI when GH connected; richer marketplace checks still ~ |
| Self-service actions vs Port | ~ | Not a full action marketplace |
| Golden paths vs Backstage | ~ | Template depth |
| On-call scheduling | ✗ / ~ | Stays in PagerDuty |
| Alert correlation vs incident.io | ~ | Rules-only |
| Postmortems vs PD Scribe | ✓ / ~ | Draft quality; not full Scribe workflow |
| Multi-region Postgres HA | ✗ | Out of G7 |

---

## Invariants

**These MUST NOT regress in P1–P8 fixes:**

1. **No global ToolAccount fallback** — user / workspace / tenant only (`scoped_tool_access.py`).
2. **GET never returns decrypted secrets** — `has_credentials` on list; decrypt in-process for tests only.
3. **`ENABLE_DEMO_DATA=false` ⇒ no fake success** for Slack/Jira/PD/GitHub.
4. **Command baseline blocklist cannot be overridden by approval**.
5. **Command policy worst-effect wins; shlex failure → `require_approval`**.
6. **MCP dangerous tools → HITL**.
7. **Agents: grounding none + no_data when connector missing**.
8. **Cross-tenant access → 404**.
9. **Webhook HMAC on raw body; `delivery_id` idempotent**.
10. **Production compose:** dual API/workers, Postgres, Redis, demo off, isolation on.

### Verified-pass (audit sampling)

- JWT refuses insecure default outside test.
- CORS no `*` + credentials combo in production.
- Webhook HMAC on raw body; missing secret fails closed in non-dev.
- No global ToolAccount env fallback on API paths.
- G5 connector 400 → Tool Registry empty state.
- Zero `dangerouslySetInnerHTML` in `src/`.
- `authFetch` central 401 → logout (when callers use it).
- Prod `/health/ready` on API containers.
- Agent FE: grounding badge, HITL busy guards, `parseApiError` (P7).

---

## Suggested phase mapping (completed)

| Phase | Focus | Status |
|-------|--------|--------|
| **P1** | Approval races + tenant + auto-exec | Done |
| **P2** | Reliability / webhooks / ready | Done |
| **P3** | Agent production contract | Done |
| **P4** | Prod-like agent E2E + HITL | Done |
| **P5** | Competitor gaps | Done |
| **P6** | Compose + pilot smoke | Done |
| **P7** | FE agent/HITL/connectors UX | Done |
| **P8** | Release readiness / backlog close | Done |

---

## Audit method notes

- Static grep + targeted reads; prior subagent audits merged.
- P8: no known P0 open; P1 either fixed or accepted risk with named owner.
- Do not push from release prep unless explicitly requested.
