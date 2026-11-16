from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
import types
from pathlib import Path

import psutil
import pytest
import requests

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    import mcp  # noqa: F401
except ModuleNotFoundError:
    _mcp = types.ModuleType("mcp")
    _mcp.ClientSession = object
    _mcp_client = types.ModuleType("mcp.client")
    _mcp_stdio = types.ModuleType("mcp.client.stdio")
    _mcp_stdio.StdioServerParameters = object
    _mcp_stdio.stdio_client = object
    sys.modules.update({
        "mcp": _mcp,
        "mcp.client": _mcp_client,
        "mcp.client.stdio": _mcp_stdio,
    })

from agent.controller import AgentConfig, LocalAgent  # noqa: E402
from agent.process_tools import stop_managed_process  # noqa: E402
from core.llm_settings import test_llm_connection as probe_llm_connection  # noqa: E402
from llm.server_lifecycle import (  # noqa: E402
    ServerLifecycleRegistry,
    _is_process_alive,
    load_lifecycle_config,
)
from tests._fake_server import (  # noqa: E402
    FAKE_HTTP_SERVER_CODE,
    SLEEP_PROCESS_CODE,
    FakeServerManager,
    creation_flags,
    find_free_port,
    make_dummy_model,
    wait_dead,
)


def _wait_health(port: int, timeout: float = 10.0) -> bool:
    deadline = time.monotonic() + timeout
    url = f"http://127.0.0.1:{port}/health"
    while time.monotonic() < deadline:
        try:
            r = requests.get(url, timeout=0.5)
            if r.status_code == 200:
                return True
        except Exception:
            pass
        time.sleep(0.1)
    return False


class FakeClock:
    def __init__(self, initial: float = 1000.0) -> None:
        self.now = initial

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> float:
        self.now += seconds
        return self.now


@pytest.fixture
def spawn_tracker():
    pids_to_kill: list[int] = []
    popens: list[subprocess.Popen] = []

    def track_popen(proc: subprocess.Popen) -> subprocess.Popen:
        popens.append(proc)
        pids_to_kill.append(int(proc.pid))
        return proc

    def track_pid(pid: int) -> int:
        pids_to_kill.append(int(pid))
        return int(pid)

    yield track_popen, track_pid

    for proc in popens:
        try:
            if proc.poll() is None:
                proc.kill()
                proc.wait(timeout=2)
        except Exception:
            pass
    for pid in pids_to_kill:
        try:
            if psutil.pid_exists(pid):
                p = psutil.Process(pid)
                p.kill()
                p.wait(timeout=2)
        except Exception:
            pass


def test_app_starts_records_pid_and_stops_on_shutdown(tmp_path: Path, spawn_tracker) -> None:
    _, track_pid = spawn_tracker
    port = find_free_port()
    owned_file = tmp_path / "owned_pids.json"
    cfg_file = tmp_path / "lifecycle.json"
    cfg_file.write_text(
        json.dumps({"idle_shutdown_enabled": False, "owned_pids_file": str(owned_file)}),
        encoding="utf-8",
    )
    registry = ServerLifecycleRegistry(config_path=cfg_file, owned_pids_path=owned_file)
    manager = FakeServerManager(
        server_path=Path(sys.executable),
        model_path=make_dummy_model(tmp_path),
        port=port,
        startup_timeout=15,
        registry=registry,
    )

    try:
        manager.ensure_running()
        assert manager.is_running() is True
        assert manager.using_external_server is False
        pid = manager.owned_pid
        assert pid is not None and pid > 0
        track_pid(pid)

        data = json.loads(owned_file.read_text(encoding="utf-8"))
        assert len(data["servers"]) == 1
        rec = data["servers"][0]
        assert rec["pid"] == pid
        assert rec["owner_app_pid"] == os.getpid()
        assert rec["port"] == port
        assert rec["create_time"] is not None

        stopped = registry.shutdown_and_cleanup(reason="test_exit")
        assert pid in stopped
        assert wait_dead(pid) is True
        after = json.loads(owned_file.read_text(encoding="utf-8"))
        assert after["servers"] == []
    finally:
        registry.shutdown_and_cleanup(reason="fixture_cleanup")


def test_atexit_kills_owned_server_in_subprocess(tmp_path: Path, spawn_tracker) -> None:
    track_popen, track_pid = spawn_tracker
    port = find_free_port()
    owned_file = tmp_path / "owned_pids.json"
    cfg_file = tmp_path / "lifecycle.json"
    cfg_file.write_text(
        json.dumps({"idle_shutdown_enabled": False, "owned_pids_file": str(owned_file)}),
        encoding="utf-8",
    )
    model_file = make_dummy_model(tmp_path)

    child_script = tmp_path / "child_atexit_app.py"
    child_script.write_text(
        f"""
import sys
sys.path.insert(0, {repr(str(PROJECT_ROOT))})
from pathlib import Path
from llm.server_lifecycle import install_exit_handlers
from tests._fake_server import FakeServerManager

install_exit_handlers()
mgr = FakeServerManager(
    server_path=Path(sys.executable),
    model_path=Path({repr(str(model_file))}),
    port={port},
    startup_timeout=15,
)
mgr.ensure_running()
print(mgr.owned_pid, flush=True)
""",
        encoding="utf-8",
    )

    env = os.environ.copy()
    env["M_AUTO_PILOT_LIFECYCLE_CONFIG"] = str(cfg_file)
    env["M_AUTO_PILOT_OWNED_PIDS_PATH"] = str(owned_file)

    app_proc = track_popen(
        subprocess.Popen(
            [sys.executable, str(child_script)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=env,
            creationflags=creation_flags(),
        )
    )
    stdout, stderr = app_proc.communicate(timeout=20)
    assert app_proc.returncode == 0, f"stderr={stderr}"
    server_pid = int(stdout.strip().splitlines()[-1])
    track_pid(server_pid)

    assert wait_dead(server_pid) is True
    data = json.loads(owned_file.read_text(encoding="utf-8"))
    assert data["servers"] == []


@pytest.mark.skipif(sys.platform != "win32", reason="Windows Job Object test")
def test_hard_kill_parent_kills_server_via_windows_job_object(tmp_path: Path, spawn_tracker) -> None:
    track_popen, track_pid = spawn_tracker
    port = find_free_port()
    owned_file = tmp_path / "owned_pids.json"
    cfg_file = tmp_path / "lifecycle.json"
    cfg_file.write_text(
        json.dumps({"idle_shutdown_enabled": False, "owned_pids_file": str(owned_file)}),
        encoding="utf-8",
    )
    model_file = make_dummy_model(tmp_path)

    child_script = tmp_path / "child_hardkill_app.py"
    child_script.write_text(
        f"""
import sys, time
sys.path.insert(0, {repr(str(PROJECT_ROOT))})
from pathlib import Path
from tests._fake_server import FakeServerManager

mgr = FakeServerManager(
    server_path=Path(sys.executable),
    model_path=Path({repr(str(model_file))}),
    port={port},
    startup_timeout=15,
)
mgr.ensure_running()
print(mgr.owned_pid, flush=True)
time.sleep(60)
""",
        encoding="utf-8",
    )

    env = os.environ.copy()
    env["M_AUTO_PILOT_LIFECYCLE_CONFIG"] = str(cfg_file)
    env["M_AUTO_PILOT_OWNED_PIDS_PATH"] = str(owned_file)

    app_proc = track_popen(
        subprocess.Popen(
            [sys.executable, str(child_script)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=env,
            creationflags=creation_flags(),
        )
    )
    assert app_proc.stdout is not None
    first_line = app_proc.stdout.readline().strip()
    assert first_line, f"Không nhận được PID; stderr={app_proc.stderr.read() if app_proc.stderr else ''}"
    server_pid = int(first_line)
    track_pid(server_pid)

    assert _wait_health(port) is True
    assert _is_process_alive(server_pid) is True

    # Kill cứng app cha (TerminateProcess) -> không chạy Python finally/atexit, chỉ Job Object bảo vệ
    app_proc.kill()
    app_proc.wait(timeout=5)

    assert wait_dead(server_pid, timeout=6.0) is True


def test_signal_handlers_and_console_ctrl_kill_owned_server(tmp_path: Path, spawn_tracker) -> None:
    track_popen, track_pid = spawn_tracker
    port = find_free_port()
    owned_file = tmp_path / "owned_pids.json"
    cfg_file = tmp_path / "lifecycle.json"
    cfg_file.write_text(
        json.dumps({"idle_shutdown_enabled": False, "owned_pids_file": str(owned_file)}),
        encoding="utf-8",
    )
    model_file = make_dummy_model(tmp_path)

    # 1) Kiểm tra SIGTERM / SIGINT trong subprocess thật với install_exit_handlers()
    child_script = tmp_path / "child_signal_app.py"
    child_script.write_text(
        f"""
import signal, sys
sys.path.insert(0, {repr(str(PROJECT_ROOT))})
from pathlib import Path
from llm.server_lifecycle import install_exit_handlers
from tests._fake_server import FakeServerManager

install_exit_handlers()
mgr = FakeServerManager(
    server_path=Path(sys.executable),
    model_path=Path({repr(str(model_file))}),
    port={port},
    startup_timeout=15,
)
mgr.ensure_running()
print(mgr.owned_pid, flush=True)
signal.raise_signal(signal.SIGTERM)
""",
        encoding="utf-8",
    )

    env = os.environ.copy()
    env["M_AUTO_PILOT_LIFECYCLE_CONFIG"] = str(cfg_file)
    env["M_AUTO_PILOT_OWNED_PIDS_PATH"] = str(owned_file)

    app_proc = track_popen(
        subprocess.Popen(
            [sys.executable, str(child_script)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=env,
            creationflags=creation_flags(),
        )
    )
    stdout, _ = app_proc.communicate(timeout=20)
    server_pid = int(stdout.strip().splitlines()[-1])
    track_pid(server_pid)

    assert app_proc.returncode != 0
    assert wait_dead(server_pid, timeout=6.0) is True
    data = json.loads(owned_file.read_text(encoding="utf-8"))
    assert data["servers"] == []

    # 2) Kiểm tra Windows Console Ctrl Handler (CTRL_CLOSE_EVENT = 2) tắt server sở hữu
    from llm import server_lifecycle as lifecycle_mod

    port2 = find_free_port()
    registry = ServerLifecycleRegistry(config_path=cfg_file, owned_pids_path=owned_file)
    old_default = lifecycle_mod._DEFAULT_REGISTRY
    lifecycle_mod._DEFAULT_REGISTRY = registry
    try:
        mgr2 = FakeServerManager(
            server_path=Path(sys.executable),
            model_path=model_file,
            port=port2,
            startup_timeout=15,
            registry=registry,
        )
        mgr2.ensure_running()
        pid2 = mgr2.owned_pid
        assert pid2 is not None
        track_pid(pid2)
        assert _is_process_alive(pid2) is True

        handled = lifecycle_mod._handle_console_ctrl_event(2)  # CTRL_CLOSE_EVENT
        assert handled is False
        assert wait_dead(pid2, timeout=6.0) is True
    finally:
        lifecycle_mod._DEFAULT_REGISTRY = old_default
        registry.shutdown_and_cleanup(reason="test_cleanup")


def test_external_server_is_shared_and_never_killed(tmp_path: Path, spawn_tracker) -> None:
    track_popen, _ = spawn_tracker
    port = find_free_port()
    owned_file = tmp_path / "owned_pids.json"
    cfg_file = tmp_path / "lifecycle.json"
    cfg_file.write_text(
        json.dumps({"idle_shutdown_enabled": True, "idle_timeout_minutes": 15, "owned_pids_file": str(owned_file)}),
        encoding="utf-8",
    )

    external_proc = track_popen(
        subprocess.Popen(
            [sys.executable, "-c", FAKE_HTTP_SERVER_CODE, "127.0.0.1", str(port)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=creation_flags(),
        )
    )
    assert _wait_health(port) is True

    clock = FakeClock(1000.0)
    registry = ServerLifecycleRegistry(config_path=cfg_file, owned_pids_path=owned_file, clock=clock)
    manager = FakeServerManager(
        server_path=Path(sys.executable),
        model_path=make_dummy_model(tmp_path),
        port=port,
        startup_timeout=10,
        registry=registry,
    )

    manager.ensure_running()
    assert manager.is_running() is True
    assert manager.using_external_server is True
    assert manager.owned_pid is None
    assert not owned_file.exists() or json.loads(owned_file.read_text(encoding="utf-8"))["servers"] == []

    # Cả stop(), idle 60 phút, lẫn shutdown đều KHÔNG được tắt server ngoài
    manager.stop()
    clock.advance(60 * 60)
    assert registry.check_idle_once() == []
    assert registry.shutdown_and_cleanup(reason="app_exit") == []

    assert external_proc.poll() is None
    assert _is_process_alive(external_proc.pid) is True
    assert _wait_health(port, timeout=2.0) is True


def test_crash_leftover_orphan_cleaned_on_next_launch(tmp_path: Path, spawn_tracker) -> None:
    track_popen, track_pid = spawn_tracker
    port = find_free_port()
    owned_file = tmp_path / "owned_pids.json"
    cfg_file = tmp_path / "lifecycle.json"
    cfg_file.write_text(
        json.dumps({"idle_shutdown_enabled": False, "owned_pids_file": str(owned_file)}),
        encoding="utf-8",
    )

    orphan_proc = track_popen(
        subprocess.Popen(
            [sys.executable, "-c", FAKE_HTTP_SERVER_CODE, "127.0.0.1", str(port)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=creation_flags(),
        )
    )
    assert _wait_health(port) is True

    p_info = psutil.Process(orphan_proc.pid)
    owned_file.write_text(
        json.dumps(
            {
                "version": 1,
                "servers": [
                    {
                        "pid": orphan_proc.pid,
                        "create_time": p_info.create_time(),
                        "started_at": "2026-11-16T08:06:32+07:00",
                        "owner_app_pid": 99999998,
                        "owner_app_create_time": 12345.0,
                        "host": "127.0.0.1",
                        "port": port,
                        "server_path": sys.executable,
                        "model_path": str(make_dummy_model(tmp_path)),
                        "process_name": p_info.name(),
                        "cmdline": p_info.cmdline(),
                    }
                ],
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    registry = ServerLifecycleRegistry(config_path=cfg_file, owned_pids_path=owned_file)
    manager = FakeServerManager(
        server_path=Path(sys.executable),
        model_path=make_dummy_model(tmp_path),
        port=port,
        startup_timeout=15,
        registry=registry,
    )

    try:
        manager.ensure_running()
        assert wait_dead(orphan_proc.pid) is True
        assert manager.owned_pid is not None
        assert manager.owned_pid != orphan_proc.pid
        track_pid(manager.owned_pid)
        assert manager.is_running() is True
    finally:
        registry.shutdown_and_cleanup(reason="test_cleanup")


def test_orphan_cleanup_protects_reused_pid_and_live_other_instance(tmp_path: Path, spawn_tracker) -> None:
    track_popen, _ = spawn_tracker
    owned_file = tmp_path / "owned_pids.json"
    cfg_file = tmp_path / "lifecycle.json"
    cfg_file.write_text(
        json.dumps({"idle_shutdown_enabled": False, "owned_pids_file": str(owned_file)}),
        encoding="utf-8",
    )

    unrelated_proc = track_popen(
        subprocess.Popen(
            [sys.executable, "-c", SLEEP_PROCESS_CODE],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=creation_flags(),
        )
    )
    unrelated_info = psutil.Process(unrelated_proc.pid)

    other_app_proc = track_popen(
        subprocess.Popen(
            [sys.executable, "-c", SLEEP_PROCESS_CODE],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=creation_flags(),
        )
    )
    other_app_info = psutil.Process(other_app_proc.pid)
    other_server_proc = track_popen(
        subprocess.Popen(
            [sys.executable, "-c", SLEEP_PROCESS_CODE],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=creation_flags(),
        )
    )
    other_server_info = psutil.Process(other_server_proc.pid)

    owned_file.write_text(
        json.dumps(
            {
                "version": 1,
                "servers": [
                    {
                        "pid": unrelated_proc.pid,
                        "create_time": unrelated_info.create_time() - 3600.0,
                        "started_at": "2026-11-16T08:06:32+07:00",
                        "owner_app_pid": 99999997,
                        "owner_app_create_time": 1000.0,
                        "host": "127.0.0.1",
                        "port": 8080,
                        "server_path": sys.executable,
                        "model_path": "dummy.gguf",
                        "process_name": unrelated_info.name(),
                        "cmdline": unrelated_info.cmdline(),
                    },
                    {
                        "pid": other_server_proc.pid,
                        "create_time": other_server_info.create_time(),
                        "started_at": "2026-11-17T00:05:00+07:00",
                        "owner_app_pid": other_app_proc.pid,
                        "owner_app_create_time": other_app_info.create_time(),
                        "host": "127.0.0.1",
                        "port": 8080,
                        "server_path": sys.executable,
                        "model_path": "dummy.gguf",
                        "process_name": other_server_info.name(),
                        "cmdline": other_server_info.cmdline(),
                    },
                ],
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    registry = ServerLifecycleRegistry(config_path=cfg_file, owned_pids_path=owned_file)
    cleaned = registry.cleanup_orphaned_servers()
    assert cleaned == []
    assert _is_process_alive(unrelated_proc.pid) is True
    assert _is_process_alive(other_server_proc.pid) is True

    remaining = json.loads(owned_file.read_text(encoding="utf-8"))["servers"]
    assert [item["pid"] for item in remaining] == [other_server_proc.pid]


def test_idle_timeout_15_minutes_shuts_down_and_restarts_on_demand(tmp_path: Path, spawn_tracker) -> None:
    _, track_pid = spawn_tracker
    port = find_free_port()
    owned_file = tmp_path / "owned_pids.json"

    repo_cfg = load_lifecycle_config(PROJECT_ROOT / "config" / "llama_lifecycle.json")
    assert repo_cfg.idle_shutdown_enabled is True
    assert repo_cfg.idle_timeout_minutes == 15.0

    clock = FakeClock(1000.0)
    registry = ServerLifecycleRegistry(
        config_path=PROJECT_ROOT / "config" / "llama_lifecycle.json",
        owned_pids_path=owned_file,
        clock=clock,
    )
    manager = FakeServerManager(
        server_path=Path(sys.executable),
        model_path=make_dummy_model(tmp_path),
        port=port,
        startup_timeout=15,
        registry=registry,
    )

    try:
        manager.ensure_running()
        first_pid = manager.owned_pid
        assert first_pid is not None
        track_pid(first_pid)

        clock.advance(14 * 60 + 59)
        assert registry.check_idle_once() == []
        assert _is_process_alive(first_pid) is True

        clock.advance(2)
        stopped = registry.check_idle_once()
        assert stopped == [first_pid]
        assert wait_dead(first_pid) is True
        assert manager.is_running() is False

        manager.ensure_running()
        second_pid = manager.owned_pid
        assert second_pid is not None
        assert second_pid != first_pid
        track_pid(second_pid)
        assert manager.is_running() is True
    finally:
        registry.shutdown_and_cleanup(reason="test_cleanup")


def test_idle_timeout_respects_active_requests_and_config_overrides(tmp_path: Path, spawn_tracker) -> None:
    _, track_pid = spawn_tracker
    port = find_free_port()
    owned_file = tmp_path / "owned_pids.json"
    cfg_file = tmp_path / "lifecycle.json"
    cfg_file.write_text(
        json.dumps({"idle_shutdown_enabled": False, "idle_timeout_minutes": 1, "owned_pids_file": str(owned_file)}),
        encoding="utf-8",
    )

    clock = FakeClock(5000.0)
    registry = ServerLifecycleRegistry(config_path=cfg_file, owned_pids_path=owned_file, clock=clock)
    manager = FakeServerManager(
        server_path=Path(sys.executable),
        model_path=make_dummy_model(tmp_path),
        port=port,
        startup_timeout=15,
        registry=registry,
    )

    try:
        manager.ensure_running()
        pid = manager.owned_pid
        assert pid is not None
        track_pid(pid)

        clock.advance(120 * 60)
        assert registry.check_idle_once() == []
        assert _is_process_alive(pid) is True

        cfg_file.write_text(
            json.dumps({"idle_shutdown_enabled": True, "idle_timeout_minutes": 2, "owned_pids_file": str(owned_file)}),
            encoding="utf-8",
        )
        registry.touch_activity()

        with registry.request_scope():
            clock.advance(5 * 60)
            assert registry.check_idle_once() == []
            assert _is_process_alive(pid) is True

        clock.advance(119)
        assert registry.check_idle_once() == []
        clock.advance(2)
        assert registry.check_idle_once() == [pid]
        assert wait_dead(pid) is True
    finally:
        registry.shutdown_and_cleanup(reason="test_cleanup")


def test_controller_keeps_server_alive_across_turns_and_tracks_activity(tmp_path: Path, monkeypatch, spawn_tracker) -> None:
    _, track_pid = spawn_tracker
    port = find_free_port()
    owned_file = tmp_path / "owned_pids.json"
    cfg_file = tmp_path / "lifecycle.json"
    cfg_file.write_text(
        json.dumps({"idle_shutdown_enabled": True, "idle_timeout_minutes": 15, "owned_pids_file": str(owned_file)}),
        encoding="utf-8",
    )

    clock = FakeClock(2000.0)
    registry = ServerLifecycleRegistry(config_path=cfg_file, owned_pids_path=owned_file, clock=clock)
    monkeypatch.setattr("llm.server_lifecycle._DEFAULT_REGISTRY", registry)

    manager = FakeServerManager(
        server_path=Path(sys.executable),
        model_path=make_dummy_model(tmp_path),
        port=port,
        startup_timeout=15,
        registry=registry,
    )

    agent = LocalAgent(
        config=AgentConfig(
            provider="local",
            endpoint=f"http://127.0.0.1:{port}/v1/chat/completions",
            server_host="127.0.0.1",
            server_port=port,
            auto_start_server=True,
        ),
        server_manager=manager,
    )

    try:
        agent._ensure_server("qwen38_iq3s")
        pid = manager.owned_pid
        assert pid is not None
        track_pid(pid)

        clock.advance(10 * 60)
        msg = agent._chat(
            [{"role": "user", "content": "ping"}],
            tool_definitions=[],
            max_tokens=64,
        )
        assert msg["content"] == "fake-server-ok"

        agent.close()
        assert _is_process_alive(pid) is True

        clock.advance(6 * 60)
        assert registry.check_idle_once() == []
        assert _is_process_alive(pid) is True

        clock.advance(10 * 60)
        assert registry.check_idle_once() == [pid]
        assert wait_dead(pid) is True
    finally:
        registry.shutdown_and_cleanup(reason="test_cleanup")


def test_process_tools_and_llm_settings_sync_with_lifecycle(tmp_path: Path, monkeypatch, spawn_tracker) -> None:
    _, track_pid = spawn_tracker
    port = find_free_port()
    owned_file = tmp_path / "owned_pids.json"
    cfg_file = tmp_path / "lifecycle.json"
    cfg_file.write_text(
        json.dumps({"idle_shutdown_enabled": True, "idle_timeout_minutes": 15, "owned_pids_file": str(owned_file)}),
        encoding="utf-8",
    )

    clock = FakeClock(3000.0)
    registry = ServerLifecycleRegistry(config_path=cfg_file, owned_pids_path=owned_file, clock=clock)
    monkeypatch.setattr("llm.server_lifecycle._DEFAULT_REGISTRY", registry)

    manager = FakeServerManager(
        server_path=Path(sys.executable),
        model_path=make_dummy_model(tmp_path),
        port=port,
        startup_timeout=15,
        registry=registry,
    )

    try:
        manager.ensure_running()
        pid = manager.owned_pid
        assert pid is not None
        track_pid(pid)

        # test_llm_connection trên endpoint local phải làm mới thời điểm hoạt động
        clock.advance(10 * 60)
        ok, _ = probe_llm_connection(
            endpoint=f"http://127.0.0.1:{port}/v1/chat/completions",
            model="qwen38_iq3s",
            provider="local",
        )
        assert ok is True
        clock.advance(6 * 60)
        assert registry.check_idle_once() == []

        # stop_managed_process dừng llama-server phải gỡ PID khỏi owned_pids.json
        real_process_cls = psutil.Process

        class _FakeLlamaProcess(real_process_cls):
            def name(self):
                return "llama-server.exe"

        monkeypatch.setattr("agent.process_tools.psutil.Process", _FakeLlamaProcess)
        res = stop_managed_process(pid)
        assert res["stopped"] is True
        assert wait_dead(pid) is True
        assert registry.owned_pids() == []
        data = json.loads(owned_file.read_text(encoding="utf-8"))
        assert data["servers"] == []
    finally:
        registry.shutdown_and_cleanup(reason="test_cleanup")
