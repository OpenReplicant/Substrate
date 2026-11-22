"""A stub stdio MCP server with the memory profile's tool names (recall, remember), for test_worker.py."""
from mcp.server.mcpserver import MCPServer

mcp = MCPServer("stub-memory")


@mcp.tool()
def recall(question: str) -> str:
    """Briefing of what is known about a question."""
    return "#abc12345 the water pump is on shelf B (source: stock list)"


@mcp.tool()
def remember(text: str, source: str = "") -> str:
    """Keep a claim."""
    return "remembered #def67890"


@mcp.tool()
def secret_admin() -> str:
    """Not a memory tool; the worker must not offer it."""
    return "no"


if __name__ == "__main__":
    mcp.run("stdio")
