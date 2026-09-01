from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

try:
    import psutil
except ImportError:
    psutil = None


@dataclass(frozen=True)
class AIVideoLocalizerTarget:
    root: Path
    executable: Path

    @classmethod
    def from_environment(cls) -> "AIVideoLocalizerTarget":
        root = Path(
            os.environ.get(
                "M_AUTO_PILOT_TARGET_ROOT",
                str(Path.home() / "applications"),
            )
        ).expanduser().resolve()
        
        default_exe = (
            Path("/Applications/Safari.app/Contents/MacOS/Safari")
            if sys.platform == "darwin"
            else Path(r"C:\Windows\System32\notepad.exe")
        )
        executable = Path(
            os.environ.get(
                "M_AUTO_PILOT_TARGET_EXE",
                str(default_exe),
            )
        ).expanduser().resolve()
        return cls(root=root, executable=executable)

    def status(self) -> dict[str, object]:
        running_pids = []
        if psutil is not None:
            for process in psutil.process_iter(["pid", "exe"]):
                try:
                    if Path(process.info.get("exe") or "").resolve() == self.executable:
                        running_pids.append(int(process.info["pid"]))
                except (OSError, RuntimeError, TypeError, ValueError):
                    continue
        return {
            "root": str(self.root),
            "root_exists": self.root.is_dir(),
            "executable": str(self.executable),
            "executable_exists": self.executable.is_file(),
            "running": bool(running_pids),
            "pids": running_pids,
        }

    def launch(self) -> dict[str, object]:
        current = self.status()
        if not current["executable_exists"]:
            return {
                "ok": False,
                "started": False,
                "already_running": False,
                "error": f"Target application executable not found: {self.executable}",
                **current,
            }
        if current["running"]:
            return {"ok": True, "started": False, "already_running": True, **current}
        try:
            process = subprocess.Popen(
                [str(self.executable)],
                cwd=str(self.root) if self.root.is_dir() else None,
                close_fds=True,
            )
            return {
                "ok": True,
                "started": True,
                "already_running": False,
                "pid": process.pid,
                **self.status(),
            }
        except Exception as e:
            return {
                "ok": False,
                "started": False,
                "error": str(e),
                **current,
            }
