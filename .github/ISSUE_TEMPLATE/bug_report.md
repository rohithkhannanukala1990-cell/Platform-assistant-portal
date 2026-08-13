---
name: Bug report
about: Something behaves differently from how it's documented or intended
title: ''
labels: bug
assignees: ''
---

<!-- SECURITY: if this is a vulnerability, do NOT file it here. Use private
     reporting instead — see SECURITY.md. A public issue discloses the bug to
     everyone the moment you file it. -->

## What happened

## What you expected

## How to reproduce

1.
2.
3.

## Which setup were you running?

<!-- These behave differently — the lean stack has no Postgres, Redis, Celery, or
     CLI tools, so a bug there may not reproduce on the full stack, and vice versa. -->

- [ ] `make dev` — lean stack (SQLite, mock LLM, no CLI tools)
- [ ] `make up` — full stack (Postgres, Redis, Celery, bundled CLI tools)
- [ ] No Docker — uvicorn + `npm run dev`
- [ ] Production compose (`deploy/docker-compose.prod.yml`)

## Environment

- Commit SHA:
- OS:
- Docker version (if relevant):
- Browser (if a UI bug):
- LLM mode: <!-- mock (default) or a real provider -->

## Which area?

- [ ] Agents / agent runs
- [ ] Approvals (inbox, Slack, or terminal)
- [ ] Workflows
- [ ] Command policy / terminal
- [ ] Code editor
- [ ] Catalog / scorecards / golden paths
- [ ] Connectors <!-- which one? -->
- [ ] Auth / RBAC / tenancy
- [ ] Setup or docs
- [ ] Something else

## Logs or output

<!-- The startup config summary line is useful — it appears in the first ~6 lines
     of backend output and reports database, redis, llm_mode, and connectors.
     Please redact anything sensitive; don't paste real tokens. -->

```
```

## Anything else

<!-- Does it happen every time or intermittently? Did it work before? If you
     know which commit changed the behaviour, that's very helpful. -->
