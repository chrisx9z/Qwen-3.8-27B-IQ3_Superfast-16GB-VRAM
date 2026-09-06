from __future__ import annotations

import json
import os
import subprocess
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

import psutil

from core.project import APP_ROOT


RESOURCE_STATE_PATH = APP_ROOT / "work" / "auto_pilot" / "resource_state.json"
_LOCK = threading.RLock()


class GPUResourceManager:
    def claim_agent(
        self,
        *,
        profile: str,
        port: int,
        model_path: str,
    ) -> dict[str, Any]:
        with _LOCK:
            state = _load_state()
            active = state.get("active_agent")
            if active and _is_auto_pilot_process(active.get("owner_pid")):
                owner_pid = int(active["owner_pid"])
                if owner_pid != os.getpid():
                    same_profile = str(active.get("profile", "")).strip().lower() == str(profile).strip().lower()
                    same_port = int(active.get("port", 0)) == int(port)
                    # Nếu cùng profile và cùng port, cả 2 tiến trình chia sẻ chung llama-server hoàn toàn an toàn
                    if not (same_profile and same_port):
                        raise RuntimeError(
                            "Một Auto Pilot process khác đang giữ resource model "
                            f"{active.get('profile', '')} trên port {active.get('port', '')}."
                        )
            state["active_agent"] = {
                "owner_pid": os.getpid(),
                "profile": profile,
                "port": port,
                "model_path": model_path,
                "updated_at": datetime.now().isoformat(timespec="seconds"),
            }
            _save_state(state)
            return self.status()

    def release_agent(self) -> None:
        with _LOCK:
            state = _load_state()
            active = state.get("active_agent")
            if active and int(active.get("owner_pid", 0)) == os.getpid():
                state.pop("active_agent", None)
                _save_state(state)

    def status(self) -> dict[str, Any]:
        with _LOCK:
            state = _load_state()
            active = state.get("active_agent")
            if active and not _is_auto_pilot_process(active.get("owner_pid")):
                state.pop("active_agent", None)
                _save_state(state)
                active = None
            servers = _llama_servers()
            gpu = _gpu_status()
            warnings: list[str] = []
            ports = {server["port"] for server in servers if server.get("port")}
            if 8080 in ports:
                # Cả 2 ứng dụng dùng chung port 8080
                pass
            if gpu.get("available") and gpu.get("free_bytes", 0) < 2 * 1024**3:
                warnings.append("VRAM trống dưới 2 GB.")
            return {
                "policy": "exclusive_agent_model",
                "active_agent": active,
                "llama_servers": servers,
                "gpu": gpu,
                "warnings": warnings,
            }


def _load_state() -> dict[str, Any]:
    try:
        value = json.loads(RESOURCE_STATE_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def _save_state(state: dict[str, Any]) -> None:
    RESOURCE_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    RESOURCE_STATE_PATH.write_text(
        json.dumps(state, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _is_auto_pilot_process(value: Any) -> bool:
    try:
        if not value:
            return False
        pid = int(value)
        if not psutil.pid_exists(pid):
            return False
        p = psutil.Process(pid)
        if not p.is_running() or p.status() == psutil.STATUS_ZOMBIE:
            return False
        name = p.name().lower()
        if any(k in name for k in ("auto pilot", "autopilot", "qwen", "llama", "python")):
            return True
        try:
            cmd = " ".join(p.cmdline()).lower()
            if any(k in cmd for k in ("auto_pilot", "auto pilot", "controller.py", "main.py", "app.py", "llama")):
                return True
        except (psutil.Error, OSError):
            pass
        return False
    except (TypeError, ValueError, psutil.Error, OSError):
        return False


def _pid_alive(value: Any) -> bool:
    return _is_auto_pilot_process(value)


def _llama_servers() -> list[dict[str, Any]]:
    ports_by_pid: dict[int, list[int]] = {}
    try:
        for connection in psutil.net_connections(kind="tcp"):
            if connection.status != psutil.CONN_LISTEN or not connection.pid:
                continue
            if not connection.laddr:
                continue
            ports_by_pid.setdefault(connection.pid, []).append(connection.laddr.port)
    except psutil.Error:
        return []
    servers: list[dict[str, Any]] = []
    for pid, ports in ports_by_pid.items():
        try:
            process = psutil.Process(pid)
            p_name = process.name().lower()
            if p_name not in ("llama-server.exe", "llama-server"):
                continue
            servers.append({
                "pid": pid,
                "ports": sorted(set(ports)),
                "port": min(ports),
                "cmdline": process.cmdline()[-12:],
            })
        except (psutil.Error, OSError):
            continue
    return sorted(servers, key=lambda item: item["port"])


def _gpu_status() -> dict[str, Any]:
    import sys
    # macOS Apple Silicon Metal Unified Memory
    if sys.platform == "darwin":
        try:
            vm = psutil.virtual_memory()
            return {
                "available": True,
                "device_name": "Apple Silicon (Metal Unified Memory)",
                "total_bytes": vm.total,
                "used_bytes": vm.used,
                "free_bytes": vm.available,
                "utilization_percent": round(vm.percent, 1),
            }
        except Exception:
            pass

    command = [
        "nvidia-smi",
        "--query-gpu=memory.total,memory.used,memory.free,utilization.gpu",
        "--format=csv,noheader,nounits",
    ]
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=3,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return {"available": False, "reason": "GPU monitor không khả dụng"}
    if completed.returncode != 0 or not completed.stdout.strip():
        return {"available": False, "reason": "GPU monitor không trả dữ liệu"}
    values = [value.strip() for value in completed.stdout.splitlines()[0].split(",")]
    if len(values) < 4:
        return {"available": False, "reason": "Không đọc được trạng thái VRAM"}
    try:
        total_mb, used_mb, free_mb, utilization = (float(value) for value in values[:4])
    except ValueError:
        return {"available": False, "reason": "Dữ liệu GPU không hợp lệ"}
    return {
        "available": True,
        "total_bytes": int(total_mb * 1024 * 1024),
        "used_bytes": int(used_mb * 1024 * 1024),
        "free_bytes": int(free_mb * 1024 * 1024),
        "utilization_percent": utilization,
    }
