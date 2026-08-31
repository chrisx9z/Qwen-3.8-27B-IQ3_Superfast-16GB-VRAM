from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from agent.controller import AgentConfig, LocalAgent
from agent.tools import LocalToolRegistry
from llm.server_manager import LocalLLMServerManager


class StubAgent(LocalAgent):
    def __init__(self) -> None:
        super().__init__(
            config=AgentConfig(
                auto_start_server=True,
                model_profile="qwen38_iq3s",
            )
        )
        self.profiles: list[str] = []
        self.responses = [
            {
                "role": "assistant",
                "tool_calls": [
                    {
                        "id": "call1",
                        "type": "function",
                        "function": {
                            "name": "list_projects",
                            "arguments": "{\"limit\":1}",
                        },
                    }
                ],
            },
            {
                "role": "assistant",
                "content": "Đã kiểm tra project.",
            },
        ]

    def _ensure_server(self, profile: str) -> None:
        self.profiles.append(profile)

    def _chat(
        self,
        messages: list[dict],
        tool_definitions: list[dict],
        max_tokens: int,
    ) -> dict:
        return self.responses.pop(0)


def main() -> int:
    config = AgentConfig(auto_start_server=False)
    assert config.server_port == 8090
    assert config.endpoint.endswith(":8090/v1/chat/completions")
    assert config.model_profile == "qwen38_iq3s"

    manager = LocalLLMServerManager(
        profile="qwen38_iq3s",
        port=8090,
    )
    command = manager._build_command()
    assert command[command.index("--port") + 1] == "8090"
    assert "--model" in command

    registry = LocalToolRegistry()
    assert len(registry.definitions()) == 48
    assert not registry.execute(
        "browser_open",
        {"url": "file:///not-allowed"},
    )["ok"]
    assert not registry.execute(
        "browser_snapshot",
        {},
    )["ok"]
    assert not registry.execute(
        "ui_press_key",
        {"window_title": "missing", "key": "F1"},
    )["ok"]
    assert registry.execute(
        "list_processes",
        {"name": "python", "limit": 5},
    )["ok"]
    assert registry.execute(
        "get_resource_status",
        {},
    )["ok"]
    assert not registry.execute(
        "screen_ocr",
        {"image_path": "C:\\Windows\\not-allowed.png"},
    )["ok"]
    assert registry.execute(
        "read_code_file",
        {"path": "agent/controller.py", "max_chars": 2000},
    )["ok"]
    assert registry.execute(
        "search_code",
        {"query": "class LocalAgent", "path": "agent"},
    )["ok"]
    assert registry.execute(
        "git_status",
        {},
    )["ok"]
    assert registry.execute(
        "git_diff",
        {"path": "agent/tools.py"},
    )["ok"]
    assert registry.execute(
        "run_code_check",
        {"kind": "compile", "path": "agent/controller.py"},
    )["ok"]
    checkpoint = registry.execute(
        "create_checkpoint",
        {"paths": ["agent/controller.py"]},
    )
    assert checkpoint["ok"]
    assert registry.execute(
        "restore_checkpoint",
        {"checkpoint_id": checkpoint["result"]["checkpoint_id"]},
    )["ok"]
    assert registry.execute(
        "list_directory",
        {"path": "agent", "limit": 5},
    )["ok"]
    assert registry.execute(
        "get_system_status",
        {},
    )["ok"]
    assert not registry.execute(
        "run_project_stage",
        {"project_id": "missing", "stage": "invalid"},
    )["ok"]
    assert not registry.execute(
        "download_bilibili",
        {"url": "https://example.com"},
    )["ok"]

    agent = StubAgent()
    result = agent.run(
        "Liệt kê project.",
        model_profile="q6",
    )

    assert result.text == "Đã kiểm tra project."
    assert result.steps == 2
    assert agent.profiles == ["qwen38_q6"]
    print("local-agent tool-loop/profile: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
