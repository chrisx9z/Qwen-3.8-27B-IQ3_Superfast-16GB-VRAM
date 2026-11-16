from __future__ import annotations

import json
import os
import re
import time
from contextlib import nullcontext
from pathlib import Path
from typing import Any
import requests

from core.project import APP_ROOT

SETTINGS_FILE = APP_ROOT / "work" / "auto_pilot" / "app_settings.json"

DEFAULT_PROVIDERS: dict[str, dict[str, Any]] = {
    "local": {
        "id": "local",
        "name": "🟢 Local GPU (Huihui-Qwen 3.8 27B Uncensored)",
        "short_name": "Huihui Qwen 27B",
        "endpoint": "http://127.0.0.1:8080/v1/chat/completions",
        "model": "huihui-qwen38-abliterated",
        "api_key": "",
        "suggested_models": [
            "huihui-qwen38-abliterated",
            "qwen38_iq3s",
            "local-qwen",
            "qwen2.5-coder-7b",
        ],
        "is_local": True,
        "docs_url": "Chạy mô hình cục bộ không kiểm duyệt trên RTX 5070 Ti qua llama-server.exe (hoàn toàn offline)",
    },
    "ollama": {
        "id": "ollama",
        "name": "🦙 Ollama (Local Offline Server)",
        "short_name": "Ollama",
        "endpoint": "http://127.0.0.1:11434/v1/chat/completions",
        "model": "qwen2.5:latest",
        "api_key": "",
        "suggested_models": [
            "qwen2.5:latest",
            "qwen2.5:32b",
            "deepseek-r1:latest",
            "llama3.3:latest",
            "mistral:latest",
            "codellama:latest",
        ],
        "is_local": True,
        "docs_url": "Chạy mô hình cục bộ qua Ollama (Cài đặt: https://ollama.com)",
    },
    "vllm": {
        "id": "vllm",
        "name": "⚡ vLLM Server (High-Throughput)",
        "short_name": "vLLM",
        "endpoint": "http://127.0.0.1:8000/v1/chat/completions",
        "model": "Qwen/Qwen2.5-32B-Instruct",
        "api_key": "",
        "suggested_models": [
            "Qwen/Qwen2.5-32B-Instruct",
            "deepseek-ai/DeepSeek-V3",
            "meta-llama/Llama-3.3-70B-Instruct",
        ],
        "is_local": True,
        "docs_url": "vLLM Inference Server (OpenAI-compatible: http://127.0.0.1:8000)",
    },
    "openrouter": {
        "id": "openrouter",
        "name": "🔵 OpenRouter (Claude 3.5, GPT-4o, DeepSeek R1...)",
        "short_name": "OpenRouter",
        "endpoint": "https://openrouter.ai/api/v1/chat/completions",
        "model": "anthropic/claude-3.5-sonnet",
        "api_key": "",
        "suggested_models": [
            "anthropic/claude-3.5-sonnet",
            "deepseek/deepseek-r1",
            "deepseek/deepseek-chat",
            "openai/gpt-4o",
            "openai/gpt-4o-mini",
            "google/gemini-2.0-flash-001",
            "meta-llama/llama-3.3-70b-instruct",
            "qwen/qwen-2.5-72b-instruct",
        ],
        "is_local": False,
        "docs_url": "Lấy API Key tại: https://openrouter.ai/keys",
    },
    "openai": {
        "id": "openai",
        "name": "🟢 OpenAI (GPT-4o, o1, o3-mini...)",
        "short_name": "OpenAI",
        "endpoint": "https://api.openai.com/v1/chat/completions",
        "model": "gpt-4o",
        "api_key": "",
        "suggested_models": [
            "gpt-4o",
            "gpt-4o-mini",
            "o1",
            "o3-mini",
            "gpt-4-turbo",
        ],
        "is_local": False,
        "docs_url": "Lấy API Key tại: https://platform.openai.com/api-keys",
    },
    "gemini": {
        "id": "gemini",
        "name": "🟡 Google Gemini (Flash 2.0, Pro 1.5...)",
        "short_name": "Gemini",
        "endpoint": "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
        "model": "gemini-2.0-flash",
        "api_key": "",
        "suggested_models": [
            "gemini-2.0-flash",
            "gemini-2.0-flash-lite",
            "gemini-1.5-pro",
            "gemini-1.5-flash",
        ],
        "is_local": False,
        "docs_url": "Lấy API Key tại: https://aistudio.google.com/apikey",
    },
    "deepseek": {
        "id": "deepseek",
        "name": "🟣 DeepSeek (V3, R1)",
        "short_name": "DeepSeek",
        "endpoint": "https://api.deepseek.com/chat/completions",
        "model": "deepseek-chat",
        "api_key": "",
        "suggested_models": [
            "deepseek-chat",
            "deepseek-reasoner",
        ],
        "is_local": False,
        "docs_url": "Lấy API Key tại: https://platform.deepseek.com/api_keys",
    },
    "groq": {
        "id": "groq",
        "name": "🟠 Groq (Llama 3.3 70B Siêu Tốc)",
        "short_name": "Groq",
        "endpoint": "https://api.groq.com/openai/v1/chat/completions",
        "model": "llama-3.3-70b-versatile",
        "api_key": "",
        "suggested_models": [
            "llama-3.3-70b-versatile",
            "llama-3.1-8b-instant",
            "mixtral-8x7b-32768",
            "deepseek-r1-distill-llama-70b",
        ],
        "is_local": False,
        "docs_url": "Lấy API Key tại: https://console.groq.com/keys",
    },
    "together": {
        "id": "together",
        "name": "🤝 Together AI",
        "short_name": "Together",
        "endpoint": "https://api.together.xyz/v1/chat/completions",
        "model": "meta-llama/Llama-3.3-70B-Instruct-Turbo",
        "api_key": "",
        "suggested_models": [
            "meta-llama/Llama-3.3-70B-Instruct-Turbo",
            "deepseek-ai/DeepSeek-V3",
            "Qwen/Qwen2.5-72B-Instruct-Turbo",
        ],
        "is_local": False,
        "docs_url": "Lấy API Key tại: https://api.together.ai/settings/api-keys",
    },
    "siliconflow": {
        "id": "siliconflow",
        "name": "🌊 SiliconFlow (SiliconCloud)",
        "short_name": "SiliconFlow",
        "endpoint": "https://api.siliconflow.cn/v1/chat/completions",
        "model": "deepseek-ai/DeepSeek-V3",
        "api_key": "",
        "suggested_models": [
            "deepseek-ai/DeepSeek-V3",
            "deepseek-ai/DeepSeek-R1",
            "Qwen/Qwen2.5-72B-Instruct",
            "Pro/deepseek-ai/DeepSeek-V3",
        ],
        "is_local": False,
        "docs_url": "Lấy API Key tại: https://cloud.siliconflow.cn/account/ak",
    },
    "custom": {
        "id": "custom",
        "name": "⚙️ Custom Server (Tùy biến OpenAI API)",
        "short_name": "Custom",
        "endpoint": "http://127.0.0.1:11434/v1/chat/completions",
        "model": "qwen2.5:latest",
        "api_key": "",
        "suggested_models": [
            "qwen2.5:latest",
            "llama3.3:latest",
            "deepseek-r1:latest",
            "mistral:latest",
        ],
        "is_local": False,
        "docs_url": "Tương thích mọi server chuẩn OpenAI Chat Completions API",
    },
}


def normalize_endpoint(endpoint: str) -> str:
    """
    Chuẩn hóa Endpoint URL về định dạng OpenAI /v1/chat/completions.
    Tự động hỗ trợ các trường hợp người dùng chỉ nhập port hoặc hostname.
    """
    ep = endpoint.strip()
    if not ep:
        return ""
    while ep.endswith("/"):
        ep = ep[:-1]

    if ep.endswith("/chat/completions"):
        return ep
    if ep.endswith("/v1"):
        return f"{ep}/chat/completions"
    if ep.endswith("/openai"):
        return f"{ep}/v1/chat/completions"

    for port_str in (":11434", ":8000", ":8080", ":1234", ":5000", ":8090"):
        if ep.endswith(port_str):
            return f"{ep}/v1/chat/completions"

    return ep


def get_settings_file() -> Path:
    candidates = [
        SETTINGS_FILE,
        Path.home() / ".auto_pilot" / "app_settings.json",
        Path(r"D:\Vibe Code\M-Auto-Pilot\work\auto_pilot\app_settings.json"),
    ]
    for c in candidates:
        if c.is_file():
            return c
    return SETTINGS_FILE


def get_llm_settings() -> dict[str, Any]:
    """
    Đọc toàn bộ cấu hình LLM từ app_settings.json.
    Tự động hòa nhập các provider mặc định và tất cả custom providers mà người dùng đã tạo.
    """
    cfg_file = get_settings_file()
    data: dict[str, Any] = {}
    if cfg_file.is_file():
        try:
            data = json.loads(cfg_file.read_text(encoding="utf-8"))
        except Exception:
            data = {}

    saved_providers: dict[str, dict[str, Any]] = data.get("providers") or {}

    merged_providers: dict[str, dict[str, Any]] = {}
    # 1. Điền các provider mặc định
    for pid, pdef in DEFAULT_PROVIDERS.items():
        pdata = dict(pdef)
        if pid in saved_providers and isinstance(saved_providers[pid], dict):
            sp = saved_providers[pid]
            if sp.get("model"):
                pdata["model"] = str(sp["model"]).strip()
            if sp.get("endpoint"):
                pdata["endpoint"] = str(sp["endpoint"]).strip()
            if "api_key" in sp:
                pdata["api_key"] = str(sp["api_key"]).strip()
            if "verified" in sp:
                pdata["verified"] = bool(sp["verified"])
            if sp.get("name"):
                pdata["name"] = str(sp["name"]).strip()
            if sp.get("short_name"):
                pdata["short_name"] = str(sp["short_name"]).strip()
        merged_providers[pid] = pdata

    # 2. Bổ sung các custom provider do người dùng tạo không nằm trong DEFAULT_PROVIDERS
    for pid, sp in saved_providers.items():
        if pid not in merged_providers and isinstance(sp, dict):
            p_name = str(sp.get("name") or f"⚙️ {pid.title()}").strip()
            p_short = str(sp.get("short_name") or pid.title()).strip()
            endpoint = str(sp.get("endpoint") or "").strip()
            is_local = bool(sp.get("is_local", ("127.0.0.1" in endpoint or "localhost" in endpoint)))
            merged_providers[pid] = {
                "id": pid,
                "name": p_name,
                "short_name": p_short,
                "endpoint": endpoint,
                "model": str(sp.get("model") or "").strip(),
                "api_key": str(sp.get("api_key") or "").strip(),
                "suggested_models": list(sp.get("suggested_models") or [str(sp.get("model") or "")]),
                "is_local": is_local,
                "is_custom": True,
                "verified": bool(sp.get("verified", False)),
                "docs_url": str(sp.get("docs_url") or f"Endpoint: {endpoint}"),
            }

    active_provider = str(data.get("llm_provider") or "local").strip().lower()
    if active_provider not in merged_providers:
        active_provider = "local"

    active_pdata = merged_providers[active_provider]
    active_model = str(data.get("llm_model") or active_pdata["model"]).strip()
    active_endpoint = str(data.get("llm_endpoint") or active_pdata["endpoint"]).strip()
    active_api_key = str(data.get("llm_api_key") if "llm_api_key" in data else active_pdata["api_key"]).strip()

    # Đồng bộ ngược vào active_pdata
    active_pdata["model"] = active_model
    active_pdata["endpoint"] = active_endpoint
    active_pdata["api_key"] = active_api_key

    return {
        "llm_provider": active_provider,
        "llm_model": active_model,
        "llm_endpoint": active_endpoint,
        "llm_api_key": active_api_key,
        "providers": merged_providers,
    }


def save_llm_settings(
    provider: str,
    model: str,
    endpoint: str,
    api_key: str,
    providers_map: dict[str, dict[str, Any]] | None = None,
) -> None:
    """
    Lưu cấu hình LLM vào app_settings.json bền vững, giữ nguyên các cài đặt khác.
    """
    cfg_file = get_settings_file()
    cfg_file.parent.mkdir(parents=True, exist_ok=True)

    data: dict[str, Any] = {}
    if cfg_file.is_file():
        try:
            data = json.loads(cfg_file.read_text(encoding="utf-8"))
        except Exception:
            data = {}

    data["llm_provider"] = provider
    data["llm_model"] = model.strip()
    data["llm_endpoint"] = normalize_endpoint(endpoint)
    data["llm_api_key"] = api_key.strip()

    # Cập nhật bảng providers
    saved_providers = data.get("providers") or {}
    if providers_map:
        for pid, pdata in providers_map.items():
            saved_providers[pid] = {
                "name": str(pdata.get("name", "")).strip(),
                "short_name": str(pdata.get("short_name", "")).strip(),
                "model": str(pdata.get("model", "")).strip(),
                "endpoint": normalize_endpoint(str(pdata.get("endpoint", ""))),
                "api_key": str(pdata.get("api_key", "")).strip(),
                "verified": bool(pdata.get("verified", False)),
                "is_local": bool(pdata.get("is_local", False)),
                "is_custom": bool(pdata.get("is_custom", False)),
            }
    else:
        # Cập nhật riêng provider hiện tại
        existing = saved_providers.get(provider, {})
        saved_providers[provider] = {
            "name": str(existing.get("name", "")),
            "short_name": str(existing.get("short_name", "")),
            "model": model.strip(),
            "endpoint": normalize_endpoint(endpoint),
            "api_key": api_key.strip(),
            "verified": bool(existing.get("verified", False)),
            "is_local": bool(existing.get("is_local", False)),
            "is_custom": bool(existing.get("is_custom", False)),
        }

    data["providers"] = saved_providers

    try:
        cfg_file.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception as exc:
        print(f"[LLMSettings] Warning: Không thể ghi file {cfg_file}: {exc}")


def add_custom_provider(
    provider_id: str,
    name: str,
    endpoint: str,
    model: str,
    api_key: str = "",
    short_name: str = "",
    is_local: bool | None = None,
    suggested_models: list[str] | None = None,
) -> dict[str, Any]:
    """
    Đăng ký một nhà cung cấp AI mới do người dùng tùy biến.
    """
    pid = re.sub(r"[^a-zA-Z0-9_\-]", "_", provider_id.strip().lower())
    if not pid:
        pid = f"custom_{int(time.time())}"

    endpoint = normalize_endpoint(endpoint)
    if is_local is None:
        is_local = ("127.0.0.1" in endpoint or "localhost" in endpoint)

    clean_name = name.strip() or f"⚙️ {pid.title()}"
    clean_short = short_name.strip() or pid.title()
    clean_model = model.strip()

    pentry = {
        "id": pid,
        "name": clean_name,
        "short_name": clean_short,
        "endpoint": endpoint,
        "model": clean_model,
        "api_key": api_key.strip(),
        "suggested_models": suggested_models or ([clean_model] if clean_model else []),
        "is_local": is_local,
        "is_custom": True,
        "verified": False,
        "docs_url": f"Endpoint: {endpoint}",
    }

    settings = get_llm_settings()
    providers = settings.get("providers") or {}
    providers[pid] = pentry

    save_llm_settings(
        provider=settings.get("llm_provider", "local"),
        model=settings.get("llm_model", "qwen38_iq3s"),
        endpoint=settings.get("llm_endpoint", ""),
        api_key=settings.get("llm_api_key", ""),
        providers_map=providers,
    )
    return pentry


def delete_custom_provider(provider_id: str) -> bool:
    """
    Xóa một nhà cung cấp tùy biến do người dùng tạo.
    Không cho phép xóa các nhà cung cấp mặc định hệ thống.
    """
    pid = provider_id.strip().lower()
    if pid in DEFAULT_PROVIDERS:
        return False

    cfg_file = get_settings_file()
    if not cfg_file.is_file():
        return False

    try:
        data = json.loads(cfg_file.read_text(encoding="utf-8"))
        providers = data.get("providers") or {}
        if pid in providers:
            del providers[pid]
            data["providers"] = providers

            # Nếu đang kích hoạt provider bị xóa, chuyển về local
            if data.get("llm_provider") == pid:
                data["llm_provider"] = "local"
                def_local = DEFAULT_PROVIDERS["local"]
                data["llm_model"] = def_local["model"]
                data["llm_endpoint"] = def_local["endpoint"]
                data["llm_api_key"] = def_local["api_key"]

            cfg_file.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
            return True
    except Exception as exc:
        print(f"[LLMSettings] Error deleting provider {pid}: {exc}")
    return False


def get_verified_models() -> list[dict[str, Any]]:
    """
    Trả về danh sách các mô hình hợp lệ có thể chọn trong khung chat:
    1. Qwen 3.8 27B (Local GPU) luôn là mặc định (offline, không cần API Key bên ngoài).
    2. Các mô hình khác:
       - Nếu là server cục bộ (Ollama, vLLM, localhost): hợp lệ khi ĐÃ KIỂM TRA KẾT NỐI (verified == True) và có tên model (api_key tùy chọn).
       - Nếu là cloud (OpenAI, Gemini, OpenRouter...): hợp lệ khi ĐÃ CÓ API KEY và ĐÃ KIỂM TRA KẾT NỐI (verified == True).
    """
    settings = get_llm_settings()
    providers = settings.get("providers") or {}

    local_p = providers.get("local") or DEFAULT_PROVIDERS.get("local", {})
    verified_list: list[dict[str, Any]] = [
        {
            "id": "local",
            "provider": "local",
            "model": str(local_p.get("model") or "huihui-qwen38-abliterated"),
            "display_name": "⚡ Huihui-Qwen 3.8 27B (Uncensored GPU - Mặc định)",
            "endpoint": str(local_p.get("endpoint") or "http://127.0.0.1:8080/v1/chat/completions"),
            "api_key": "",
            "is_default": True,
        }
    ]

    for pid, pdata in providers.items():
        if pid == "local":
            continue
        api_key = str(pdata.get("api_key") or "").strip()
        is_verified = bool(pdata.get("verified", False))
        model = str(pdata.get("model") or "").strip()
        is_local = bool(pdata.get("is_local", False))
        endpoint = str(pdata.get("endpoint") or "").strip()
        if not is_local and ("127.0.0.1" in endpoint or "localhost" in endpoint):
            is_local = True

        # Đủ điều kiện hiển thị nếu: đã verify, có tên model, và (có api_key HOẶC là server local offline)
        if is_verified and model and (api_key or is_local):
            def_pdata = DEFAULT_PROVIDERS.get(pid, {})
            p_name = pdata.get("short_name") or def_pdata.get("short_name", pid.title())

            if pid == "ollama":
                icon = "🦙"
            elif pid == "vllm":
                icon = "⚡"
            elif pid == "openai":
                icon = "🟢"
            elif pid == "gemini":
                icon = "🟡"
            elif pid == "deepseek":
                icon = "🟣"
            elif pid == "groq":
                icon = "🟠"
            elif pid == "together":
                icon = "🤝"
            elif pid == "siliconflow":
                icon = "🌊"
            elif pdata.get("is_custom"):
                icon = "⚙️"
            else:
                icon = "🌐"

            verified_list.append({
                "id": pid,
                "provider": pid,
                "model": model,
                "display_name": f"{icon} {model} ({p_name})",
                "endpoint": endpoint or def_pdata.get("endpoint", ""),
                "api_key": api_key,
                "is_default": False,
            })

    return verified_list


def set_active_provider_and_model(provider: str, model: str | None = None) -> None:
    """
    Đặt mô hình và nhà cung cấp đang hoạt động cho toàn bộ hệ thống.
    """
    settings = get_llm_settings()
    providers = settings.get("providers") or {}
    pdata = providers.get(provider) or DEFAULT_PROVIDERS.get(provider, {})
    m = model or pdata.get("model", "qwen38_iq3s")
    endpoint = pdata.get("endpoint", "")
    api_key = pdata.get("api_key", "")
    save_llm_settings(provider=provider, model=m, endpoint=endpoint, api_key=api_key, providers_map=providers)


def test_llm_connection(
    endpoint: str,
    model: str,
    api_key: str = "",
    provider: str = "custom",
    timeout: float = 15.0,
) -> tuple[bool, str]:
    """
    Kiểm tra kết nối và tính hợp lệ của API Key / Model tới endpoint chuẩn OpenAI.
    Trả về (True, message) nếu thành công, hoặc (False, error_message) nếu thất bại.
    """
    endpoint = normalize_endpoint(endpoint)
    model = model.strip()
    if not endpoint:
        return False, "Endpoint URL không được để trống."
    if not model:
        return False, "Tên Model không được để trống."

    headers: dict[str, str] = {
        "Content-Type": "application/json",
    }
    if api_key.strip():
        headers["Authorization"] = f"Bearer {api_key.strip()}"

    if provider == "openrouter" or "openrouter.ai" in endpoint:
        headers["HTTP-Referer"] = "https://m-auto-pilot.local"
        headers["X-Title"] = "M Auto Pilot"

    payload: dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "user", "content": "ping"}
        ],
        "max_tokens": 5,
        "stream": False,
    }

    try:
        is_local_ep = ("127.0.0.1" in endpoint or "localhost" in endpoint)
        scope_ctx = nullcontext()
        if is_local_ep:
            try:
                from llm.server_lifecycle import get_lifecycle_registry

                scope_ctx = get_lifecycle_registry().request_scope()
            except Exception:
                scope_ctx = nullcontext()
        with scope_ctx:
            resp = requests.post(
                endpoint,
                headers=headers,
                json=payload,
                timeout=timeout,
            )
        status_code = resp.status_code
        if status_code == 200:
            res_json = {}
            try:
                res_json = resp.json()
            except Exception:
                pass
            content_preview = ""
            choices = res_json.get("choices") or []
            if choices and isinstance(choices[0], dict):
                content_preview = str(choices[0].get("message", {}).get("content", "")).strip()
            reply_txt = f" Phản hồi: '{content_preview[:40]}...'" if content_preview else ""
            return True, f"✅ Kết nối thành công tới {model}!{reply_txt}"

        # Xử lý các mã lỗi phổ biến
        err_msg = ""
        try:
            err_data = resp.json()
            if isinstance(err_data, dict):
                if "error" in err_data:
                    err_obj = err_data["error"]
                    if isinstance(err_obj, dict):
                        err_msg = err_obj.get("message") or str(err_obj)
                    else:
                        err_msg = str(err_obj)
                elif "message" in err_data:
                    err_msg = str(err_data["message"])
        except Exception:
            err_msg = resp.text[:200]

        if status_code in (401, 403):
            return False, f"❌ Lỗi xác thực ({status_code}): API Key không chính xác hoặc không đủ quyền.\nChi tiết: {err_msg}"
        elif status_code == 404:
            return False, f"❌ Lỗi 404: Endpoint hoặc tên model '{model}' không tìm thấy.\nChi tiết: {err_msg}"
        elif status_code == 429:
            return False, f"❌ Lỗi 429: Hết hạn mức Quota hoặc vượt quá giới hạn Rate Limit.\nChi tiết: {err_msg}"
        else:
            return False, f"❌ Lỗi kết nối HTTP {status_code}: {err_msg or resp.reason}"

    except requests.Timeout:
        return False, f"⏱️ Hết thời gian chờ kết nối ({timeout}s). Vui lòng kiểm tra lại mạng hoặc Endpoint."
    except requests.ConnectionError as ce:
        return False, f"🔌 Không thể kết nối tới máy chủ ({endpoint}): {ce}"
    except Exception as ex:
        return False, f"⚠️ Lỗi phát sinh khi kiểm tra: {ex}"

