# Command policy engine (Guardrails v2 — Phase G1)

How AI-proposed and human-approved commands are authorized before execution.

> Positioning note: the guardrail layer is a **structured policy engine (v1)**,
> not a regex-only blocklist. The regex blocklist still exists but is only the
> first, non-negotiable layer.

## Two layers

1. **Baseline blocklist** (`backend/command_validator.py`) — compiled regex
   patterns for catastrophic commands (`rm -rf`, `mkfs`, `dd if=`, `DROP
   DATABASE`, fork bombs, `curl | bash`, …). Always runs first. A hit is an
   unconditional **deny** with reason `baseline_blocklist` — approval cannot
   override it.
2. **CommandPolicy engine** (`backend/services/command_policy.py`) — DB-backed
   `CommandPolicyRule` rows evaluated in priority order (lower first). The
   first rule whose context *and* command condition match decides the effect.

## Effects

| Effect | Meaning |
|--------|---------|
| `allow` | Safe for auto-execution (`safe_for_auto=True`) |
| `require_approval` | Must go through HITL approval before execution |
| `deny` | Never executes; audited as `command_policy_denied` |

For a list of commands the **worst effect wins**: `deny` >
`require_approval` > `allow`.

## Rule matching

A rule matches when ALL of its context conditions hold:

- `match_roles` — caller role (`["*"]` = any)
- `match_environments` — `production`/`prod`/`dr` are one bucket
- `match_tools` — logical tool (`shell`, `kubernetes`, `github`, …)

and its command condition holds:

- `match_command_prefixes` — argv prefix match after `shlex.split`
  (`"kubectl delete"` matches `kubectl delete pod x`; tokens ending in `=`
  match by prefix, so `"dd if="` matches `dd if=/dev/zero`)
- `match_regex` — case-insensitive regex on the raw command
- If **both** are set, either matching counts. If **neither** is set, the rule
  matches any command (context-only rule — used for the production catch-all).

Rules with `tenant_id = NULL` are global defaults; tenant-scoped rules apply
only to that tenant. Both are evaluated for a tenant's commands, ordered by
priority.

## Fail-closed behavior

- A command that `shlex.split` cannot parse → `require_approval`
  (`matched_rule_ids=["parse_failure"]`).
- The seeded `production-default-approval` rule (priority 900) forces
  `require_approval` for **any** production command that no earlier `allow`
  rule matched.
- `SafeExecutor.execute` re-evaluates policy **per step** at execution time:
  - `deny` → stop, audit `command_policy_denied`
  - `require_approval` without `context["approved"]=True` → refuse, audit
    `command_policy_approval_required`
- Call sites that predate policy context get a conservative default context
  (role `User`, environment from `ENV`, no approval flag).

## Seeded defaults

| Effect | Rules |
|--------|-------|
| deny | `rm -rf /`, `mkfs`, `dd if=`, `DROP DATABASE/SCHEMA`, `kubectl delete namespace`, `chmod -R 777 /`, fork bomb |
| allow (priority 30) | `kubectl get/describe/logs/top`, `git status/log/diff`, `curl` to `/health`-style endpoints |
| require_approval (priority 50) | `kubectl delete`, `kubectl scale`, `helm uninstall`, `terraform apply/destroy` |
| require_approval (priority 900) | production catch-all |

Seeds are written only when the table has no global rules, so admin edits
survive restarts.

## Where policy is enforced

| Path | Enforcement |
|------|-------------|
| `SafeExecutor.dry_run/execute` | per-step, with audit |
| Orchestrator `_validate_commands_in_result` | deny → run failed (no pending approval with bad commands); require_approval → `requires_approval=True` |
| Incident dry-run/approve (`/api/incidents/{id}/...`) | approve endpoint passes `approved=True` (it IS the HITL step) |
| Agent run approval (`/api/agents/{run_id}/approve`) | passes `approved=True` |
| WebSocket terminal (`ws_portal`) | require_approval commands are refused interactively |
| Agent base `_execute` | auto-execution never carries the approval flag |

## Admin API

Prefix `/api/policies/commands`:

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| GET | `/` | any user | list rules (global + own tenant) |
| POST | `/` | admin | create rule (`tenant_scoped: true` binds to caller tenant) |
| PUT | `/{id}` | admin | update rule |
| DELETE | `/{id}` | admin | delete rule |
| POST | `/evaluate` | any user | dry-evaluate `{command, environment, tool}` |

UI: Settings → **Command policy** — rule table + "Test command" box.

## Audit events

`command_policy_denied`, `command_policy_approval_required`,
`command_policy_rule_created/updated/deleted`.
