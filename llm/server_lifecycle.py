from __future__ import annotations

import atexit
import ctypes
import ctypes.wintypes as wintypes
import json
import os
import signal
import subprocess
import sys
import threading
import time
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterator

try:
    import psutil
except ImportError:
    psutil = None

from core.project import APP_ROOT


IS_WINDOWS = sys.platform == "win32"

DEFAULT_IDLE_TIMEOUT_MINUTES = 15.0
DEFAULT_IDLE_CHECK_INTERVAL_SECONDS = 10.0
DEFAULT_OWNED_PIDS_REL = "runtime/owned_pids.json"
DEFAULT_CONFIG_REL = Path("config") / "llama_lifecycle.json"

_CREATE_TIME_TOLERANCE_SECONDS = 2.5


@dataclass(frozen=True)
class LifecycleConfig:
    """Cấu hình vòng đời llama-server cho M Auto Pilot."""

    idle_shutdown_enabled: bool = True
    idle_timeout_minutes: float = DEFAULT_IDLE_TIMEOUT_MINUTES
    idle_check_interval_seconds: float = DEFAULT_IDLE_CHECK_INTERVAL_SECONDS
    owned_pids_file: str = DEFAULT_OWNED_PIDS_REL
    minimize_to_tray_on_close: bool = False


@dataclass
class OwnedServerRecord:
    """Thông tin định danh một tiến trình llama-server do chính app khởi chạy."""

    pid: int
    create_time: float | None
    started_at: str
    owner_app_pid: int
    owner_app_create_time: float | None
    host: str
    port: int
    server_path: str
    model_path: str
    process_name: str
    cmdline: list[str]

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "OwnedServerRecord | None":
        try:
            pid = int(raw["pid"])
        except (KeyError, TypeError, ValueError):
            return None
        if pid <= 0:
            return None
        create_time_raw = raw.get("create_time")
        owner_create_raw = raw.get("owner_app_create_time")
        try:
            create_time = float(create_time_raw) if create_time_raw is not None else None
        except (TypeError, ValueError):
            create_time = None
        try:
            owner_create_time = float(owner_create_raw) if owner_create_raw is not None else None
        except (TypeError, ValueError):
            owner_create_time = None
        try:
            owner_pid = int(raw.get("owner_app_pid") or 0)
        except (TypeError, ValueError):
            owner_pid = 0
        try:
            port = int(raw.get("port") or 0)
        except (TypeError, ValueError):
            port = 0
        cmdline_raw = raw.get("cmdline")
        cmdline = [str(item) for item in cmdline_raw] if isinstance(cmdline_raw, list) else []
        return cls(
            pid=pid,
            create_time=create_time,
            started_at=str(raw.get("started_at") or ""),
            owner_app_pid=owner_pid,
            owner_app_create_time=owner_create_time,
            host=str(raw.get("host") or "127.0.0.1"),
            port=port,
            server_path=str(raw.get("server_path") or ""),
            model_path=str(raw.get("model_path") or ""),
            process_name=str(raw.get("process_name") or ""),
            cmdline=cmdline,
        )


def _current_app_root() -> Path:
    configured = os.environ.get("M_AUTO_PILOT_ROOT", "").strip()
    if configured:
        return Path(configured).resolve()
    return APP_ROOT


def _resolve_config_path(explicit_path: Path | str | None = None) -> Path:
    if explicit_path is not None:
        return Path(explicit_path).resolve()
    env_cfg = os.environ.get("M_AUTO_PILOT_LIFECYCLE_CONFIG", "").strip()
    if env_cfg:
        return Path(env_cfg).resolve()
    app_cfg = _current_app_root() / DEFAULT_CONFIG_REL
    if app_cfg.is_file():
        return app_cfg
    bundle_root = Path(getattr(sys, "_MEIPASS", _current_app_root()))
    bundle_cfg = bundle_root / DEFAULT_CONFIG_REL
    if bundle_cfg.is_file():
        return bundle_cfg
    return app_cfg


def _parse_bool(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        norm = value.strip().lower()
        if norm in {"1", "true", "yes", "on"}:
            return True
        if norm in {"0", "false", "no", "off"}:
            return False
    return default


def load_lifecycle_config(config_path: Path | str | None = None) -> LifecycleConfig:
    """Đọc cấu hình vòng đời từ config/llama_lifecycle.json (có hỗ trợ env override)."""
    path = _resolve_config_path(config_path)
    raw: dict[str, Any] = {}
    if path.is_file():
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                raw = loaded
        except (OSError, ValueError):
            raw = {}

    enabled = _parse_bool(raw.get("idle_shutdown_enabled"), True)
    env_enabled = os.environ.get("M_AUTO_PILOT_IDLE_SHUTDOWN", "").strip()
    if env_enabled:
        enabled = _parse_bool(env_enabled, enabled)

    try:
        timeout_minutes = float(raw.get("idle_timeout_minutes", DEFAULT_IDLE_TIMEOUT_MINUTES))
    except (TypeError, ValueError):
        timeout_minutes = DEFAULT_IDLE_TIMEOUT_MINUTES
    env_minutes = os.environ.get("M_AUTO_PILOT_IDLE_MINUTES", "").strip()
    if env_minutes:
        try:
            timeout_minutes = float(env_minutes)
        except ValueError:
            pass
    if timeout_minutes <= 0:
        enabled = False

    try:
        check_interval = float(
            raw.get("idle_check_interval_seconds", DEFAULT_IDLE_CHECK_INTERVAL_SECONDS)
        )
    except (TypeError, ValueError):
        check_interval = DEFAULT_IDLE_CHECK_INTERVAL_SECONDS
    check_interval = max(0.05, check_interval)

    owned_pids_file = str(raw.get("owned_pids_file") or DEFAULT_OWNED_PIDS_REL).strip()
    if not owned_pids_file:
        owned_pids_file = DEFAULT_OWNED_PIDS_REL

    minimize_on_close = _parse_bool(raw.get("minimize_to_tray_on_close"), False)

    return LifecycleConfig(
        idle_shutdown_enabled=enabled,
        idle_timeout_minutes=timeout_minutes,
        idle_check_interval_seconds=check_interval,
        owned_pids_file=owned_pids_file,
        minimize_to_tray_on_close=minimize_on_close,
    )


def _resolve_owned_pids_path(
    config: LifecycleConfig,
    explicit_path: Path | str | None = None,
) -> Path:
    if explicit_path is not None:
        return Path(explicit_path).resolve()
    env_path = os.environ.get("M_AUTO_PILOT_OWNED_PIDS_PATH", "").strip()
    if env_path:
        return Path(env_path).resolve()
    candidate = Path(config.owned_pids_file)
    if candidate.is_absolute():
        return candidate.resolve()
    return (_current_app_root() / candidate).resolve()


def _get_process_create_time(pid: int) -> float | None:
    if psutil is None or pid <= 0:
        return None
    try:
        return float(psutil.Process(pid).create_time())
    except (psutil.Error, OSError, ValueError):
        return None


def _get_process_metadata(pid: int) -> tuple[str, list[str]]:
    if psutil is None or pid <= 0:
        return "", []
    try:
        proc = psutil.Process(pid)
        name = str(proc.name() or "")
        try:
            cmdline = [str(part) for part in proc.cmdline()]
        except (psutil.Error, OSError):
            cmdline = []
        return name, cmdline
    except (psutil.Error, OSError):
        return "", []


def _is_process_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if psutil is not None:
        try:
            proc = psutil.Process(pid)
            if not proc.is_running():
                return False
            if proc.status() == psutil.STATUS_ZOMBIE:
                return False
            return True
        except (psutil.Error, OSError):
            return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _is_same_process_instance(pid: int, expected_create_time: float | None) -> bool:
    if not _is_process_alive(pid):
        return False
    if expected_create_time is None:
        return True
    actual = _get_process_create_time(pid)
    if actual is None:
        return False
    return abs(actual - expected_create_time) <= _CREATE_TIME_TOLERANCE_SECONDS


def _verify_owned_server_record(record: OwnedServerRecord) -> bool:
    """
    Xác minh PID trong record vẫn còn sống và đúng là tiến trình server đã khởi chạy,
    tránh giết nhầm tiến trình khác khi OS tái sử dụng PID.
    """
    if not _is_process_alive(record.pid):
        return False
    if record.create_time is not None:
        actual_ct = _get_process_create_time(record.pid)
        if actual_ct is None or abs(actual_ct - record.create_time) > _CREATE_TIME_TOLERANCE_SECONDS:
            return False

    if psutil is not None:
        try:
            proc = psutil.Process(record.pid)
            actual_name = str(proc.name() or "").strip().lower()
            try:
                actual_exe = str(proc.exe() or "").strip().lower()
            except (psutil.Error, OSError):
                actual_exe = ""
            try:
                actual_cmd = [str(part) for part in proc.cmdline()]
            except (psutil.Error, OSError):
                actual_cmd = []

            expected_name = record.process_name.strip().lower()
            expected_server_name = Path(record.server_path).name.strip().lower() if record.server_path else ""
            if expected_name and actual_name and actual_name != expected_name:
                return False
            if expected_server_name and actual_name:
                # Cho phép sai khác nhỏ giữa "llama-server" và "llama-server.exe" hoặc symlink python
                if (
                    actual_name != expected_server_name
                    and actual_name != f"{expected_server_name}.exe"
                    and "llama-server" not in actual_name
                    and Path(actual_exe).name.lower() != expected_server_name
                ):
                    return False

            if record.cmdline and actual_cmd:
                # Kiểm tra cmdline khớp để chống PID reuse trên cùng executable (vd: python.exe -c ...)
                if Path(record.cmdline[0]).name.lower() != Path(actual_cmd[0]).name.lower():
                    return False
                if record.cmdline[1:] != actual_cmd[1:]:
                    return False
        except (psutil.Error, OSError):
            return False

    return True


def _terminate_pid_tree(
    pid: int,
    *,
    popen: subprocess.Popen[Any] | None = None,
    grace_timeout: float = 4.0,
) -> bool:
    """Dừng tiến trình (và tiến trình con nếu có) theo thứ tự terminate -> kill."""
    if pid <= 0:
        return False

    children: list[Any] = []
    if psutil is not None:
        try:
            parent = psutil.Process(pid)
            children = parent.children(recursive=True)
        except (psutil.Error, OSError):
            children = []

    if popen is not None and popen.poll() is None:
        try:
            popen.terminate()
            popen.wait(timeout=grace_timeout)
        except Exception:
            try:
                popen.kill()
                popen.wait(timeout=2.0)
            except Exception:
                pass
    elif psutil is not None:
        try:
            proc = psutil.Process(pid)
            proc.terminate()
            try:
                proc.wait(timeout=grace_timeout)
            except psutil.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=2.0)
        except (psutil.NoSuchProcess, psutil.ZombieProcess):
            pass
        except psutil.AccessDenied:
            pass
    else:
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            pass

    for child in children:
        try:
            if child.is_running():
                child.terminate()
        except (psutil.Error, OSError):
            pass

    if psutil is not None and children:
        deadline = time.monotonic() + 1.5
        for child in children:
            remaining = max(0.0, deadline - time.monotonic())
            try:
                child.wait(timeout=remaining)
            except (psutil.TimeoutExpired, psutil.Error, OSError):
                try:
                    child.kill()
                except (psutil.Error, OSError):
                    pass

    return not _is_process_alive(pid)


class _WindowsJobObject:
    """Bọc Windows Job Object với JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE."""

    JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000
    JOB_OBJECT_EXTENDED_LIMIT_INFORMATION_CLASS = 9
    PROCESS_SET_QUOTA = 0x0100
    PROCESS_TERMINATE = 0x0001

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._handle: int | None = None

    def _ensure_job_handle(self) -> int | None:
        if not IS_WINDOWS:
            return None
        with self._lock:
            if self._handle is not None:
                return self._handle

            class _JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
                _fields_ = [
                    ("PerProcessUserTimeLimit", ctypes.c_int64),
                    ("PerJobUserTimeLimit", ctypes.c_int64),
                    ("LimitFlags", wintypes.DWORD),
                    ("MinimumWorkingSetSize", ctypes.c_size_t),
                    ("MaximumWorkingSetSize", ctypes.c_size_t),
                    ("ActiveProcessLimit", wintypes.DWORD),
                    ("Affinity", ctypes.c_size_t),
                    ("PriorityClass", wintypes.DWORD),
                    ("SchedulingClass", wintypes.DWORD),
                ]

            class _IO_COUNTERS(ctypes.Structure):
                _fields_ = [
                    ("ReadOperationCount", ctypes.c_uint64),
                    ("WriteOperationCount", ctypes.c_uint64),
                    ("OtherOperationCount", ctypes.c_uint64),
                    ("ReadTransferCount", ctypes.c_uint64),
                    ("WriteTransferCount", ctypes.c_uint64),
                    ("OtherTransferCount", ctypes.c_uint64),
                ]

            class _JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
                _fields_ = [
                    ("BasicLimitInformation", _JOBOBJECT_BASIC_LIMIT_INFORMATION),
                    ("IoInfo", _IO_COUNTERS),
                    ("ProcessMemoryLimit", ctypes.c_size_t),
                    ("JobMemoryLimit", ctypes.c_size_t),
                    ("PeakProcessMemoryUsed", ctypes.c_size_t),
                    ("PeakJobMemoryUsed", ctypes.c_size_t),
                ]

            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel32.CreateJobObjectW.argtypes = [wintypes.LPVOID, wintypes.LPCWSTR]
            kernel32.CreateJobObjectW.restype = wintypes.HANDLE
            kernel32.SetInformationJobObject.argtypes = [
                wintypes.HANDLE,
                ctypes.c_int,
                wintypes.LPVOID,
                wintypes.DWORD,
            ]
            kernel32.SetInformationJobObject.restype = wintypes.BOOL
            kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
            kernel32.CloseHandle.restype = wintypes.BOOL

            job = kernel32.CreateJobObjectW(None, None)
            if not job:
                return None

            info = _JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
            info.BasicLimitInformation.LimitFlags = self.JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
            ok = kernel32.SetInformationJobObject(
                job,
                self.JOB_OBJECT_EXTENDED_LIMIT_INFORMATION_CLASS,
                ctypes.byref(info),
                ctypes.sizeof(info),
            )
            if not ok:
                kernel32.CloseHandle(job)
                return None

            self._handle = int(job)
            return self._handle

    def assign_pid(self, pid: int) -> bool:
        if not IS_WINDOWS or pid <= 0:
            return False
        job = self._ensure_job_handle()
        if not job:
            return False

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        kernel32.AssignProcessToJobObject.restype = wintypes.BOOL
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel32.CloseHandle.restype = wintypes.BOOL

        proc_handle = kernel32.OpenProcess(
            self.PROCESS_SET_QUOTA | self.PROCESS_TERMINATE,
            False,
            int(pid),
        )
        if not proc_handle:
            return False
        try:
            return bool(kernel32.AssignProcessToJobObject(wintypes.HANDLE(job), proc_handle))
        finally:
            kernel32.CloseHandle(proc_handle)

    def close(self) -> None:
        if not IS_WINDOWS:
            return
        with self._lock:
            if self._handle is not None:
                try:
                    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
                    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
                    kernel32.CloseHandle.restype = wintypes.BOOL
                    kernel32.CloseHandle(wintypes.HANDLE(self._handle))
                except Exception:
                    pass
                self._handle = None


class ServerLifecycleRegistry:
    """
    Quản lý tập trung vòng đời mọi tiến trình llama-server do CHÍNH M Auto Pilot khởi chạy:
    - Lưu PID + create_time + thông tin tiến trình vào runtime/owned_pids.json;
    - Gán vào Windows Job Object (KILL_ON_JOB_CLOSE);
    - Dọn PID mồ côi khi app mở lại sau crash (không đụng server ngoài hoặc instance app khác đang sống);
    - Theo dõi idle timeout (mặc định 15 phút) để tự tắt server khi rảnh và bật lại khi có request;
    - Dừng sạch toàn bộ server sở hữu khi app thoát (kể cả qua signal / atexit / console ctrl).
    """

    def __init__(
        self,
        *,
        config_path: Path | str | None = None,
        owned_pids_path: Path | str | None = None,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self._lock = threading.RLock()
        self._config_path = Path(config_path).resolve() if config_path else None
        self._explicit_owned_pids_path = Path(owned_pids_path).resolve() if owned_pids_path else None
        self._clock: Callable[[], float] = clock or time.monotonic

        self._owned: dict[int, OwnedServerRecord] = {}
        self._popens: dict[int, subprocess.Popen[Any]] = {}
        self._job = _WindowsJobObject()

        self._active_requests = 0
        self._last_activity_ts = self._clock()

        self._monitor_stop = threading.Event()
        self._monitor_thread: threading.Thread | None = None

    @property
    def config(self) -> LifecycleConfig:
        return load_lifecycle_config(self._config_path)

    @property
    def owned_pids_path(self) -> Path:
        return _resolve_owned_pids_path(self.config, self._explicit_owned_pids_path)

    def _read_disk_records(self) -> list[OwnedServerRecord]:
        path = self.owned_pids_path
        if not path.is_file():
            return []
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return []
        if isinstance(payload, dict):
            raw_list = payload.get("servers")
        elif isinstance(payload, list):
            raw_list = payload
        else:
            raw_list = []
        if not isinstance(raw_list, list):
            return []
        records: list[OwnedServerRecord] = []
        for item in raw_list:
            if isinstance(item, dict):
                rec = OwnedServerRecord.from_dict(item)
                if rec is not None:
                    records.append(rec)
        return records

    def _write_disk_records(self, records: list[OwnedServerRecord]) -> None:
        path = self.owned_pids_path
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": 1,
            "updated_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
            "servers": [asdict(rec) for rec in records],
        }
        serialized = json.dumps(payload, ensure_ascii=False, indent=2)
        tmp_path = path.with_name(f".{path.name}.{os.getpid()}.tmp")
        tmp_path.write_text(serialized, encoding="utf-8")
        os.replace(tmp_path, path)

    def _sync_current_process_records_to_disk(self) -> None:
        """Hợp nhất danh sách của process hiện tại vào file đĩa, giữ nguyên record của instance app khác còn sống."""
        my_pid = os.getpid()
        existing = self._read_disk_records()
        kept: list[OwnedServerRecord] = []
        for rec in existing:
            if rec.owner_app_pid == my_pid:
                continue
            if rec.owner_app_pid > 0 and _is_same_process_instance(rec.owner_app_pid, rec.owner_app_create_time):
                kept.append(rec)
        for rec in self._owned.values():
            kept.append(rec)
        self._write_disk_records(kept)

    def register_process(
        self,
        process: subprocess.Popen[Any],
        *,
        host: str,
        port: int,
        server_path: Path | str,
        model_path: Path | str,
    ) -> OwnedServerRecord:
        """Ghi nhận tiến trình llama-server mới do chính app khởi chạy."""
        pid = int(process.pid)
        my_pid = os.getpid()
        proc_name, cmdline = _get_process_metadata(pid)
        if not proc_name:
            proc_name = Path(server_path).name

        record = OwnedServerRecord(
            pid=pid,
            create_time=_get_process_create_time(pid),
            started_at=datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
            owner_app_pid=my_pid,
            owner_app_create_time=_get_process_create_time(my_pid),
            host=str(host),
            port=int(port),
            server_path=str(server_path),
            model_path=str(model_path),
            process_name=proc_name,
            cmdline=cmdline,
        )
        with self._lock:
            self._owned[pid] = record
            self._popens[pid] = process
            self._last_activity_ts = self._clock()
            self._job.assign_pid(pid)
            self._sync_current_process_records_to_disk()
        self.ensure_idle_monitor_started()
        return record

    def unregister_pid(self, pid: int) -> None:
        with self._lock:
            removed = self._owned.pop(int(pid), None) is not None
            self._popens.pop(int(pid), None)
            if removed:
                self._sync_current_process_records_to_disk()

    def owned_pids(self) -> list[int]:
        """Trả về danh sách PID thuộc chính app hiện tại và vẫn còn sống."""
        with self._lock:
            dead = [pid for pid in self._owned if not _is_process_alive(pid)]
            if dead:
                for pid in dead:
                    self._owned.pop(pid, None)
                    self._popens.pop(pid, None)
                self._sync_current_process_records_to_disk()
            return list(self._owned.keys())

    def is_owned_pid(self, pid: int) -> bool:
        with self._lock:
            return int(pid) in self._owned

    def get_owned_pid_for_endpoint(self, host: str, port: int) -> int | None:
        with self._lock:
            for pid in self.owned_pids():
                rec = self._owned.get(pid)
                if rec and rec.host == host and rec.port == int(port):
                    return pid
            return None

    def stop_owned_pid(self, pid: int, *, grace_timeout: float = 4.0) -> bool:
        """Tắt một PID nếu và chỉ nếu nó thuộc sở hữu của app hiện tại."""
        target_pid = int(pid)
        with self._lock:
            record = self._owned.get(target_pid)
            if record is None:
                return False
            popen = self._popens.get(target_pid)
            verified = _verify_owned_server_record(record)

        if verified:
            _terminate_pid_tree(target_pid, popen=popen, grace_timeout=grace_timeout)

        with self._lock:
            self._owned.pop(target_pid, None)
            self._popens.pop(target_pid, None)
            self._sync_current_process_records_to_disk()
        return verified

    def shutdown_all_owned(self, *, reason: str = "exit", grace_timeout: float = 3.0) -> list[int]:
        """Tắt toàn bộ llama-server do chính app hiện tại bật."""
        with self._lock:
            targets = list(self._owned.items())

        stopped: list[int] = []
        for pid, record in targets:
            with self._lock:
                popen = self._popens.get(pid)
            if _verify_owned_server_record(record):
                _terminate_pid_tree(pid, popen=popen, grace_timeout=grace_timeout)
                stopped.append(pid)

        with self._lock:
            for pid, _ in targets:
                self._owned.pop(pid, None)
                self._popens.pop(pid, None)
            self._sync_current_process_records_to_disk()
        return stopped

    def cleanup_orphaned_servers(self, *, grace_timeout: float = 3.0) -> list[int]:
        """
        Dọn các PID cũ trong owned_pids.json còn sót sau khi app lần trước bị crash.
        Không bao giờ chạm vào:
        - server của chính process hiện tại;
        - server của một instance M Auto Pilot khác còn đang sống;
        - server ngoài (không nằm trong owned_pids.json hoặc PID bị OS tái sử dụng khác create_time/tên).
        """
        my_pid = os.getpid()
        with self._lock:
            disk_records = self._read_disk_records()
            if not disk_records:
                return []

            kept_records: list[OwnedServerRecord] = []
            orphan_candidates: list[OwnedServerRecord] = []

            for rec in disk_records:
                if rec.owner_app_pid == my_pid and _is_same_process_instance(my_pid, rec.owner_app_create_time):
                    if rec.pid in self._owned or _verify_owned_server_record(rec):
                        kept_records.append(rec)
                    continue

                if rec.owner_app_pid > 0 and _is_same_process_instance(rec.owner_app_pid, rec.owner_app_create_time):
                    # Một instance app khác vẫn đang sống và sở hữu server này
                    kept_records.append(rec)
                    continue

                orphan_candidates.append(rec)

        cleaned_pids: list[int] = []
        for rec in orphan_candidates:
            if _verify_owned_server_record(rec):
                _terminate_pid_tree(rec.pid, popen=None, grace_timeout=grace_timeout)
                cleaned_pids.append(rec.pid)

        with self._lock:
            # Hợp nhất lại với các owned record hiện có trong bộ nhớ
            merged: list[OwnedServerRecord] = []
            seen_pids: set[int] = set()
            for rec in self._owned.values():
                merged.append(rec)
                seen_pids.add(rec.pid)
            for rec in kept_records:
                if rec.pid not in seen_pids and rec.owner_app_pid != my_pid:
                    merged.append(rec)
                    seen_pids.add(rec.pid)
            self._write_disk_records(merged)

        return cleaned_pids

    def touch_activity(self, *, now: float | None = None) -> None:
        with self._lock:
            self._last_activity_ts = self._clock() if now is None else float(now)

    def begin_request(self, *, now: float | None = None) -> None:
        with self._lock:
            self._active_requests += 1
            self._last_activity_ts = self._clock() if now is None else float(now)

    def end_request(self, *, now: float | None = None) -> None:
        with self._lock:
            self._active_requests = max(0, self._active_requests - 1)
            self._last_activity_ts = self._clock() if now is None else float(now)

    @contextmanager
    def request_scope(self) -> Iterator[None]:
        self.begin_request()
        try:
            yield
        finally:
            self.end_request()

    def check_idle_once(self, *, now: float | None = None) -> list[int]:
        """Kiểm tra một lần xem server do app bật đã rảnh quá cấu hình chưa; nếu quá thì tắt."""
        cfg = self.config
        if not cfg.idle_shutdown_enabled or cfg.idle_timeout_minutes <= 0:
            return []

        current_ts = self._clock() if now is None else float(now)
        with self._lock:
            if self._active_requests > 0:
                return []
            alive_owned = self.owned_pids()
            if not alive_owned:
                return []
            idle_seconds = current_ts - self._last_activity_ts
            if idle_seconds < cfg.idle_timeout_minutes * 60.0:
                return []

        return self.shutdown_all_owned(reason="idle_timeout")

    def ensure_idle_monitor_started(self) -> None:
        cfg = self.config
        if not cfg.idle_shutdown_enabled or cfg.idle_timeout_minutes <= 0:
            return
        with self._lock:
            if self._monitor_thread is not None and self._monitor_thread.is_alive():
                return
            self._monitor_stop.clear()
            thread = threading.Thread(
                target=self._idle_monitor_loop,
                name="llama-server-idle-monitor",
                daemon=True,
            )
            self._monitor_thread = thread
            thread.start()

    def stop_idle_monitor(self) -> None:
        self._monitor_stop.set()
        with self._lock:
            thread = self._monitor_thread
            self._monitor_thread = None
        if thread is not None and thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout=1.5)

    def _idle_monitor_loop(self) -> None:
        while not self._monitor_stop.is_set():
            interval = self.config.idle_check_interval_seconds
            if self._monitor_stop.wait(timeout=interval):
                break
            try:
                self.check_idle_once()
            except Exception:
                # Thread giám sát không được chết im lặng vì lỗi tạm thời
                continue

    def shutdown_and_cleanup(self, *, reason: str = "exit") -> list[int]:
        self.stop_idle_monitor()
        stopped = self.shutdown_all_owned(reason=reason)
        self._job.close()
        return stopped


_DEFAULT_REGISTRY: ServerLifecycleRegistry | None = None
_REGISTRY_LOCK = threading.Lock()
_EXIT_HANDLERS_INSTALLED = False
_CONSOLE_CTRL_HANDLER_REF: Any = None
_SHUTDOWN_ONCE_LOCK = threading.Lock()


def get_lifecycle_registry() -> ServerLifecycleRegistry:
    global _DEFAULT_REGISTRY
    with _REGISTRY_LOCK:
        if _DEFAULT_REGISTRY is None:
            _DEFAULT_REGISTRY = ServerLifecycleRegistry()
        return _DEFAULT_REGISTRY


def shutdown_owned_servers(*, reason: str = "exit") -> list[int]:
    registry = get_lifecycle_registry()
    with _SHUTDOWN_ONCE_LOCK:
        return registry.shutdown_and_cleanup(reason=reason)


def cleanup_orphaned_owned_servers() -> list[int]:
    return get_lifecycle_registry().cleanup_orphaned_servers()


def _install_windows_console_handler() -> None:
    global _CONSOLE_CTRL_HANDLER_REF
    if not IS_WINDOWS or _CONSOLE_CTRL_HANDLER_REF is not None:
        return
    try:
        handler_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.DWORD)

        @handler_type
        def _console_ctrl_handler(ctrl_type: int) -> bool:
            # CTRL_C_EVENT=0, CTRL_BREAK_EVENT=1, CTRL_CLOSE_EVENT=2,
            # CTRL_LOGOFF_EVENT=5, CTRL_SHUTDOWN_EVENT=6
            if ctrl_type in (0, 1, 2, 5, 6):
                try:
                    shutdown_owned_servers(reason=f"console_ctrl_{ctrl_type}")
                except Exception:
                    pass
            return False

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.SetConsoleCtrlHandler.argtypes = [handler_type, wintypes.BOOL]
        kernel32.SetConsoleCtrlHandler.restype = wintypes.BOOL
        if kernel32.SetConsoleCtrlHandler(_console_ctrl_handler, True):
            _CONSOLE_CTRL_HANDLER_REF = _console_ctrl_handler
    except Exception:
        pass


def install_exit_handlers() -> None:
    """Đăng ký atexit, signal handlers (SIGINT/SIGTERM/SIGBREAK) và Windows SetConsoleCtrlHandler."""
    global _EXIT_HANDLERS_INSTALLED
    with _REGISTRY_LOCK:
        if _EXIT_HANDLERS_INSTALLED:
            return
        _EXIT_HANDLERS_INSTALLED = True

    atexit.register(shutdown_owned_servers, reason="atexit")
    _install_windows_console_handler()

    if threading.current_thread() is not threading.main_thread():
        return

    sig_names = ["SIGINT", "SIGTERM"]
    if hasattr(signal, "SIGBREAK"):
        sig_names.append("SIGBREAK")

    for sig_name in sig_names:
        sig = getattr(signal, sig_name, None)
        if sig is None:
            continue
        try:
            prev_handler = signal.getsignal(sig)
        except (ValueError, OSError):
            continue

        def _make_handler(captured_sig: int, captured_prev: Any) -> Callable[[int, Any], None]:
            def _handler(signum: int, frame: Any) -> None:
                try:
                    shutdown_owned_servers(reason=f"signal_{signum}")
                except Exception:
                    pass
                if captured_prev in (None, signal.SIG_IGN):
                    return
                if callable(captured_prev):
                    captured_prev(signum, frame)
                    return
                if captured_prev == signal.SIG_DFL:
                    raise SystemExit(128 + int(signum))

            return _handler

        try:
            signal.signal(sig, _make_handler(int(sig), prev_handler))
        except (ValueError, OSError):
            continue
