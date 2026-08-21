from __future__ import annotations

import asyncio
import json
import os
import re
import threading
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

from core.project import APP_ROOT


@dataclass(frozen=True)
class MCPServerSpec:
    name: str
    command: str
    args: tuple[str, ...]
    cwd: str | None
    env: dict[str, str] | None


class MCPClientManager:
    def __init__(self, config_path: str | Path | None = None) -> None:
        self.config_path = (
            Path(config_path).expanduser()
            if config_path
            else None
        )
        self._errors: dict[str, str] = {}
        self._specs = self._load_specs()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._ready = threading.Event()
        self._lock = threading.RLock()
        self._sessions: dict[str, ClientSession] = {}
        self._session_contexts: dict[str, Any] = {}
        self._stdio_contexts: dict[str, Any] = {}
        self._tool_map: dict[str, tuple[str, str]] = {}
        self._definitions: list[dict[str, Any]] = []

    def start(self) -> None:
        if not self._specs:
            return
        with self._lock:
            if self._thread and self._thread.is_alive():
                return
            self._thread = threading.Thread(
                target=self._thread_main,
                name="m-auto-pilot-mcp",
                daemon=True,
            )
            self._thread.start()
        if not self._ready.wait(5):
            self._errors["manager"] = "MCP client loop không khởi động kịp."
            return
        loop = self._loop
        if loop is None:
            return
        future = asyncio.run_coroutine_threadsafe(
            self._connect_all(),
            loop,
        )
        try:
            future.result(timeout=30)
        except Exception as error:
            self._errors["manager"] = str(error)

    def definitions(self) -> list[dict[str, Any]]:
        with self._lock:
            return list(self._definitions)

    def has_tool(self, name: str) -> bool:
        with self._lock:
            return name in self._tool_map

    def execute(
        self,
        name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        with self._lock:
            target = self._tool_map.get(name)
            loop = self._loop
        if target is None:
            return {"ok": False, "error": f"MCP tool không được phép: {name}"}
        if loop is None:
            return {"ok": False, "error": "MCP client chưa kết nối."}
        future = asyncio.run_coroutine_threadsafe(
            self._call_tool(target[0], target[1], arguments),
            loop,
        )
        try:
            return future.result(timeout=1800)
        except Exception as error:
            return {"ok": False, "error": f"MCP tool lỗi: {error}"}

    def status(self) -> dict[str, Any]:
        with self._lock:
            return {
                "configured": len(self._specs),
                "connected": len(self._sessions),
                "tools": len(self._definitions),
                "errors": dict(self._errors),
            }

    def close(self) -> None:
        with self._lock:
            loop = self._loop
            thread = self._thread
        if loop is not None and loop.is_running():
            future = asyncio.run_coroutine_threadsafe(
                self._close_all(),
                loop,
            )
            with suppress(Exception):
                future.result(timeout=10)
            loop.call_soon_threadsafe(loop.stop)
        if thread is not None and thread.is_alive():
            thread.join(timeout=10)
        with self._lock:
            self._loop = None
            self._thread = None
            self._ready.clear()

    def _thread_main(self) -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        with self._lock:
            self._loop = loop
        self._ready.set()
        try:
            loop.run_forever()
        finally:
            loop.close()

    async def _connect_all(self) -> None:
        for spec in self._specs:
            stdio_context = None
            session_context = None
            try:
                parameters = StdioServerParameters(
                    command=spec.command,
                    args=list(spec.args),
                    cwd=spec.cwd,
                    env=spec.env,
                )
                stdio_context = stdio_client(parameters)
                streams = await stdio_context.__aenter__()
                session_context = ClientSession(*streams)
                session = await session_context.__aenter__()
                await session.initialize()
                listed = await session.list_tools()
                with self._lock:
                    self._stdio_contexts[spec.name] = stdio_context
                    self._session_contexts[spec.name] = session_context
                    self._sessions[spec.name] = session
                    for tool in listed.tools:
                        exposed_name = self._exposed_name(
                            spec.name,
                            tool.name,
                        )
                        self._tool_map[exposed_name] = (
                            spec.name,
                            tool.name,
                        )
                        self._definitions.append({
                            "type": "function",
                            "function": {
                                "name": exposed_name,
                                "description": tool.description or (
                                    f"MCP tool {tool.name} từ {spec.name}."
                                ),
                                "parameters": tool.input_schema,
                            },
                        })
            except Exception as error:
                if session_context is not None:
                    with suppress(Exception):
                        await session_context.__aexit__(None, None, None)
                if stdio_context is not None:
                    with suppress(Exception):
                        await stdio_context.__aexit__(None, None, None)
                self._errors[spec.name] = str(error)

    async def _call_tool(
        self,
        server_name: str,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        with self._lock:
            session = self._sessions.get(server_name)
        if session is None:
            return {"ok": False, "error": f"MCP server chưa kết nối: {server_name}"}
        result = await session.call_tool(tool_name, arguments)
        parts: list[Any] = []
        for item in result.content:
            if getattr(item, "type", "") == "text":
                parts.append(item.text)
            else:
                with suppress(Exception):
                    parts.append(item.model_dump(mode="json", by_alias=True))
        value: Any = parts[0] if len(parts) == 1 else parts
        if isinstance(value, str):
            with suppress(json.JSONDecodeError):
                value = json.loads(value)
        if getattr(result, "is_error", False) or getattr(result, "isError", False):
            return {"ok": False, "error": value}
        if isinstance(value, dict) and isinstance(value.get("ok"), bool):
            return value
        return {"ok": True, "result": value}

    async def _close_all(self) -> None:
        for server_name in list(self._sessions):
            session_context = self._session_contexts.pop(server_name, None)
            stdio_context = self._stdio_contexts.pop(server_name, None)
            self._sessions.pop(server_name, None)
            if session_context is not None:
                with suppress(Exception):
                    await session_context.__aexit__(None, None, None)
            if stdio_context is not None:
                with suppress(Exception):
                    await stdio_context.__aexit__(None, None, None)
        with self._lock:
            self._tool_map.clear()
            self._definitions.clear()

    def _load_specs(self) -> list[MCPServerSpec]:
        if self.config_path is None or not self.config_path.is_file():
            return []
        try:
            payload = json.loads(self.config_path.read_text(encoding="utf-8"))
        except Exception as error:
            self._errors["config"] = str(error)
            return []
        if isinstance(payload, dict) and isinstance(payload.get("servers"), dict):
            payload = payload["servers"]
        if not isinstance(payload, dict):
            self._errors["config"] = "Cấu hình MCP phải là object server."
            return []
        specs: list[MCPServerSpec] = []
        for name, value in payload.items():
            if not isinstance(value, dict) or value.get("enabled", True) is False:
                continue
            command = value.get("command")
            if not isinstance(command, str) or not command.strip():
                self._errors[str(name)] = "Thiếu command MCP."
                continue
            args = value.get("args", [])
            if not isinstance(args, list) or not all(isinstance(item, str) for item in args):
                self._errors[str(name)] = "args MCP phải là mảng chuỗi."
                continue
            cwd = value.get("cwd")
            if isinstance(cwd, str) and cwd:
                cwd_path = Path(cwd).expanduser()
                if not cwd_path.is_absolute():
                    cwd_path = APP_ROOT / cwd_path
                cwd = str(cwd_path.resolve())
            else:
                cwd = None
            env_value = value.get("env")
            env = None
            if isinstance(env_value, dict):
                env = dict(os.environ)
                env.update({str(key): str(item) for key, item in env_value.items()})
            specs.append(MCPServerSpec(
                name=str(name),
                command=command,
                args=tuple(args),
                cwd=cwd,
                env=env,
            ))
        return specs

    def _exposed_name(self, server_name: str, tool_name: str) -> str:
        prefix = re.sub(r"[^a-zA-Z0-9_]+", "_", server_name).strip("_") or "server"
        suffix = re.sub(r"[^a-zA-Z0-9_]+", "_", tool_name).strip("_") or "tool"
        candidate = f"mcp__{prefix}__{suffix}"
        index = 2
        while candidate in self._tool_map:
            candidate = f"mcp__{prefix}__{suffix}_{index}"
            index += 1
        return candidate
