"""MCP server that lets a running Copilot session list and switch the active BYOM model."""

from __future__ import annotations

from . import state

try:  # mcp >= 2
    from mcp.server.mcpserver import MCPServer as _Server
except ImportError:  # mcp 1.x
    from mcp.server.fastmcp import FastMCP as _Server

server = _Server(
    "byom",
    instructions="Use these tools when the user asks which model is active, to list models, "
    "or to switch model (e.g. 'switch to claude-haiku'). Match partial names to an alias.",
)


@server.tool()
def byom_status() -> str:
    """Show which BYOM model the Copilot session currently uses."""
    return f"Active model: {state.get_active() or 'none (run byom sync)'}"


@server.tool()
def byom_list_models() -> str:
    """List the models that can be selected with byom_use."""
    active = state.get_active()
    lines = [f"{'* ' if a == active else '  '}{a}" for a in state.list_aliases()]
    return "\n".join(lines) or "No models. Run 'byom sync' first."


@server.tool()
def byom_use(alias: str) -> str:
    """Switch the active BYOM model. Takes effect on the next request in this session."""
    try:
        state.set_active(alias)
    except ValueError as e:
        return str(e)
    return f"Active model is now {alias}. The next message is answered by this model."


def main() -> None:
    server.run("stdio")
