from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

from core.project import APP_ROOT

try:
    import psutil
except ImportError:  # pragma: no cover - psutil là dependency bắt buộc của app
    psutil = None


OBLITERATUS_DIRNAME = "OBLITERATUS"
DEFAULT_UI_PORT = 7860
PROBE_CACHE = APP_ROOT / "work" / "auto_pilot" / "obliteratus_probe.json"

# Chỉ cho phép các lệnh CLI an toàn, có kiểm soát tham số.
# Loại trừ: interactive (cần TTY), distributed (worker ngoài), tourney (chuỗi dài).
ALLOWED_SUBCOMMANDS = {
    # Đọc thông tin, không tải model
    "info",
    "models",
    "presets",
    "strategies",
    "gpu-calc",
    "recommend",
    "runs",
    "report",
    "aggregate",
    "checkpoint",
    # Pipeline abliteration (chạy nền, tốn GPU/thời gian)
    "obliterate",
    "abliterate",
    "blend",
    "self-improve",
    "capability-check",
    "restore-multimodal",
    "run",
}

ALLOWED_METHODS = {
    "basic",
    "advanced",
    "surgical",
    "optimized",
    "informed",
    "ega",
    "lora",
}


def _candidate_roots() -> tuple[Path, ...]:
    configured = os.environ.get("M_AUTO_PILOT_OBLITERATUS_ROOT", "").strip()
    roots: list[Path] = []
    if configured:
        roots.append(Path(configured))
    roots.append(
        APP_ROOT / "work" / "auto_pilot" / "external" / OBLITERATUS_DIRNAME
    )
    roots.append(
        Path(r"D:\Vibe Code\M-Auto-Pilot")
        / "work"
        / "auto_pilot"
        / "external"
        / OBLITERATUS_DIRNAME
    )
    roots.append(
        Path(r"D:\M-Auto-Pilot")
        / "work"
        / "auto_pilot"
        / "external"
        / OBLITERATUS_DIRNAME
    )
    return tuple(roots)


@dataclass(frozen=True)
class ObliteratusTarget:
    """Adapter điều khiển OBLITERATUS (abliteration toolkit) như ứng dụng ngoài."""

    root: Path
    python: Path
    ui_port: int = DEFAULT_UI_PORT
    log_dir: Path = field(default_factory=lambda: APP_ROOT / "work" / "auto_pilot" / "obliteratus_logs")

    @classmethod
    def from_environment(cls) -> "ObliteratusTarget":
        root = next(
            (candidate for candidate in _candidate_roots() if candidate.is_dir()),
            _candidate_roots()[0],
        )
        python = Path(
            os.environ.get(
                "M_AUTO_PILOT_OBLITERATUS_PYTHON",
                str(root / ".venv" / "Scripts" / "python.exe"),
            )
        )
        try:
            port = int(
                os.environ.get("M_AUTO_PILOT_OBLITERATUS_PORT", DEFAULT_UI_PORT)
            )
        except (TypeError, ValueError):
            port = DEFAULT_UI_PORT
        return cls(root=root, python=python, ui_port=port)

    # ----------------------------------------------------------- helpers

    @property
    def cli(self) -> Path:
        return self.root / ".venv" / "Scripts" / "obliteratus.exe"

    @property
    def app_script(self) -> Path:
        return self.root / "app.py"

    @property
    def installed(self) -> bool:
        return self.python.is_file() and (self.cli.is_file() or self.app_script.is_file())

    def _processes(self) -> list[dict[str, object]]:
        matches: list[dict[str, object]] = []
        if psutil is None or not self.root.is_dir():
            return matches
        root_text = str(self.root).lower()
        for process in psutil.process_iter(["pid", "name", "cmdline"]):
            try:
                cmdline = process.info.get("cmdline") or []
                joined = " ".join(str(part) for part in cmdline).lower()
                if root_text in joined and (
                    "obliteratus" in joined or "app.py" in joined
                ):
                    matches.append({
                        "pid": int(process.info["pid"]),
                        "name": str(process.info.get("name") or ""),
                        "command": joined[:400],
                    })
            except (OSError, RuntimeError, TypeError, ValueError):
                continue
        return matches

    def _port_busy(self) -> bool:
        if psutil is None:
            return False
        try:
            for connection in psutil.net_connections(kind="tcp"):
                address = connection.laddr
                if (
                    connection.status == psutil.CONN_LISTEN
                    and address
                    and address.port == self.ui_port
                ):
                    return True
        except psutil.Error:
            return False
        return False

    def probe_python(self, *, force: bool = False) -> dict[str, object]:
        """Kiểm tra nhanh torch/CUDA của venv OBLITERATUS (có cache 1 ngày)."""

        if not force and PROBE_CACHE.is_file():
            try:
                cached = json.loads(PROBE_CACHE.read_text(encoding="utf-8"))
                if time.time() - float(cached.get("checked_at", 0)) < 86400:
                    return cached
            except (OSError, ValueError, TypeError):
                pass

        if not self.python.is_file():
            return {"ok": False, "error": f"Không tìm thấy python: {self.python}"}

        script = (
            "import json\n"
            "info = {}\n"
            "try:\n"
            "    import torch\n"
            "    info['torch'] = torch.__version__\n"
            "    info['cuda_available'] = bool(torch.cuda.is_available())\n"
            "    info['cuda_version'] = getattr(torch.version, 'cuda', None)\n"
            "    if info['cuda_available']:\n"
            "        info['gpu'] = torch.cuda.get_device_name(0)\n"
            "        info['vram_gb'] = round(torch.cuda.get_device_properties(0).total_memory / 1024**3, 2)\n"
            "except Exception as error:\n"
            "    info['error'] = str(error)\n"
            "try:\n"
            "    import obliteratus\n"
            "    info['obliteratus'] = getattr(obliteratus, '__version__', 'installed')\n"
            "except Exception as error:\n"
            "    info['obliteratus'] = f'error: {error}'\n"
            "print(json.dumps(info))\n"
        )
        try:
            completed = subprocess.run(
                [str(self.python), "-c", script],
                cwd=str(self.root),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=180,
                env=self._child_env(),
            )
        except (OSError, subprocess.SubprocessError) as error:
            return {"ok": False, "error": str(error)}

        payload: dict[str, object] = {"ok": False}
        for line in reversed(completed.stdout.strip().splitlines()):
            line = line.strip()
            if line.startswith("{"):
                try:
                    payload = json.loads(line)
                    payload["ok"] = "torch" in payload
                    break
                except ValueError:
                    continue
        if not payload.get("ok"):
            payload.setdefault("error", completed.stderr.strip()[-500:])

        payload["checked_at"] = time.time()
        try:
            PROBE_CACHE.parent.mkdir(parents=True, exist_ok=True)
            PROBE_CACHE.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except OSError:
            pass
        return payload

    def log_path(self, name: str) -> Path:
        safe = "".join(ch for ch in name if ch.isalnum() or ch in "-_") or "run"
        self.log_dir.mkdir(parents=True, exist_ok=True)
        return self.log_dir / f"{safe}-{time.strftime('%Y%m%d-%H%M%S')}.log"

    def _child_env(self) -> dict[str, str]:
        """Ép UTF-8 cho tiến trình con (CLI in banner/khung unicode)."""

        environment = os.environ.copy()
        environment["PYTHONIOENCODING"] = "utf-8"
        environment["PYTHONUTF8"] = "1"
        environment["M_AUTO_PILOT_ROOT"] = str(APP_ROOT)
        return environment

    # ------------------------------------------------------------ actions

    def status(self) -> dict[str, object]:
        processes = self._processes()
        return {
            "ok": True,
            "root": str(self.root),
            "root_exists": self.root.is_dir(),
            "installed": self.installed,
            "python": str(self.python),
            "python_exists": self.python.is_file(),
            "cli": str(self.cli),
            "cli_exists": self.cli.is_file(),
            "app_script_exists": self.app_script.is_file(),
            "ui_port": self.ui_port,
            "ui_port_busy": self._port_busy(),
            "ui_url": f"http://127.0.0.1:{self.ui_port}",
            "running": bool(processes),
            "processes": processes,
        }

    def launch_ui(
        self,
        *,
        port: int | None = None,
        share: bool = False,
    ) -> dict[str, object]:
        current = self.status()
        if not current["installed"]:
            return {
                "ok": False,
                "started": False,
                "error": (
                    "OBLITERATUS chưa được cài đủ (thiếu .venv hoặc CLI). "
                    f"Root: {self.root}"
                ),
                **current,
            }
        if current["running"]:
            return {
                "ok": True,
                "started": False,
                "already_running": True,
                **current,
            }

        ui_port = int(port or self.ui_port)
        command = [str(self.cli), "ui", "--port", str(ui_port), "--no-browser"]
        if share:
            command.append("--share")
        log_file = self.log_path("ui")

        creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        try:
            with log_file.open("a", encoding="utf-8") as handle:
                handle.write(" ".join(command) + "\n")
                handle.flush()
                process = subprocess.Popen(
                    command,
                    cwd=str(self.root),
                    stdout=handle,
                    stderr=subprocess.STDOUT,
                    creationflags=creation_flags,
                    env=self._child_env(),
                )
        except OSError as error:
            return {
                "ok": False,
                "started": False,
                "error": f"Không khởi động được OBLITERATUS UI: {error}",
                **current,
            }

        return {
            "ok": True,
            "started": True,
            "already_running": False,
            "pid": process.pid,
            "ui_url": f"http://127.0.0.1:{ui_port}",
            "log_path": str(log_file),
            "note": "Gradio UI cần 15-60 giây để sẵn sàng; xem log_path nếu cần.",
            **self.status(),
        }

    def run_cli(
        self,
        subcommand: str,
        args: list[str] | None = None,
        *,
        background: bool = False,
        timeout: int = 600,
        tag: str = "",
    ) -> dict[str, object]:
        name = str(subcommand or "").strip().lower()
        if name not in ALLOWED_SUBCOMMANDS:
            return {
                "ok": False,
                "error": (
                    f"Lệnh '{subcommand}' không nằm trong allowlist. "
                    f"Cho phép: {sorted(ALLOWED_SUBCOMMANDS)}"
                ),
            }
        if not self.installed:
            return {
                "ok": False,
                "error": f"OBLITERATUS chưa được cài: {self.root}",
            }

        safe_args = [str(value) for value in (args or [])]
        if len(safe_args) > 40:
            return {"ok": False, "error": "Quá nhiều tham số (tối đa 40)."}

        command = [str(self.cli), name, *safe_args]
        log_file = self.log_path(tag or name)

        if background:
            creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            try:
                with log_file.open("a", encoding="utf-8") as handle:
                    handle.write(" ".join(command) + "\n")
                    handle.flush()
                    process = subprocess.Popen(
                        command,
                        cwd=str(self.root),
                        stdout=handle,
                        stderr=subprocess.STDOUT,
                        creationflags=creation_flags,
                        env=self._child_env(),
                    )
            except OSError as error:
                return {"ok": False, "error": str(error), "command": command}
            return {
                "ok": True,
                "background": True,
                "pid": process.pid,
                "command": command,
                "log_path": str(log_file),
                "note": "Đang chạy nền; đọc log_path để theo dõi tiến trình.",
            }

        try:
            completed = subprocess.run(
                command,
                cwd=str(self.root),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
                env=self._child_env(),
            )
        except subprocess.TimeoutExpired:
            return {
                "ok": False,
                "error": f"Hết thời gian chờ {timeout}s cho lệnh {name}.",
                "command": command,
            }
        except OSError as error:
            return {"ok": False, "error": str(error), "command": command}

        output = (completed.stdout or "").strip()
        error_output = (completed.stderr or "").strip()
        return {
            "ok": completed.returncode == 0,
            "exit_code": completed.returncode,
            "command": command,
            "stdout": output[-6000:],
            "stderr": error_output[-2000:],
        }

    def stop(self) -> dict[str, object]:
        processes = self._processes()
        stopped: list[int] = []
        if psutil is not None:
            for entry in processes:
                try:
                    process = psutil.Process(int(entry["pid"]))
                    process.terminate()
                    try:
                        process.wait(timeout=8)
                    except psutil.TimeoutExpired:
                        process.kill()
                    stopped.append(int(entry["pid"]))
                except (psutil.Error, OSError, ValueError):
                    continue
        return {
            "ok": True,
            "stopped": stopped,
            "note": "Chỉ dừng tiến trình OBLITERATUS do adapter phát hiện.",
            **self.status(),
        }


if __name__ == "__main__":  # pragma: no cover - chẩn đoán nhanh
    target = ObliteratusTarget.from_environment()
    print(json.dumps(target.status(), ensure_ascii=False, indent=2))
    print(json.dumps(target.probe_python(), ensure_ascii=False, indent=2))
