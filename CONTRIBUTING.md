# Contributing

Thanks for looking at this. Before anything else: read
[the safety invariants](#safety-invariants--do-not-break-these). They are the
part of this codebase that must not regress, and they are easy to break without
noticing.

## Getting set up

The README documents three local-dev paths — fastest (Docker + SQLite), full
stack (Postgres + Redis + real CLI tools), and no Docker — with honest timings
and a what-works/what-doesn't breakdown for each. Rather than duplicate it here
and let the two drift:

**→ [README: Local development](README.md#local-development)**

For most contributions `make dev` is enough. Reach for `make up` when you're
touching terminal CLI execution, Celery-backed background jobs, or anything
Postgres-specific.

If the README's setup steps don't work exactly as written, that's a bug in the
README — please report it or fix it in your PR. A setup doc that's wrong is worse
than one that's vague.

## Running the tests

```bash
make test-backend     # backend suite in Docker
make test-frontend    # frontend suite (vitest)
make smoke            # end-to-end smoke; needs a server already on :8000
```

Without `make`:

```bash
docker compose run --rm -e DATABASE_URL=sqlite:////tmp/test.db \
  -v "$PWD/deploy:/deploy:ro" -v "$PWD/scripts:/scripts:ro" \
  -v "$PWD/.github:/.github:ro" -v "$PWD/.env.production.example:/.env.production.example:ro" \
  backend env -u CELERY_BROKER_URL -u CELERY_RESULT_BACKEND -u RATELIMIT_STORAGE_URL -u REDIS_URL \
  python -m pytest backend/tests/ -q
npm run test
python3 scripts/mock_portal_smoke.py   # Windows: `python` — `python3` hits the Microsoft Store stub
```

The mounts and `env -u` above are not optional garnish: the compose-config tests
resolve repo-root paths that are absent from the backend image, and
`docker compose run` leaks `CELERY_BROKER_URL` into the rate-limiter test.
Without them the suite reports 9 failures that CI does not have.

`make` is not available on Windows by default, which is why every `make` target
above has a raw equivalent.

Two things worth knowing before you debug a failure:

- **CI runs the backend suite against real PostgreSQL 16**, not SQLite. Tests can
  pass locally on SQLite and fail in CI on dialect differences — `PRAGMA` vs
  `pg_indexes`, transaction-abort semantics, type coercion, row ordering without
  `ORDER BY`. If you touch raw SQL, branch on `_is_postgres` (there are 13 such
  branches already) or verify against Postgres:

  ```bash
  docker run -d --name ci-pg -e POSTGRES_USER=postgres -e POSTGRES_PASSWORD=postgres \
    -e POSTGRES_DB=aiops_test -p 5432:5432 postgres:16-alpine
  ```

- **The `client` fixture is module-scoped.** Against a shared database, state
  from one test leaks into the next, and so does in-memory state like the
  rate limiter. If your test depends on a clean starting point, reset it in a
  fixture rather than relying on test order.

## Safety invariants — do not break these

This project's proposition is that AI-proposed changes cannot reach production
without a recorded human approval. These six invariants are what make that true.
A PR that weakens any of them will not be merged, however good the rest is. Each
is enforced by tests; if your change makes one of those tests fail, the change is
wrong, not the test.

**1. No write action executes in production without a recorded human approval.**
Mutating agents in a production environment return `status="pending_approval"`
with an approval payload — they do not execute. `BaseAgent._should_require_approval`
and `requires_approval_envs` drive this. Read-only agents (`read_only = True`)
never carry executable commands at all; the orchestrator strips them a second
time as defence in depth.

**2. Approvals use compare-and-swap, never check-then-update.** Claiming an
approval is a conditional UPDATE — `UPDATE ... WHERE id = ? AND status =
'pending_approval'` — and the winner is decided by row count. See the five
`claim_*` helpers in `backend/services/approval_claim.py`. A read-then-write
sequence lets two concurrent approvers both win and the action execute twice.
Related: an approved artifact is **frozen**. The exact command, file content, or
Terraform plan that was reviewed is what executes; nothing is re-read or
re-planned after approval.

**3. Every agent result carries a grounding value.** One of `live`, `partial`,
`none`, `demo` — `VALID_GROUNDING` in `backend/agents/base.py`. An agent with no
connector data must return `_no_data_result` (`grounding="none"`, `status="skipped"`)
and say so, never an empty result that reads like a clean scan. Agents reason
only over the EVIDENCE block; they must not invent metrics, PR numbers, pod
names, or ticket IDs.

**4. Cross-tenant access returns 404, not 403.** `assert_same_tenant` in
`backend/services/isolation.py` raises 404 deliberately — a 403 confirms the
resource exists, which is itself a leak. Every tenant-scoped query filters on
`tenant_id`.

**5. Secrets never appear in responses, logs, audit entries, or agent evidence.**
`redact_secret_like` / `redact_structure` in `backend/agents/base.py` scrub agent
output; `sanitize_audit_detail` in `backend/services/audit_compliance.py` scrubs
audit rows. Tool accounts expose `has_credentials`, never the credential. If you
add a field that could carry a token, make sure it goes through redaction.

**6. `shell=False` in every subprocess call.** There are currently zero
`shell=True` occurrences in `backend/` and it must stay that way — commands are
passed as argument lists. Every command also goes through the two-layer policy
engine (baseline blocklist, then DB-backed rules) before execution; do not add a
path that skips `CommandValidator.validate_with_context`. Unparseable commands
fail closed to `require_approval`.

## Commit messages

Imperative subject line, then a body explaining **why** rather than restating the
diff. Look at recent history for the shape:

```
Fix test_scale_indexes_exist: PRAGMA is SQLite-only, CI runs Postgres

test_scale_indexes_exist queried index metadata with `PRAGMA index_list(...)`,
which is SQLite syntax and doesn't exist in Postgres — CI's backend-tests job
runs against real Postgres, so this failed every time...
```

Conventional-commit prefixes (`feat:`, `fix:`, `docs:`, `chore:`) appear in the
older history and are fine, but aren't required. What matters is that someone
reading `git log` in a year understands why the change was made.

If you fix a test, say whether the test was wrong or the code was wrong, and why.
That distinction matters more than almost anything else in a commit message here.

## Pull requests

`main` is protected: the four CI jobs — `backend-tests`, `frontend-lint`,
`e2e-smoke`, `docker-build` — must pass before a PR can merge, and the branch
must be up to date. No review approval is required, but the checks are not
optional and admins are not exempt.

```bash
git checkout -b fix/short-description
# ... work, commit ...
git push -u origin fix/short-description
gh pr create --fill
```

Note that `e2e-smoke` and `docker-build` declare `needs: [backend-tests,
frontend-lint]`. If either dependency fails, they show as **skipped**, not
failed — skipped is not passed.

Do not weaken a gate to get green: no `continue-on-error` on the pytest step, no
skip/xfail markers, no deleted tests, no downgraded audit level. If a dependency
has a CVE, bump the dependency.

The PR template asks whether your change touches an approval or policy path.
Answer it honestly — that's the flag for extra scrutiny.

## Reporting bugs and vulnerabilities

Security issues go through [SECURITY.md](SECURITY.md) — privately, never a public
issue. Everything else: use the issue templates. Known open defects already live
in [docs/PRODUCTION_BUG_BACKLOG.md](docs/PRODUCTION_BUG_BACKLOG.md); it's worth
checking there first.

## Licence

Contributions are accepted under the [Apache License 2.0](LICENSE), per §5 of
that licence. There are no per-file licence headers in this repository — please
don't add them.
