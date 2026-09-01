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
        # App & Brand
        "app_title": "Qwen 3.8 27B IQ3_Superfast 16GB VRAM",
        "brand_name": "Auto Pilot",
        "subtitle": "Personal Assistant · Coding Agent · Computer Use",
        "local_model_footer": "Qwen3.8-27B · Running Locally",
        "model_label": "Model: Qwen3.8-27B · IQ3_S",
        
        # Sidebar Actions
        "new_chat": "＋ New Chat",
        "search_chats_placeholder": "🔍 Search chats...",
        "pin": "📌 Pin",
        "unpin": "📌 Unpin",
        "rename": "✏️ Rename",
        "delete": "🗑️ Delete",
        "export_md": "📄 Export MD",
        "reading_resources": "⚡ Reading system resources...",
        "resource_gpu": "⚡ GPU: {gpu}% | VRAM: {vram_used}/{vram_total} GB | CPU: {cpu}% | RAM: {ram_used}/{ram_total} GB",
        
        # Header Controls
        "mode_label": "Mode",
        "mode_assistant": "Personal Assistant",
        "mode_coding": "Coding Agent",
        "mode_auto": "Auto Pilot",
        "gpu_status": "GPU Status",
        "deepseek_harness": "DeepSeek Harness",
        "language_setting": "🌐 Language",
        
        # Status Messages
        "status_ready": "Ready",
        "status_thinking": "Thinking · Step {step}/{max_steps}...",
        "status_streaming": "Generating answer...",
        "status_stopped": "Execution stopped",
        "status_connecting": "Connecting to local LLM server...",
        "status_error": "An error occurred: {error}",
        
        # Input & Actions
        "prompt_placeholder": "Ask anything, write/fix code, search web, or request computer tasks... (Enter to send, Shift+Enter for newline, /help for commands)",
        "send_button": "Send",
        "stop_button": "Stop",
        "attach_button": "📎 Attach",
        "token_estimate": "Tokens: ~{prompt} prompt / ~{max_tok} max out",
        "attached_files": "Attached: {count} file(s)",
        
        # Quick Action Chips
        "chip_plan": "💡 /plan",
        "chip_plan_tip": "Step-by-step implementation planning",
        "chip_fix": "🐛 /fix",
        "chip_fix_tip": "Debug and fix issues",
        "chip_review": "🔍 /review",
        "chip_review_tip": "Detailed code review and optimizations",
        "chip_test": "🧪 /test",
        "chip_test_tip": "Generate and run unit tests",
        "chip_turbo": "🚀 Turbo Mode",
        "chip_turbo_tip": "Activate 4-tier acceleration engine",
        "chip_recovery": "🛡️ Auto Recovery",
        "chip_recovery_tip": "LLM Circuit Breaker & Watchdog",
        "chip_memory": "🧠 RAG Memory",
        "chip_memory_tip": "Vector Embeddings & Long-Term Memory",
        "chip_ram": "💾 RAM Optimizer",
        "chip_ram_tip": "Zero GC Pause & Memory Arena",
        "chip_uitest": "🧪 UI Testing",
        "chip_uitest_tip": "Headless Snapshots & Benchmark",
        "chip_all_tools": "🎛️ All Tools (283 Tools)...",
        "chip_all_tools_tip": "Explore all 283 system automation tools",
        "chip_safety": "🛡️ Safety Sandbox",
        "chip_safety_tip": "Computer action firewall & userscript injector",
        "chip_mission": "🎯 Mission Control",
        "chip_mission_tip": "Autonomous multi-step computer task planner",
        
        # Cards & Message Elements
        "reasoning_title": "🧠 Reasoning & Thought Process",
        "reasoning_collapsed": "🧠 Thought process (Click to expand)",
        "reasoning_expanded": "🧠 Thought process (Click to collapse)",
        "terminal_title": "⚙️ Execution Logs & Output",
        "terminal_collapsed": "⚙️ Execution logs (Click to expand)",
        "terminal_expanded": "⚙️ Execution logs (Click to collapse)",
        "show_details": "Show details",
        "hide_details": "Hide details",
        "copy_content": "📋 Copy",
        "copied": "✅ Copied!",
        "auto_scroll": "Auto scroll",
        
        # Dialogs & Prompts
        "confirm_delete_title": "Confirm Delete",
        "confirm_delete_msg": "Are you sure you want to delete this chat session?",
        "rename_title": "Rename Chat",
        "rename_prompt": "Enter new chat title:",
        "export_success": "📄 Exported chat to {filename} (Path copied to clipboard)",
        "export_failed": "❌ Failed to export chat: {error}",
        "default_new_chat_title": "New Chat",
        "welcome_title": "### 👋 Welcome to Auto Pilot Qwen 3.8 27B IQ3_Superfast!",
        "welcome_body": "I am your local autonomous AI Assistant & Coding Agent with **283 automation tools**.\n\n**Quick capabilities:**\n- 💻 **Coding Agent**: Read code, edit files, syntax checking, and git operations.\n- 🖥️ **Computer Use**: Natural mouse movement, typing, and desktop automation.\n- 🌐 **Chrome Automation**: Multi-tab control, DOM inspection, and CDP scripting.\n- 🛡️ **Safety Sandbox**: Real-time action safety firewall.\n\n*Type your request below or click any quick action above to start!*",
    },
    "vi": {
        # App & Brand
        "app_title": "Qwen 3.8 27B IQ3_Superfast 16GB VRAM",
        "brand_name": "Auto Pilot",
        "subtitle": "Trợ lý cá nhân · Coding Agent · Điều khiển máy tính",
        "local_model_footer": "Qwen3.8-27B · Chạy cục bộ",
        "model_label": "Model: Qwen3.8-27B · IQ3_S",
        
        # Sidebar Actions
        "new_chat": "＋ Chat mới",
        "search_chats_placeholder": "🔍 Tìm kiếm chat...",
        "pin": "📌 Ghim",
        "unpin": "📌 Bỏ ghim",
        "rename": "✏️ Đổi tên",
        "delete": "🗑️ Xóa",
        "export_md": "📄 Xuất MD",
        "reading_resources": "⚡ Đang đọc tài nguyên hệ thống...",
        "resource_gpu": "⚡ GPU: {gpu}% | VRAM: {vram_used}/{vram_total} GB | CPU: {cpu}% | RAM: {ram_used}/{ram_total} GB",
        
        # Header Controls
        "mode_label": "Chế độ",
        "mode_assistant": "Trợ lý cá nhân",
        "mode_coding": "Coding Agent",
        "mode_auto": "Auto Pilot",
        "gpu_status": "GPU Status",
        "deepseek_harness": "DeepSeek Harness",
        "language_setting": "🌐 Ngôn ngữ",
        
        # Status Messages
        "status_ready": "Sẵn sàng",
        "status_thinking": "Đang suy luận · Bước {step}/{max_steps}...",
        "status_streaming": "Đang tạo câu trả lời...",
        "status_stopped": "Đã dừng thực thi",
        "status_connecting": "Đang kết nối LLM Server cục bộ...",
        "status_error": "Đã xảy ra lỗi: {error}",
        
        # Input & Actions
        "prompt_placeholder": "Hỏi bất cứ điều gì, yêu cầu viết/sửa code, tìm tài liệu hoặc điều khiển máy... (Enter để gửi, Shift+Enter xuống dòng, /help xem lệnh)",
        "send_button": "Gửi",
        "stop_button": "Dừng",
        "attach_button": "📎 Đính kèm",
        "token_estimate": "Tokens: ~{prompt} prompt / ~{max_tok} max out",
        "attached_files": "Đã đính kèm: {count} file",
        
        # Quick Action Chips
        "chip_plan": "💡 /plan",
        "chip_plan_tip": "Lập kế hoạch từng bước",
        "chip_fix": "🐛 /fix",
        "chip_fix_tip": "Sửa lỗi và debug",
        "chip_review": "🔍 /review",
        "chip_review_tip": "Review code chi tiết và tối ưu hóa",
        "chip_test": "🧪 /test",
        "chip_test_tip": "Tạo và chạy kiểm thử tự động",
        "chip_turbo": "🚀 Turbo Mode",
        "chip_turbo_tip": "Kích hoạt 4 tầng tăng tốc",
        "chip_recovery": "🛡️ Tự Hồi Phục",
        "chip_recovery_tip": "LLM Circuit Breaker & Watchdog",
        "chip_memory": "🧠 Bộ Nhớ RAG",
        "chip_memory_tip": "Vector Embeddings & Bộ nhớ dài hạn",
        "chip_ram": "💾 Tối Ưu RAM",
        "chip_ram_tip": "Zero GC Pause & Bộ đệm Arena",
        "chip_uitest": "🧪 Kiểm Thử UI",
        "chip_uitest_tip": "Headless Snapshots & Benchmark",
        "chip_all_tools": "🎛️ Tất Cả Công Cụ (283 Tools)...",
        "chip_all_tools_tip": "Tra cứu toàn bộ 283 công cụ tự động hóa",
        "chip_safety": "🛡️ Tường Lửa An Toàn",
        "chip_safety_tip": "Tường lửa bảo vệ máy tính & tiêm userscript",
        "chip_mission": "🎯 Điều Khiển Nhiệm Vụ",
        "chip_mission_tip": "Lập kế hoạch tác vụ máy tính đa bước tự động",
        
        # Cards & Message Elements
        "reasoning_title": "🧠 Quá Trình Suy Luận & Phân Tích",
        "reasoning_collapsed": "🧠 Quá trình suy luận (Bấm để mở rộng)",
        "reasoning_expanded": "🧠 Quá trình suy luận (Bấm để thu gọn)",
        "terminal_title": "⚙️ Lệnh Thực Thi & Nhật Ký Output",
        "terminal_collapsed": "⚙️ Nhật ký thực thi (Bấm để mở rộng)",
        "terminal_expanded": "⚙️ Nhật ký thực thi (Bấm để thu gọn)",
        "show_details": "Xem chi tiết",
        "hide_details": "Thu gọn",
        "copy_content": "📋 Sao chép",
        "copied": "✅ Đã sao chép!",
        "auto_scroll": "Tự động cuộn",
        
        # Dialogs & Prompts
        "confirm_delete_title": "Xác nhận xóa",
        "confirm_delete_msg": "Bạn có chắc chắn muốn xóa cuộc trò chuyện này?",
        "rename_title": "Đổi tên cuộc trò chuyện",
        "rename_prompt": "Nhập tiêu đề mới:",
        "export_success": "📄 Đã xuất chat ra {filename} (Đã copy đường dẫn)",
        "export_failed": "❌ Xuất chat thất bại: {error}",
        "default_new_chat_title": "Chat mới",
        "welcome_title": "### 👋 Chào mừng bạn đến với Auto Pilot Qwen 3.8 27B IQ3_Superfast!",
        "welcome_body": "Tôi là Trợ lý AI cá nhân & Coding Agent chạy cục bộ với **283 công cụ tự động hóa**.\n\n**Các khả năng chính:**\n- 💻 **Coding Agent**: Đọc code, sửa file, kiểm tra cú pháp và thao tác git.\n- 🖥️ **Computer Use**: Di chuyển chuột tự nhiên, gõ văn bản và tự động hóa desktop.\n- 🌐 **Chrome CDP**: Điều khiển đa tab, đọc DOM và tiêm script tự động.\n- 🛡️ **Safety Sandbox**: Tường lửa bảo vệ an toàn hệ thống theo thời gian thực.\n\n*Nhập yêu cầu bên dưới hoặc bấm vào các nút tắt phía trên để bắt đầu!*",
    },
    "zh": {
        # App & Brand
        "app_title": "Qwen 3.8 27B IQ3_Superfast 16GB VRAM",
        "brand_name": "Auto Pilot",
        "subtitle": "个人助理 · 编程智能体 · 电脑自动化控制",
        "local_model_footer": "Qwen3.8-27B · 本地离线运行",
        "model_label": "模型: Qwen3.8-27B · IQ3_S",
        
        # Sidebar Actions
        "new_chat": "＋ 新对话",
        "search_chats_placeholder": "🔍 搜索对话记录...",
        "pin": "📌 置顶",
        "unpin": "📌 取消置顶",
        "rename": "✏️ 重命名",
        "delete": "🗑️ 删除",
        "export_md": "📄 导出 MD",
        "reading_resources": "⚡ 正在读取系统资源...",
        "resource_gpu": "⚡ 显卡: {gpu}% | 显存: {vram_used}/{vram_total} GB | CPU: {cpu}% | 内存: {ram_used}/{ram_total} GB",
        
        # Header Controls
        "mode_label": "模式",
        "mode_assistant": "个人助理",
        "mode_coding": "编程智能体",
        "mode_auto": "自动驾驶",
        "gpu_status": "显卡状态",
        "deepseek_harness": "DeepSeek Harness",
        "language_setting": "🌐 语言 / Language",
        
        # Status Messages
        "status_ready": "就绪",
        "status_thinking": "正在思考推理 · 步骤 {step}/{max_steps}...",
        "status_streaming": "正在生成回答...",
        "status_stopped": "已停止执行",
        "status_connecting": "正在连接本地 LLM 服务...",
        "status_error": "发生错误: {error}",
        
        # Input & Actions
        "prompt_placeholder": "请输入任何问题、编写/修改代码、搜索网络或请求自动化任务... (Enter 发送, Shift+Enter 换行, /help 查看命令)",
        "send_button": "发送",
        "stop_button": "停止",
        "attach_button": "📎 附件",
        "token_estimate": "Tokens: ~{prompt} prompt / ~{max_tok} max out",
        "attached_files": "已添加附件: {count} 个文件",
        
        # Quick Action Chips
        "chip_plan": "💡 /plan",
        "chip_plan_tip": "分步执行规划",
        "chip_fix": "🐛 /fix",
        "chip_fix_tip": "排查与修复错误",
        "chip_review": "🔍 /review",
        "chip_review_tip": "代码深度审查与优化建议",
        "chip_test": "🧪 /test",
        "chip_test_tip": "生成并执行单元测试",
        "chip_turbo": "🚀 Turbo 极速模式",
        "chip_turbo_tip": "开启 4 层极速推理加速引擎",
        "chip_recovery": "🛡️ 自动容灾",
        "chip_recovery_tip": "LLM 断路器与自动看门狗",
        "chip_memory": "🧠 RAG 长期记忆",
        "chip_memory_tip": "向量嵌入与长期上下文记忆",
        "chip_ram": "💾 内存优化",
        "chip_ram_tip": "零 GC 暂停与内存 Arena 优化",
        "chip_uitest": "🧪 界面测试",
        "chip_uitest_tip": "无头快照与基准性能测试",
        "chip_all_tools": "🎛️ 全部工具 (283 工具)...",
        "chip_all_tools_tip": "查看全部 283 个系统与浏览器自动化工具",
        "chip_safety": "🛡️ 安全防火墙",
        "chip_safety_tip": "系统动作防火墙与 Userscript 脚本注入",
        "chip_mission": "🎯 任务控制中心",
        "chip_mission_tip": "全自主多步电脑任务执行规划器",
        
        # Cards & Message Elements
        "reasoning_title": "🧠 深度思考与推理过程",
        "reasoning_collapsed": "🧠 思考过程 (点击展开)",
        "reasoning_expanded": "🧠 思考过程 (点击折叠)",
        "terminal_title": "⚙️ 命令执行与日志输出",
        "terminal_collapsed": "⚙️ 执行日志 (点击展开)",
        "terminal_expanded": "⚙️ 执行日志 (点击折叠)",
        "show_details": "查看详情",
        "hide_details": "收起详情",
        "copy_content": "📋 复制",
        "copied": "✅ 已复制!",
        "auto_scroll": "自动滚动",
        
        # Dialogs & Prompts
        "confirm_delete_title": "确认删除",
        "confirm_delete_msg": "确定要删除此对话记录吗？",
        "rename_title": "重命名对话",
        "rename_prompt": "请输入新的对话标题:",
        "export_success": "📄 对话已导出至 {filename} (已复制路径到剪贴板)",
        "export_failed": "❌ 导出对话失败: {error}",
        "default_new_chat_title": "新对话",
        "welcome_title": "### 👋 欢迎使用 Auto Pilot Qwen 3.8 27B IQ3_Superfast!",
        "welcome_body": "我是您的本地离线自主 AI 助手与编程智能体，内置 **283 个系统自动化工具**。\n\n**核心能力：**\n- 💻 **编程智能体**：代码阅读、文件编辑、语法检查与 Git 操作。\n- 🖥️ **电脑自动化控制**：拟人平滑鼠标移动、键盘输入与桌面控制。\n- 🌐 **Chrome CDP 控制**：多标签页管理、DOM 审查与脚本注入。\n- 🛡️ **安全沙箱防火墙**：实时操作安全审计，防止破坏性系统指令。\n\n*在下方输入您的请求，或点击上方快捷按钮即可开始！*",
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
