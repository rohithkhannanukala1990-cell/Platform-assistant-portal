# Enterprise beta — go / no-go checklist

Use this before promoting a production (or customer beta / design-partner pilot) environment.
Related: [`PRODUCTION_READINESS.md`](./PRODUCTION_READINESS.md), [`PILOT_PLAYBOOK.md`](./PILOT_PLAYBOOK.md),
[`product_comparison.md`](./product_comparison.md), [`RUNBOOK_BACKUP.md`](./RUNBOOK_BACKUP.md),
[`ALERT_RULES.md`](../deploy/grafana/ALERT_RULES.md),
[`.env.production.example`](../.env.production.example), [`deploy/docker-compose.prod.yml`](../deploy/docker-compose.prod.yml).

**Legend:** `[x]` = proven by automated tests / compose defaults / CI.  
`[ ]` = **human / ops** — must be verified on the live pilot stack with real secrets.

## Go / no-go

### Security & isolation (Phase 8–9 / 15)
- [x] Phase 8 secrets + scoping (Fernet at rest, no secret leakage on GET, scoped ToolAccounts) — covered by phase 8 / secrets tests
- [x] Phase 9 isolation tests green (`pytest backend/tests/test_phase9_isolation.py -q`)
- [x] Demo data off in prod compose defaults (`ENABLE_DEMO_DATA=false`, `ENV=production` in `docker-compose.prod.yml` + example env)
- [x] Workspace isolation on (`ENFORCE_WORKSPACE_ISOLATION=true` in prod compose + example env)
- [ ] MFA policy decided (`MFA_REQUIRED_ROLES` / settings `mfa_required_roles`) — **human**
- [ ] Backup restore rehearsed once (see `docs/RUNBOOK_BACKUP.md`) — **human**
- [ ] GitHub connected path smoke tested (Tool Registry PAT → `/api/github/repos`) — **human** (real PAT)
- [ ] No placeholder users (seed admin password rotated; no demo/test accounts in prod DB) — **human**
- [ ] Audit export works (`GET /api/audit/export` as Admin) — **human** on live stack

### Gap-close features (Phase G1–G6)
- [x] **G1** Command policy engine — deny / allow / require_approval — automated (`test_phase_g1_command_policy.py` + evaluate API)
- [x] **G2** Agent grounding + evidence / HITL matrix — automated (P3/P4 eval + prod E2E); see `docs/AGENTS.md`
- [ ] **G3** Postmortem generate / edit / download on a **real** incident — **human**
- [ ] **G4** On-call widget + at least one alert rule proven on **live ingest** — **human** (dry-run API automated)
- [ ] **G5** First-class connectors needed by partner connected — **human** (registry + connector unit tests automated)
- [x] **G6** Catalog self-service + scorecard v2 evidence model — automated (`test_phase_g6_*`, P5 live CI path); partner still should click-through once — see `product_comparison.md`

### HA / pilot baseline (Phase G7 / P6)
- [x] Prod compose baseline: Postgres + Redis (no SQLite), **api ×2**, **celery ×2**, nginx upstream — `test_phase_g7_ha_pilot.py` / `test_phase_p6_compose_config.py`
- [x] `/health/ready` returns ready with database + redis checks (logic + pytest; live probe on deploy)
- [ ] `bash scripts/pilot_smoke.sh` green against **live** nginx URL — **human** (script maintained in P6)
- [ ] Pilot playbook week-0 prep done (`docs/PILOT_PLAYBOOK.md`) — **human**
- [ ] Agent real-world checklist with real keys (`scripts/agent_realworld_checklist.md`) — **human**

## Quick smoke

```bash
# Automated (no live stack required)
pytest backend/tests -q
pytest backend/tests/test_phase15_beta_smoke.py backend/tests/test_phase_g7_ha_pilot.py backend/tests/test_phase_p6_compose_config.py -q

# Live stack (human)
bash scripts/beta_smoke.sh
bash scripts/pilot_smoke.sh          # /health/ready + agents + policy evaluate
```

## Required secrets reminder

| Secret | Purpose |
|--------|---------|
| `SECRET_KEY` | JWT signing |
| `SECRETS_ENCRYPTION_KEY` | Decrypt ToolAccount vault refs |
| `POSTGRES_PASSWORD` / `REDIS_PASSWORD` | Prod compose data plane |
| `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` | LLM (or DB-stored keys) |
| `GITHUB_WEBHOOK_SECRET` | HMAC for GitHub webhooks in production |

**No-go** if any required secret is still a compose/dev default (`dev_jwt_secret_change_me`, empty Fernet key, `LLM_MOCK=1`, or `ENABLE_DEMO_DATA=true`).
