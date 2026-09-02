# -*- coding: utf-8 -*-
"""Plugin & DeepSeek Harness Manager for M Auto Pilot.

Supports dynamically adding, enabling, disabling, and executing:
1. Custom Python Tool Plugins (.py scripts)
2. MCP (Model Context Protocol) Servers (stdio / sse)
3. DeepSeek Harness Personas / Skills (.json / .md)
"""
from __future__ import annotations

import importlib.util
import inspect
import json
import os
import sys
from pathlib import Path
from typing import Any, Callable

APP_ROOT = Path(os.environ.get("M_AUTO_PILOT_ROOT", Path(__file__).resolve().parents[1])).resolve()
PLUGIN_CONFIG_FILE = APP_ROOT / "work" / "auto_pilot" / "plugins.json"
CUSTOM_PLUGINS_DIR = APP_ROOT / "work" / "auto_pilot" / "custom_plugins"


class PluginInfo:
    def __init__(
        self,
        id: str,
        name: str,
        plugin_type: str,  # 'python_tool', 'mcp_server', 'harness_persona'
        description: str = "",
        entrypoint: str = "",
        enabled: bool = True,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self.id = id
        self.name = name
        self.plugin_type = plugin_type
        self.description = description
        self.entrypoint = entrypoint
        self.enabled = enabled
        self.metadata = metadata or {}

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "plugin_type": self.plugin_type,
            "description": self.description,
            "entrypoint": self.entrypoint,
            "enabled": self.enabled,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PluginInfo:
        return cls(
            id=data.get("id", ""),
            name=data.get("name", "Unnamed Plugin"),
            plugin_type=data.get("plugin_type", "python_tool"),
            description=data.get("description", ""),
            entrypoint=data.get("entrypoint", ""),
            enabled=data.get("enabled", True),
            metadata=data.get("metadata", {}),
        )


class PluginManager:
    _instance: PluginManager | None = None

    def __new__(cls) -> PluginManager:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self) -> None:
        if getattr(self, "_initialized", False):
            return
        self._initialized = True
        self.plugins: dict[str, PluginInfo] = {}
        CUSTOM_PLUGINS_DIR.mkdir(parents=True, exist_ok=True)
        self.load_plugins()

    def load_plugins(self) -> None:
        """Load plugin registrations from disk."""
        if not PLUGIN_CONFIG_FILE.exists():
            # Seed with default built-in plugins
            self._seed_default_plugins()
            self.save_plugins()
            return

        try:
            with open(PLUGIN_CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            for item in data.get("plugins", []):
                p = PluginInfo.from_dict(item)
                self.plugins[p.id] = p
        except Exception:
            self._seed_default_plugins()

    def _seed_default_plugins(self) -> None:
        self.plugins = {
            "mcp_local_hub": PluginInfo(
                id="mcp_local_hub",
                name="MCP Local Tool Hub",
                plugin_type="mcp_server",
                description="Hệ thống máy chủ MCP kết nối 302 công cụ tự động hóa hệ thống",
                entrypoint="agent.mcp_server",
                enabled=True,
                metadata={"tools_count": 302, "built_in": True},
            ),
            "deepseek_harness": PluginInfo(
                id="deepseek_harness",
                name="DeepSeek Harness Studio",
                plugin_type="harness_persona",
                description="Môi trường Prompt Harness & Multi-Agent Swarm tại cổng 3080",
                entrypoint="scripts/run_deepseek_harness.py",
                enabled=True,
                metadata={"port": 3080, "built_in": True},
            ),
            "vision_grounding": PluginInfo(
                id="vision_grounding",
                name="Computer Vision Grounding",
                plugin_type="python_tool",
                description="Công cụ phân tích UI, OCR văn bản và xác định tọa độ màn hình",
                entrypoint="agent.screen_tools",
                enabled=True,
                metadata={"built_in": True},
            ),
            "browser_automation": PluginInfo(
                id="browser_automation",
                name="Headless Browser Controller",
                plugin_type="python_tool",
                description="Điều khiển duyệt web tự động, cào dữ liệu và chụp ảnh trang web",
                entrypoint="agent.browser_tools",
                enabled=True,
                metadata={"built_in": True},
            ),
        }

    def save_plugins(self) -> None:
        """Persist plugin registrations to disk."""
        PLUGIN_CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "version": "2.0.0",
            "plugins": [p.to_dict() for p in self.plugins.values()],
        }
        with open(PLUGIN_CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def get_all_plugins(self) -> list[PluginInfo]:
        return list(self.plugins.values())

    def toggle_plugin(self, plugin_id: str, enabled: bool | None = None) -> bool:
        p = self.plugins.get(plugin_id)
        if p:
            if enabled is None:
                p.enabled = not p.enabled
            else:
                p.enabled = enabled
            self.save_plugins()
            return p.enabled
        return False

    def add_python_plugin(self, file_path: Path | str) -> tuple[bool, str]:
        """Import a Python script and register it as a plugin."""
        path = Path(file_path).resolve()
        if not path.exists() or path.suffix != ".py":
            return False, f"File không tồn tại hoặc không phải file Python: {path}"

        plugin_id = path.stem.lower().replace(" ", "_")
        try:
            spec = importlib.util.spec_from_file_location(plugin_id, str(path))
            if spec is None or spec.loader is None:
                return False, "Không thể đọc Python module spec"
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)

            desc = getattr(mod, "__doc__", "") or f"Python Plugin: {path.name}"
            target_dest = CUSTOM_PLUGINS_DIR / path.name
            if target_dest != path:
                target_dest.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")

            info = PluginInfo(
                id=plugin_id,
                name=path.stem.replace("_", " ").title(),
                plugin_type="python_tool",
                description=desc.strip(),
                entrypoint=str(target_dest),
                enabled=True,
                metadata={"filename": path.name, "built_in": False},
            )
            self.plugins[plugin_id] = info
            self.save_plugins()
            return True, f"Đã nạp thành công Plugin: {info.name}"
        except Exception as e:
            return False, f"Lỗi nạp Plugin: {e}"

    def add_mcp_server(self, name: str, command: str, args: list[str], env: dict[str, str] | None = None) -> tuple[bool, str]:
        """Register an MCP server configuration."""
        if not name or not command:
            return False, "Tên và lệnh thực thi MCP không được để trống"

        plugin_id = f"mcp_{name.lower().replace(' ', '_')}"
        info = PluginInfo(
            id=plugin_id,
            name=f"MCP: {name}",
            plugin_type="mcp_server",
            description=f"Máy chủ MCP chạy lệnh `{command} {' '.join(args)}`",
            entrypoint=command,
            enabled=True,
            metadata={"command": command, "args": args, "env": env or {}, "built_in": False},
        )
        self.plugins[plugin_id] = info
        self.save_plugins()
        return True, f"Đã đăng ký máy chủ MCP: {name}"

    def add_harness_persona(self, name: str, prompt_content: str, description: str = "") -> tuple[bool, str]:
        """Register a custom DeepSeek Harness persona / skill."""
        if not name or not prompt_content:
            return False, "Tên và nội dung Prompt Persona không được để trống"

        plugin_id = f"harness_{name.lower().replace(' ', '_')}"
        info = PluginInfo(
            id=plugin_id,
            name=f"Harness: {name}",
            plugin_type="harness_persona",
            description=description or f"Custom Prompt Persona: {name}",
            entrypoint=prompt_content[:100],
            enabled=True,
            metadata={"prompt": prompt_content, "built_in": False},
        )
        self.plugins[plugin_id] = info
        self.save_plugins()
        return True, f"Đã thêm Prompt Harness Persona: {name}"

    def remove_plugin(self, plugin_id: str) -> bool:
        if plugin_id in self.plugins:
            del self.plugins[plugin_id]
            self.save_plugins()
            return True
        return False
