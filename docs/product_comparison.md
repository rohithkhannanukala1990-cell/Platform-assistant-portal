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
| Scorecards | ✓ | ✓ | ~ (plugins) | ✗ | Evidence checks + weights; **live GitHub Actions CI** when connector present, metadata fallback offline |
| Self-service actions | ~ | ✓ | ~ | ✗ | CatalogAction builtins + HITL deploy propose; not a full Port action marketplace |
| Golden paths / scaffolder | ~ | ~ | ✓ | ✗ | Templates + runs + clearer invalid-template errors; not Backstage Software Templates depth |
| On-call now | ~ | ✗ | ✗ | ✓ | Multi-schedule list + PD deep links; **scheduling stays in PagerDuty** |
| Alert correlation | ~ | ✗ | ✗ | ✓ | Rules-based grouping/suppress + **dry-run tester** + admin counters — not ML |
| Postmortems | ✓ | ✗ | ✗ | ✓ | SEV1/SEV2 templates, action-item checklist, copy markdown; timeline grounded (no invent) |
| Agents + HITL | ✓ | ✗ | ✗ | ~ | Guardrails / command policy (G1–G2) |
| First-class connectors | ~ | ~ | ~ | ~ | Slack/Prom/Argo/webhook pack (G5); long-tail via MCP |
| MCP long-tail | ✓ | ✗ | ~ | ✗ | Explicitly not a replacement for Tool Registry |
| Production HA compose | ✓ | n/a | n/a | n/a | G7: dual API + dual Celery + Postgres/Redis/nginx |

Update this table when a ~ becomes a real ✓ (or when we intentionally stay ~).
