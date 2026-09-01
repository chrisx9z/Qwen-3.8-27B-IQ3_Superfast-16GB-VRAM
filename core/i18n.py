from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from core.project import APP_ROOT

SETTINGS_FILE = APP_ROOT / "work" / "auto_pilot" / "app_settings.json"

SUPPORTED_LANGUAGES = {
    "en": "English",
    "vi": "Tiếng Việt",
    "zh": "简体中文",
}

DEFAULT_LANGUAGE = "en"

TRANSLATIONS: dict[str, dict[str, str]] = {
    "en": {
        "app_title": "Auto Pilot Qwen 3.8 27B IQ3_Superfast",
        "brand_name": "Auto Pilot",
        "subtitle": "Personal Assistant · Coding Agent · Computer Use",
        "new_chat": "＋ New Chat",
        "search_chats_placeholder": "🔍 Search chats...",
        "pin": "📌 Pin",
        "unpin": "📌 Unpin",
        "rename": "✏️ Rename",
        "delete": "🗑️ Delete",
        "export_md": "📄 Export MD",
        "reading_resources": "⚡ Reading resources...",
        "local_model_footer": "Qwen3.8-27B · Running Locally",
        "mode_label": "Mode",
        "mode_assistant": "Personal Assistant",
        "mode_coding": "Coding Agent",
        "mode_auto": "Auto Pilot",
        "status_ready": "Ready",
        "status_thinking": "Thinking · step {step}/{max_steps}...",
        "status_streaming": "Generating answer...",
        "status_stopped": "Stopped",
        "gpu_status": "GPU Status",
        "deepseek_harness": "DeepSeek Harness",
        "language_setting": "🌐 Language",
        "prompt_placeholder": "Ask anything, write code, or request a computer task... (Enter to send, Shift+Enter for new line)",
        "send_button": "Send",
        "stop_button": "Stop",
        "attach_button": "📎 Attach",
        "token_estimate": "Tokens: {prompt} prompt / ~{max_tok} max out",
        "confirm_delete_title": "Confirm Delete",
        "confirm_delete_msg": "Are you sure you want to delete this chat?",
        "rename_title": "Rename Chat",
        "rename_prompt": "Enter new title:",
        "export_success": "📄 Exported chat to {filename} (Path copied to clipboard)",
        "all_tools_chip": "🎛️ All Tools (283 Tools)...",
        "all_tools_tip": "Browse all 283 system automation tools",
        "model_label": "Model: Qwen3.8-27B · IQ3_S",
        "chip_plan": "💡 /plan",
        "chip_plan_tip": "Step-by-step implementation planning",
        "chip_fix": "🐛 /fix",
        "chip_fix_tip": "Debug and fix issues",
        "chip_review": "🔍 /review",
        "chip_review_tip": "Detailed code review",
        "chip_test": "🧪 /test",
        "chip_test_tip": "Generate and run unit tests",
        "chip_turbo": "🚀 Turbo Mode",
        "chip_turbo_tip": "Activate 4-tier acceleration engine",
        "chip_safety": "🛡️ Safety Sandbox",
        "chip_safety_tip": "Computer action firewall & userscript injector",
    },
    "vi": {
        "app_title": "Auto Pilot Qwen 3.8 27B IQ3_Superfast",
        "brand_name": "Auto Pilot",
        "subtitle": "Trợ lý cá nhân · Coding Agent · Điều khiển máy tính",
        "new_chat": "＋ Chat mới",
        "search_chats_placeholder": "🔍 Tìm kiếm chat...",
        "pin": "📌 Ghim",
        "unpin": "📌 Bỏ ghim",
        "rename": "✏️ Đổi tên",
        "delete": "🗑️ Xóa",
        "export_md": "📄 Xuất MD",
        "reading_resources": "⚡ Đang đọc tài nguyên...",
        "local_model_footer": "Qwen3.8-27B · Chạy cục bộ",
        "mode_label": "Chế độ",
        "mode_assistant": "Trợ lý cá nhân",
        "mode_coding": "Coding Agent",
        "mode_auto": "Auto Pilot",
        "status_ready": "Sẵn sàng",
        "status_thinking": "Đang suy luận · bước {step}/{max_steps}...",
        "status_streaming": "Đang tạo câu trả lời...",
        "status_stopped": "Đã dừng",
        "gpu_status": "GPU Status",
        "deepseek_harness": "DeepSeek Harness",
        "language_setting": "🌐 Ngôn ngữ",
        "prompt_placeholder": "Hỏi bất cứ điều gì, viết code hoặc yêu cầu tác vụ... (Enter để gửi, Shift+Enter xuống dòng)",
        "send_button": "Gửi",
        "stop_button": "Dừng",
        "attach_button": "📎 Đính kèm",
        "token_estimate": "Tokens: {prompt} prompt / ~{max_tok} max out",
        "confirm_delete_title": "Xác nhận xóa",
        "confirm_delete_msg": "Bạn có chắc chắn muốn xóa cuộc trò chuyện này?",
        "rename_title": "Đổi tên cuộc trò chuyện",
        "rename_prompt": "Nhập tiêu đề mới:",
        "export_success": "📄 Đã xuất chat ra {filename} (Đã copy đường dẫn)",
        "all_tools_chip": "🎛️ Tất Cả Công Cụ (283 Tools)...",
        "all_tools_tip": "Tra cứu toàn bộ 283 công cụ tự động hóa",
        "model_label": "Model: Qwen3.8-27B · IQ3_S",
        "chip_plan": "💡 /plan",
        "chip_plan_tip": "Lập kế hoạch từng bước",
        "chip_fix": "🐛 /fix",
        "chip_fix_tip": "Sửa lỗi và debug",
        "chip_review": "🔍 /review",
        "chip_review_tip": "Review code chi tiết",
        "chip_test": "🧪 /test",
        "chip_test_tip": "Tạo và chạy test",
        "chip_turbo": "🚀 Turbo Mode",
        "chip_turbo_tip": "Kích hoạt 4 tầng tăng tốc",
        "chip_safety": "🛡️ Tường Lửa An Toàn",
        "chip_safety_tip": "Tường lửa bảo vệ máy tính & tiêm userscript",
    },
    "zh": {
        "app_title": "Auto Pilot Qwen 3.8 27B IQ3_Superfast",
        "brand_name": "Auto Pilot",
        "subtitle": "个人助理 · 编程智能体 · 电脑自动化控制",
        "new_chat": "＋ 新对话",
        "search_chats_placeholder": "🔍 搜索对话...",
        "pin": "📌 置顶",
        "unpin": "📌 取消置顶",
        "rename": "✏️ 重命名",
        "delete": "🗑️ 删除",
        "export_md": "📄 导出 MD",
        "reading_resources": "⚡ 正在读取系统资源...",
        "local_model_footer": "Qwen3.8-27B · 本地离线运行",
        "mode_label": "模式",
        "mode_assistant": "个人助理",
        "mode_coding": "编程智能体",
        "mode_auto": "自动驾驶",
        "status_ready": "就绪",
        "status_thinking": "正在思考推理 · 步骤 {step}/{max_steps}...",
        "status_streaming": "正在生成回答...",
        "status_stopped": "已停止",
        "gpu_status": "显卡状态",
        "deepseek_harness": "DeepSeek Harness",
        "language_setting": "🌐 语言 / Language",
        "prompt_placeholder": "请输入任何问题、编写代码或请求自动化任务... (Enter 发送, Shift+Enter 换行)",
        "send_button": "发送",
        "stop_button": "停止",
        "attach_button": "📎 附件",
        "token_estimate": "Tokens: {prompt} prompt / ~{max_tok} max out",
        "confirm_delete_title": "确认删除",
        "confirm_delete_msg": "确定要删除此对话记录吗？",
        "rename_title": "重命名对话",
        "rename_prompt": "请输入新的对话标题:",
        "export_success": "📄 对话已导出至 {filename} (已复制路径到剪贴板)",
        "all_tools_chip": "🎛️ 全部工具 (283 工具)...",
        "all_tools_tip": "查看全部 283 个系统与浏览器自动化工具",
        "model_label": "模型: Qwen3.8-27B · IQ3_S",
        "chip_plan": "💡 /plan",
        "chip_plan_tip": "分步执行计划",
        "chip_fix": "🐛 /fix",
        "chip_fix_tip": "排查与修复错误",
        "chip_review": "🔍 /review",
        "chip_review_tip": "代码审查与优化建议",
        "chip_test": "🧪 /test",
        "chip_test_tip": "生成并执行单元测试",
        "chip_turbo": "🚀 Turbo 加速模式",
        "chip_turbo_tip": "开启 4 层极速推理引擎",
        "chip_safety": "🛡️ 安全防火墙",
        "chip_safety_tip": "系统动作防火墙与 Userscript 脚本注入",
    },
}

_CURRENT_LANGUAGE: str = DEFAULT_LANGUAGE


def load_saved_language() -> str:
    global _CURRENT_LANGUAGE
    try:
        if SETTINGS_FILE.is_file():
            data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
            lang = str(data.get("language", DEFAULT_LANGUAGE)).strip().lower()
            if lang in SUPPORTED_LANGUAGES:
                _CURRENT_LANGUAGE = lang
                return lang
    except Exception:
        pass
    _CURRENT_LANGUAGE = DEFAULT_LANGUAGE
    return DEFAULT_LANGUAGE


def save_language(lang_code: str) -> None:
    global _CURRENT_LANGUAGE
    if lang_code not in SUPPORTED_LANGUAGES:
        lang_code = DEFAULT_LANGUAGE
    _CURRENT_LANGUAGE = lang_code
    try:
        SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
        data = {}
        if SETTINGS_FILE.is_file():
            try:
                data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
            except Exception:
                data = {}
        data["language"] = lang_code
        SETTINGS_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


set_language = save_language


def get_current_language() -> str:
    return _CURRENT_LANGUAGE


def t(key: str, **kwargs: Any) -> str:
    lang = get_current_language()
    dict_lang = TRANSLATIONS.get(lang, TRANSLATIONS[DEFAULT_LANGUAGE])
    val = dict_lang.get(key) or TRANSLATIONS[DEFAULT_LANGUAGE].get(key) or key
    if kwargs:
        try:
            return val.format(**kwargs)
        except Exception:
            return val
    return val
