# Sprint 17 — Run D (ws_terminal verification)

**Date:** 2026-05-18  
**Scope:** Read `backend/ws_portal.py` in full; verify `@router.websocket("/ws/terminal")` exists and satisfies all five security/correctness requirements; fix anything missing.

## Verification result: NO CHANGES REQUIRED

The endpoint at line 210 already satisfies every requirement:

| Requirement | Location | Detail |
|---|---|---|
| `token` query param + `_authenticate_ws_token` | lines 213–223 | Rejects with `close(code=4001)`-equivalent before `accept()` |
| `BLOCKED_PATTERNS` list | lines 186–198 | Regex-based (catches whitespace variants; broader than literal strings) |
| `_is_blocked(command)` before execution | lines 265–273 | Called before any subprocess spawn |
| `asyncio.wait_for` with 300 s timeout | lines 237–239 | `timeout=300.0` idle cutoff |
| Output as `{"type":"output","data":"..."}` | throughout | All send_json calls use this shape |

## Why the existing implementation is stronger than the Run D snippet

- Uses `re.search` with `re.IGNORECASE` instead of `str.lower() in str.lower()` — catches variants like `rm  -rf /` (extra spaces).
- Runs an additional `CommandValidator` + `safe_executor` layer after the block-list check.
- Has a richer welcome banner (includes username).

## Conclusion

No edits to `ws_portal.py` were made. This file records the verification outcome for traceability.
