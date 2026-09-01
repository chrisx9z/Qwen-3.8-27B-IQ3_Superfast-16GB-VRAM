from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import requests

try:
    import psutil
except ImportError:
    psutil = None


APP_ROOT = Path(os.environ.get("M_AUTO_PILOT_ROOT", Path(__file__).resolve().parent.parent)).resolve()

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
        return Path(configured)

    for candidate in candidates:
        marker = candidate.with_name(candidate.name + ".downloading")
        if candidate.exists() and not marker.exists():
            return candidate

    return candidates[0] if candidates else Path("model.gguf")


def _model_available(path: Path) -> bool:
    marker = path.with_name(path.name + ".downloading")
    return path.exists() and not marker.exists()


QWEN38_IQ3S_MODEL_CANDIDATES = _model_candidates(
    "Qwen3.8-27B-UD-IQ3_S.gguf",
    "Qwen3.8-27B-IQ3_S.gguf",
    "Qwen2.5-32B-Instruct-IQ3_S.gguf",
)

QWEN38_MODEL_PATH = Path(
    os.environ.get(
        "M_AUTO_PILOT_MODEL_PATH",
        str(_configured_path("M_AUTO_PILOT_MODEL_PATH", QWEN38_IQ3S_MODEL_CANDIDATES)),
    )
)

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
        model_path: Path | None = None,
        context_size: int = 16384,
        startup_timeout: int = 300,
        profile: str | None = None,
        reasoning: str = "off",
        host: str = SERVER_HOST,
        port: int = AGENT_SERVER_PORT,
        replace_existing: bool = False,
    ) -> None:
        self.server_path = server_path.resolve() if isinstance(server_path, Path) else Path(server_path)
        self.host = host.strip() or SERVER_HOST
        self.port = max(1, min(65535, int(port)))
        self.base_url = f"http://{self.host}:{self.port}"
        self.health_url = f"{self.base_url}/health"
        self.props_url = f"{self.base_url}/props"
        self._process: subprocess.Popen | None = None
        self.startup_timeout = startup_timeout
        self.context_size = context_size
        self.reasoning = reasoning
        self.replace_existing = replace_existing
        self.profile = "qwen38_iq3s"

        self.model_path = (
            model_path.resolve()
            if model_path
            else QWEN38_MODEL_PATH.resolve()
        )

    def is_running(self) -> bool:
        try:
            res = requests.get(self.health_url, timeout=1.0)
            return res.status_code == 200
        except Exception:
            return False

    is_ready = is_running

    def ensure_running(self) -> None:
        if self.is_running():
            return
        self.start()

    def start(self) -> None:
        if not self.model_path.is_file():
            raise FileNotFoundError(
                f"Model file not found: {self.model_path}. "
                f"Please download Qwen3.8-27B-UD-IQ3_S.gguf and place it into {MODEL_DIR_CANDIDATES[0]} or ~/.auto_pilot/models/"
            )

        cmd = self._build_command()
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        log_file = open(LOG_PATH, "w", encoding="utf-8")

        creation_flags = 0
        if IS_WINDOWS and hasattr(subprocess, "CREATE_NO_WINDOW"):
            creation_flags = subprocess.CREATE_NO_WINDOW

        self._process = subprocess.Popen(
            cmd,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            creationflags=creation_flags,
        )

        # Wait for server readiness
        start_time = time.time()
        while time.time() - start_time < self.startup_timeout:
            if self.is_running():
                return
            if self._process.poll() is not None:
                raise RuntimeError(f"llama-server terminated unexpectedly. Check {LOG_PATH}")
            time.sleep(0.5)

        raise TimeoutError(f"llama-server timed out after {self.startup_timeout}s.")

    def _build_command(self) -> list[str]:
        cmd = [
            str(self.server_path),
            "--model", str(self.model_path),
            "--host", self.host,
            "--port", str(self.port),
            "-c", str(self.context_size),
            "-ngl", "99",
            "--flash-attn", "on",
            "-b", "2048",
            "-ub", "512",
            "--cont-batching",
            "--ctx-shift",
        ]
        lookup_ngram = os.environ.get("M_AUTO_PILOT_LOOKUP_NGRAM", "3").strip()
        if lookup_ngram and lookup_ngram != "0":
            cmd.extend(["--lookup-ngram-min", lookup_ngram])

        draft_model = os.environ.get("M_AUTO_PILOT_DRAFT_MODEL", "").strip()
        if draft_model and Path(draft_model).is_file():
            cmd.extend(["--model-draft", draft_model, "--draft-max", "16", "--draft-min", "2"])

        return cmd

    def stop(self) -> None:
        if self._process and self._process.poll() is None:
            self._process.terminate()
            try:
                self._process.wait(timeout=3)
            except Exception:
                self._process.kill()
