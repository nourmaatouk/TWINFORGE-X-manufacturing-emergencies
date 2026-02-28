"""
MCP Client - Calls tools on MCP (Model Context Protocol) tool servers.
"""

import logging
from typing import Any
import httpx

logger = logging.getLogger(__name__)


class MCPClient:
    """Client for interacting with MCP tool servers."""

    def __init__(self, server_url: str):
        self.server_url = server_url

    async def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """Call a tool on the MCP server."""
        logger.info(f"Calling MCP tool: {tool_name}")

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{self.server_url}/tools/{tool_name}",
                    json=arguments,
                )
                response.raise_for_status()
                return response.json()
        except httpx.HTTPError as e:
            logger.error(f"MCP tool call failed: {e}")
            return {"error": str(e), "tool": tool_name}

    async def list_tools(self) -> list[dict[str, Any]]:
        """List available tools on the MCP server."""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(f"{self.server_url}/tools")
                response.raise_for_status()
                return response.json()
        except httpx.HTTPError as e:
            logger.error(f"Failed to list MCP tools: {e}")
            return []
