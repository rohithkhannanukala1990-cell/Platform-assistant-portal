# Agent platform (Phase G2)

Quality bar for every specialist agent: **grounding**, **evidence**, **guardrails**, **HITL**.

## Contract

Every agent must:

1. Return `AgentResult` with `grounding` ∈ `{live, partial, none, demo}`.
2. Attach `evidence[]` entries (`type`, `title`, `source`, optional `url` / `snippet`) for any claim.
3. If the primary tool is missing → `status=skipped`, `grounding=none` via `_no_data_result` (never invent connector data).
4. Use LLM only to summarize/plan from an **EVIDENCE** blob (`GROUNDING_RULES`).
5. Pass any commands through `CommandValidator.validate_with_context` / `_apply_command_policy` (Phase G1).
6. Force HITL (`requires_approval`) for mutating work in production.

## Catalog

| Agent | Mode | Primary tools | Prod HITL |
|-------|------|---------------|-----------|
| `code_review_agent` | read_only | GitHub (+ MCP) | — |
| `pipeline_monitor_agent` | read_only | GitHub Actions | — |
| `incident_agent` | mutating writes | PagerDuty | ack/resolve/create |
| `infra_agent` | mutating | Kubernetes | delete/scale |
| `auto_heal_agent` | mutating | Kubernetes | always in prod |
| `alert_noise_agent` | read_only (Rules-based correlation) | PagerDuty + AlertRule | — |
| `scorecard_agent` | read_only | Scorecards DB | — |
| `deploy_agent` | mutating | K8s / Helm / Actions | prod |
| `migration_agent` | mutating | kubectl/helm/terraform | prod + backup reminder |
| `tester_agent` | mutating retry | GitHub CI | prod |
| `security_agent` | read_only | AWS Security Hub / scanners | — |
| `runbook_agent` | plan / HITL | Catalog / Golden paths | prod |
| `documentation_agent` | read_only | GitHub README | — |
| `onboarding_agent` | plan HITL | Templates / Golden paths | prod |
| `cost_agent` | read_only | AWS Cost Explorer | — |
| `dependency_drift_agent` | read_only | GitHub manifests | — |
| `catalog_health_agent` | read_only | Catalog DB | — |

## HITL matrix

| Situation | Behavior |
|-----------|----------|
| Policy `deny` | `status=failed`, no approval_payload, audit `agent_run_denied_policy` |
| Policy `require_approval` | `requires_approval=True`, pending HITL |
| Production + mutating agent | HITL even if policy allows |
| MCP dangerous tools | Still HITL via MCP bridge (M1) |
| Read-only agents | Never execute shell commands |

## Orchestrator guarantees

- Requires `user_id`; rejects missing `tenant_id` when `ENFORCE_WORKSPACE_ISOLATION` is on (else fills defaults)
- 30s timeout, RBAC gate, command cap (25); agent exceptions → failed `AgentResult`
- Re-validates commands with policy context (strip read_only; prod mutating → HITL)
- Persists `evidence` / `grounding` / `policy` into run `details_json`
- Redacts secrets before persist; audits `agent_run_started` / `agent_run_completed` / `agent_run_denied_policy` / `agent_pending_approval`

## UI

Agent runner / history show a **grounding badge**, collapsible **evidence**, **policy** summary, and a Tool Registry link when `grounding=none`.

## Production verification

Before promoting agent changes:

1. **Contract in code** — every `AGENT_REGISTRY` agent returns `AgentResult` via `_result` / `_no_data_result` / `finalize_result` (policy + HITL + command cap 25 + secret redaction).
2. **Read-only** — `read_only=True` agents always clear `details.commands` / approval commands; orchestrator strips again.
3. **Production mutating** — context `environment` in `{production,prod,dr}` **or** process `ENV` same → mutating agents set `requires_approval=True`; `auto_heal_agent` never executes without approval.
4. **Deny never executes** — policy `deny` → `status=failed`, empty commands, audit `agent_run_denied_policy`.
5. **Eval harness** — `pytest backend/tests/test_agent_eval_harness.py -q` loads `backend/tests/fixtures/agents/*.json` (incident, code review, pipeline, auto-heal, deploy, scorecard, alert noise, infra, migration).
6. **LLM failures** — agent/orchestrator catch → `status=failed` AgentResult (not HTTP 500 from the run path).
7. **Evidence size** — `_call_llm` truncates evidence (~30k chars) and always injects `GROUNDING_RULES`.

## See also

- [`COMMAND_POLICY.md`](./COMMAND_POLICY.md) — Guardrails v2
- [`MCP.md`](./MCP.md) — MCP HITL tools
- [`PRODUCTION_BUG_BACKLOG.md`](./PRODUCTION_BUG_BACKLOG.md) — agent IDs fixed in P3
