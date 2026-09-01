from __future__ import annotations

import os
import sys
from pathlib import Path


def get_project_root() -> Path:
    configured = os.environ.get("M_AUTO_PILOT_ROOT", "").strip()
    if configured:
        return Path(configured).resolve()
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    file_root = Path(__file__).resolve().parents[1]
    if (file_root / "agent").is_dir() and (file_root / "ui").is_dir():
        return file_root
    vibe_path = Path(r"D:\Vibe Code\M-Auto-Pilot")
    if vibe_path.is_dir():
        return vibe_path
    return file_root


PROJECT_ROOT = get_project_root()
os.environ["M_AUTO_PILOT_ROOT"] = str(PROJECT_ROOT)
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import threading
from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import QApplication, QMainWindow, QMenu, QSystemTrayIcon

from ui.agent_page import AgentPage


class GlobalHotkeyListener(QObject):
    hotkey_triggered = Signal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._running = True
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def _loop(self) -> None:
        if sys.platform == "darwin":
            try:
                from pynput import keyboard
                with keyboard.GlobalHotKeys({
                    '<cmd>+<shift>+m': self.hotkey_triggered.emit,
                    '<ctrl>+<shift>+m': self.hotkey_triggered.emit,
                }) as h:
                    while self._running:
                        import time
                        time.sleep(0.5)
            except Exception:
                pass
            return

        if sys.platform == "win32":
            try:
                import ctypes
                import ctypes.wintypes
                user32 = ctypes.windll.user32
                HOTKEY_ID = 101
                MOD_ALT = 0x0001
                MOD_SHIFT = 0x0004
                VK_M = 0x4D

                if not user32.RegisterHotKey(None, HOTKEY_ID, MOD_ALT | MOD_SHIFT, VK_M):
                    return

                msg = ctypes.wintypes.MSG()
                while self._running:
                    if user32.GetMessageW(ctypes.byref(msg), None, 0, 0) != 0:
                        if msg.message == 0x0312:
                            self.hotkey_triggered.emit()
                        user32.TranslateMessage(ctypes.byref(msg))
                        user32.DispatchMessageW(ctypes.byref(msg))
            except Exception:
                pass
            finally:
                try:
                    ctypes.windll.user32.UnregisterHotKey(None, 101)
                except Exception:
                    pass

    def stop(self) -> None:
        self._running = False


def load_stylesheet(app: QApplication) -> None:
    bundle_root = Path(getattr(sys, "_MEIPASS", PROJECT_ROOT))
    candidates = [
        PROJECT_ROOT / "ui" / "styles.qss",
        bundle_root / "ui" / "styles.qss",
    ]
    for candidate in candidates:
        try:
            if candidate.is_file():
                app.setStyleSheet(candidate.read_text(encoding="utf-8"))
                return
        except OSError:
            continue


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Auto Pilot Qwen 3.8 27B IQ3_Superfast")
    app.setQuitOnLastWindowClosed(False)
    load_stylesheet(app)
    bundle_root = Path(getattr(sys, "_MEIPASS", PROJECT_ROOT))
    icon_path = bundle_root / "assets" / "M_Auto_Pilot_logo.png"
    if icon_path.is_file():
        app_icon = QIcon(str(icon_path))
        app.setWindowIcon(app_icon)
    else:
        app_icon = app.style().standardIcon(app.style().StandardPixmap.SP_ComputerIcon)

    window = QMainWindow()
    window.setWindowTitle("Auto Pilot Qwen 3.8 27B IQ3_Superfast")
    window.resize(1280, 820)
    window.setMinimumSize(1000, 660)
    agent_page = AgentPage(window)
    window.setCentralWidget(agent_page)

    def toggle_window() -> None:
        if window.isVisible() and not window.isMinimized():
            window.hide()
        else:
            window.showNormal()
            window.raise_()
            window.activateWindow()

    # System Tray
    tray = QSystemTrayIcon(app_icon, app)
    shortcut_txt = "Cmd+Shift+M" if sys.platform == "darwin" else "Alt+Shift+M"
    tray.setToolTip(f"Auto Pilot Qwen 3.8 27B IQ3_Superfast · AI Assistant & Coding Agent ({shortcut_txt})")
    tray_menu = QMenu()

    toggle_action = QAction(f"Show / Hide Window ({shortcut_txt})", tray_menu)
    toggle_action.triggered.connect(toggle_window)
    tray_menu.addAction(toggle_action)

    new_chat_action = QAction("＋ New Chat", tray_menu)
    new_chat_action.triggered.connect(
        lambda: (
            window.showNormal(),
            window.raise_(),
            window.activateWindow(),
            agent_page.new_chat(),
        )
    )
    tray_menu.addAction(new_chat_action)

    tray_menu.addSeparator()
    exit_action = QAction("Quit Auto Pilot", tray_menu)
    exit_action.triggered.connect(app.quit)
    tray_menu.addAction(exit_action)

    tray.setContextMenu(tray_menu)
    tray.activated.connect(
        lambda reason: toggle_window()
        if reason in (
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.DoubleClick,
        )
        else None
    )
    tray.show()

    # Global Hotkey (Alt + Shift + M)
    hotkey = GlobalHotkeyListener(app)
    hotkey.hotkey_triggered.connect(toggle_window)
    hotkey.start()

    window.show()
    result = app.exec()
    hotkey.stop()
    return result


if __name__ == "__main__":
    raise SystemExit(main())
