# On-call visibility (Phase G4)

On-call **scheduling, overrides, and escalations remain in PagerDuty**. Platform Assistant Portal provides read-only visibility for operators.

## API

- `GET /api/oncall/now?service=&schedule_id=` — tenant-scoped; uses the caller's connected PagerDuty Tool Account via `pagerduty_access`.
- `GET /api/pagerduty/oncalls` — full roster table (existing Phase 12 route; now supports `schedule_id` and `service` filters).

## UI

- **Ops dashboard** — `OncallWidget` ("Who is on-call") with link to PagerDuty schedules.
- **PagerDuty view** (`/pagerduty`) — compact on-call widget above incidents/on-call tables.

## Connect PagerDuty

1. Open **Tool Registry** → add PagerDuty API key.
2. Widgets show current on-call users from PagerDuty schedules/services.
3. Click **Open in PagerDuty** to manage schedules in PagerDuty.

## Alert rules (rules-based correlation)

Alert correlation is **rules-based only** — not ML. Configure rules in **Settings → Alert rules (v1)** or `GET/POST /api/alert-rules` (admin writes).

Rules apply on webhook/alert ingest before AI triage:

| Action | Behavior |
|--------|----------|
| `suppress` | Drop alert; metric `alerts_suppressed_total` |
| `create_incident` | Triage + optional grouping window |
| `attach_existing` | Within `group_window_sec`, attach to prior incident; metric `alerts_grouped_total` |

`alert_noise_agent` surfaces configured rules and labels output **Rules-based correlation**.
