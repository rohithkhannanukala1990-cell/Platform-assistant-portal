# Product comparison — honest gaps vs adjacent tools

This is a **design-partner honesty sheet, not marketing.** If you are evaluating this portal, the fastest way to a good decision is knowing precisely where it loses.

Last reviewed against the market: August 2026.

| Symbol | Meaning |
|--------|---------|
| ✓ | Shipped and usable for the stated job |
| ~ | Partial — rules-based, HITL-gated, or shallower than a specialist tool |
| ✗ | Out of scope or not built |

---

## Start here: what changed in the market

When this portal started, human-in-the-loop approval for AI remediation was a genuine differentiator. **It no longer is.** By 2026 every serious platform ships remediation behind a gate — AWS DevOps Agent needs explicit action approval, Datadog's Bits Dev Agent opens PRs for humans to merge, incident.io's "Code it up" drafts a PR, and New Relic refuses to remediate at all on principle.

The reasoning behind that convergence is worth stating because it is also this portal's design thesis: autonomous remediation failure modes are asymmetric — a false-positive restart that takes down the payment system costs far more than a false-negative page that wakes an engineer.

So "we have HITL" is table stakes. What follows is what actually remains different, and what does not.

---

## Two markets, and this portal sits between them

**Internal developer portals** — Backstage, Port, Cortex, OpsLevel, Humanitec. Service catalog, scorecards, golden paths, self-service. No incident intelligence.

**AI SRE / incident response** — Datadog Bits AI SRE, PagerDuty SRE Agent, incident.io, Rootly, Resolve AI, New Relic SRE Agent, IncidentFox. Triage, root cause, remediation. No catalog or golden paths.

Most production IDP stacks combine a portal with an orchestration layer and a scorecard platform — no single tool covers all three concerns. In practice a team buys one from each column and wires them together.

This portal covers both columns in one deployable product. That is the actual differentiator — not any individual feature.

---

## Versus internal developer portals

| Capability | This portal | Port | Cortex | OpsLevel | Backstage |
|---|---|---|---|---|---|
| Service catalog | ✓ | ✓ | ✓ | ✓ | ✓ |
| Scorecards | ✓ deterministic, evidence-backed | ✓ | ✓ | ✓ | ~ plugins |
| Golden paths / scaffolder | ~ | ~ | ~ | ~ | ✓ deepest |
| Self-service actions | ~ | ✓ strongest | ~ | ~ | ~ plugins |
| Plugin ecosystem | ✗ | ~ | ~ | ~ | ✓ 150+ |
| Incident triage | ✓ | ✗ | ✗ | ✗ | ✗ |
| Agentic remediation | ✓ | ✗ | ✗ | ✗ | ✗ |
| Self-hosted | ✓ | ✗ SaaS | ✗ SaaS | ✗ SaaS | ✓ required |
| Time to production | hours | 3–6 months typical | 6+ months | 30–45 days | 6 months common |
| Licence cost | free, Apache 2.0, self-hosted | ~$30+/user/mo | ~$65/user/mo | ~half of Port | free |
| Real cost | your infrastructure + your time | subscription | subscription | subscription | 3–12 engineers, $2M+ over three years |

**Where we lose.** Backstage's scaffolder and plugin ecosystem are years ahead — if your requirement is "template-driven service creation with deep customisation," Backstage wins and it is not close. Port's self-service action marketplace is more mature than our catalog actions. Cortex and OpsLevel have more polished scorecard UX and far more integrations.

**Where we win.** None of them do incident response at all. If you are buying an IDP *and* an AI SRE tool, that is two subscriptions, two vendors, two data models, and a glue layer you maintain.

---

## Versus AI SRE and incident response

| Capability | This portal | Datadog Bits AI SRE | PagerDuty SRE Agent | incident.io | Rootly | IncidentFox |
|---|---|---|---|---|---|---|
| Autonomous alert investigation | ✓ | ✓ deepest telemetry | ✓ | ✓ | ~ | ✓ |
| Root cause with evidence | ✓ grounded | ✓ | ✓ | ✓ | ~ | ✓ |
| Proposes code fix as PR | ✓ | ✓ | ~ | ✓ | ✗ | ✓ |
| HITL approval gate | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Slack-native approval | ✓ | ✓ | ✓ | ✓ best-in-class | ✓ best-in-class | ~ |
| ML alert correlation | ✗ rules only | ✓ | ✓ | ~ | ~ | ✓ |
| On-call scheduling | ~ read + propose | ✗ | ✓ category leader | ✓ | ✓ | ✗ |
| Postmortem generation | ✓ | ✓ | ✓ | ✓ best-in-class | ✓ | ~ |
| Own telemetry platform | ✗ | ✓ | ✗ | ✗ | ✗ | ✗ |
| Integration count | 12 | 800+ | 700+ | 30+ | 30+ | 300+ |
| Self-hosted | ✓ | ✗ | ✗ | ✗ | ✗ | ✓ Apache 2.0 |
| Service catalog / IDP | ✓ | ✗ | ✗ | ✗ | ✗ | ✗ |
| Published outcome data | ✗ none | ✓ | ✓ | 600+ companies, 250k incidents | 81% MTTR reduction, SOC2 Type II since 2022 | ~ |
| Production track record | **zero** | extensive | extensive | extensive | extensive | growing |

**Where we lose badly.** Integration count is not close — 12 against 300–800. Datadog owns the telemetry, so its agent sees data ours can only reach through a connector. PagerDuty owns on-call scheduling. incident.io and Rootly have years of Slack-native workflow refinement. Resolve AI publishes hard numbers from named enterprises — Coinbase at 72% reduction in critical incident investigation time, DoorDash at 87% faster investigations. We have none of that.

**The closest competitor is IncidentFox.** Apache 2.0 open core, self-hostable, 300+ tools, root cause analysis with fix scripts, and one-click remediation with human-in-the-loop approval. That is nearly our positioning, with 25× the integrations. What it does not have is a service catalog, golden paths, or scorecards.

---

## What is genuinely differentiated

Four things, honestly assessed.

**1. Both categories in one deployment.** No competitor in either table covers the other column. A team running this gets catalog, scorecards, golden paths, incident triage, remediation, and postmortems from one install with one data model. Whether that consolidation is worth being shallower in each area than a specialist is the actual buying question.

**2. Self-hosted with LLM choice.** Runs on your infrastructure under Apache 2.0. Works with OpenAI, Anthropic, or any OpenAI-compatible endpoint — the provider's base URL is configurable per provider record, which is how you point it at a local model served by Ollama, vLLM, or LM Studio. Note the precision there: there is no first-class Ollama integration, and `supported_providers` is `openai`, `openai_compatible`, `anthropic`. Local models work through the OpenAI-compatible path, not a dedicated one. Every SaaS competitor is a proprietary model on their infrastructure. For teams in regulated industries or with data residency constraints, this frequently ends the conversation before features matter. IncidentFox is the only comparable option here.

**3. The command policy engine.** A two-layer gate — a non-overridable baseline blocklist, then database-backed policy rules scoped by role, environment, and tool, resolving to allow / deny / require-approval with worst-effect-wins across a command list, failing closed on anything unparseable. Approvals are race-safe via database compare-and-swap, and the approved artefact is frozen so what you reviewed is exactly what executes. Competitors gate remediation; we have not found one that publishes a policy model at this granularity. Whether buyers value that or find it over-engineered is untested.

**4. Compliance evidence collection.** SOC 2 control mapping (CC6.1, CC6.2, CC6.3, CC7.2, CC7.4, CC8.1) with continuous gap scanning built from data the portal already holds — flagging things like production deploys with no approval record before an auditor does. No IDP or AI SRE tool in either table does this natively.

---

## What is not differentiated any more

Stated plainly so nobody builds a pitch on it:

- **HITL approval.** Table stakes across the entire AI SRE category.
- **AI incident triage.** Six major platforms ship it.
- **PR proposals from AI.** Datadog, incident.io, and IncidentFox all do this.
- **Postmortem generation.** Standard in incident management tools, and incident.io does it better.

---

## Honest weaknesses

**Zero production users.** This is the one that matters. Every competitor has customers, uptime history, and incident scars. Code quality does not substitute for a track record, and no amount of engineering closes this gap — only a first deployment does.

**No ML correlation.** Alert grouping is rules-based, which is a deliberate v1 choice — ML correlation needs training data we do not have. Rules are configurable and predictable; they are not adaptive.

**Integration long tail.** Twelve connectors covers the common stack. MCP handles some of the tail, but a team running something unusual will hit a wall a 300-integration product would not.

**No plugin ecosystem.** Backstage has 150+ community plugins. We have none.

**On-call is read and propose, not manage.** Schedules, rotations, and escalation policies stay in PagerDuty. We surface them and can propose overrides; we do not replace them.

**No compliance certification.** The control *mapping* exists and the evidence collection works. There is no SOC 2 audit report. Rootly has held SOC2 Type II since 2022. For procurement at a regulated enterprise, that difference is decisive.

**Self-hosted means you operate it.** Backups, upgrades, availability, incident response for the portal itself. SaaS competitors absorb that.

---

## Who should and should not use this

**Good fit**

- 20–200 engineers, needing both a catalog and incident intelligence, without budget for two SaaS subscriptions
- Data residency or regulatory constraints that rule out SaaS
- Teams wanting to run their own model rather than send production telemetry to a vendor
- Organisations where every production change genuinely must be human-approved and auditable
- Teams comfortable being an early design partner and shaping the roadmap

**Poor fit**

- Needing a proven track record today — buy incident.io, Rootly, or Datadog
- Deep Backstage plugin requirements
- Needing on-call scheduling replaced — buy PagerDuty
- Needing ML correlation across a very high alert volume
- Wanting SaaS with no operational burden
- Requiring SOC 2 Type II before procurement will sign

---

## The honest summary

Broader than any single competitor, shallower than the specialist in each area, and unproven where all of them are proven.

If your problem is genuinely spread across both catalog and incidents, consolidation plus self-hosting plus model choice is a real value proposition. If your problem is concentrated in one area, buy the specialist — it will be better at that one thing, and it has customers who can vouch for it.

Update this file when a ~ becomes a real ✓, when a competitor closes one of our gaps, or when we deliberately decide to stay ~.
