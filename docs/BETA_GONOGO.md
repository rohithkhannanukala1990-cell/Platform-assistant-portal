# Enterprise beta — go / no-go checklist

Use this before promoting a production (or customer beta) environment.
Related: [`RUNBOOK_BACKUP.md`](./RUNBOOK_BACKUP.md), [`ALERT_RULES.md`](../deploy/grafana/ALERT_RULES.md), [`.env.production.example`](../.env.production.example).

## Go / no-go

- [ ] Phase 8 secrets + scoping (Fernet at rest, no secret leakage on GET, scoped ToolAccounts)
- [ ] Phase 9 isolation tests green (`pytest backend/tests/test_phase9_isolation.py -q`)
- [ ] Demo data off in prod (`ENABLE_DEMO_DATA=false`, `ENV=production`)
- [ ] MFA policy decided (`MFA_REQUIRED_ROLES` / settings `mfa_required_roles`)
- [ ] Backup restore rehearsed once (see `docs/RUNBOOK_BACKUP.md`)
- [ ] GitHub connected path smoke tested (Tool Registry PAT → `/api/github/repos`)
- [ ] No placeholder users (seed admin password rotated; no demo/test accounts in prod DB)
- [ ] Audit export works (`GET /api/audit/export` as Admin)

## Quick smoke

```bash
# From repo root (API must be up)
bash scripts/beta_smoke.sh
# Or:
pytest backend/tests/test_phase15_beta_smoke.py -q -m smoke
```

## Required secrets reminder

| Secret | Purpose |
|--------|---------|
| `SECRET_KEY` | JWT signing |
| `SECRETS_ENCRYPTION_KEY` | Decrypt ToolAccount vault refs |
| `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` | LLM (or DB-stored keys) |
| `GITHUB_WEBHOOK_SECRET` | HMAC for GitHub webhooks in production |

**No-go** if any required secret is still a compose/dev default (`dev_jwt_secret_change_me`, empty Fernet key, `LLM_MOCK=1`, or `ENABLE_DEMO_DATA=true`).
