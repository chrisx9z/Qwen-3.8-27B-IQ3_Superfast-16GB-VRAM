from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Callable
from urllib.parse import parse_qs, quote, unquote, urlparse
from uuid import uuid4

import psutil
import requests

from core.project import (
    APP_ROOT,
    VideoProject,
    load_all_projects,
)
from downloader.platform_config import Platform, detect_platform
from downloader.video_downloader import DownloadRequest, VideoDownloader


ToolHandler = Callable[[dict[str, Any]], dict[str, Any]]

VIDEO_EXTENSIONS = {
    ".avi",
    ".m4v",
    ".mkv",
    ".mov",
    ".mp4",
    ".webm",
}

CODE_EXTENSIONS = {
    ".bat",
    ".css",
    ".html",
    ".ini",
    ".js",
    ".json",
    ".md",
    ".ps1",
    ".py",
    ".pyi",
    ".toml",
    ".ts",
    ".tsx",
    ".txt",
    ".yaml",
    ".yml",
}

SKIP_CODE_DIRECTORIES = {
    ".git",
    ".venv",
    "downloads",
    "input",
    "models",
    "output",
    "__pycache__",
}

CHECKPOINT_ROOT = APP_ROOT / "work" / "auto_pilot" / "checkpoints"
EXTERNAL_ROOT = APP_ROOT / "work" / "auto_pilot" / "external"
ALLOWED_WORKSPACE_EXECUTABLES = {
    "ffmpeg",
    "ffmpeg.exe",
    "ffprobe",
    "ffprobe.exe",
    "git",
    "git.exe",
    "node",
    "node.exe",
    "npm",
    "npm.cmd",
    "npx",
    "npx.cmd",
    "pip",
    "pip.exe",
    "python",
    "python.exe",
    "py",
    "py.exe",
    "uv",
    "uv.exe",
}

ALLOWED_VIDEO_ROOTS = tuple(
    (APP_ROOT / folder).resolve()
    for folder in (
        "downloads",
        "input",
        "output",
    )
)

ALLOWED_APPLICATION_ROOTS = tuple(
    path.resolve()
    for path in (
        APP_ROOT,
        Path(r"D:\AI-Video-Localizer"),
        Path(r"D:\OneDrive\Desktop"),
        Path.home() / "Desktop",
        Path.home() / "Downloads",
    )
)


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    parameters: dict[str, Any]
    handler: ToolHandler

    def definition(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


class LocalToolRegistry:
    def __init__(self) -> None:
        self._specs = {
            spec.name: spec
            for spec in (
                ToolSpec(
                    name="list_projects",
                    description=(
                        "Liệt kê các project video hiện có trong Queue. "
                        "Chỉ đọc dữ liệu."
                    ),
                    parameters={
                        "type": "object",
                        "properties": {
                            "limit": {
                                "type": "integer",
                                "minimum": 1,
                                "maximum": 50,
                                "description": "Số project tối đa cần trả về.",
                            },
                        },
                        "additionalProperties": False,
                    },
                    handler=self._list_projects,
                ),
                ToolSpec(
                    name="get_project",
                    description=(
                        "Đọc trạng thái, stage và artifact của một project "
                        "theo ID. Chỉ đọc dữ liệu."
                    ),
                    parameters={
                        "type": "object",
                        "properties": {
                            "project_id": {
                                "type": "string",
                                "description": "ID 8 ký tự của project.",
                            },
                        },
                        "required": ["project_id"],
                        "additionalProperties": False,
                    },
                    handler=self._get_project,
                ),
                ToolSpec(
                    name="download_bilibili",
                    description=(
                        "Tải một video hoặc playlist Bilibili vào thư mục "
                        "downloads hoặc input của ứng dụng. Đây là thao tác "
                        "ghi file và có thể chạy lâu."
                    ),
                    parameters={
                        "type": "object",
                        "properties": {
                            "url": {
                                "type": "string",
                                "description": "URL video hoặc playlist Bilibili.",
                            },
                            "destination": {
                                "type": "string",
                                "enum": ["downloads", "input"],
                                "description": "Thư mục đích logic.",
                            },
                            "max_height": {
                                "type": "integer",
                                "description": "Giới hạn độ phân giải theo chiều cao.",
                            },
                            "prefer_h264": {
                                "type": "boolean",
                                "description": "Ưu tiên codec H.264 để tương thích xuất video.",
                            },
                            "use_cookie": {
                                "type": "boolean",
                                "description": "Dùng cookie Bilibili đã cấu hình.",
                            },
                            "download_playlist": {
                                "type": "boolean",
                                "description": "Tải toàn bộ playlist thay vì một video.",
                            },
                        },
                        "required": ["url"],
                        "additionalProperties": False,
                    },
                    handler=self._download_bilibili,
                ),
                ToolSpec(
                    name="create_project",
                    description=(
                        "Tạo project từ một video đã có trong downloads, input "
                        "hoặc output. Không chấp nhận đường dẫn ngoài các thư "
                        "mục được phép."
                    ),
                    parameters={
                        "type": "object",
                        "properties": {
                            "video_path": {
                                "type": "string",
                                "description": "Đường dẫn file video hiện có.",
                            },
                        },
                        "required": ["video_path"],
                        "additionalProperties": False,
                    },
                    handler=self._create_project,
                ),
                ToolSpec(
                    name="list_directory",
                    description=(
                        "Liệt kê file/thư mục trong vùng ứng dụng. Chỉ đọc dữ liệu "
                        "và không truy cập ra ngoài thư mục AI Video Localizer."
                    ),
                    parameters={
                        "type": "object",
                        "properties": {
                            "path": {
                                "type": "string",
                                "description": "Đường dẫn tương đối trong thư mục ứng dụng.",
                            },
                            "recursive": {
                                "type": "boolean",
                                "description": "Duyệt đệ quy hay không.",
                            },
                            "limit": {
                                "type": "integer",
                                "minimum": 1,
                                "maximum": 200,
                                "description": "Số entry tối đa.",
                            },
                        },
                        "additionalProperties": False,
                    },
                    handler=self._list_directory,
                ),
                ToolSpec(
                    name="get_system_status",
                    description=(
                        "Đọc trạng thái CPU, RAM, dung lượng đĩa và các port local "
                        "của llama-server. Chỉ đọc dữ liệu."
                    ),
                    parameters={
                        "type": "object",
                        "properties": {},
                        "additionalProperties": False,
                    },
                    handler=self._get_system_status,
                ),
                ToolSpec(
                    name="get_resource_status",
                    description=(
                        "Đọc resource manager: model agent đang giữ, llama-server "
                        "8080/8090, VRAM và cảnh báo tranh chấp."
                    ),
                    parameters={
                        "type": "object",
                        "properties": {},
                        "additionalProperties": False,
                    },
                    handler=self._get_resource_status,
                ),
                ToolSpec(
                    name="screen_capture",
                    description=(
                        "Chụp màn hình desktop hoặc một vùng màn hình, lưu trong "
                        "work/auto_pilot/screenshots."
                    ),
                    parameters={
                        "type": "object",
                        "properties": {
                            "x": {"type": "integer"},
                            "y": {"type": "integer"},
                            "width": {"type": "integer", "minimum": 1, "maximum": 10000},
                            "height": {"type": "integer", "minimum": 1, "maximum": 10000},
                        },
                        "additionalProperties": False,
                    },
                    handler=self._screen_capture,
                ),
                ToolSpec(
                    name="screen_ocr",
                    description=(
                        "Nhận dạng text trên ảnh trong workspace hoặc chụp màn hình "
                        "rồi OCR bằng RapidOCR CPU."
                    ),
                    parameters={
                        "type": "object",
                        "properties": {
                            "image_path": {"type": "string"},
                            "x": {"type": "integer"},
                            "y": {"type": "integer"},
                            "width": {"type": "integer", "minimum": 1, "maximum": 10000},
                            "height": {"type": "integer", "minimum": 1, "maximum": 10000},
                            "min_confidence": {"type": "number", "minimum": 0, "maximum": 1},
                        },
                        "additionalProperties": False,
                    },
                    handler=self._screen_ocr,
                ),
                ToolSpec(
                    name="list_processes",
                    description="Liệt kê tiến trình Windows và mức dùng RAM; chỉ đọc.",
                    parameters={
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "limit": {"type": "integer", "minimum": 1, "maximum": 100},
                        },
                        "additionalProperties": False,
                    },
                    handler=self._list_processes,
                ),
                ToolSpec(
                    name="read_runtime_log",
                    description="Đọc phần cuối của log trong workspace.",
                    parameters={
                        "type": "object",
                        "properties": {
                            "path": {"type": "string"},
                            "lines": {"type": "integer", "minimum": 1, "maximum": 1000},
                        },
                        "required": ["path"],
                        "additionalProperties": False,
                    },
                    handler=self._read_runtime_log,
                ),
                ToolSpec(
                    name="stop_managed_process",
                    description=(
                        "Dừng runtime allowlist của ứng dụng: llama-server, ffmpeg hoặc "
                        "ffprobe theo PID."
                    ),
                    parameters={
                        "type": "object",
                        "properties": {"pid": {"type": "integer", "minimum": 1}},
                        "required": ["pid"],
                        "additionalProperties": False,
                    },
                    handler=self._stop_managed_process,
                ),
                ToolSpec(
                    name="browser_open",
                    description=(
                        "Mở URL http/https trong Edge hoặc Chrome qua Playwright "
                        "và giữ phiên browser cho các tool tiếp theo."
                    ),
                    parameters={
                        "type": "object",
                        "properties": {
                            "url": {"type": "string", "description": "URL http/https."},
                            "headless": {"type": "boolean", "description": "Ẩn cửa sổ browser hay không."},
                            "wait_ms": {"type": "integer", "minimum": 0, "maximum": 10000},
                        },
                        "required": ["url"],
                        "additionalProperties": False,
                    },
                    handler=self._browser_open,
                ),
                ToolSpec(
                    name="browser_snapshot",
                    description="Đọc tiêu đề, URL và text hiện tại của trang browser.",
                    parameters={
                        "type": "object",
                        "properties": {"max_chars": {"type": "integer", "minimum": 100, "maximum": 30000}},
                        "additionalProperties": False,
                    },
                    handler=self._browser_snapshot,
                ),
                ToolSpec(
                    name="browser_click",
                    description="Click phần tử browser bằng CSS selector hoặc text hiển thị.",
                    parameters={
                        "type": "object",
                        "properties": {
                            "selector": {"type": "string"},
                            "text": {"type": "string"},
                            "wait_ms": {"type": "integer", "minimum": 0, "maximum": 10000},
                        },
                        "additionalProperties": False,
                    },
                    handler=self._browser_click,
                ),
                ToolSpec(
                    name="browser_type",
                    description="Điền text vào input browser bằng CSS selector hoặc text.",
                    parameters={
                        "type": "object",
                        "properties": {
                            "value": {"type": "string"},
                            "selector": {"type": "string"},
                            "text": {"type": "string"},
                            "press_enter": {"type": "boolean"},
                        },
                        "required": ["value"],
                        "additionalProperties": False,
                    },
                    handler=self._browser_type,
                ),
                ToolSpec(
                    name="browser_extract",
                    description="Đọc text của một vùng trang browser.",
                    parameters={
                        "type": "object",
                        "properties": {
                            "selector": {"type": "string"},
                            "max_chars": {"type": "integer", "minimum": 100, "maximum": 30000},
                        },
                        "additionalProperties": False,
                    },
                    handler=self._browser_extract,
                ),
                ToolSpec(
                    name="browser_screenshot",
                    description="Chụp màn hình browser vào work/auto_pilot/browser.",
                    parameters={
                        "type": "object",
                        "properties": {},
                        "additionalProperties": False,
                    },
                    handler=self._browser_screenshot,
                ),
                ToolSpec(
                    name="browser_close",
                    description="Đóng phiên browser Auto Pilot.",
                    parameters={
                        "type": "object",
                        "properties": {},
                        "additionalProperties": False,
                    },
                    handler=self._browser_close,
                ),
                ToolSpec(
                    name="ui_list_windows",
                    description="Liệt kê cửa sổ Windows đang hiển thị qua UI Automation.",
                    parameters={
                        "type": "object",
                        "properties": {"limit": {"type": "integer", "minimum": 1, "maximum": 100}},
                        "additionalProperties": False,
                    },
                    handler=self._ui_list_windows,
                ),
                ToolSpec(
                    name="ui_snapshot",
                    description="Đọc cây control của một cửa sổ Windows qua UI Automation.",
                    parameters={
                        "type": "object",
                        "properties": {
                            "window_title": {"type": "string"},
                            "limit": {"type": "integer", "minimum": 1, "maximum": 200},
                        },
                        "required": ["window_title"],
                        "additionalProperties": False,
                    },
                    handler=self._ui_snapshot,
                ),
                ToolSpec(
                    name="ui_click",
                    description="Click control Windows theo title/automation_id trong một cửa sổ xác định.",
                    parameters={
                        "type": "object",
                        "properties": {
                            "window_title": {"type": "string"},
                            "control_title": {"type": "string"},
                            "automation_id": {"type": "string"},
                            "control_type": {"type": "string"},
                        },
                        "required": ["window_title"],
                        "additionalProperties": False,
                    },
                    handler=self._ui_click,
                ),
                ToolSpec(
                    name="ui_type",
                    description="Nhập text vào control Edit Windows theo title/automation_id.",
                    parameters={
                        "type": "object",
                        "properties": {
                            "window_title": {"type": "string"},
                            "value": {"type": "string"},
                            "control_title": {"type": "string"},
                            "automation_id": {"type": "string"},
                            "control_type": {"type": "string"},
                            "press_enter": {"type": "boolean"},
                        },
                        "required": ["window_title", "value"],
                        "additionalProperties": False,
                    },
                    handler=self._ui_type,
                ),
                ToolSpec(
                    name="ui_press_key",
                    description="Gửi một phím được allowlist tới cửa sổ/control Windows.",
                    parameters={
                        "type": "object",
                        "properties": {
                            "window_title": {"type": "string"},
                            "key": {"type": "string"},
                            "control_title": {"type": "string"},
                            "automation_id": {"type": "string"},
                            "control_type": {"type": "string"},
                        },
                        "required": ["window_title", "key"],
                        "additionalProperties": False,
                    },
                    handler=self._ui_press_key,
                ),
                ToolSpec(
                    name="launch_application",
                    description=(
                        "Mở một ứng dụng Windows .exe trong các thư mục được phép, "
                        "không dùng shell và không thực thi chuỗi lệnh tùy ý."
                    ),
                    parameters={
                        "type": "object",
                        "properties": {
                            "path": {"type": "string", "description": "Đường dẫn tuyệt đối tới file .exe."},
                            "args": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Tham số dạng danh sách, không qua shell.",
                            },
                        },
                        "required": ["path"],
                        "additionalProperties": False,
                    },
                    handler=self._launch_application,
                ),
                ToolSpec(
                    name="ai_video_localizer_status",
                    description=(
                        "Đọc trạng thái workspace và tiến trình AI Video Localizer "
                        "qua adapter độc lập. Chỉ đọc."
                    ),
                    parameters={
                        "type": "object",
                        "properties": {},
                        "additionalProperties": False,
                    },
                    handler=self._ai_video_localizer_status,
                ),
                ToolSpec(
                    name="ai_video_localizer_launch",
                    description=(
                        "Mở AI Video Localizer bằng executable đã cấu hình trong adapter. "
                        "Không sửa source của ứng dụng đích."
                    ),
                    parameters={
                        "type": "object",
                        "properties": {},
                        "additionalProperties": False,
                    },
                    handler=self._ai_video_localizer_launch,
                ),
                ToolSpec(
                    name="read_code_file",
                    description=(
                        "Đọc một file văn bản trong workspace để phân tích code. "
                        "Không đọc secret hoặc file ngoài workspace."
                    ),
                    parameters={
                        "type": "object",
                        "properties": {
                            "path": {
                                "type": "string",
                                "description": "Đường dẫn tương đối trong workspace.",
                            },
                            "max_chars": {
                                "type": "integer",
                                "minimum": 100,
                                "maximum": 100000,
                                "description": "Số ký tự tối đa cần đọc.",
                            },
                        },
                        "required": ["path"],
                        "additionalProperties": False,
                    },
                    handler=self._read_code_file,
                ),
                ToolSpec(
                    name="search_code",
                    description=(
                        "Tìm chuỗi trong các file code/text của workspace và trả về "
                        "file, dòng và nội dung khớp."
                    ),
                    parameters={
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "Chuỗi cần tìm.",
                            },
                            "path": {
                                "type": "string",
                                "description": "Thư mục hoặc file tương đối cần tìm.",
                            },
                            "case_sensitive": {
                                "type": "boolean",
                                "description": "Phân biệt chữ hoa/chữ thường.",
                            },
                            "limit": {
                                "type": "integer",
                                "minimum": 1,
                                "maximum": 100,
                                "description": "Số kết quả tối đa.",
                            },
                        },
                        "required": ["query"],
                        "additionalProperties": False,
                    },
                    handler=self._search_code,
                ),
                ToolSpec(
                    name="replace_code",
                    description=(
                        "Thay một đoạn text duy nhất trong file code. Tool tự tạo "
                        "checkpoint file trước khi ghi và trả checkpoint_id để rollback."
                    ),
                    parameters={
                        "type": "object",
                        "properties": {
                            "path": {
                                "type": "string",
                                "description": "File tương đối trong workspace.",
                            },
                            "old_text": {
                                "type": "string",
                                "description": "Đoạn text hiện tại, phải xuất hiện đúng một lần.",
                            },
                            "new_text": {
                                "type": "string",
                                "description": "Đoạn text thay thế.",
                            },
                        },
                        "required": ["path", "old_text", "new_text"],
                        "additionalProperties": False,
                    },
                    handler=self._replace_code,
                ),
                ToolSpec(
                    name="create_code_file",
                    description=(
                        "Tạo file code/text mới trong workspace. Không ghi đè file đã có."
                    ),
                    parameters={
                        "type": "object",
                        "properties": {
                            "path": {
                                "type": "string",
                                "description": "File mới tương đối trong workspace.",
                            },
                            "content": {
                                "type": "string",
                                "description": "Nội dung file.",
                            },
                        },
                        "required": ["path", "content"],
                        "additionalProperties": False,
                    },
                    handler=self._create_code_file,
                ),
                ToolSpec(
                    name="git_status",
                    description="Đọc trạng thái và nhánh Git của workspace.",
                    parameters={
                        "type": "object",
                        "properties": {},
                        "additionalProperties": False,
                    },
                    handler=self._git_status,
                ),
                ToolSpec(
                    name="git_diff",
                    description="Đọc diff Git hiện tại của workspace hoặc một file.",
                    parameters={
                        "type": "object",
                        "properties": {
                            "path": {
                                "type": "string",
                                "description": "File tương đối cần xem diff; bỏ trống để xem toàn bộ.",
                            },
                        },
                        "additionalProperties": False,
                    },
                    handler=self._git_diff,
                ),
                ToolSpec(
                    name="run_code_check",
                    description=(
                        "Chạy kiểm tra được allowlist: compile, pytest hoặc git_diff_check. "
                        "Không chạy shell command tùy ý."
                    ),
                    parameters={
                        "type": "object",
                        "properties": {
                            "kind": {
                                "type": "string",
                                "enum": ["compile", "pytest", "git_diff_check"],
                                "description": "Loại kiểm tra.",
                            },
                            "path": {
                                "type": "string",
                                "description": "File/thư mục test hoặc compile; mặc định workspace.",
                            },
                        },
                        "required": ["kind"],
                        "additionalProperties": False,
                    },
                    handler=self._run_code_check,
                ),
                ToolSpec(
                    name="create_checkpoint",
                    description=(
                        "Lưu snapshot các file code trước khi thay đổi. Có thể dùng "
                        "checkpoint_id để khôi phục."
                    ),
                    parameters={
                        "type": "object",
                        "properties": {
                            "paths": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Danh sách file/thư mục tương đối; mặc định các thư mục code chính.",
                            },
                        },
                        "additionalProperties": False,
                    },
                    handler=self._create_checkpoint,
                ),
                ToolSpec(
                    name="restore_checkpoint",
                    description="Khôi phục các file đã lưu trong một checkpoint.",
                    parameters={
                        "type": "object",
                        "properties": {
                            "checkpoint_id": {
                                "type": "string",
                                "description": "ID checkpoint do create_checkpoint trả về.",
                            },
                        },
                        "required": ["checkpoint_id"],
                        "additionalProperties": False,
                    },
                    handler=self._restore_checkpoint,
                ),
                ToolSpec(
                    name="web_search",
                    description=(
                        "Tìm kiếm thông tin mới trên Internet bằng query. Dùng khi "
                        "cần tìm repo, tài liệu, package hoặc hướng giải quyết. Chỉ đọc."
                    ),
                    parameters={
                        "type": "object",
                        "properties": {
                            "query": {"type": "string", "description": "Từ khóa tìm kiếm."},
                            "limit": {"type": "integer", "minimum": 1, "maximum": 10},
                            "domain": {"type": "string", "description": "Giới hạn domain nếu cần."},
                        },
                        "required": ["query"],
                        "additionalProperties": False,
                    },
                    handler=self._web_search,
                ),
                ToolSpec(
                    name="bilibili_search",
                    description=(
                        "Tìm trực tiếp video trên Bilibili bằng từ khóa và trả về "
                        "tiêu đề cùng URL. Chỉ đọc."
                    ),
                    parameters={
                        "type": "object",
                        "properties": {
                            "query": {"type": "string", "description": "Từ khóa tìm video."},
                            "limit": {"type": "integer", "minimum": 1, "maximum": 10},
                        },
                        "required": ["query"],
                        "additionalProperties": False,
                    },
                    handler=self._bilibili_search,
                ),
                ToolSpec(
                    name="douyin_search",
                    description=(
                        "Tìm trực tiếp video trên Douyin bằng từ khóa và trả về "
                        "tiêu đề cùng URL. Chỉ đọc."
                    ),
                    parameters={
                        "type": "object",
                        "properties": {
                            "query": {"type": "string", "description": "Từ khóa tìm video."},
                            "limit": {"type": "integer", "minimum": 1, "maximum": 10},
                        },
                        "required": ["query"],
                        "additionalProperties": False,
                    },
                    handler=self._douyin_search,
                ),
                ToolSpec(
                    name="youtube_search",
                    description=(
                        "Tìm trực tiếp video trên YouTube bằng từ khóa và trả về "
                        "tiêu đề cùng URL. Chỉ đọc."
                    ),
                    parameters={
                        "type": "object",
                        "properties": {
                            "query": {"type": "string", "description": "Từ khóa tìm video."},
                            "limit": {"type": "integer", "minimum": 1, "maximum": 10},
                        },
                        "required": ["query"],
                        "additionalProperties": False,
                    },
                    handler=self._youtube_search,
                ),
                ToolSpec(
                    name="web_open",
                    description=(
                        "Mở và đọc nội dung một URL http/https để lấy hướng dẫn hoặc "
                        "chi tiết kỹ thuật. Chỉ đọc, không thực thi code từ trang."
                    ),
                    parameters={
                        "type": "object",
                        "properties": {
                            "url": {"type": "string", "description": "URL http/https."},
                            "max_chars": {"type": "integer", "minimum": 500, "maximum": 50000},
                        },
                        "required": ["url"],
                        "additionalProperties": False,
                    },
                    handler=self._web_open,
                ),
                ToolSpec(
                    name="search_github_repositories",
                    description=(
                        "Tìm repo public trên GitHub theo query, sắp xếp theo độ phù hợp/stars. "
                        "Dùng khi repo người dùng nêu không tồn tại hoặc cần tìm phương án thay thế."
                    ),
                    parameters={
                        "type": "object",
                        "properties": {
                            "query": {"type": "string", "description": "Query GitHub repository search."},
                            "language": {"type": "string", "description": "Ngôn ngữ tùy chọn, ví dụ TypeScript."},
                            "limit": {"type": "integer", "minimum": 1, "maximum": 10},
                        },
                        "required": ["query"],
                        "additionalProperties": False,
                    },
                    handler=self._search_github_repositories,
                ),
                ToolSpec(
                    name="run_workspace_command",
                    description=(
                        "Chạy một lệnh workspace dạng argv có allowlist executable để install, "
                        "build, test hoặc chạy script trong repo. Không hỗ trợ shell operators, "
                        "PowerShell command tùy ý hay đường dẫn ngoài workspace."
                    ),
                    parameters={
                        "type": "object",
                        "properties": {
                            "command": {
                                "type": "array",
                                "items": {"type": "string"},
                                "minItems": 1,
                                "maxItems": 30,
                                "description": "argv, ví dụ ['npm','run','build'] hoặc ['python','-m','pytest'].",
                            },
                            "cwd": {
                                "type": "string",
                                "description": "Thư mục tương đối trong workspace; mặc định root repo.",
                            },
                            "timeout": {"type": "integer", "minimum": 1, "maximum": 3600},
                        },
                        "required": ["command"],
                        "additionalProperties": False,
                    },
                    handler=self._run_workspace_command,
                ),
                ToolSpec(
                    name="inspect_github_repository",
                    description=(
                        "Kiểm tra repo GitHub public trước khi cài: xác nhận tồn tại, "
                        "mô tả, ngôn ngữ và file gốc. Chỉ đọc, không clone."
                    ),
                    parameters={
                        "type": "object",
                        "properties": {
                            "repository": {
                                "type": "string",
                                "description": "URL github.com/owner/repo hoặc owner/repo.",
                            },
                        },
                        "required": ["repository"],
                        "additionalProperties": False,
                    },
                    handler=self._inspect_github_repository,
                ),
                ToolSpec(
                    name="inspect_npm_package",
                    description=(
                        "Kiểm tra package public trên npm trước khi cài: xác nhận tồn tại, "
                        "version mới nhất và mô tả. Chỉ đọc."
                    ),
                    parameters={
                        "type": "object",
                        "properties": {
                            "package": {
                                "type": "string",
                                "description": "Tên package npm, có thể kèm @version.",
                            },
                        },
                        "required": ["package"],
                        "additionalProperties": False,
                    },
                    handler=self._inspect_npm_package,
                ),
                ToolSpec(
                    name="install_github_repository",
                    description=(
                        "Clone repo GitHub public vào work/auto_pilot/external và cài "
                        "dependency theo allowlist npm hoặc Python. Không tự chạy ứng dụng. "
                        "Phải inspect_github_repository trước."
                    ),
                    parameters={
                        "type": "object",
                        "properties": {
                            "repository": {
                                "type": "string",
                                "description": "URL github.com/owner/repo hoặc owner/repo.",
                            },
                            "destination": {
                                "type": "string",
                                "description": "Thư mục tương đối dưới work/auto_pilot/external; bỏ trống để tự đặt tên.",
                            },
                            "package_manager": {
                                "type": "string",
                                "enum": ["auto", "npm", "python", "none"],
                                "description": "Cách cài dependency; auto tự nhận dạng package.json/requirements.txt.",
                            },
                            "install_dependencies": {
                                "type": "boolean",
                                "description": "Có cài dependency hay chỉ clone repo.",
                            },
                        },
                        "required": ["repository"],
                        "additionalProperties": False,
                    },
                    handler=self._install_github_repository,
                ),
                ToolSpec(
                    name="install_npm_package",
                    description=(
                        "Tạo thư mục npm cô lập trong work/auto_pilot/external/npm và cài "
                        "một package public bằng npm --ignore-scripts. Phải inspect_npm_package trước."
                    ),
                    parameters={
                        "type": "object",
                        "properties": {
                            "package": {
                                "type": "string",
                                "description": "Tên package npm, có thể kèm @version.",
                            },
                        },
                        "required": ["package"],
                        "additionalProperties": False,
                    },
                    handler=self._install_npm_package,
                ),
                ToolSpec(
                    name="run_project_stage",
                    description=(
                        "Chạy một stage được allowlist cho project theo ID. Đây là "
                        "thao tác ghi file và có thể chạy lâu; chỉ gọi khi người dùng "
                        "yêu cầu xử lý project rõ ràng."
                    ),
                    parameters={
                        "type": "object",
                        "properties": {
                            "project_id": {
                                "type": "string",
                                "description": "ID 8 ký tự của project.",
                            },
                            "stage": {
                                "type": "string",
                                "enum": [
                                    "transcribe",
                                    "translate",
                                    "tts",
                                    "merge_export",
                                    "export",
                                    "finalize",
                                ],
                                "description": "Stage cần chạy.",
                            },
                        },
                        "required": ["project_id", "stage"],
                        "additionalProperties": False,
                    },
                    handler=self._run_project_stage,
                ),
            )
        }

    def definitions(self) -> list[dict[str, Any]]:
        return [
            spec.definition()
            for spec in self._specs.values()
        ]

    def execute(
        self,
        name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        spec = self._specs.get(name)

        if spec is None:
            return {
                "ok": False,
                "error": f"Tool không được phép: {name}",
            }

        if not isinstance(arguments, dict):
            return {
                "ok": False,
                "error": "Tham số tool phải là object JSON.",
            }

        try:
            result = spec.handler(arguments)
        except Exception as error:
            return {
                "ok": False,
                "error": str(error),
            }

        return {
            "ok": True,
            "result": result,
        }

    def _list_projects(
        self,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        limit = _bounded_int(
            arguments.get("limit", 20),
            minimum=1,
            maximum=50,
        )
        projects = load_all_projects()[:limit]

        return {
            "count": len(projects),
            "projects": [
                _project_summary(project)
                for project in projects
            ],
        }

    def _get_project(
        self,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        project_id = _required_text(
            arguments.get("project_id"),
            "project_id",
        )

        project = _find_project(project_id)

        if project is None:
            raise ValueError(
                f"Không tìm thấy project có ID: {project_id}"
            )

        return _project_summary(
            project,
            include_settings=True,
        )

    def _download_bilibili(
        self,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        url = _required_text(arguments.get("url"), "url")

        if detect_platform(url) != Platform.BILIBILI:
            raise ValueError(
                "Tool này chỉ nhận URL Bilibili hoặc b23.tv."
            )

        destination_name = str(
            arguments.get("destination", "downloads")
        ).strip().lower()
        destination_map = {
            "downloads": APP_ROOT / "downloads",
            "input": APP_ROOT / "input",
        }
        output_dir = destination_map.get(destination_name)

        if output_dir is None:
            raise ValueError(
                "destination phải là downloads hoặc input."
            )

        progress: list[str] = []
        downloader = VideoDownloader(
            progress_callback=progress.append,
        )
        result = downloader.download(
            DownloadRequest(
                url=url,
                output_dir=output_dir,
                max_height=_optional_height(
                    arguments.get("max_height")
                ),
                prefer_h264=_as_bool(
                    arguments.get("prefer_h264", False)
                ),
                use_cookie=_as_bool(
                    arguments.get("use_cookie", True)
                ),
                download_playlist=_as_bool(
                    arguments.get("download_playlist", False)
                ),
            )
        )

        paths = [
            str(path)
            for path in (result.video_paths or [result.video_path])
            if path is not None
        ]

        return {
            "platform": str(result.platform),
            "video_paths": paths,
            "metadata_path": (
                str(result.metadata_path)
                if result.metadata_path is not None
                else None
            ),
            "playlist_dir": (
                str(result.playlist_dir)
                if result.playlist_dir is not None
                else None
            ),
            "last_progress": progress[-40:],
        }

    def _create_project(
        self,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        video_path = _safe_video_path(
            _required_text(
                arguments.get("video_path"),
                "video_path",
            )
        )
        project = VideoProject.create(video_path)

        return _project_summary(project)

    def _list_directory(
        self,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        directory = _safe_app_path(arguments.get("path", "."))
        if not directory.is_dir():
            raise NotADirectoryError(f"Không phải thư mục: {directory}")

        recursive = _as_bool(arguments.get("recursive", False))
        limit = _bounded_int(
            arguments.get("limit", 100),
            minimum=1,
            maximum=200,
        )
        entries = directory.rglob("*") if recursive else directory.iterdir()
        results: list[dict[str, Any]] = []

        for entry in sorted(entries, key=lambda item: str(item).lower()):
            if len(results) >= limit:
                break
            try:
                results.append({
                    "path": str(entry.relative_to(APP_ROOT)),
                    "type": "directory" if entry.is_dir() else "file",
                    "size": entry.stat().st_size if entry.is_file() else None,
                })
            except OSError:
                continue

        return {
            "path": str(directory.relative_to(APP_ROOT)),
            "recursive": recursive,
            "count": len(results),
            "entries": results,
        }

    def _get_system_status(
        self,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        memory = psutil.virtual_memory()
        disk = shutil.disk_usage(APP_ROOT)
        ports: list[int] = []

        try:
            ports = sorted({
                connection.laddr.port
                for connection in psutil.net_connections(kind="tcp")
                if connection.status == psutil.CONN_LISTEN
                and connection.laddr
                and connection.pid
                and _is_llama_server(connection.pid)
            })
        except psutil.Error:
            ports = []

        return {
            "cpu_percent": psutil.cpu_percent(interval=0.2),
            "ram": {
                "total_bytes": memory.total,
                "available_bytes": memory.available,
                "percent": memory.percent,
            },
            "disk": {
                "free_bytes": disk.free,
                "total_bytes": disk.total,
                "percent_used": round(
                    (disk.total - disk.free) * 100 / disk.total,
                    2,
                ) if disk.total else 0,
            },
            "llama_server_ports": ports,
        }

    def _get_resource_status(
        self,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        from llm.resource_manager import GPUResourceManager

        return GPUResourceManager().status()

    def _screen_capture(
        self,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        from agent.screen_tools import screen_capture

        return screen_capture(
            x=_optional_int(arguments.get("x")),
            y=_optional_int(arguments.get("y")),
            width=_optional_int(arguments.get("width")),
            height=_optional_int(arguments.get("height")),
        )

    def _screen_ocr(
        self,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        from agent.screen_tools import screen_ocr

        confidence = float(arguments.get("min_confidence", 0.35))
        if not 0 <= confidence <= 1:
            raise ValueError("min_confidence phải nằm trong khoảng 0 đến 1.")
        return screen_ocr(
            image_path=str(arguments.get("image_path", "")),
            x=_optional_int(arguments.get("x")),
            y=_optional_int(arguments.get("y")),
            width=_optional_int(arguments.get("width")),
            height=_optional_int(arguments.get("height")),
            min_confidence=confidence,
        )

    def _list_processes(
        self,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        from agent.process_tools import list_processes

        return list_processes(
            name=str(arguments.get("name", "")),
            limit=_bounded_int(
                arguments.get("limit", 50),
                minimum=1,
                maximum=100,
            ),
        )

    def _read_runtime_log(
        self,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        from agent.process_tools import read_log

        return read_log(
            _required_text(arguments.get("path"), "path"),
            lines=_bounded_int(
                arguments.get("lines", 200),
                minimum=1,
                maximum=1000,
            ),
        )

    def _stop_managed_process(
        self,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        from agent.process_tools import stop_managed_process

        pid = _bounded_int(
            arguments.get("pid"),
            minimum=1,
            maximum=2**31 - 1,
        )
        return stop_managed_process(pid)

    def _browser_open(
        self,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        from agent.browser_tools import browser_open

        return browser_open(
            _required_text(arguments.get("url"), "url"),
            headless=_as_bool(arguments.get("headless", False)),
            wait_ms=_bounded_int(
                arguments.get("wait_ms", 1000),
                minimum=0,
                maximum=10000,
            ),
        )

    def _browser_snapshot(
        self,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        from agent.browser_tools import browser_snapshot

        return browser_snapshot(
            max_chars=_bounded_int(
                arguments.get("max_chars", 12000),
                minimum=100,
                maximum=30000,
            )
        )

    def _browser_click(
        self,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        from agent.browser_tools import browser_click

        return browser_click(
            selector=str(arguments.get("selector", "")),
            text=str(arguments.get("text", "")),
            wait_ms=_bounded_int(
                arguments.get("wait_ms", 500),
                minimum=0,
                maximum=10000,
            ),
        )

    def _browser_type(
        self,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        from agent.browser_tools import browser_type

        return browser_type(
            str(arguments.get("value", "")),
            selector=str(arguments.get("selector", "")),
            text=str(arguments.get("text", "")),
            press_enter=_as_bool(arguments.get("press_enter", False)),
        )

    def _browser_extract(
        self,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        from agent.browser_tools import browser_extract

        return browser_extract(
            selector=str(arguments.get("selector", "")),
            max_chars=_bounded_int(
                arguments.get("max_chars", 12000),
                minimum=100,
                maximum=30000,
            ),
        )

    def _browser_screenshot(
        self,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        from agent.browser_tools import browser_screenshot

        return browser_screenshot()

    def _browser_close(
        self,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        from agent.browser_tools import browser_close

        return browser_close()

    def _ui_list_windows(
        self,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        from agent.windows_tools import ui_list_windows

        return ui_list_windows(
            limit=_bounded_int(
                arguments.get("limit", 50),
                minimum=1,
                maximum=100,
            )
        )

    def _ui_snapshot(
        self,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        from agent.windows_tools import ui_snapshot

        return ui_snapshot(
            _required_text(arguments.get("window_title"), "window_title"),
            limit=_bounded_int(
                arguments.get("limit", 100),
                minimum=1,
                maximum=200,
            ),
        )

    def _ui_click(
        self,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        from agent.windows_tools import ui_click

        return ui_click(
            _required_text(arguments.get("window_title"), "window_title"),
            control_title=str(arguments.get("control_title", "")),
            automation_id=str(arguments.get("automation_id", "")),
            control_type=str(arguments.get("control_type", "")),
        )

    def _ui_type(
        self,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        from agent.windows_tools import ui_type

        return ui_type(
            _required_text(arguments.get("window_title"), "window_title"),
            str(arguments.get("value", "")),
            control_title=str(arguments.get("control_title", "")),
            automation_id=str(arguments.get("automation_id", "")),
            control_type=str(arguments.get("control_type", "Edit")),
            press_enter=_as_bool(arguments.get("press_enter", False)),
        )

    def _ui_press_key(
        self,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        from agent.windows_tools import ui_press_key

        return ui_press_key(
            _required_text(arguments.get("window_title"), "window_title"),
            _required_text(arguments.get("key"), "key"),
            control_title=str(arguments.get("control_title", "")),
            automation_id=str(arguments.get("automation_id", "")),
            control_type=str(arguments.get("control_type", "")),
        )

    def _ai_video_localizer_status(
        self,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        from adapters.ai_video_localizer import AIVideoLocalizerTarget

        return AIVideoLocalizerTarget.from_environment().status()

    def _ai_video_localizer_launch(
        self,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        from adapters.ai_video_localizer import AIVideoLocalizerTarget

        return AIVideoLocalizerTarget.from_environment().launch()

    def _launch_application(
        self,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        path = _safe_application_path(arguments.get("path"))
        args = arguments.get("args", [])
        if not isinstance(args, list) or len(args) > 20:
            raise ValueError("args phải là danh sách tối đa 20 phần tử.")
        process = subprocess.Popen(
            [str(path), *(str(value) for value in args)],
            cwd=str(path.parent),
            close_fds=True,
        )
        return {"started": True, "pid": process.pid, "path": str(path)}

    def _read_code_file(
        self,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        path = _safe_code_path(arguments.get("path"), must_exist=True)
        if not path.is_file():
            raise IsADirectoryError(f"Không phải file: {path}")
        max_chars = _bounded_int(
            arguments.get("max_chars", 30000),
            minimum=100,
            maximum=100000,
        )
        content = path.read_text(encoding="utf-8", errors="replace")
        return {
            "path": str(path.relative_to(APP_ROOT)),
            "truncated": len(content) > max_chars,
            "content": content[:max_chars],
        }

    def _search_code(
        self,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        query = _required_text(arguments.get("query"), "query")
        root = _safe_code_path(arguments.get("path", "."), must_exist=True)
        case_sensitive = _as_bool(arguments.get("case_sensitive", False))
        limit = _bounded_int(
            arguments.get("limit", 50),
            minimum=1,
            maximum=100,
        )
        needle = query if case_sensitive else query.lower()
        matches: list[dict[str, Any]] = []

        for path in _iter_code_files(root):
            if len(matches) >= limit:
                break
            try:
                if path.stat().st_size > 2 * 1024 * 1024:
                    continue
                lines = path.read_text(
                    encoding="utf-8",
                    errors="replace",
                ).splitlines()
            except OSError:
                continue
            for line_number, line in enumerate(lines, start=1):
                haystack = line if case_sensitive else line.lower()
                if needle in haystack:
                    matches.append({
                        "path": str(path.relative_to(APP_ROOT)),
                        "line": line_number,
                        "text": line[:500],
                    })
                    if len(matches) >= limit:
                        break

        return {
            "query": query,
            "count": len(matches),
            "matches": matches,
        }

    def _replace_code(
        self,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        path = _safe_code_path(arguments.get("path"), must_exist=True)
        if not path.is_file():
            raise IsADirectoryError(f"Không phải file: {path}")
        old_text = str(arguments.get("old_text", ""))
        new_text = str(arguments.get("new_text", ""))
        if not old_text:
            raise ValueError("old_text không được để trống.")
        content = path.read_text(encoding="utf-8", errors="replace")
        occurrences = content.count(old_text)
        if occurrences != 1:
            raise ValueError(
                f"old_text phải xuất hiện đúng một lần, hiện có {occurrences} lần."
            )
        checkpoint = _create_checkpoint_for_paths([path])
        path.write_text(
            content.replace(old_text, new_text),
            encoding="utf-8",
        )
        return {
            "path": str(path.relative_to(APP_ROOT)),
            "checkpoint_id": checkpoint,
            "changed": True,
        }

    def _create_code_file(
        self,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        path = _safe_code_path(arguments.get("path"), must_exist=False)
        if path.exists():
            raise FileExistsError(f"File đã tồn tại: {path}")
        if path.suffix.lower() not in CODE_EXTENSIONS:
            raise ValueError("Chỉ được tạo file code/text được hỗ trợ.")
        content = str(arguments.get("content", ""))
        if len(content) > 500000:
            raise ValueError("Nội dung file vượt quá 500000 ký tự.")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return {
            "path": str(path.relative_to(APP_ROOT)),
            "created": True,
        }

    def _git_status(
        self,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        return _run_workspace_process(
            ["git", "status", "--short", "--branch"],
            timeout=30,
        )

    def _git_diff(
        self,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        command = ["git", "diff", "--"]
        raw_path = str(arguments.get("path", "")).strip()
        if raw_path:
            path = _safe_code_path(raw_path, must_exist=True)
            command.append(str(path.relative_to(APP_ROOT)))
        result = _run_workspace_process(command, timeout=60)
        result["diff"] = result.pop("output")
        return result

    def _run_code_check(
        self,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        kind = _required_text(arguments.get("kind"), "kind").lower()
        raw_path = str(arguments.get("path", "")).strip()
        path = _safe_code_path(raw_path, must_exist=True) if raw_path else APP_ROOT
        if kind == "compile":
            if not raw_path:
                command = [
                    sys.executable,
                    "-m",
                    "compileall",
                    "-q",
                    "agent",
                    "core",
                    "llm",
                    "scripts",
                    "ui",
                ]
            else:
                command = [
                    sys.executable,
                    "-m",
                    "py_compile" if path.is_file() else "compileall",
                ]
                if not path.is_file():
                    command.append("-q")
                command.append(str(path))
            timeout = 300
        elif kind == "pytest":
            command = [sys.executable, "-m", "pytest", str(path)]
            timeout = 1800
        elif kind == "git_diff_check":
            command = ["git", "diff", "--check"]
            timeout = 60
        else:
            raise ValueError(f"Loại kiểm tra không được phép: {kind}")
        result = _run_workspace_process(command, timeout=timeout)
        result["kind"] = kind
        return result

    def _create_checkpoint(
        self,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        raw_paths = arguments.get("paths")
        if raw_paths is None:
            paths = ["agent", "core", "llm", "scripts", "ui"]
        elif isinstance(raw_paths, list) and raw_paths:
            paths = [str(path) for path in raw_paths]
        else:
            raise ValueError("paths phải là một mảng không rỗng.")
        checkpoint_id, count = _create_checkpoint(paths)
        return {
            "checkpoint_id": checkpoint_id,
            "file_count": count,
        }

    def _restore_checkpoint(
        self,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        checkpoint_id = _required_text(
            arguments.get("checkpoint_id"),
            "checkpoint_id",
        )
        return _restore_checkpoint(checkpoint_id)

    def _web_search(
        self,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        query = _required_text(arguments.get("query"), "query")
        limit = _bounded_int(arguments.get("limit", 5), minimum=1, maximum=10)
        domain = str(arguments.get("domain", "")).strip()
        search_query = f"site:{domain} {query}" if domain else query
        try:
            response = requests.get(
                "https://html.duckduckgo.com/html/",
                params={"q": search_query},
                headers={"User-Agent": "M-Auto-Pilot/1.0"},
                timeout=30,
            )
            response.raise_for_status()
            parser = _DuckDuckGoParser(limit)
            parser.feed(response.text)
            if parser.results:
                return {
                    "query": query,
                    "count": len(parser.results),
                    "results": parser.results[:limit],
                }
        except (requests.RequestException, ValueError):
            pass

        response = requests.get(
            "https://www.bing.com/search",
            params={"format": "rss", "q": search_query},
            headers={
                "User-Agent": "M-Auto-Pilot/1.0",
                "Accept-Language": "vi-VN,vi;q=0.9,en;q=0.8",
            },
            timeout=30,
        )
        response.raise_for_status()
        root = ET.fromstring(response.text)
        results = []
        for item in root.findall(".//item"):
            url = str(item.findtext("link") or "").strip()
            if not url.startswith(("http://", "https://")):
                continue
            results.append({
                "title": " ".join(str(item.findtext("title") or "").split()),
                "url": url,
                "snippet": " ".join(str(item.findtext("description") or "").split()),
            })
            if len(results) >= limit:
                break
        return {
            "query": query,
            "count": len(results),
            "results": results,
        }

    def _youtube_search(
        self,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        query = _required_text(arguments.get("query"), "query")
        limit = _bounded_int(arguments.get("limit", 5), minimum=1, maximum=10)
        response = requests.get(
            "https://www.youtube.com/results",
            params={"search_query": query},
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131 Safari/537.36",
                "Accept-Language": "vi-VN,vi;q=0.9,en;q=0.8",
            },
            timeout=30,
        )
        response.raise_for_status()
        pattern = re.compile(
            r'"videoId":"([^"]+)".{0,1200}?"title":\{"runs":\[\{"text":"(.*?)"',
            re.DOTALL,
        )
        results: list[dict[str, str]] = []
        seen: set[str] = set()
        for video_id, raw_title in pattern.findall(response.text):
            if video_id in seen:
                continue
            seen.add(video_id)
            try:
                title = json.loads(f'"{raw_title}"')
            except json.JSONDecodeError:
                title = raw_title
            results.append({
                "title": " ".join(str(title).split()),
                "url": f"https://www.youtube.com/watch?v={video_id}",
                "video_id": video_id,
            })
            if len(results) >= limit:
                break
        return {
            "query": query,
            "count": len(results),
            "results": results,
        }

    def _bilibili_search(
        self,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        query = _required_text(arguments.get("query"), "query")
        limit = _bounded_int(arguments.get("limit", 5), minimum=1, maximum=10)
        queries = []
        lowered = query.lower()
        translations = {
            "thức tỉnh hệ thống": "觉醒 系统",
            "hệ thống": "系统",
            "tu tiên": "修仙",
            "xuyên không": "穿越",
            "truyện tranh": "漫画",
            "phim hoạt hình": "动画",
        }
        for source, translated in translations.items():
            if source in lowered:
                candidate = lowered.replace(source, translated)
                if candidate not in queries:
                    queries.append(candidate)
        if query not in queries:
            queries.append(query)
        for search_query in queries:
            response = requests.get(
                "https://www.bing.com/search",
                params={
                    "format": "rss",
                    "q": f"site:bilibili.com/video {search_query}",
                },
                headers={
                    "User-Agent": "M-Auto-Pilot/1.0",
                    "Accept-Language": "vi-VN,vi;q=0.9,en;q=0.8",
                },
                timeout=30,
            )
            response.raise_for_status()
            root = ET.fromstring(response.text)
            results = []
            for item in root.findall(".//item"):
                url = str(item.findtext("link") or "").strip()
                if "bilibili.com/video/" not in url:
                    continue
                results.append({
                    "title": " ".join(str(item.findtext("title") or "").split()),
                    "url": url,
                    "snippet": " ".join(str(item.findtext("description") or "").split()),
                })
                if len(results) >= limit:
                    break
            if results:
                return {
                    "query": search_query,
                    "count": len(results),
                    "results": results,
                }
        return {"query": query, "count": 0, "results": []}

    def _douyin_search(
        self,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        query = _required_text(arguments.get("query"), "query")
        limit = _bounded_int(arguments.get("limit", 5), minimum=1, maximum=10)
        translated = {
            "thức tỉnh hệ thống": "觉醒 系统",
            "hệ thống": "系统",
            "tu tiên": "修仙",
            "xuyên không": "穿越",
            "truyện tranh": "漫画",
        }
        queries = [translated.get(query.lower(), query)]
        if query not in queries:
            queries.append(query)
        for search_query in queries:
            response = requests.get(
                "https://www.bing.com/search",
                params={
                    "q": f"site:douyin.com/video {search_query}",
                    "count": 20,
                },
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131 Safari/537.36",
                    "Accept-Language": "zh-CN,zh;q=0.9",
                },
                timeout=30,
            )
            response.raise_for_status()
            blocks = re.findall(
                r"<li[^>]+class=[\"'][^\"']*b_algo[^\"']*[\"'][^>]*>.*?</li>",
                response.text,
                flags=re.IGNORECASE | re.DOTALL,
            )
            results: list[dict[str, str]] = []
            for block in blocks:
                match = re.search(
                    r"<h2[^>]*>\s*<a[^>]+href=[\"']([^\"']+)[\"'][^>]*>(.*?)</a>",
                    block,
                    flags=re.IGNORECASE | re.DOTALL,
                )
                if not match:
                    continue
                url = unquote(match.group(1)).strip()
                host = urlparse(url).netloc.lower()
                path = urlparse(url).path.lower()
                if not (host.endswith("douyin.com") and "/video/" in path):
                    continue
                title = re.sub(r"<[^>]+>", " ", match.group(2))
                snippet = re.sub(r"<[^>]+>", " ", block)
                snippet = " ".join(snippet.split())
                results.append({
                    "title": " ".join(title.split()),
                    "url": url,
                    "snippet": snippet[:500],
                })
                if len(results) >= limit:
                    break
            if results:
                return {
                    "query": search_query,
                    "count": len(results),
                    "results": results,
                }
        return {
            "query": query,
            "count": 1,
            "results": [{
                "title": f"Mở tìm kiếm Douyin cho: {query}",
                "url": f"https://www.douyin.com/search/{quote(query)}?type=general",
                "snippet": "Bing không trả về trang video Douyin công khai; có thể mở trang tìm kiếm để xem kết quả đầy đủ.",
            }],
        }

    def _web_open(
        self,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        url = _required_text(arguments.get("url"), "url")
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("Chỉ hỗ trợ URL http/https.")
        max_chars = _bounded_int(
            arguments.get("max_chars", 20000),
            minimum=500,
            maximum=50000,
        )
        response = requests.get(
            url,
            headers={"User-Agent": "M-Auto-Pilot/1.0"},
            timeout=30,
        )
        response.raise_for_status()
        content_type = response.headers.get("content-type", "")
        if "html" in content_type.lower():
            parser = _WebTextParser()
            parser.feed(response.text)
            content = parser.text()
        else:
            content = response.text
        return {
            "url": response.url,
            "status_code": response.status_code,
            "content_type": content_type,
            "content": content[:max_chars],
            "truncated": len(content) > max_chars,
        }

    def _search_github_repositories(
        self,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        query = _required_text(arguments.get("query"), "query")
        language = str(arguments.get("language", "")).strip()
        limit = _bounded_int(arguments.get("limit", 5), minimum=1, maximum=10)
        search_query = query + (f" language:{language}" if language else "")
        response = requests.get(
            "https://api.github.com/search/repositories",
            params={
                "q": search_query,
                "sort": "stars",
                "order": "desc",
                "per_page": limit,
            },
            headers={
                "Accept": "application/vnd.github+json",
                "User-Agent": "M-Auto-Pilot",
            },
            timeout=30,
        )
        response.raise_for_status()
        items = response.json().get("items") or []
        return {
            "query": search_query,
            "count": len(items),
            "results": [
                {
                    "full_name": item.get("full_name"),
                    "html_url": item.get("html_url"),
                    "description": item.get("description"),
                    "language": item.get("language"),
                    "stars": item.get("stargazers_count"),
                    "updated_at": item.get("updated_at"),
                }
                for item in items[:limit]
            ],
        }

    def _run_workspace_command(
        self,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        command = arguments.get("command")
        if not isinstance(command, list) or not command or len(command) > 30:
            raise ValueError("command phải là argv không rỗng, tối đa 30 phần tử.")
        if not all(isinstance(item, str) and item.strip() for item in command):
            raise ValueError("Mỗi phần tử command phải là chuỗi không rỗng.")
        if any(any(marker in item for marker in ("\r", "\n", "&&", "||", "<", ">")) for item in command):
            raise ValueError("Không cho phép shell operator trong command.")
        executable = Path(command[0]).name.lower()
        if executable not in ALLOWED_WORKSPACE_EXECUTABLES:
            raise ValueError(f"Executable chưa được allowlist: {executable}")
        if not Path(command[0]).is_absolute() and not shutil.which(command[0]):
            raise FileNotFoundError(f"Không tìm thấy executable: {command[0]}")
        cwd = _workspace_cwd(arguments.get("cwd"))
        timeout = _bounded_int(arguments.get("timeout", 300), minimum=1, maximum=3600)
        result = _run_workspace_process(command, timeout=timeout, cwd=cwd)
        result.update({
            "command": command,
            "cwd": str(cwd.relative_to(APP_ROOT)),
        })
        return result

    def _inspect_github_repository(
        self,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        owner, repo = _parse_github_repository(arguments.get("repository"))
        metadata = _github_api(f"/repos/{owner}/{repo}")
        contents = _github_api(
            f"/repos/{owner}/{repo}/contents?ref={quote(str(metadata.get('default_branch') or 'main'))}"
        )
        files = [
            str(item.get("name"))
            for item in contents
            if isinstance(item, dict) and item.get("name")
        ] if isinstance(contents, list) else []
        license_data = metadata.get("license") or {}
        return {
            "exists": True,
            "full_name": metadata.get("full_name"),
            "html_url": metadata.get("html_url"),
            "description": metadata.get("description"),
            "language": metadata.get("language"),
            "default_branch": metadata.get("default_branch"),
            "license": license_data.get("spdx_id"),
            "stars": metadata.get("stargazers_count"),
            "updated_at": metadata.get("updated_at"),
            "root_files": files[:100],
        }

    def _inspect_npm_package(
        self,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        package_name, requested_version = _parse_npm_package(
            arguments.get("package")
        )
        metadata = _npm_api(package_name)
        dist_tags = metadata.get("dist-tags") or {}
        latest = str(dist_tags.get("latest") or "")
        version = requested_version or latest
        version_data = (metadata.get("versions") or {}).get(version) or {}
        return {
            "exists": True,
            "name": metadata.get("name", package_name),
            "requested_version": requested_version,
            "latest_version": latest,
            "description": metadata.get("description"),
            "license": version_data.get("license") or metadata.get("license"),
            "repository": metadata.get("repository"),
            "homepage": metadata.get("homepage"),
        }

    def _install_github_repository(
        self,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        owner, repo = _parse_github_repository(arguments.get("repository"))
        metadata = _github_api(f"/repos/{owner}/{repo}")
        raw_destination = str(arguments.get("destination") or "").strip()
        destination = _external_path(raw_destination or repo)
        if destination.exists() and any(destination.iterdir()):
            raise FileExistsError(f"Thư mục đích không rỗng: {destination}")
        git = shutil.which("git")
        if not git:
            raise FileNotFoundError("Không tìm thấy git trong PATH.")
        destination.parent.mkdir(parents=True, exist_ok=True)
        clone = _run_workspace_process(
            [
                git,
                "clone",
                "--depth",
                "1",
                f"https://github.com/{owner}/{repo}.git",
                str(destination),
            ],
            timeout=900,
            cwd=APP_ROOT,
        )
        result: dict[str, Any] = {
            "repository": metadata.get("full_name"),
            "path": str(destination.relative_to(APP_ROOT)),
            "cloned": clone["ok"],
            "clone_output": clone["output"],
        }
        if not clone["ok"]:
            return result

        manager = str(arguments.get("package_manager", "auto")).strip().lower()
        if manager not in {"auto", "npm", "python", "none"}:
            raise ValueError("package_manager không hợp lệ.")
        if manager == "auto":
            if (destination / "package.json").is_file():
                manager = "npm"
            elif (destination / "requirements.txt").is_file():
                manager = "python"
            else:
                manager = "none"
        result["package_manager"] = manager
        if arguments.get("install_dependencies", True) is False or manager == "none":
            result["dependencies_installed"] = False
            result["message"] = "Đã clone; không có dependency được cài."
            return result
        dependency = _install_repository_dependencies(destination, manager)
        result.update(dependency)
        return result

    def _install_npm_package(
        self,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        raw_package = _required_text(arguments.get("package"), "package")
        package_name, _ = _parse_npm_package(raw_package)
        metadata = _npm_api(package_name)
        npm = shutil.which("npm") or shutil.which("npm.cmd")
        if not npm:
            raise FileNotFoundError("Không tìm thấy npm trong PATH.")
        slug = re.sub(r"[^a-zA-Z0-9_.-]+", "_", package_name.replace("/", "_"))
        destination = _external_path(EXTERNAL_ROOT / "npm" / slug)
        if destination.exists() and any(destination.iterdir()):
            raise FileExistsError(f"Thư mục npm đã tồn tại và không rỗng: {destination}")
        destination.mkdir(parents=True, exist_ok=True)
        init = _run_workspace_process(
            [npm, "init", "-y"],
            timeout=120,
            cwd=destination,
        )
        if not init["ok"]:
            return {
                "package": metadata.get("name", package_name),
                "path": str(destination.relative_to(APP_ROOT)),
                "installed": False,
                "output": init["output"],
            }
        install = _run_workspace_process(
            [npm, "install", raw_package, "--ignore-scripts"],
            timeout=1800,
            cwd=destination,
        )
        return {
            "package": metadata.get("name", package_name),
            "version": (metadata.get("dist-tags") or {}).get("latest"),
            "path": str(destination.relative_to(APP_ROOT)),
            "installed": install["ok"],
            "output": (init["output"] + install["output"])[-20000:],
        }

    def _run_project_stage(
        self,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        project_id = _required_text(
            arguments.get("project_id"),
            "project_id",
        )
        stage = _required_text(
            arguments.get("stage"),
            "stage",
        ).lower()
        scripts = {
            "transcribe": "run_project_transcription.py",
            "translate": "run_project_translation.py",
            "tts": "run_project_tts.py",
            "merge_export": "run_project_merge_export.py",
            "export": "run_project_export.py",
            "finalize": "run_project_finalize.py",
        }
        script_name = scripts.get(stage)
        if script_name is None:
            raise ValueError(f"Stage không được phép: {stage}")

        project = _find_project(project_id)
        if project is None:
            raise ValueError(
                f"Không tìm thấy project có ID: {project_id}"
            )

        project_dir = _safe_project_path(project.project_dir)
        command = [
            sys.executable,
            str(APP_ROOT / "scripts" / script_name),
            str(project_dir),
        ]
        try:
            completed = subprocess.run(
                command,
                cwd=str(APP_ROOT),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=6 * 60 * 60,
                check=False,
            )
        except subprocess.TimeoutExpired as error:
            raise TimeoutError(
                f"Stage {stage} vượt quá thời gian tối đa 6 giờ."
            ) from error

        output = (
            (completed.stdout or "")
            + (completed.stderr or "")
        )
        if completed.returncode != 0:
            raise RuntimeError(
                f"Stage {stage} thất bại với mã {completed.returncode}.\n"
                f"{output[-12000:]}"
            )

        return {
            "project_id": project.id,
            "stage": stage,
            "returncode": completed.returncode,
            "output_tail": output[-12000:],
        }


def _find_project(project_id: str) -> VideoProject | None:
    normalized = project_id.strip().lower()

    for project in load_all_projects():
        if project.id.lower() == normalized:
            return project

    return None


def _project_summary(
    project: VideoProject,
    *,
    include_settings: bool = False,
) -> dict[str, Any]:
    summary = {
        "id": project.id,
        "name": project.name,
        "source_video": project.source_video,
        "project_dir": project.project_dir,
        "progress_percent": project.progress_percent,
        "stages": dict(project.stages),
        "updated_at": project.updated_at,
    }

    if include_settings:
        summary["processing_settings"] = dict(
            project.processing_settings
        )

    return summary


def _safe_video_path(raw_path: str) -> Path:
    candidate = Path(raw_path).expanduser()

    if not candidate.is_absolute():
        candidate = APP_ROOT / candidate

    resolved = candidate.resolve()

    if not any(
        resolved.is_relative_to(root)
        for root in ALLOWED_VIDEO_ROOTS
    ):
        raise ValueError(
            "Chỉ được dùng video nằm trong downloads, input hoặc output."
        )

    if resolved.suffix.lower() not in VIDEO_EXTENSIONS:
        raise ValueError(
            "File không có phần mở rộng video được hỗ trợ."
        )

    if not resolved.is_file():
        raise FileNotFoundError(
            f"Không tìm thấy file video: {resolved}"
        )

    return resolved


def _safe_app_path(raw_path: Any) -> Path:
    candidate = Path(str(raw_path or ".")).expanduser()
    if not candidate.is_absolute():
        candidate = APP_ROOT / candidate

    resolved = candidate.resolve()
    if not resolved.is_relative_to(APP_ROOT.resolve()):
        raise ValueError(
            "Chỉ được truy cập đường dẫn trong thư mục AI Video Localizer."
        )

    return resolved


def _safe_code_path(
    raw_path: Any,
    *,
    must_exist: bool,
) -> Path:
    resolved = _safe_app_path(raw_path)
    if resolved.name.lower() in {".env", ".env.local"}:
        raise ValueError("Không được truy cập file secret.")
    if any(
        part.lower() in {".git", ".venv", "models"}
        for part in resolved.relative_to(APP_ROOT).parts
    ):
        raise ValueError("Không được truy cập thư mục runtime hoặc model.")
    if resolved.suffix.lower() not in CODE_EXTENSIONS and not resolved.is_dir():
        raise ValueError("Chỉ được truy cập file code/text được hỗ trợ.")
    if must_exist and not resolved.exists():
        raise FileNotFoundError(f"Không tìm thấy đường dẫn: {resolved}")
    return resolved


def _iter_code_files(root: Path):
    if root.is_file():
        if root.suffix.lower() in CODE_EXTENSIONS:
            yield root
        return
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if any(
            part.lower() in SKIP_CODE_DIRECTORIES
            for part in path.relative_to(APP_ROOT).parts
        ):
            continue
        if path.suffix.lower() in CODE_EXTENSIONS:
            yield path


def _run_workspace_process(
    command: list[str],
    *,
    timeout: int,
    cwd: str | Path | None = None,
) -> dict[str, Any]:
    try:
        completed = subprocess.run(
            command,
            cwd=str(cwd or APP_ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as error:
        raise TimeoutError(
            f"Lệnh kiểm tra vượt quá thời gian tối đa {timeout} giây."
        ) from error
    output = ((completed.stdout or "") + (completed.stderr or ""))[-20000:]
    return {
        "returncode": completed.returncode,
        "ok": completed.returncode == 0,
        "output": output,
    }


class _DuckDuckGoParser(HTMLParser):
    def __init__(self, limit: int) -> None:
        super().__init__()
        self.limit = limit
        self.results: list[dict[str, str]] = []
        self._kind = ""
        self._text: list[str] = []
        self._href = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        classes = set((values.get("class") or "").split())
        if tag == "a" and "result__a" in classes and len(self.results) < self.limit:
            self._kind = "title"
            self._text = []
            self._href = values.get("href") or ""
        elif "result__snippet" in classes and self.results:
            self._kind = "snippet"
            self._text = []

    def handle_data(self, data: str) -> None:
        if self._kind:
            self._text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if self._kind == "title" and tag == "a":
            href = self._href
            query_values = parse_qs(urlparse(href).query).get("uddg")
            if query_values:
                href = unquote(query_values[0])
            self.results.append({
                "title": " ".join("".join(self._text).split()),
                "url": href,
                "snippet": "",
            })
            self._kind = ""
        elif self._kind == "snippet" and tag in {"a", "div", "span"}:
            self.results[-1]["snippet"] = " ".join(
                "".join(self._text).split()
            )
            self._kind = ""


class _WebTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._skip_depth = 0
        self._parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "noscript", "svg"}:
            self._skip_depth += 1
        elif tag in {"br", "p", "div", "li", "h1", "h2", "h3", "pre"} and not self._skip_depth:
            self._parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript", "svg"} and self._skip_depth:
            self._skip_depth -= 1
        elif tag in {"p", "div", "li", "h1", "h2", "h3", "pre"} and not self._skip_depth:
            self._parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self._skip_depth:
            self._parts.append(data)

    def text(self) -> str:
        lines = [" ".join(line.split()) for line in "".join(self._parts).splitlines()]
        return "\n".join(line for line in lines if line)


def _workspace_cwd(value: Any) -> Path:
    raw = str(value or "").strip()
    candidate = Path(raw) if raw else APP_ROOT
    if not candidate.is_absolute():
        candidate = APP_ROOT / candidate
    resolved = candidate.resolve()
    root = APP_ROOT.resolve()
    if resolved != root and root not in resolved.parents:
        raise ValueError("cwd phải nằm trong workspace.")
    if not resolved.is_dir():
        raise NotADirectoryError(f"Không tìm thấy cwd: {resolved}")
    return resolved


def _safe_application_path(value: Any) -> Path:
    raw = _required_text(value, "path")
    candidate = Path(raw).expanduser()
    if not candidate.is_absolute():
        candidate = APP_ROOT / candidate
    resolved = candidate.resolve()
    if resolved.suffix.lower() != ".exe":
        raise ValueError("Chỉ được mở file .exe.")
    if not resolved.is_file():
        raise FileNotFoundError(f"Không tìm thấy ứng dụng: {resolved}")
    if not any(
        resolved == root or root in resolved.parents
        for root in ALLOWED_APPLICATION_ROOTS
    ):
        raise ValueError("Ứng dụng nằm ngoài các thư mục được phép.")
    return resolved


def _parse_github_repository(value: Any) -> tuple[str, str]:
    raw = _required_text(value, "repository").strip().rstrip("/")
    if raw.startswith("https://") or raw.startswith("http://"):
        parsed = urlparse(raw)
        if parsed.scheme != "https" or parsed.netloc.lower() not in {
            "github.com",
            "www.github.com",
        }:
            raise ValueError("Chỉ hỗ trợ repo public trên github.com qua HTTPS.")
        parts = [part for part in parsed.path.split("/") if part]
    else:
        parts = [part for part in raw.split("/") if part]
    if len(parts) != 2 or not all(re.fullmatch(r"[A-Za-z0-9_.-]+", part) for part in parts):
        raise ValueError("repository phải có dạng github.com/owner/repo hoặc owner/repo.")
    return parts[0], parts[1].removesuffix(".git")


def _github_api(path: str) -> dict[str, Any] | list[Any]:
    response = requests.get(
        f"https://api.github.com{path}",
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "M-Auto-Pilot",
        },
        timeout=20,
    )
    if response.status_code == 404:
        raise FileNotFoundError("GitHub repo không tồn tại hoặc không public.")
    response.raise_for_status()
    return response.json()


def _parse_npm_package(value: Any) -> tuple[str, str | None]:
    raw = _required_text(value, "package")
    if any(char.isspace() for char in raw) or raw.startswith("-"):
        raise ValueError("Tên npm package không hợp lệ.")
    if raw.startswith("@"):
        match = re.fullmatch(r"(@[^/]+/[^@]+)(?:@(.+))?", raw)
    else:
        match = re.fullmatch(r"([^@/]+)(?:@(.+))?", raw)
    if match is None:
        raise ValueError("Tên npm package không hợp lệ.")
    return match.group(1), match.group(2)


def _npm_api(package_name: str) -> dict[str, Any]:
    response = requests.get(
        f"https://registry.npmjs.org/{quote(package_name, safe='@/')}",
        headers={"User-Agent": "M-Auto-Pilot"},
        timeout=20,
    )
    if response.status_code == 404:
        raise FileNotFoundError(f"npm package không tồn tại: {package_name}")
    response.raise_for_status()
    return response.json()


def _external_path(value: Any) -> Path:
    raw = str(value or "").strip()
    candidate = Path(raw) if raw else EXTERNAL_ROOT
    if not candidate.is_absolute():
        candidate = EXTERNAL_ROOT / candidate
    resolved = candidate.resolve()
    root = EXTERNAL_ROOT.resolve()
    if resolved != root and root not in resolved.parents:
        raise ValueError("Chỉ được cài repo/package dưới work/auto_pilot/external.")
    return resolved


def _install_repository_dependencies(
    path: Path,
    manager: str,
) -> dict[str, Any]:
    if manager == "npm":
        npm = shutil.which("npm") or shutil.which("npm.cmd")
        if not npm:
            raise FileNotFoundError("Không tìm thấy npm trong PATH.")
        result = _run_workspace_process(
            [npm, "install", "--ignore-scripts"],
            timeout=1800,
            cwd=path,
        )
        return {
            "dependencies_installed": result["ok"],
            "dependency_output": result["output"],
        }
    if manager == "python":
        venv_path = path / ".venv"
        python_path = venv_path / "Scripts" / "python.exe"
        if not python_path.is_file():
            create_venv = _run_workspace_process(
                [sys.executable, "-m", "venv", str(venv_path)],
                timeout=600,
                cwd=path,
            )
            if not create_venv["ok"]:
                return {
                    "dependencies_installed": False,
                    "dependency_output": create_venv["output"],
                }
        result = _run_workspace_process(
            [str(python_path), "-m", "pip", "install", "-r", "requirements.txt"],
            timeout=1800,
            cwd=path,
        )
        return {
            "dependencies_installed": result["ok"],
            "dependency_output": result["output"],
            "python_environment": str(venv_path.relative_to(APP_ROOT)),
        }
    raise ValueError(f"Package manager không được hỗ trợ: {manager}")


def _create_checkpoint_for_paths(paths: list[Path]) -> str:
    checkpoint_id, _ = _create_checkpoint(paths)
    return checkpoint_id


def _create_checkpoint(paths: list[str | Path]) -> tuple[str, int]:
    checkpoint_id = datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + uuid4().hex[:8]
    checkpoint_dir = CHECKPOINT_ROOT / checkpoint_id / "files"
    checkpoint_dir.mkdir(parents=True, exist_ok=False)
    copied: list[str] = []
    seen: set[Path] = set()
    for raw_path in paths:
        path = _safe_code_path(raw_path, must_exist=True)
        candidates = [path] if path.is_file() else list(_iter_code_files(path))
        for source in candidates:
            if source in seen or source.stat().st_size > 5 * 1024 * 1024:
                continue
            seen.add(source)
            relative = source.relative_to(APP_ROOT)
            destination = checkpoint_dir / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
            copied.append(str(relative))
    if not copied:
        shutil.rmtree(checkpoint_dir.parent, ignore_errors=True)
        raise ValueError("Không có file code phù hợp để tạo checkpoint.")
    manifest = {
        "checkpoint_id": checkpoint_id,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "files": copied,
    }
    (checkpoint_dir.parent / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return checkpoint_id, len(copied)


def _restore_checkpoint(checkpoint_id: str) -> dict[str, Any]:
    if Path(checkpoint_id).name != checkpoint_id:
        raise ValueError("checkpoint_id không hợp lệ.")
    checkpoint_dir = CHECKPOINT_ROOT / checkpoint_id
    manifest_path = checkpoint_dir / "manifest.json"
    if not manifest_path.is_file():
        raise FileNotFoundError(f"Không tìm thấy checkpoint: {checkpoint_id}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    restored = 0
    for relative in manifest.get("files", []):
        source = checkpoint_dir / "files" / relative
        destination = _safe_code_path(relative, must_exist=False)
        if not source.is_file():
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        restored += 1
    return {
        "checkpoint_id": checkpoint_id,
        "restored_files": restored,
    }


def _safe_project_path(raw_path: Any) -> Path:
    candidate = Path(str(raw_path)).expanduser().resolve()
    projects_root = (APP_ROOT / "work" / "projects").resolve()
    if not candidate.is_relative_to(projects_root):
        raise ValueError(
            "Project phải nằm trong work/projects."
        )
    if not candidate.is_dir():
        raise FileNotFoundError(
            f"Không tìm thấy thư mục project: {candidate}"
        )
    return candidate


def _is_llama_server(process_id: int) -> bool:
    try:
        return psutil.Process(process_id).name().lower() == "llama-server.exe"
    except psutil.Error:
        return False


def _required_text(value: Any, name: str) -> str:
    text = str(value or "").strip()

    if not text:
        raise ValueError(f"Thiếu tham số bắt buộc: {name}")

    return text


def _bounded_int(
    value: Any,
    *,
    minimum: int,
    maximum: int,
) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError) as error:
        raise ValueError("Tham số phải là số nguyên.") from error

    return max(minimum, min(maximum, number))


def _optional_height(value: Any) -> int | None:
    if value is None or value == "":
        return None

    return _bounded_int(
        value,
        minimum=240,
        maximum=2160,
    )


def _optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    return int(value)


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value

    if isinstance(value, str):
        return value.strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }

    return bool(value)
