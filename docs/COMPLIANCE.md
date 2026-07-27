# Compliance control mapping

Maps common enterprise control themes to Platform Assistant features.
This is a **control → feature** index, not a formal certification.

| Control theme | Evidence / feature | Where |
|---------------|-------------------|--------|
| Access control | JWT auth, roles (Admin/User/ReadOnly), RBAC permissions | `backend/auth.py`, `/api/rbac` |
| MFA | `MFA_REQUIRED_ROLES` / settings; TOTP enroll | Phase 13, Settings |
| Session management | JWT `jti` registry, logout, revoke all | `/api/auth/sessions` |
| Tenant isolation | Middleware + `assert_same_tenant` | Phase 9 |
| Secrets at rest | Fernet `SECRETS_ENCRYPTION_KEY` for ToolAccount / LLM keys | Phase 8 |
| Secrets in transit / UI | Never return decrypted secrets; `has_credentials` only | Tool Registry, MCP servers |
| Audit logging | `AuditLog` + `write_audit` (with secret redaction) | `/api/audit` |
| Audit retention | Setting `audit_log_retention_days` (default 90); prune job | `/api/audit/retention`, `cron_jobs.archive_old_logs` |
| Immutable evidence | Export with SHA-256 hash chain | `GET /api/audit/export?immutable=true&format=json` |
| Change control / HITL | Incident approve/reject; agent approvals; MCP write tools pending | Phases 11, M1–M2 |
| Webhook integrity | HMAC verify before processing; delivery idempotency | Phases 10, 14 |
| Vulnerability mgmt | `pip-audit` + `npm audit` in CI | `.github/workflows/ci.yml`, `pr-check.yml` |
| Secure defaults (prod) | Demo data off, isolation on, mock LLM off | `.env.production.example`, Phase 15 |
| Backup / recovery | Postgres dump/restore runbook; secret-key warning | `docs/RUNBOOK_BACKUP.md` |
| Threat modeling | Short STRIDE | `docs/THREAT_MODEL.md` |
| Beta go/no-go | Checklist before customer beta | `docs/BETA_GONOGO.md` |
| Observability | Metrics, Grafana dashboard, alert recipes | Phase 15, `deploy/grafana/` |

## Privacy notes

- Passwords, TOTP codes, and API tokens must not appear in `AuditLog.detail` — enforced by `sanitize_audit_detail` / `redact_secrets` and covered by tests.
- Audit exports are admin-only.

## Dependency pin review (Phase 16)

Reviewed `backend/requirements.txt` and root `package.json`:

- **Pinned (==):** FastAPI, uvicorn, httpx, jose, passlib/bcrypt, slowapi, sentry-sdk, apscheduler, python-multipart, python-dotenv
- **Floor-pinned (>=):** sqlmodel, cryptography, openai, celery, redis, k8s/cloud SDKs — allow security patches within major lines
- **CI:** `pip-audit --requirement backend/requirements.txt`; `npm audit --audit-level=moderate`
- Action: before GA, re-run both audits and bump any high/critical findings; prefer pinning new direct deps with `==` when added

## Related docs

- [`THREAT_MODEL.md`](./THREAT_MODEL.md)
- [`BETA_GONOGO.md`](./BETA_GONOGO.md)
- [`RUNBOOK_BACKUP.md`](./RUNBOOK_BACKUP.md)
- [`MCP.md`](./MCP.md)
- [`ARCHITECTURE.md`](./ARCHITECTURE.md)
