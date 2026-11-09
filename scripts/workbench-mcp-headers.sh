#!/bin/sh
# Claude Code's headersHelper for Workbench's MCP server (.mcp.json, written by scripts/harness.py): prints
# {"Authorization": "Bearer <a fresh one-hour token for the claude-code agent>"}. Claude Code runs it at each
# connection and again after a 401, so no token is ever stored in a file.
exec "$(dirname "$0")/workbench.sh" token "${WB_MCP_AGENT:-claude-code}" --hours 1 --header
