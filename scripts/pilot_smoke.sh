#!/usr/bin/env bash
# Pilot smoke — HA readiness + authenticated agent/policy checks (Phase G7/P6).
# Default BASE_URL is nginx edge. Override for direct API:
#   BASE_URL=http://localhost:8000 bash scripts/pilot_smoke.sh
#
# Exits non-zero on HTTP 500 or failed assertions. Never prints secrets.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BASE_URL="${BASE_URL:-http://localhost}"
ADMIN_USER="${DEFAULT_ADMIN_USERNAME:-admin}"
ADMIN_PASS="${DEFAULT_ADMIN_PASSWORD:-Admin123!}"
WORKSPACE_ID="${SMOKE_WORKSPACE_ID:-smoke-ws}"
TMP_DIR="${TMPDIR:-/tmp}"
GH_OUT="${TMP_DIR}/pilot_gh_repos.$$.json"
POLICY_OUT="${TMP_DIR}/pilot_policy.$$.json"
AGENTS_OUT="${TMP_DIR}/pilot_agents.$$.json"
trap 'rm -f "${GH_OUT}" "${POLICY_OUT}" "${AGENTS_OUT}"' EXIT

auth_hdr() {
  echo "Authorization: Bearer ${TOKEN}"
}

echo "==> pilot: health/live"
LIVE_CODE=$(curl -sS -o /tmp/pilot_live.json -w "%{http_code}" "${BASE_URL}/health/live" || true)
if [[ "${LIVE_CODE}" == "500" ]]; then
  echo "FAIL health/live returned HTTP 500" >&2
  cat /tmp/pilot_live.json >&2 || true
  exit 1
fi
curl -fsS "${BASE_URL}/health/live" | grep -q '"status"'

echo "==> pilot: health/ready must be ready (db + redis)"
READY_CODE=$(curl -sS -o /tmp/pilot_ready.json -w "%{http_code}" "${BASE_URL}/health/ready" || true)
if [[ "${READY_CODE}" == "500" ]]; then
  echo "FAIL health/ready returned HTTP 500" >&2
  cat /tmp/pilot_ready.json >&2 || true
  exit 1
fi
READY_JSON=$(curl -fsS "${BASE_URL}/health/ready")
echo "${READY_JSON}" | grep -q '"status":"ready"\|"status": "ready"'
echo "${READY_JSON}" | grep -q 'database'
echo "${READY_JSON}" | grep -q 'redis'
# Reject not_ready / degraded pilots
if echo "${READY_JSON}" | grep -qi '"status":[[:space:]]*"not_ready"'; then
  echo "FAIL health/ready is not_ready: ${READY_JSON}" >&2
  exit 1
fi

echo "==> pilot: login"
LOGIN_CODE=$(curl -sS -o /tmp/pilot_login.json -w "%{http_code}" -X POST "${BASE_URL}/auth/login" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=${ADMIN_USER}&password=${ADMIN_PASS}" || true)
if [[ "${LOGIN_CODE}" == "500" ]]; then
  echo "FAIL login returned HTTP 500" >&2
  exit 1
fi
TOKEN=$(python -c "import json; print(json.load(open('/tmp/pilot_login.json'))['access_token'])")
test -n "${TOKEN}"

echo "==> pilot: /api/llm/status"
LLM_CODE=$(curl -sS -o /tmp/pilot_llm.json -w "%{http_code}" \
  "${BASE_URL}/api/llm/status" \
  -H "$(auth_hdr)" \
  -H "X-Workspace-Id: ${WORKSPACE_ID}" || true)
if [[ "${LLM_CODE}" == "500" ]]; then
  echo "FAIL /api/llm/status returned HTTP 500" >&2
  cat /tmp/pilot_llm.json >&2 || true
  exit 1
fi
if [[ "${LLM_CODE}" != "200" ]]; then
  echo "FAIL /api/llm/status HTTP ${LLM_CODE}" >&2
  cat /tmp/pilot_llm.json >&2 || true
  exit 1
fi
grep -q . /tmp/pilot_llm.json

echo "==> pilot: authenticated GET /api/agents/"
AGENTS_CODE=$(curl -sS -o "${AGENTS_OUT}" -w "%{http_code}" \
  "${BASE_URL}/api/agents/" \
  -H "$(auth_hdr)" \
  -H "X-Workspace-Id: ${WORKSPACE_ID}" || true)
if [[ "${AGENTS_CODE}" == "500" ]]; then
  echo "FAIL /api/agents/ returned HTTP 500" >&2
  cat "${AGENTS_OUT}" >&2 || true
  exit 1
fi
if [[ "${AGENTS_CODE}" != "200" ]]; then
  echo "FAIL /api/agents/ HTTP ${AGENTS_CODE}" >&2
  cat "${AGENTS_OUT}" >&2 || true
  exit 1
fi
python -c "import json,sys; data=json.load(open(sys.argv[1])); assert isinstance(data,list) and len(data)>=1" "${AGENTS_OUT}"

echo "==> pilot: /api/policies/commands/evaluate (kubectl get sample)"
POLICY_CODE=$(curl -sS -o "${POLICY_OUT}" -w "%{http_code}" \
  -X POST "${BASE_URL}/api/policies/commands/evaluate" \
  -H "$(auth_hdr)" \
  -H "Content-Type: application/json" \
  -H "X-Workspace-Id: ${WORKSPACE_ID}" \
  -d '{"command":"kubectl get pods -n default","environment":"production","tool":"shell"}' || true)
if [[ "${POLICY_CODE}" == "500" ]]; then
  echo "FAIL policy evaluate returned HTTP 500" >&2
  cat "${POLICY_OUT}" >&2 || true
  exit 1
fi
if [[ "${POLICY_CODE}" != "200" ]]; then
  echo "FAIL policy evaluate HTTP ${POLICY_CODE}" >&2
  cat "${POLICY_OUT}" >&2 || true
  exit 1
fi
python -c "import json,sys; d=json.load(open(sys.argv[1])); assert 'effect' in d" "${POLICY_OUT}"

echo "==> pilot: github repos (expect 400 without account, 200 when connected)"
GH_CODE=$(curl -sS -o "${GH_OUT}" -w "%{http_code}" \
  "${BASE_URL}/api/github/repos" \
  -H "$(auth_hdr)" \
  -H "X-Workspace-Id: ${WORKSPACE_ID}" || true)
if [[ "${GH_CODE}" == "500" ]]; then
  echo "FAIL /api/github/repos returned HTTP 500" >&2
  cat "${GH_OUT}" >&2 || true
  exit 1
fi
if [[ "${GH_CODE}" != "400" && "${GH_CODE}" != "200" ]]; then
  echo "unexpected /api/github/repos status: ${GH_CODE}" >&2
  cat "${GH_OUT}" >&2 || true
  exit 1
fi
echo "github repos HTTP ${GH_CODE} (400=no account, 200=connected)"

echo "OK — pilot smoke passed against ${BASE_URL}"
echo "    Next: scripts/agent_realworld_checklist.md + docs/PILOT_PLAYBOOK.md"
