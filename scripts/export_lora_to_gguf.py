#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Export LoRA Adapter Checkpoint to GGUF format for llama.cpp / M-Auto-Pilot.
Wraps convert_lora_to_gguf.py and ensures full tensor compatibility.
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def export_adapter_to_gguf(
    adapter_dir: Path,
    output_gguf_path: Path,
    base_model_path: str = "Qwen/Qwen2.5-7B-Instruct",
) -> int:
    """Chuyển đổi LoRA Adapter PyTorch sang GGUF."""
    converter_script = Path("D:/AI-Video-Localizer/cache/ik_llama.cpp/convert_lora_to_gguf.py")
    if not converter_script.exists():
        raise FileNotFoundError(f"Không tìm thấy script chuyển đổi: {converter_script}")

    if not adapter_dir.exists():
        raise FileNotFoundError(f"Không tìm thấy thư mục LoRA adapter: {adapter_dir}")

    output_gguf_path.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        sys.executable,
        str(converter_script),
        str(adapter_dir),
        "--outfile",
        str(output_gguf_path),
        "--base",
        base_model_path,
    ]

    print(f"[*] Đang thực thi chuyển đổi LoRA sang GGUF:")
    print(f"    {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode == 0:
        print(f"[✓] Chuyển đổi thành công: {output_gguf_path}")
        print(f"    Dung lượng file GGUF: {output_gguf_path.stat().st_size / (1024*1024):.2f} MB")
        return 0
    else:
        print(f"[-] Lỗi chuyển đổi (code {result.returncode}):")
        print(result.stderr)
        return result.returncode


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Xuất LoRA Adapter sang định dạng GGUF cho M-Auto-Pilot."
    )
    parser.add_argument(
        "--adapter-dir",
        type=str,
        default="work/lora_checkpoints/final_adapter",
        help="Thư mục chứa weights adapter sau khi train.",
    )
    parser.add_argument(
        "--output-file",
        type=str,
        default="work/lora_checkpoints/lora_adapter.gguf",
        help="Đường dẫn file .gguf đầu ra.",
    )
    parser.add_argument(
        "--base-model",
        type=str,
        default="Qwen/Qwen2.5-7B-Instruct",
        help="Tên base model trên HuggingFace hoặc đường dẫn thư mục base weights.",
    )

    args = parser.parse_args()
    project_root = Path(__file__).resolve().parents[1]
    adapter_dir = project_root / args.adapter_dir
    output_path = project_root / args.output_file

    return export_adapter_to_gguf(
        adapter_dir=adapter_dir,
        output_gguf_path=output_path,
        base_model_path=args.base_model,
    )


if __name__ == "__main__":
    sys.exit(main())
