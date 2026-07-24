# Backup & restore runbook

Operational guide for backing up Platform-assistant-portal data when using
`docker compose` (Postgres service name: **`postgres`**, database **`aiops`**).

## What to back up

| Asset | Why |
|-------|-----|
| Postgres volume / logical dump | Incidents, catalog, tool accounts (encrypted refs), audit, webhook delivery ledger, sessions |
| `.env` / `backend/.env` (offline, encrypted) | `SECRET_KEY`, `SECRETS_ENCRYPTION_KEY`, SSO/JWT keys — **required to decrypt vault refs and verify JWTs** |
| Optional: Grafana / Prometheus volumes | Observability history only |

## What NOT to back up

- `node_modules/`
- Frontend `dist/` / build caches
- `__pycache__/`, `.pytest_cache/`, `*.pyc`
- Local SQLite test DBs (`backend/test_pytest.db`, etc.)
- Redis data (ephemeral queues/locks — recreate on restore)

## Secret key warning

Losing `SECRET_KEY` or `SECRETS_ENCRYPTION_KEY` after a restore means:

- Existing JWTs cannot be verified (users must re-login).
- ToolAccount `credentials_vault_ref` blobs cannot be decrypted.

Back up encryption keys **separately** from the database dump (e.g. password manager / KMS), never commit them to git.

## pg_dump (docker-compose)

From the repo root, with the stack running:

```bash
# Logical dump (recommended)
docker compose exec -T postgres \
  pg_dump -U postgres -d aiops --clean --if-exists \
  > backup-aiops-$(date +%Y%m%d).sql

# Or compressed custom format
docker compose exec -T postgres \
  pg_dump -U postgres -d aiops -Fc \
  > backup-aiops-$(date +%Y%m%d).dump
```

Default compose credentials (override via `.env`):

- User: `postgres`
- Password: `POSTGRES_PASSWORD` (default `postgres123`)
- DB: `aiops`

## Restore

```bash
# Plain SQL dump
docker compose exec -T postgres \
  psql -U postgres -d aiops < backup-aiops-YYYYMMDD.sql

# Custom format
docker compose exec -T postgres \
  pg_restore -U postgres -d aiops --clean --if-exists < backup-aiops-YYYYMMDD.dump
```

After restore:

1. Restore `.env` secrets (`SECRET_KEY`, `SECRETS_ENCRYPTION_KEY`, webhook secrets).
2. `docker compose up -d` and confirm `/api/health` / `/api/health/full`.
3. Spot-check Tool Registry connections and a sample incident.

## Volume snapshot (optional)

Compose volume name is typically `*_postgres_data`. Prefer logical dumps for portability; use volume snapshots only for cold DR of the same host/engine.
