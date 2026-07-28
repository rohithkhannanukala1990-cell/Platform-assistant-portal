# Enterprise beta — go / no-go checklist

Use this before promoting a production (or customer beta / design-partner pilot) environment.
Related: [`PILOT_PLAYBOOK.md`](./PILOT_PLAYBOOK.md), [`product_comparison.md`](./product_comparison.md),
[`RUNBOOK_BACKUP.md`](./RUNBOOK_BACKUP.md), [`ALERT_RULES.md`](../deploy/grafana/ALERT_RULES.md),
[`.env.production.example`](../.env.production.example), [`deploy/docker-compose.prod.yml`](../deploy/docker-compose.prod.yml).

## Go / no-go

### Security & isolation (Phase 8–9 / 15)
- [ ] Phase 8 secrets + scoping (Fernet at rest, no secret leakage on GET, scoped ToolAccounts)
- [ ] Phase 9 isolation tests green (`pytest backend/tests/test_phase9_isolation.py -q`)
- [ ] Demo data off in prod (`ENABLE_DEMO_DATA=false`, `ENV=production`)
- [ ] Workspace isolation on (`ENFORCE_WORKSPACE_ISOLATION=true`)
- [ ] MFA policy decided (`MFA_REQUIRED_ROLES` / settings `mfa_required_roles`)
- [ ] Backup restore rehearsed once (see `docs/RUNBOOK_BACKUP.md`)
- [ ] GitHub connected path smoke tested (Tool Registry PAT → `/api/github/repos`)
- [ ] No placeholder users (seed admin password rotated; no demo/test accounts in prod DB)
- [ ] Audit export works (`GET /api/audit/export` as Admin)

### Gap-close features (Phase G1–G6)
- [ ] **G1** Command policy engine — deny / allow / require_approval evaluated; Settings policy panel reviewed
- [ ] **G2** Agent grounding + evidence — no invented connector facts; HITL matrix understood (`docs/AGENTS.md`)
- [ ] **G3** Postmortem generate / edit / download on a real incident
- [ ] **G4** On-call widget + at least one alert rule (suppress or group) proven on ingest
- [ ] **G5** First-class connectors needed by partner connected (Slack / Prometheus / Argo / outbound webhook as applicable)
- [ ] **G6** Catalog self-service action executed; scorecard v2 shows pass/fail evidence (honest ~ vs Port/Backstage — see `product_comparison.md`)

### HA / pilot baseline (Phase G7)
- [ ] Prod compose up: Postgres + Redis (no SQLite), **api ×2**, **celery ×2**, nginx upstream
- [ ] `/health/ready` returns ready with database + redis checks
- [ ] `bash scripts/pilot_smoke.sh` green against nginx URL
- [ ] Pilot playbook week-0 prep done (`docs/PILOT_PLAYBOOK.md`)

## Quick smoke

```bash
# From repo root (API or nginx edge must be up)
bash scripts/beta_smoke.sh
bash scripts/pilot_smoke.sh          # extends beta with /health/ready
# Or:
pytest backend/tests/test_phase15_beta_smoke.py backend/tests/test_phase_g7_ha_pilot.py -q
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
