from __future__ import annotations

import json
from typing import Any

import anyio
from mcp.server.lowlevel import Server
from mcp.server.stdio import stdio_server
from mcp.types import CallToolRequestParams, CallToolResult, ListToolsResult, TextContent, Tool

from agent.tools import LocalToolRegistry


registry = LocalToolRegistry()


async def list_tools(_context: Any, _params: Any) -> ListToolsResult:
    result: list[Tool] = []
    for definition in registry.definitions():
        function = definition["function"]
        result.append(
            Tool(
                name=function["name"],
                description=function.get("description"),
                inputSchema=function["parameters"],
            )
        )
    return ListToolsResult(tools=result)


async def call_tool(
    _context: Any,
    params: CallToolRequestParams,
) -> CallToolResult:
    result = registry.execute(params.name, params.arguments or {})
    return CallToolResult(
        content=[
            TextContent(
                type="text",
                text=json.dumps(result, ensure_ascii=False, default=str),
            )
        ],
        isError=not result.get("ok", False),
    )


server = Server(
    "m-auto-pilot",
    version="1.0.0",
    on_list_tools=list_tools,
    on_call_tool=call_tool,
)


async def _run_server() -> None:
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


def run_server() -> None:
    anyio.run(_run_server)


if __name__ == "__main__":
    run_server()
