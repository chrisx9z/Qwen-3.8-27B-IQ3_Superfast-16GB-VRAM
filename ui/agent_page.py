from __future__ import annotations

import html
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from PySide6.QtCore import QObject, QProcess, QRunnable, QThreadPool, Qt, Signal, Slot
from PySide6.QtGui import QTextCursor
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
    QScrollArea,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from agent.controller import AgentConfig, AgentResult, LocalAgent


def markdown_to_html(text: str) -> str:
    """Chuyển markdown cơ bản sang HTML an toàn (dùng cho QTextBrowser)."""

    def escape(value: str) -> str:
        return html.escape(value, quote=False)

    parts: list[str] = []
    segments = re.split(r"(```[\s\S]*?```)", text)

    for segment in segments:
        if not segment:
            continue
        if segment.startswith("```"):
            inner = segment[3:]
            if inner.endswith("```"):
                inner = inner[:-3]
            language = ""
            first_line, _, rest = inner.partition("\n")
            if first_line.strip() and not rest:
                language = first_line.strip()
                code = ""
            elif first_line.strip() and re.fullmatch(r"[A-Za-z0-9_+-]*", first_line.strip()):
                language = first_line.strip()
                code = rest
            else:
                code = inner
            parts.append(
                f'<pre class="code-block"><code>{escape(code.rstrip("\n"))}</code></pre>'
            )
            continue

        lines = escape(segment).split("\n")
        output: list[str] = []
        paragraph: list[str] = []
        in_list: str | None = None
        in_quote = False

        def flush_paragraph() -> None:
            nonlocal paragraph
            if paragraph:
                output.append("<p>" + "<br>".join(paragraph) + "</p>")
                paragraph = []

        def close_list() -> None:
            nonlocal in_list
            if in_list:
                output.append(f"</{in_list}>")
                in_list = None

        def close_quote() -> None:
            nonlocal in_quote
            if in_quote:
                output.append("</blockquote>")
                in_quote = False

        for raw_line in lines:
            line = raw_line.rstrip()
            stripped = line.strip()

            if not stripped:
                flush_paragraph()
                close_list()
                close_quote()
                continue

            heading = re.match(r"^(#{1,4})\s+(.*)$", stripped)
            if heading:
                flush_paragraph()
                close_list()
                close_quote()
                level = len(heading.group(1))
                output.append(
                    f"<h{level}>{_inline_md(heading.group(2))}</h{level}>"
                )
                continue

            if re.match(r"^---+$", stripped) or re.match(r"^\*\*\*+$", stripped):
                flush_paragraph()
                close_list()
                close_quote()
                output.append("<hr>")
                continue

            quote = re.match(r"^&gt;\s?(.*)$", stripped)
            if quote:
                flush_paragraph()
                close_list()
                if not in_quote:
                    output.append("<blockquote>")
                    in_quote = True
                output.append(_inline_md(quote.group(1)))
                continue

            unordered = re.match(r"^[-*]\s+(.*)$", stripped)
            if unordered:
                flush_paragraph()
                close_quote()
                if in_list != "ul":
                    close_list()
                    output.append("<ul>")
                    in_list = "ul"
                output.append(f"<li>{_inline_md(unordered.group(1))}</li>")
                continue

            ordered = re.match(r"^\d+[.)]\s+(.*)$", stripped)
            if ordered:
                flush_paragraph()
                close_quote()
                if in_list != "ol":
                    close_list()
                    output.append("<ol>")
                    in_list = "ol"
                output.append(f"<li>{_inline_md(ordered.group(1))}</li>")
                continue

            close_list()
            if in_quote:
                output.append("<br>")
            paragraph.append(_inline_md(line))

        flush_paragraph()
        close_list()
        close_quote()
        parts.append("\n".join(output))

    return "\n".join(parts)


def _inline_md(value: str) -> str:
    value = re.sub(
        r"`([^`]+)`",
        lambda m: f'<code class="inline-code">{m.group(1)}</code>',
        value,
    )
    value = re.sub(
        r"\[([^\]]+)\]\((https?://[^)\s]+)\)",
        r'<a href="\2">\1</a>',
        value,
    )
    value = re.sub(
        r"\*\*([^*]+)\*\*",
        r"<b>\1</b>",
        value,
    )
    value = re.sub(
        r"(?<!\*)\*([^*\n]+)\*(?!\*)",
        r"<i>\1</i>",
        value,
    )
    return value


class ChatInput(QPlainTextEdit):
    submit = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

    def keyPressEvent(self, event: Any) -> None:
        if (
            event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter)
            and not (
                event.modifiers() & Qt.KeyboardModifier.ShiftModifier
            )
        ):
            self.submit.emit()
            event.accept()
            return
        super().keyPressEvent(event)


class AgentWorkerSignals(QObject):
    status_changed = Signal(str)
    step = Signal(str)
    delta = Signal(str, str)
    completed = Signal(str, object)
    failed = Signal(str)
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
            self.signals.step.emit(message)
        elif event == "tool_call":
            name = str(payload.get("name", ""))
            self.signals.step.emit(f"🔧 Đang gọi tool `{name}`")
        elif event == "tool_result":
            name = str(payload.get("name", ""))
            ok = bool(payload.get("ok", False))
            mark = "✅" if ok else "⚠️"
            self.signals.step.emit(f"{mark} Tool `{name}` "
                                   f"{'thành công' if ok else 'có lỗi'}")
        elif event == "delta":
            if payload.get("text"):
                self.signals.delta.emit("text", str(payload["text"]))
            elif payload.get("reasoning"):
                self.signals.delta.emit("reasoning", str(payload["reasoning"]))


class AgentPage(QWidget):
    def __init__(
        self,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.chats: list[dict[str, Any]] = []
        self.active_chat_id = ""
        self.worker: AgentWorker | None = None
        self.harness_process: QProcess | None = None
        self._streaming_browser: QTextBrowser | None = None
        self._streaming_row: QWidget | None = None
        self._streaming_text = ""
        self._reasoning_chip: QLabel | None = None
        self._reasoning_parts: list[str] = []
        self.load_chats()
        self.build_ui()
        self.refresh_chat_list()
        if self.chats:
            self.select_chat(self.chats[0]["id"])
        else:
            self.new_chat()

    # ------------------------------------------------------------- UI

    def build_ui(self) -> None:
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ---- Sidebar (lịch sử chat) ----
        sidebar = QFrame()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(248)
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(14, 16, 14, 14)
        sidebar_layout.setSpacing(10)

        brand = QLabel("M Auto Pilot")
        brand.setObjectName("Brand")
        sidebar_layout.addWidget(brand)

        self.new_chat_button = QPushButton("＋ Chat mới")
        self.new_chat_button.setObjectName("PrimaryButton")
        self.new_chat_button.clicked.connect(self.new_chat)
        sidebar_layout.addWidget(self.new_chat_button)

        self.chat_list = QListWidget()
        self.chat_list.setObjectName("ChatList")
        self.chat_list.itemClicked.connect(self.on_chat_selected)
        sidebar_layout.addWidget(self.chat_list, 1)

        sidebar_actions = QHBoxLayout()
        sidebar_actions.setSpacing(6)
        self.pin_button = QPushButton("Ghim")
        self.rename_button = QPushButton("Đổi tên")
        self.delete_button = QPushButton("Xóa")
        for button in (
            self.pin_button,
            self.rename_button,
            self.delete_button,
        ):
            button.setObjectName("GhostButton")
            sidebar_actions.addWidget(button)
        sidebar_layout.addLayout(sidebar_actions)

        footer = QLabel("Qwen3.8-27B · chạy cục bộ")
        footer.setObjectName("MutedText")
        sidebar_layout.addWidget(footer)

        root.addWidget(sidebar)

        # ---- Main column ----
        main = QWidget()
        root.addWidget(main, 1)
        main_layout = QVBoxLayout(main)
        main_layout.setContentsMargins(22, 16, 22, 16)
        main_layout.setSpacing(12)

        header = QFrame()
        header.setObjectName("Card")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(16, 10, 16, 10)
        header_layout.setSpacing(10)

        title = QLabel("Trợ lý cá nhân · Coding · Điều khiển máy")
        title.setObjectName("PageTitle")
        header_layout.addWidget(title)

        header_layout.addStretch(1)

        header_layout.addWidget(QLabel("Model"))
        self.profile_combo = QComboBox()
        self.profile_combo.setObjectName("Combo")
        self.profile_combo.addItem("IQ3_S · mặc định", "qwen38_iq3s")
        self.profile_combo.addItem("Q4 · cân bằng", "qwen38_q4")
        self.profile_combo.addItem("Q6 · suy luận sâu", "qwen38_q6")
        self.profile_combo.addItem("Qwen3 14B · nhanh", "qwen14")
        header_layout.addWidget(self.profile_combo)

        header_layout.addWidget(QLabel("Chế độ"))
        self.mode_combo = QComboBox()
        self.mode_combo.setObjectName("Combo")
        self.mode_combo.addItem("Trợ lý cá nhân", "assistant")
        self.mode_combo.addItem("Coding Agent", "coding")
        self.mode_combo.addItem("Auto Pilot", "auto")
        header_layout.addWidget(self.mode_combo)

        self.status_label = QLabel("Sẵn sàng")
        self.status_label.setObjectName("StatusLabel")
        header_layout.addWidget(self.status_label)

        self.resource_button = QPushButton("GPU status")
        self.resource_button.setObjectName("GhostButton")
        self.resource_button.clicked.connect(self.refresh_resource_status)
        header_layout.addWidget(self.resource_button)

        self.harness_button = QPushButton("DeepSeek Harness")
        self.harness_button.setObjectName("GhostButton")
        self.harness_button.clicked.connect(self.open_deepseek_harness)
        header_layout.addWidget(self.harness_button)

        main_layout.addWidget(header)

        # ---- Chat area ----
        self.scroll = QScrollArea()
        self.scroll.setObjectName("ChatScroll")
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        chat_host = QWidget()
        self.chat_layout = QVBoxLayout(chat_host)
        self.chat_layout.setContentsMargins(4, 10, 4, 10)
        self.chat_layout.setSpacing(14)
        self.chat_layout.addStretch(1)
        self.scroll.setWidget(chat_host)
        main_layout.addWidget(self.scroll, 1)

        # ---- Input row ----
        input_row = QFrame()
        input_row.setObjectName("InputCard")
        input_layout = QHBoxLayout(input_row)
        input_layout.setContentsMargins(14, 10, 14, 10)
        input_layout.setSpacing(10)

        self.prompt_input = ChatInput()
        self.prompt_input.setObjectName("ChatInput")
        self.prompt_input.setPlaceholderText(
            "Hỏi bất cứ điều gì, yêu cầu viết/sửa code, tìm tài liệu, "
            "tải video hoặc điều khiển máy…  (Enter để gửi, Shift+Enter xuống dòng)"
        )
        self.prompt_input.setMinimumHeight(56)
        self.prompt_input.setMaximumHeight(150)
        self.prompt_input.submit.connect(self.run_prompt)
        input_layout.addWidget(self.prompt_input, 1)

        self.send_button = QPushButton("Gửi ➤")
        self.send_button.setObjectName("PrimaryButton")
        self.send_button.setMinimumHeight(44)
        self.send_button.clicked.connect(self.run_prompt)
        input_layout.addWidget(self.send_button)

        main_layout.addWidget(input_row)

    def create_card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("Card")
        return card

    # --------------------------------------------------------- Chat

    def active_chat(self) -> dict[str, Any] | None:
        return next(
            (chat for chat in self.chats if chat["id"] == self.active_chat_id),
            None,
        )

    def agent_messages(self, chat: dict[str, Any]) -> list[dict[str, Any]]:
        messages = chat.get("agent_messages")
        if isinstance(messages, list):
            return messages
        legacy = chat.get("messages")
        if isinstance(legacy, list):
            return legacy
        return []

    def history(self, chat: dict[str, Any]) -> list[dict[str, Any]]:
        history = chat.get("history")
        if isinstance(history, list):
            return history
        legacy = chat.get("messages")
        if isinstance(legacy, list):
            display: list[dict[str, Any]] = []
            for entry in legacy:
                role = str(entry.get("role", ""))
                if role == "user":
                    display.append({
                        "role": "user",
                        "content": str(entry.get("content", "")),
                    })
                elif role == "assistant":
                    content = str(entry.get("content", "")).strip()
                    if content:
                        display.append({
                            "role": "assistant",
                            "content": content,
                        })
            if display:
                return display
        transcript = str(chat.get("transcript", "")).strip()
        prompt = str(chat.get("prompt", "")).strip()
        display = []
        if prompt:
            display.append({"role": "user", "content": prompt})
        if transcript:
            display.append({"role": "assistant", "content": transcript})
        return display

    def load_chats(self) -> None:
        try:
            data = json.loads(self.chats_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = []
        self.chats = [
            chat
            for chat in data
            if isinstance(chat, dict) and chat.get("id")
        ]

    def save_chats(self) -> None:
        self.chats_path.parent.mkdir(parents=True, exist_ok=True)
        self.chats_path.write_text(
            json.dumps(self.chats, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    @property
    def chats_path(self) -> Path:
        root = Path(
            os.environ.get(
                "M_AUTO_PILOT_ROOT",
                Path(__file__).resolve().parents[1],
            )
        )
        return root / "work" / "auto_pilot" / "chats.json"

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
            "history": [],
            "agent_messages": [],
            "updated": "",
        }
        self.chats.insert(0, chat)
        self.active_chat_id = chat["id"]
        if hasattr(self, "chat_layout"):
            self.clear_chat_area()
            self.prompt_input.clear()
            self.status_label.setText("Sẵn sàng · chat mới")
            self.refresh_chat_list()
        self.save_chats()

    def on_chat_selected(self, item: QListWidgetItem) -> None:
        self.select_chat(str(item.data(32)))

    def select_chat(self, chat_id: str) -> None:
        if self.worker is not None:
            return
        chat = next(
            (entry for entry in self.chats if entry["id"] == chat_id),
            None,
        )
        if chat is None:
            return
        self.active_chat_id = chat_id
        self.clear_chat_area()
        for message in self.history(chat):
            self.append_message(message)
        self.status_label.setText("Sẵn sàng")
        for index in range(self.chat_list.count()):
            item = self.chat_list.item(index)
            if item.data(32) == chat_id:
                self.chat_list.setCurrentItem(item)
                break
        self.refresh_chat_list()
        self.scroll_to_bottom()

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
        title, accepted = QInputDialog.getText(
            self,
            "Đổi tên chat",
            "Tên mới:",
            text=chat.get("title", "New chat"),
        )
        if accepted and title.strip():
            chat["title"] = title.strip()[:80]
            self.save_chats()
            self.refresh_chat_list()

    def delete_chat(self) -> None:
        if self.worker is not None or not self.active_chat_id:
            return
        self.chats = [
            chat
            for chat in self.chats
            if chat["id"] != self.active_chat_id
        ]
        self.active_chat_id = ""
        self.save_chats()
        self.refresh_chat_list()
        if self.chats:
            self.select_chat(self.chats[0]["id"])
        else:
            self.new_chat()

    # -------------------------------------------------- Rendering

    def clear_chat_area(self) -> None:
        while self.chat_layout.count() > 1:
            item = self.chat_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._streaming_browser = None
        self._streaming_row = None
        self._streaming_text = ""
        self._reasoning_chip = None
        self._reasoning_parts = []

    def scroll_to_bottom(self) -> None:
        bar = self.scroll.verticalScrollBar()
        bar.setValue(bar.maximum())

    def append_message(self, message: dict[str, Any]) -> None:
        role = str(message.get("role", "assistant"))
        content = str(message.get("content", ""))
        ts = message.get("ts", "")
        if role == "user":
            self._add_user_bubble(content, ts)
        else:
            self._add_assistant_bubble(content, ts)

    def _timestamp(self) -> str:
        return datetime.now().strftime("%H:%M")

    def _add_user_bubble(self, text: str, ts: str = "") -> None:
        row = QWidget()
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.addStretch(1)
        bubble = QLabel(text)
        bubble.setObjectName("UserBubble")
        bubble.setWordWrap(True)
        bubble.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        row_layout.addWidget(bubble, 0)
        self.chat_layout.insertWidget(self.chat_layout.count() - 1, row)

    def _add_assistant_bubble(self, text: str, ts: str = "") -> None:
        row = QWidget()
        row_layout = QVBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(6)
        browser = QTextBrowser()
        browser.setObjectName("ChatBrowser")
        browser.setOpenExternalLinks(True)
        browser.setHtml(markdown_to_html(text))
        browser.setMinimumHeight(40)
        row_layout.addWidget(browser)
        meta = QLabel(f"M Auto Pilot · {ts}" if ts else "M Auto Pilot")
        meta.setObjectName("MutedText")
        row_layout.addWidget(meta)
        self.chat_layout.insertWidget(self.chat_layout.count() - 1, row)

    def _start_assistant_stream(self) -> QTextBrowser:
        row = QWidget()
        row_layout = QVBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(6)
        browser = QTextBrowser()
        browser.setObjectName("ChatBrowser")
        browser.setOpenExternalLinks(True)
        browser.setMinimumHeight(40)
        row_layout.addWidget(browser)
        meta = QLabel(f"M Auto Pilot · {self._timestamp()}")
        meta.setObjectName("MutedText")
        row_layout.addWidget(meta)
        self.chat_layout.insertWidget(self.chat_layout.count() - 1, row)
        self._streaming_browser = browser
        self._streaming_row = row
        self._streaming_text = ""
        return browser

    def _append_stream_text(self, text: str) -> None:
        if self._streaming_browser is None:
            self._start_assistant_stream()
        self._streaming_text += text
        cursor = self._streaming_browser.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self._streaming_browser.setTextCursor(cursor)
        self._streaming_browser.insertPlainText(text)
        self.scroll_to_bottom()

    def _finalize_stream(self) -> str:
        text = self._streaming_text
        if self._streaming_browser is not None:
            if text:
                self._streaming_browser.setHtml(markdown_to_html(text))
            else:
                row = self._streaming_row
                if row is not None:
                    row.deleteLater()
        self._streaming_browser = None
        self._streaming_row = None
        self._streaming_text = ""
        self._reasoning_chip = None
        self._reasoning_parts = []
        self.scroll_to_bottom()
        return text

    def _add_step(self, message: str) -> None:
        chip = QLabel("· " + message)
        chip.setObjectName("StepText")
        chip.setWordWrap(True)
        row = QWidget()
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.addStretch(1)
        row_layout.addWidget(chip)
        row_layout.addStretch(1)
        self.chat_layout.insertWidget(self.chat_layout.count() - 1, row)
        self.scroll_to_bottom()

    def _add_error(self, message: str) -> None:
        row = QWidget()
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.addStretch(1)
        label = QLabel("⚠️ " + message)
        label.setObjectName("ErrorText")
        label.setWordWrap(True)
        row_layout.addWidget(label)
        row_layout.addStretch(1)
        self.chat_layout.insertWidget(self.chat_layout.count() - 1, row)
        self.scroll_to_bottom()

    # ---------------------------------------------------- Actions

    def run_prompt(self) -> None:
        prompt = self.prompt_input.toPlainText().strip()
        if not prompt or self.worker is not None:
            return

        self.send_button.setEnabled(False)
        self.status_label.setText("Đang xử lý…")

        if not self.active_chat_id:
            self.new_chat()
        chat = self.active_chat()
        if chat is None:
            return

        if chat["title"] == "New chat":
            chat["title"] = prompt[:42].replace("\n", " ").strip()

        self.append_message({
            "role": "user",
            "content": prompt,
            "ts": self._timestamp(),
        })
        chat.setdefault("history", []).append({
            "role": "user",
            "content": prompt,
            "ts": self._timestamp(),
        })
        chat["prompt"] = prompt
        chat["updated"] = datetime.now().isoformat(timespec="seconds")
        self.refresh_chat_list()
        self.save_chats()

        self._start_assistant_stream()
        self.worker = AgentWorker(
            prompt,
            list(self.agent_messages(chat)),
            str(self.profile_combo.currentData()),
            str(self.mode_combo.currentData()),
        )
        self.worker.signals.status_changed.connect(
            self.status_label.setText,
            Qt.ConnectionType.QueuedConnection,
        )
        self.worker.signals.step.connect(
            self._add_step,
            Qt.ConnectionType.QueuedConnection,
        )
        self.worker.signals.delta.connect(
            self._on_delta,
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

    def _on_delta(self, kind: str, text: str) -> None:
        if kind == "text":
            self._append_stream_text(text)
        elif kind == "reasoning":
            self._reasoning_parts.append(text)
            if self._reasoning_chip is None:
                self._reasoning_chip = self._add_reasoning_chip()
            combined = "".join(self._reasoning_parts).strip()
            preview = combined
            if len(preview) > 240:
                preview = preview[:240] + "…"
            self._reasoning_chip.setText(f"🤔 {preview}")
            self.scroll_to_bottom()

    def _add_reasoning_chip(self) -> QLabel:
        chip = QLabel("🤔")
        chip.setObjectName("StepText")
        chip.setWordWrap(True)
        row = QWidget()
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.addStretch(1)
        row_layout.addWidget(chip)
        row_layout.addStretch(1)
        self.chat_layout.insertWidget(self.chat_layout.count() - 1, row)
        return chip

    def on_completed(self, text: str, messages: object) -> None:
        final_text = text.strip()
        if not final_text:
            final_text = self._streaming_text.strip()
        elif not self._streaming_text.strip():
            # Kết quả trả về nguyên cục (không stream) — đưa vào bong bóng.
            self._append_stream_text(final_text)
        self._finalize_stream()
        chat = self.active_chat()
        if chat is not None:
            if isinstance(messages, list):
                chat["agent_messages"] = messages
            if final_text:
                chat.setdefault("history", []).append({
                    "role": "assistant",
                    "content": final_text,
                    "ts": self._timestamp(),
                })
            chat["updated"] = datetime.now().isoformat(timespec="seconds")
            self.save_chats()
        self.status_label.setText("Hoàn tất")

    def on_failed(self, message: str) -> None:
        self._finalize_stream()
        self._add_error(message)
        chat = self.active_chat()
        if chat is not None:
            chat["updated"] = datetime.now().isoformat(timespec="seconds")
            self.save_chats()
        self.status_label.setText("Có lỗi")

    def on_thread_finished(self) -> None:
        self.worker = None
        self.send_button.setEnabled(True)

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
                message
                + (f" · {warnings[0]}" if warnings else " · sẵn sàng")
            )
        except Exception as error:
            self.status_label.setText(f"Không đọc được resource: {error}")

    def open_deepseek_harness(self) -> None:
        if (
            self.harness_process is not None
            and self.harness_process.state() != QProcess.ProcessState.NotRunning
        ):
            self.status_label.setText("DeepSeek Harness đang chạy tại cổng 3080")
            return

        root = Path(
            os.environ.get(
                "M_AUTO_PILOT_ROOT",
                Path(__file__).resolve().parents[1],
            )
        ).resolve()
        launcher = root / "scripts" / "run_deepseek_harness.py"
        python_executable = (
            root / ".venv" / "Scripts" / "python.exe"
            if getattr(sys, "frozen", False)
            else Path(sys.executable)
        )
        if not launcher.is_file() or not python_executable.is_file():
            self.status_label.setText(
                "Không tìm thấy launcher hoặc Python môi trường"
            )
            return
        profile = str(self.profile_combo.currentData()).rsplit("_", 1)[-1]
        self.harness_process = QProcess(self)
        self.harness_process.setWorkingDirectory(str(root))
        self.harness_process.started.connect(
            lambda: self.status_label.setText(
                "DeepSeek Harness đang chạy tại cổng 3080"
            )
        )
        self.harness_process.errorOccurred.connect(
            lambda: self.status_label.setText(
                "Không khởi động được DeepSeek Harness"
            )
        )
        self.harness_process.finished.connect(
            lambda: self.status_label.setText("DeepSeek Harness đã dừng")
        )
        self.harness_process.start(
            str(python_executable),
            [str(launcher), "--profile", profile],
        )
