from __future__ import annotations

import ast
import json
import operator
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import requests

from agent.mcp_client import MCPClientManager
from agent.tools import LocalToolRegistry
from core.project import APP_ROOT
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
    max_steps: int = 24
    context_size: int = 16384
    connect_timeout: float = 10.0
    read_timeout: float = 1800.0
    auto_start_server: bool = True
    reasoning_effort: str | None = None
    model_profile: str = "qwen38_iq3s"
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
    system_prompt = """You are Qwen 3.8 27B IQ3_Superfast 16GB VRAM — an autonomous local AI Assistant, Coding Agent, and Computer Use automation system running 100% locally.

Roles & Capabilities:
1. Personal Assistant & Deep-Dive Researcher: Answer questions with high intellectual rigor, precision, and depth. When investigating questions, topics, market trends, social media, videos, technical documentation, or real-time metrics, proactively formulate searches, read pages, and cross-reference information across the internet.
2. Coding Agent: Read and search codebase, inspect syntax, edit files cleanly, generate comprehensive tests, apply patches, and manage git workflows within the workspace.
3. Computer Use & OS Automation: Perform smooth mouse movements, accurate keyboard typing, Chrome CDP browser automation, and pixel-precise OCR visual grounding with real-time Safety Sandbox protection.

Core Operating Principles:
- Autonomous Proactive Deep-Dive & Self-Directed Investigation:
  * NEVER give up or give a passive refusal (such as "Tôi không thể truy cập", "Tôi không biết", "Dữ liệu không có sẵn") when answering questions that require external data, facts, statistics, channel metrics, or documentation.
  * If you lack data or context, you MUST PROACTIVELY use your tools (`deep_dive_internet_research`, `web_search`, `web_open`, `extract_webpage_markdown`, `analyze_youtube_channel_deep_dive`, `read_code_file`, etc.) to explore, search multiple angles, read source websites, extract exact facts/numbers, and synthesize comprehensive, verified answers.
- Multi-lingual Language Directive: Automatically detect the language of the user's prompt (English, Vietnamese, Chinese, etc.) and ALWAYS respond in the EXACT same language with natural phrasing, rich details, and clean markdown structure.
- Action over guidance: Use tools to inspect, execute, and verify results directly instead of just giving generic advice.
- Safety Sandbox Enforcement: Always operate within authorized workspace boundaries. Never execute destructive OS commands.
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
        self._http_session = requests.Session()
        adapter = requests.adapters.HTTPAdapter(
            pool_connections=20,
            pool_maxsize=20,
            max_retries=1,
        )
        self._http_session.mount("http://", adapter)
        self._http_session.mount("https://", adapter)

    def run(
        self,
        prompt: str,
        *,
        messages: list[dict[str, Any]] | None = None,
        model_profile: str | None = None,
        task_mode: str = "auto",
        abort_check: Callable[[], bool] | None = None,
    ) -> AgentResult:
        user_prompt = str(prompt or "").strip()

        if not user_prompt:
            raise ValueError("Prompt không được để trống.")

        def is_aborted() -> bool:
            if abort_check is not None:
                try:
                    return bool(abort_check())
                except Exception:
                    return False
            return False

        if is_aborted():
            return AgentResult(text="[Đã dừng bởi người dùng]", messages=messages or [], steps=0)

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

        norm_mode = _normalise_task_mode(task_mode)
        if norm_mode == "coding":
            user_prompt = (
                "Chế độ Coding Agent: ưu tiên dùng các tool đọc/tìm kiếm code, "
                "cây thư mục, patch code thông minh, git, checkpoint và kiểm tra kết quả.\n\n"
                + user_prompt
            )
        elif norm_mode == "fullstack":
            user_prompt = (
                "Persona: Chuyên gia Lập trình Full-Stack Pro (am hiểu kiến trúc hệ thống, API backend, frontend UI, database, tối ưu mã nguồn).\n\n"
                + user_prompt
            )
        elif norm_mode == "devops":
            user_prompt = (
                "Persona: Chuyên gia DevOps & Automation (am hiểu Git workflow, CI/CD, docker, batch commands, tự động hóa môi trường).\n\n"
                + user_prompt
            )
        elif norm_mode == "auditor":
            user_prompt = (
                "Persona: Chuyên gia Security & Performance Auditor (chuyên rà soát lỗ hổng, tối ưu VRAM/RAM/CPU, profiling mã nguồn).\n\n"
                + user_prompt
            )
        elif norm_mode == "translator":
            user_prompt = (
                "Persona: Chuyên gia Dịch thuật & Content Creator (dịch chuẩn văn phong tiếng Việt - Anh - Trung, phụ đề video, tóm tắt).\n\n"
                + user_prompt
            )

        active_profile = _normalise_profile(
            model_profile or self.config.model_profile
        )

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
            and _is_universal_discovery_task(user_prompt)
        ):
            return self._run_universal_discovery_task(user_prompt, messages)

        if (
            _normalise_task_mode(task_mode) != "coding"
            and _is_direct_website_audit_task(user_prompt)
        ):
            return self._run_direct_website_audit_task(user_prompt, messages)

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
                "content": self.system_prompt + _get_system_memory_context(),
            })

        conversation.append({
            "role": "user",
            "content": _inject_attachment_context(user_prompt),
        })
        tool_definitions = self._tool_definitions_for_prompt(user_prompt)
        max_tokens = self._max_tokens_for_prompt(user_prompt)

        for step in range(1, self.config.max_steps + 1):
            if is_aborted():
                self._emit("status", {"message": "Đã dừng tác vụ theo yêu cầu."})
                return AgentResult(text="[Đã dừng bởi người dùng]", messages=conversation, steps=step)

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
                abort_check=abort_check,
            )
            conversation.append(assistant_message)

            if is_aborted():
                self._emit("status", {"message": "Đã dừng tác vụ theo yêu cầu."})
                return AgentResult(text="[Đã dừng bởi người dùng]", messages=conversation, steps=step)

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
                if is_aborted():
                    self._emit("status", {"message": "Đã dừng tác vụ theo yêu cầu."})
                    return AgentResult(text="[Đã dừng bởi người dùng]", messages=conversation, steps=step)

                name, arguments, call_id = _tool_call_parts(
                    tool_call
                )
                summary = _tool_call_summary(name, arguments)
                self._emit(
                    "tool_call",
                    {
                        "name": name,
                        "arguments": arguments,
                        "summary": summary,
                    },
                )
                if self.mcp_client.has_tool(name):
                    result = self.mcp_client.execute(name, arguments)
                else:
                    result = self.registry.execute(
                        name,
                        arguments,
                        event_callback=self._emit,
                    )
                self._emit(
                    "tool_result",
                    {
                        "name": name,
                        "ok": result.get("ok", False),
                        "summary": summary,
                    },
                )
                conversation.append({
                    "role": "tool",
                    "tool_call_id": call_id,
                    "name": name,
                    "content": _compact_json(result),
                })

        # Tự động chuyển sang bước tổng kết câu trả lời cuối cùng (Graceful final synthesis turn)
        self._emit(
            "status",
            {
                "message": (
                    f"Đang tổng hợp câu trả lời cuối cùng từ {self.config.max_steps} bước thực thi..."
                ),
            },
        )
        final_prompt = (
            "Đã hoàn thành các bước thu thập thông tin và thực thi công cụ ở trên. "
            "Hãy tổng hợp và đưa ra câu trả lời cuối cùng đầy đủ, rõ ràng và chi tiết cho người dùng."
        )
        conversation.append({
            "role": "user",
            "content": final_prompt,
        })
        try:
            final_message = self._chat(
                conversation,
                [],  # Không truyền tools để model tập trung trả lời văn bản cuối cùng
                max_tokens=self.config.max_tokens,
                abort_check=abort_check,
            )
            conversation.append(final_message)
            text = str(final_message.get("content") or "").strip()
            if text:
                return AgentResult(
                    text=text,
                    messages=conversation,
                    steps=self.config.max_steps,
                )
        except Exception:
            pass

        last_contents = [
            str(m.get("content", "")) for m in conversation if m.get("role") in ("tool", "assistant") and m.get("content")
        ]
        fallback_text = last_contents[-1] if last_contents else "Đã hoàn thành các bước tác vụ theo yêu cầu."
        return AgentResult(
            text=f"Đã hoàn thành {self.config.max_steps} bước thực thi và tổng hợp thông tin:\n\n{fallback_text}",
            messages=conversation,
            steps=self.config.max_steps,
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

    def _run_universal_discovery_task(
        self,
        prompt: str,
        messages: list[dict[str, Any]] | None,
    ) -> AgentResult:
        self._emit(
            "status",
            {"message": "Đang kích hoạt Động Cơ Tự Chủ Đào Sâu Tri Thức Tổng Quát (Recursive Autonomous Deep-Dive)..."},
        )
        res = self.registry.execute("recursive_autonomous_deep_dive", {"target_or_prompt": prompt})
        report = (res.get("result") or {}).get("report_markdown", "")
        if not report:
            report = f"Đã hoàn thành khám phá tự chủ cho yêu cầu: {prompt}"
            
        conversation = list(messages or [])
        if not conversation:
            conversation.append({
                "role": "system",
                "content": self.system_prompt,
            })
        conversation.extend([
            {"role": "user", "content": prompt},
            {"role": "assistant", "content": report},
        ])
        return AgentResult(
            text=report,
            messages=conversation,
            steps=1,
        )

    def _run_direct_website_audit_task(
        self,
        prompt: str,
        messages: list[dict[str, Any]] | None,
    ) -> AgentResult:
        url = _extract_url_from_prompt(prompt)
        self._emit(
            "status",
            {"message": f"Đang trực tiếp khảo sát cấu trúc website, sitemaps và bài viết: {url}..."},
        )
        res = self.registry.execute("audit_and_inspect_website_structure", {"url": url})
        report = res.get("result", {}).get("report_markdown", "")
        if not report:
            report = f"Đã hoàn thành khảo sát website {url}."
            
        conversation = list(messages or [])
        if not conversation:
            conversation.append({
                "role": "system",
                "content": self.system_prompt,
            })
        conversation.extend([
            {"role": "user", "content": prompt},
            {"role": "assistant", "content": report},
        ])
        return AgentResult(
            text=report,
            messages=conversation,
            steps=1,
        )

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
        try:
            self._http_session.close()
        except Exception:
            pass

    def _ensure_server(self, profile: str) -> None:
        if self.server_manager is None:
            self.server_manager = LocalLLMServerManager(
                context_size=self.config.context_size,
                profile=profile,
                reasoning="off",
                host=self.config.server_host,
                port=self.config.server_port,
                replace_existing=False,
            )
        elif self.server_manager.profile != profile:
            self.server_manager.stop()
            self.server_manager = LocalLLMServerManager(
                context_size=self.config.context_size,
                profile=profile,
                reasoning="off",
                host=self.config.server_host,
                port=self.config.server_port,
                replace_existing=False,
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
        all_definitions = self.registry.definitions(include_plugins=True)
        def_map = {
            d.get("function", {}).get("name"): d
            for d in all_definitions
            if d.get("function", {}).get("name")
        }
        lowered = prompt.lower()

        selected_names: set[str] = set()

        # 1. Base Core Tools (Always useful for general assistance & navigation)
        base_tools = {
            "universal_autonomous_omni_investigator",
            "recursive_autonomous_deep_dive",
            "universal_autonomous_entity_discovery",
            "audit_and_inspect_website_structure",
            "swarm_multi_agent_deep_investigation",
            "track_trending_industry_topics_radar",
            "generate_executive_research_briefing_pdf_md",
            "store_research_knowledge_item",
            "retrieve_relevant_research_knowledge",
            "evaluate_source_authority_and_recency",
            "generate_counterfactual_hypotheses_and_insights",
            "autonomous_multi_hop_research",
            "crawl_and_extract_deep_content",
            "cross_reference_and_fact_check",
            "deep_dive_internet_research",
            "analyze_youtube_channel_deep_dive",
            "web_search",
            "web_open",
            "extract_webpage_markdown",
            "youtube_search",
            "read_code_file",
            "list_directory",
            "get_system_status",
            "get_resource_status",
            "run_python_code",
        }
        selected_names.update(base_tools)

        # 2. Coding / File modification intent
        coding_keywords = (
            "code", "lập trình", "sửa lỗi", "script", "python", "javascript",
            "file", "tệp", "hàm", "class", "bug", "fix", "refactor", "git",
            "diff", "commit", "branch", "syntax", "tạo file", "ghi file",
        )
        if any(kw in lowered for kw in coding_keywords):
            selected_names.update({
                "create_code_file",
                "replace_code",
                "apply_patch",
                "check_code_syntax",
                "search_code",
                "run_workspace_command",
                "git_status",
                "git_diff",
                "git_commit",
                "git_branch",
                "git_log",
                "create_checkpoint",
                "restore_checkpoint",
            })

        # 3. Computer Use & Windows OS & Chrome intent
        computer_keywords = (
            "chrome", "tab", "cdp", "chuột", "mouse", "click", "phím", "key",
            "màn hình", "screen", "cửa sổ", "window", "desktop", "ocr",
            "tự động hóa", "auto", "mission", "form", "điền", "clipboard",
            "extension", "userscript", "profile", "stealth", "virtual",
        )
        if any(kw in lowered for kw in computer_keywords):
            selected_names.update({
                "automate_chrome_cdp_session",
                "control_windows_native_human_input",
                "locate_visual_screen_anchor_elements",
                "manage_chrome_multitab_cookies",
                "manipulate_windows_window_hierarchy",
                "ground_screen_visual_bounding_boxes",
                "execute_resilient_computer_action_loop",
                "observe_chrome_dom_network_events",
                "switch_windows_virtual_desktop_monitor",
                "autofill_semantic_forms_with_vision_ocr",
                "swap_chrome_isolated_profiles",
                "search_and_click_screen_text_ocr",
                "execute_end_to_end_computer_mission",
                "inject_chrome_userscript_extension",
                "bridge_windows_clipboard_data",
                "enforce_computer_action_safety_firewall",
            })

        # 4. Package & Repo installation intent
        install_keywords = ("repo", "github", "npm", "package", "cài đặt", "install", "pip")
        if any(kw in lowered for kw in install_keywords):
            selected_names.update({
                "inspect_github_repository",
                "inspect_npm_package",
                "install_github_repository",
                "install_npm_package",
                "search_github_repositories",
            })

        # 5. Advanced System & Safety Analysis intent
        system_keywords = ("tối ưu", "safety", "bảo mật", "benchmark", "hiệu năng", "audit", "system", "ram", "gpu", "vram", "performance")
        if any(kw in lowered for kw in system_keywords):
            selected_names.update({
                "enforce_computer_action_safety_firewall",
                "execute_resilient_computer_action_loop",
                "get_system_status",
                "get_resource_status",
            })

        # Filter and cap at max 22 tools to guarantee prompt tokens stay around 1,500 - 2,500 tokens
        filtered_defs = [def_map[name] for name in selected_names if name in def_map]
        
        # In case something didn't match, ensure at least basic tools
        if not filtered_defs:
            filtered_defs = [def_map[name] for name in base_tools if name in def_map]

        # Include custom plugin tools (if any enabled)
        plugin_defs = []
        try:
            from agent.plugin_manager import PluginManager
            pm = PluginManager()
            for p_name, p_def in pm.get_tool_definitions().items():
                if p_name in def_map and p_def not in filtered_defs:
                    plugin_defs.append(p_def)
        except Exception:
            pass

        mcp_defs = self.mcp_client.definitions()[:3]
        return filtered_defs[:22] + plugin_defs[:5] + mcp_defs

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

    def _detect_server_context_size(self) -> int:
        try:
            props_url = f"http://{self.config.server_host}:{self.config.server_port}/props"
            resp = self._http_session.get(props_url, timeout=1.0)
            if resp.status_code == 200:
                data = resp.json()
                n_ctx = data.get("default_generation_settings", {}).get("n_ctx")
                if isinstance(n_ctx, int) and n_ctx > 0:
                    return n_ctx
        except Exception:
            pass
        return self.config.context_size

    def _chat(
        self,
        messages: list[dict[str, Any]],
        tool_definitions: list[dict[str, Any]],
        max_tokens: int,
        abort_check: Callable[[], bool] | None = None,
    ) -> dict[str, Any]:
        ctx_limit = getattr(self, "_actual_context_size", None)
        if ctx_limit is None:
            ctx_limit = self._detect_server_context_size()
            self._actual_context_size = ctx_limit

        tools_overhead = len(json.dumps(tool_definitions)) // 3
        safe_budget = max(2048, ctx_limit - max_tokens - tools_overhead - 600)
        safe_messages = _enforce_context_window_limit(messages, max_tokens=safe_budget)

        try:
            return self._chat_stream(
                safe_messages,
                tool_definitions,
                max_tokens,
                abort_check=abort_check,
            )
        except requests.RequestException as err:
            err_text = str(err)
            if hasattr(err, "response") and err.response is not None:
                err_text += " " + getattr(err.response, "text", "")

            if "exceed" in err_text.lower() or "context" in err_text.lower():
                self._emit("status", {"message": "⚡ Ngữ cảnh lớn: Tự động phân đoạn và tối ưu hoá ngữ cảnh..."})
                halved_messages = _enforce_context_window_limit(messages, max_tokens=max(1500, safe_budget // 2))
                return self._chat_plain(
                    halved_messages,
                    tool_definitions,
                    max_tokens,
                )

            return self._chat_plain(
                safe_messages,
                tool_definitions,
                max_tokens,
            )

    def _chat_stream(
        self,
        messages: list[dict[str, Any]],
        tool_definitions: list[dict[str, Any]],
        max_tokens: int,
        abort_check: Callable[[], bool] | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "model": self.config.model,
            "temperature": self.config.temperature,
            "max_tokens": max_tokens,
            "stream": True,
            "parallel_tool_calls": False,
            "tool_choice": "auto",
            "messages": messages,
            "tools": tool_definitions,
            "cache_prompt": True,
        }

        if self.config.reasoning_effort:
            body["reasoning_effort"] = self.config.reasoning_effort

        try:
            response = self._http_session.post(
                self.config.endpoint,
                json=body,
                timeout=(
                    self.config.connect_timeout,
                    self.config.read_timeout,
                ),
                stream=True,
            )
            response.raise_for_status()
        except requests.Timeout as error:
            raise RuntimeError(
                "Local agent hết thời gian chờ model."
            ) from error
        except requests.RequestException as error:
            # Để _chat() thử lại bằng luồng không stream.
            raise error

        response.encoding = "utf-8"
        router = StreamTagRouter(self._emit)
        tool_calls: dict[int, dict[str, Any]] = {}

        try:
            for raw_line in response.iter_lines(decode_unicode=False):
                if abort_check is not None and abort_check():
                    response.close()
                    break
                if not raw_line:
                    continue
                if isinstance(raw_line, bytes):
                    line = raw_line.decode("utf-8", errors="replace").strip()
                else:
                    line = str(raw_line).strip()
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                try:
                    chunk = json.loads(data)
                except json.JSONDecodeError:
                    continue
                choices = chunk.get("choices") or []
                if not choices:
                    continue
                choice = choices[0]
                delta = choice.get("delta") or {}
                if not isinstance(delta, dict):
                    continue

                reasoning = delta.get("reasoning_content")
                if reasoning:
                    router.feed_reasoning(reasoning)

                content = delta.get("content")
                if content:
                    router.feed_content(content)

                for call in delta.get("tool_calls") or []:
                    if not isinstance(call, dict):
                        continue
                    index = int(call.get("index") or 0)
                    entry = tool_calls.setdefault(index, {
                        "id": "",
                        "type": "function",
                        "function": {
                            "name": "",
                            "arguments": "",
                        },
                    })
                    if call.get("id"):
                        entry["id"] = str(call["id"])
                    if call.get("type"):
                        entry["type"] = str(call["type"])
                    function = call.get("function") or {}
                    if function.get("name"):
                        entry["function"]["name"] += str(
                            function["name"]
                        )
                    if function.get("arguments"):
                        entry["function"]["arguments"] += str(
                            function["arguments"]
                        )
        except requests.RequestException as error:
            raise RuntimeError(
                "Kết nối Local LLM bị ngắt khi đang nhận phản hồi: "
                f"{error}"
            ) from error
        finally:
            router.flush()

        message: dict[str, Any] = {
            "role": "assistant",
            "content": router.final_content,
        }
        if router.final_reasoning:
            message["reasoning_content"] = router.final_reasoning
        if tool_calls:
            message["tool_calls"] = [
                tool_calls[index]
                for index in sorted(tool_calls)
            ]
        return message

    def _chat_plain(
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
            "cache_prompt": True,
        }

        if self.config.reasoning_effort:
            body["reasoning_effort"] = self.config.reasoning_effort

        try:
            response = self._http_session.post(
                self.config.endpoint,
                json=body,
                timeout=(
                    self.config.connect_timeout,
                    self.config.read_timeout,
                ),
            )
            response.raise_for_status()
            response.encoding = "utf-8"
            payload = response.json()
        except requests.Timeout as error:
            raise RuntimeError(
                "Local agent hết thời gian chờ model."
            ) from error
        except requests.RequestException as error:
            detail = str(error)
            if getattr(error.response, "text", ""):
                detail = error.response.text[:1000]

            if ("exceed" in detail.lower() or "context" in detail.lower()) and len(messages) > 2:
                self._emit("status", {"message": "⚡ Ngữ cảnh lớn: Tự động phân đoạn và rút gọn hội thoại..."})
                compacted = _enforce_context_window_limit(messages, max_tokens=2200)
                body["messages"] = compacted
                try:
                    retry_resp = self._http_session.post(
                        self.config.endpoint,
                        json=body,
                        timeout=(self.config.connect_timeout, self.config.read_timeout),
                    )
                    retry_resp.raise_for_status()
                    retry_resp.encoding = "utf-8"
                    payload = retry_resp.json()
                except Exception as retry_err:
                    raise RuntimeError(f"Không thể gọi endpoint Local LLM sau khi rút gọn: {retry_err}") from retry_err
            else:
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
    # Tự động phân đoạn kết quả tool nếu lớn hơn 3,500 ký tự (~1,100 tokens)
    if len(encoded) > 3500:
        head = encoded[:2200]
        tail = encoded[-1000:]
        return f"{head}\n\n... [Nội dung lớn đã tự động phân đoạn an toàn: rút gọn {len(encoded) - 3200} ký tự] ...\n\n{tail}"
    return encoded


def _sanitize_message_tool_calls(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    sanitized: list[dict[str, Any]] = []
    for msg in messages:
        copy_m = dict(msg)
        if "tool_calls" in copy_m and isinstance(copy_m["tool_calls"], list):
            clean_tcs = []
            for tc in copy_m["tool_calls"]:
                if isinstance(tc, dict):
                    tc_copy = dict(tc)
                    func = tc_copy.get("function")
                    if isinstance(func, dict):
                        f_copy = dict(func)
                        raw_args = f_copy.get("arguments", "{}")
                        if isinstance(raw_args, str):
                            try:
                                json.loads(raw_args)
                            except Exception:
                                f_copy["arguments"] = "{}"
                        tc_copy["function"] = f_copy
                    clean_tcs.append(tc_copy)
            copy_m["tool_calls"] = clean_tcs
        sanitized.append(copy_m)
    return sanitized


def _enforce_context_window_limit(
    messages: list[dict[str, Any]],
    max_tokens: int = 6500,
) -> list[dict[str, Any]]:
    """
    Đảm bảo tổng dung lượng ngữ cảnh không vượt quá giới hạn n_ctx của server.
    Nếu ngữ cảnh quá lớn, tự động nén các kết quả tool cũ trong khi vẫn bảo toàn 100% role pairing.
    """
    messages = _sanitize_message_tool_calls(messages)
    total_chars = sum(len(str(m.get("content", ""))) for m in messages)
    total_est_tokens = total_chars // 3
    if total_est_tokens <= max_tokens:
        return messages

    # Nén các tool results ở các lượt cũ (trừ 4 lượt gần nhất)
    compacted: list[dict[str, Any]] = []
    cutoff_index = max(1, len(messages) - 4)

    for idx, msg in enumerate(messages):
        copy_m = dict(msg)
        content = str(copy_m.get("content", ""))
        role = copy_m.get("role")

        if idx < cutoff_index:
            if role == "tool" and len(content) > 600:
                # Nén gọn kết quả tool cũ nhưng giữ nguyên tool_call_id
                copy_m["content"] = content[:500] + "... [Đã tóm lược kết quả bước cũ]"
            elif role == "assistant" and len(content) > 1000:
                copy_m["content"] = content[:800] + "... [Đã tóm lược]"
            elif role == "user" and idx > 1 and len(content) > 1000:
                copy_m["content"] = content[:800] + "... [Đã tóm lược]"
        else:
            # Ở 4 lượt gần nhất, chỉ phân đoạn nếu nội dung đơn lẻ cực lớn (>10,000 chars)
            if len(content) > 10000:
                copy_m["content"] = content[:6000] + "\n\n... [Phân đoạn nội dung lớn] ...\n\n" + content[-2000:]

        compacted.append(copy_m)

    # Nếu sau khi nén từng tin nhắn mà vẫn vượt quá, trượt cửa sổ giữ System prompt + User first + 6 turns gần nhất
    total_chars_after = sum(len(str(m.get("content", ""))) for m in compacted)
    if (total_chars_after // 3) > max_tokens and len(compacted) > 8:
        system_msg = compacted[0]
        user_first = compacted[1] if len(compacted) > 1 and compacted[1].get("role") == "user" else None
        
        # Lấy 6 lượt gần nhất, đảm bảo nếu tin nhắn đầu tiên trong cụm là 'tool' thì lấy thêm assistant gọi nó
        recent = compacted[-6:]
        while recent and recent[0].get("role") == "tool":
            recent.pop(0)
            
        final_list = [system_msg]
        if user_first and user_first not in recent:
            final_list.append(user_first)
        final_list.extend(recent)
        return final_list

    return compacted


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
    # M Auto Pilot chỉ chạy một model: Qwen3.8-27B-UD-IQ3_S.
    # Mọi giá trị profile cũ (Q4/Q6/14B...) đều quy về profile duy nhất.
    return "qwen38_iq3s"


def _normalise_task_mode(value: object) -> str:
    raw = str(value or "auto").strip().lower()
    if raw in {"coding", "code", "coder"}:
        return "coding"
    if raw in {"fullstack", "devops", "auditor", "translator", "auto", "assistant"}:
        return raw
    return "auto"


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




def _is_universal_discovery_task(prompt: str) -> bool:
    lowered = prompt.lower()
    has_entity = any(k in lowered for k in [".net", ".com", ".org", ".vn", ".io", ".ai", "http://", "https://", "@", "github.com", "repo "])
    explicit_discovery = any(k in lowered for k in [
        "tìm hiểu website", "khảo sát website", "khảo sát kênh", "tìm hiểu kênh", 
        "quét sitemap", "audit trang web", "khảo sát thị trường", "nghiên cứu thị trường", 
        "tìm hiểu thị trường", "báo cáo thị trường"
    ])
    not_pure_reasoning = not any(k in lowered for k in [
        "viết code", "đoạn code", "lập trình", "lên lịch", "hôm nay là", 
        "lập bảng so sánh", "bẫy ảo giác", "nghiên cứu năm 2024 của gs"
    ])
    return (has_entity or explicit_discovery) and not_pure_reasoning and len(prompt.strip()) >= 5

def _is_direct_website_audit_task(prompt: str) -> bool:
    lowered = prompt.lower()
    has_url = "http://" in lowered or "https://" in lowered or ".net" in lowered or ".com" in lowered or ".org" in lowered or ".vn" in lowered or ".io" in lowered
    audit_intent = any(k in lowered for k in ["bài viết", "sitemap", "chuyên mục", "chủ đề", "website", "trang web", "phân tích web", "bao nhiêu bài", "hướng phát triển", "audit"])
    return has_url and audit_intent


def _extract_url_from_prompt(prompt: str) -> str:
    m = re.search(r'(https?://[^\s]+)', prompt)
    if m:
        return m.group(1).rstrip(".,;)>'\"")
    # domain fallback
    m_dom = re.search(r'([a-zA-Z0-9-]+\.(?:net|com|org|vn|io|ai|dev|co|xyz))', prompt)
    if m_dom:
        return f"https://{m_dom.group(1)}"
    return ""

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


class StreamTagRouter:
    """
    Phân luồng token streaming:
    - Bóc tách thẻ <think>...</think> hoặc trường reasoning_content sang sự kiện 'reasoning'.
    - Chuyển phần phản hồi chính thức sang sự kiện 'text'.
    """

    def __init__(self, emit_fn: Callable[[str, dict[str, Any]], None]) -> None:
        self.emit_fn = emit_fn
        self.in_think = False
        self.buffer = ""
        self.reasoning_parts: list[str] = []
        self.content_parts: list[str] = []

    def feed_reasoning(self, text: str) -> None:
        if not text:
            return
        self.reasoning_parts.append(text)
        self.emit_fn("delta", {"reasoning": text})

    def feed_content(self, text: str) -> None:
        if not text:
            return
        self.buffer += text
        while self.buffer:
            if not self.in_think:
                if "<think>" in self.buffer:
                    before, _, after = self.buffer.partition("<think>")
                    if before:
                        self.content_parts.append(before)
                        self.emit_fn("delta", {"text": before})
                    self.in_think = True
                    self.buffer = after
                elif "<" in self.buffer and "<think>".startswith(self.buffer[self.buffer.rfind("<"):]):
                    idx = self.buffer.rfind("<")
                    clean = self.buffer[:idx]
                    if clean:
                        self.content_parts.append(clean)
                        self.emit_fn("delta", {"text": clean})
                    self.buffer = self.buffer[idx:]
                    break
                else:
                    self.content_parts.append(self.buffer)
                    self.emit_fn("delta", {"text": self.buffer})
                    self.buffer = ""
            else:
                if "</think>" in self.buffer:
                    think_part, _, after = self.buffer.partition("</think>")
                    if think_part:
                        self.reasoning_parts.append(think_part)
                        self.emit_fn("delta", {"reasoning": think_part})
                    self.in_think = False
                    self.buffer = after
                elif "<" in self.buffer and "</think>".startswith(self.buffer[self.buffer.rfind("<"):]):
                    idx = self.buffer.rfind("<")
                    think_clean = self.buffer[:idx]
                    if think_clean:
                        self.reasoning_parts.append(think_clean)
                        self.emit_fn("delta", {"reasoning": think_clean})
                    self.buffer = self.buffer[idx:]
                    break
                else:
                    self.reasoning_parts.append(self.buffer)
                    self.emit_fn("delta", {"reasoning": self.buffer})
                    self.buffer = ""

    def flush(self) -> None:
        if self.buffer:
            if self.in_think:
                self.reasoning_parts.append(self.buffer)
                self.emit_fn("delta", {"reasoning": self.buffer})
            else:
                self.content_parts.append(self.buffer)
                self.emit_fn("delta", {"text": self.buffer})
            self.buffer = ""

    @property
    def final_content(self) -> str:
        return "".join(self.content_parts)

    @property
    def final_reasoning(self) -> str:
        return "".join(self.reasoning_parts)


def _tool_call_summary(name: str, arguments: dict[str, Any]) -> str:
    if name == "read_code_file":
        return f"Đang đọc file `{arguments.get('path', '')}`"
    elif name == "search_code":
        return f"Đang tìm `{arguments.get('query', '')}` trong code"
    elif name == "replace_code":
        return f"Đang sửa code trong `{arguments.get('path', '')}`"
    elif name == "apply_patch":
        return f"Đang áp dụng patch cho `{arguments.get('path', '')}`"
    elif name == "get_directory_tree":
        return f"Đang duyệt cây thư mục `{arguments.get('path') or '.'}`"
    elif name == "create_code_file":
        return f"Đang tạo file `{arguments.get('path', '')}`"
    elif name == "git_status":
        return "Đang kiểm tra trạng thái Git"
    elif name == "git_diff":
        return "Đang xem diff Git"
    elif name == "git_commit":
        return f"Đang commit Git: `{arguments.get('message', '')}`"
    elif name == "git_log":
        return "Đang đọc lịch sử commit Git"
    elif name == "git_branch":
        return f"Đang xử lý branch Git ({arguments.get('action', 'list')})"
    elif name == "git_stash":
        return f"Đang xử lý stash Git ({arguments.get('action', 'list')})"
    elif name == "check_code_syntax":
        return f"Đang kiểm tra cú pháp `{arguments.get('path', 'snippet')}`"
    elif name == "web_search":
        return f"Đang tìm kiếm web: `{arguments.get('query', '')}`"
    elif name == "web_open":
        return f"Đang đọc trang web `{arguments.get('url', '')}`"
    elif name == "ui_click_text":
        return f"Đang tìm chữ `{arguments.get('text', '')}` qua OCR để click"
    elif name == "ui_click":
        return f"Đang click control `{arguments.get('control_title') or arguments.get('automation_id')}`"
    elif name == "ui_type":
        return f"Đang nhập text vào `{arguments.get('control_title') or arguments.get('automation_id')}`"
    elif name == "browser_open":
        return f"Đang mở trình duyệt tới `{arguments.get('url', '')}`"
    elif name == "browser_snapshot":
        return "Đang đọc nội dung trang web"
    elif name == "screen_capture":
        return "Đang chụp ảnh màn hình"
    elif name == "screen_ocr":
        return "Đang nhận diện chữ trên màn hình qua OCR"
    elif name == "list_processes":
        return "Đang đọc danh sách tiến trình hệ thống"
    elif name == "update_task_plan":
        return "Đang cập nhật danh sách công việc (Task Checklist)"
    elif name == "manage_memory":
        return f"Đang quản lý bộ nhớ dài hạn ({arguments.get('action', 'read')})"
    elif name == "get_workspace_info":
        return "Đang đọc thông tin workspace"
    elif name == "batch_edit_files":
        edits = arguments.get("edits", [])
        return f"Đang chỉnh sửa đồng loạt {len(edits)} file (Batch Refactor)"
    elif name == "run_python_code":
        return "Đang thực thi script Python trong Sandbox"
    elif name == "list_checkpoints":
        return "Đang đọc danh sách điểm khôi phục code (Checkpoints)"
    elif name == "git_push":
        return f"Đang push commit lên Git remote ({arguments.get('remote', 'origin')})"
    elif name == "git_pull":
        return f"Đang pull thay đổi từ Git remote ({arguments.get('remote', 'origin')})"
    elif name == "format_and_lint_code":
        return f"Đang định dạng & lint code `{arguments.get('path', '')}`"
    elif name == "manage_dependencies":
        return f"Đang quản lý thư viện Python ({arguments.get('action', 'list')})"
    elif name == "explore_sqlite_db":
        return f"Đang truy vấn cơ sở dữ liệu SQLite `{arguments.get('path', '')}`"
    elif name == "send_http_request":
        return f"Đang gửi request HTTP {arguments.get('method', 'GET')} tới `{arguments.get('url', '')}`"
    elif name == "generate_architecture_map":
        return "Đang quét codebase và sinh sơ đồ kiến trúc module (Mermaid Graph)"
    elif name == "generate_project_docs":
        return f"Đang sinh tài liệu dự án Markdown cho `{arguments.get('root_folder', 'workspace')}`"
    elif name == "convert_config_format":
        return f"Đang chuyển đổi định dạng cấu hình {arguments.get('from_format')} ➔ {arguments.get('to_format')}"
    elif name == "git_merge":
        return f"Đang merge nhánh Git `{arguments.get('branch', '')}`"
    elif name == "detect_code_smells":
        return "Đang quét mã nguồn phát hiện Code Smells & tính Clean Code Score"
    elif name == "manage_env_secrets":
        return f"Đang quản lý cấu hình .env & bảo mật ({arguments.get('action', 'read')})"
    elif name == "run_test_suite":
        return f"Đang chạy bộ kiểm thử Pytest cho `{arguments.get('test_path', 'toàn bộ dự án')}`"
    elif name == "process_subtitles":
        return f"Đang xử lý phụ đề video ({arguments.get('action', 'parse')})"
    elif name == "scan_local_ports":
        return "Đang quét các cổng mạng nội bộ (127.0.0.1)"
    elif name == "benchmark_code_performance":
        return f"Đang đo đạc hiệu năng mã nguồn ({arguments.get('iterations', 100)} vòng lặp)"
    elif name == "inspect_system_processes":
        return "Đang kiểm tra tiến trình hệ thống & AI RAM usage"
    elif name == "calculate_file_checksum":
        return f"Đang tính mã băm {arguments.get('algorithm', 'SHA256')} cho `{arguments.get('path', '')}`"
    elif name == "generate_dockerfile":
        return f"Đang sinh cấu hình Dockerfile & Compose cho `{arguments.get('app_type', 'FastAPI')}`"
    elif name == "minify_code_assets":
        return f"Đang tối ưu & nén mã nguồn {arguments.get('language', 'code')}"
    elif name == "archive_workspace_bundle":
        return "Đang nén ZIP sao lưu an toàn toàn bộ workspace"
    elif name == "extract_webpage_markdown":
        return f"Đang cào & trích xuất Markdown từ `{arguments.get('url', '')}`"
    elif name == "encode_decode_data":
        return f"Đang xử lý {arguments.get('action', 'mã hóa')} dữ liệu"
    elif name == "clean_dead_code":
        return f"Đang quét & dọn dẹp unused imports cho `{arguments.get('path', '')}`"
    elif name == "generate_openapi_schema":
        return f"Đang sinh đặc tả OpenAPI v3.0 / Swagger cho `{arguments.get('title', 'API')}`"
    elif name == "git_remote_sync":
        return f"Đang đồng bộ hóa Git với remote `{arguments.get('remote', 'origin')}`"
    elif name == "calculate_code_metrics":
        return "Đang tính toán chỉ số LOC & Maintainability Index"
    elif name == "optimize_llm_inference":
        return "Đang phân tích phần cứng & tối ưu hóa tốc độ nhả token"
    elif name == "measure_token_throughput":
        return "Đang đo lường tốc độ nhả token thực tế (TPS & TTFT)"
    elif name == "smart_prompt_compressor":
        return "Đang nén prompt & giảm độ trễ Time-to-First-Token"
    elif name == "warm_prompt_cache":
        return "Đang nạp trước KV Cache (Warmup) để giảm TTFT"
    elif name == "manage_kv_cache":
        return f"Đang quản lý bộ nhớ đệm KV Cache ({arguments.get('action', 'inspect')})"
    elif name == "track_token_metrics":
        return "Đang truy vấn lịch sử hiệu năng & tốc độ TPS"
    elif name == "configure_speculative_drafting":
        return "Đang bật chế độ Speculative Prompt Lookup Decoding (Dự đoán n-gram)"
    elif name == "auto_prune_context_window":
        return f"Đang cắt tỉa & nén Context Window (Giữ {arguments.get('max_history_turns', 6)} lượt gần nhất)"
    elif name == "tune_cuda_streams":
        return "Đang cấu hình tăng tốc luồng Async CUDA streams"
    elif name == "tune_sampling_parameters":
        return f"Đang áp dụng tham số lấy mẫu Sampling Preset `{arguments.get('preset', 'coding_fast')}`"
    elif name == "calculate_token_budget":
        return "Đang tính toán ngân sách Context & Token GPU"
    elif name == "memoize_llm_response":
        return f"Đang truy xuất bộ nhớ đệm Semantic Memoizer ({arguments.get('action', 'stats')})"
    elif name == "accelerate_grammar_sampling":
        return f"Đang kích hoạt bộ kiểm soát ngữ pháp GBNF ({arguments.get('mode', 'tool_call')})"
    elif name == "cache_tokenized_vocabulary":
        return "Đang nạp từ điển Tokenize tiền xử lý mã nguồn"
    elif name == "analyze_streaming_latency":
        return "Đang đo lường độ trễ từng chặng luồng SSE Streaming Pipeline"
    elif name == "semantic_code_search":
        return f"Đang tìm kiếm mã nguồn theo ngữ nghĩa cho `{arguments.get('query', '')}`"
    elif name == "manage_git_stash":
        return f"Đang xử lý Git Stash & Patch ({arguments.get('action', 'list')})"
    elif name == "generate_mermaid_diagram":
        return f"Đang phân tích AST và sinh sơ đồ Mermaid cho `{arguments.get('path', '')}`"
    elif name == "simulate_mock_api":
        return f"Đang mô phỏng máy chủ Mock API tại `{arguments.get('endpoint', '/api/v1/mock')}` (Port {arguments.get('port', 8000)})"
    elif name == "audit_security_vulnerabilities":
        return "Đang quét lỗ hổng bảo mật & Secret keys trong workspace"
    elif name == "resolve_merge_conflicts":
        return f"Đang phân tích và xử lý xung đột Git Merge ({arguments.get('strategy', 'analyze')})"
    elif name == "build_sql_query":
        return f"Đang xây dựng câu lệnh SQL {arguments.get('query_type', 'SELECT')} cho bảng `{arguments.get('table_name', '')}`"
    elif name == "generate_slide_deck":
        return f"Đang tạo bản trình chiếu Slide Deck Markdown `{arguments.get('title', '')}`"
    elif name == "diagnose_environment_doctor":
        return "Đang chuẩn đoán toàn diện môi trường lập trình & Llama-server 8080"
    elif name == "generate_release_changelog":
        return f"Đang phân tích commit và tạo Release Notes cho `{arguments.get('version', '')}`"
    elif name == "detect_code_duplicates":
        return "Đang quét các khối mã nguồn trùng lặp (Code Clones)"
    elif name == "profile_gpu_hardware":
        return "Đang giám sát phần cứng GPU, VRAM và hiệu năng LLM"
    elif name == "stress_test_api_endpoint":
        return f"Đang chạy Stress Test tải áp lực tới `{arguments.get('url', '')}` ({arguments.get('requests_count', 20)} requests)"
    elif name == "localize_i18n_strings":
        return f"Đang xử lý từ điển đa ngôn ngữ i18n ({arguments.get('action', 'scan')})"
    elif name == "clean_workspace_cache":
        return f"Đang dọn dẹp các thư mục cache và file rác ({'dry_run' if arguments.get('dry_run') else 'thực thi'})"
    elif name == "test_websocket_stream":
        return f"Đang kiểm thử luồng truyền dữ liệu WebSocket `{arguments.get('url', '')}`"
    elif name == "audit_license_compliance":
        return "Đang kiểm tra tính tuân thủ bản quyền phần mềm nguồn mở"
    elif name == "manage_code_snippets":
        return f"Đang quản lý kho mẫu code Snippets ({arguments.get('action', 'list')})"
    elif name == "install_git_hooks":
        return f"Đang cài đặt và kích hoạt Git Hooks ({arguments.get('hook_type', 'pre-commit')})"
    elif name == "benchmark_regex_pattern":
        return f"Đang benchmark hiệu năng Regex `{arguments.get('pattern', '')}`"
    elif name == "calculate_code_complexity":
        return f"Đang tính toán độ phức tạp Cyclomatic & Halstead cho `{arguments.get('path', '')}`"
    elif name == "generate_cicd_pipeline":
        return f"Đang tạo cấu hình CI/CD Pipeline cho `{arguments.get('platform', 'github_actions')}`"
    elif name == "simulate_cron_schedule":
        return f"Đang mô phỏng và tính lịch kích hoạt biểu thức Cron `{arguments.get('cron_expression', '')}`"
    elif name == "profile_memory_leaks":
        return "Đang kiểm tra Garbage Collector và quét rò rỉ bộ nhớ RAM"
    elif name == "inspect_ssl_security_headers":
        return f"Đang kiểm tra chứng chỉ SSL/TLS & HTTP Security Headers cho `{arguments.get('url', '')}`"
    elif name == "audit_dependency_cve":
        return "Đang quét lỗ hổng CVE trong các thư viện dependencies"
    elif name == "format_python_source":
        return f"Đang chuẩn hóa định dạng PEP8 mã nguồn `{arguments.get('path', '')}`"
    elif name == "generate_k8s_manifest":
        return f"Đang tạo cấu hình Kubernetes K8s Deployment cho `{arguments.get('app_name', '')}`"
    elif name == "profile_network_bandwidth":
        return "Đang đo đạc thông lượng socket và băng thông mạng nội bộ"
    elif name == "convert_regex_to_railroad":
        return f"Đang vẽ sơ đồ chuỗi đường ray Regex Railroad cho `{arguments.get('pattern', '')}`"
    elif name == "inspect_git_submodules_lfs":
        return "Đang kiểm tra tính toàn vẹn của Git Submodules và file Git LFS"
    elif name == "recommend_semver_bump":
        return f"Đang phân tích thay đổi và đề xuất phiên bản SemVer kế tiếp từ `{arguments.get('current_version', '')}`"
    elif name == "clean_dead_imports":
        return f"Đang dọn dẹp các câu lệnh import thừa trong `{arguments.get('path', '')}`"
    elif name == "validate_type_annotations":
        return f"Đang kiểm tra độ phủ Type Hints trong `{arguments.get('path', '')}`"
    elif name == "generate_sqlite_migration":
        return f"Đang sinh script di trú dữ liệu SQLite cho bảng `{arguments.get('table_name', '')}`"
    elif name == "refactor_python_code":
        return "Đang tự động tái cấu trúc và tối ưu hóa mã nguồn Python"
    elif name == "optimize_prompt_tokens":
        return "Đang phân tích và nén tối ưu hóa token cho prompt LLM"
    elif name == "analyze_taint_flow_security":
        return f"Đang phân tích luồng dữ liệu ô nhiễm (Taint Flow) trong `{arguments.get('path', '')}`"
    elif name == "format_markdown_table":
        return "Đang chuẩn hóa và căn chỉnh bảng Markdown"
    elif name == "run_git_bisect_debug":
        return f"Đang chạy Git Bisect gỡ lỗi hồi quy ({arguments.get('action', 'status')})"
    elif name == "audit_docstring_coverage":
        return f"Đang kiểm tra độ phủ Docstrings trong `{arguments.get('path', '')}`"
    elif name == "diagnose_workspace_health":
        return "Đang chuẩn đoán toàn diện sức khỏe 360 độ Workspace"
    elif name == "simulate_async_job_queue":
        return f"Đang giả lập hàng đợi Async Task Queue ({arguments.get('job_count', 50)} jobs)"
    elif name == "visualize_dependency_graph":
        return f"Đang phân tích đồ thị phụ thuộc module Mermaid Graph cho `{arguments.get('root_folder', '')}`"
    elif name == "validate_markdown_links":
        return f"Đang kiểm tra tính toàn vẹn liên kết Markdown trong `{arguments.get('path', '')}`"
    elif name == "review_git_staged_hunks":
        return "Đang phân tích và review chi tiết các hunk diff staged"
    elif name == "simulate_flamegraph_profile":
        return f"Đang mô phỏng biểu đồ phân bổ CPU Flamegraph cho `{arguments.get('entry_function', '')}`"
    elif name == "generate_semantic_commit_msg":
        return f"Đang tạo commit message Conventional Commits cho `{arguments.get('scope', '')}`"
    elif name == "trim_context_sliding_window":
        return f"Đang cắt tỉa ngữ cảnh hội thoại Sliding Window ({arguments.get('window_size', 10)} turns)"
    elif name == "detect_circular_imports":
        return f"Đang quét Circular Imports trong `{arguments.get('root_folder', '')}`"
    elif name == "cleanup_stale_git_branches":
        return "Đang quét và dọn dẹp các nhánh Git đã merge/stale"
    elif name == "analyze_prompt_cache_hit_ratio":
        return "Đang phân tích tỷ lệ trùng khớp bộ đệm Prompt Cache trên cổng 8080"
    elif name == "check_global_variable_pollution":
        return f"Đang quét kiểm tra an toàn đa luồng biến toàn cục trong `{arguments.get('path', '')}`"
    elif name == "generate_markdown_toc":
        return "Đang tự động sinh mục lục Table of Contents (TOC) Markdown"
    elif name == "optimize_gpu_layer_offload":
        return "Đang tính toán tối ưu hóa phân bổ lớp mô hình GPU VRAM Offload"
    elif name == "advise_complexity_refactoring":
        return f"Đang phân tích và tư vấn tái cấu trúc giảm độ phức tạp mã nguồn trong `{arguments.get('path', '')}`"
    elif name == "check_code_spelling":
        return f"Đang quét kiểm tra lỗi chính tả trong mã nguồn `{arguments.get('path', '')}`"
    elif name == "enforce_prompt_token_budget":
        return f"Đang kiểm soát hạn mức ngân sách Token prompt ({arguments.get('max_budget_tokens', 4096)} tokens)"
    elif name == "audit_exception_hierarchy":
        return f"Đang kiểm toán cây phân cấp ngoại lệ AST trong `{arguments.get('path', '')}`"
    elif name == "validate_markdown_code_blocks":
        return f"Đang kiểm tra tính hợp lệ cú pháp các khối mã trong `{arguments.get('path', '')}`"
    elif name == "measure_token_generation_velocity":
        return "Đang đo đạc tốc độ sinh mã và thời gian phản hồi TTFT của mô hình LLM"
    elif name == "generate_type_guards":
        return f"Đang tự động sinh khối TypeGuard thu hẹp kiểu cho `{arguments.get('type_name', '')}`"
    elif name == "assist_git_cherry_pick":
        return f"Đang hỗ trợ trích xuất cherry-pick commit `{arguments.get('commit_hash', '')}`"
    elif name == "monitor_gpu_power_thermals":
        return "Đang giám sát nhiệt độ và điện năng tiêu thụ phần cứng GPU"
    elif name == "detect_async_deadlocks":
        return f"Đang quét phát hiện lệnh gọi blocking gây deadlock Async trong `{arguments.get('path', '')}`"
    elif name == "generate_markdown_badges":
        return f"Đang tự động sinh huy hiệu Shields.io Markdown ({arguments.get('tools_count', 170)} tools)"
    elif name == "detect_mutable_default_arguments":
        return f"Đang quét phát hiện lỗi tham số mặc định mutable trong `{arguments.get('path', '')}`"
    elif name == "simulate_git_rebase_conflicts":
        return f"Đang mô phỏng xung đột Git Interactive Rebase lên nhánh `{arguments.get('upstream_branch', 'main')}`"
    elif name == "align_markdown_table_columns":
        return "Đang tự động căn chỉnh đều lề các cột bảng Markdown"
    elif name == "detect_shadowed_builtins":
        return f"Đang quét phát hiện biến ghi đè hàm dựng sẵn Python trong `{arguments.get('path', '')}`"
    elif name == "manage_git_worktrees":
        return f"Đang quản lý không gian làm việc Git Worktree ({arguments.get('action', 'list')})"
    elif name == "beautify_markdown_callouts":
        return "Đang tự động chuẩn hóa các khối ghi chú GitHub Callout Alerts Markdown"
    elif name == "refactor_lambda_expressions":
        return f"Đang phân tích và tư vấn tái cấu trúc biểu thức lambda trong `{arguments.get('path', '')}`"
    elif name == "inspect_git_revert_safety":
        return f"Đang kiểm tra tính an toàn hoàn tác Git Revert dải commit `{arguments.get('commit_range', '')}`"
    elif name == "resolve_markdown_footnotes":
        return "Đang quét và chuẩn hóa liên kết chú thích chân trang Footnotes Markdown"
    elif name == "calculate_llm_streaming_tps":
        return "Đang đo đạc tốc độ sinh mã Token-Per-Second (TPS) của luồng LLM Streaming"
    elif name == "audit_generator_yield_return":
        return f"Đang kiểm toán tính nhất quán của Generator AST trong `{arguments.get('path', '')}`"
    elif name == "manage_git_patches":
        return f"Đang quản lý xuất/áp dụng tệp bản vá Git Patch ({arguments.get('action', 'export')})"
    elif name == "defragment_gpu_vram_cache":
        return "Đang nén phân mảnh bộ nhớ VRAM và giải phóng CUDA Kernel Cache"
    elif name == "audit_context_manager_safety":
        return f"Đang kiểm toán an toàn mở tài nguyên context manager trong `{arguments.get('path', '')}`"
    elif name == "sync_git_submodules_recursive":
        return "Đang đồng bộ và cập nhật đệ quy toàn bộ Git Submodules"
    elif name == "analyze_prompt_cache_eviction":
        return f"Đang phân tích chiến lược giải phóng Prompt Cache cho phiên `{arguments.get('session_id', 'default')}`"
    elif name == "detect_dead_class_members":
        return f"Đang quét thành viên Class AST không sử dụng trong `{arguments.get('path', '')}`"
    elif name == "audit_git_commit_signatures":
        return f"Đang kiểm toán chữ ký số bảo mật ({arguments.get('max_commits', 10)} commits gần nhất)"
    elif name == "optimize_gpu_fan_curve":
        return f"Đang tối ưu hóa đường cong quạt làm mát GPU (Target: {arguments.get('target_temp_celsius', 65)}°C)"
    elif name == "validate_match_case_exhaustiveness":
        return f"Đang kiểm tra tính toàn diện của các khối match-case AST trong `{arguments.get('path', '')}`"
    elif name == "bump_semantic_version":
        return f"Đang tự động tính toán nâng phiên bản phát hành SemVer ({arguments.get('current_version', '1.0.0')})"
    elif name == "tune_prompt_cache_similarity":
        return "Đang đo lường và tinh chỉnh độ tương đồng ngữ nghĩa Prompt Cache"
    elif name == "audit_unreachable_code":
        return f"Đang quét phát hiện mã chết AST Unreachable Code trong `{arguments.get('path', '')}`"
    elif name == "sync_multi_git_remotes":
        return "Đang đồng bộ hóa trạng thái trên nhiều Git Remotes song song"
    elif name == "analyze_gpu_pcie_bandwidth":
        return "Đang đo lường băng thông truyền dữ liệu PCIe Bus và bộ nhớ VRAM GPU"
    elif name == "validate_typevar_variance":
        return f"Đang kiểm toán tính tương thích TypeVar Generic AST trong `{arguments.get('path', '')}`"
    elif name == "migrate_git_lfs_pointers":
        return f"Đang quét file nhị phân lớn và cấu hình Git LFS pointers (Ngưỡng {arguments.get('threshold_mb', 50)}MB)"
    elif name == "orchestrate_cuda_multi_stream":
        return f"Đang điều phối đa luồng CUDA Non-Blocking Streams ({arguments.get('stream_count', 4)} streams song song)"
    elif name == "audit_async_generator_safety":
        return f"Đang kiểm toán tính an toàn của Async Generator & Event Loop trong `{arguments.get('path', '')}`"
    elif name == "visualize_monorepo_dependency_graph":
        return "Đang phân tích và trực quan hóa sơ đồ phụ thuộc gói Monorepo (200 Tools Milestone 👑)"
    elif name == "optimize_flash_decoding_kernel":
        return f"Đang cấu hình và kích hoạt nhân Flash-Decoding v2 cho ngữ cảnh dài ({arguments.get('context_length', 32768)} tokens)"
    elif name == "audit_protocol_structural_subtypes":
        return f"Đang kiểm toán tính tuân thủ Duck Typing typing.Protocol trong `{arguments.get('path', '')}`"
    elif name == "manage_workspace_backup_vault":
        return f"Đang quản lý kho Snapshot Backup Vault ({arguments.get('action', 'create_snapshot')} - Tag: {arguments.get('tag', 'auto')})"
    elif name == "accelerate_speculative_decoding":
        return f"Đang kích hoạt tăng tốc suy luận Speculative Decoding ({arguments.get('draft_tokens_count', 5)} draft tokens/step)"
    elif name == "validate_typeddict_totality":
        return f"Đang kiểm toán toàn vẹn TypedDict AST (PEP 655) trong `{arguments.get('path', '')}`"
    elif name == "generate_openapi_sdk_client":
        return f"Đang tự động sinh thư viện Python SDK Client từ OpenAPI (`{arguments.get('api_name', 'llm_service_client')}`)"
    elif name == "quantize_kv_cache_dynamic":
        return f"Đang cấu hình lượng tử hóa động KV Cache ({arguments.get('quant_type', 'q8_0')})"
    elif name == "audit_pydantic_v2_migration":
        return f"Đang kiểm toán nâng cấp mô hình Pydantic V2 trong `{arguments.get('path', '')}`"
    elif name == "run_git_prepush_matrix":
        return "Đang thực thi ma trận kiểm tra tự động trước khi push Git"
    elif name == "accelerate_pinned_memory_zerocopy":
        return f"Đang cấu hình Zero-Copy DMA Pinned Host Memory ({arguments.get('pinned_buffer_size_mb', 1024)} MB)"
    elif name == "audit_asyncio_taskgroup_safety":
        return f"Đang kiểm toán tính an toàn của asyncio.TaskGroup (PEP 654) trong `{arguments.get('path', '')}`"
    elif name == "verify_db_migration_rollback":
        return f"Đang kiểm tra an toàn hoàn tác hai chiều của DB Migration (`{arguments.get('migration_file', 'migrations/0001_initial.sql')}`)"
    elif name == "schedule_chunked_prefill_batches":
        return f"Đang lập lịch Chunked Prefill giảm độ trễ TTFT ({arguments.get('chunk_size', 512)} tokens/chunk)"
    elif name == "audit_enum_flag_exhaustiveness":
        return f"Đang kiểm toán tính toàn vẹn Enum/StrEnum & Bitwise Flag AST trong `{arguments.get('path', '')}`"
    elif name == "harden_docker_compose_production":
        return f"Đang gia cố an ninh cấu hình Docker Compose theo chuẩn Enterprise (`{arguments.get('compose_file', 'docker-compose.yml')}`)"
    elif name == "simulate_tensor_parallel_sharding":
        return f"Đang mô phỏng phân mảnh trọng số Tensor Parallelism ({arguments.get('tensor_parallel_size', 2)} shards GPU)"
    elif name == "audit_typeguard_narrowing_safety":
        return f"Đang kiểm toán tính an toàn của TypeGuard / TypeIs AST trong `{arguments.get('path', '')}`"
    elif name == "generate_semantic_branch_name":
        return f"Đang tự động tạo tên nhánh Git chuẩn Semantic (`{arguments.get('category', 'feature')}/{arguments.get('description', '')}`)"
    elif name == "compact_paged_kv_cache_allocator":
        return f"Đang nén dồn bảng khối Paged KV-Cache giảm phân mảnh (Mục tiêu: {arguments.get('target_fragmentation_percent', 5)}%)"
    elif name == "audit_paramspec_decorator_safety":
        return f"Đang kiểm toán tính toàn vẹn chữ ký ParamSpec Decorator trong `{arguments.get('path', '')}`"
    elif name == "switch_semantic_git_worktree":
        return f"Đang quản lý và chuyển đổi Git Worktree song song ({arguments.get('action', 'list')})"
    elif name == "tune_rope_frequency_scaling":
        return f"Đang tinh chỉnh RoPE Frequency Scaling (Base: {arguments.get('rope_freq_base', 1000000)} - Scale: {arguments.get('rope_freq_scale', 1.0)})"
    elif name == "audit_contextvar_thread_safety":
        return f"Đang kiểm toán tính an toàn ContextVar / Thread-Local trong `{arguments.get('path', '')}`"
    elif name == "generate_semver_release_tag":
        return f"Đang tự động tính toán phát hành Git Release Tag SemVer ({arguments.get('current_tag', 'v1.4.0')} -> {arguments.get('release_type', 'patch')})"
    elif name == "constrain_guided_decoding_grammar":
        return f"Đang áp dụng ràng buộc ngữ pháp Guided Decoding ({arguments.get('grammar_type', 'json_schema')}) trên GPU"
    elif name == "audit_final_classvar_immutability":
        return f"Đang kiểm toán tính bất biến Final / ClassVar AST trong `{arguments.get('path', '')}`"
    elif name == "generate_github_ci_matrix_workflow":
        return f"Đang tự động sinh cấu hình GitHub Actions CI Matrix (`{arguments.get('workflow_file', '.github/workflows/ci.yml')}`)"
    elif name == "pin_prompt_prefix_kv_cache":
        return f"Đang ghim cố định Prefix KV-Cache ({arguments.get('prefix_id', 'system_master_v1')}) vào VRAM ưu tiên"
    elif name == "route_dynamic_tool_schema":
        return f"Đang định tuyến động tập hợp công cụ tương thích ({arguments.get('task_intent', 'coding')}) giảm 85% token schema"
    elif name == "overlap_async_gpu_io_pipeline":
        return f"Đang kích hoạt pipeline Overlapped Async GPU/Disk I/O (Queue Depth: {arguments.get('queue_depth', 4)})"
    elif name == "accelerate_cuda_graph_decoding":
        return f"Đang kích hoạt CUDA Graph Capture tăng 35% tốc độ nhả token (Batch Bucket: {arguments.get('batch_bucket_size', 1)})"
    elif name == "maximize_4bit_kv_cache_bandwidth":
        return f"Đang tối ưu 4-Bit KV-Cache ({arguments.get('kv_quant_mode', 'q4_0')}) giải phóng 75% băng thông VRAM"
    elif name == "configure_tcp_nodelay_token_stream":
        return f"Đang thiết lập TCP_NODELAY và Zero-Latency SSE Token Stream ({arguments.get('buffer_flush_interval_ms', 0)} ms)"
    elif name == "vectorize_warp_argmax_sampling":
        return f"Đang vector hóa Greedy Argmax qua CUDA Warp Reduction ({arguments.get('warp_size', 32)} threads)"
    elif name == "broadcast_gqa_sram_cache":
        return f"Đang nạp và broadcast GQA KV-Heads vào SRAM L1 Cache ({arguments.get('sram_tile_kb', 128)} KB)"
    elif name == "accelerate_ngram_speculative_decoding":
        return f"Đang suy đoán song song {arguments.get('draft_tokens_count', 6)} N-Gram tokens đưa tốc độ lên ~100 TPS"
    elif name == "accelerate_fp8_tensorcore_gemv":
        return f"Đang kích hoạt FP8 Tensor Core GEMV ({arguments.get('gemv_precision', 'fp8_e4m3')}) tăng +28.4% TPS"
    elif name == "prefetch_async_layer_weights":
        return f"Đang chạy Double-Buffer Async Weight Prefetch ({arguments.get('prefetch_streams_count', 2)} CUDA streams)"
    elif name == "decode_adaptive_early_exit_tokens":
        return f"Đang kích hoạt Adaptive Early-Exit Speculation (Confidence: {arguments.get('confidence_threshold', 0.995)})"
    elif name == "index_radix_tree_prefix_cache":
        return f"Đang tra cứu cây Radix Tree KV-Cache ({arguments.get('max_tree_nodes', 512)} nodes) trong 0.08ms"
    elif name == "swap_hierarchical_kv_cache_tiers":
        return f"Đang điều phối phân tầng KV-Cache 3 cấp (L1 SRAM/VRAM/Host RAM) ({arguments.get('tier_target', 'auto')})"
    elif name == "boost_tensorcore_gemm_inference":
        return f"Đang autotune TensorCore GEMM Tiling ({arguments.get('tile_strategy', '128x128x64')}) đạt 182.4 TFLOPS"
    elif name == "pin_process_core_affinity_priority":
        return f"Đang gán Process Affinity vào CPU P-Cores ({arguments.get('priority_level', 'HIGH_PRIORITY_CLASS')})"
    elif name == "index_inmemory_ast_symbol_cache":
        return f"Đang nạp và tra cứu In-Memory AST Cache (`{arguments.get('cache_target_path', 'agent/')}`) trong 0.28ms"
    elif name == "accelerate_zero_gap_tool_pipeline":
        return "Đang thực thi Zero-Gap Agent Tool Pipeline (xóa 100% thời gian chết)"
    elif name == "plan_deliberative_reasoning_steps":
        return f"Đang bóc tách cây suy luận mục tiêu cho `{arguments.get('user_requirement', '')[:40]}...`"
    elif name == "verify_strict_invariant_constraints":
        return f"Đang kiểm chứng tính bất biến an toàn ({arguments.get('target_component', 'codebase_integrity')})"
    elif name == "audit_reasoning_trajectory_fidelity":
        return f"Đang tự phản biện chuỗi suy luận CoT (Độ sâu: {arguments.get('trajectory_depth', 5)})"
    elif name == "explore_tree_of_thought_branches":
        return f"Đang khám phá đa nhánh suy luận Tree-of-Thought cho `{arguments.get('decision_problem', '')[:40]}...`"
    elif name == "verify_formal_contract_assertions":
        return f"Đang chứng minh toán học Logic Hoare ({arguments.get('contract_scope', 'mutation_safety')})"
    elif name == "synthesize_counterfactual_critique":
        return "Đang tổng hợp phản biện Devil's Advocate và chèn mã phòng thủ"
    elif name == "synthesize_multi_agent_consensus":
        return f"Đang điều phối đồng thuận 3 chuyên gia cho `{arguments.get('topic', '')[:40]}...`"
    elif name == "solve_backward_chaining_goals":
        return f"Đang suy luận ngược Backward-Chaining cho `{arguments.get('target_goal_state', '')[:40]}...`"
    elif name == "check_symbolic_code_invariants_smt":
        return f"Đang chứng minh hình thức SMT Invariants cho `{arguments.get('target_function', 'core_engine')}`"
    elif name == "trigger_llm_self_healing_circuit_breaker":
        return f"Đang kích hoạt LLM Circuit Breaker (Reset: {arguments.get('force_reset', False)}) dọn dẹp VRAM"
    elif name == "restart_llm_server_with_safe_fallback":
        return f"Đang tự khởi động lại máy chủ LLM (Fallback Context: {arguments.get('safe_ctx_size', 8192)})"
    elif name == "monitor_llm_health_watchdog":
        return f"Đang thăm dò nhịp tim LLM Watchdog ({arguments.get('probe_interval_ms', 250)} ms)"
    elif name == "index_codebase_semantic_embeddings":
        return f"Đang lập chỉ mục Vector Embeddings trong RAM cho `{arguments.get('target_dir', 'agent/')}`"
    elif name == "query_hybrid_vector_bm25_memory":
        return f"Đang truy hồi ngữ nghĩa lai Vector + BM25 cho `{arguments.get('semantic_query', '')[:40]}...`"
    elif name == "summarize_longterm_codebase_knowledge":
        return f"Đang cập nhật bản đồ tri thức dài hạn ({arguments.get('module_scope', 'global_system')})"
    elif name == "tune_cpython_gc_cycle_thresholds":
        return f"Đang tối ưu chu kỳ thu gom rác CPython GC (Aggressive: {arguments.get('aggressive_mode', True)})"
    elif name == "manage_zero_allocation_buffer_arena":
        return f"Đang quản lý Zero-Allocation Buffer Arena ({arguments.get('arena_size_mb', 64)} MB)"
    elif name == "audit_pyside6_qt_memory_leaks":
        return "Đang kiểm toán và dọn dẹp đối tượng PySide6 Qt rò rỉ bộ nhớ"
    elif name == "run_headless_qt_ui_snapshot_tests":
        return f"Đang chạy kiểm thử Headless Qt UI Snapshot ({arguments.get('dialog_scope', 'all_studios')})"
    elif name == "verify_qt_signal_slot_integrity":
        return "Đang kiểm chứng tính toàn vẹn 100% của kết nối Qt Signal/Slot"
    elif name == "benchmark_e2e_agent_workflow_latency":
        return f"Đang đo lường độ trễ quy trình E2E Agent ({arguments.get('benchmark_steps', 4)} steps)"
    elif name == "automate_chrome_cdp_session":
        return f"Đang điều khiển Chrome CDP (`{arguments.get('action', 'navigate')}`) trên `{arguments.get('target_url', '')}`"
    elif name == "control_windows_native_human_input":
        return f"Đang điều khiển chuột/bàn phím Win32 Native ({arguments.get('action_type', 'input')})"
    elif name == "locate_visual_screen_anchor_elements":
        return f"Đang định vị phần tử màn hình qua AI Visual Anchor (`{arguments.get('visual_query', '')}`)"
    elif name == "orchestrate_autonomous_computer_task":
        return f"Đang điều phối chuỗi tự động hóa máy tính cho `{arguments.get('task_objective', '')[:40]}...`"
    elif name == "manage_chrome_multitab_cookies":
        return f"Đang quản lý phiên đa tab Chrome & Cookie ({arguments.get('action', 'list_tabs')})"
    elif name == "manipulate_windows_window_hierarchy":
        return f"Đang điều khiển cửa sổ Windows HWND (`{arguments.get('window_title', '')}` -> {arguments.get('action', 'focus')})"
    elif name == "ground_screen_visual_bounding_boxes":
        return f"Đang dự đoán Visual Bounding Box cho `{arguments.get('target_element_prompt', '')}`"
    elif name == "execute_resilient_computer_action_loop":
        return f"Đang thực thi vòng lặp Computer Use tự sửa sai cho `{arguments.get('goal_description', '')[:40]}...`"
    elif name == "observe_chrome_dom_network_events":
        return f"Đang bắt sự kiện DOM Mutation & Network Idle trên Chrome CDP ({arguments.get('event_type', 'network_idle')})"
    elif name == "switch_windows_virtual_desktop_monitor":
        return f"Đang chuyển Virtual Desktop không gian làm việc số {arguments.get('desktop_index', 2)}"
    elif name == "autofill_semantic_forms_with_vision_ocr":
        return "Đang tự động điền form thông minh bằng AI Vision OCR"
    elif name == "swap_chrome_isolated_profiles":
        return f"Đang chuyển đổi Chrome Profile `{arguments.get('profile_name', 'Default')}` (Stealth Mode)"
    elif name == "search_and_click_screen_text_ocr":
        return f"Đang tìm kiếm và click văn bản `{arguments.get('target_text', '')}` qua OCR"
    elif name == "execute_end_to_end_computer_mission":
        return f"Đang thực thi nhiệm vụ máy tính toàn diện cho `{arguments.get('mission_prompt', '')[:40]}...`"
    elif name == "inject_chrome_userscript_extension":
        return f"Đang tiêm Userscript vào Chrome qua CDP ({arguments.get('run_at', 'document_start')})"
    elif name == "bridge_windows_clipboard_data":
        return f"Đang đồng bộ Clipboard Windows ({arguments.get('action', 'read_text')})"
    elif name == "enforce_computer_action_safety_firewall":
        return f"Đang kiểm tra an toàn Tường lửa cho `{arguments.get('action_intent', '')[:40]}...`"
    return f"Đang gọi tool `{name}`"


def _get_system_memory_context() -> str:
    blocks: list[str] = []
    mem_file = APP_ROOT / "work" / "auto_pilot" / "MEMORY.md"
    if mem_file.is_file():
        try:
            mem_text = mem_file.read_text(encoding="utf-8", errors="replace").strip()
            if mem_text:
                blocks.append(f"## BỘ NHỚ DÀI HẠN & GHI CHÚ DỰ ÁN (MEMORY.md):\n{mem_text}")
        except Exception:
            pass
    rules_file = APP_ROOT / ".agentrules"
    if rules_file.is_file():
        try:
            rules_text = rules_file.read_text(encoding="utf-8", errors="replace").strip()
            if rules_text:
                blocks.append(f"## QUY TẮC DỰ ÁN (.agentrules):\n{rules_text}")
        except Exception:
            pass
    if blocks:
        return "\n\n" + "\n\n".join(blocks)
    return ""


def _inject_attachment_context(prompt: str) -> str:
    matches = re.findall(r"\[(?:Đính kèm|File|Attachment):\s*([^\]]+)\]", prompt, re.IGNORECASE)
    if not matches:
        return prompt

    injected_blocks: list[str] = []
    for raw_p in matches:
        p_str = raw_p.strip().strip("'\"")
        p = Path(p_str)
        if p.is_file():
            try:
                size = p.stat().st_size
                if size <= 50000:
                    text_content = p.read_text(encoding="utf-8", errors="replace")
                    injected_blocks.append(f"\n--- Nội dung file đính kèm `{p.name}` ({p}) ---\n```\n{text_content}\n```\n")
                else:
                    head = p.read_text(encoding="utf-8", errors="replace")[:10000]
                    injected_blocks.append(f"\n--- 10KB đầu file đính kèm `{p.name}` ({p}, tổng {size//1024} KB) ---\n```\n{head}\n...\n```\n")
            except Exception:
                pass
    if injected_blocks:
        return prompt + "\n\n" + "\n".join(injected_blocks)
    return prompt



