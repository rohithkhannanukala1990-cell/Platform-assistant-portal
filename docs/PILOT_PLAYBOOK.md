# Pilot playbook — 2-week design partner (Phase G7)

Use with [`BETA_GONOGO.md`](./BETA_GONOGO.md), [`SCALING.md`](./SCALING.md), and
`deploy/docker-compose.prod.yml`. Goal: run a **track-record pilot** on the HA
compose baseline (Postgres + Redis, dual API + dual Celery, nginx upstream),
not a laptop SQLite demo.

## Week 0 — Prep (before kickoff)

1. Complete go/no-go in `BETA_GONOGO.md` (including G1–G6 feature boxes).
2. Copy `.env.production.example` → `.env.production`; set strong secrets.
3. Bring up HA stack:

```bash
docker compose -f deploy/docker-compose.prod.yml --env-file .env.production up -d --build
bash scripts/pilot_smoke.sh   # BASE_URL=http://localhost by default (nginx)
```

4. Confirm `/health/ready` returns `status=ready` with `checks.database` + `checks.redis` ok.
5. Rotate seed admin password; enroll MFA if required.
6. Connect first-class tools the partner will use (GitHub, PagerDuty, Slack, …) via Tool Registry — **no global env fallbacks** on API paths.
7. Walk `scripts/agent_realworld_checklist.md` with real keys (code review → pipeline → HITL → postmortem → audit → User B isolation).

## Week 1 — Design partner focus

| Day | Focus | Partner asks |
|-----|--------|--------------|
| 1–2 | Catalog + scorecards v2 + self-service actions | Can teams self-serve golden path / scorecard refresh without tickets? |
| 3 | Incidents + postmortem generate/edit/download | Is the AI postmortem usable as a first draft? |
| 4 | On-call widget + alert rules | Does “who is on-call” + rules-based grouping reduce noise? |
| 5 | Agents + command policy HITL | Do approvals feel safe in production env? |

Daily: capture friction in a shared doc (blocker / workaround / ask).

## Week 2 — Depth + track record

| Day | Focus | Partner asks |
|-----|--------|--------------|
| 6–7 | Connector pack (Slack notify HITL, Prometheus, Argo CD, outbound webhook) | Which connectors are must-have vs MCP long-tail? |
| 8 | Multi-user / workspace isolation | Can two teams share one portal without cross-leak? |
| 9 | Restore drill (backup runbook) + ready/HA failover note | Can we recover DB and still pass smoke? |
| 10 | Retro + go/no-go for paid pilot or expand | Decide next 30 days |

## Success metrics (suggest agreeing Day 1)

| Metric | Target (2 weeks) | How to measure |
|--------|------------------|----------------|
| Time-to-first-value | < 1 day after stack up | Partner creates catalog entity + evaluates scorecard |
| Alert noise | ≥ 20% fewer pages vs prior week (if PD connected) | PD + portal suppress/group metrics |
| HITL trust | 0 unapproved prod commands executed | Audit + agent approval queue |
| Self-service | ≥ 5 catalog actions executed | Audit `catalog_action_executed` |
| Ready SLO | `/health/ready` success ≥ 99% during pilot hours | nginx/LB checks or uptime probe |
| Feedback loop | ≥ 8 written notes (bug/idea/praise) | Shared feedback doc |

## Feedback channels

- **In-product:** Settings → support / admin notes; audit export for evidence.
- **Async:** shared Slack/Teams channel + weekly 30-min sync.
- **Structured:** end-of-week form — Must fix / Nice to have / Won’t use.
- **Exit interview (Day 10):** Would you replace or keep Port/Backstage/incident.io tools for these jobs? See honest comparison in [`product_comparison.md`](./product_comparison.md).

## Out of scope for a 2-week pilot

- Multi-region Postgres HA / automatic failover
- Full k6 load suite (use light smoke in `SCALING.md`)
- Replacing partner’s PagerDuty scheduling or Backstage plugins wholesale

## Sign-off

- [ ] Pilot smoke green against nginx URL
- [ ] Partner success metrics recorded
- [ ] Feedback summarized → backlog
- [ ] BETA_GONOGO still green after week 2
