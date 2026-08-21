from __future__ import annotations

import os
import sys
from pathlib import Path


def get_project_root() -> Path:
    configured = os.environ.get("M_AUTO_PILOT_ROOT", "").strip()
    if configured:
        return Path(configured).resolve()
    if getattr(sys, "frozen", False):
        return Path(r"D:\M-Auto-Pilot")
    return Path(__file__).resolve().parents[1]


PROJECT_ROOT = get_project_root()
os.environ["M_AUTO_PILOT_ROOT"] = str(PROJECT_ROOT)
os.environ.setdefault(
    "M_AUTO_PILOT_TARGET_ROOT",
    r"D:\AI-Video-Localizer",
)
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QMainWindow

from ui.agent_page import AgentPage


def main() -> int:
    app = QApplication(sys.argv)
    bundle_root = Path(getattr(sys, "_MEIPASS", PROJECT_ROOT))
    icon_path = bundle_root / "assets" / "M_Auto_Pilot_logo.png"
    if icon_path.is_file():
        app.setWindowIcon(QIcon(str(icon_path)))
    window = QMainWindow()
    window.setWindowTitle("M Auto Pilot")
    window.resize(1120, 760)
    window.setMinimumSize(900, 600)
    window.setCentralWidget(AgentPage(window))
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
