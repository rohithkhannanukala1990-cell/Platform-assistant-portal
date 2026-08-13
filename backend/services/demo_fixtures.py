"""Demo / fixture data gated by ENABLE_DEMO_DATA and environment."""

from __future__ import annotations

import os

from ..context import PlatformContext


def demo_data_enabled() -> bool:
    flag = (os.getenv("ENABLE_DEMO_DATA") or "").strip().lower()
    if flag in {"1", "true", "yes", "on"}:
        return True
    if flag in {"0", "false", "no", "off"}:
        return False
    return PlatformContext.is_dev_environment()


ANOMALY_INCIDENT = {
    "severity": "Warning",
    "summary": "Predictive Anomaly: Gradual Memory Leak in auth-service",
    "root_cause": (
        "auth-service memory usage is increasing by ~5% every hour despite flat request traffic. "
        "A slow object-reference leak in the session cache layer is the most likely cause."
    ),
    "evidence": [
        "auth-service RSS: 210 MB → 315 MB over 6 hours (flat traffic)",
        "GC pause frequency up 3× in the last 2 hours",
        "No corresponding spike in active sessions or request rate",
        "Heap dump shows accumulation in SessionCacheManager.activeTokens map",
    ],
    "action_plan": [
        "1. Capture a heap dump immediately: kill -s SIGUSR1 <pid>",
        "2. Increase JVM -XX:MaxHeapSize as a short-term buffer",
        "3. Rolling restart of auth-service pods to clear current leak",
        "4. Pin SessionCacheManager.activeTokens with a TTL eviction policy",
        "5. Deploy fix and monitor for 2 hours before declaring stable",
    ],
    "commands": [
        "kubectl top pods -n auth --sort-by=memory",
        "kubectl exec -it auth-service-<pod> -- kill -s SIGUSR1 1",
        "kubectl rollout restart deployment/auth-service -n auth",
        "kubectl logs -f deployment/auth-service -n auth | grep -i 'cache\\|leak\\|OOM'",
    ],
    "files_to_check": [
        "src/auth/cache/SessionCacheManager.java",
        "k8s/auth-service/deployment.yaml  (resource limits)",
        "config/auth/cache-config.properties",
    ],
    "validation_steps": [
        "Memory growth should plateau within 15 min of rolling restart",
        "GC pause frequency should return to baseline (<5 pauses/min)",
        "Re-run heap dump after 1 hour; activeTokens map should be stable",
    ],
    "raw_logs": "[anomaly-scanner] Predictive analysis triggered by background log scan.",
    "model_used": "Anomaly Scanner v1.0 (rule-based)",
    "raw_response": "",
    "source": "anomaly-scanner",
}


CICD_ACTIVE_RUNS = [
    {
        "id": "run-a1b2",
        "repository": "platform/auth-service",
        "branch": "main",
        "trigger_user": "alex.chen",
        "trigger_event": "push",
        "commit": "a3f91bc",
        "commit_message": "fix: token refresh race condition",
        "stages": ["Build", "Test", "Security Scan", "Deploy"],
        "current_stage": "Test",
        "status": "running",
        "elapsed_time": "3m 12s",
        "stage_statuses": {
            "Build": "success",
            "Test": "running",
            "Security Scan": "pending",
            "Deploy": "pending",
        },
    },
    {
        "id": "run-c3d4",
        "repository": "platform/api-gateway",
        "branch": "feature/rate-limiting",
        "trigger_user": "priya.m",
        "trigger_event": "pull_request",
        "commit": "d7e22fa",
        "commit_message": "feat: per-endpoint rate limiting",
        "stages": ["Build", "Test", "Security Scan", "Deploy"],
        "current_stage": "Security Scan",
        "status": "running",
        "elapsed_time": "8m 44s",
        "stage_statuses": {
            "Build": "success",
            "Test": "success",
            "Security Scan": "running",
            "Deploy": "pending",
        },
    },
    {
        "id": "run-e5f6",
        "repository": "platform/data-ingestion",
        "branch": "feature/v2-refactor",
        "trigger_user": "james.t",
        "trigger_event": "push",
        "commit": "c14a3b2",
        "commit_message": "refactor: switch to async queue",
        "stages": ["Build", "Test", "Security Scan", "Deploy"],
        "current_stage": "Test",
        "status": "failed",
        "elapsed_time": "5m 01s",
        "stage_statuses": {
            "Build": "success",
            "Test": "failed",
            "Security Scan": "pending",
            "Deploy": "pending",
        },
    },
    {
        "id": "run-g7h8",
        "repository": "platform/frontend-web",
        "branch": "release/2026-q2",
        "trigger_user": "ci-bot",
        "trigger_event": "schedule",
        "commit": "f80d91e",
        "commit_message": "chore: bump dependency versions",
        "stages": ["Build", "Test", "Security Scan", "Deploy"],
        "current_stage": "Deploy",
        "status": "running",
        "elapsed_time": "11m 22s",
        "stage_statuses": {
            "Build": "success",
            "Test": "success",
            "Security Scan": "success",
            "Deploy": "running",
        },
    },
    {
        "id": "run-i9j0",
        "repository": "platform/ml-inference",
        "branch": "main",
        "trigger_user": "ana.v",
        "trigger_event": "push",
        "commit": "b55aec1",
        "commit_message": "perf: model quantisation",
        "stages": ["Build", "Test", "Security Scan", "Deploy"],
        "current_stage": "Deploy",
        "status": "success",
        "elapsed_time": "14m 05s",
        "stage_statuses": {
            "Build": "success",
            "Test": "success",
            "Security Scan": "success",
            "Deploy": "success",
        },
    },
]


DORA_METRICS = {
    "deployment_frequency": {
        "value": "14 per day",
        "level": "Elite",
        "trend": "+2 vs last week",
        "trend_dir": "up",
    },
    "lead_time": {
        "value": "45 mins",
        "level": "Elite",
        "trend": "-8 min vs last week",
        "trend_dir": "down_good",
    },
    "change_failure_rate": {
        "value": "2.4%",
        "level": "Elite",
        "trend": "-0.3% vs last week",
        "trend_dir": "down_good",
    },
    "mttr": {
        "value": "12 mins",
        "level": "Elite",
        "trend": "-4 min vs last week",
        "trend_dir": "down_good",
    },
}


# Stage → owner role for HITL routing
CICD_STAGE_ROLES: dict[str, str] = {
    "Build": "Developer",
    "Lint": "Developer",
    "Test": "Developer",
    "Unit Test": "Developer",
    "Security Scan": "NetworkEngineer",
    "SAST": "NetworkEngineer",
    "Deploy": "Developer",
    "Release": "Developer",
}


CICD_MONITOR_SCENARIOS = [
    {
        "stage": "Security Scan",
        "service": "api-gateway",
        "severity": "High",
        "title": "CI/CD Alert: Security Scan failed — CVE detected in api-gateway",
        "summary": (
            "CVE-2026-4127 (CVSS 8.9) detected in api-gateway:log4j-core:2.17.0 during "
            "Security Scan stage. Immediate patching required."
        ),
        "action_plan": [
            "Update log4j-core to >= 2.23.1",
            "Re-run SAST scan to confirm remediation",
            "Merge security patch to release branch",
        ],
        "commands": [
            "mvn versions:set-property -Dproperty=log4j.version -DnewVersion=2.23.1",
            "mvn dependency-check:check",
        ],
        "owner_role": "NetworkEngineer",
    },
    {
        "stage": "Test",
        "service": "auth-service",
        "severity": "Medium",
        "title": "CI/CD Alert: Flaky tests detected — auth-service integration suite",
        "summary": (
            "3 of 47 integration tests failed intermittently in auth-service CI. "
            "Tests: TokenRefreshTest, SessionExpiry, ConcurrentLoginTest."
        ),
        "action_plan": [
            "Isolate flaky tests and run in --retry mode",
            "Add test retries for async timing issues",
            "Pin external mock server version",
        ],
        "commands": [
            "pytest tests/integration -k 'TokenRefresh or SessionExpiry' --reruns 3",
            "git blame tests/integration/test_auth.py",
        ],
        "owner_role": "Developer",
    },
    {
        "stage": "Deploy",
        "service": "data-ingestion",
        "severity": "High",
        "title": "CI/CD Alert: Deployment rollback required — data-ingestion v3.1.0",
        "summary": (
            "data-ingestion v3.1.0 deployment to production failed health check after 3 minutes. "
            "P99 latency jumped from 120ms to 4.2s. Automatic rollback triggered."
        ),
        "action_plan": [
            "Rollback to v3.0.9 via ArgoCD",
            "Investigate latency regression in async queue implementation",
            "Run load test against staging before re-deploying",
        ],
        "commands": [
            "argocd app rollback data-ingestion",
            "kubectl rollout history deployment/data-ingestion -n production",
        ],
        "owner_role": "Developer",
    },
]
