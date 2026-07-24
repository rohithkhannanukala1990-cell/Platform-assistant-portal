# Grafana / Prometheus alert rules (Phase 15)

Recommended alerts for enterprise beta. Implement in Grafana Alerting or
Prometheus `rule_files`. Metrics are scraped from the backend `/metrics`
endpoint (see `prometheus/prometheus.yml`).

## 1. API 5xx rate

**Intent:** Catch backend outages and unhandled errors.

```promql
sum(rate(aiops_http_requests_total{status_code=~"5.."}[5m]))
  /
clamp_min(sum(rate(aiops_http_requests_total[5m])), 1e-9)
```

| Setting | Suggestion |
|---------|------------|
| Threshold | `> 0.05` (5% of requests) for 5m |
| Severity | critical |
| Silence | Deploy windows |

## 2. Webhook signature failures

**Intent:** Detect misconfigured secrets, replay attacks, or attacker probes.

```promql
sum(rate(webhook_signature_failures_total[5m]))
```

| Setting | Suggestion |
|---------|------------|
| Threshold | `> 0.1` for 5m (sustained rejects) |
| Severity | warning → critical if `> 1` for 10m |
| Notes | Metric also aliased conceptually as webhook failures |

Also watch duplicates (usually benign):

```promql
sum(rate(webhook_duplicates_total[5m])) by (source)
```

## 3. Celery queue depth

**Intent:** Catch broker backlog before triage/notify latency spikes.

```promql
celery_queue_depth{queue=~"triage|notify|celery"}
```

| Setting | Suggestion |
|---------|------------|
| Threshold | `> 100` for 10m on any queue |
| Severity | warning; `> 500` critical |
| Notes | Gauge is Redis `LLEN` at scrape time; 0 when Redis unreachable |

Also alert on dead-letters:

```promql
sum(increase(celery_task_failures_total[15m])) > 0
```

## Related panels

Dashboard JSON: `deploy/grafana/dashboards/platform-overview.json`  
Provisioned via compose volume mounts (see `docker-compose.yml` `grafana` service).
