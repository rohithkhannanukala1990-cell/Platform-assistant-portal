"""
AI Safety Guardrail — CommandValidator
=======================================
Scans AI-generated remediation plans and raw command lists for destructive
or dangerous patterns before the agent is allowed to queue them for execution.

If any blocklisted term is matched, the caller is expected to:
  1. Change the incident status to "ESCALATED_SECURITY_RISK"
  2. Clear proposed_remediation_plan
  3. Create a security notification
"""

from __future__ import annotations
import re

# ── Blocklist definition ──────────────────────────────────────────────────────

# Each entry is a plain-text fragment (case-insensitive) or a regex pattern.
# Group them by category for clear violation messages.

_BLOCKLIST: list[tuple[str, str]] = [
    # ── Filesystem destruction ────────────────────────────────────────────────
    (r"rm\s+-[a-z]*r[a-z]*f",      "Recursive force file deletion (rm -rf)"),
    (r"rm\s+-[a-z]*f[a-z]*r",      "Recursive force file deletion (rm -fr)"),
    (r"mkfs",                       "Filesystem format command (mkfs)"),
    (r"dd\s+if=",                   "Raw disk write via dd"),
    (r"shred\s+",                   "Secure file deletion (shred)"),
    (r"wipefs",                     "Partition signature wipe (wipefs)"),
    (r":(){:|:&};:",                "Fork bomb pattern"),
    (r">\s*/dev/sd",                "Direct disk write via redirection"),

    # ── Permission escalation ─────────────────────────────────────────────────
    (r"chmod\s+777",                "World-writable permission grant (chmod 777)"),
    (r"chmod\s+-R\s+777",           "Recursive world-writable (chmod -R 777)"),
    (r"chown\s+-R\s+.*\s+/",        "Recursive ownership change on root"),
    (r"sudo\s+su\b",                "Root shell escalation (sudo su)"),
    (r"sudo\s+-i\b",                "Interactive root shell (sudo -i)"),

    # ── Destructive SQL ───────────────────────────────────────────────────────
    (r"\bDROP\s+TABLE\b",           "SQL DROP TABLE"),
    (r"\bDROP\s+DATABASE\b",        "SQL DROP DATABASE"),
    (r"\bDROP\s+SCHEMA\b",          "SQL DROP SCHEMA"),
    (r"\bTRUNCATE\b",               "SQL TRUNCATE"),
    (r"\bDELETE\s+FROM\b(?![\s\S]*?\bWHERE\b)", "Unfiltered SQL DELETE (no WHERE clause)"),
    (r"\bDROP\s+INDEX\b",           "SQL DROP INDEX"),
    (r"\bALTER\s+TABLE.*DROP\s+COLUMN\b", "SQL DROP COLUMN"),

    # ── Network / firewall nukes ──────────────────────────────────────────────
    (r"iptables\s+-F",              "Flush all firewall rules (iptables -F)"),
    (r"ufw\s+disable",              "Disable firewall (ufw disable)"),
    (r"iptables\s+--flush",         "Flush all firewall rules"),

    # ── Credential / secret exfiltration ──────────────────────────────────────
    (r"curl.*\|\s*bash",            "Remote code execution via curl | bash"),
    (r"wget.*\|\s*bash",            "Remote code execution via wget | bash"),
    (r"curl.*\|\s*sh\b",            "Remote code execution via curl | sh"),
    (r"base64\s+--decode.*\|\s*(bash|sh|python)", "Encoded payload execution"),
    (r"cat\s+/etc/shadow",          "Read shadow password file"),
    (r"cat\s+/etc/passwd",          "Read passwd file"),
    (r"cat\s+~/.ssh",               "Read SSH keys"),

    # ── Container / cluster nukes ─────────────────────────────────────────────
    (r"kubectl\s+delete\s+namespace",  "Delete Kubernetes namespace"),
    (r"kubectl\s+delete\s+--all",      "Delete all Kubernetes resources"),
    (r"docker\s+system\s+prune\s+-a",  "Prune all Docker images/containers"),
    (r"docker\s+rm\s+-f",              "Force remove running containers"),

    # ── Cloud-nuke patterns ────────────────────────────────────────────────────
    (r"aws\s+s3\s+rm\s+.*--recursive", "Recursive S3 delete"),
    (r"gcloud.*delete.*--quiet",       "Silent GCP resource delete"),
    (r"az\s+group\s+delete",           "Azure resource group delete"),
]

# Compile all patterns once at import time for performance
_COMPILED: list[tuple[re.Pattern, str]] = [
    (re.compile(pattern, re.IGNORECASE | re.MULTILINE), reason)
    for pattern, reason in _BLOCKLIST
]


# ── Public API ────────────────────────────────────────────────────────────────

class ValidationResult:
    __slots__ = ("safe", "violations")

    def __init__(self, safe: bool, violations: list[str]):
        self.safe       = safe
        self.violations = violations

    def __bool__(self):
        return self.safe

    def __repr__(self):
        return f"ValidationResult(safe={self.safe}, violations={self.violations!r})"


class CommandValidator:
    """
    Validates AI-generated command lists and remediation plan steps against
    a blocklist of dangerous patterns.

    Usage:
        result = CommandValidator.validate(plan_steps)
        if not result.safe:
            # escalate
    """

    @staticmethod
    def validate(items: list[str]) -> ValidationResult:
        """
        Scan every string in *items* against the blocklist.

        Returns a ValidationResult:
          .safe       → True if nothing dangerous was found
          .violations → list of human-readable violation descriptions
        """
        violations: list[str] = []
        combined_text = "\n".join(items)

        for pattern, reason in _COMPILED:
            if pattern.search(combined_text):
                violations.append(reason)

        return ValidationResult(safe=len(violations) == 0, violations=violations)

    @staticmethod
    def validate_text(text: str) -> ValidationResult:
        """Single-string variant — useful for validating a raw log or command string."""
        return CommandValidator.validate([text])
