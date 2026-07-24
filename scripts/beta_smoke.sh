#!/usr/bin/env bash
# Beta smoke checks against a running API (default http://localhost:8000).
set -euo pipefail

BASE_URL="${BASE_URL:-http://localhost:8000}"
ADMIN_USER="${DEFAULT_ADMIN_USERNAME:-admin}"
ADMIN_PASS="${DEFAULT_ADMIN_PASSWORD:-Admin123!}"

echo "==> health"
curl -fsS "${BASE_URL}/health" | grep -q '"status"'

echo "==> ready"
curl -fsS "${BASE_URL}/ready" | grep -q '"status":"ready"\|"status": "ready"'

echo "==> login"
TOKEN=$(curl -fsS -X POST "${BASE_URL}/auth/login" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=${ADMIN_USER}&password=${ADMIN_PASS}" \
  | python -c "import sys,json; print(json.load(sys.stdin)['access_token'])")
test -n "${TOKEN}"

echo "==> llm status"
curl -fsS "${BASE_URL}/api/llm/status" \
  -H "Authorization: Bearer ${TOKEN}" | grep -q .

echo "==> github repos (expect 400 without account)"
CODE=$(curl -sS -o /tmp/gh_repos.json -w "%{http_code}" \
  "${BASE_URL}/api/github/repos" \
  -H "Authorization: Bearer ${TOKEN}" || true)
if [[ "${CODE}" != "400" && "${CODE}" != "200" ]]; then
  echo "unexpected /api/github/repos status: ${CODE}" >&2
  cat /tmp/gh_repos.json >&2 || true
  exit 1
fi
echo "github repos HTTP ${CODE} (400=no account, 200=connected)"

echo "OK — beta smoke passed against ${BASE_URL}"
