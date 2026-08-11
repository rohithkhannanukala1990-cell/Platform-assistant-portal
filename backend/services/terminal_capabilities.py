"""Probe which CLI binaries the terminal advertises are actually present in
this deployment's image, so the terminal never advertises a tool it can't run.

Computed once (cached) — call ``refresh_capabilities()`` at process startup;
``get_capabilities()`` returns the cached result everywhere else (the WS help
text, ``GET /api/terminal/capabilities``, and ``safe_executor``'s pre-flight
check all read from the same cache).
"""

from __future__ import annotations

import re
import shutil
import subprocess
from typing import Any

from .terminal_service import KNOWN_BINARIES

_VERSION_ARGS: dict[str, list[str]] = {
    "kubectl": ["kubectl", "version", "--client"],
    "helm": ["helm", "version", "--short"],
    "terraform": ["terraform", "version"],
    "git": ["git", "--version"],
    "aws": ["aws", "--version"],
    "npm": ["npm", "--version"],
    "pip": ["pip", "--version"],
}

_VERSION_RE = re.compile(r"\d+\.\d+\.\d+")
_PROBE_TIMEOUT_SECONDS = 5

_cache: dict[str, dict[str, Any]] | None = None


def _probe_one(tool: str) -> dict[str, Any]:
    path = shutil.which(tool)
    if not path:
        return {"tool": tool, "available": False, "version": None}

    version = None
    args = _VERSION_ARGS.get(tool, [tool, "--version"])
    try:
        result = subprocess.run(
            args, capture_output=True, text=True, timeout=_PROBE_TIMEOUT_SECONDS
        )
        blob = f"{result.stdout}\n{result.stderr}"
        match = _VERSION_RE.search(blob)
        if match:
            version = match.group(0)
    except Exception:
        pass  # binary is present but the version probe failed — still "available"

    return {"tool": tool, "available": True, "version": version}


def refresh_capabilities() -> dict[str, dict[str, Any]]:
    """Re-probe every advertised binary and replace the cache. Call at startup."""
    global _cache
    _cache = {tool: _probe_one(tool) for tool in KNOWN_BINARIES}
    return _cache


def get_capabilities() -> dict[str, dict[str, Any]]:
    """Return the cached capability map, probing once on first call if needed."""
    if _cache is None:
        return refresh_capabilities()
    return _cache


def is_available(tool: str) -> bool:
    caps = get_capabilities()
    entry = caps.get(tool)
    if entry is not None:
        return bool(entry["available"])
    # Not one of the advertised binaries — fall back to a live check rather
    # than silently assuming it's missing.
    return shutil.which(tool) is not None
