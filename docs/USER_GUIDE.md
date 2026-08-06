# How to use the AIOps Portal

You do **not** need every page.  
Pick what you’re trying to do → go there → ask AI for help only if you need it.

---

## The one rule

1. **Do the work on the page** (Catalog, Incidents, Scorecards…).  
2. **Ask an agent** when you want analysis, a plan, or a suggested fix.  
3. **Approve** anything that would change production.

Think of pages as your desk, and agents as specialists you call over when stuck.

---

## “I want to…” (start here)

| I want to… | Go to… | Then… |
|------------|--------|--------|
| See my service / who owns it | **Catalog** | Search the name → open the card |
| Create a new service the recommended way | **Golden Paths** | Pick a template → Launch |
| Check if my service is “healthy / ready” | **Scorecards** or **Standards** | Evaluate → fix the red items |
| Handle a page / outage | **Incidents** (or **Alert Triage**) | Open the incident → use Related agents |
| See if the platform itself is OK | **Health** | Check red/yellow cards |
| Approve something an agent wants to do | **Approvals** (or the bell icon) | Read the command → Approve or Deny |
| Fix a failed CI build | **Connectors → GitHub Actions** | Related agents → Pipeline |
| Review a pull request with AI | **Connectors → GitHub PRs** | Related agents → Code review |
| See deploy frequency / MTTR | **DORA Metrics** | Open the four score cards |
| See how much the AI costs us | **Reports → Token Utilization** | Check tokens, estimated $ and per-user usage |
| Try a data / deploy UI that isn’t live yet | **Deployments** or **Data Tools** | Look for the amber **Preview** badge — sample data only |
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
4. You’re set — explore from there.

**Admins (before the team relies on AI)**

1. **Tool Registry** — connect the tools you actually use (GitHub, PagerDuty, Kubernetes, AWS…).  
2. Create **workspaces** for teams.  
3. Leave **Environment** on Development while trying things; switch to Production only when ready.  
4. Quick check: Catalog → **Related agents** → Catalog health.  
   - Good: result says it used live data.  
   - Needs setup: it tells you a tool is missing — go back to Tool Registry.

---

## Agents explained (read this if you’re confused)

### What is an “agent”?

An **agent is not a separate product**.  
It is a **pre-built AI helper for one job**, with access to the right tools.

Examples:

- **Incident** agent → good at outages / PagerDuty  
- **Pipeline** agent → good at failed CI  
- **Cost** agent → good at AWS spend  
- **Scorecard** agent → good at service quality checks  

Same idea as calling a plumber vs an electrician.  
You don’t need to memorize every name.

### Agents vs AI Assistant vs chat bubble

| Thing | What it is | Use it when… |
|-------|------------|--------------|
| **Related agents** (chips on a page) | One-click “call the right helper for *this* screen” | You see chips like Incident / Pipeline — **prefer this** |
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
- Or tap one chip (e.g. “pipeline”) if you know the job.

### Tiny examples

**Outage**  
Incidents page → chip **Incident** → read the plan → approve only if it looks right.

**CI red**  
GitHub Actions → chip **Pipeline** → read why it failed → fix in GitHub.

**“How do we onboard here?”**  
AI Assistant → ask in chat (no specialist needed).

### Where should I click for AI help?

Use this order:

1. **Related agents chips** on the page you’re already on (best).  
2. **Agents** page if you want to type your own task.  
3. **AI Assistant** for open-ended chat.  
4. **Floating chat** for a one-line side question.

---

## What do those result badges mean?

After an agent runs you’ll see a small status about its data:

| Badge | Plain English |
|-------|----------------|
| **live** | Used real data from your tools |
| **partial** | Some real data, some gaps |
| **none** | Tool not connected — fix in Tool Registry |
| **demo** | Sample data (not your production systems) |

If you see **none**, connecting the tool will do more than re-asking the same question.

---

## When do I have to approve something?

If an agent wants to **change** production (restart pods, deploy, ack an incident, etc.), it will usually **wait for a human**.

You’ll notice it in:

- the **bell** (notifications) in the top bar  
- a badge on **Agents** in the sidebar  
- the **Approvals** page  

Only approve if you understand the action.  
If unsure → **Deny**, tighten the task, run again.

---

## Which pages matter for my role?

### I’m on-call / SRE
Home → **Dashboard** → **Alerts** → **Incidents** → **Health**.  
Also: **Runbooks**, **Approvals**.

### I build services (developer)
**Catalog** (your service) → **Scorecards** → **Connectors** (PRs / Actions).  
Also: **Golden Paths**, **AI Assistant**.

### I run the platform (DevOps / platform)
**Catalog** → **Scorecards** → **Standards** → **Golden Paths**.  
Also: **Deployments**, **CI/CD**, **Kubernetes**, **Tool Registry**.

### I’m an admin
**Admin Console** → **RBAC** → **Tool Registry** → **Workspaces** → **Settings**.

---

## Five common recipes

### Find my service
**Catalog** → search → open it → check owner and links.  
Optional: Related agents → **Catalog health**.

### Something is paging me
Open the **incident** → Related agents → **Incident** or **Runbook**.  
If it proposes a fix in production → **Approvals**.

### Raise my scorecard score
**Scorecards** → Evaluate → fix the failing checks → Evaluate again.  
Optional: Related agents → **Scorecard**.

### Spin up a new service the “right” way
**Golden Paths** → choose a path → Launch.  
When it finishes, the service shows up in **Catalog**.

### CI is red
**Connectors → GitHub Actions** → Related agents → **Pipeline**.  
Fix the failure before asking for a deploy.

---

## Workspaces (your team’s “desk”)

A **workspace** is a saved box for one team or purpose: name, members, tools/accounts, and a default environment.

Think: **“Payments team desk”** or **“Platform SRE desk”** — not a Kubernetes namespace, and not the same thing as Local/Dev/Prod.

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
3. Work normally — Catalog, agents, health, etc. now run in that workspace’s context.  
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

- One workspace per team or major product area (don’t make dozens of tiny ones).  
- Put the right **tool accounts** on the workspace so people don’t hunt credentials.  
- Developers mostly only **switch**; admins **create and maintain**.  
- If data looks empty or “wrong team,” check the workspace name in the top bar first.

---

## Environments (Local, Dev, Test, Staging, Prod, DR)

The top-bar **context** control (sliders icon) sets which **world** your actions target.

It is **not** “which computer you’re on.”  
It is “treat my next actions as if they apply to **this** stage of the system.”

### The ladder (safer → riskier)

| Environment | Plain English | Typical use | Agent changes need your OK? |
|-------------|---------------|-------------|-----------------------------|
| **Local** | Your laptop / personal sandbox | Trying things alone | Usually no |
| **Development** | Shared team sandbox | Day-to-day build & break | Usually no |
| **Test** | QA environment | Verification before release | Usually no |
| **Staging** | Dress rehearsal of prod | Final checks | Usually no (still be careful) |
| **Production** | Real users / live systems | Real ops only | **Yes — almost always** |
| **DR** | Disaster-recovery copy of prod | Failover / drills | **Yes — almost always** |

Switching to **Production** or **DR** shows a warning. That’s intentional.

### Three switches people mix up

| Control | Meaning |
|---------|---------|
| **Workspace** | *Who* — your team’s space in the portal |
| **Environment** | *Where* — local / dev / test / staging / prod / DR |
| **Tool account** | *Which credentials* — e.g. “prod AWS” vs “dev AWS” for GitHub/K8s/etc. |

Example: Workspace = **Payments team**, Environment = **Staging**, Account = **staging-aws**.  
Agents then talk to staging systems as that team — not production.

### What changes when you switch environment

1. Your choice is saved for your user session (and remembered in the browser).  
2. Agent runs carry that environment in their context.  
3. In **Production / DR**, mutating agents (deploy, heal, infra changes…) **pause for approval**.  
4. Tool accounts are often tagged by environment in **Tool Registry** — pick the matching account so you don’t hit prod creds while “on” staging.

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
| **Workspace** | Your team’s space inside the portal |
| **Environment** | Which stage you are targeting (local → prod) |
| **Catalog** | List of services and who owns them |
| **Scorecard** | Health / quality checklist for a service |
| **Golden Path** | Guided “do it the company way” template |
| **Connector** | Link to an external tool (GitHub, PagerDuty…) |
| **Agent** | An AI specialist for one job (incidents, cost, CI…) |
| **Approval** | Human OK required before a risky action runs |
| **Run History** | Log of what agents did, with evidence |
| **Token Utilization** | How many AI tokens (and estimated $) your org used |

---

## Appendix: specialist agents (names → jobs)

You usually don’t type these names — the Related agents chips pick them for you. Handy if you’re on the Agents page:

| When you need… | Pick this agent |
|----------------|-----------------|
| Triage an incident | Incident |
| Quiet noisy alerts | Alert noise |
| Suggest a safe restart / heal | Auto-heal |
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

For engineers extending agents, see [`AGENTS.md`](./AGENTS.md).  
For a pilot rollout plan, see [`PILOT_PLAYBOOK.md`](./PILOT_PLAYBOOK.md).
