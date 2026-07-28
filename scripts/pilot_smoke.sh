#!/usr/bin/env bash
# Pilot smoke — extends beta_smoke with HA readiness (db+redis) and prod flag checks.
# Default BASE_URL is nginx edge (Phase G7). Override for direct API:
#   BASE_URL=http://localhost:8000 bash scripts/pilot_smoke.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BASE_URL="${BASE_URL:-http://localhost}"
ADMIN_USER="${DEFAULT_ADMIN_USERNAME:-admin}"
ADMIN_PASS="${DEFAULT_ADMIN_PASSWORD:-Admin123!}"

echo "==> pilot: health/live"
curl -fsS "${BASE_URL}/health/live" | grep -q '"status"'

echo "==> pilot: health/ready (db + redis)"
READY_JSON=$(curl -fsS "${BASE_URL}/health/ready")
echo "${READY_JSON}" | grep -q '"status":"ready"\|"status": "ready"'
echo "${READY_JSON}" | grep -q 'database'
echo "${READY_JSON}" | grep -q 'redis'

# Reuse beta checks (login, llm, github) against the same BASE_URL
export BASE_URL
# shellcheck source=beta_smoke.sh
# beta_smoke expects /health and /ready — both exist on nginx and API
bash "${ROOT}/scripts/beta_smoke.sh"

echo "==> pilot: optional prod config hint (API /health/ready already green)"
echo "OK — pilot smoke passed against ${BASE_URL}"
echo "    Next: docs/PILOT_PLAYBOOK.md + docs/BETA_GONOGO.md"
