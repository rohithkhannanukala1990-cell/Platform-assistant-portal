# Agent real-world checklist (Phase P6)

Operator runbook for a **production-like** pilot with **real** connector keys.
Do **not** commit secrets. Prefer `.env.production` (gitignored) and Tool Registry vault refs.

Prerequisites: `deploy/docker-compose.prod.yml` up, `scripts/pilot_smoke.sh` green.

---

## a) Configure `.env.production`

1. `cp .env.production.example .env.production`
2. Set strong values (no placeholders):
   - `SECRET_KEY`, `POSTGRES_PASSWORD`, `REDIS_PASSWORD`, `DEFAULT_ADMIN_PASSWORD`
   - `SECRETS_ENCRYPTION_KEY` — Fernet key from:
     `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`
3. Confirm flags (already in the example):
   - `ENV=production`
   - `ENABLE_DEMO_DATA=false`
   - `ENFORCE_WORKSPACE_ISOLATION=true`
   - `LLM_MOCK=0`
4. Add LLM keys as needed: `OPENAI_API_KEY` and/or `ANTHROPIC_API_KEY`
5. Optional: `GITHUB_WEBHOOK_SECRET` if using GitHub webhooks
6. Bring up stack:
   ```bash
   docker compose -f deploy/docker-compose.prod.yml --env-file .env.production up -d --build
   bash scripts/pilot_smoke.sh
   ```

---

## b) Connect tools in the UI

1. Log in as admin (strong password from env).
2. Ensure you have an active **workspace** (isolation is enforced).
3. Open **Tool Registry** and connect at least:
   - **GitHub** — PAT with `repo` + `actions:read` (or finer scopes for your org)
   - **PagerDuty** — API token for incidents / on-call
4. Pin active accounts for your user (UserContext / account switcher).
5. Confirm User B (separate login) does **not** see User A’s accounts (step h).

---

## c) Run `code_review_agent` on a small repo

1. Agents → run with override `code_review_agent` (or natural language “review PR #N in owner/repo”).
2. Prefer a small public or internal PR with few files.
3. Expect:
   - HTTP 200 (not 500)
   - `grounding` ∈ `live|partial`
   - Findings reference **only** files/content from the PR evidence
4. If GitHub is disconnected → `skipped` / `grounding=none` (honest no_data).

---

## d) Run `pipeline_monitor_agent` on a failed workflow

1. Pick a known failed GitHub Actions `run_id` (or use a staging repo).
2. Run with `owner`, `repo`, `run_id` params.
3. Expect evidence containing that run id; failed jobs listed from GitHub — no invented workflows.
4. Without GitHub → no_data / skipped.

---

## e) Incident → triage → dry-run → approve/reject

1. Create or ingest an incident (UI or `open_incident` catalog action).
2. Open Incident Command Center → triage / remediation proposal.
3. Prefer **dry-run** before execute.
4. For mutating commands in production:
   - Expect HITL / `pending_approval`
   - Admin **approve** (dry-run policy preview first) or **reject**
5. Second approve of the same run must be refused (400/409).
6. Policy deny (e.g. `rm -rf /`) must **fail** without shell execute.

---

## f) Generate postmortem

1. On a resolved (or documented) incident → **Generate** postmortem.
2. Confirm SEV template (Critical → SEV1) and action_items checklist.
3. **Download** and/or **Copy markdown**.
4. Timeline must only reflect known incident events (no invented times/actors).

---

## g) Verify audit export

1. Admin → Audit log → export CSV/JSON (`/api/audit/export`).
2. Confirm recent events appear: login, agent runs, approvals, tool account creates.
3. Optional: immutable export with hash chain when enabled.

---

## h) Tenant / ownership isolation (User B)

1. Create User A and User B (same or different tenants per your pilot design).
2. As User A, create a GitHub or PagerDuty ToolAccount.
3. As User B:
   - List tool accounts → must **not** include A’s account
   - Agent run with A’s `tool_accounts` id hint → must not resolve A’s credentials
4. Cross-tenant incident GET → 404 for foreign tenant.

---

## Exit criteria

| Check | Pass |
|-------|------|
| `pilot_smoke.sh` | ready + agents + policy evaluate |
| Demo data | Off — no fake green CI/DORA |
| HITL | Prod mutating paths require approval |
| Isolation | B cannot use A’s tools |
| No secrets in git | `.env.production` untracked |

See also: `docs/PILOT_PLAYBOOK.md`, `docs/BETA_GONOGO.md`, `docs/AGENTS.md`.
