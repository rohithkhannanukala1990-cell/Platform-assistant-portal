# How to use the AIOps Portal

You do **not** need every page.  
Pick what you're trying to do → go there → ask AI for help only if you need it.

---

## The one rule

1. **Do the work on the page** (Catalog, Incidents, Scorecards…).  
2. **Ask an agent** when you want analysis, a plan, or a suggested fix.  
3. **Approve** anything that would change production.

Think of pages as your desk, and agents as specialists you call over when stuck.

---

## "I want to…" (start here)

| I want to… | Go to… | Then… |
|------------|--------|--------|
| See my service / who owns it | **Catalog** | Search the name → open the card |
| Create a new service the recommended way | **Golden Paths** | Pick a template → Launch |
| Check if my service is "healthy / ready" | **Scorecards** or **Standards** | Evaluate → fix the red items |
| Handle a page / outage | **Incidents** (or **Alert Triage**) | Open the incident → use Related agents |
| See who's on call right now | **On-call** | Check the current rotation, or propose an override |
| See if the platform itself is OK | **Health** | Check red/yellow cards |
| Approve something an agent (or anyone) wants to do | **Approvals** | Read the item → Approve or Reject |
| Run real shell commands or ask an agent inline | **Terminal** | Type a command, or `@agent <task>` |
| Edit a file — local scratch or a real repo | **Code Editor** | Open/create a file → edit → save (or propose a PR) |
| Automate a multi-step process on a schedule | **Workflows** | Build a workflow → set a trigger → save |
| Request access to something you don't have | **Access** | Describe what you need → it routes to the owner |
| Fix a failed CI build | **Connectors → GitHub Actions** | Related agents → Pipeline |
| Review a pull request with AI | **Connectors → GitHub PRs** | Related agents → Code review |
| See deploy frequency / MTTR | **DORA Metrics** | Open the four score cards |
| See how much the AI costs us | **Reports → Token Utilization** | Check tokens, estimated $ and per-user usage |
| See live deploy / workflow runs | **Deployments** | Needs GitHub (and optionally Argo CD) in Tool Registry |
| Check where we stand on audit controls | **Compliance** | Review mapped controls, look for gaps |
| Connect GitHub / PagerDuty / AWS | **Tool Registry** (admin) | Add the account, then retry |
| Ask a free-form question | **AI Assistant** | Type the question in plain English |
| Run a named specialist myself | **Agents** | Pick agent(s) → write a clear task → Run |

Press **⌘K** (Mac) or **Ctrl+K** (Windows) anytime to search pages and jump there.

---

## First day on the portal

**Everyone**

1. Sign in.  
2. In the top bar, pick your **workspace** (your team).  
3. Open **Catalog** and find one service you know.  
4. You're set — explore from there.

**Admins (before the team relies on AI)**

1. **Tool Registry** — connect the tools you actually use (GitHub, PagerDuty, Kubernetes, AWS…).  
2. Create **workspaces** for teams.  
3. Leave **Environment** on Development while trying things; switch to Production only when ready.  
4. Quick check: Catalog → **Related agents** → Catalog health.  
   - Good: result says it used live data.  
   - Needs setup: it tells you a tool is missing — go back to Tool Registry.

---

## Agents explained (read this if you're confused)

### What is an "agent"?

An **agent is not a separate product**.  
It is a **pre-built AI helper for one job**, with access to the right tools.

Examples:

- **Incident** agent → good at outages / PagerDuty  
- **Pipeline** agent → good at failed CI  
- **Cost** agent → good at AWS spend  
- **Scorecard** agent → good at service quality checks  

Same idea as calling a plumber vs an electrician.  
You don't need to memorize every name.

### Agents vs AI Assistant vs chat bubble

| Thing | What it is | Use it when… |
|-------|------------|--------------|
| **Related agents** (chips on a page) | One-click "call the right helper for *this* screen" | You see chips like Incident / Pipeline — **prefer this** |
| **Agents** page | Form: write a task → pick helpers → Run | You want a serious, tracked run with evidence |
| **AI Assistant** | Normal chat | You have a general question, not a specific ops task |
| **Floating chat** | Tiny helper in the corner | A quick side question while you stay on the page |

**If you remember only one thing:**  
Most days, click a **Related agents** chip. Ignore the rest until you need it.

### What actually happens when you run an agent

1. You give it a **task** in plain English.  
2. It looks at **connected tools** (GitHub, K8s, PagerDuty…).  
3. It comes back with a **summary + evidence** (why it thinks that).  
4. If it wants to **change** production, it **stops and asks you to approve**.

You are still in control. Agents suggest; you decide.

### Do I have to pick an agent every time?

No.

- Click a **Related agents** chip → already picked for you.  
- On the Agents page you can leave agents empty → the portal routes the task.  
- Or tap one chip (e.g. "pipeline") if you know the job.

### Tiny examples

**Outage**  
Incidents page → chip **Incident** → read the plan → approve only if it looks right.

**CI red**  
GitHub Actions → chip **Pipeline** → read why it failed → fix in GitHub.

**"How do we onboard here?"**  
AI Assistant → ask in chat (no specialist needed).

### Where should I click for AI help?

Use this order:

1. **Related agents chips** on the page you're already on (best).  
2. **Agents** page if you want to type your own task.  
3. **AI Assistant** for open-ended chat.  
4. **Floating chat** for a one-line side question.

---

## What do those result badges mean?

After an agent runs you'll see a small status about its data:

| Badge | Plain English |
|-------|----------------|
| **live** | Used real data from your tools |
| **partial** | Some real data, some gaps |
| **none** | Tool not connected — fix in Tool Registry |
| **demo** | Sample data (not your production systems) |

If you see **none**, connecting the tool will do more than re-asking the same question.

---

## When do I have to approve something?

If an agent (or a workflow, or someone else on your team) wants to **change** production — restart pods, deploy, ack an incident, grant access — it usually **waits for a human**.

You'll notice it in:

- the **bell** (notifications) in the top bar  
- a badge on **Agents** in the sidebar  
- the **Approvals** page  

Only approve if you understand the action.  
If unsure → **Reject**, tighten the task, run again.

See the full **Approvals** section below for how the inbox actually works, including Slack.

---

## The Terminal

A real shell — commands you type actually run, the same as they would on your own machine, but every command passes through the platform's policy engine first. Something risky doesn't fail silently; it either runs, gets denied with a reason, or gets queued for approval.

**Which tools are available.** Type `help` at the prompt. It lists every CLI tool the deployment knows about, each one marked as available (with its version) or "not installed in this deployment." A lean local dev setup won't have kubectl/helm/terraform/aws-cli; a full deployment usually does.

**Line editing works normally.** Arrow keys move through command history, Tab completes, and the usual shortcuts work: **Ctrl+A** (start of line), **Ctrl+E** (end of line), **Ctrl+U** (clear the line). It behaves like a terminal you already know.

**The `@agent` syntax** invokes an AI agent inline, without leaving the shell:

```
@incident what's the current status of INC-482?
@security scan the payments-api repo for exposed secrets
@cost what did we spend on EC2 last month?
@deploy roll out the latest image to staging
@heal restart the crash-looping pod in checkout-ns
```

`@agents` lists everyone available; `@runs` shows your last 10 agent runs; `@help` shows the full `@` syntax reference.

**A command that needs approval doesn't dead-end.** If the policy engine flags something as `require_approval`, the terminal doesn't just fail — it waits inline. The command runs automatically the moment someone approves it from the Approvals page or Slack, and you'll see the output land in the same terminal session.

---

## The Code Editor

**Local files always work**, with autosave — no setup required. Create a scratch file, write in it, and it's saved as you type.

**Editing files from an actual repository needs a GitHub connection** (Settings → Tool Registry). Without one, you can still use the editor for local scratch work; you just won't see repo files in the file browser.

**Selecting text exposes agent actions** — highlight a block of code and a panel offers relevant agent actions:

| Action | What it does |
|---|---|
| Explain | Summarizes what the selected code does, in plain English |
| Review | Flags bugs, style issues, or risky patterns in the selection |
| Fix | Proposes a corrected version of the selection |

**Suggestions are never applied automatically.** Every agent suggestion comes back as an accept/reject diff — you see exactly what would change before anything is written to the file.

**Proposing a pull request** packages your changes and opens a PR against the connected repo, gated by the normal approval flow. If the file changed upstream since you opened it (someone else pushed to the same file), the proposal is blocked with an explicit message rather than silently overwriting their change — reload the file to pick up the latest version, or force the proposal through if you're sure.

---

## Workflows

A **workflow** is a saved sequence of steps that runs together, instead of you (or an agent) doing each one by hand every time.

**Concrete example:** every Monday at 9am, run the `cost_agent` to pull last week's AWS spend, then if spend increased more than 10%, post a summary to a Slack channel via the outbound webhook connector — no human needed to kick it off, and nothing destructive happens along the way.

### Building one

Open **Workflows** → **New**. Add steps one at a time — each step is one of three types:

- **Agent** — run a specialist agent with a given input.
- **Connector action** — call a connector method directly (post to Slack, create a Jira ticket, query Prometheus, and so on).
- **Condition** — branch based on the result of an earlier step.

Save it, pick a trigger, and it's ready.

### Trigger types

| Trigger | When it runs |
|---|---|
| **Manual** | Only when someone clicks "Run" |
| **Schedule** | On a cron expression you set (e.g. every Monday at 9am) |
| **Event** | When a matching platform event occurs |

### Safety rails

These apply regardless of who set the workflow up:

- **Forced first dry-run.** The very first time a schedule or event trigger would fire a workflow live, the platform forces that run to be a dry run instead — no real side effects — no matter what the workflow itself says. It only runs for real after an admin explicitly approves live execution.
- **Re-approval after editing steps.** Change the steps in a workflow that's already been approved for live runs, and that approval is cleared. It goes back to forced-dry-run until someone re-approves — so an edited workflow can't quietly start doing something different than what was reviewed.
- **Rate limits.** A workflow can only run so many times per hour (12 by default). Hit the limit and further triggers are rejected until the window resets.
- **Concurrency caps.** Only so many runs of the same workflow can be in flight at once (1 by default) — an over-limit run is either queued or dropped, depending on how the workflow is configured.
- **Kill switch.** An admin can suspend every automatic (schedule/event) trigger platform-wide with one flag, without touching any individual workflow's configuration — useful if something's misbehaving and you need everything to stop firing right now.

---

## Approvals

Every pending decision in the portal — an agent run that wants to change something, a workflow step, an access request, a change record — lands in **one inbox**: the Approvals page. You don't need to know which subsystem generated it; it's all in one list, sorted by how long it's been waiting.

**Keyboard shortcuts** (press `?` on the Approvals page to see this list any time):

| Key | Does |
|---|---|
| `j` / `k` | Move focus down / up the list |
| `a` | Approve the focused item |
| `r` | Reject the focused item |
| `Enter` | Expand or collapse the focused item |
| `?` | Toggle this shortcuts overlay |

**Slack approvals** carry the exact same permission checks as approving from the web UI — there's no separate, looser path through Slack. If you can approve it on the Approvals page, you can approve it from the Slack message.

**Two categories deliberately don't get a Slack button:**

- Anything requiring **typed confirmation** (destroying Terraform resources — you have to type the workspace name back).
- Anything requiring a **second approver** (destructive database migrations).

For these, Slack posts a link back to the portal instead of Approve/Reject buttons. That's intentional — these are the actions you can't undo, and a thumb shouldn't be able to hit the wrong button on a phone.

---

## Access requests

Need access to something — a GitHub team, a Kubernetes role, an AWS IAM role, an Okta group — that you don't currently have? Go to **Access**, describe what you need in plain language, and submit.

The request **routes to whoever actually owns that resource**, not a generic admin queue. If no owner is configured for that specific resource, it falls back to an admin and flags that the resource has no owner on record (worth fixing if you see this often).

Access granted through this flow is **time-bound** — it expires automatically after the duration set on the request, not "until someone remembers to revoke it." You'll get a warning about an hour before it expires, so you're not cut off mid-task without notice.

---

## Compliance

The **Compliance** page maps portal activity to six specific SOC 2 control areas: logical access controls, timely access removal, least privilege, system monitoring, change management, and incident response. For each one, you can pull the underlying evidence for a given period — who has access, which incidents got postmortems, which production changes had an approval record.

**Gap scanning is the most useful part.** Rather than just producing an evidence pack after the fact, it actively looks for holes — an admin without MFA, access that was never reviewed, a production change that happened without a matching change record. Finding these yourself, before an audit, beats an auditor finding them for you.

---

## Which pages matter for my role?

### I'm on-call / SRE
Home → **Dashboard** → **Alerts** → **Incidents** → **Health** → **On-call**.  
Also: **Runbooks**, **Approvals**, **Terminal**.

### I build services (developer)
**Catalog** (your service) → **Scorecards** → **Connectors** (PRs / Actions).  
Also: **Golden Paths**, **Code Editor**, **AI Assistant**.

### I run the platform (DevOps / platform)
**Catalog** → **Scorecards** → **Standards** → **Golden Paths**.  
Also: **Deployments**, **CI/CD**, **Kubernetes**, **Workflows**, **Tool Registry**.

### I'm an admin
**Admin Console** → **RBAC** → **Tool Registry** → **Workspaces** → **Settings**.  
Also: **Compliance**, **Access** (reviewing/routing requests).

---

## Common recipes

### Find my service
**Catalog** → search → open it → check owner and links.  
Optional: Related agents → **Catalog health**.

### Something is paging me
Open the **incident** → Related agents → **Incident** or **Runbook**.  
If it proposes a fix in production → **Approvals**.

### Raise my scorecard score
**Scorecards** → Evaluate → fix the failing checks → Evaluate again.  
Optional: Related agents → **Scorecard**.

### Spin up a new service the "right" way
**Golden Paths** → choose a path → Launch.  
When it finishes, the service shows up in **Catalog**.

### CI is red
**Connectors → GitHub Actions** → Related agents → **Pipeline**.  
Fix the failure before asking for a deploy.

### I need access to something
**Access** → describe what you need → submit.  
It routes to the resource owner; you'll get a time-bound grant once approved.

### I want a repeatable weekly check
**Workflows** → New → add the steps you'd otherwise do by hand → set a **Schedule** trigger.  
Its first live run is a forced dry-run — approve it once you've checked the output looks right.

---

## Workspaces (your team's "desk")

A **workspace** is a saved box for one team or purpose: name, members, tools/accounts, and a default environment.

Think: **"Payments team desk"** or **"Platform SRE desk"** — not a Kubernetes namespace, and not the same thing as Local/Dev/Prod.

### Workspace vs Environment vs Account

| Control | Question it answers | Example |
|---------|---------------------|---------|
| **Workspace** | *Whose* desk am I on? | Payments team |
| **Environment** | *Which stage* am I targeting? | Staging |
| **Tool account** | *Which credentials* for GitHub/AWS/K8s? | payments-staging-aws |

You usually set **workspace first**, then environment/account if needed.

### Everyday use (everyone)

1. Top bar → click the **workspace** button (folder / name).  
2. Pick a **Pinned** workspace, or one under **All**.  
3. Work normally — Catalog, agents, health, etc. now run in that workspace's context.  
4. **Clear Workspace** if you want to drop back to no active desk.

Your last choice is remembered in the browser for next login.

**Tip:** Pin the workspace you use every day so it stays at the top.

### What a workspace contains (admins / owners)

Open **Administration → Workspaces** (or **View All** / **New Workspace** from the switcher).

There you can:

- **Create** a workspace (name, icon, description, default environment)  
- **Add tools** — which connectors belong on this desk (GitHub, K8s, PagerDuty…)  
- **Attach accounts** — which credential each tool should use here  
- **Add members** — who can use this workspace (and their role)  
- **Settings** — workspace-level flags (HITL preferences, etc.)  
- Optionally start from a **template** (blueprint) instead of building from scratch  

### What changes when you switch workspace

1. The portal sends that workspace id with API calls (`X-Workspace-Id`).  
2. Agent runs and many pages use that workspace as context.  
3. If the workspace has a default environment different from your current one, the portal may **align environment** to match.  
4. In stricter deployments, APIs can **require** an active workspace before you do much else.

### Practical habits

- One workspace per team or major product area (don't make dozens of tiny ones).  
- Put the right **tool accounts** on the workspace so people don't hunt credentials.  
- Developers mostly only **switch**; admins **create and maintain**.  
- If data looks empty or "wrong team," check the workspace name in the top bar first.

---

## Environments (Local, Dev, Test, Staging, Prod, DR)

The top-bar **context** control (sliders icon) sets which **world** your actions target.

It is **not** "which computer you're on."  
It is "treat my next actions as if they apply to **this** stage of the system."

### The ladder (safer → riskier)

| Environment | Plain English | Typical use | Agent changes need your OK? |
|-------------|---------------|-------------|-----------------------------|
| **Local** | Your laptop / personal sandbox | Trying things alone | Usually no |
| **Development** | Shared team sandbox | Day-to-day build & break | Usually no |
| **Test** | QA environment | Verification before release | Usually no |
| **Staging** | Dress rehearsal of prod | Final checks | Usually no (still be careful) |
| **Production** | Real users / live systems | Real ops only | **Yes — almost always** |
| **DR** | Disaster-recovery copy of prod | Failover / drills | **Yes — almost always** |

Switching to **Production** or **DR** shows a warning. That's intentional.

### Three switches people mix up

| Control | Meaning |
|---------|---------|
| **Workspace** | *Who* — your team's space in the portal |
| **Environment** | *Where* — local / dev / test / staging / prod / DR |
| **Tool account** | *Which credentials* — e.g. "prod AWS" vs "dev AWS" for GitHub/K8s/etc. |

Example: Workspace = **Payments team**, Environment = **Staging**, Account = **staging-aws**.  
Agents then talk to staging systems as that team — not production.

### What changes when you switch environment

1. Your choice is saved for your user session (and remembered in the browser).  
2. Agent runs carry that environment in their context.  
3. In **Production / DR**, mutating agents (deploy, heal, infra changes…) **pause for approval**.  
4. Tool accounts are often tagged by environment in **Tool Registry** — pick the matching account so you don't hit prod creds while "on" staging.

### Practical habits

- Learn the portal in **Development** or **Local**.  
- Use **Staging** before anything scary.  
- Switch to **Production** only when you mean it — then read Approvals carefully.  
- If results look wrong, check all three: workspace + environment + tool account.

---

## Token utilization & AI cost (Reports)

Every AI call in the portal — chat, floating chat, and agent runs — records how many **tokens** it used and an **estimated cost in USD**, tagged with the user who triggered it.

Where to look:

- **Reports → Token Utilization** — org-wide totals for the last 30 days:
  - total tokens, estimated cost, number of API calls, active users
  - breakdown **by user** (who is using the AI most)
  - breakdown **by provider / model** (where the money goes)
  - **monthly token budget** bars per configured provider
- **Settings → LLM providers** (admin) — each provider shows a usage bar against its monthly token budget; set the budget when adding or editing a provider.

Good to know:

- Cost is an **estimate** based on public list prices per model — use it for trends and accountability, not invoicing.
- Budget bars turn **amber at 70%** and **red at 90%** of the monthly limit.
- Usage is scoped to your organization (tenant), so you only see your own org's numbers.

---

## Quick glossary

| Word in the UI | What it means |
|----------------|----------------|
| **Workspace** | Your team's space inside the portal |
| **Environment** | Which stage you are targeting (local → prod) |
| **Catalog** | List of services and who owns them |
| **Scorecard** | Health / quality checklist for a service |
| **Golden Path** | Guided "do it the company way" template |
| **Connector** | Link to an external tool (GitHub, PagerDuty…) |
| **Agent** | An AI specialist for one job (incidents, cost, CI…) |
| **Approval** | Human OK required before a risky action runs |
| **Approval inbox** | The single Approvals page where every pending decision lands, regardless of source |
| **Workflow** | A saved multi-step sequence that can run on a schedule, an event, or on demand |
| **Access request** | A plain-language ask for access, routed to the resource owner and granted time-bound |
| **Run History** | Log of what agents did, with evidence |
| **Token Utilization** | How many AI tokens (and estimated $) your org used |

---

## Appendix: specialist agents (names → jobs)

You usually don't type these names — the Related agents chips pick them for you. Handy if you're on the Agents page:

| When you need… | Pick this agent |
|----------------|-----------------|
| Triage an incident | Incident |
| Quiet noisy alerts | Alert noise |
| Suggest a safe restart / heal | Auto-heal |
| Check on-call coverage or propose an override | On-call |
| Look at Kubernetes / infra | Infra |
| Plan a deploy | Deploy |
| Explain a CI failure | Pipeline |
| Review a PR | Code review |
| Help with failing tests | Tester |
| Catalog completeness | Catalog health |
| Scorecard deep-dive | Scorecard |
| Outdated dependencies | Deps drift |
| Matching runbook | Runbook |
| New-hire / new-service plan | Onboarding |
| Improve docs | Docs |
| Cloud spend | Cost |
| Security misconfigurations | Security |
| Migration plan | Migration |
| Request or review access to a resource | Access |
| Draft, submit, or close a change request | Change |
| Collect SOC 2 evidence or scan for gaps | Compliance |

For engineers extending agents, see [`AGENTS.md`](./AGENTS.md).  
For a structured pilot evaluation plan, see [`PILOT_PLAYBOOK.md`](./PILOT_PLAYBOOK.md).
