# Pilot playbook — two-week evaluation

This is for a platform, DevOps, or SRE team of roughly 5–50 engineers with an on-call rotation, deciding whether this portal is worth adopting. By the end of two weeks you'll know whether the agents produce output your team actually trusts, whether the approval model fits how you already work, and whether it's worth the operational overhead of running one more service — backed by your own team's judgment, not a vendor's claims.

## Set expectations honestly, first

This has no production track record anywhere. If you run this pilot, **you would be the first production deployment.** That's not a disqualifier, but it should shape how you scope the two weeks:

- You will find things nobody else has found. Budget time for that; don't treat it as a sign something is unusually broken.
- **Don't put this on the critical path for a real incident in week one.** Run it alongside your existing tools and compare, rather than relying on it before you've built confidence.
- What's ready: the agent catalog, the two-layer command policy, the approval inbox (web + Slack + terminal), the workflow engine, the editor, compliance evidence collection.
- What isn't: a production track record, load-tested multi-region HA, and a certified compliance posture. See [Out of scope](#out-of-scope-for-a-two-week-pilot) below.
- What you need from your side: someone with admin access to set up connectors, a short list of real recent incidents to compare agent output against, and 30–60 minutes a day from 2–3 engineers during week 1.

## Week 0 — Setup (before kickoff)

1. **Provision a VM.** 4 vCPU, 8GB RAM, ~20GB disk is enough for the HA compose baseline (Postgres + Redis, dual API + dual Celery, nginx). Don't run the pilot on a laptop SQLite setup — you want it to behave like it would in production.
2. **Configure secrets.** Copy `.env.production.example` → `.env.production` and set strong values — `SECRET_KEY`, `SECRETS_ENCRYPTION_KEY`, database and Redis passwords, at minimum. The backend refuses to start with default/empty secrets outside test environments — that's intentional, not a bug to work around.
3. **Bring up the stack:**

   ```bash
   docker compose -f deploy/docker-compose.prod.yml --env-file .env.production up -d --build
   bash scripts/pilot_smoke.sh   # BASE_URL defaults to http://localhost (nginx)
   ```

4. **Confirm health.** `/health/ready` should report `status=ready` with both `checks.database` and `checks.redis` OK.
5. **Secure it.** Rotate the seed admin password immediately; enroll MFA if your policy requires it. This machine will hold real (if scoped-down) credentials — treat it like production infrastructure, because from a security standpoint, it is.
6. **Connect tools, in priority order.** Each one unlocks a specific slice of agent capability:
   - **GitHub** first — unlocks code review, pipeline monitoring, dependency drift, documentation agents, and the editor's repo browsing. Most agents lean on it.
   - **PagerDuty** second — unlocks incident, alert noise, and on-call agents. Together with GitHub, these two cover most of what a pilot will actually exercise.
   - **Slack** — unlocks approvals from Slack and incident notifications. Cheap to set up, high visibility for the team.
   - Everything else (AWS, Kubernetes, Jira, ServiceNow, Okta, ArgoCD, Prometheus, Confluence) as relevant to what you'll actually test.
7. **Seed enough of the catalog to be real.** A handful of actual services with real owners — not a demo dataset. Agents grounding against an empty catalog will tell you that honestly (`grounding=none`), which is correct behavior, but it also means you haven't tested anything yet.
8. **Decide who's involved.** At minimum: one admin who owns setup and connector configuration, two or three engineers who'll spend real time in week 1, and whoever ordinarily approves production changes — they need to be comfortable with the approval flow before week 1 starts.

## Week 1 — Does it produce useful output?

The organizing idea for this week: **compare agent output against incidents that already happened.** You don't need to wait for a real outage to judge accuracy — pull three or four recent incidents and ask the incident agent to investigate them fresh. If its summary and evidence match what you already know happened, that's a real signal. If it doesn't, that's exactly the kind of gap this pilot exists to find.

| Day | Focus | What to do | Questions to ask honestly |
|---|---|---|---|
| 1 | Catalog and scorecards | Seed real services, run scorecard evaluations | Does the completeness/health scoring match your own sense of which services are in good shape? |
| 2 | Incident review | Pick 2–3 past incidents, run the incident agent against them retroactively | Does the evidence it gathers match what actually happened? Would its summary have saved you time at 3am? |
| 3 | On-call and alerts | Connect PagerDuty, check current coverage, try alert noise correlation | Does the coverage-gap detection catch anything real? Does noise correlation flag things you'd actually suppress? |
| 4 | Code review and pipelines | Point the code review agent at a real open PR; run pipeline monitor against a real CI failure | Is the review actually useful, or generic? Does the CI triage save a trip to the Actions log? |
| 5 | Approvals, end to end | Trigger one approval each way — approve from the **web UI**, then from **Slack**, then queue one from the **terminal** | Does each path feel equally trustworthy? Would your team actually use Slack approvals, or default to the web UI out of caution? |

Capture friction daily in a shared doc — see [Feedback collection](#feedback-collection) below for the format.

## Week 2 — Would this fit how we work?

| Day | Focus | What to do | Questions to ask honestly |
|---|---|---|---|
| 6–7 | Workflows | Build one workflow that mirrors something your team does manually and repeatedly | Is the safety model (forced first dry-run, re-approval after edits) reassuring or just friction? |
| 8 | Editor and terminal in daily use | Have engineers use the editor and terminal for real (small) tasks over these two days, not a scripted demo | Does it save time over your normal editor/terminal, or just add a context switch? |
| 9 | Multi-team isolation | If you have more than one team, set up two workspaces and confirm neither can see the other's data/credentials | Any cross-team leakage, even minor? This is a hard requirement, not a nice-to-have. |
| 10 | Backup and restore drill | Follow [`RUNBOOK_BACKUP.md`](./RUNBOOK_BACKUP.md) — take a real backup, then actually restore from it | Did the restore work cleanly? How long did it take? Would that recovery time be acceptable in a real incident? |
| — | Retro | Walk through the metrics table below and the collected feedback as a team | See [Decision questions](#decision-questions) below |

## Metrics

Agree on these Day 1, so nobody's re-litigating what "success" means during the retro.

| Metric | Suggested target | How to measure |
|---|---|---|
| Time-to-first-value | < 1 day after stack is up | First real catalog entity created and scorecard evaluated |
| Alert noise reduction | ≥ 20% fewer pages vs. the prior week (if PagerDuty connected) | Compare PagerDuty + portal suppression/grouping metrics |
| Agent accuracy on past incidents | Team consensus: "would have helped" on ≥ 2 of the 3–4 incidents tested | Day 2 exercise, judged qualitatively by the team |
| Self-service actions | ≥ 5 catalog/workflow actions run without a ticket | Audit log |
| Readiness SLO | `/health/ready` success ≥ 99% during pilot hours | nginx/LB checks or an uptime probe |
| Feedback volume | ≥ 8 written notes across blocker/friction/wish | Shared feedback doc |
| **Unapproved production changes** | **Zero. Not a target — a requirement.** | Audit log + approval inbox history |

That last row isn't like the others. The entire safety model in this portal rests on production changes going through approval — everything else in this pilot is secondary to that number staying at zero. **If it's ever not zero, stop and investigate before continuing the pilot.** Don't average it into a scorecard; treat a single unapproved production change as a pilot-halting event until you understand exactly why it happened.

## Feedback collection

Capture notes daily, in three categories:

- **Blocker** — stops you from doing something you need to do.
- **Friction** — works, but is annoying, confusing, or slower than it should be.
- **Wish** — doesn't exist yet, would be nice.

**Friction is the most valuable category, not the least.** Blockers get fixed because they're impossible to ignore — someone hits one and the work stops until it's resolved. Friction is what quietly kills adoption three weeks after the pilot ends, once the novelty wears off and people drift back to their old tools because the new one was just a little more annoying every time. Pay closer attention to a recurring friction note than to a single dramatic blocker.

## Out of scope for a two-week pilot

Don't expect any of the following to be validated or delivered in two weeks:

- Multi-region Postgres HA or automatic failover
- A full load-testing pass (a light smoke test is enough — see [`SCALING.md`](./SCALING.md))
- Custom agents built for your specific environment
- SOC 2 certification (the [Compliance](./USER_GUIDE.md#compliance) page maps controls and surfaces gaps — it is not a certification)
- Replacing your existing PagerDuty scheduling or internal-tooling plugins wholesale

## Decision questions

Walk through these as a team at the end of week 2:

1. **Would you use this next week if the pilot ended today?** Not "would you consider it" — would you actually reach for it on Monday.
2. **What's the single biggest blocker to real adoption**, and is it something that gets fixed, or something structural?
3. **Did the approval model build trust or erode it?** Two weeks of watching agents propose and humans approve should give a real answer either way.
4. **What would change your mind** — either direction — in the next 30 days?

Three honest outcomes, all legitimate:

- **Adopt** — move to a longer paid pilot or production rollout, with a scoped plan for the gaps you found.
- **Adopt with conditions** — specific blockers need fixing first; revisit in a defined timeframe.
- **Stop** — this isn't the right fit, or not yet. Document why.

A documented **no** is worth more than a polite **yes**. If the pilot didn't earn real trust, say so plainly — that's a more useful outcome for both sides than a lukewarm "sure, maybe" that quietly goes nowhere.
