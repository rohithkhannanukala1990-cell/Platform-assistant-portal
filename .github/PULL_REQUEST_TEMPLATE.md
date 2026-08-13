## What and why

<!-- What changes, and why it's needed. If it fixes a bug, say whether the bug
     was in the code or in a test's assumption. -->

## Safety review

<!-- The important section. See CONTRIBUTING.md#safety-invariants. -->

- [ ] This change **does not** touch an approval, policy, or execution path
- [ ] This change **does** touch one of those paths — described below

<!-- If it touches one, answer these. Delete if it doesn't. -->

Which path (approval / command policy / agent execution / tenant isolation /
secret handling / subprocess)?

How did you verify the invariant still holds?

## Invariants

Tick only what applies to this change — not everything is relevant to every PR.

- [ ] No write action can execute in production without a recorded human approval
- [ ] Approvals still use compare-and-swap (`claim_*`), not check-then-update
- [ ] Every agent result still carries a `grounding` value; no-data returns `_no_data_result`
- [ ] Cross-tenant access still returns 404, not 403
- [ ] No secret can reach a response, log, audit entry, or agent evidence blob
- [ ] Any new subprocess call passes `shell=False` with an argument list
- [ ] Any new command path still goes through `CommandValidator.validate_with_context`

## Tests

- [ ] `make test-backend` passes
- [ ] `make test-frontend` passes
- [ ] `make smoke` passes 9/9
- [ ] New or changed behaviour has a test covering it

<!-- If you changed raw SQL, confirm you checked it against Postgres, not just
     SQLite — CI runs the backend suite against Postgres 16. -->

- [ ] Not applicable / no raw SQL changed
- [ ] Raw SQL changed and verified against Postgres

## Anything reviewers should know

<!-- Known limitations, follow-up work, things you deliberately left out.
     Deliberate omissions are fine — silent ones aren't. -->
