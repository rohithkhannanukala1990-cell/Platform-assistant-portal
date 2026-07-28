# Product comparison — honest gaps vs adjacent tools (Phase G7)

This is a **design-partner honesty** sheet, not marketing. Symbols:

| Symbol | Meaning |
|--------|---------|
| ✓ | Shipped and usable in portal for the stated job |
| ~ | Partial / rules-based / offline-safe / HITL-gated — not full parity |
| ✗ | Out of scope or not built |

| Capability | Platform Assistant | Port | Backstage | incident.io / PD Scribe | Notes |
|------------|-------------------|------|-----------|-------------------------|-------|
| Service catalog | ✓ | ✓ | ✓ | ✗ | Portal catalog + dependencies |
| Scorecards | ~ | ✓ | ~ (plugins) | ✗ | G6 evidence checks + weights; CI green is **offline/metadata**, not live GitHub Checks API |
| Self-service actions | ~ | ✓ | ~ | ✗ | CatalogAction builtins + HITL deploy propose; not a full Port action marketplace |
| Golden paths / scaffolder | ~ | ~ | ✓ | ✗ | Templates + runs exist; not Backstage Software Templates depth |
| On-call now | ~ | ✗ | ✗ | ✓ | Widget + PD schedules; **scheduling stays in PagerDuty** |
| Alert correlation | ~ | ✗ | ✗ | ✓ | **Rules-based** grouping/suppress (G4) — not ML |
| Postmortems | ~ | ✗ | ✗ | ✓ | AI draft from incident evidence (G3); not a full timeline product |
| Agents + HITL | ✓ | ✗ | ✗ | ~ | Guardrails / command policy (G1–G2) |
| First-class connectors | ~ | ~ | ~ | ~ | Slack/Prom/Argo/webhook pack (G5); long-tail via MCP |
| MCP long-tail | ✓ | ✗ | ~ | ✗ | Explicitly not a replacement for Tool Registry |
| Production HA compose | ✓ | n/a | n/a | n/a | G7: dual API + dual Celery + Postgres/Redis/nginx |

Update this table when a ~ becomes a real ✓ (or when we intentionally stay ~).
