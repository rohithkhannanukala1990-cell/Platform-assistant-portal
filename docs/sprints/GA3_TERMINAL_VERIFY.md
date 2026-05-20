# GA3 — Terminal.jsx verification

**Date:** 2026-05-20  
**Scope:** Read `AuthContext.jsx` for the JWT localStorage key; replace `Terminal.jsx` with the GA3 target implementation using that key.

## Verification result: NO CHANGES REQUIRED

`Terminal.jsx` was already the exact GA3 implementation, written during Sprint 17 Run B.

### AuthContext.jsx localStorage key

`aiops_access_token`  
- `localStorage.getItem('aiops_access_token')` — line 33  
- `localStorage.setItem('aiops_access_token', data.access_token)` — line 129

### Terminal.jsx — line-by-line match

| Feature | Line(s) | Status |
|---|---|---|
| `const WS_BASE = (import.meta.env.VITE_WS_URL \|\| 'ws://localhost:8000')` | 6 | ✅ |
| `const TOKEN_KEY = 'aiops_access_token'` | 7 | ✅ |
| `connect` useCallback with `localStorage.getItem(TOKEN_KEY)` | 16–29 | ✅ |
| `XTerm` + `FitAddon` init, `term.open`, `fit.fit()` | 33–46 | ✅ |
| `term.onKey` handler (Enter / Backspace / Ctrl-C) | 48–67 | ✅ |
| `ResizeObserver` → `fitRef.current?.fit()` | 69–70 | ✅ |
| macOS-style toolbar dots (red / yellow / green) | 80–82 | ✅ |
| `↺ Reconnect` button calling `close + clear + connect` | 86–91 | ✅ |
| Cleanup: `ro.disconnect`, `wsRef.current?.close`, `term.dispose` | 73 | ✅ |

## Conclusion

`Terminal.jsx` was not modified. This file exists only to leave a **traceable record** of the verification outcome in git history.
