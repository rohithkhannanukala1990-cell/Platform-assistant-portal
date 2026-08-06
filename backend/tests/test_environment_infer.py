"""Tests for discovery environment inference."""

from backend.importers.environment_infer import (
    apply_environment_to_account,
    infer_environment,
    normalize_environment,
    requires_hitl_for_env,
)
from backend.importers.cloud_discovery import cloud_discovery
from backend.importers.service_discovery import service_discovery
import pytest


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("prod", "production"),
        ("PRODUCTION", "production"),
        ("stg", "staging"),
        ("qa", "test"),
        ("dev", "development"),
        ("sandbox", "local"),
        ("dr", "dr"),
        ("", "development"),
    ],
)
def test_normalize_environment(raw, expected):
    assert normalize_environment(raw) == expected


@pytest.mark.parametrize(
    "hint,expected",
    [
        ("acme-prod-aws", "production"),
        ("payments-staging", "staging"),
        ("my-org-dev", "development"),
        ("qa-cluster", "test"),
        ("dr-failover", "dr"),
        ("local-sandbox", "local"),
        ("K8s cluster / staging", "staging"),
        ("namespace production", "production"),
        ("random-account", "development"),
    ],
)
def test_infer_from_name(hint, expected):
    env, source, _conf = infer_environment(hint)
    assert env == expected
    if expected == "development" and "random" in hint:
        assert source == "default"
    else:
        assert source in {"inferred", "explicit", "default"}


def test_explicit_override_wins():
    env, source, conf = infer_environment("acme-prod", explicit="test")
    assert env == "test"
    assert source == "explicit"
    assert conf == "high"


def test_requires_hitl():
    assert requires_hitl_for_env("production") is True
    assert requires_hitl_for_env("dr") is True
    assert requires_hitl_for_env("staging") is False
    assert requires_hitl_for_env("development") is False


@pytest.mark.asyncio
async def test_cloud_aws_infers_from_alias():
    out = await cloud_discovery.discover_aws(
        {
            "account_id": "111",
            "account_alias": "acme-staging",
            "regions": ["us-east-1"],
        }
    )
    assert out["accounts"][0]["environment"] == "staging"
    assert out["accounts"][0]["requires_hitl"] is False
    assert out["accounts"][0]["environment_source"] == "inferred"


@pytest.mark.asyncio
async def test_cloud_aws_batch_environment_override():
    out = await cloud_discovery.discover_aws(
        {
            "account_alias": "acme-prod",
            "environment": "development",
            "regions": ["us-east-1"],
        }
    )
    assert out["accounts"][0]["environment"] == "development"
    assert out["accounts"][0]["environment_source"] == "explicit"


@pytest.mark.asyncio
async def test_cloud_gcp_infers_from_project():
    out = await cloud_discovery.discover_gcp({"project_id": "shop-prod-123"})
    assert out["accounts"][0]["environment"] == "production"
    assert out["accounts"][0]["requires_hitl"] is True


@pytest.mark.asyncio
async def test_k8s_namespaces_get_distinct_envs():
    out = await service_discovery.discover_from_kubernetes(
        {"account_identifier": "cluster-1", "environment": "development"}
    )
    by_ns = {
        (a.get("metadata") or {}).get("namespace"): a["environment"]
        for a in out["discovered"]
    }
    assert by_ns["production"] == "production"
    assert by_ns["staging"] == "staging"
    assert by_ns["dev"] == "development"
    assert by_ns["test"] == "test"


def test_apply_environment_to_account_metadata():
    row = apply_environment_to_account(
        {"account_name": "Datadog", "tool_id": "datadog"},
        "acme-prod",
    )
    assert row["environment"] == "production"
    assert row["environment_source"] == "inferred"
    assert "environment_confidence" in row
