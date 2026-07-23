"""Infrastructure generator and CI/CD pipeline APIs."""

from __future__ import annotations

import asyncio
import json
import re

import ollama
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from ..ai.ai_utils import AI_PROVIDER, OLLAMA_MODEL, gemini_client
from ..auth import User, get_current_user
from ..database import (
    create_notification,
    get_all_cicd,
    get_all_infra,
    save_cicd,
    save_incident,
    save_infra,
)
from ..observability.logger import logger
from ..rate_limit import limiter
from ..services.demo_fixtures import (
    CICD_ACTIVE_RUNS,
    CICD_MONITOR_SCENARIOS,
    DORA_METRICS,
    demo_data_enabled,
)
from ..services.incidents_service import hitl_evaluate as _hitl_evaluate
from ..services.incidents_service import to_list as _to_list

router = APIRouter(tags=["infra-cicd"])

# ── Infra Builder ─────────────────────────────────────────────────────────────

PROVIDER_CONTEXT = {
    "AWS": {
        "full_name": "Amazon Web Services",
        "tf_provider": (
            'terraform {\n  required_providers {\n    aws = {\n      source  = "hashicorp/aws"\n'
            '      version = "~> 5.0"\n    }\n  }\n}\nprovider "aws" {\n  region = "us-east-1"\n}'
        ),
        "tf_resources": "aws_instance, aws_s3_bucket, aws_db_instance, aws_vpc, aws_subnet, aws_security_group, aws_iam_role",
        "cli_tool": "AWS CLI (aws)",
        "cli_examples": "aws ec2 run-instances, aws s3 mb, aws rds create-db-instance",
        "free_tier": "t2.micro/t3.micro EC2 (750 hrs/month), 5GB S3, 750hrs RDS db.t2.micro",
        "default_region": "us-east-1",
    },
    "GCP": {
        "full_name": "Google Cloud Platform",
        "tf_provider": (
            'terraform {\n  required_providers {\n    google = {\n      source  = "hashicorp/google"\n'
            '      version = "~> 5.0"\n    }\n  }\n}\nprovider "google" {\n  project = "my-project-id"\n'
            '  region  = "us-central1"\n}'
        ),
        "tf_resources": "google_compute_instance, google_storage_bucket, google_sql_database_instance, google_container_cluster, google_cloud_run_service",
        "cli_tool": "gcloud CLI",
        "cli_examples": "gcloud compute instances create, gcloud storage buckets create, gcloud sql instances create",
        "free_tier": "e2-micro in us-central1 (1 per month free), 5GB Cloud Storage, f1-micro Cloud SQL",
        "default_region": "us-central1",
    },
    "Azure": {
        "full_name": "Microsoft Azure",
        "tf_provider": (
            'terraform {\n  required_providers {\n    azurerm = {\n      source  = "hashicorp/azurerm"\n'
            '      version = "~> 3.0"\n    }\n  }\n}\nprovider "azurerm" {\n  features {}\n}'
        ),
        "tf_resources": "azurerm_virtual_machine, azurerm_storage_account, azurerm_sql_server, azurerm_resource_group, azurerm_virtual_network, azurerm_app_service",
        "cli_tool": "Azure CLI (az)",
        "cli_examples": "az vm create, az storage account create, az sql server create",
        "free_tier": "B1s VM (750 hrs/month free for 12 months), 5GB Blob Storage, Azure SQL 250GB",
        "default_region": "eastus",
    },
    "DigitalOcean": {
        "full_name": "DigitalOcean",
        "tf_provider": (
            'terraform {\n  required_providers {\n    digitalocean = {\n      source  = "digitalocean/digitalocean"\n'
            '      version = "~> 2.0"\n    }\n  }\n}\nprovider "digitalocean" {\n  token = var.do_token\n}'
        ),
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
            "cli_commands": _to_list(data.get("cli_commands", [])),
            "cost_estimate": str(data.get("cost_estimate", "")),
        }
    except (json.JSONDecodeError, ValueError):
        return {
            "resource_name": "Parse Error — Raw Output",
            "provider_used": provider,
            "terraform_code": text,
            "cli_commands": [],
            "cost_estimate": "Could not parse cost estimate.",
        }


@router.post("/api/infra/generate", response_model=InfraResponse)
@limiter.limit("5/minute")
async def generate_infra(
    request: Request,
    infra_in: InfraRequest,
    current_user: User = Depends(get_current_user),
):
    if not infra_in.prompt.strip():
        raise HTTPException(status_code=400, detail="Prompt cannot be empty.")

    provider = infra_in.provider.strip() or "GCP"
    system_prompt = build_infra_prompt(provider)
    user_msg = f"Infrastructure request: {infra_in.prompt}"

    try:
        if AI_PROVIDER == "ollama":
            response = ollama.chat(
                model=OLLAMA_MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_msg},
                ],
            )
            raw_text = response.message.content
            model_used = "Ollama / Gemma 3 4B (Local)"
        else:
            full_prompt = f"{system_prompt}\n\n{user_msg}"
            result = gemini_client.models.generate_content(model="gemma-3-27b-it", contents=full_prompt)
            raw_text = result.text
            model_used = "Gemma 3 27B (Cloud)"
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"AI provider error: {str(exc)}")

    parsed = parse_infra_response(raw_text, provider)

    save_infra(
        {
            **parsed,
            "prompt": infra_in.prompt,
            "model_used": model_used,
        }
    )

    return InfraResponse(
        resource_name=parsed["resource_name"],
        provider_used=parsed["provider_used"],
        terraform_code=parsed["terraform_code"],
        cli_commands=parsed["cli_commands"],
        cost_estimate=parsed["cost_estimate"],
        model_used=model_used,
    )


@router.get("/api/infra/history")
def list_infra(current_user: User = Depends(get_current_user)):
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
            "tool_name": str(data.get("tool_name", tool)),
            "yaml_code": str(data.get("yaml_code", text)),
            "explanation": str(data.get("explanation", "")),
            "security_checks": _to_list(data.get("security_checks", [])),
        }
    except (json.JSONDecodeError, ValueError):
        return {
            "tool_name": tool,
            "yaml_code": text,
            "explanation": "Could not parse structured explanation.",
            "security_checks": [],
        }


@router.post("/api/cicd/generate", response_model=CICDResponse)
@limiter.limit("5/minute")
async def generate_cicd(
    request: Request,
    cicd_in: CICDRequest,
    current_user: User = Depends(get_current_user),
):
    if not cicd_in.prompt.strip():
        raise HTTPException(status_code=400, detail="Prompt cannot be empty.")

    tool = cicd_in.cicd_tool.strip() or "GitHub Actions"
    ctx = CICD_TOOL_CONTEXT.get(tool, CICD_TOOL_CONTEXT["GitHub Actions"])

    system_prompt = CICD_SYSTEM_PROMPT_TEMPLATE.format(
        tool=tool,
        file=ctx["file"],
        format=ctx["format"],
        syntax_hints=ctx["syntax_hints"],
        stage_pattern=ctx["stage_pattern"],
        example_stages=ctx["example_stages"],
    )
    user_msg = f"Application description: {cicd_in.prompt}"

    try:
        if AI_PROVIDER == "ollama":
            response = ollama.chat(
                model=OLLAMA_MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_msg},
                ],
            )
            raw_text = response.message.content
            model_used = "Ollama / Gemma 3 4B (Local)"
        else:
            result = gemini_client.models.generate_content(
                model="gemma-3-27b-it",
                contents=f"{system_prompt}\n\n{user_msg}",
            )
            raw_text = result.text
            model_used = "Gemma 3 27B (Cloud)"
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"AI provider error: {str(exc)}")

    parsed = parse_cicd_response(raw_text, tool)

    save_cicd(
        {
            **parsed,
            "prompt": cicd_in.prompt,
            "model_used": model_used,
        }
    )

    return CICDResponse(
        tool_name=parsed["tool_name"],
        yaml_code=parsed["yaml_code"],
        explanation=parsed["explanation"],
        security_checks=parsed["security_checks"],
        model_used=model_used,
    )


@router.get("/api/cicd/history")
def list_cicd(current_user: User = Depends(get_current_user)):
    return get_all_cicd()


@router.get("/api/cicd/active-runs")
def get_cicd_active_runs(current_user: User = Depends(get_current_user)):
    """Return list of currently executing CI/CD pipeline runs."""
    if not demo_data_enabled():
        return {
            "status": "no_data",
            "runs": [],
            "message": "Connect a GitHub or GitLab CI account to populate active runs.",
        }
    return CICD_ACTIVE_RUNS


@router.get("/api/cicd/dora-metrics")
def get_dora_metrics(current_user: User = Depends(get_current_user)):
    """Return DORA metrics for the organisation."""
    if not demo_data_enabled():
        return {
            "status": "no_data",
            "message": "Connect CI/CD tools to compute real DORA metrics.",
            "deployment_frequency": None,
            "lead_time_for_changes": None,
            "change_failure_rate": None,
            "time_to_restore": None,
        }
    return DORA_METRICS


@router.post("/api/cicd/monitor", status_code=202)
@limiter.limit("5/minute")
async def trigger_cicd_monitor(request: Request, current_user: User = Depends(get_current_user)):
    """Dispatch the CI/CD monitor Celery task (or in-process fallback)."""
    from ..tasks import monitor_cicd_pipelines as _monitor_task

    try:
        task = _monitor_task.delay()
        return {"status": "accepted", "task_id": task.id, "message": "CI/CD monitor scan dispatched."}
    except Exception:
        asyncio.create_task(_cicd_monitor_fallback())
        return {
            "status": "accepted",
            "task_id": "local-fallback",
            "message": "CI/CD monitor scan running in-process.",
        }


async def _cicd_monitor_fallback():
    """In-process fallback for monitor when Redis/Celery is unavailable."""
    if not demo_data_enabled():
        logger.info("CI/CD monitor fallback skipped — demo data disabled")
        return
    import random as _rand

    await asyncio.sleep(2)
    scenario = _rand.choice(CICD_MONITOR_SCENARIOS)
    record = save_incident(
        {
            "summary": scenario["title"],
            "severity": scenario["severity"],
            "root_cause": (
                f"CI/CD monitor detected a failure in the {scenario['stage']} stage. "
                f"{scenario['summary']}"
            ),
            "action_plan": scenario["action_plan"],
            "commands": scenario["commands"],
            "evidence": [f"Pipeline stage: {scenario['stage']}", f"Service: {scenario['service']}"],
            "status": "OPEN",
            "source": "cicd-monitor",
            "owner_role": scenario["owner_role"],
        }
    )
    create_notification(
        message=f"🔴 CI/CD Monitor: {scenario['title']}",
        type="critical" if scenario["severity"] == "High" else "warning",
        incident_id=record.id,
    )
    parsed = {
        "summary": scenario["summary"],
        "action_plan": scenario["action_plan"],
        "commands": scenario["commands"],
    }
    asyncio.create_task(
        _hitl_evaluate(
            record.id,
            scenario["severity"],
            parsed,
            scenario["owner_role"],
            scenario.get("source", "cicd-monitor"),
        )
    )
