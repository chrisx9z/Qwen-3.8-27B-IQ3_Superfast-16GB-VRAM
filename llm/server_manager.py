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

LLAMA_SERVER_PATH = (
    APP_ROOT
    / "tools"
    / "llama.cpp"
    / "llama-server.exe"
)

MODEL_PATH = (
    APP_ROOT
    / "models"
    / "Qwen3-14B-Q4_K_M.gguf"
)

FALLBACK_MODEL_PATH = (
    APP_ROOT
    / "models"
    / "Qwen3-8B-Q4_K_M.gguf"
)

QWEN36_MODEL_PATH = (
    APP_ROOT
    / "models"
    / "experimental"
    / "Qwen3.6-35B-A3B-GGUF"
    / "Qwen3.6-35B-A3B-Q4_K_M.gguf"
)

QWEN36_MTP_PATH = (
    APP_ROOT
    / "models"
    / "experimental"
    / "Qwen3.6-35B-A3B-GGUF"
    / "mtp-Qwen3.6-35B-A3B-Q4_0.gguf"
)


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


QWEN38_Q4_MODEL_CANDIDATES = (
    APP_ROOT / "models" / "Qwen3.8-27B-UD-Q4_K_M.gguf",
    APP_ROOT / "models" / "Qwen3.8-27B-Q4_K_M.gguf",
    APP_ROOT
    / "models"
    / "experimental"
    / "Qwen3.8-27B-GGUF"
    / "Qwen3.8-27B-UD-Q4_K_M.gguf",
    APP_ROOT
    / "models"
    / "experimental"
    / "Qwen3.8-27B-GGUF"
    / "Qwen3.8-27B-Q4_K_M.gguf",
)

QWEN38_Q6_MODEL_CANDIDATES = (
    APP_ROOT / "models" / "Qwen3.8-27B-UD-Q6_K_M.gguf",
    APP_ROOT / "models" / "Qwen3.8-27B-Q6_K_M.gguf",
    APP_ROOT / "models" / "Qwen3.8-27B-Q6_K.gguf",
    APP_ROOT / "models" / "Qwen3.8-27B-Q6_K_L.gguf",
    APP_ROOT
    / "models"
    / "experimental"
    / "Qwen3.8-27B-GGUF"
    / "Qwen3.8-27B-UD-Q6_K_M.gguf",
    APP_ROOT
    / "models"
    / "experimental"
    / "Qwen3.8-27B-GGUF"
    / "Qwen3.8-27B-Q6_K_M.gguf",
)

QWEN38_Q4_MODEL_PATH = Path(
    os.environ.get(
        "AI_VIDEO_QWEN38_MODEL_PATH",
        str(
            _configured_path(
                "AI_VIDEO_QWEN38_Q4_MODEL_PATH",
                QWEN38_Q4_MODEL_CANDIDATES,
            )
        ),
    )
)

QWEN38_Q6_MODEL_PATH = _configured_path(
    "AI_VIDEO_QWEN38_Q6_MODEL_PATH",
    QWEN38_Q6_MODEL_CANDIDATES,
)

QWEN38_MODEL_PATH = QWEN38_Q4_MODEL_PATH

QWEN38_MTP_PATH = Path(
    os.environ.get(
        "AI_VIDEO_QWEN38_MTP_PATH",
        str(
            APP_ROOT
            / "models"
            / "experimental"
            / "Qwen3.8-27B-GGUF"
            / "mtp-Qwen3.8-27B-Q4_0.gguf"
        ),
    )
)

SERVER_HOST = "127.0.0.1"
SERVER_PORT = 8080
AGENT_SERVER_PORT = 8090

BASE_URL = f"http://{SERVER_HOST}:{SERVER_PORT}"
HEALTH_URL = f"{BASE_URL}/health"

LOG_PATH = APP_ROOT / "logs" / "llama-server.log"


class LocalLLMServerManager:
    """
    Quản lý llama-server chạy cục bộ.

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
        fallback_model_path: Path = FALLBACK_MODEL_PATH,
        context_size: int = 8192,
        startup_timeout: int = 120,
        profile: str | None = None,
        reasoning: str = "off",
        host: str = SERVER_HOST,
        port: int = SERVER_PORT,
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
        selected_profile = (
            profile
            if profile is not None
            else os.environ.get(
                "AI_VIDEO_LLM_PROFILE",
                "auto",
            )
        ).strip().lower()
        if selected_profile not in {
            "auto",
            "qwen38",
            "qwen38_q4",
            "qwen38_q6",
            "qwen38_mtp",
            "qwen36",
            "qwen36_mtp",
            "qwen14",
        }:
            selected_profile = "auto"

        self.profile = selected_profile
        self.reasoning = (
            reasoning.strip().lower()
            if reasoning.strip().lower() in {"on", "off", "auto"}
            else "off"
        )
        self.qwen38_quant = "q4"

        if selected_profile == "qwen38_q6":
            self.qwen38_quant = "q6"
        elif selected_profile == "auto":
            if (
                not _model_available(QWEN38_Q4_MODEL_PATH)
                and _model_available(QWEN38_Q6_MODEL_PATH)
            ):
                self.qwen38_quant = "q6"

        self.qwen38_model_path = (
            QWEN38_Q6_MODEL_PATH
            if self.qwen38_quant == "q6"
            else QWEN38_Q4_MODEL_PATH
        )
        self.qwen38_mtp_enabled = model_path is None and (
            selected_profile == "qwen38_mtp"
            or (
                selected_profile == "auto"
                and _model_available(self.qwen38_model_path)
                and QWEN38_MTP_PATH.exists()
            )
        )
        self.qwen38_enabled = model_path is None and (
            self.qwen38_mtp_enabled
            or selected_profile in {
                "qwen38",
                "qwen38_q4",
                "qwen38_q6",
            }
            or (
                selected_profile == "auto"
                and _model_available(self.qwen38_model_path)
            )
        )
        self.qwen36_mtp_enabled = model_path is None and (
            selected_profile == "qwen36_mtp"
            or (
                selected_profile == "auto"
                and not self.qwen38_enabled
                and QWEN36_MODEL_PATH.exists()
                and QWEN36_MTP_PATH.exists()
            )
        )
        self.qwen36_enabled = model_path is None and (
            self.qwen36_mtp_enabled
            or selected_profile == "qwen36"
            or (
                selected_profile == "auto"
                and not self.qwen38_enabled
                and QWEN36_MODEL_PATH.exists()
            )
        )
        self.mtp_enabled = (
            self.qwen38_mtp_enabled
            or self.qwen36_mtp_enabled
        )
        self.mtp_model_path = (
            (
                QWEN38_MTP_PATH
                if self.qwen38_mtp_enabled
                else QWEN36_MTP_PATH
            ).resolve()
            if self.mtp_enabled
            else None
        )
        self.primary_model_path = (
            (
                self.qwen38_model_path
                if self.qwen38_enabled
                else (
                    QWEN36_MODEL_PATH
                    if self.qwen36_enabled
                    else (model_path or MODEL_PATH)
                )
            )
        ).resolve()
        self.fallback_model_path = fallback_model_path.resolve()
        self.model_path = self._select_model_path()
        self.context_size = max(1024, int(context_size))
        if self.qwen38_enabled:
            self.startup_timeout = max(startup_timeout, 300)
        elif self.mtp_enabled:
            self.context_size = min(self.context_size, 4096)
            self.startup_timeout = max(startup_timeout, 300)
        elif self.qwen36_enabled:
            self.context_size = min(self.context_size, 4096)
            self.startup_timeout = max(startup_timeout, 180)
        else:
            self.startup_timeout = startup_timeout

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
            return Path(running_path).resolve() == self.model_path.resolve()
        except OSError:
            return running_path.lower() == str(self.model_path).lower()

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

        if self.mtp_enabled:
            missing = [
                path
                for path in (
                    self.model_path,
                    self.mtp_model_path,
                )
                if path is not None and not path.exists()
            ]
            if missing:
                model_name = (
                    f"Qwen3.8-27B {self.qwen38_quant.upper()}"
                    if self.qwen38_mtp_enabled
                    else "Qwen3.6"
                )
                raise FileNotFoundError(
                    f"Không tìm thấy đủ model {model_name} MTP.\n\n"
                    + "\n".join(str(path) for path in missing)
                )
            return

        if self.qwen38_enabled:
            if not _model_available(self.model_path):
                raise FileNotFoundError(
                    f"Không tìm thấy model Qwen3.8-27B {self.qwen38_quant.upper()}.\n\n"
                    f"{self.model_path}\n\n"
                    "Đặt model đúng profile hoặc cấu hình "
                    "AI_VIDEO_QWEN38_Q4_MODEL_PATH/"
                    "AI_VIDEO_QWEN38_Q6_MODEL_PATH."
                )
            return

        if self.qwen36_enabled:
            if not self.model_path.exists():
                raise FileNotFoundError(
                    "Không tìm thấy model Qwen3.6 base.\n\n"
                    f"{self.model_path}"
                )
            return

        if not self.model_path.exists():
            raise FileNotFoundError(
                "Không tìm thấy model GGUF.\n\n"
                "Ứng dụng ưu tiên Qwen3.8-27B, sau đó Qwen3.6, "
                "Qwen3-14B và fallback Qwen3-8B ở profile auto.\n\n"
                f"Model chính:\n{self.primary_model_path}\n\n"
                f"Model fallback:\n{self.fallback_model_path}"
            )

    def _select_model_path(self) -> Path:
        if self.primary_model_path.exists():
            return self.primary_model_path

        if (
            self.profile in {
                "qwen38",
                "qwen38_q4",
                "qwen38_q6",
                "qwen38_mtp",
                "qwen36",
                "qwen36_mtp",
            }
            or self.qwen38_enabled
            or self.qwen36_enabled
        ):
            return self.primary_model_path

        if self.fallback_model_path.exists():
            return self.fallback_model_path

        return self.primary_model_path

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

            if process_name != "llama-server.exe":
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
        command = [
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
            "1",

            "--cont-batching",

            "--cache-prompt",

            "--n-gpu-layers",
            "auto",

            "--flash-attn",
            "on",

            "--cache-type-k",
            "q8_0",

            "--cache-type-v",
            "q8_0",

            "--reasoning",
            self.reasoning,

            "--log-file",
            str(LOG_PATH),
        ]

        if self.mtp_enabled and self.mtp_model_path is not None:
            command.extend([
                "--spec-draft-model",
                str(self.mtp_model_path),
                "--spec-type",
                "draft-mtp",
                "--spec-draft-n-max",
                os.environ.get("AI_VIDEO_MTP_DRAFT_MAX", "3"),
                "--spec-draft-ngl",
                "auto",
                "--n-cpu-moe",
                os.environ.get("AI_VIDEO_N_CPU_MOE", "32"),
                "--reasoning-budget",
                "0",
            ])

        return command

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
