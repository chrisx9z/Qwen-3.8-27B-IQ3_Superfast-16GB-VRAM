from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path

import requests

try:
    import psutil
except ImportError:
    psutil = None


APP_ROOT = Path(os.environ.get("M_AUTO_PILOT_ROOT", Path(__file__).resolve().parent.parent)).resolve()

# Thư mục model dùng chung (M Auto Pilot và AI Video Localizer cùng đọc).
# Có thể ghi đè bằng biến môi trường M_AUTO_PILOT_MODELS_DIR.
SHARED_MODELS_DIR = (
    Path(os.environ["M_AUTO_PILOT_MODELS_DIR"]).resolve()
    if os.environ.get("M_AUTO_PILOT_MODELS_DIR", "").strip()
    else Path(r"D:\AI-Video-Localizer\models")
)

MODEL_DIR_CANDIDATES = (
    APP_ROOT / "models",
    Path.home() / "models",
    Path.home() / ".auto_pilot" / "models",
    Path("/opt/homebrew/share/models"),
    SHARED_MODELS_DIR,
)


def _first_existing(*paths: Path) -> Path:
    for path in paths:
        if path.is_file():
            return path
    return paths[0]


def _llama_server_candidates() -> tuple[Path, ...]:
    import shutil
    configured = os.environ.get("M_AUTO_PILOT_LLAMA_SERVER", "").strip()
    candidates: list[Path] = []
    if configured:
        candidates.append(Path(configured))
    
    # Check PATH first (e.g. brew install llama.cpp)
    which_server = shutil.which("llama-server")
    if which_server:
        candidates.append(Path(which_server))
        
    # Standard macOS Homebrew / Local paths
    candidates.append(Path("/opt/homebrew/bin/llama-server"))
    candidates.append(Path("/usr/local/bin/llama-server"))
    candidates.append(APP_ROOT / "tools" / "llama.cpp" / "llama-server")
    candidates.append(APP_ROOT / "tools" / "llama.cpp" / "llama-server.exe")
    candidates.append(Path.home() / ".auto_pilot" / "tools" / "llama-server")
    candidates.append(Path(r"D:\AI-Video-Localizer\tools\llama.cpp\llama-server.exe"))
    return tuple(candidates)


LLAMA_SERVER_PATH = _first_existing(*_llama_server_candidates())


def _model_candidates(
    *filenames: str,
) -> tuple[Path, ...]:
    candidates: list[Path] = []
    for directory in MODEL_DIR_CANDIDATES:
        for filename in filenames:
            candidates.append(directory / filename)
    candidates.append(
        APP_ROOT
        / "models"
        / "experimental"
        / "Qwen3.8-27B-GGUF"
        / filenames[-1]
    )
    return tuple(candidates)


def _configured_path(
    env_name: str,
    candidates: tuple[Path, ...],
) -> Path:
    configured = os.environ.get(env_name, "").strip()

    if configured:
        return Path(configured)

    for candidate in candidates:
        marker = candidate.with_name(
            candidate.name + ".downloading"
        )
        if candidate.exists() and not marker.exists():
            return candidate

    return candidates[0]


def _model_available(path: Path) -> bool:
    marker = path.with_name(
        path.name + ".downloading"
    )
    return path.exists() and not marker.exists()


# Model duy nhất của M Auto Pilot: Qwen3.8-27B-UD-IQ3_S.
QWEN38_IQ3S_MODEL_CANDIDATES = _model_candidates(
    "Qwen3.8-27B-UD-IQ3_S.gguf",
    "Qwen3.8-27B-IQ3_S.gguf",
)

QWEN38_MODEL_PATH = Path(
    os.environ.get(
        "M_AUTO_PILOT_MODEL_PATH",
        str(
            _configured_path(
                "M_AUTO_PILOT_MODEL_PATH",
                QWEN38_IQ3S_MODEL_CANDIDATES,
            )
        ),
    )
)

SERVER_HOST = "127.0.0.1"
AGENT_SERVER_PORT = 8080

LOG_PATH = APP_ROOT / "logs" / "llama-server.log"


class LocalLLMServerManager:
    """
    Quản lý llama-server chạy cục bộ với model Qwen3.8-27B IQ3_S.

    Trách nhiệm:
    - Kiểm tra server đã hoạt động chưa.
    - Tự khởi động llama-server nếu cần.
    - Chờ server tải model và sẵn sàng.
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
        self.server_path = server_path.resolve()
        self.host = host.strip() or SERVER_HOST
        self.port = max(1, min(65535, int(port)))
        self.base_url = f"http://{self.host}:{self.port}"
        self.health_url = f"{self.base_url}/health"
        self.props_url = f"{self.base_url}/props"
        self._process: subprocess.Popen | None = None
        self.replace_existing = replace_existing
        self.profile = "qwen38_iq3s"
        self.reasoning = (
            reasoning.strip().lower()
            if reasoning.strip().lower() in {"on", "off", "auto"}
            else "off"
        )
        self.model_path = (
            QWEN38_MODEL_PATH
            if model_path is None
            else Path(model_path)
        ).resolve()
        self.context_size = max(1024, int(context_size))
        self.startup_timeout = max(startup_timeout, 300)

    def ensure_running(self) -> None:
        """
        Đảm bảo llama-server đang chạy và sẵn sàng nhận request.
        """

        if self.is_ready():
            if self._running_model_matches():
                return

            if self._process_is_running():
                self.stop()
            elif self.replace_existing and self._stop_external_server():
                pass
            else:
                raise RuntimeError(
                    "Cổng Local LLM đang phục vụ model khác.\n\n"
                    f"Model cần dùng:\n{self.model_path}\n\n"
                    "Hãy dừng server hiện tại rồi thử lại."
                )

        self._validate_files()

        if self._process_is_running():
            self._wait_until_ready()
            return

        self._start_server()
        self._wait_until_ready()

    def is_ready(self) -> bool:
        """
        Kiểm tra endpoint /health.
        """

        try:
            response = requests.get(
                self.health_url,
                timeout=2,
            )

            if not response.ok:
                return False

            try:
                payload = response.json()
            except ValueError:
                # Một số phiên bản server có thể trả nội dung
                # không phải JSON nhưng HTTP 200 vẫn là sẵn sàng.
                return True

            status = str(
                payload.get("status", "")
            ).strip().lower()

            return not status or status in {
                "ok",
                "ready",
            }

        except requests.RequestException:
            return False

    def _running_model_matches(self) -> bool:
        try:
            response = requests.get(
                self.props_url,
                timeout=2,
            )
            response.raise_for_status()
            payload = response.json()
        except (
            requests.RequestException,
            ValueError,
        ):
            return True

        running_path = str(
            payload.get("model_path")
            or payload.get("model_alias")
            or ""
        ).strip()

        if not running_path:
            return True

        try:
            return (
                Path(running_path).name.lower() == self.model_path.name.lower()
                or "qwen" in running_path.lower()
                or Path(running_path).resolve() == self.model_path.resolve()
            )
        except OSError:
            return "qwen" in running_path.lower() or running_path.lower() == str(self.model_path).lower()

    def stop(self) -> None:
        """
        Dừng server nếu server do ứng dụng này khởi động.
        """

        process = self._process

        if process is None:
            return

        if process.poll() is None:
            process.terminate()

            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()

        self._process = None

    def _validate_files(self) -> None:
        if not self.server_path.exists():
            raise FileNotFoundError(
                "Không tìm thấy llama-server.exe:\n"
                f"{self.server_path}"
            )

        if not _model_available(self.model_path):
            raise FileNotFoundError(
                "Không tìm thấy model Qwen3.8-27B IQ3_S.\n\n"
                f"{self.model_path}\n\n"
                "Đặt model trong thư mục models hoặc cấu hình "
                "M_AUTO_PILOT_MODEL_PATH."
            )

    def _process_is_running(self) -> bool:
        process = self._process

        return (
            process is not None
            and process.poll() is None
        )

    def _stop_external_server(self) -> bool:
        if psutil is None:
            return False

        try:
            connections = psutil.net_connections(kind="tcp")
        except psutil.Error:
            return False

        for connection in connections:
            address = connection.laddr
            process_id = connection.pid
            if (
                connection.status != psutil.CONN_LISTEN
                or not address
                or address.port != self.port
                or not process_id
            ):
                continue

            try:
                process = psutil.Process(process_id)
                command = process.cmdline()
                process_name = process.name().lower()
            except (psutil.Error, OSError):
                continue

            if process_name not in ("llama-server.exe", "llama-server"):
                continue

            if not any(
                token.lower() == "--port"
                and index + 1 < len(command)
                and command[index + 1] == str(self.port)
                for index, token in enumerate(command)
            ):
                continue

            try:
                process.terminate()
                process.wait(timeout=10)
            except psutil.TimeoutExpired:
                process.kill()
                process.wait(timeout=10)
            except (psutil.Error, OSError):
                return False

            return True

        return False

    def _start_server(self) -> None:
        command = self._build_command()

        creation_flags = 0

        if hasattr(
            subprocess,
            "CREATE_NO_WINDOW",
        ):
            creation_flags = subprocess.CREATE_NO_WINDOW

        LOG_PATH.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        try:
            log_file = LOG_PATH.open(
                "a",
                encoding="utf-8",
            )
            log_file.write(
                "\n\n=== Starting llama-server ===\n"
            )
            log_file.write(
                " ".join(command)
            )
            log_file.write("\n")
            log_file.flush()

            process = subprocess.Popen(
                command,
                cwd=str(self.server_path.parent),
                stdout=log_file,
                stderr=subprocess.STDOUT,
                creationflags=creation_flags,
            )
        except OSError as error:
            raise RuntimeError(
                "Không thể khởi động llama-server.exe.\n\n"
                f"Chi tiết: {error}"
            ) from error

        self._process = process

    def _build_command(self) -> list[str]:
        cpu_threads = max(4, min(16, (os.cpu_count() or 8) - 2))
        return [
            str(self.server_path),

            "--model",
            str(self.model_path),

            "--host",
            self.host,

            "--port",
            str(self.port),

            "--ctx-size",
            str(self.context_size),

            "--parallel",
            "2",

            "--cont-batching",

            "--cache-prompt",

            "--n-gpu-layers",
            "99",

            "--flash-attn",
            "on",

            "--batch-size",
            "2048",

            "--ubatch-size",
            "512",

            "--threads",
            str(cpu_threads),

            "--cache-type-k",
            "q8_0",

            "--cache-type-v",
            "q8_0",

            "--reasoning",
            self.reasoning,

            "--log-file",
            str(LOG_PATH),
        ]

    def _wait_until_ready(self) -> None:
        deadline = time.monotonic() + self.startup_timeout

        while time.monotonic() < deadline:
            process = self._process

            if (
                process is not None
                and process.poll() is not None
            ):
                exit_code = process.returncode
                self._process = None

                raise RuntimeError(
                    "llama-server đã thoát trong khi tải model.\n\n"
                    f"Mã thoát: {exit_code}"
                )

            if self.is_ready():
                return

            time.sleep(1)

        raise TimeoutError(
            "llama-server mất quá nhiều thời gian để khởi động.\n\n"
            f"Đã chờ {self.startup_timeout} giây nhưng "
            f"{self.health_url} vẫn chưa sẵn sàng."
        )
