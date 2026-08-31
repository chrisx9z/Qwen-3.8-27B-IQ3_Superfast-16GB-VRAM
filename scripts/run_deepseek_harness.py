from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from llm.resource_manager import GPUResourceManager
from llm.server_manager import AGENT_SERVER_PORT, LocalLLMServerManager

from core.console import configure_utf8_stdio


HARNESS_CONFIG_ROOT = PROJECT_ROOT / "config" / "deepseek_harness"
HARNESS_HOME = PROJECT_ROOT / "work" / "auto_pilot" / "deepseek_harness"
HARNESS_SETTINGS = HARNESS_CONFIG_ROOT / "settings.yaml"
HARNESS_PATCH = HARNESS_CONFIG_ROOT / "mcp_m_auto_pilot.cordis.yml"
MCP_SERVER = PROJECT_ROOT / "scripts" / "run_mcp_server.py"
HARNESS_PACKAGE = "@deepseek-ai/dsh@0.1.0-rc.8"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Khởi động DeepSeek Harness với M Auto Pilot và Qwen local."
    )
    parser.add_argument(
        "--profile",
        choices=("iq3s", "q4", "q6"),
        default="iq3s",
        help="IQ3_S mặc định; Q4 cân bằng; Q6 dùng cho request phức tạp.",
    )
    parser.add_argument(
        "--no-server",
        action="store_true",
        help="Chỉ kết nối server Qwen đang chạy.",
    )
    parser.add_argument(
        "--no-open",
        action="store_true",
        help="Không tự mở trình duyệt.",
    )
    parser.add_argument(
        "--dump-config",
        action="store_true",
        help="In cấu hình Harness rồi thoát.",
    )
    return parser


def _prepare_home() -> Path:
    HARNESS_HOME.mkdir(parents=True, exist_ok=True)
    target = HARNESS_HOME / "settings.yaml"
    if not target.exists():
        shutil.copyfile(HARNESS_SETTINGS, target)
    return HARNESS_HOME


def _ensure_qwen(profile: str, no_server: bool) -> None:
    if no_server:
        return

    manager = LocalLLMServerManager(
        context_size=16384,
        profile=f"qwen38_{profile}",
        reasoning="auto" if profile == "q6" else "off",
        host="127.0.0.1",
        port=AGENT_SERVER_PORT,
        replace_existing=False,
    )
    was_ready = manager.is_ready()
    if not was_ready:
        GPUResourceManager().claim_agent(
            profile=f"qwen38_{profile}",
            port=AGENT_SERVER_PORT,
            model_path=str(manager.model_path),
        )
    manager.ensure_running()


def _run_harness(home: Path, no_open: bool, dump_config: bool) -> int:
    pnpm_candidates = [
        shutil.which("pnpm.cmd"),
        shutil.which("pnpm"),
    ]
    pnpm_home = os.environ.get("PNPM_HOME", "").strip()
    if pnpm_home:
        pnpm_candidates.append(str(Path(pnpm_home) / "pnpm.cmd"))
    pnpm_candidates.extend([
        str(Path.home() / "AppData" / "Local" / "pnpm" / "pnpm.cmd"),
        str(Path.home() / ".cache" / "codex-runtimes" / "codex-primary-runtime" / "dependencies" / "bin" / "fallback" / "pnpm.cmd"),
    ])
    pnpm = next((candidate for candidate in pnpm_candidates if candidate and Path(candidate).is_file()), None)
    npx = shutil.which("npx.cmd") or shutil.which("npx")
    if not pnpm and not npx:
        raise RuntimeError(
            "Không tìm thấy Node.js/pnpm/npx. Hãy cài Node.js 22 LTS trở lên."
        )

    environment = os.environ.copy()
    environment.update({
        "DSH_HOME": str(home),
        "M_AUTO_PILOT_ROOT": str(PROJECT_ROOT),
        "M_AUTO_PILOT_PYTHON": sys.executable,
        "M_AUTO_PILOT_MCP_SERVER": str(MCP_SERVER),
        "M_AUTO_PILOT_LOCAL_API_KEY": "local-only",
        "DSH_PERMISSION_MODE": os.environ.get(
            "DSH_PERMISSION_MODE",
            "danger-full-access",
        ),
    })

    if pnpm:
        command = [pnpm, "dlx", HARNESS_PACKAGE, "--profile", "web"]
    else:
        command = [npx, "--yes", HARNESS_PACKAGE, "--profile", "web"]
    command.extend(["--patch", str(HARNESS_PATCH)])
    if dump_config:
        command.append("--dump-config")
    if no_open and not dump_config:
        command.append("--no-open")
    return subprocess.run(
        command,
        cwd=str(PROJECT_ROOT),
        env=environment,
        check=False,
    ).returncode


def main() -> int:
    configure_utf8_stdio()
    args = _parser().parse_args()
    if not HARNESS_SETTINGS.exists() or not HARNESS_PATCH.exists():
        raise RuntimeError("Thiếu cấu hình DeepSeek Harness trong config/deepseek_harness.")
    if not MCP_SERVER.exists():
        raise RuntimeError("Không tìm thấy M Auto Pilot MCP server.")

    _ensure_qwen(args.profile, args.no_server)
    home = _prepare_home()
    return _run_harness(home, args.no_open, args.dump_config)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(130)
    except Exception as error:
        print(f"DeepSeek Harness không khởi động được: {error}", file=sys.stderr)
        raise SystemExit(1)
