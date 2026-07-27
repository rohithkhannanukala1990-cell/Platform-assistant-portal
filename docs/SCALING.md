# Scaling & HA notes (Phase 17)

How to run Platform-assistant-portal with multiple API replicas and shared state.

## Multiple API replicas

- Run N identical FastAPI processes behind a load balancer (nginx, ALB, Traefik).
- Point all replicas at the **same Postgres** and the **same Redis** (`REDIS_URL` / `CELERY_BROKER_URL`).
- Do **not** rely on in-process memory for login lockout or rate limits in multi-replica deploys.

When Redis is configured:

| Concern | Behavior |
|---------|----------|
| Login lockout | Redis lists keyed by username (`auth` module) |
| SlowAPI rate limits | Shared counters via Limiter `storage_uri` (falls back to memory if Redis blips) |
| Celery | Broker + result backend on Redis |

Without Redis, lockout and rate limits are **per-process** (fine for single-replica local/dev only).

Optional override: `RATELIMIT_STORAGE_URL` (checked before `CELERY_BROKER_URL` / `REDIS_URL`).

## Sticky sessions not required (JWT)

Auth is bearer JWT (plus optional server-side session revoke via DB/Redis jti). The load balancer does **not** need sticky/session affinity for API traffic.

Exceptions where affinity can still help (optional, not required):

- Long-lived SSE/WebSocket streams if you add them later
- Browser cookie-only flows (this portal uses Authorization headers)

## Celery workers

Scale workers independently of the API:

```bash
# Example: more concurrency for webhook triage / monitors
celery -A backend.tasks worker --loglevel=info --concurrency=4
```

- API replicas enqueue tasks; workers drain Redis queues.
- Dead-letter / failure rows land in `celery_task_failure` for replay (see Phase 14).
- Queue depth is exposed on `/metrics` for capacity alerts.

## Database indexes (hot paths)

Migrated idempotently on startup (`_ensure_scale_indexes`):

- `incident.tenant_id`, `workspace_id`, `timestamp`, `status`
- `user` / `workspaces` / `catalog_entities` / `tool_accounts` / `agent_runs` tenant (and workspace where present)
- `webhookevent.timestamp`, `cloud_event_id`
- `webhook_delivery.delivery_id` (PK; explicit index for clarity)

List endpoints default to **page=1, page_size=50** (max 200) so replicas do not dump unbounded tables.

## Load smoke (not a full k6 suite)

Before a capacity change, run a light smoke — enough to catch connection pool / Redis / 5xx issues:

```bash
# Health
curl -sf "$PORTAL_URL/api/health"

# Authenticated list (replace TOKEN)
for i in $(seq 1 50); do
  curl -sf -H "Authorization: Bearer $TOKEN" \
    "$PORTAL_URL/api/incidents?page=1&page_size=50" >/dev/null || echo fail-$i
done

# Login rate-limit path (expect 429 after burst)
for i in $(seq 1 20); do
  curl -s -o /dev/null -w "%{http_code}\n" -X POST "$PORTAL_URL/auth/login" \
    -H "Content-Type: application/x-www-form-urlencoded" \
    -d "username=nosuch&password=bad"
done
```

Optional one-liner with [hey](https://github.com/rakyll/hey) (install separately):

```bash
hey -n 200 -c 10 -H "Authorization: Bearer $TOKEN" \
  "$PORTAL_URL/api/incidents?page=1&page_size=50"
```

A full k6 scenario is out of scope for Phase 17; use the above as a go/no-go smoke before beta traffic.

## Checklist

- [ ] `REDIS_URL` (or Celery broker URL) set on every API replica and worker
- [ ] Postgres connection pool sized for `replicas × workers`
- [ ] LB health check → `/api/health`
- [ ] Celery worker replicas ≥ 1; alert on queue depth
- [ ] Load smoke passed after deploy
