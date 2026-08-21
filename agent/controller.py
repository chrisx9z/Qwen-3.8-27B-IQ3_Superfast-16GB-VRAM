from __future__ import annotations

import ast
import json
import operator
import os
import re
from dataclasses import dataclass
from typing import Any, Callable

import requests

from agent.mcp_client import MCPClientManager
from agent.tools import LocalToolRegistry
from llm.resource_manager import GPUResourceManager
from llm.server_manager import AGENT_SERVER_PORT, LocalLLMServerManager


AGENT_SERVER_HOST = "127.0.0.1"
AGENT_BASE_URL = f"http://{AGENT_SERVER_HOST}:{AGENT_SERVER_PORT}"


EventCallback = Callable[[str, dict[str, Any]], None]


@dataclass(frozen=True)
class AgentConfig:
    endpoint: str = f"{AGENT_BASE_URL}/v1/chat/completions"
    server_host: str = AGENT_SERVER_HOST
    server_port: int = AGENT_SERVER_PORT
    model: str = "local-qwen"
    temperature: float = 0.2
    max_tokens: int = 2048
    max_steps: int = 16
    context_size: int = 16384
    connect_timeout: float = 10.0
    read_timeout: float = 1800.0
    auto_start_server: bool = True
    reasoning_effort: str | None = None
    model_profile: str = "qwen38_q4"
    mcp_config: str | None = None

    @classmethod
    def from_env(cls, **overrides: Any) -> "AgentConfig":
        server_host = os.environ.get(
            "AI_AGENT_LLM_HOST",
            cls.server_host,
        ).strip() or cls.server_host
        server_port = _env_int(
            "AI_AGENT_LLM_PORT",
            cls.server_port,
            minimum=1,
            maximum=65535,
        )
        values: dict[str, Any] = {
            "endpoint": os.environ.get(
                "AI_AGENT_LLM_ENDPOINT",
                f"http://{server_host}:{server_port}/v1/chat/completions",
            ),
            "server_host": server_host,
            "server_port": server_port,
            "model": os.environ.get(
                "AI_AGENT_LLM_MODEL",
                cls.model,
            ),
            "temperature": _env_float(
                "AI_AGENT_TEMPERATURE",
                cls.temperature,
                minimum=0.0,
                maximum=2.0,
            ),
            "max_tokens": _env_int(
                "AI_AGENT_MAX_TOKENS",
                cls.max_tokens,
                minimum=256,
                maximum=8192,
            ),
            "max_steps": _env_int(
                "AI_AGENT_MAX_STEPS",
                cls.max_steps,
                minimum=1,
                maximum=20,
            ),
            "context_size": _env_int(
                "AI_AGENT_CONTEXT_SIZE",
                cls.context_size,
                minimum=4096,
                maximum=131072,
            ),
            "connect_timeout": _env_float(
                "AI_AGENT_CONNECT_TIMEOUT",
                cls.connect_timeout,
                minimum=1.0,
                maximum=120.0,
            ),
            "read_timeout": _env_float(
                "AI_AGENT_READ_TIMEOUT",
                cls.read_timeout,
                minimum=5.0,
                maximum=3600.0,
            ),
            "auto_start_server": _env_bool(
                "AI_AGENT_AUTO_START_SERVER",
                cls.auto_start_server,
            ),
            "reasoning_effort": os.environ.get(
                "AI_AGENT_REASONING_EFFORT",
                "",
            ).strip()
            or None,
            "model_profile": _normalise_profile(
                os.environ.get(
                    "AI_AGENT_MODEL_PROFILE",
                    cls.model_profile,
                )
            ),
            "mcp_config": os.environ.get(
                "AI_AGENT_MCP_CONFIG",
                "",
            ).strip() or None,
        }
        values.update(overrides)
        return cls(**values)


@dataclass(frozen=True)
class AgentResult:
    text: str
    messages: list[dict[str, Any]]
    steps: int


class LocalAgent:
    system_prompt = """Bạn là agent cục bộ điều khiển AI Video Localizer.

Bạn phải biến yêu cầu thành công việc thực tế. Hãy tự chia nhỏ nhiệm vụ, kiểm tra trạng thái hiện tại, tìm kiếm Internet khi thiếu thông tin, thực thi từng bước bằng tool phù hợp và xác minh kết quả cuối. Không chỉ trả lời hướng dẫn nếu bạn có thể thực hiện bằng tool.

Chỉ sử dụng các tool được cung cấp. Không tự tạo shell command trong nội dung trả lời, không tự đoán đường dẫn và không tuyên bố đã hoàn thành nếu tool chưa trả kết quả thành công.

Dùng ID project và đường dẫn do tool trả về. Với thao tác tải hoặc tạo project, thực hiện đúng tham số người dùng yêu cầu và báo rõ kết quả, file đầu ra hoặc lỗi.

Chỉ gọi run_project_stage khi người dùng yêu cầu rõ việc xử lý một project; không tự chạy stage chỉ vì thấy project đang pending.

Khi người dùng yêu cầu lập trình, hãy đọc/tìm kiếm code liên quan, tạo checkpoint trước khi sửa, thay đổi tối thiểu, chạy run_code_check và kiểm tra git_diff. Chỉ sửa trong workspace; không truy cập secret, model, .venv hoặc chạy shell tùy ý.

Khi cần cài đặt, build, test hoặc chạy script trong repo, dùng run_workspace_command với argv allowlist; không dùng shell operators. Sau mỗi thao tác ghi/cài/chạy, đọc output và thực hiện bước xác minh tiếp theo.

Khi người dùng yêu cầu thao tác web, dùng browser_open rồi browser_snapshot/extract để xác định nội dung, sau đó click/type bằng selector hoặc text. Khi người dùng yêu cầu thao tác ứng dụng Windows, dùng ui_list_windows và ui_snapshot trước, rồi định vị control bằng title hoặc automation_id; không đoán tọa độ màn hình.

Khi cần thông tin bên ngoài, ưu tiên web_search rồi web_open hoặc search_github_repositories. Đánh giá nguồn và ngày cập nhật; không tin tuyệt đối vào repo/package do người dùng trích dẫn nếu chưa inspect.

Khi UI Automation không thấy control, dùng screen_capture hoặc screen_ocr để quan sát; OCR chỉ là tín hiệu định vị, không tự suy ra thao tác nguy hiểm. Dùng list_processes/read_runtime_log để chẩn đoán và chỉ stop_managed_process với runtime allowlist. Dùng get_resource_status trước request nặng hoặc khi đổi Q4/Q6; không chạy đồng thời nhiều model lớn nếu cảnh báo VRAM xuất hiện.

Nếu có MCP tool với tiền tố mcp__, dùng đúng namespace đó và báo rõ server MCP khi thao tác thất bại.

Khi người dùng yêu cầu cài repo hoặc npm package bên ngoài, trước tiên phải gọi inspect_github_repository hoặc inspect_npm_package để xác minh tồn tại. Nếu không tồn tại, dùng search_github_repositories/web_search tìm phương án thay thế; chỉ cài phương án thay thế nếu phù hợp rõ ràng và báo chính xác tên repo đã chọn. Nếu tồn tại, dùng install_github_repository hoặc install_npm_package; không tự chạy ứng dụng sau khi cài và chỉ báo thành công khi tool trả kết quả thành công.

Nếu tool trả lỗi, giải thích ngắn gọn nguyên nhân và đề xuất bước tiếp theo an toàn.
"""

    def __init__(
        self,
        *,
        config: AgentConfig | None = None,
        registry: LocalToolRegistry | None = None,
        server_manager: LocalLLMServerManager | None = None,
        mcp_client: MCPClientManager | None = None,
        event_callback: EventCallback | None = None,
    ) -> None:
        self.config = config or AgentConfig.from_env()
        self.registry = registry or LocalToolRegistry()
        self.server_manager = server_manager
        self.resource_manager = GPUResourceManager()
        self.mcp_client = mcp_client or MCPClientManager(
            self.config.mcp_config
        )
        self.event_callback = event_callback

    def run(
        self,
        prompt: str,
        *,
        messages: list[dict[str, Any]] | None = None,
        model_profile: str | None = None,
        task_mode: str = "auto",
    ) -> AgentResult:
        user_prompt = str(prompt or "").strip()

        if not user_prompt:
            raise ValueError("Prompt không được để trống.")

        quick_answer = _quick_arithmetic_answer(user_prompt)
        if quick_answer is not None:
            conversation = list(messages or [])
            if not conversation:
                conversation.append({
                    "role": "system",
                    "content": self.system_prompt,
                })
            conversation.extend([
                {"role": "user", "content": user_prompt},
                {"role": "assistant", "content": quick_answer},
            ])
            return AgentResult(
                text=quick_answer,
                messages=conversation,
                steps=0,
            )

        if _normalise_task_mode(task_mode) == "coding":
            user_prompt = (
                "Chế độ Coding Agent: ưu tiên dùng các tool đọc/tìm kiếm code, "
                "checkpoint, chỉnh sửa có kiểm soát và kiểm tra kết quả.\n\n"
                + user_prompt
            )

        active_profile = _normalise_profile(
            model_profile or self.config.model_profile
        )
        if active_profile == "qwen38_q4" and _should_use_fast_profile(user_prompt):
            active_profile = "qwen14"

        if (
            _normalise_task_mode(task_mode) != "coding"
            and _is_direct_localizer_task(user_prompt)
        ):
            return self._run_direct_localizer_task(user_prompt, messages)

        if (
            _normalise_task_mode(task_mode) != "coding"
            and _is_direct_repo_task(user_prompt)
        ):
            return self._run_direct_repo_task(user_prompt, messages)

        if (
            _normalise_task_mode(task_mode) != "coding"
            and _is_direct_youtube_search_task(user_prompt)
        ):
            return self._run_direct_youtube_search_task(user_prompt, messages)

        if (
            _normalise_task_mode(task_mode) != "coding"
            and _is_direct_bilibili_search_task(user_prompt)
        ):
            return self._run_direct_bilibili_search_task(user_prompt, messages)

        if (
            _normalise_task_mode(task_mode) != "coding"
            and _is_direct_douyin_search_task(user_prompt)
        ):
            return self._run_direct_douyin_search_task(user_prompt, messages)

        if (
            _normalise_task_mode(task_mode) != "coding"
            and _is_direct_web_search_task(user_prompt)
        ):
            return self._run_direct_web_search_task(user_prompt, messages)

        self._emit(
            "status",
            {"message": f"Đang chuẩn bị Auto Pilot {active_profile.upper()}..."},
        )
        self.mcp_client.start()

        if self.config.auto_start_server:
            self._emit(
                "status",
                {"message": f"Đang kiểm tra model {active_profile.upper()}..."},
            )
            self._ensure_server(active_profile)

        conversation = list(messages or [])

        if not conversation:
            conversation.append({
                "role": "system",
                "content": self.system_prompt,
            })

        conversation.append({
            "role": "user",
            "content": user_prompt,
        })
        tool_definitions = self._tool_definitions_for_prompt(user_prompt)
        max_tokens = self._max_tokens_for_prompt(user_prompt)

        for step in range(1, self.config.max_steps + 1):
            self._emit(
                "status",
                {
                    "message": (
                        f"Đang suy luận {active_profile.upper()} · "
                        f"bước {step}/{self.config.max_steps}..."
                    ),
                },
            )
            assistant_message = self._chat(
                conversation,
                tool_definitions,
                max_tokens,
            )
            conversation.append(assistant_message)

            tool_calls = assistant_message.get("tool_calls") or []

            if not tool_calls:
                text = str(
                    assistant_message.get("content")
                    or ""
                ).strip()

                if not text:
                    raise RuntimeError(
                        "Model không trả về nội dung hoặc tool call."
                    )

                return AgentResult(
                    text=text,
                    messages=conversation,
                    steps=step,
                )

            for tool_call in tool_calls:
                name, arguments, call_id = _tool_call_parts(
                    tool_call
                )
                self._emit(
                    "tool_call",
                    {
                        "name": name,
                        "arguments": arguments,
                    },
                )
                if self.mcp_client.has_tool(name):
                    result = self.mcp_client.execute(name, arguments)
                else:
                    result = self.registry.execute(name, arguments)
                self._emit(
                    "tool_result",
                    {
                        "name": name,
                        "ok": result.get("ok", False),
                    },
                )
                conversation.append({
                    "role": "tool",
                    "tool_call_id": call_id,
                    "name": name,
                    "content": _compact_json(result),
                })

        raise RuntimeError(
            f"Agent vượt quá giới hạn {self.config.max_steps} bước."
        )

    def _run_direct_repo_task(
        self,
        prompt: str,
        messages: list[dict[str, Any]] | None,
    ) -> AgentResult:
        conversation = list(messages or [])
        if not conversation:
            conversation.append({
                "role": "system",
                "content": self.system_prompt,
            })
        conversation.append({"role": "user", "content": prompt})

        explicit = _github_repository_from_prompt(prompt)
        selected = ""
        search_query_used = ""
        search_result_count = 0
        if explicit:
            query_result = self._execute_direct_tool(
                "inspect_github_repository",
                {"repository": explicit},
            )
            selected = explicit if query_result.get("ok") else ""
            if not selected:
                self._emit(
                    "status",
                    {"message": "Repo được nêu không tồn tại, đang tìm phương án thay thế..."},
                )
        if not selected:
            for search_query in _repo_search_queries(prompt):
                self._emit(
                    "status",
                    {"message": f"Đang tìm GitHub: {search_query}..."},
                )
                query_result = self._execute_direct_tool(
                    "search_github_repositories",
                    {
                        "query": search_query,
                        "limit": 5,
                    },
                )
                search_query_used = search_query
                search_result_count = _repository_count(query_result)
                selected = _best_repository(query_result)
                if selected:
                    break

        if not selected:
            text = (
                "Không tìm thấy repo GitHub phù hợp để cài. "
                "Hãy cung cấp tên repo hoặc mô tả cụ thể hơn."
            )
            conversation.append({"role": "assistant", "content": text})
            return AgentResult(text=text, messages=conversation, steps=1)

        if selected != explicit:
            inspect_result = self._execute_direct_tool(
                "inspect_github_repository",
                {"repository": selected},
            )
            if not inspect_result.get("ok"):
                text = f"Đã tìm thấy {selected} nhưng không xác minh được repo."
                conversation.append({"role": "assistant", "content": text})
                return AgentResult(text=text, messages=conversation, steps=1)

        self._emit(
            "status",
            {"message": f"Đang cài repo {selected}..."},
        )
        install_result = self._execute_direct_tool(
            "install_github_repository",
            {
                "repository": selected,
                "package_manager": "auto",
                "install_dependencies": True,
            },
        )
        if install_result.get("ok"):
            details = install_result.get("result") or {}
            search_note = (
                f"Đã tìm GitHub với query `{search_query_used}` và nhận "
                f"{search_result_count} kết quả.\n"
                if search_query_used
                else "Đã inspect trực tiếp repo được nêu.\n"
            )
            text = (
                f"{search_note}Đã chọn và inspect `{selected}`.\n"
                f"Đã cài repo {selected}.\n"
                f"Đường dẫn: {details.get('path', 'không rõ')}\n"
                f"Dependency: {details.get('message') or details.get('dependencies_installed', 'đã xử lý')}"
            )
        else:
            text = f"Đã xác minh {selected} nhưng cài đặt thất bại: {install_result.get('error', 'lỗi không rõ')}."
        conversation.append({"role": "assistant", "content": text})
        return AgentResult(text=text, messages=conversation, steps=1)

    def _run_direct_youtube_search_task(
        self,
        prompt: str,
        messages: list[dict[str, Any]] | None,
    ) -> AgentResult:
        conversation = list(messages or [])
        if not conversation:
            conversation.append({
                "role": "system",
                "content": self.system_prompt,
            })
        conversation.append({"role": "user", "content": prompt})

        query = _youtube_search_query(prompt)
        self._emit(
            "status",
            {"message": f"Đang tìm YouTube: {query}..."},
        )
        result = self._execute_direct_tool(
            "youtube_search",
            {
                "query": query,
                "limit": 5,
            },
        )
        payload = result.get("result") if result.get("ok") else None
        results = payload.get("results") if isinstance(payload, dict) else []
        if not results:
            result = self._execute_direct_tool(
                "web_search",
                {"query": f"site:youtube.com/watch {query}", "limit": 5},
            )
            payload = result.get("result") if result.get("ok") else None
            results = payload.get("results") if isinstance(payload, dict) else []

        if results:
            lines = [
                f"Đã tìm YouTube với query `{query}` và nhận {len(results)} kết quả:",
            ]
            for index, item in enumerate(results[:5], 1):
                title = str(item.get("title") or "Không có tiêu đề").strip()
                url = str(item.get("url") or "").strip()
                snippet = str(item.get("snippet") or "").strip()
                lines.append(f"{index}. {title}\n   {url}")
                if snippet:
                    lines.append(f"   {snippet}")
            text = "\n".join(lines)
        else:
            error = result.get("error") if isinstance(result, dict) else ""
            text = (
                f"Không tìm thấy kết quả YouTube cho `{query}`."
                + (f" Lỗi tìm kiếm: {error}" if error else "")
            )
        conversation.append({"role": "assistant", "content": text})
        return AgentResult(text=text, messages=conversation, steps=1)

    def _run_direct_bilibili_search_task(
        self,
        prompt: str,
        messages: list[dict[str, Any]] | None,
    ) -> AgentResult:
        conversation = list(messages or [])
        if not conversation:
            conversation.append({
                "role": "system",
                "content": self.system_prompt,
            })
        conversation.append({"role": "user", "content": prompt})

        query = _video_search_query(prompt)
        self._emit(
            "status",
            {"message": f"Đang tìm Bilibili: {query}..."},
        )
        result = self._execute_direct_tool(
            "bilibili_search",
            {"query": query, "limit": 5},
        )
        payload = result.get("result") if result.get("ok") else None
        results = payload.get("results") if isinstance(payload, dict) else []
        if results:
            lines = [
                f"Đã tìm Bilibili với query `{payload.get('query', query)}` và nhận {len(results)} kết quả:",
            ]
            for index, item in enumerate(results[:5], 1):
                title = str(item.get("title") or "Không có tiêu đề").strip()
                url = str(item.get("url") or "").strip()
                snippet = str(item.get("snippet") or "").strip()
                lines.append(f"{index}. {title}\n   {url}")
                if snippet:
                    lines.append(f"   {snippet}")
            text = "\n".join(lines)
        else:
            error = result.get("error") if isinstance(result, dict) else ""
            text = (
                f"Không tìm thấy kết quả Bilibili cho `{query}`."
                + (f" Lỗi tìm kiếm: {error}" if error else "")
            )
        conversation.append({"role": "assistant", "content": text})
        return AgentResult(text=text, messages=conversation, steps=1)

    def _run_direct_douyin_search_task(
        self,
        prompt: str,
        messages: list[dict[str, Any]] | None,
    ) -> AgentResult:
        conversation = list(messages or [])
        if not conversation:
            conversation.append({
                "role": "system",
                "content": self.system_prompt,
            })
        conversation.append({"role": "user", "content": prompt})

        query = _video_search_query(prompt)
        self._emit(
            "status",
            {"message": f"Đang tìm Douyin: {query}..."},
        )
        result = self._execute_direct_tool(
            "douyin_search",
            {"query": query, "limit": 5},
        )
        payload = result.get("result") if result.get("ok") else None
        results = payload.get("results") if isinstance(payload, dict) else []
        if results:
            lines = [
                f"Đã tìm Douyin với query `{payload.get('query', query)}` và nhận {len(results)} kết quả:",
            ]
            for index, item in enumerate(results[:5], 1):
                title = str(item.get("title") or "Không có tiêu đề").strip()
                url = str(item.get("url") or "").strip()
                snippet = str(item.get("snippet") or "").strip()
                lines.append(f"{index}. {title}\n   {url}")
                if snippet:
                    lines.append(f"   {snippet}")
            text = "\n".join(lines)
        else:
            error = result.get("error") if isinstance(result, dict) else ""
            text = (
                f"Không tìm thấy kết quả Douyin cho `{query}`."
                + (f" Lỗi tìm kiếm: {error}" if error else "")
            )
        conversation.append({"role": "assistant", "content": text})
        return AgentResult(text=text, messages=conversation, steps=1)

    def _run_direct_web_search_task(
        self,
        prompt: str,
        messages: list[dict[str, Any]] | None,
    ) -> AgentResult:
        conversation = list(messages or [])
        if not conversation:
            conversation.append({
                "role": "system",
                "content": self.system_prompt,
            })
        conversation.append({"role": "user", "content": prompt})

        query = _web_search_query(prompt)
        self._emit(
            "status",
            {"message": f"Đang tìm trên Internet: {query}..."},
        )
        result = self._execute_direct_tool(
            "web_search",
            {"query": query, "limit": 5},
        )
        payload = result.get("result") if result.get("ok") else None
        results = payload.get("results") if isinstance(payload, dict) else []
        if results:
            wants_research = any(
                marker in prompt.lower()
                for marker in ("tài liệu", "thông tin", "giải thích", "phân tích", "so sánh", "xác minh")
            )
            if wants_research:
                enriched = []
                for item in results[:3]:
                    url = str(item.get("url") or "").strip()
                    if not url:
                        continue
                    opened = self._execute_direct_tool(
                        "web_open",
                        {"url": url, "max_chars": 3000},
                    )
                    opened_payload = opened.get("result") if opened.get("ok") else None
                    if isinstance(opened_payload, dict):
                        item = dict(item)
                        item["excerpt"] = str(opened_payload.get("content") or "")[:900]
                    enriched.append(item)
                results = enriched or results
            lines = [
                f"Đã tìm Internet với query `{payload.get('query', query)}` và nhận {len(results)} kết quả:",
            ]
            for index, item in enumerate(results[:5], 1):
                title = str(item.get("title") or "Không có tiêu đề").strip()
                url = str(item.get("url") or "").strip()
                snippet = str(item.get("snippet") or "").strip()
                lines.append(f"{index}. {title}\n   {url}")
                if snippet:
                    lines.append(f"   {snippet}")
                excerpt = str(item.get("excerpt") or "").strip()
                if excerpt:
                    lines.append(f"   Trích xuất: {excerpt}")
            text = "\n".join(lines)
        else:
            error = result.get("error") if isinstance(result, dict) else ""
            text = (
                f"Không tìm thấy tài liệu phù hợp cho `{query}`."
                + (f" Lỗi tìm kiếm: {error}" if error else "")
            )
        conversation.append({"role": "assistant", "content": text})
        return AgentResult(text=text, messages=conversation, steps=1)

    def _run_direct_localizer_task(
        self,
        prompt: str,
        messages: list[dict[str, Any]] | None,
    ) -> AgentResult:
        conversation = list(messages or [])
        if not conversation:
            conversation.append({
                "role": "system",
                "content": self.system_prompt,
            })
        conversation.append({"role": "user", "content": prompt})
        lowered = prompt.lower()
        should_launch = any(
            marker in lowered
            for marker in ("mở", "khởi động", "launch", "start")
        )
        tool_name = (
            "ai_video_localizer_launch"
            if should_launch
            else "ai_video_localizer_status"
        )
        self._emit(
            "status",
            {"message": "Đang kiểm tra adapter AI Video Localizer..."},
        )
        result = self._execute_direct_tool(tool_name, {})
        if result.get("ok"):
            payload = result.get("result") or {}
            if should_launch:
                if payload.get("already_running"):
                    text = f"AI Video Localizer đã chạy, PID: {payload.get('pids', [])}."
                else:
                    text = f"Đã mở AI Video Localizer, PID: {payload.get('pid')}."
            else:
                text = (
                    "AI Video Localizer đang chạy."
                    if payload.get("running")
                    else "AI Video Localizer hiện chưa chạy."
                )
            text += f"\nWorkspace: {payload.get('root')}\nExecutable: {payload.get('executable')}"
        else:
            text = f"Không thể thao tác AI Video Localizer: {result.get('error', 'lỗi không rõ')}"
        conversation.append({"role": "assistant", "content": text})
        return AgentResult(text=text, messages=conversation, steps=1)

    def _execute_direct_tool(
        self,
        name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        self._emit(
            "tool_call",
            {"name": name, "arguments": arguments},
        )
        result = self.registry.execute(name, arguments)
        self._emit(
            "tool_result",
            {"name": name, "ok": result.get("ok", False)},
        )
        return result

    def close(self) -> None:
        self.mcp_client.close()

    def _ensure_server(self, profile: str) -> None:
        if self.server_manager is None:
            self.server_manager = LocalLLMServerManager(
                context_size=self.config.context_size,
                profile=profile,
                reasoning="auto" if profile == "qwen38_q6" else "off",
                host=self.config.server_host,
                port=self.config.server_port,
                replace_existing=True,
            )
        elif self.server_manager.profile != profile:
            self.server_manager.stop()
            self.server_manager = LocalLLMServerManager(
                context_size=self.config.context_size,
                profile=profile,
                reasoning="auto" if profile == "qwen38_q6" else "off",
                host=self.config.server_host,
                port=self.config.server_port,
                replace_existing=True,
            )

        self.resource_manager.claim_agent(
            profile=profile,
            port=self.server_manager.port,
            model_path=str(self.server_manager.model_path),
        )
        self.server_manager.ensure_running()

    def _tool_definitions_for_prompt(
        self,
        prompt: str,
    ) -> list[dict[str, Any]]:
        definitions = self.registry.definitions()
        lowered = prompt.lower()
        external_request = any(
            keyword in lowered
            for keyword in (
                "repo",
                "github",
                "npm",
                "package",
                "cài đặt",
                "cài phần mềm",
                "tìm kiếm",
                "thư viện",
                "install",
            )
        )
        coding_request = any(
            keyword in lowered
            for keyword in (
                "code",
                "lập trình",
                "sửa lỗi",
                "script",
                "python",
                "javascript",
            )
        )
        video_request = any(
            keyword in lowered
            for keyword in (
                "bilibili",
                "video",
                "project",
                "phụ đề",
                "localizer",
            )
        )
        if external_request and not coding_request and not video_request:
            names = {
                "get_resource_status",
                "get_system_status",
                "inspect_github_repository",
                "inspect_npm_package",
                "install_github_repository",
                "install_npm_package",
                "list_directory",
                "run_workspace_command",
                "search_github_repositories",
                "web_open",
                "web_search",
            }
            definitions = [
                definition
                for definition in definitions
                if definition.get("function", {}).get("name") in names
            ]
        elif coding_request and not video_request:
            names = {
                "create_checkpoint",
                "create_code_file",
                "git_diff",
                "git_status",
                "list_directory",
                "read_code_file",
                "replace_code",
                "run_code_check",
                "run_workspace_command",
                "search_code",
                "web_open",
                "web_search",
            }
            definitions = [
                definition
                for definition in definitions
                if definition.get("function", {}).get("name") in names
            ]
        elif video_request:
            names = {
                "download_bilibili",
                "get_project",
                "get_resource_status",
                "list_projects",
                "list_directory",
                "run_project_stage",
                "run_workspace_command",
                "browser_open",
                "browser_snapshot",
                "browser_extract",
                "browser_close",
                "ai_video_localizer_status",
                "ai_video_localizer_launch",
                "ui_list_windows",
                "ui_snapshot",
                "ui_click",
                "ui_type",
                "ui_press_key",
                "bilibili_search",
                "youtube_search",
                "web_open",
                "web_search",
            }
            definitions = [
                definition
                for definition in definitions
                if definition.get("function", {}).get("name") in names
            ]
        return definitions + self.mcp_client.definitions()

    def _max_tokens_for_prompt(self, prompt: str) -> int:
        lowered = prompt.lower()
        if any(
            keyword in lowered
            for keyword in (
                "repo",
                "github",
                "npm",
                "package",
                "cài đặt",
                "install",
            )
        ):
            return min(self.config.max_tokens, 768)
        return self.config.max_tokens

    def _chat(
        self,
        messages: list[dict[str, Any]],
        tool_definitions: list[dict[str, Any]],
        max_tokens: int,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "model": self.config.model,
            "temperature": self.config.temperature,
            "max_tokens": max_tokens,
            "stream": False,
            "parallel_tool_calls": False,
            "tool_choice": "auto",
            "messages": messages,
            "tools": tool_definitions,
        }

        if self.config.reasoning_effort:
            body["reasoning_effort"] = self.config.reasoning_effort

        try:
            response = requests.post(
                self.config.endpoint,
                json=body,
                timeout=(
                    self.config.connect_timeout,
                    self.config.read_timeout,
                ),
            )
            response.raise_for_status()
            payload = response.json()
        except requests.Timeout as error:
            raise RuntimeError(
                "Local agent hết thời gian chờ model."
            ) from error
        except requests.RequestException as error:
            detail = str(error)
            if getattr(error.response, "text", ""):
                detail = error.response.text[:1000]
            raise RuntimeError(
                "Không thể gọi endpoint Local LLM: "
                f"{detail}"
            ) from error
        except ValueError as error:
            raise RuntimeError(
                "Endpoint Local LLM trả về JSON không hợp lệ."
            ) from error

        choices = payload.get("choices") or []

        if not choices:
            raise RuntimeError(
                "Local LLM không trả về choices."
            )

        message = choices[0].get("message") or {}

        if not isinstance(message, dict):
            raise RuntimeError(
                "Local LLM trả về message không hợp lệ."
            )

        return message

    def _emit(
        self,
        event: str,
        payload: dict[str, Any],
    ) -> None:
        if self.event_callback is not None:
            self.event_callback(event, payload)


def _tool_call_parts(
    tool_call: dict[str, Any],
) -> tuple[str, dict[str, Any], str]:
    function = tool_call.get("function") or {}
    name = str(function.get("name") or "").strip()
    raw_arguments = function.get("arguments", {})
    call_id = str(tool_call.get("id") or name)

    if isinstance(raw_arguments, str):
        try:
            arguments = json.loads(raw_arguments or "{}")
        except json.JSONDecodeError:
            arguments = {}
    elif isinstance(raw_arguments, dict):
        arguments = raw_arguments
    else:
        arguments = {}

    if not isinstance(arguments, dict):
        arguments = {}

    return name, arguments, call_id


def _compact_json(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return encoded[:16000]


def _env_int(
    name: str,
    default: int,
    *,
    minimum: int,
    maximum: int,
) -> int:
    try:
        value = int(os.environ.get(name, default))
    except (TypeError, ValueError):
        value = default

    return max(minimum, min(maximum, value))


def _env_float(
    name: str,
    default: float,
    *,
    minimum: float,
    maximum: float,
) -> float:
    try:
        value = float(os.environ.get(name, default))
    except (TypeError, ValueError):
        value = default

    return max(minimum, min(maximum, value))


def _env_bool(
    name: str,
    default: bool,
) -> bool:
    value = os.environ.get(name)

    if value is None:
        return default

    return value.strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _normalise_profile(value: object) -> str:
    profile = str(value or "").strip().lower()

    if profile in {"q4", "qwen38", "qwen38_q4"}:
        return "qwen38_q4"

    if profile in {"q6", "qwen38_q6"}:
        return "qwen38_q6"

    if profile in {"qwen14", "qwen3_14b", "fast"}:
        return "qwen14"

    return "qwen38_q4"


def _normalise_task_mode(value: object) -> str:
    return "coding" if str(value or "").strip().lower() == "coding" else "auto"


def _should_use_fast_profile(prompt: str) -> bool:
    lowered = prompt.lower()
    if len(prompt) > 420 or any(
        marker in lowered
        for marker in (
            "phức tạp",
            "toàn bộ",
            "kiến trúc",
            "nhiều bước",
            "phân tích sâu",
            "triển khai hệ thống",
        )
    ):
        return False
    return any(
        marker in lowered
        for marker in (
            "repo",
            "github",
            "npm",
            "package",
            "cài đặt",
            "tải",
            "tìm kiếm",
            "sửa lỗi",
            "chạy test",
        )
    )


def _is_direct_repo_task(prompt: str) -> bool:
    lowered = prompt.lower()
    has_target = any(
        marker in lowered
        for marker in ("repo", "github", "npm", "package")
    )
    has_install = any(
        marker in lowered
        for marker in ("cài", "install", "clone")
    )
    if _github_repository_from_prompt(prompt):
        return has_target and has_install
    if len(prompt) > 420 or any(
        marker in lowered
        for marker in (
            "phức tạp",
            "toàn bộ",
            "kiến trúc",
            "nhiều bước",
            "phân tích sâu",
            "triển khai hệ thống",
        )
    ):
        return False
    return has_target and has_install


def _is_direct_youtube_search_task(prompt: str) -> bool:
    lowered = prompt.lower()
    has_youtube = "youtube" in lowered or "youtu.be" in lowered
    has_search = any(
        marker in lowered
        for marker in ("tìm video", "tìm kiếm video", "tìm trên youtube", "search video")
    )
    has_download = any(
        marker in lowered
        for marker in ("tải video", "download", "tải xuống", "lưu video")
    )
    return has_youtube and has_search and not has_download and len(prompt) <= 420


def _is_direct_bilibili_search_task(prompt: str) -> bool:
    lowered = prompt.lower()
    has_bilibili = "bilibili" in lowered or "b23.tv" in lowered
    has_search = any(
        marker in lowered
        for marker in ("tìm video", "tìm kiếm video", "tìm trên bilibili", "search video")
    )
    has_download = any(
        marker in lowered
        for marker in ("tải video", "download", "tải xuống", "lưu video")
    )
    return has_bilibili and has_search and not has_download and len(prompt) <= 420


def _is_direct_douyin_search_task(prompt: str) -> bool:
    lowered = prompt.lower()
    has_douyin = "douyin" in lowered or "抖音" in lowered
    has_search = any(
        marker in lowered
        for marker in ("tìm video", "tìm kiếm video", "tìm trên douyin", "search video")
    )
    has_download = any(
        marker in lowered
        for marker in ("tải video", "download", "tải xuống", "lưu video")
    )
    return has_douyin and has_search and not has_download and len(prompt) <= 420


def _is_direct_web_search_task(prompt: str) -> bool:
    lowered = prompt.lower()
    has_search = any(
        marker in lowered
        for marker in (
            "tìm",
            "tra cứu",
            "search",
            "look up",
            "tìm tài liệu",
            "tìm thông tin",
        )
    )
    has_topic = any(
        marker in lowered
        for marker in (
            "internet",
            "trên web",
            "website",
            "trang web",
            "tài liệu",
            "thông tin",
            "video",
            "phim",
            "tin tức",
        )
    )
    has_action = any(
        marker in lowered
        for marker in (
            "cài đặt",
            "tải xuống",
            "download",
            "sửa lỗi",
            "viết code",
            "lập trình",
            "chạy code",
            "mở ứng dụng",
        )
    )
    return has_search and has_topic and not has_action and len(prompt) <= 1200


def _is_direct_localizer_task(prompt: str) -> bool:
    lowered = prompt.lower()
    has_target = "ai video localizer" in lowered or "video localizer" in lowered
    has_action = any(
        marker in lowered
        for marker in (
            "mở",
            "khởi động",
            "launch",
            "start",
            "trạng thái",
            "status",
            "đang chạy",
            "kiểm tra",
        )
    )
    return has_target and has_action and len(prompt) <= 300


def _video_search_query(prompt: str) -> str:
    query = re.sub(
        r"https?://\S+|www\.youtube\.com\S*|youtu\.be/\S*|bilibili(?:\.com)?\S*|b23\.tv\S*|douyin(?:\.com)?\S*",
        " ",
        prompt,
        flags=re.IGNORECASE,
    )
    query = re.sub(
        r"\b(giúp tôi|hãy|tìm kiếm|tìm|kiếm|cho tôi|video|trên|youtube|bilibili|douyin|đi)\b",
        " ",
        query,
        flags=re.IGNORECASE,
    )
    query = re.sub(r"\s+", " ", query).strip(" .,:;!?\"")
    return query[:160] or "video mới nhất"


def _web_search_query(prompt: str) -> str:
    query = re.sub(
        r"\b(giúp tôi|hãy|cho tôi|tìm kiếm|tìm|tra cứu|search|look up|trên internet|trên web|website|trang web|đi)\b",
        " ",
        prompt,
        flags=re.IGNORECASE,
    )
    query = re.sub(r"\s+", " ", query).strip(" .,:;!?\"")
    return query[:240] or "tài liệu mới nhất"


def _youtube_search_query(prompt: str) -> str:
    return _video_search_query(prompt)


def _github_repository_from_prompt(prompt: str) -> str:
    match = re.search(
        r"(?:https?://)?github\.com/([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)",
        prompt,
        re.IGNORECASE,
    )
    if match:
        return match.group(1).rstrip(".,;:)")

    for token in re.findall(r"\b[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+\b", prompt):
        if token.count("/") == 1:
            return token
    return ""


def _repo_search_query(prompt: str) -> str:
    lowered = prompt.lower()
    if "tiểu thuyết" in lowered or "novel" in lowered:
        return "novel writing"
    if any(
        marker in lowered
        for marker in ("vẽ tranh", "viết tranh", "minh họa", "hội họa", "digital art")
    ):
        return "drawing application"
    if "numerology" in lowered or "thần số học" in lowered:
        return "numerology"
    cleaned = re.sub(
        r"https?://\S+|github\.com/\S+|\b(repo|github|npm|package)\b",
        " ",
        prompt,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(
        r"\b(giúp tôi|hãy|tìm|cài đặt|cài|một|một repo|được đánh giá cao)\b",
        " ",
        cleaned,
        flags=re.IGNORECASE,
    )
    query = re.sub(r"\s+", " ", cleaned).strip()
    return query[:100] or "open source software"


def _repo_search_queries(prompt: str) -> tuple[str, ...]:
    lowered = prompt.lower()
    if "tiểu thuyết" in lowered or "novel" in lowered:
        return ("novel writing", "novel editor")
    if any(
        marker in lowered
        for marker in ("vẽ tranh", "viết tranh", "minh họa", "hội họa", "digital art")
    ):
        return ("drawing application", "digital art")
    if "numerology" in lowered or "thần số học" in lowered:
        return ("numerology", "numerology calculator")
    return (_repo_search_query(prompt),)


def _repository_count(result: dict[str, Any]) -> int:
    payload = result.get("result") if result.get("ok") else None
    if not isinstance(payload, dict):
        return 0
    results = payload.get("results")
    return len(results) if isinstance(results, list) else 0


def _best_repository(result: dict[str, Any]) -> str:
    if not result.get("ok"):
        return ""
    payload = result.get("result") or {}
    repositories = payload.get("results") if isinstance(payload, dict) else None
    if not isinstance(repositories, list):
        return ""
    candidates = [
        item
        for item in repositories
        if isinstance(item, dict) and item.get("full_name")
    ]
    if not candidates:
        return ""
    selected = max(
        candidates,
        key=lambda item: int(item.get("stars") or 0),
    )
    return str(selected["full_name"])


def _quick_arithmetic_answer(prompt: str) -> str | None:
    lowered = prompt.lower()
    if len(prompt) > 120 or any(
        keyword in lowered
        for keyword in (
            "cài",
            "tải",
            "sửa",
            "chạy",
            "mở",
            "repo",
            "file",
            "project",
            "download",
            "install",
            "code",
            "internet",
            "web",
        )
    ):
        return None

    match = re.search(r"(?<![\w.])([0-9][0-9\s()+*/%.-]*[0-9])", prompt)
    if match is None:
        return None

    expression = match.group(1).replace(" ", "")
    if not re.fullmatch(r"[0-9]+(?:[+*/%-][0-9]+)+", expression):
        return None

    try:
        tree = ast.parse(expression, mode="eval").body
        value = _evaluate_arithmetic(tree)
    except (ArithmeticError, SyntaxError, ValueError):
        return None

    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return f"{value:g}" if isinstance(value, float) else str(value)


def _evaluate_arithmetic(node: ast.AST) -> int | float:
    operators = {
        ast.Add: operator.add,
        ast.Sub: operator.sub,
        ast.Mult: operator.mul,
        ast.Div: operator.truediv,
        ast.Mod: operator.mod,
    }
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in operators:
        return operators[type(node.op)](
            _evaluate_arithmetic(node.left),
            _evaluate_arithmetic(node.right),
        )
    raise ValueError("Biểu thức không được hỗ trợ.")
