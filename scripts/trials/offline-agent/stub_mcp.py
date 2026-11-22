"""Stub stdio MCP server with one tool, `add` (mcp SDK 2.x MCPServer, which replaced FastMCP)."""
from mcp.server.mcpserver import MCPServer

mcp = MCPServer("stub")


@mcp.tool()
def add(a: int, b: int) -> int:
    """Add two integers."""
    return a + b


if __name__ == "__main__":
    mcp.run("stdio")
