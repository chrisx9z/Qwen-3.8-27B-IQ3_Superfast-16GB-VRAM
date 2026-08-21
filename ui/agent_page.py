from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from PySide6.QtCore import QObject, QProcess, QRunnable, QThreadPool, Qt, Signal, Slot
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QInputDialog,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from agent.controller import AgentConfig, AgentResult, LocalAgent


class AgentWorkerSignals(QObject):
    completed = Signal(str, object)
    failed = Signal(str)
    status_changed = Signal(str)
    progress = Signal(str)
    finished = Signal()


class AgentWorker(QRunnable):

    def __init__(
        self,
        prompt: str,
        messages: list[dict[str, Any]],
        profile: str,
        task_mode: str,
    ) -> None:
        super().__init__()
        self.setAutoDelete(False)
        self.signals = AgentWorkerSignals()
        self.prompt = prompt
        self.messages = messages
        self.profile = profile
        self.task_mode = task_mode

    @Slot()
    def run(self) -> None:
        agent: LocalAgent | None = None
        try:
            agent = LocalAgent(
                config=AgentConfig.from_env(),
                event_callback=self.on_event,
            )
            result = agent.run(
                self.prompt,
                messages=self.messages or None,
                model_profile=self.profile,
                task_mode=self.task_mode,
            )
        except Exception as error:
            self.signals.failed.emit(
                f"{type(error).__name__}: {error}"
            )
        else:
            if isinstance(result, AgentResult):
                self.signals.completed.emit(
                    result.text,
                    result.messages,
                )
        finally:
            if agent is not None:
                agent.close()
            self.signals.finished.emit()

    def on_event(
        self,
        event: str,
        payload: dict[str, Any],
    ) -> None:
        if event == "status":
            message = str(payload.get("message", "Đang xử lý..."))
            self.signals.status_changed.emit(message)
            self.signals.progress.emit(f"Bước: {message}")
        elif event == "tool_call":
            name = str(payload.get("name", ""))
            arguments = payload.get("arguments") or {}
            if name == "web_search":
                message = f"Bước: đang tìm tài liệu trên Internet với query `{arguments.get('query', '')}`"
            elif name == "web_open":
                message = f"Bước: đang mở và đọc nguồn `{arguments.get('url', '')}`"
            else:
                message = f"Bước: đang gọi tool `{name}`"
            self.signals.status_changed.emit(message)
            self.signals.progress.emit(message)
        elif event == "tool_result":
            message = f"Bước: đã nhận kết quả từ `{payload.get('name', '')}`"
            self.signals.status_changed.emit(message)
            self.signals.progress.emit(message)


class AgentPage(QWidget):
    def __init__(
        self,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.messages: list[dict[str, Any]] = []
        self.chats: list[dict[str, Any]] = []
        self.active_chat_id = ""
        self.worker: AgentWorker | None = None
        self.harness_process: QProcess | None = None
        self.load_chats()
        self.build_ui()
        self.refresh_chat_list()
        if self.chats:
            self.select_chat(self.chats[0]["id"])
        else:
            self.new_chat()

    def build_ui(self) -> None:
        root = QHBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(16)

        history = self.create_card()
        history.setFixedWidth(230)
        history_layout = QVBoxLayout(history)
        history_layout.setContentsMargins(12, 12, 12, 12)
        history_layout.setSpacing(10)

        history_title = QLabel("M Auto Pilot")
        history_title.setObjectName("PageTitle")
        history_layout.addWidget(history_title)

        self.new_chat_button = QPushButton("＋ New chat")
        self.new_chat_button.clicked.connect(self.new_chat)
        history_layout.addWidget(self.new_chat_button)

        self.chat_list = QListWidget()
        self.chat_list.itemClicked.connect(self.on_chat_selected)
        history_layout.addWidget(self.chat_list, 1)

        history_actions = QHBoxLayout()
        self.pin_button = QPushButton("Ghim")
        self.pin_button.clicked.connect(self.toggle_pin)
        self.rename_button = QPushButton("Đổi tên")
        self.rename_button.clicked.connect(self.rename_chat)
        self.delete_button = QPushButton("Xóa")
        self.delete_button.clicked.connect(self.delete_chat)
        history_actions.addWidget(self.pin_button)
        history_actions.addWidget(self.rename_button)
        history_actions.addWidget(self.delete_button)
        history_layout.addLayout(history_actions)

        content = QWidget()
        root.addWidget(history)
        root.addWidget(content, 1)

        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(14)

        title = QLabel("Auto Pilot")
        title.setObjectName("PageTitle")

        description = QLabel(
            "Điều khiển downloader và project bằng Qwen local. Q4 mặc định; Q6 dành cho request phức tạp."
        )
        description.setObjectName("MutedText")
        description.setWordWrap(True)

        settings = self.create_card()
        settings_layout = QHBoxLayout(settings)

        settings_layout.addWidget(QLabel("Profile"))
        self.profile_combo = QComboBox()
        self.profile_combo.addItem("Q4 mặc định", "qwen38_q4")
        self.profile_combo.addItem("Q6 request phức tạp", "qwen38_q6")
        self.profile_combo.addItem("Qwen3 14B nhanh", "qwen14")
        settings_layout.addWidget(self.profile_combo)

        settings_layout.addWidget(QLabel("Chế độ"))
        self.mode_combo = QComboBox()
        self.mode_combo.addItem("Auto Pilot", "auto")
        self.mode_combo.addItem("Coding Agent", "coding")
        settings_layout.addWidget(self.mode_combo)

        self.status_label = QLabel("Sẵn sàng · endpoint agent 8090")
        self.status_label.setObjectName("MutedText")
        settings_layout.addWidget(self.status_label, 1)

        self.resource_button = QPushButton("GPU status")
        self.resource_button.clicked.connect(self.refresh_resource_status)
        settings_layout.addWidget(self.resource_button)

        self.run_button = QPushButton("Chạy Auto Pilot")
        self.run_button.clicked.connect(self.run_prompt)
        settings_layout.addWidget(self.run_button)

        self.harness_button = QPushButton("Mở DeepSeek Harness")
        self.harness_button.clicked.connect(self.open_deepseek_harness)
        settings_layout.addWidget(self.harness_button)

        self.prompt_input = QPlainTextEdit()
        self.prompt_input.setPlaceholderText(
            "Ví dụ: Liệt kê project, tải video Bilibili, hoặc sửa lỗi trong code rồi chạy test..."
        )
        self.prompt_input.setMinimumHeight(130)

        self.output = QPlainTextEdit()
        self.output.setReadOnly(True)
        self.output.setPlaceholderText("Kết quả Auto Pilot sẽ hiển thị ở đây.")

        content_layout.addWidget(title)
        content_layout.addWidget(description)
        content_layout.addWidget(settings)
        content_layout.addWidget(QLabel("Yêu cầu"))
        content_layout.addWidget(self.prompt_input)
        content_layout.addWidget(QLabel("Kết quả"))
        content_layout.addWidget(self.output, 1)

    def create_card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("Card")
        return card

    def run_prompt(self) -> None:
        prompt = self.prompt_input.toPlainText().strip()
        if not prompt or self.worker is not None:
            return

        self.run_button.setEnabled(False)
        self.status_label.setText("Đang khởi động Auto Pilot...")
        self.output.appendPlainText(f"Bạn: {prompt}\n")
        if not self.active_chat_id:
            self.new_chat()
        chat = self.active_chat()
        if chat and chat["title"] == "New chat":
            chat["title"] = prompt[:42].replace("\n", " ").strip()
        if chat:
            chat["prompt"] = prompt
            chat["updated"] = datetime.now().isoformat(timespec="seconds")
            self.refresh_chat_list()
        self.save_chats()

        self.worker = AgentWorker(
            prompt,
            list(self.messages),
            str(self.profile_combo.currentData()),
            str(self.mode_combo.currentData()),
        )
        self.worker.signals.status_changed.connect(
            self.status_label.setText,
            Qt.ConnectionType.QueuedConnection,
        )
        self.worker.signals.progress.connect(
            self.on_progress,
            Qt.ConnectionType.QueuedConnection,
        )
        self.worker.signals.completed.connect(
            self.on_completed,
            Qt.ConnectionType.QueuedConnection,
        )
        self.worker.signals.failed.connect(
            self.on_failed,
            Qt.ConnectionType.QueuedConnection,
        )
        self.worker.signals.finished.connect(
            self.on_thread_finished,
            Qt.ConnectionType.QueuedConnection,
        )
        QThreadPool.globalInstance().start(self.worker)

    def on_progress(self, message: str) -> None:
        self.output.appendPlainText(f"Auto Pilot: {message}")

    def open_deepseek_harness(self) -> None:
        if self.harness_process is not None and self.harness_process.state() != QProcess.NotRunning:
            self.status_label.setText("DeepSeek Harness đang chạy tại cổng 3080")
            return

        root = Path(os.environ.get("M_AUTO_PILOT_ROOT", Path(__file__).resolve().parents[1])).resolve()
        launcher = root / "scripts" / "run_deepseek_harness.py"
        python_executable = (
            root / ".venv" / "Scripts" / "python.exe"
            if getattr(sys, "frozen", False)
            else Path(sys.executable)
        )
        if not launcher.is_file() or not python_executable.is_file():
            self.status_label.setText("Không tìm thấy launcher hoặc Python môi trường")
            return
        profile = str(self.profile_combo.currentData()).rsplit("_", 1)[-1]
        self.harness_process = QProcess(self)
        self.harness_process.setWorkingDirectory(str(root))
        self.harness_process.started.connect(
            lambda: self.status_label.setText("DeepSeek Harness đang chạy tại cổng 3080")
        )
        self.harness_process.errorOccurred.connect(
            lambda: self.status_label.setText("Không khởi động được DeepSeek Harness")
        )
        self.harness_process.finished.connect(
            lambda: self.status_label.setText("DeepSeek Harness đã dừng")
        )
        self.harness_process.start(
            str(python_executable),
            [str(launcher), "--profile", profile],
        )

    def on_completed(
        self,
        text: str,
        messages: object,
    ) -> None:
        if isinstance(messages, list):
            self.messages = messages
        self.output.appendPlainText(f"Agent: {text}\n")
        chat = self.active_chat()
        if chat is not None:
            chat["messages"] = self.messages
            chat["transcript"] = self.output.toPlainText()
            chat["updated"] = datetime.now().isoformat(timespec="seconds")
            self.save_chats()
        self.status_label.setText("Hoàn tất")

    def on_failed(self, message: str) -> None:
        self.output.appendPlainText(f"Lỗi: {message}\n")
        chat = self.active_chat()
        if chat is not None:
            chat["messages"] = self.messages
            chat["transcript"] = self.output.toPlainText()
            chat["updated"] = datetime.now().isoformat(timespec="seconds")
            self.save_chats()
        self.status_label.setText("Có lỗi")

    def on_thread_finished(self) -> None:
        self.worker = None
        self.run_button.setEnabled(True)

    def refresh_resource_status(self) -> None:
        try:
            from llm.resource_manager import GPUResourceManager

            status = GPUResourceManager().status()
            gpu = status.get("gpu", {})
            if gpu.get("available"):
                free_gb = gpu.get("free_bytes", 0) / 1024**3
                message = f"VRAM trống {free_gb:.2f} GB"
            else:
                message = "Không đọc được VRAM"
            warnings = status.get("warnings") or []
            self.status_label.setText(
                message + (f" · {warnings[0]}" if warnings else " · sẵn sàng")
            )
        except Exception as error:
            self.status_label.setText(f"Không đọc được resource: {error}")

    @property
    def chats_path(self) -> Path:
        root = Path(os.environ.get("M_AUTO_PILOT_ROOT", Path(__file__).resolve().parents[1]))
        return root / "work" / "auto_pilot" / "chats.json"

    def load_chats(self) -> None:
        try:
            data = json.loads(self.chats_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = []
        self.chats = [chat for chat in data if isinstance(chat, dict) and chat.get("id")]
        migrated = False
        for chat in self.chats:
            if "prompt" not in chat:
                chat["prompt"] = chat.get("title", "") if not chat.get("messages") and not chat.get("transcript") else ""
                migrated = True
        if migrated:
            self.save_chats()

    def save_chats(self) -> None:
        self.chats_path.parent.mkdir(parents=True, exist_ok=True)
        self.chats_path.write_text(
            json.dumps(self.chats, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def active_chat(self) -> dict[str, Any] | None:
        return next((chat for chat in self.chats if chat["id"] == self.active_chat_id), None)

    def refresh_chat_list(self) -> None:
        if not hasattr(self, "chat_list"):
            return
        self.chat_list.clear()
        ordered = sorted(
            self.chats,
            key=lambda chat: chat.get("updated", ""),
            reverse=True,
        )
        ordered.sort(
            key=lambda chat: not chat.get("pinned", False),
        )
        for chat in ordered:
            marker = "★ " if chat.get("pinned", False) else ""
            item = QListWidgetItem(marker + chat.get("title", "New chat"))
            item.setData(32, chat["id"])
            self.chat_list.addItem(item)
        self.pin_button.setEnabled(bool(self.active_chat_id))
        self.rename_button.setEnabled(bool(self.active_chat_id))
        self.delete_button.setEnabled(bool(self.active_chat_id))

    def new_chat(self) -> None:
        if self.worker is not None:
            return
        chat = {
            "id": uuid4().hex,
            "title": "New chat",
            "pinned": False,
            "prompt": "",
            "messages": [],
            "transcript": "",
            "updated": "",
        }
        self.chats.insert(0, chat)
        self.active_chat_id = chat["id"]
        self.messages = []
        if hasattr(self, "output"):
            self.output.clear()
            self.prompt_input.clear()
            self.status_label.setText("Sẵn sàng · chat mới")
            self.refresh_chat_list()
        self.save_chats()

    def on_chat_selected(self, item: QListWidgetItem) -> None:
        self.select_chat(str(item.data(32)))

    def select_chat(self, chat_id: str) -> None:
        chat = next((entry for entry in self.chats if entry["id"] == chat_id), None)
        if chat is None:
            return
        self.active_chat_id = chat_id
        self.messages = list(chat.get("messages", []))
        if hasattr(self, "output"):
            prompt = str(chat.get("prompt", "")).strip()
            if not prompt and not self.messages and not chat.get("transcript"):
                prompt = str(chat.get("title", "")).strip()
            self.prompt_input.setPlainText(prompt)
            self.output.setPlainText(chat.get("transcript", ""))
            self.status_label.setText("Sẵn sàng")
            for index in range(self.chat_list.count()):
                item = self.chat_list.item(index)
                if item.data(32) == chat_id:
                    self.chat_list.setCurrentItem(item)
                    break
            self.refresh_chat_list()

    def toggle_pin(self) -> None:
        chat = self.active_chat()
        if chat is None:
            return
        chat["pinned"] = not chat.get("pinned", False)
        self.save_chats()
        self.refresh_chat_list()

    def rename_chat(self) -> None:
        chat = self.active_chat()
        if chat is None:
            return
        title, accepted = QInputDialog.getText(self, "Đổi tên chat", "Tên mới:", text=chat.get("title", "New chat"))
        if accepted and title.strip():
            chat["title"] = title.strip()[:80]
            self.save_chats()
            self.refresh_chat_list()

    def delete_chat(self) -> None:
        if self.worker is not None or not self.active_chat_id:
            return
        self.chats = [chat for chat in self.chats if chat["id"] != self.active_chat_id]
        self.active_chat_id = ""
        self.save_chats()
        self.refresh_chat_list()
        if self.chats:
            self.select_chat(self.chats[0]["id"])
        else:
            self.new_chat()
