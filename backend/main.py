import os
import re
import json
import ollama
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from google import genai
from database import (
    create_db_and_tables,
    save_incident, get_all_incidents,
    save_infra,    get_all_infra,
    save_cicd,     get_all_cicd,
    get_settings,  update_settings,
    create_notification, get_all_notifications, mark_notification_read,
)

load_dotenv()

# ── Provider config ──────────────────────────────────────────────────────────
AI_PROVIDER  = os.getenv("AI_PROVIDER", "gemini").lower()
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "gemma3:4b")

gemini_client = None
if AI_PROVIDER == "gemini":
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY is not set. Please add it to backend/.env")
    gemini_client = genai.Client(api_key=GEMINI_API_KEY)

app = FastAPI(title="AIOps Portal API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:5174",
        "http://localhost:5175",
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup():
    create_db_and_tables()


# ── System prompt ────────────────────────────────────────────────────────────
SYSTEM_PROMPT = """You are a senior DevOps and SRE engineer embedded inside Cursor IDE.
Analyze the provided server logs and return ONLY a valid JSON object — no markdown, no explanation, no code fences.

The JSON must have exactly these keys:

{
  "severity": "<Critical | High | Medium | Low>",
  "summary": "<One sentence describing what is broken and the immediate impact.>",
  "root_cause": "<2-4 sentences. State the failing component, the technical reason it failed, and blast radius. Reference specific error codes or service names from the logs. Do not restate the logs — explain WHY.>",
  "evidence": [
    "<Specific log line or pattern that proves the root cause>",
    "<Another supporting log entry>"
  ],
  "action_plan": [
    "Immediate: <One action to stop active damage right now with the exact command or config change.>",
    "Fix: <The permanent code, config, or infra change — specify the file and what to change.>",
    "Harden: <One monitoring or alerting improvement to prevent recurrence.>"
  ],
  "commands": [
    "<exact shell command 1>",
    "<exact shell command 2>"
  ],
  "files_to_check": [
    "<file path or k8s resource> (<reason>)",
    "<file path or k8s resource> (<reason>)"
  ],
  "validation_steps": [
    "<Exact command or log pattern to confirm the fix worked>",
    "<Metric or threshold to verify system health>"
  ]
}

Rules:
- Use real inferred values from the logs. Do not use placeholder strings like <namespace> or <your-service>.
- The commands array must contain runnable shell/kubectl/psql/docker commands only — no prose.
- Return ONLY the JSON object. Nothing before or after it."""


# ── Pydantic models ──────────────────────────────────────────────────────────
class TriageRequest(BaseModel):
    logs: str


class TriageResponse(BaseModel):
    id: int
    timestamp: str
    severity: str
    summary: str
    root_cause: str
    evidence: list[str]
    action_plan: list[str]
    commands: list[str]
    files_to_check: list[str]
    validation_steps: list[str]
    raw: str
    model_used: str


class IncidentSummary(BaseModel):
    id: int
    timestamp: str
    severity: str
    summary: str
    root_cause: str
    evidence: list[str]
    action_plan: list[str]
    commands: list[str]
    files_to_check: list[str]
    validation_steps: list[str]
    model_used: str
    source: str = "manual"
    raw_logs: str = ""


# ── JSON parser with fallback ────────────────────────────────────────────────
def parse_json_response(text: str) -> dict:
    cleaned = re.sub(r"^```(?:json)?\s*", "", text.strip(), flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned.strip())
    json_match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if json_match:
        cleaned = json_match.group(0)
    try:
        data = json.loads(cleaned)
        return {
            "severity":         str(data.get("severity", "Unknown")).capitalize(),
            "summary":          str(data.get("summary", "")),
            "root_cause":       str(data.get("root_cause", "")),
            "evidence":         _to_list(data.get("evidence", [])),
            "action_plan":      _to_list(data.get("action_plan", [])),
            "commands":         _to_list(data.get("commands", [])),
            "files_to_check":   _to_list(data.get("files_to_check", [])),
            "validation_steps": _to_list(data.get("validation_steps", [])),
        }
    except (json.JSONDecodeError, ValueError):
        return {
            "severity":         "Unknown",
            "summary":          "Model returned an unstructured response. See raw output.",
            "root_cause":       text[:800],
            "evidence":         [],
            "action_plan":      [],
            "commands":         [],
            "files_to_check":   [],
            "validation_steps": [],
        }


def _to_list(value) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


# ── AI provider calls ────────────────────────────────────────────────────────
async def call_ollama(logs: str, system_prompt: str = SYSTEM_PROMPT) -> str:
    response = ollama.chat(
        model=OLLAMA_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": logs},
        ],
    )
    return response.message.content


async def call_gemini(logs: str, system_prompt: str = SYSTEM_PROMPT) -> str:
    prompt = f"{system_prompt}\n\nLogs to analyze:\n{logs}"
    result = gemini_client.models.generate_content(
        model="gemma-3-27b-it",
        contents=prompt,
    )
    return result.text


# ── Shared triage core ────────────────────────────────────────────────────────

async def _run_triage(log_text: str, source: str = "manual") -> dict:
    """
    Call AI → parse → save incident → notification → Slack.
    Returns the serialised TriageResponse dict (or raises on AI error).
    """
    if AI_PROVIDER == "ollama":
        raw_text  = await call_ollama(log_text)
        model_used = "Ollama / Gemma 3 4B (Local)"
    else:
        raw_text  = await call_gemini(log_text)
        model_used = "Gemma 3 27B (Cloud)"

    parsed = parse_json_response(raw_text)

    record = save_incident({
        **parsed,
        "raw_logs":     log_text,
        "model_used":   model_used,
        "raw_response": raw_text,
        "source":       source,
    })

    severity   = parsed["severity"]
    notif_type = "critical" if severity == "Critical" else \
                 "warning"  if severity in ("High", "Medium") else "info"
    notif_msg  = f"[{severity}] {parsed['summary']}"
    if source != "manual":
        notif_msg += f"  •  via webhook: {source.removeprefix('webhook:')}"
    create_notification(message=notif_msg, type=notif_type, incident_id=record.id)

    if severity in ("Critical", "High"):
        settings = get_settings()
        webhook  = settings.get("slack_webhook_url", "").strip()
        if webhook:
            await _send_slack_alert(webhook, severity, parsed["summary"], parsed["root_cause"])

    return {
        "id":              record.id,
        "timestamp":       record.timestamp.isoformat(),
        "severity":        parsed["severity"],
        "summary":         parsed["summary"],
        "root_cause":      parsed["root_cause"],
        "evidence":        parsed["evidence"],
        "action_plan":     parsed["action_plan"],
        "commands":        parsed["commands"],
        "files_to_check":  parsed["files_to_check"],
        "validation_steps":parsed["validation_steps"],
        "raw":             raw_text,
        "model_used":      model_used,
    }


# ── Routes ───────────────────────────────────────────────────────────────────

@app.post("/api/triage", response_model=TriageResponse)
async def triage_logs(request: TriageRequest):
    if not request.logs.strip():
        raise HTTPException(status_code=400, detail="Log text cannot be empty.")
    try:
        result = await _run_triage(request.logs, source="manual")
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"AI provider error: {str(exc)}")
    return TriageResponse(**result)


@app.get("/api/incidents", response_model=list[IncidentSummary])
def list_incidents():
    return get_all_incidents()


# ── Webhook Ingestion ──────────────────────────────────────────────────────────

class WebhookLogRequest(BaseModel):
    source:    str
    log_text:  str
    timestamp: str | None = None


async def _webhook_background(log_text: str, source: str):
    """Background task: run triage silently, log any errors."""
    try:
        await _run_triage(log_text, source=f"webhook:{source}")
    except Exception as exc:
        print(f"[webhook] Background triage failed for source={source}: {exc}")


@app.post("/api/webhooks/logs", status_code=202)
async def ingest_webhook_log(request: WebhookLogRequest, background_tasks: BackgroundTasks):
    """Accept a log payload, return 202 immediately, triage in the background."""
    if not request.log_text.strip():
        raise HTTPException(status_code=400, detail="log_text cannot be empty.")
    if not request.source.strip():
        raise HTTPException(status_code=400, detail="source cannot be empty.")

    background_tasks.add_task(_webhook_background, request.log_text, request.source.strip())

    return {
        "status":  "accepted",
        "message": f"Log from '{request.source}' queued for triage.",
    }


# ── Slack helper ──────────────────────────────────────────────────────────────

async def _send_slack_alert(webhook: str, severity: str, summary: str, root_cause: str):
    """Fire-and-forget Slack webhook; logs errors but never raises."""
    color = "#FF0000" if severity == "Critical" else "#FFA500"
    payload = {
        "attachments": [{
            "color": color,
            "blocks": [
                {"type": "header", "text": {"type": "plain_text", "text": f"🚨 {severity} Alert — AIOps Portal"}},
                {"type": "section", "fields": [
                    {"type": "mrkdwn", "text": f"*Summary:*\n{summary}"},
                    {"type": "mrkdwn", "text": f"*Root Cause:*\n{root_cause}"},
                ]},
                {"type": "context", "elements": [
                    {"type": "mrkdwn", "text": "Sent by *Platform Engineering Assistant*"}
                ]},
            ],
        }]
    }
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            r = await client.post(webhook, json=payload)
            r.raise_for_status()
    except Exception as exc:
        print(f"[Slack] Failed to send alert: {exc}")


# ── Notifications ──────────────────────────────────────────────────────────────

@app.get("/api/notifications")
def fetch_notifications():
    return get_all_notifications()


@app.put("/api/notifications/{notification_id}/read")
def read_notification(notification_id: int):
    result = mark_notification_read(notification_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Notification not found")
    return result


# ── Jira Integration ───────────────────────────────────────────────────────────

JIRA_FORMAT_PROMPT = """You are a senior SRE writing a Jira incident ticket.
Given the incident data below, return ONLY a JSON object with these fields:
- "title": concise one-line issue summary (max 100 chars)
- "description": detailed markdown description (2-4 sentences, plain text)
- "steps_to_reproduce": list of strings describing how to reproduce / verify the issue
- "priority": one of "Highest", "High", "Medium", "Low"

Return ONLY raw JSON. No markdown fences.
"""

def _to_adf(text: str) -> dict:
    """Wrap plain text in Atlassian Document Format paragraph."""
    return {
        "version": 1,
        "type": "doc",
        "content": [{
            "type": "paragraph",
            "content": [{"type": "text", "text": text}],
        }],
    }


@app.post("/api/incidents/{incident_id}/jira")
async def create_jira_ticket(incident_id: int):
    # Load incident
    all_incidents = get_all_incidents()
    incident = next((i for i in all_incidents if i["id"] == incident_id), None)
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")

    # Load Jira settings
    settings = get_settings()
    domain    = settings.get("jira_domain", "").strip()
    email     = settings.get("jira_email", "").strip()
    token     = settings.get("jira_api_token", "").strip()
    proj_key  = settings.get("jira_project_key", "").strip()

    if not all([domain, email, token, proj_key]):
        raise HTTPException(status_code=400, detail="Jira credentials are incomplete. Configure them in Settings.")

    # Ask AI to format the ticket
    incident_summary_text = (
        f"Severity: {incident['severity']}\n"
        f"Summary: {incident['summary']}\n"
        f"Root Cause: {incident['root_cause']}\n"
        f"Action Plan: {'; '.join(incident.get('action_plan', []))}\n"
        f"Commands: {'; '.join(incident.get('commands', []))}"
    )
    prompt = JIRA_FORMAT_PROMPT + "\n\nIncident:\n" + incident_summary_text

    try:
        if AI_PROVIDER == "ollama":
            raw = await call_ollama(incident_summary_text, system_prompt=JIRA_FORMAT_PROMPT)
        else:
            raw = await call_gemini(incident_summary_text, system_prompt=JIRA_FORMAT_PROMPT)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"AI provider error: {str(exc)}")

    # Parse AI response
    try:
        cleaned = re.sub(r"^```(?:json)?\s*", "", raw.strip(), flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned.strip())
        m = re.search(r"\{.*\}", cleaned, re.DOTALL)
        jira_data = json.loads(m.group(0)) if m else {}
    except Exception:
        jira_data = {}

    title      = jira_data.get("title", incident["summary"])[:100]
    description = jira_data.get("description", incident["root_cause"])
    steps       = jira_data.get("steps_to_reproduce", [])
    priority    = jira_data.get("priority", "High")

    # Build description ADF with steps
    steps_text = "\n".join(f"{i+1}. {s}" for i, s in enumerate(steps)) if steps else ""
    full_desc   = f"{description}\n\nSteps to Reproduce:\n{steps_text}" if steps_text else description
    adf_body    = _to_adf(full_desc)

    # Call Jira API
    import base64
    creds = base64.b64encode(f"{email}:{token}".encode()).decode()
    headers = {
        "Authorization": f"Basic {creds}",
        "Content-Type":  "application/json",
        "Accept":        "application/json",
    }
    payload = {
        "fields": {
            "project":     {"key": proj_key},
            "summary":     title,
            "description": adf_body,
            "issuetype":   {"name": "Bug"},
            "priority":    {"name": priority},
        }
    }
    jira_url = f"https://{domain}/rest/api/3/issue"
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(jira_url, headers=headers, json=payload)
            resp.raise_for_status()
            result = resp.json()
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=502, detail=f"Jira API error {exc.response.status_code}: {exc.response.text}")
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Jira connection error: {str(exc)}")

    ticket_key = result.get("key", "UNKNOWN")
    ticket_url = f"https://{domain}/browse/{ticket_key}"

    create_notification(
        message=f"Jira ticket {ticket_key} created for Incident #{incident_id}",
        type="info",
        incident_id=incident_id,
    )

    return {"ticket_key": ticket_key, "ticket_url": ticket_url}


# ── Infra Builder ─────────────────────────────────────────────────────────────

PROVIDER_CONTEXT = {
    "AWS": {
        "full_name": "Amazon Web Services",
        "tf_provider": 'terraform {\n  required_providers {\n    aws = {\n      source  = "hashicorp/aws"\n      version = "~> 5.0"\n    }\n  }\n}\nprovider "aws" {\n  region = "us-east-1"\n}',
        "tf_resources": "aws_instance, aws_s3_bucket, aws_db_instance, aws_vpc, aws_subnet, aws_security_group, aws_iam_role",
        "cli_tool": "AWS CLI (aws)",
        "cli_examples": "aws ec2 run-instances, aws s3 mb, aws rds create-db-instance",
        "free_tier": "t2.micro/t3.micro EC2 (750 hrs/month), 5GB S3, 750hrs RDS db.t2.micro",
        "default_region": "us-east-1",
    },
    "GCP": {
        "full_name": "Google Cloud Platform",
        "tf_provider": 'terraform {\n  required_providers {\n    google = {\n      source  = "hashicorp/google"\n      version = "~> 5.0"\n    }\n  }\n}\nprovider "google" {\n  project = "my-project-id"\n  region  = "us-central1"\n}',
        "tf_resources": "google_compute_instance, google_storage_bucket, google_sql_database_instance, google_container_cluster, google_cloud_run_service",
        "cli_tool": "gcloud CLI",
        "cli_examples": "gcloud compute instances create, gcloud storage buckets create, gcloud sql instances create",
        "free_tier": "e2-micro in us-central1 (1 per month free), 5GB Cloud Storage, f1-micro Cloud SQL",
        "default_region": "us-central1",
    },
    "Azure": {
        "full_name": "Microsoft Azure",
        "tf_provider": 'terraform {\n  required_providers {\n    azurerm = {\n      source  = "hashicorp/azurerm"\n      version = "~> 3.0"\n    }\n  }\n}\nprovider "azurerm" {\n  features {}\n}',
        "tf_resources": "azurerm_virtual_machine, azurerm_storage_account, azurerm_sql_server, azurerm_resource_group, azurerm_virtual_network, azurerm_app_service",
        "cli_tool": "Azure CLI (az)",
        "cli_examples": "az vm create, az storage account create, az sql server create",
        "free_tier": "B1s VM (750 hrs/month free for 12 months), 5GB Blob Storage, Azure SQL 250GB",
        "default_region": "eastus",
    },
    "DigitalOcean": {
        "full_name": "DigitalOcean",
        "tf_provider": 'terraform {\n  required_providers {\n    digitalocean = {\n      source  = "digitalocean/digitalocean"\n      version = "~> 2.0"\n    }\n  }\n}\nprovider "digitalocean" {\n  token = var.do_token\n}',
        "tf_resources": "digitalocean_droplet, digitalocean_spaces_bucket, digitalocean_database_cluster, digitalocean_vpc, digitalocean_firewall, digitalocean_app",
        "cli_tool": "doctl CLI",
        "cli_examples": "doctl compute droplet create, doctl spaces create, doctl databases create",
        "free_tier": "No permanent free tier — cheapest Droplet is $4/month (512MB RAM). $200 credit for new accounts.",
        "default_region": "nyc3",
    },
}

INFRA_SYSTEM_PROMPT_TEMPLATE = """You are a Senior Multi-Cloud Architect with deep expertise in {full_name} infrastructure.
The user will describe the infrastructure they need. Generate production-ready Terraform and CLI commands SPECIFICALLY for {full_name}.
Return ONLY a valid JSON object — no markdown, no explanation, no code fences.

The JSON must have exactly these keys:

{{
  "resource_name": "<short descriptive name, e.g. '{provider} Free-Tier Web Server'>",
  "provider_used": "{provider}",
  "terraform_code": "<complete runnable HCL. Start with the provider block then resource blocks. Use these resource types: {tf_resources}. Use free-tier eligible sizes wherever possible. Escape all quotes inside the string.>",
  "cli_commands": [
    "<exact {cli_tool} command 1>",
    "<exact {cli_tool} command 2>",
    "<exact {cli_tool} command 3>"
  ],
  "cost_estimate": "<Free tier: {free_tier}. State the exact monthly cost for anything outside free tier. Be concise and practical.>"
}}

Rules:
- terraform_code must start with the provider block: {tf_provider_hint}
- Use the default region {default_region} unless the user specifies otherwise.
- cli_commands must use the {cli_tool} — example patterns: {cli_examples}
- All commands must be exact and copy-pasteable with no placeholder syntax like <your-value>.
- Return ONLY the JSON object. Nothing before or after it."""


class InfraRequest(BaseModel):
    prompt: str
    provider: str = "GCP"


class InfraResponse(BaseModel):
    resource_name: str
    provider_used: str
    terraform_code: str
    cli_commands: list[str]
    cost_estimate: str
    model_used: str


def build_infra_prompt(provider: str) -> str:
    ctx = PROVIDER_CONTEXT.get(provider.strip(), PROVIDER_CONTEXT["GCP"])
    return INFRA_SYSTEM_PROMPT_TEMPLATE.format(
        full_name=ctx["full_name"],
        provider=provider,
        tf_resources=ctx["tf_resources"],
        cli_tool=ctx["cli_tool"],
        cli_examples=ctx["cli_examples"],
        free_tier=ctx["free_tier"],
        default_region=ctx["default_region"],
        tf_provider_hint=ctx["tf_provider"].split("\n")[0],
    )


def parse_infra_response(text: str, provider: str) -> dict:
    cleaned = re.sub(r"^```(?:json)?\s*", "", text.strip(), flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned.strip())
    json_match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if json_match:
        cleaned = json_match.group(0)
    try:
        data = json.loads(cleaned)
        return {
            "resource_name": str(data.get("resource_name", "Unnamed Resource")),
            "provider_used": str(data.get("provider_used", provider)),
            "terraform_code": str(data.get("terraform_code", "")),
            "cli_commands":  _to_list(data.get("cli_commands", [])),
            "cost_estimate": str(data.get("cost_estimate", "")),
        }
    except (json.JSONDecodeError, ValueError):
        return {
            "resource_name": "Parse Error — Raw Output",
            "provider_used": provider,
            "terraform_code": text,
            "cli_commands":  [],
            "cost_estimate": "Could not parse cost estimate.",
        }


@app.post("/api/infra/generate", response_model=InfraResponse)
async def generate_infra(request: InfraRequest):
    if not request.prompt.strip():
        raise HTTPException(status_code=400, detail="Prompt cannot be empty.")

    provider      = request.provider.strip() or "GCP"
    system_prompt = build_infra_prompt(provider)
    user_msg      = f"Infrastructure request: {request.prompt}"

    try:
        if AI_PROVIDER == "ollama":
            response = ollama.chat(
                model=OLLAMA_MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user",   "content": user_msg},
                ],
            )
            raw_text   = response.message.content
            model_used = "Ollama / Gemma 3 4B (Local)"
        else:
            full_prompt = f"{system_prompt}\n\n{user_msg}"
            result      = gemini_client.models.generate_content(model="gemma-3-27b-it", contents=full_prompt)
            raw_text    = result.text
            model_used  = "Gemma 3 27B (Cloud)"
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"AI provider error: {str(exc)}")

    parsed = parse_infra_response(raw_text, provider)

    save_infra({
        **parsed,
        "prompt":     request.prompt,
        "model_used": model_used,
    })

    return InfraResponse(
        resource_name=parsed["resource_name"],
        provider_used=parsed["provider_used"],
        terraform_code=parsed["terraform_code"],
        cli_commands=parsed["cli_commands"],
        cost_estimate=parsed["cost_estimate"],
        model_used=model_used,
    )


@app.get("/api/infra/history")
def list_infra():
    return get_all_infra()


# ── CI/CD Pipeline Generator ─────────────────────────────────────────────────

CICD_TOOL_CONTEXT = {
    "GitHub Actions": {
        "file": ".github/workflows/main.yml",
        "format": "YAML",
        "syntax_hints": "Uses 'on', 'jobs', 'steps', 'uses', 'run' keywords. Jobs run on 'ubuntu-latest' by default. Secrets via ${{ secrets.NAME }}.",
        "stage_pattern": "jobs > build/test/deploy each with 'steps'",
        "example_stages": "checkout, setup language, install deps, run tests, build artifact, deploy",
    },
    "GitLab CI": {
        "file": ".gitlab-ci.yml",
        "format": "YAML",
        "syntax_hints": "Uses 'stages', 'image', 'script', 'only', 'artifacts', 'cache' keywords. Variables via $VARIABLE_NAME.",
        "stage_pattern": "stages list at top, then job blocks referencing each stage",
        "example_stages": "build, test, lint, security-scan, deploy",
    },
    "Jenkins": {
        "file": "Jenkinsfile",
        "format": "Groovy (Declarative Pipeline)",
        "syntax_hints": "Uses 'pipeline', 'agent', 'stages', 'stage', 'steps', 'sh', 'environment', 'post' blocks. Secrets via credentials().",
        "stage_pattern": "pipeline > stages > stage('Name') { steps { sh '...' } }",
        "example_stages": "Checkout, Build, Test, Code Analysis, Docker Build, Deploy",
    },
}

CICD_SYSTEM_PROMPT_TEMPLATE = """You are a Senior Release Engineer and DevOps expert specializing in CI/CD pipelines.
The user will describe their application and deployment target. Generate a production-ready {tool} pipeline.
Return ONLY a valid JSON object — no markdown, no explanation, no code fences.

Pipeline file: {file}
Format: {format}
Syntax guide: {syntax_hints}
Stage pattern: {stage_pattern}
Recommended stages: {example_stages}

The JSON must have exactly these keys:

{{
  "tool_name": "{tool}",
  "yaml_code": "<The complete {format} pipeline as a single string. Use \\n for newlines. Include all stages: install, lint, test, build, and deploy. Add comments explaining non-obvious steps. Make it production-ready, not a skeleton.>",
  "explanation": "<3-5 sentences explaining what each stage does, why the order matters, and any environment variables or secrets the user needs to configure.>",
  "security_checks": [
    "<Security or quality step 1 — e.g. dependency vulnerability scan>",
    "<Security or quality step 2 — e.g. SAST/static analysis>",
    "<Security or quality step 3 — e.g. Docker image scanning or secret detection>"
  ]
}}

Rules:
- yaml_code must be the FULL pipeline — never truncate or use placeholder comments like '# add more steps here'.
- Include at minimum: dependency install, unit tests, lint, build/package, deploy stages.
- Use environment variables and secrets correctly for {tool}.
- security_checks must be 3 specific items referencing tools or commands in the pipeline.
- Return ONLY the JSON object. Nothing before or after it."""


class CICDRequest(BaseModel):
    prompt: str
    cicd_tool: str = "GitHub Actions"


class CICDResponse(BaseModel):
    tool_name: str
    yaml_code: str
    explanation: str
    security_checks: list[str]
    model_used: str


def parse_cicd_response(text: str, tool: str) -> dict:
    cleaned = re.sub(r"^```(?:json)?\s*", "", text.strip(), flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned.strip())
    json_match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if json_match:
        cleaned = json_match.group(0)
    try:
        data = json.loads(cleaned)
        return {
            "tool_name":       str(data.get("tool_name", tool)),
            "yaml_code":       str(data.get("yaml_code", text)),
            "explanation":     str(data.get("explanation", "")),
            "security_checks": _to_list(data.get("security_checks", [])),
        }
    except (json.JSONDecodeError, ValueError):
        return {
            "tool_name":       tool,
            "yaml_code":       text,
            "explanation":     "Could not parse structured explanation.",
            "security_checks": [],
        }


@app.post("/api/cicd/generate", response_model=CICDResponse)
async def generate_cicd(request: CICDRequest):
    if not request.prompt.strip():
        raise HTTPException(status_code=400, detail="Prompt cannot be empty.")

    tool = request.cicd_tool.strip() or "GitHub Actions"
    ctx  = CICD_TOOL_CONTEXT.get(tool, CICD_TOOL_CONTEXT["GitHub Actions"])

    system_prompt = CICD_SYSTEM_PROMPT_TEMPLATE.format(
        tool=tool,
        file=ctx["file"],
        format=ctx["format"],
        syntax_hints=ctx["syntax_hints"],
        stage_pattern=ctx["stage_pattern"],
        example_stages=ctx["example_stages"],
    )
    user_msg = f"Application description: {request.prompt}"

    try:
        if AI_PROVIDER == "ollama":
            response   = ollama.chat(
                model=OLLAMA_MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user",   "content": user_msg},
                ],
            )
            raw_text   = response.message.content
            model_used = "Ollama / Gemma 3 4B (Local)"
        else:
            result     = gemini_client.models.generate_content(
                model="gemma-3-27b-it",
                contents=f"{system_prompt}\n\n{user_msg}",
            )
            raw_text   = result.text
            model_used = "Gemma 3 27B (Cloud)"
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"AI provider error: {str(exc)}")

    parsed = parse_cicd_response(raw_text, tool)

    save_cicd({
        **parsed,
        "prompt":     request.prompt,
        "model_used": model_used,
    })

    return CICDResponse(
        tool_name=parsed["tool_name"],
        yaml_code=parsed["yaml_code"],
        explanation=parsed["explanation"],
        security_checks=parsed["security_checks"],
        model_used=model_used,
    )


@app.get("/api/cicd/history")
def list_cicd():
    return get_all_cicd()


@app.get("/api/settings")
def fetch_settings():
    return get_settings()


@app.post("/api/settings")
def save_settings(body: dict):
    return update_settings(body)


@app.get("/api/analytics")
def get_analytics():
    from collections import Counter
    from datetime import datetime, timezone, timedelta

    incidents  = get_all_incidents()
    infra_list = get_all_infra()
    cicd_list  = get_all_cicd()
    notifs     = get_all_notifications()

    # ── Basic counts ──────────────────────────────────────────────────────────
    total_incidents   = len(incidents)
    critical_alerts   = sum(1 for i in incidents if i["severity"] == "Critical")
    unread_notifs     = sum(1 for n in notifs if not n["is_read"])

    # ── Incidents by severity ─────────────────────────────────────────────────
    severity_order = ["Critical", "High", "Medium", "Low", "Unknown"]
    sev_counter    = Counter(i["severity"] for i in incidents)
    incidents_by_severity = [
        {"name": s, "value": sev_counter.get(s, 0)}
        for s in severity_order if sev_counter.get(s, 0) > 0
    ]

    # ── Top sources ───────────────────────────────────────────────────────────
    src_counter = Counter(
        (i.get("source") or "manual").replace("webhook:", "") for i in incidents
    )
    top_sources = [
        {"name": src, "value": cnt}
        for src, cnt in src_counter.most_common(8)
    ]

    # ── Incidents over last 7 days ────────────────────────────────────────────
    now  = datetime.now(timezone.utc)
    days = [(now - timedelta(days=i)).strftime("%b %d") for i in range(6, -1, -1)]
    day_counter: dict[str, int] = {d: 0 for d in days}
    for inc in incidents:
        try:
            ts  = datetime.fromisoformat(inc["timestamp"])
            key = ts.strftime("%b %d")
            if key in day_counter:
                day_counter[key] += 1
        except Exception:
            pass
    incidents_over_time = [{"date": d, "count": day_counter[d]} for d in days]

    # ── Module activity ───────────────────────────────────────────────────────
    module_activity = [
        {"name": "Alerts",    "value": total_incidents},
        {"name": "Infra",     "value": len(infra_list)},
        {"name": "CI/CD",     "value": len(cicd_list)},
    ]

    # ── MTTR proxy (avg minutes between consecutive incidents) ────────────────
    mttr_display = "N/A"
    if len(incidents) >= 2:
        try:
            sorted_ts = sorted(
                datetime.fromisoformat(i["timestamp"]) for i in incidents
            )
            gaps = [(sorted_ts[j+1] - sorted_ts[j]).total_seconds() / 60
                    for j in range(len(sorted_ts) - 1)]
            avg_gap = sum(gaps) / len(gaps)
            if avg_gap < 60:
                mttr_display = f"{int(avg_gap)}m"
            else:
                mttr_display = f"{avg_gap / 60:.1f}h"
        except Exception:
            pass

    return {
        "total_incidents":      total_incidents,
        "critical_alerts":      critical_alerts,
        "unread_notifications": unread_notifs,
        "total_infra":          len(infra_list),
        "total_cicd":           len(cicd_list),
        "mttr":                 mttr_display,
        "incidents_by_severity":incidents_by_severity,
        "top_sources":          top_sources,
        "incidents_over_time":  incidents_over_time,
        "module_activity":      module_activity,
    }


@app.get("/health")
def health():
    return {"status": "ok", "provider": AI_PROVIDER, "model": OLLAMA_MODEL}
