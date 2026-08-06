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

Internal review (Aug 2026): **~7.5–8 / 10** for a design-partner pilot — not a claim of product perfection.

What already lifts the score: HITL agents, tenant isolation, backend test depth, docs, LLM cost tracking.

What still blocks a higher score:

| Gap | Why it matters |
|-----|----------------|
| Preview/demo pages | Deployments + Data Tools are labeled **Preview** and show sample banners — still not live integrations |
| Frontend tests | Growing Vitest suite; still thin vs route count |
| No TypeScript | Large JSX surface without static types |
| God files | Catalog/auth/AI/health modules remain large |
| Soft dep audits | Full `pip-audit` / moderate `npm audit` stay advisory until baselines are clean |

Path toward **9+**: replace preview pages with live connectors, TypeScript on critical FE modules, split god files, hard-fail remaining audits, browser e2e for login → catalog → agent approve.

## What remains (~ vs competitors)

- **Self-service** — not a Port action marketplace; catalog HITL post-approve may be status-only (ID-033).
- **Golden paths** — not Backstage Software Templates depth.
- **On-call / alerts** — read-only PD view + rules-based correlation; scheduling & ML stay with PD / incident.io.
- **Postmortems** — strong first draft; not full Scribe workflow.
- **Ops polish** — metrics edge exposure (ID-075), some legacy FE `fetch` paths, triage grounding (ID-060).

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
