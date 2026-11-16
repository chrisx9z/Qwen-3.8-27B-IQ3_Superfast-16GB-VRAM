from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from PySide6.QtWidgets import QApplication, QMainWindow  # noqa: E402

import llm.server_lifecycle as lifecycle_mod  # noqa: E402
from llm.server_lifecycle import ServerLifecycleRegistry, _is_process_alive  # noqa: E402
from scripts.run_auto_pilot_gui import bind_window_lifecycle  # noqa: E402
from tests._fake_server import (  # noqa: E402
    FakeServerManager,
    find_free_port,
    make_dummy_model,
    wait_dead,
)
from ui.agent_page import AgentPage  # noqa: E402


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        owned_file = tmp_path / "owned_pids.json"
        cfg_file = tmp_path / "lifecycle.json"
        cfg_file.write_text(
            json.dumps(
                {
                    "idle_shutdown_enabled": False,
                    "owned_pids_file": str(owned_file),
                    "minimize_to_tray_on_close": False,
                }
            ),
            encoding="utf-8",
        )
        os.environ["M_AUTO_PILOT_LIFECYCLE_CONFIG"] = str(cfg_file)
        os.environ["M_AUTO_PILOT_OWNED_PIDS_PATH"] = str(owned_file)

        registry = ServerLifecycleRegistry(config_path=cfg_file, owned_pids_path=owned_file)
        lifecycle_mod._DEFAULT_REGISTRY = registry

        port = find_free_port()
        manager = FakeServerManager(
            server_path=Path(sys.executable),
            model_path=make_dummy_model(tmp_path),
            port=port,
            startup_timeout=15,
            registry=registry,
        )
        manager.ensure_running()
        pid = manager.owned_pid
        assert pid is not None and _is_process_alive(pid)

        window = QMainWindow()
        page = AgentPage(window)
        window.setCentralWidget(page)
        perform_shutdown, quit_application = bind_window_lifecycle(
            app,
            window,
            page,
            tray=None,
            hotkey=None,
        )

        # Đóng cửa sổ chính (closeEvent) phải kích hoạt tắt server sở hữu
        closed = window.close()
        assert closed is True
        assert wait_dead(pid) is True

        # Thử thêm đường quit_application từ tray menu khi mở lại server
        port2 = find_free_port()
        manager2 = FakeServerManager(
            server_path=Path(sys.executable),
            model_path=make_dummy_model(tmp_path),
            port=port2,
            startup_timeout=15,
            registry=registry,
        )
        manager2.ensure_running()
        pid2 = manager2.owned_pid
        assert pid2 is not None and _is_process_alive(pid2)

        quit_application()
        assert wait_dead(pid2) is True
        perform_shutdown("final_check")

    print("GUI LIFECYCLE OFFSCREEN TEST PASSED!")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
