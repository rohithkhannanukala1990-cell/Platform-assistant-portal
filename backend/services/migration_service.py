"""SQL migration shadow validation and destructive guards."""

from __future__ import annotations

import asyncio
import os
import re
import time
from typing import Any


DESTRUCTIVE_PATTERNS = [
    re.compile(r"\bDROP\s+TABLE\b", re.I),
    re.compile(r"\bDROP\s+COLUMN\b", re.I),
    re.compile(r"\bTRUNCATE\b", re.I),
]


def is_destructive_sql(sql: str) -> bool:
    text = sql or ""
    for pat in DESTRUCTIVE_PATTERNS:
        if pat.search(text):
            return True
    for stmt in re.split(r";\s*", text):
        if re.search(r"\bDELETE\s+FROM\b", stmt, re.I) and not re.search(
            r"\bWHERE\b", stmt, re.I
        ):
            return True
    return False


def generate_rollback_sql(forward_sql: str) -> str:
    """Best-effort rollback companion for common DDL patterns."""
    sql = (forward_sql or "").strip()
    stmts = [s.strip() for s in re.split(r";\s*", sql) if s.strip()]
    rollbacks: list[str] = []
    ident = r"[`\"'\w.]+"
    for stmt in reversed(stmts):
        m = re.match(
            rf"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?({ident})",
            stmt,
            re.I,
        )
        if m:
            rollbacks.append(f"DROP TABLE IF EXISTS {m.group(1)}")
            continue
        m = re.match(
            rf"ALTER\s+TABLE\s+({ident})\s+ADD\s+(?:COLUMN\s+)?({ident})",
            stmt,
            re.I,
        )
        if m:
            rollbacks.append(f"ALTER TABLE {m.group(1)} DROP COLUMN {m.group(2)}")
            continue
        m = re.match(
            rf"ALTER\s+TABLE\s+({ident})\s+DROP\s+COLUMN\s+({ident})",
            stmt,
            re.I,
        )
        if m:
            rollbacks.append(
                f"-- MANUAL: restore column {m.group(2)} on {m.group(1)} from backup"
            )
            continue
        m = re.match(rf"DROP\s+TABLE\s+(?:IF\s+EXISTS\s+)?({ident})", stmt, re.I)
        if m:
            rollbacks.append(f"-- MANUAL: restore table {m.group(1)} from backup")
            continue
        m = re.match(
            rf"CREATE\s+(?:UNIQUE\s+)?INDEX\s+(?:IF\s+NOT\s+EXISTS\s+)?({ident})",
            stmt,
            re.I,
        )
        if m:
            rollbacks.append(f"DROP INDEX IF EXISTS {m.group(1)}")
            continue
        rollbacks.append(f"-- MANUAL rollback for: {stmt[:120]}")
    return ";\n".join(rollbacks) + (";" if rollbacks else "")


def _execute_sql(dsn: str, sql: str) -> dict[str, Any]:
    """Run SQL against a DSN using SQLAlchemy if available, else sqlite3/psycopg fallback."""
    started = time.perf_counter()
    affected = 0
    try:
        from sqlalchemy import create_engine, text

        eng = create_engine(dsn)
        with eng.begin() as conn:
            for stmt in [s.strip() for s in re.split(r";\s*", sql) if s.strip()]:
                result = conn.execute(text(stmt))
                try:
                    affected += int(result.rowcount or 0)
                except Exception:
                    pass
        duration_ms = int((time.perf_counter() - started) * 1000)
        return {
            "ok": True,
            "success": True,
            "error": None,
            "duration_ms": duration_ms,
            "affected_rows": affected,
        }
    except Exception as exc:
        duration_ms = int((time.perf_counter() - started) * 1000)
        return {
            "ok": False,
            "success": False,
            "error": str(exc)[:2000],
            "duration_ms": duration_ms,
            "affected_rows": affected,
        }


async def run_shadow_migration(forward_sql: str) -> dict[str, Any]:
    """Execute forward SQL against SHADOW_DATABASE_URL. Caller must check env first."""
    dsn = (os.getenv("SHADOW_DATABASE_URL") or "").strip()
    if not dsn:
        return {
            "ok": False,
            "success": False,
            "error": "SHADOW_DATABASE_URL is not set",
            "missing_shadow": True,
            "duration_ms": 0,
            "affected_rows": 0,
        }

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, lambda: _execute_sql(dsn, forward_sql))


async def execute_production_migration(forward_sql: str) -> dict[str, Any]:
    """Execute frozen forward SQL against production DSN."""
    dsn = (
        (os.getenv("PRODUCTION_DATABASE_URL") or "").strip()
        or (os.getenv("DATABASE_URL") or "").strip()
    )
    if not dsn:
        return {
            "ok": False,
            "error": "PRODUCTION_DATABASE_URL / DATABASE_URL is not set",
            "url": None,
        }
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, lambda: _execute_sql(dsn, forward_sql))
    return {
        "ok": bool(result.get("ok")),
        "error": result.get("error"),
        "affected_rows": result.get("affected_rows"),
        "duration_ms": result.get("duration_ms"),
        "url": None,
    }


def shadow_url_configured() -> bool:
    return bool((os.getenv("SHADOW_DATABASE_URL") or "").strip())
