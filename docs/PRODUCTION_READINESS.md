# Production readiness (one-pager)

**Status: Production candidate (Phase P8)** — safe for a **design-partner pilot** on the HA compose baseline.  
Not a claim of Port/Backstage/incident.io feature parity.

## What is ready

| Area | Ready |
|------|--------|
| Security baseline | Approval CAS, tenant isolation on critical paths, SSRF/TLS defaults, non-root API image, Fernet secrets, demo-data off in prod |
| Agents | Production contract (grounding, evidence, policy, HITL), eval harness, prod-like E2E tests |
| Incidents | Approve/reject, postmortem SEV templates + markdown, command policy |
| Catalog / scorecards | Self-service builtins, scorecard evidence + optional live GitHub CI |
| HA deploy | `deploy/docker-compose.prod.yml` — api×2, workers×2, Postgres, Redis, nginx, `/health/ready` |
| FE pilot UX | Agent grounding/HITL states, Tool Registry errors without raw tokens, safe login errors |
| Automation | `pytest backend/tests` green; compose config tests; `scripts/pilot_smoke.sh` |

**P0 blockers:** none open. Remaining P1 FE/ops items are **accepted risk** with owners — see `docs/PRODUCTION_BUG_BACKLOG.md`.

## Quality score (honest)

Canonical scorecard (Aug 2026). **Primary public number: design-partner pilot 8.2 / 10** — ship to a friendly org with guardrails. Not a claim of GA SaaS or category parity.

| Lens | Score | Meaning |
|------|-------|---------|
| Design-partner pilot | **8.2 / 10** | Primary rating — ship to a friendly org with guardrails |
| Feature ambition / architecture | 8.5 / 10 | Agents, HITL, catalog, incidents, MCP, cost tracking |
| Engineering rigor | 8.5 / 10 | Deep backend tests, Postgres CI, docs, Alembic |
| Security posture | 7.5 / 10 | Real controls; HITL mostly prod; soft audits; default-cred risk |
| Frontend polish / product UX | 7.5 / 10 | Much improved; partial TS; thin browser e2e |
| GA multi-tenant SaaS | 6.5–7 / 10 | Not there yet without P0/P1 hardening |
| vs category leaders (parity) | 5–6 / 10 | Broad surface, not category depth everywhere |

What already lifts the scores: HITL agents, tenant isolation, backend test depth, docs, LLM cost tracking,
typed Auth/API helpers, live Deployments (GitHub Actions + optional Argo CD), preview-labeled labs,
authFetch consistency, Postgres pytest in CI, Playwright login smoke.

What still caps the pilot / FE / security lenses:

| Gap | Why it matters |
|-----|----------------|
| Partial TypeScript | Critical modules typed; most pages still JSX |
| Preview Data Tools | Sample schema/lineage/storage until live connectors |
| Frontend tests | Growing Vitest + one Playwright smoke; still thin vs route count |
| God files | Catalog/auth/AI/health modules remain large |
| Soft dep audits | Full `pip-audit` / moderate `npm audit` stay advisory until baselines are clean |

Path toward **9.5+ pilot**: TypeScript across high-traffic pages, expand browser e2e beyond login, split god files, hard-fail remaining audits, replace remaining preview Data Tools.

## What remains (~ vs competitors)

- **Self-service** — not a Port action marketplace; catalog HITL post-approve may be status-only (ID-033).
- **Golden paths** — not Backstage Software Templates depth.
- **On-call / alerts** — read-only PD view + rules-based correlation; scheduling & ML stay with PD / incident.io.
- **Postmortems** — strong first draft; not full Scribe workflow.
- **Ops polish** — JWT TTL tuning (ID-023); triage grounding fixed (ID-060).

Honest matrix: [`docs/product_comparison.md`](./product_comparison.md).

## How to run a pilot

1. Copy env and set **strong** secrets (never commit `.env.production`):
   ```bash
   cp .env.production.example .env.production
   # SECRET_KEY, SECRETS_ENCRYPTION_KEY (Fernet), POSTGRES/REDIS/ADMIN passwords, LLM keys
   ```
2. Bring up HA stack:
   ```bash
   docker compose -f deploy/docker-compose.prod.yml --env-file .env.production up -d --build
   ```
3. Automate smoke against nginx (default `http://localhost`):
   ```bash
   bash scripts/pilot_smoke.sh
   ```
4. Complete human go/no-go boxes in [`docs/BETA_GONOGO.md`](./BETA_GONOGO.md) (MFA, backup drill, real PAT, admin rotation).
5. Walk the 2-week partner plan: [`docs/PILOT_PLAYBOOK.md`](./PILOT_PLAYBOOK.md).

## Agent real-world checklist

With **real** OpenAI/Anthropic, GitHub PAT, and PagerDuty token:

→ **[`scripts/agent_realworld_checklist.md`](../scripts/agent_realworld_checklist.md)**  
(env → Tool Registry → code_review → pipeline_monitor → incident HITL → postmortem → audit export → User B isolation)

## Regression before release

```bash
pytest backend/tests -q
npm test   # FE vitest (optional but recommended after UI changes)
```

**Do not go** if: demo data on, isolation off, empty Fernet/JWT secrets, or any P0 reopens.
