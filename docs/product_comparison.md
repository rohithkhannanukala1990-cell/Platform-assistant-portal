# Product comparison — honest gaps vs adjacent tools (P8)

This is a **design-partner honesty** sheet, not marketing. Symbols:

| Symbol | Meaning |
|--------|---------|
| ✓ | Shipped and usable in portal for the stated job |
| ~ | Partial / rules-based / offline-safe / HITL-gated — not full parity |
| ✗ | Out of scope or not built |

| Capability | Platform Assistant | Port | Backstage | incident.io / PD Scribe | Notes |
|------------|-------------------|------|-----------|-------------------------|-------|
| Service catalog | ✓ | ✓ | ✓ | ✗ | Portal catalog + dependencies + tenant scope |
| Scorecards | ✓ | ✓ | ~ (plugins) | ✗ | Weighted checks + evidence; **live GitHub Actions CI** when connector present; metadata fallback offline |
| Self-service actions | ~ | ✓ | ~ | ✗ | CatalogAction builtins + HITL deploy propose; not a Port marketplace (catalog post-approve gap ID-033) |
| Golden paths / scaffolder | ~ | ~ | ✓ | ✗ | Templates + runs + validation errors; not Backstage Software Templates depth |
| On-call now | ~ | ✗ | ✗ | ✓ | Multi-schedule list + PD deep links; **scheduling stays in PagerDuty** |
| Alert correlation | ~ | ✗ | ✗ | ✓ | Rules-based grouping/suppress + dry-run tester — **not ML** |
| Postmortems | ✓ | ✗ | ✗ | ~ | SEV1/SEV2 templates, action items, copy markdown; timeline grounded — not full Scribe lifecycle |
| Agents + HITL | ✓ | ✗ | ✗ | ~ | Command policy, grounding/evidence UI, prod HITL approve/reject (P3–P7) |
| First-class connectors | ~ | ~ | ~ | ~ | Slack/Prom/Argo/webhook/GitHub/PD pack; long-tail via MCP |
| MCP long-tail | ✓ | ✗ | ~ | ✗ | Explicitly not a replacement for Tool Registry |
| Tenant / tool isolation | ✓ | ~ | ~ | ~ | Workspace enforcement + ToolAccount ownership (no global env fallback on API) |
| Production HA compose | ✓ | n/a | n/a | n/a | Dual API + dual Celery + Postgres/Redis/nginx + ready probes |

Update this table when a ~ becomes a real ✓ (or when we intentionally stay ~).
