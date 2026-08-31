from __future__ import annotations

import argparse
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from agent.controller import AgentConfig, LocalAgent
from core.console import configure_utf8_stdio


def main() -> int:
    configure_utf8_stdio()
    parser = argparse.ArgumentParser(
        description="Chạy agent local dùng Qwen3.8 với tool an toàn."
    )
    parser.add_argument(
        "prompt",
        nargs="?",
        help="Yêu cầu chạy một lần; bỏ trống để vào chế độ hội thoại.",
    )
    parser.add_argument(
        "--endpoint",
        default=None,
        help="Endpoint OpenAI-compatible của Local LLM.",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=None,
        help="Cổng agent, mặc định 8090.",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="Tên model gửi trong request.",
    )
    parser.add_argument(
        "--no-server",
        action="store_true",
        help="Không tự khởi động llama-server.",
    )
    parser.add_argument(
        "--max-steps",
        type=int,
        default=None,
        help="Số vòng model tối đa.",
    )
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=None,
        help="Số token model tối đa mỗi vòng.",
    )
    parser.add_argument(
        "--context-size",
        type=int,
        default=None,
        help="Context agent, mặc định 16384.",
    )
    parser.add_argument(
        "--reasoning-effort",
        choices=("low", "medium", "high", "xhigh"),
        default=None,
        help="Mức reasoning tùy endpoint hỗ trợ.",
    )
    parser.add_argument(
        "--mcp-config",
        default=None,
        help="File JSON cấu hình MCP client tùy chọn.",
    )
    args = parser.parse_args()

    endpoint = args.endpoint
    if endpoint is None and args.port is not None:
        endpoint = f"http://127.0.0.1:{args.port}/v1/chat/completions"

    overrides = {
        key: value
        for key, value in {
            "endpoint": endpoint,
            "server_port": args.port,
            "model": args.model,
            "max_steps": args.max_steps,
            "max_tokens": args.max_tokens,
            "context_size": args.context_size,
            "reasoning_effort": args.reasoning_effort,
            "mcp_config": args.mcp_config,
            "model_profile": "qwen38_iq3s",
            "auto_start_server": not args.no_server,
        }.items()
        if value is not None
    }
    config = AgentConfig.from_env(**overrides)

    def on_event(event: str, payload: dict) -> None:
        if event == "tool_call":
            print(
                f"[tool] {payload.get('name')} "
                f"{payload.get('arguments')}"
            )
        elif event == "tool_result":
            print(
                f"[tool-result] {payload.get('name')} "
                f"ok={payload.get('ok')}"
            )
        elif event == "delta" and payload.get("text"):
            print(payload["text"], end="", flush=True)

    agent = LocalAgent(
        config=config,
        event_callback=on_event,
    )
    messages = None

    if args.prompt:
        result = agent.run(args.prompt)
        print(result.text)
        return 0

    print("Local agent đã sẵn sàng (Qwen3.8-27B IQ3_S). Gõ 'exit' để thoát.")

    while True:
        try:
            prompt = input("Bạn> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0

        if prompt.lower() in {"exit", "quit", ":q"}:
            return 0

        if not prompt:
            continue

        try:
            result = agent.run(
                prompt,
                messages=messages,
                model_profile="qwen38_iq3s",
            )
            messages = result.messages
            print(f"\nAgent> {result.text}")
        except Exception as error:
            print(f"Lỗi: {error}")


if __name__ == "__main__":
    raise SystemExit(main())
