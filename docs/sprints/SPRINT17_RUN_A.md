# Sprint 17 — Run A (package verification)

**Date:** 2026-05-18  
**Scope:** Read `package.json` in full; confirm Monaco and xterm packages are in `dependencies`; run `npm install`; do not change existing versions or scripts.

## Required packages

| Package | Example pin (task text) | Already in `package.json` |
|--------|-------------------------|---------------------------|
| `@monaco-editor/react` | `^4.6.0` | `^4.7.0` (in `dependencies`) |
| `@xterm/xterm` | `^5.3.0` | `^6.0.0` (in `dependencies`) |
| `@xterm/addon-fit` | `^0.8.0` | `^0.11.0` (in `dependencies`) |

## Why `package.json` was not modified

1. All three packages were **already declared** under `dependencies`.
2. The run explicitly forbade **changing any existing package versions or scripts**. Replacing the current ranges with the older example pins would violate that rule without adding capability (the requested packages are already present).
3. **Duplicate keys** for the same package in a single JSON object are invalid; we could not “add” a second entry for each name.

## Follow-up

`npm install` was executed after verification; the tree reported **up to date** (no `package.json` or lockfile edits required for this check).

This file exists only to leave a **traceable record** of the verification outcome in git history.
