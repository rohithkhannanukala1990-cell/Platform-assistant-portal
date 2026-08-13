# Security policy

This project's core proposition is that AI-proposed changes cannot reach
production without a recorded human approval. A vulnerability that lets someone
bypass that gate is the most serious class of bug this repository can have, and
is treated accordingly.

## Supported versions

This project has not yet cut a tagged release and has no production deployments.
Until it does, there is exactly one supported version:

| Version | Supported |
|---|---|
| `main` (latest commit) | ✅ Fixes land here |
| Anything older | ❌ Rebase onto `main` |

Fixes are applied to `main` only. There are no backport branches, and there is no
long-term-support line to promise patches for. When the first tagged release
exists, this table will state a real support window rather than implying one now.

## Reporting a vulnerability

**Do not open a public issue.** A public issue is visible to everyone the moment
it is filed, including before a fix exists.

Report privately through **GitHub's private vulnerability reporting**, which is
enabled on this repository:

1. Go to the [Security tab](https://github.com/rohithkhannanukala1990-cell/Platform-assistant-portal/security)
2. Click **Report a vulnerability**
3. Describe the issue

That creates a private advisory visible only to you and the maintainer, and gives
us a private fork to develop and review the fix in before anything is disclosed.

If you cannot use that route, email the repository owner via their GitHub profile
and put `SECURITY` in the subject. Please do not include exploit details in an
initial email if you can avoid it — ask for the advisory link instead.

### What to include

The more of this you can provide, the faster it gets triaged:

- What an attacker gains — read another tenant's data, execute an unapproved
  command, escalate a role, extract a secret
- Steps to reproduce, ideally against a local `make dev` stack
- The commit SHA you tested
- Which component: agent, connector, policy engine, approval path, terminal,
  editor, webhook receiver, or auth
- Whether it needs authentication, and at what role

## Response commitment

These are commitments deliberately scoped to what a single maintainer on a
pre-production project can actually keep. They are not enterprise SLAs.

| Stage | Target |
|---|---|
| Acknowledgement that the report was received | 3 business days |
| Initial assessment — severity, whether reproducible | 10 business days |
| Fix or documented mitigation for a confirmed critical/high | 30 days |
| Public advisory after a fix ships | Coordinated with you |

If a deadline is going to slip, you will be told before it slips rather than
after. If you get no acknowledgement within 3 business days, assume the report
was missed and re-send it — that is a failure on our side, not impatience on
yours.

You will be credited in the advisory unless you ask not to be. There is no bug
bounty; this is an unfunded project and pretending otherwise would be dishonest.

## Scope

### In scope

- **Approval bypass** — any path that executes a write action in a production
  environment without a recorded approval, or that lets one person satisfy a
  two-approver gate
- **Command policy bypass** — evading the baseline blocklist, or getting a
  `deny` rule to resolve as `allow`
- **Approval race conditions** — defeating the compare-and-swap so an item is
  approved and executed twice
- **Cross-tenant or cross-workspace data access** — anything returning another
  tenant's data instead of a 404
- **Authentication and authorisation** — JWT handling, session revocation, MFA
  enforcement, role escalation, RBAC checks that can be skipped
- **Secret exposure** — credentials in API responses, logs, audit entries, agent
  evidence, or error messages
- **Webhook forgery** — defeating HMAC signature verification or replay windows
- **SSRF** in connectors or the outbound webhook sender
- **Command injection** through the terminal, the safe executor, or agent-proposed
  commands
- **Prompt injection that causes a real side effect** — for example, content in a
  repository or incident that makes an agent execute an action, rather than
  merely producing odd text

### Out of scope

- Anything requiring the attacker to already be an authenticated Admin. Admins
  can configure policy and approve actions by design; that is the product, not a
  vulnerability.
- The intentionally weak defaults in `docker-compose.yml` (`Admin123!`,
  `dev_jwt_secret_change_me`, mock LLM). These exist so `make dev` works with
  zero configuration. `deploy/docker-compose.prod.yml` refuses to start without
  real secrets — that is the boundary. Reports that local dev defaults are weak
  will be closed.
- Missing hardening on a deployment you configured — no TLS, `/metrics` exposed
  publicly, a database reachable from the internet. See
  [PRODUCTION_READINESS.md](docs/PRODUCTION_READINESS.md).
- Denial of service through resource exhaustion. Known and accepted for now;
  rate limits are per-process without Redis.
- Vulnerabilities in a third-party dependency with no exploitable path through
  this code. Report those upstream. If you can show a working path through this
  repository, that is in scope.
- Findings from an automated scanner with no demonstrated impact.
- Social engineering, physical access, or attacks on GitHub itself.

## Known and accepted

Stated so you do not spend time rediscovering them:

- **No security audit or penetration test has been performed.** This code has
  never run in production.
- Alert correlation is rules-based, not ML — deliberate, not a defect.
- Without Redis, login lockout and rate limiting are per-process, so a
  multi-replica deployment weakens both. See [SCALING.md](docs/SCALING.md).
- SOC 2 controls are *mapped and evidenced*, not *certified*. There is no audit
  report. See [COMPLIANCE.md](docs/COMPLIANCE.md).

## Design background

Before reporting, [THREAT_MODEL.md](docs/THREAT_MODEL.md) is worth a read — it
carries the STRIDE analysis, the trust boundaries, and the residual risks that
are already known and accepted. [COMMAND_POLICY.md](docs/COMMAND_POLICY.md)
documents the two-layer policy engine in depth, which is where several of the
in-scope categories above live.
