from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

import psutil


@dataclass(frozen=True)
class AIVideoLocalizerTarget:
    root: Path
    executable: Path

    @classmethod
    def from_environment(cls) -> "AIVideoLocalizerTarget":
        root = Path(
            os.environ.get(
                "M_AUTO_PILOT_TARGET_ROOT",
                r"D:\AI-Video-Localizer",
            )
        ).expanduser().resolve()
        executable = Path(
            os.environ.get(
                "M_AUTO_PILOT_TARGET_EXE",
                r"D:\OneDrive\Desktop\AI Video Localizer.exe",
            )
        ).expanduser().resolve()
        return cls(root=root, executable=executable)

    def status(self) -> dict[str, object]:
        running_pids = []
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
            raise FileNotFoundError(f"Không tìm thấy AI Video Localizer: {self.executable}")
        if current["running"]:
            return {"started": False, "already_running": True, **current}
        process = subprocess.Popen(
            [str(self.executable)],
            cwd=str(self.root) if self.root.is_dir() else None,
            close_fds=True,
        )
        return {
            "started": True,
            "already_running": False,
            "pid": process.pid,
            **self.status(),
        }
