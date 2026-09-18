from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

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
    "aggressive",
    "spectral_cascade",
    "informed",
    "surgical",
    "optimized",
    "som",
    "inverted",
    "nuclear",
}

ALLOWED_DTYPES = {"auto", "bfloat16", "float16", "float32"}
ALLOWED_QUANTIZATION = {"4bit", "8bit"}

# Ngưỡng an toàn cho tham số tự do truyền vào CLI.
MAX_EXTRA_ARGS = 20


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

    # ------------------------------------------- packaged liberation pipeline

    def local_gpu_memory_gb(self) -> float:
        """VRAM khả dụng (GB) của GPU đầu tiên, dùng cho ước lượng."""

        try:
            test = subprocess.run(
                [
                    str(self.python),
                    "-c",
                    "import torch;"
                    "p=torch.cuda.get_device_properties(0);"
                    "print(round(p.total_memory/1024**3, 1))",
                ],
                cwd=str(self.root),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=180,
                env=self._child_env(),
            )
            return float(test.stdout.strip().splitlines()[-1])
        except (OSError, subprocess.SubprocessError, ValueError, IndexError):
            return 0.0

    def fit_check(
        self,
        model: str,
        *,
        gpu_mem: int | None = None,
    ) -> dict[str, object]:
        """Ước lượng VRAM cần cho một model và kết luận máy này có chạy được không."""

        name = str(model or "").strip()
        if not name:
            return {"ok": False, "error": "Thiếu tên model HuggingFace."}

        memory = int(gpu_mem or 0) or int(self.local_gpu_memory_gb() or 0)
        if memory <= 0:
            return {"ok": False, "error": "Không đọc được VRAM GPU cục bộ."}

        result = self.run_cli(
            "gpu-calc",
            [name, "--gpu-mem", str(memory)],
            timeout=300,
            tag="gpu-calc",
        )
        output = str(result.get("stdout") or "")
        if not result.get("ok") and not output:
            return {
                "ok": False,
                "error": result.get("error") or result.get("stderr") or "gpu-calc thất bại.",
                "command": result.get("command"),
            }

        needed = re.search(r"Total needed:\s*([0-9.]+)\s*GB", output)
        minimum = re.search(r"Minimum GPUs:\s*(\d+)", output)
        total_params = re.search(r"Total params:\s*([0-9.]+)B", output)

        min_gpus = int(minimum.group(1)) if minimum else 0
        return {
            "ok": True,
            "model": name,
            "gpu_mem_gb": memory,
            "total_params_b": float(total_params.group(1)) if total_params else None,
            "total_needed_gb": float(needed.group(1)) if needed else None,
            "minimum_gpus": min_gpus,
            "fits_this_machine": min_gpus <= 1,
            "verdict": (
                "Chạy được trên máy này (1 GPU)."
                if min_gpus == 1
                else f"Cần tối thiểu {min_gpus} GPU {memory} GB — máy này chỉ có 1."
            ),
            "raw_output_tail": output[-1500:],
        }

    def liberate(
        self,
        model: str,
        *,
        method: str = "advanced",
        dtype: str = "",
        quantization: str = "",
        output_dir: str = "",
        extra_args: list[str] | None = None,
        background: bool = True,
    ) -> dict[str, object]:
        """Đóng gói pipeline abliteration: tải model -> probe -> SVD -> excise -> verify -> save."""

        name = str(model or "").strip()
        if not name:
            return {"ok": False, "error": "Thiếu tên model HuggingFace hoặc đường dẫn checkpoint."}
        if not self.installed:
            return {"ok": False, "error": f"OBLITERATUS chưa được cài: {self.root}"}

        selected_method = str(method or "advanced").strip().lower()
        if selected_method not in ALLOWED_METHODS:
            return {
                "ok": False,
                "error": f"Method không hợp lệ. Cho phép: {sorted(ALLOWED_METHODS)}",
            }

        selected_dtype = str(dtype or "").strip().lower()
        if selected_dtype and selected_dtype not in ALLOWED_DTYPES:
            return {"ok": False, "error": f"dtype không hợp lệ. Cho phép: {sorted(ALLOWED_DTYPES)}"}

        selected_quant = str(quantization or "").strip().lower()
        if selected_quant and selected_quant not in ALLOWED_QUANTIZATION:
            return {
                "ok": False,
                "error": f"quantization không hợp lệ. Cho phép: {sorted(ALLOWED_QUANTIZATION)}",
            }

        extras = [str(value) for value in (extra_args or [])]
        if len(extras) > MAX_EXTRA_ARGS:
            return {"ok": False, "error": f"extra_args tối đa {MAX_EXTRA_ARGS} phần tử."}
        if any(flag in extras for flag in ("--output-dir", "--method", "--gpus", "--remote")):
            return {
                "ok": False,
                "error": "Không truyền --output-dir/--method/--gpus/--remote trong extra_args.",
            }

        destination = self._resolve_output_dir(output_dir, name)
        if isinstance(destination, str):
            return {"ok": False, "error": destination}
        destination.mkdir(parents=True, exist_ok=True)

        args = [name, "--method", selected_method, "--output-dir", str(destination)]
        if selected_dtype:
            args += ["--dtype", selected_dtype]
        if selected_quant:
            args += ["--quantization", selected_quant]
        args += extras

        result = self.run_cli(
            "obliterate",
            args,
            background=background,
            timeout=7200,
            tag=f"liberate-{_slug(name)}",
        )
        result["model"] = name
        result["method"] = selected_method
        result["output_dir"] = str(destination)
        if result.get("ok"):
            result["note"] = (
                "Pipeline abliteration đang chạy. Dùng obliteratus_progress để đọc log, "
                "obliteratus_run(command='runs') để xem danh sách run."
            )
        return result

    def progress(self, *, log_path: str = "", tail: int = 40) -> dict[str, object]:
        """Đọc phần cuối log của một run do adapter tạo (chỉ trong thư mục log)."""

        limit = max(5, min(400, int(tail or 40)))
        if log_path:
            candidate = Path(log_path)
            if not candidate.is_absolute():
                candidate = self.log_dir / candidate
            try:
                resolved = candidate.resolve()
                if not resolved.is_relative_to(self.log_dir.resolve()):
                    return {"ok": False, "error": "Chỉ đọc log trong thư mục obliteratus_logs."}
            except OSError as error:
                return {"ok": False, "error": str(error)}
        else:
            logs = sorted(
                self.log_dir.glob("*.log"),
                key=lambda item: item.stat().st_mtime,
                reverse=True,
            ) if self.log_dir.is_dir() else []
            if not logs:
                return {"ok": False, "error": "Chưa có log run nào."}
            resolved = logs[0]

        if not resolved.is_file():
            return {"ok": False, "error": f"Không thấy log: {resolved}"}

        try:
            lines = resolved.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError as error:
            return {"ok": False, "error": str(error)}

        return {
            "ok": True,
            "log_path": str(resolved),
            "total_lines": len(lines),
            "tail": "\n".join(lines[-limit:]),
            "running": bool(self._processes()),
        }

    def export_gguf(
        self,
        model_dir: str,
        *,
        outtype: str = "f16",
        quant: str = "",
        output_file: str = "",
    ) -> dict[str, object]:
        """Chuyển model đã liberate (HF) sang GGUF cho llama.cpp, tùy chọn quantize."""

        source = Path(str(model_dir or "")).expanduser()
        if not source.is_dir():
            return {"ok": False, "error": f"Không thấy thư mục model: {source}"}

        converter = self._convert_script()
        if converter is None:
            return {
                "ok": False,
                "error": (
                    "Thiếu convert_hf_to_gguf.py của llama.cpp. Tải script này vào "
                    f"{self.llama_cpp_dir} rồi thử lại: "
                    "https://raw.githubusercontent.com/ggml-org/llama.cpp/master/convert_hf_to_gguf.py"
                ),
            }

        quantize_exe = self.llama_cpp_dir / "llama-quantize.exe"
        selected_outtype = str(outtype or "f16").strip().lower() or "f16"
        target_dir = self.root / "liberated-gguf"
        target_dir.mkdir(parents=True, exist_ok=True)
        safe_name = _slug(source.name)
        f16_path = output_file or str(target_dir / f"{safe_name}-{selected_outtype}.gguf")

        convert = subprocess.run(
            [
                str(self.python),
                str(converter),
                str(source),
                "--outfile",
                str(f16_path),
                "--outtype",
                selected_outtype,
            ],
            cwd=str(self.llama_cpp_dir),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=7200,
            env=self._child_env(),
        )
        if convert.returncode != 0:
            return {
                "ok": False,
                "stage": "convert",
                "exit_code": convert.returncode,
                "stderr": (convert.stderr or "")[-1500:],
                "stdout": (convert.stdout or "")[-800:],
            }

        payload: dict[str, object] = {
            "ok": True,
            "stage": "convert",
            "gguf": f16_path,
            "sizes_gb": _file_size_gb(f16_path),
        }

        selected_quant = str(quant or "").strip().upper()
        if selected_quant:
            if not quantize_exe.is_file():
                payload["quantize_error"] = f"Không thấy {quantize_exe}"
                return payload
            quant_path = str(Path(f16_path).with_name(f"{safe_name}-{selected_quant}.gguf"))
            quantize = subprocess.run(
                [str(quantize_exe), str(f16_path), quant_path, selected_quant],
                cwd=str(self.llama_cpp_dir),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=7200,
                env=self._child_env(),
            )
            if quantize.returncode != 0:
                payload["quantize_error"] = (quantize.stderr or "")[-1000:]
                return payload
            payload.update({
                "stage": "quantized",
                "quantized_gguf": quant_path,
                "quant": selected_quant,
                "quantized_sizes_gb": _file_size_gb(quant_path),
            })
        return payload

    @property
    def llama_cpp_dir(self) -> Path:
        configured = os.environ.get("M_AUTO_PILOT_LLAMA_DIR", "").strip()
        if configured:
            return Path(configured)
        return Path(r"D:\AI-Video-Localizer\tools\llama.cpp")

    # ------------------------------------- GGUF: cài model đã liberate sẵn

    @property
    def models_dir(self) -> Path:
        configured = os.environ.get("M_AUTO_PILOT_MODELS_DIR", "").strip()
        if configured:
            return Path(configured)
        return Path(r"D:\AI-Video-Localizer\models")

    @property
    def download_progress_path(self) -> Path:
        return APP_ROOT / "work" / "auto_pilot" / "gguf_download.json"

    @property
    def active_model_path(self) -> Path:
        return APP_ROOT / "work" / "auto_pilot" / "active_model.json"

    def list_gguf_repo(self, repo_id: str) -> dict[str, object]:
        """Liệt kê các file GGUF của repo (để chọn đúng bản quant)."""

        name = str(repo_id or "").strip()
        if not name:
            return {"ok": False, "error": "Thiếu repo HuggingFace."}
        try:
            files = _hf_gguf_files(name)
        except Exception as error:  # noqa: BLE001
            return {"ok": False, "error": f"{type(error).__name__}: {error}"}
        files.sort(key=lambda item: item.get("size_bytes") or 0)
        return {"ok": True, "repo": name, "count": len(files), "files": files}

    def install_gguf(
        self,
        repo_id: str,
        filename: str = "",
        *,
        prefer: str = "IQ3_S",
        target_dir: str = "",
    ) -> dict[str, object]:
        """Tải model GGUF đã liberate (abliterated) về thư mục models của máy."""

        name = str(repo_id or "").strip()
        if not name:
            return {"ok": False, "error": "Thiếu repo HuggingFace."}

        selected = str(filename or "").strip()
        if not selected:
            listing = self.list_gguf_repo(name)
            if not listing.get("ok"):
                return listing
            files = listing.get("files") or []
            marker = str(prefer or "").upper()
            matches = [
                item for item in files
                if marker and marker in str(item["filename"]).upper()
                and "-mtp" not in str(item["filename"]).lower()
            ]
            pool = matches or [item for item in files if "-mtp" not in str(item["filename"]).lower()]
            if not pool:
                return {"ok": False, "error": f"Repo {name} không có file GGUF phù hợp."}
            selected = str(pool[0]["filename"])

        destination = Path(target_dir).expanduser() if target_dir else self.models_dir
        destination.mkdir(parents=True, exist_ok=True)
        expected = None
        try:
            for item in _hf_gguf_files(name):
                if item["filename"] == selected:
                    expected = item.get("size_bytes")
                    break
        except Exception:  # noqa: BLE001
            expected = None
        if not expected:
            expected = _remote_size(name, selected)

        # Đã có sẵn file đủ dung lượng thì bỏ qua tải lại.
        existing = destination / selected
        if existing.is_file() and expected and existing.stat().st_size == int(expected):
            return {
                "ok": True,
                "already_present": True,
                "path": str(existing),
                "size_gb": _file_size_gb(str(existing)),
            }

        script = APP_ROOT / "scripts" / "hf_download_gguf.py"
        if not script.is_file():
            return {"ok": False, "error": f"Thiếu script tải: {script}"}

        downloader = self.python if self.python.is_file() else Path(sys.executable)
        command = [
            str(downloader),
            str(script),
            name,
            selected,
            str(destination),
            str(self.download_progress_path),
        ]
        creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        log_file = self.log_path(f"download-{_slug(selected)}")
        try:
            with log_file.open("a", encoding="utf-8") as handle:
                handle.write(" ".join(command) + "\n")
                handle.flush()
                process = subprocess.Popen(
                    command,
                    cwd=str(APP_ROOT),
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
            "repo": name,
            "filename": selected,
            "dest_dir": str(destination),
            "expected_gb": round(int(expected) / 1024**3, 2) if expected else None,
            "progress_file": str(self.download_progress_path),
            "log_path": str(log_file),
            "note": (
                "Đang tải nền. Dùng obliteratus_download_progress để xem %, "
                "sau đó obliteratus_activate_model để chuyển M Auto Pilot sang model này."
            ),
        }

    def download_progress(self) -> dict[str, object]:
        path = self.download_progress_path
        if not path.is_file():
            return {"ok": False, "error": "Chưa có phiên tải nào."}
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            return {"ok": False, "error": str(error)}
        payload["ok"] = True
        payload["active_model"] = self.active_model_summary()
        return payload

    def _launcher_dir(self) -> Path:
        """Nơi đặt launcher: ưu tiên thư mục chứa M Auto Pilot.exe (kể cả Desktop OneDrive)."""

        configured = os.environ.get("M_AUTO_PILOT_LAUNCHER_DIR", "").strip()
        if configured:
            return Path(configured)
        candidates = [
            Path(r"D:\OneDrive\Desktop"),
            Path.home() / "Desktop",
            Path(r"D:\Desktop"),
            APP_ROOT,
        ]
        for candidate in candidates:
            if (candidate / "M Auto Pilot.exe").is_file():
                return candidate
        for candidate in candidates:
            if candidate.is_dir():
                return candidate
        return APP_ROOT

    def active_model_summary(self) -> dict[str, object]:
        path = self.active_model_path
        if not path.is_file():
            return {"configured": False, "model_path": str(self.models_dir / "Huihui-Qwen3.8-27B-abliterated-UD-IQ3_S.gguf")}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {"configured": False}
        model_path = str(data.get("model_path") or "")
        return {
            "configured": bool(model_path),
            "model_path": model_path,
            "exists": Path(model_path).is_file() if model_path else False,
            "source_repo": data.get("source_repo"),
            "activated_at": data.get("activated_at"),
            "launcher": data.get("launcher"),
        }

    def activate_model(self, gguf_path: str, *, note: str = "") -> dict[str, object]:
        """Ghi nhận model được chọn và tạo launcher chạy M Auto Pilot với model đó."""

        candidate = Path(str(gguf_path or "")).expanduser()
        if not candidate.is_file():
            return {"ok": False, "error": f"Không thấy file GGUF: {candidate}"}

        resolved = candidate.resolve()
        self.active_model_path.parent.mkdir(parents=True, exist_ok=True)

        launcher_dir = self._launcher_dir()
        try:
            launcher_dir.mkdir(parents=True, exist_ok=True)
        except OSError:
            launcher_dir = APP_ROOT
        launcher = launcher_dir / "M Auto Pilot (Uncensored).cmd"
        exe = Path(
            os.environ.get(
                "M_AUTO_PILOT_EXE",
                str(launcher_dir / "M Auto Pilot.exe"),
            )
        )
        content = (
            "@echo off\r\n"
            "rem M Auto Pilot chay voi model da liberate (abliterated)\r\n"
            f'set "M_AUTO_PILOT_MODEL_PATH={resolved}"\r\n'
            f'start "" "{exe}"\r\n'
        )
        try:
            launcher.write_text(content, encoding="utf-8")
        except OSError as error:
            launcher = None  # type: ignore[assignment]
            launcher_error = str(error)
        else:
            launcher_error = ""

        record = {
            "model_path": str(resolved),
            "size_gb": _file_size_gb(str(resolved)),
            "note": note,
            "activated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "launcher": str(launcher) if launcher else "",
            "exe": str(exe),
        }
        try:
            self.active_model_path.write_text(
                json.dumps(record, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except OSError as error:
            return {"ok": False, "error": f"Không ghi được cấu hình model: {error}"}

        return {
            "ok": True,
            **record,
            "launcher_error": launcher_error,
            "note_usage": (
                "Mở launcher này để M Auto Pilot dùng model đã liberate. "
                "Biến M_AUTO_PILOT_MODEL_PATH được server_manager đọc khi khởi động llama-server."
            ),
        }

    def _convert_script(self) -> Path | None:
        for candidate in (
            self.llama_cpp_dir / "convert_hf_to_gguf.py",
            APP_ROOT / "tools" / "convert_hf_to_gguf.py",
            APP_ROOT / "work" / "auto_pilot" / "tools" / "convert_hf_to_gguf.py",
        ):
            if candidate.is_file():
                return candidate
        return None

    def _resolve_output_dir(self, value: str, model: str) -> Path | str:
        raw = str(value or "").strip()
        if raw:
            candidate = Path(raw).expanduser()
            if not candidate.is_absolute():
                candidate = self.root / candidate
        else:
            candidate = self.root / "liberated" / _slug(model)
        try:
            resolved = candidate.resolve()
        except OSError as error:
            return str(error)
        allowed = (self.root.resolve(), (APP_ROOT / "work").resolve())
        if not any(resolved.is_relative_to(root) for root in allowed):
            return (
                "Thư mục đầu ra phải nằm trong thư mục cài OBLITERATUS "
                "hoặc work/ của M Auto Pilot."
            )
        return resolved


def _slug(value: str) -> str:
    text = str(value or "").strip().replace("/", "-").replace("\\", "-")
    cleaned = "".join(ch for ch in text if ch.isalnum() or ch in "-_.")
    return cleaned.strip("-_.") or "model"


def _file_size_gb(path: str) -> float | None:
    try:
        return round(Path(path).stat().st_size / 1024**3, 2)
    except OSError:
        return None


def _hf_gguf_files(repo_id: str) -> list[dict[str, Any]]:
    """Liệt kê file .gguf của một repo HuggingFace (kèm dung lượng)."""

    import requests

    response = requests.get(
        f"https://huggingface.co/api/models/{repo_id}",
        params={"files_metadata": "true"},
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()
    files: list[dict[str, Any]] = []
    for sibling in payload.get("siblings") or []:
        name = str(sibling.get("rfilename") or "")
        if not name.lower().endswith(".gguf"):
            continue
        size = sibling.get("size")
        files.append({
            "filename": name,
            "size_bytes": int(size) if size else None,
            "size_gb": round(int(size) / 1024**3, 2) if size else None,
        })
    return files


def _remote_size(repo_id: str, filename: str) -> int | None:
    """Lấy dung lượng file qua HEAD (dùng khi API không trả size, ví dụ repo Xet)."""

    import requests

    try:
        response = requests.head(
            f"https://huggingface.co/{repo_id}/resolve/main/{filename}",
            allow_redirects=True,
            timeout=30,
        )
        length = response.headers.get("x-linked-size") or response.headers.get("Content-Length")
        return int(length) if length else None
    except (requests.RequestException, ValueError, TypeError):
        return None


if __name__ == "__main__":  # pragma: no cover - chẩn đoán nhanh
    target = ObliteratusTarget.from_environment()
    print(json.dumps(target.status(), ensure_ascii=False, indent=2))
    print(json.dumps(target.probe_python(), ensure_ascii=False, indent=2))
