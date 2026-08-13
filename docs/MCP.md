# MCP (Model Context Protocol)

Platform-assistant-portal speaks MCP in **both** directions:

| Role | Package | Purpose |
|------|---------|---------|
| **Client** | `backend/mcp/` registry + `hitl_bridge` | Connect *out* to external MCP servers; tool calls go through auth, tenant scope, and HITL |
| **Server** | `backend/mcp/server_app.py` | Expose portal domain tools *in* to IDEs / agents over stdio |

MCP is an **edge protocol**. It does not replace connectors, agents, or HITL. Every mutating action still ends in a human-approval queue inside the portal.

## Architecture (blurb)

```
 IDE / Claude Desktop                 Portal
 ┌──────────────────┐                ┌─────────────────────────────────────┐
 │ MCP client       │  stdio JSON-RPC│  python -m backend.mcp.server_app   │
 │ (Cursor, etc.)   │───────────────►│  PORTAL_MCP_TOKEN auth              │
 └──────────────────┘                │  read tools → DB / GitHub connector │
                                     │  write tools → AWAITING_APPROVAL /   │
                                     │               AgentRun pending      │
 ┌──────────────────┐                │                                     │
 │ External MCP     │◄── client ─────│  /api/mcp/* + hitl_bridge (M1)      │
 │ (filesystem, …)  │                └─────────────────────────────────────┘
 └──────────────────┘
```

## Portal as MCP server

### Enable

```bash
# backend/.env
MCP_ENABLED=true
PORTAL_MCP_TOKEN=generate_a_long_random_token
```

### Run

```bash
python -m backend.mcp.server_app
```

### IDE / Claude Desktop config (example)

```json
{
  "mcpServers": {
    "platform-assistant": {
      "command": "python",
      "args": ["-m", "backend.mcp.server_app"],
      "cwd": "/path/to/Platform-assistant-portal",
      "env": {
        "MCP_ENABLED": "true",
        "PORTAL_MCP_TOKEN": "same-token-as-backend-env",
        "DATABASE_URL": "postgresql://...",
        "SECRETS_ENCRYPTION_KEY": "..."
      }
    }
  }
}
```

The child process must see the **same** `PORTAL_MCP_TOKEN` as the portal (or pass `token` in `initialize` / `tools/*` params). Requests without a matching token are rejected.

### Tools

**Read (auto-run):**

| Tool | Behavior |
|------|----------|
| `portal_list_incidents` | Tenant-scoped incident list |
| `portal_get_incident` | Single incident |
| `portal_list_catalog_services` | Active catalog entities |
| `portal_search` | Catalog name search |
| `portal_health_summary` | Platform health summary |
| `portal_list_github_repos` | Repos via scoped Tool Registry GitHub account |

**Write (HITL — never execute directly):**

| Tool | Behavior |
|------|----------|
| `portal_propose_remediation` | Sets incident `AWAITING_APPROVAL` + proposed plan |
| `portal_run_agent` | Creates `AgentRun` with `pending_approval` |

Approve remediations / agent runs in the portal UI (incident command center / agent approvals), not via a blind MCP side channel.

## External MCP servers (client)

Admin UI: **Settings → MCP Servers**. API: `/api/mcp/servers`, `/api/mcp/tools`, `/api/mcp/tools/call`.

- Env secrets encrypted with `SECRETS_ENCRYPTION_KEY`; GET returns `env_keys` / `has_env` only.
- Read tools may auto-run; write/dangerous tools (or servers with `require_hitl`) create `mcp_tool_calls` in `pending_approval`.
- Approve via `/api/mcp/calls/{id}/approve`.

## Agent integration

When `MCP_ENABLED=true`:

- `BaseAgent._call_llm` injects an MCP tool catalog into the system prompt.
- `code_review_agent` / `pipeline_monitor_agent` prefer MCP GitHub list tools when configured, otherwise the scoped GitHub connector.

## Protocol note

Wire format is MCP JSON-RPC 2.0 implemented directly (no official `mcp` SDK dependency). See `backend/mcp/types.py`.
