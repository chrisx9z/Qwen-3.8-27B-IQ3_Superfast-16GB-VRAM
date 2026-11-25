from __future__ import annotations

import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

import requests

from llm.server_lifecycle import (
    ServerLifecycleRegistry,
    _terminate_pid_tree,
    get_lifecycle_registry,
    install_exit_handlers,
)

try:
    import psutil
except ImportError:
    psutil = None


def _resolve_app_root() -> Path:
    configured = os.environ.get("M_AUTO_PILOT_ROOT", "").strip()
    if configured:
        return Path(configured).resolve()
    if getattr(sys, "frozen", False):
        exe_parent = Path(sys.executable).parent
        if (exe_parent / "agent").is_dir() and (exe_parent / "ui").is_dir():
            return exe_parent.resolve()
        vibe_path = Path(r"D:\Vibe Code\M-Auto-Pilot")
        if vibe_path.is_dir():
            return vibe_path.resolve()
        return exe_parent.resolve()
    return Path(__file__).resolve().parent.parent


APP_ROOT = _resolve_app_root()

IS_MACOS = sys.platform == "darwin"
IS_WINDOWS = sys.platform == "win32"

# Thư mục model ứng viên đa nền tảng
def _get_model_dir_candidates() -> list[Path]:
    custom_dir = os.environ.get("M_AUTO_PILOT_MODELS_DIR", "").strip()
    candidates: list[Path] = []
    if custom_dir:
        candidates.append(Path(custom_dir).resolve())
    
    candidates.extend([
        APP_ROOT / "models",
        Path.home() / ".auto_pilot" / "models",
        Path.home() / "models",
    ])
    
    if IS_WINDOWS:
        candidates.append(Path(r"D:\AI-Video-Localizer\models"))
        candidates.append(Path(r"D:\models"))
        candidates.append(Path(r"C:\models"))
    elif IS_MACOS:
        candidates.append(Path("/opt/homebrew/share/models"))
        candidates.append(Path("/usr/local/share/models"))
        
    return candidates


MODEL_DIR_CANDIDATES = tuple(_get_model_dir_candidates())


def _llama_server_candidates() -> tuple[Path, ...]:
    configured = os.environ.get("M_AUTO_PILOT_LLAMA_SERVER", "").strip()
    candidates: list[Path] = []
    if configured:
        candidates.append(Path(configured))
    
    which_server = shutil.which("llama-server")
    if which_server:
        candidates.append(Path(which_server))

    if IS_MACOS:
        candidates.extend([
            Path("/opt/homebrew/bin/llama-server"),
            Path("/usr/local/bin/llama-server"),
            Path.home() / ".local" / "bin" / "llama-server",
            APP_ROOT / "tools" / "llama.cpp" / "llama-server",
        ])
    elif IS_WINDOWS:
        candidates.extend([
            Path(r"D:\AI-Video-Localizer\tools\llama.cpp\llama-server.exe"),
            APP_ROOT / "tools" / "llama.cpp" / "llama-server.exe",
            Path.home() / ".local" / "bin" / "llama-server.exe",
        ])

    return tuple(candidates)


def _first_existing(*paths: Path) -> Path:
    for path in paths:
        if path.is_file():
            return path
    return paths[0] if paths else Path("llama-server")


LLAMA_SERVER_PATH = _first_existing(*_llama_server_candidates())


def _model_candidates(*filenames: str) -> tuple[Path, ...]:
    candidates: list[Path] = []
    for directory in MODEL_DIR_CANDIDATES:
        for filename in filenames:
            candidates.append(directory / filename)
    return tuple(candidates)


def _configured_path(
    env_name: str,
    candidates: tuple[Path, ...],
) -> Path:
    configured = os.environ.get(env_name, "").strip()
    if configured:
        candidate_p = Path(configured)
        marker = candidate_p.with_name(candidate_p.name + ".downloading")
        if candidate_p.exists() and not marker.exists():
            return candidate_p

    for candidate in candidates:
        marker = candidate.with_name(candidate.name + ".downloading")
        if candidate.exists() and not marker.exists():
            return candidate

    return candidates[0] if candidates else Path("model.gguf")


def _model_available(path: Path) -> bool:
    marker = path.with_name(path.name + ".downloading")
    return path.exists() and not marker.exists()


# 25/11/2026 (chủ dự án chốt): CHỈ dùng Qwen3.8-27B Heretic GSQ-RCO IQ3_S-mtp (đầu MTP nhúng sẵn).
QWEN38_IQ3S_MODEL_CANDIDATES = _model_candidates(
    "RVN-Qwen3.8-27B-Heretic-GSQ-RCO-IQ3_S-mtp.gguf",
)

QWEN38_MODEL_PATH = _configured_path("M_AUTO_PILOT_MODEL_PATH", QWEN38_IQ3S_MODEL_CANDIDATES)

SERVER_HOST = "127.0.0.1"
AGENT_SERVER_PORT = 8080

LOG_PATH = APP_ROOT / "logs" / "llama-server.log"


class LocalLLMServerManager:
    """
    Quản lý llama-server chạy cục bộ với model Qwen3.8-27B IQ3_S trên Windows CUDA & macOS Metal.
    """

    def __init__(
        self,
        *,
        server_path: Path = LLAMA_SERVER_PATH,
        model_path: Path | str | None = None,
        context_size: int = 32768,
        startup_timeout: int = 300,
        profile: str | None = None,
        reasoning: str = "off",
        host: str = SERVER_HOST,
        port: int = AGENT_SERVER_PORT,
        replace_existing: bool = False,
        registry: ServerLifecycleRegistry | None = None,
    ) -> None:
        self.server_path = server_path.resolve() if isinstance(server_path, Path) else Path(server_path)
        self.host = host.strip() or SERVER_HOST
        self.port = max(1, min(65535, int(port)))
        self.base_url = f"http://{self.host}:{self.port}"
        self.health_url = f"{self.base_url}/health"
        self.props_url = f"{self.base_url}/props"
        self._process: subprocess.Popen | None = None
        self._owned_pid: int | None = None
        self._using_external_server: bool = False
        self._start_lock = threading.RLock()
        self._registry = registry or get_lifecycle_registry()
        self.startup_timeout = startup_timeout
        self.context_size = int(os.environ.get("M_AUTO_PILOT_CONTEXT_SIZE", str(context_size or 32768)))
        self.reasoning = reasoning
        self.replace_existing = replace_existing
        self.profile = "qwen38_iq3s"

        self.model_path = (
            Path(model_path).resolve()
            if model_path
            else QWEN38_MODEL_PATH.resolve()
        )

    @property
    def owned_pid(self) -> int | None:
        return self._owned_pid

    @property
    def using_external_server(self) -> bool:
        return self._using_external_server

    def is_running(self) -> bool:
        try:
            res = requests.get(self.health_url, timeout=1.0)
            return res.status_code == 200
        except Exception:
            return False

    is_ready = is_running

    def ensure_running(self) -> None:
        self._registry.cleanup_orphaned_servers()
        if self.is_running():
            owned_pid = self._registry.get_owned_pid_for_endpoint(self.host, self.port)
            if owned_pid is not None:
                self._owned_pid = owned_pid
                self._using_external_server = False
                self._registry.touch_activity()
                self._registry.ensure_idle_monitor_started()
            else:
                # Server ngoài (vd: chay_llama_server_32k.bat / AI-Video-Localizer) -> dùng chung, không sở hữu
                self._owned_pid = None
                self._using_external_server = True
            return
        self.start()

    def start(self) -> None:
        install_exit_handlers()
        with self._start_lock:
            self._registry.cleanup_orphaned_servers()
            if self.is_running():
                owned_pid = self._registry.get_owned_pid_for_endpoint(self.host, self.port)
                if owned_pid is not None:
                    self._owned_pid = owned_pid
                    self._using_external_server = False
                    self._registry.touch_activity()
                    self._registry.ensure_idle_monitor_started()
                else:
                    self._owned_pid = None
                    self._using_external_server = True
                return

            if not self.model_path.is_file():
                fallback = _configured_path("M_AUTO_PILOT_MODEL_PATH", QWEN38_IQ3S_MODEL_CANDIDATES)
                if fallback.is_file():
                    self.model_path = fallback
                else:
                    first_model = QWEN38_IQ3S_MODEL_CANDIDATES[0].name if QWEN38_IQ3S_MODEL_CANDIDATES else "RVN-Qwen3.8-27B-Heretic-GSQ-RCO-IQ3_S-mtp.gguf"
                    raise FileNotFoundError(
                        f"Model file not found: {self.model_path}. "
                        f"Please download {first_model} and place it into {MODEL_DIR_CANDIDATES[0]} or ~/.auto_pilot/models/"
                    )

            cmd = self._build_command()
            LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

            creation_flags = 0
            if IS_WINDOWS and hasattr(subprocess, "CREATE_NO_WINDOW"):
                creation_flags = subprocess.CREATE_NO_WINDOW

            log_file = open(LOG_PATH, "w", encoding="utf-8")
            try:
                self._process = subprocess.Popen(
                    cmd,
                    stdout=log_file,
                    stderr=subprocess.STDOUT,
                    creationflags=creation_flags,
                )
            finally:
                try:
                    log_file.close()
                except OSError:
                    pass

            self._owned_pid = int(self._process.pid)
            self._using_external_server = False
            self._registry.register_process(
                self._process,
                host=self.host,
                port=self.port,
                server_path=self.server_path,
                model_path=self.model_path,
            )

            # Wait for server readiness
            start_time = time.time()
            while time.time() - start_time < self.startup_timeout:
                if self.is_running():
                    self._registry.touch_activity()
                    return
                if self._process.poll() is not None:
                    self.stop()
                    raise RuntimeError(f"llama-server terminated unexpectedly. Check {LOG_PATH}")
                time.sleep(0.5)

            self.stop()
            raise TimeoutError(f"llama-server timed out after {self.startup_timeout}s.")

    def _probe_help_text(self) -> str:
        if not hasattr(self, "_cached_help_text"):
            try:
                creation_flags = 0
                if IS_WINDOWS and hasattr(subprocess, "CREATE_NO_WINDOW"):
                    creation_flags = subprocess.CREATE_NO_WINDOW
                res = subprocess.run(
                    [str(self.server_path), "--help"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                    creationflags=creation_flags,
                )
                self._cached_help_text = res.stdout + res.stderr
            except Exception:
                self._cached_help_text = ""
        return self._cached_help_text

    def _build_command(self) -> list[str]:
        help_txt = self._probe_help_text()

        cache_type = os.environ.get("M_AUTO_PILOT_CACHE_TYPE", "q8_0").strip()
        batch_size = os.environ.get("M_AUTO_PILOT_BATCH_SIZE", "4096").strip()
        ubatch_size = os.environ.get("M_AUTO_PILOT_UBATCH_SIZE", "1024").strip()
        cmd = [
            str(self.server_path),
            "--model", str(self.model_path),
            "--host", self.host,
            "--port", str(self.port),
            "-c", str(self.context_size),
            "-np", "1",
            "-ngl", "99",
            "--cache-type-k", cache_type,
            "--cache-type-v", cache_type,
            "--flash-attn", "on",
            "-b", batch_size,
            "-ub", ubatch_size,
            "-t", "8",
            "-tb", "16",
            "--cont-batching",
        ]

        # Hardware thread priority & low-latency polling (i9-14900K + RTX 5070 Ti)
        if "--prio" in help_txt:
            cmd.extend(["--prio", "2"])
        if "--poll" in help_txt:
            cmd.extend(["--poll", "100"])

        # Prefix caching & System RAM KV/recurrent checkpoint pool (64 GB RAM)
        if "--cache-prompt" in help_txt:
            cmd.append("--cache-prompt")
        if "--cache-ram" in help_txt:
            cache_ram = os.environ.get("M_AUTO_PILOT_CACHE_RAM", "16384").strip()
            if cache_ram:
                cmd.extend(["--cache-ram", cache_ram])
        if "--ctx-checkpoints" in help_txt:
            cmd.extend(["--ctx-checkpoints", "64"])
        if "--checkpoint-min-step" in help_txt:
            cmd.extend(["--checkpoint-min-step", "2048"])

        if self.reasoning == "off":
            if "--reasoning" in help_txt:
                cmd.extend(["--reasoning", "off"])
            if "--no-reasoning-preserve" in help_txt:
                cmd.append("--no-reasoning-preserve")
        elif self.reasoning == "on" and "--reasoning" in help_txt:
            cmd.extend(["--reasoning", "on"])

        # Context shifting: --context-shift (new llama.cpp) vs --ctx-shift (legacy)
        if "--context-shift" in help_txt:
            cmd.append("--context-shift")
        elif "--ctx-shift" in help_txt:
            cmd.append("--ctx-shift")
        elif not help_txt:
            cmd.append("--context-shift")

        # Model *-mtp.gguf: đầu MTP nhúng sẵn -> draft-mtp (thay cho ngram). Tắt: M_AUTO_PILOT_MTP=0
        use_mtp = (
            str(self.model_path).lower().endswith("-mtp.gguf")
            and os.environ.get("M_AUTO_PILOT_MTP", "1").strip() != "0"
            and "draft-mtp" in help_txt
        )
        if use_mtp:
            cmd.extend([
                "--spec-type", "draft-mtp",
                "--spec-draft-n-max", os.environ.get("M_AUTO_PILOT_MTP_DRAFT_MAX", "2"),
            ])

        # Multi-stage lossless speculative N-gram decoding (ngram-mod + ngram-simple + ngram-map-k)
        lookup_ngram = os.environ.get("M_AUTO_PILOT_LOOKUP_NGRAM", "1").strip()
        if lookup_ngram and lookup_ngram != "0" and not use_mtp:
            if "--spec-type" in help_txt:
                spec_type = os.environ.get(
                    "M_AUTO_PILOT_SPEC_TYPE",
                    "ngram-mod,ngram-simple,ngram-map-k",
                ).strip()
                cmd.extend(["--spec-type", spec_type])
                if "--spec-ngram-mod-n-match" in help_txt:
                    cmd.extend(["--spec-ngram-mod-n-match", "16"])
                if "--spec-ngram-mod-n-min" in help_txt:
                    cmd.extend(["--spec-ngram-mod-n-min", "8"])
                if "--spec-ngram-mod-n-max" in help_txt:
                    cmd.extend(["--spec-ngram-mod-n-max", "32"])
                if "--spec-ngram-simple-size-n" in help_txt:
                    cmd.extend(["--spec-ngram-simple-size-n", "4"])
                if "--spec-ngram-simple-size-m" in help_txt:
                    cmd.extend(["--spec-ngram-simple-size-m", "16"])
                if "--spec-ngram-map-k-size-n" in help_txt:
                    cmd.extend(["--spec-ngram-map-k-size-n", "4"])
                if "--spec-ngram-map-k-size-m" in help_txt:
                    cmd.extend(["--spec-ngram-map-k-size-m", "16"])
            elif "--lookup-ngram-min" in help_txt:
                cmd.extend(["--lookup-ngram-min", "3"])

        draft_model = os.environ.get("M_AUTO_PILOT_DRAFT_MODEL", "").strip()
        if draft_model and Path(draft_model).is_file():
            if "--spec-draft-n-max" in help_txt:
                cmd.extend(["--model-draft", draft_model, "--spec-draft-n-max", "16", "--spec-draft-n-min", "2"])
            else:
                cmd.extend(["--model-draft", draft_model, "--draft-max", "16", "--draft-min", "2"])

        lora_adapter = os.environ.get("M_AUTO_PILOT_LORA_ADAPTER", "").strip()
        if not lora_adapter:
            default_lora = APP_ROOT / "work" / "lora_checkpoints" / "lora_adapter.gguf"
            if default_lora.is_file():
                lora_adapter = str(default_lora)

        if lora_adapter and Path(lora_adapter).is_file():
            cmd.extend(["--lora", lora_adapter])

        return cmd

    def stop(self) -> None:
        # Không bao giờ tắt server bên ngoài không do chính app này khởi tạo
        if self._using_external_server and self._owned_pid is None and self._process is None:
            return

        stopped_via_registry = False
        if self._owned_pid is not None:
            stopped_via_registry = self._registry.stop_owned_pid(self._owned_pid)

        if not stopped_via_registry and self._process is not None:
            if self._registry.is_owned_pid(self._process.pid):
                self._registry.stop_owned_pid(self._process.pid)
            elif self._process.poll() is None:
                _terminate_pid_tree(self._process.pid, popen=self._process, grace_timeout=3.0)

        self._process = None
        self._owned_pid = None
