from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import psutil

from core.project import APP_ROOT


MANAGED_PROCESS_NAMES = {
    "ffmpeg.exe",
    "ffprobe.exe",
    "llama-server.exe",
    "ffmpeg",
    "ffprobe",
    "llama-server",
    "node",
    "node.exe",
    "pnpm",
    "pnpm.exe",
}


def list_processes(
    *,
    name: str = "",
    limit: int = 50,
) -> dict[str, Any]:
    filter_name = name.strip().lower()
    processes: list[dict[str, Any]] = []
    for process in psutil.process_iter(
        ["pid", "name", "status", "exe", "memory_info"]
    ):
        if len(processes) >= max(1, min(limit, 100)):
            break
        try:
            info = process.info
            process_name = str(info.get("name") or "")
            if filter_name and filter_name not in process_name.lower():
                continue
            memory_info = info.get("memory_info")
            processes.append({
                "pid": info.get("pid"),
                "name": process_name,
                "status": info.get("status"),
                "exe": info.get("exe"),
                "memory_bytes": getattr(memory_info, "rss", None),
            })
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue
    return {"count": len(processes), "processes": processes}


def read_log(
    path: str,
    *,
    lines: int = 200,
) -> dict[str, Any]:
    candidate = Path(path).expanduser()
    if not candidate.is_absolute():
        candidate = APP_ROOT / candidate
    resolved = candidate.resolve()
    if not resolved.is_relative_to(APP_ROOT.resolve()):
        raise ValueError("Log must be located inside the workspace.")
    if resolved.suffix.lower() not in {".log", ".txt"}:
        raise ValueError("Only .log or .txt files are allowed.")
    if not resolved.is_file():
        raise FileNotFoundError(f"Log file not found: {resolved}")
    content = resolved.read_text(encoding="utf-8", errors="replace").splitlines()
    tail = content[-max(1, min(lines, 1000)):]
    return {
        "path": str(resolved.relative_to(APP_ROOT)),
        "line_count": len(content),
        "text": "\n".join(tail),
    }


def stop_managed_process(pid: int) -> dict[str, Any]:
    try:
        process = psutil.Process(int(pid))
        name = process.name().lower()
        if name not in MANAGED_PROCESS_NAMES and not any(name.startswith(m) for m in MANAGED_PROCESS_NAMES):
            raise ValueError(
                f"Only runtime allowlist processes can be stopped: {sorted(MANAGED_PROCESS_NAMES)}"
            )
        process.terminate()
        try:
            process.wait(timeout=5)
        except psutil.TimeoutExpired:
            process.kill()
            process.wait(timeout=3)
        return {"stopped": True, "pid": pid, "name": name}
    except psutil.NoSuchProcess as error:
        raise FileNotFoundError(f"Process not found: {pid}") from error
    except psutil.AccessDenied as error:
        raise PermissionError(f"Access denied stopping process: {pid}") from error
