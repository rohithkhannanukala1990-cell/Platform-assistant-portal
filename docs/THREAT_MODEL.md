# Threat model (short STRIDE) — Platform Assistant Portal

Scope: the FastAPI backend, React UI, Postgres, Redis/Celery, and MCP edge.
Out of scope: customer cloud accounts beyond connector credentials the portal stores.

| STRIDE | Threat | Mitigations in product |
|--------|--------|------------------------|
| **S**poofing | Stolen JWT / forged login | JWT with `jti` session registry + logout/revoke; login rate limit + lockout (Redis); MFA policy for admin roles; SSO when configured |
| **T**ampering | Altered audit history or webhook payloads | Audit export with optional SHA-256 hash chain (`immutable=true`); webhook HMAC over raw body; ToolAccount secrets encrypted at rest |
| **R**epudiation | “I didn’t approve that” | Audit log for login/MFA/approve/reject/MCP; actor + IP on HITL decisions; immutable export for offline evidence |
| **I**nformation disclosure | Tokens/PATs in logs or API | Secrets masked on GET (`has_credentials` / `env_keys`); `write_audit` redacts secret-like keys/values; demo data gated off in production |
| **D**enial of service | Login / webhook / chat flood | SlowAPI limits on login, chat, triage, webhooks; Celery queue depth metrics + alerts |
| **E**levation of privilege | Cross-tenant or admin bypass | Tenant middleware + `assert_same_tenant`; workspace isolation flag; RBAC `require_admin` / `require_role`; MCP write tools only create HITL-pending work |

## Trust boundaries

1. Browser → API (JWT + CORS allowlist)
2. API → Postgres / Redis
3. API → external SaaS (GitHub, PagerDuty, LLM) via scoped ToolAccounts
4. MCP stdio/SSE edge (`PORTAL_MCP_TOKEN`) — not a substitute for portal RBAC

## Residual risks

- Self-hosted secrets (`SECRET_KEY`, `SECRETS_ENCRYPTION_KEY`) lost ⇒ cannot decrypt vault refs — see `RUNBOOK_BACKUP.md`
- `continue-on-error` dependency audits in CI warn but do not block merges by default — review `pip-audit` / `npm audit` output on each release
- MCP stdio child process inherits env — treat IDE MCP config as a secret store

Last reviewed: Phase 16 (compliance pack).
