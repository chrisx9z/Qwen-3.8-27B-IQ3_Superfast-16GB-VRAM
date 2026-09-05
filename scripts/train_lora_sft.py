#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Automated QLoRA / SFT Training Pipeline for M-Auto-Pilot (Qwen 3.8 / Qwen 2.5)
Engineered for NVIDIA GeForce RTX 5070 Ti (16GB VRAM) on Windows.

Features:
- 4-bit NormalFloat (NF4) quantization + Double Quantization for ultra-low VRAM.
- Paged AdamW 8-bit optimizer and gradient checkpointing.
- Auto-pauses and resumes local llama-server.exe to liberate 12GB+ VRAM.
- Full compatibility with work/sft_dataset/sharegpt_sft.jsonl (5,000 pairs).
- Exports LoRA adapter checkpoints directly to work/lora_checkpoints/.
"""

import argparse
import gc
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def check_and_pause_llama_server() -> Optional[int]:
    """Tìm và tạm dừng tiến trình llama-server để giải phóng VRAM."""
    import psutil

    for proc in psutil.process_iter(["pid", "name"]):
        try:
            if "llama-server" in proc.info["name"].lower():
                pid = proc.info["pid"]
                print(f"[!] Phát hiện llama-server đang chạy (PID: {pid}). Tạm dừng để giải phóng 16GB VRAM...")
                proc.suspend()
                return pid
        except Exception:
            pass
    return None


def resume_llama_server(pid: Optional[int]) -> None:
    """Tiếp tục tiến trình llama-server sau khi huấn luyện xong."""
    if pid is None:
        return
    import psutil

    try:
        proc = psutil.Process(pid)
        print(f"[*] Khôi phục hoạt động cho llama-server (PID: {pid})...")
        proc.resume()
    except Exception as err:
        print(f"[-] Không thể khôi phục llama-server (PID: {pid}): {err}")


def load_sharegpt_dataset(file_path: Path, max_samples: Optional[int] = None) -> List[Dict[str, Any]]:
    """Đọc dữ liệu ShareGPT JSONL thành định dạng chuẩn hội thoại."""
    examples = []
    if not file_path.exists():
        raise FileNotFoundError(f"Không tìm thấy file dataset: {file_path}")

    with open(file_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            item = json.loads(line)
            examples.append(item)
            if max_samples and len(examples) >= max_samples:
                break
    return examples


def format_chat_prompt(messages: List[Dict[str, str]]) -> str:
    """Định dạng hội thoại theo ChatML template của Qwen."""
    formatted = ""
    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        formatted += f"<|im_start|>{role}\n{content}<|im_end|>\n"
    return formatted


def run_dry_run_validation(dataset_path: Path, model_id: str) -> None:
    """Kiểm tra tính hợp lệ của dataset, cấu trúc hội thoại và VRAM mà không tải model nặng."""
    import torch

    print("\n" + "=" * 65)
    print("🔍 [DRY-RUN] BẮT ĐẦU KIỂM TRA ĐIỀU KIỆN HUẤN LUYỆN")
    print("=" * 65)

    # 1. Kiểm tra GPU
    print(f"1. Kiểm tra phần cứng:")
    print(f"   - PyTorch version: {torch.__version__}")
    print(f"   - CUDA sẵn sàng:   {torch.cuda.is_available()}")
    if torch.cuda.is_available():
        gpu_name = torch.cuda.get_device_name(0)
        total_vram_gb = torch.cuda.get_device_properties(0).total_memory / (1024**3)
        allocated_vram_gb = torch.cuda.memory_allocated(0) / (1024**3)
        reserved_vram_gb = torch.cuda.memory_reserved(0) / (1024**3)
        print(f"   - Tên GPU:         {gpu_name}")
        print(f"   - Tổng VRAM:       {total_vram_gb:.2f} GB")
        print(f"   - VRAM đang dùng:  {allocated_vram_gb:.2f} GB (Đã cấp phát: {reserved_vram_gb:.2f} GB)")
    else:
        print("   [!] Cảnh báo: Không tìm thấy GPU CUDA!")

    # 2. Kiểm tra Dataset
    print(f"\n2. Kiểm tra bộ dữ liệu SFT:")
    data = load_sharegpt_dataset(dataset_path, max_samples=100)
    print(f"   - File: {dataset_path}")
    print(f"   - Số mẫu kiểm tra: {len(data)}")
    first = data[0]
    msgs = first.get("messages", [])
    print(f"   - Mẫu đầu tiên có {len(msgs)} lượt hội thoại (roles: {[m.get('role') for m in msgs]})")
    formatted_sample = format_chat_prompt(msgs)
    print(f"   - ChatML Tokens ước tính mẫu đầu: ~{len(formatted_sample) // 4} tokens")
    print(f"   - Preview 150 ký tự ChatML format:\n     {repr(formatted_sample[:150])}")

    # 3. Kiểm tra các thư viện huấn luyện
    print(f"\n3. Kiểm tra các module Training Stack:")
    import transformers
    import peft
    import trl
    import bitsandbytes
    print(f"   - transformers:   v{transformers.__version__} [✓]")
    print(f"   - peft:           v{peft.__version__} [✓]")
    print(f"   - trl:            v{trl.__version__} [✓]")
    print(f"   - bitsandbytes:   v{bitsandbytes.__version__} [✓]")

    print("\n" + "=" * 65)
    print("✅ [DRY-RUN THÀNH CÔNG] Tất cả các điều kiện kỹ thuật đã sẵn sàng để huấn luyện!")
    print("=" * 65 + "\n")


def train_lora_sft(
    dataset_path: Path,
    model_id: str,
    output_dir: Path,
    epochs: int = 1,
    batch_size: int = 1,
    grad_accum: int = 8,
    learning_rate: float = 2e-4,
    max_seq_length: int = 2048,
    lora_r: int = 16,
    lora_alpha: int = 32,
    lora_dropout: float = 0.05,
    max_samples: Optional[int] = None,
    auto_pause_server: bool = True,
) -> None:
    """Thực thi pipeline huấn luyện QLoRA SFT."""
    import torch
    from datasets import Dataset
    from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
    from transformers import (
        AutoModelForCausalLM,
        AutoTokenizer,
        BitsAndBytesConfig,
        TrainingArguments,
    )
    from trl import SFTTrainer

    output_dir.mkdir(parents=True, exist_ok=True)
    server_pid: Optional[int] = None

    if auto_pause_server:
        server_pid = check_and_pause_llama_server()
        time.sleep(1.0)
        torch.cuda.empty_cache()
        gc.collect()

    try:
        print("\n[*] Đang đọc bộ dữ liệu 5.000 mẫu SFT...")
        raw_examples = load_sharegpt_dataset(dataset_path, max_samples=max_samples)
        print(f"[✓] Đã nạp thành công {len(raw_examples)} mẫu dữ liệu.")

        formatted_texts = [format_chat_prompt(ex["messages"]) for ex in raw_examples]
        train_dataset = Dataset.from_dict({"text": formatted_texts})

        print(f"[*] Đang tải Tokenizer cho mô hình: {model_id}...")
        tokenizer = AutoTokenizer.from_pretrained(
            model_id,
            trust_remote_code=True,
            padding_side="right",
        )
        if tokenizer.pad_token is None:
            tokenizer.pad_token = tokenizer.eos_token

        print(f"[*] Cấu hình 4-bit NF4 Quantization (BitsAndBytes) để tiết kiệm VRAM...")
        bnb_config = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_compute_dtype=torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16,
            bnb_4bit_use_double_quant=True,
        )

        print(f"[*] Đang tải mô hình base: {model_id}...")
        model = AutoModelForCausalLM.from_pretrained(
            model_id,
            quantization_config=bnb_config,
            device_map="auto",
            trust_remote_code=True,
        )

        model = prepare_model_for_kbit_training(model)

        print(f"[*] Khởi tạo LoRA Adapter (r={lora_r}, alpha={lora_alpha})...")
        peft_config = LoraConfig(
            r=lora_r,
            lora_alpha=lora_alpha,
            lora_dropout=lora_dropout,
            bias="none",
            task_type="CAUSAL_LM",
            target_modules=[
                "q_proj",
                "k_proj",
                "v_proj",
                "o_proj",
                "gate_proj",
                "up_proj",
                "down_proj",
            ],
        )
        model = get_peft_model(model, peft_config)
        model.print_trainable_parameters()

        training_args = TrainingArguments(
            output_dir=str(output_dir),
            num_train_epochs=epochs,
            per_device_train_batch_size=batch_size,
            gradient_accumulation_steps=grad_accum,
            optim="paged_adamw_8bit",
            save_steps=200,
            logging_steps=10,
            learning_rate=learning_rate,
            weight_decay=0.01,
            fp16=not torch.cuda.is_bf16_supported(),
            bf16=torch.cuda.is_bf16_supported(),
            max_grad_norm=0.3,
            warmup_ratio=0.03,
            lr_scheduler_type="cosine",
            report_to="none",
        )

        trainer = SFTTrainer(
            model=model,
            train_dataset=train_dataset,
            peft_config=peft_config,
            dataset_text_field="text",
            max_seq_length=max_seq_length,
            tokenizer=tokenizer,
            args=training_args,
        )

        print("\n🚀 BẮT ĐẦU QUÁ TRÌNH HUẤN LUYỆN SFT TRÊN GPU...")
        start_time = time.time()
        trainer.train()
        elapsed = time.time() - start_time
        print(f"\n[✓] Huấn luyện hoàn tất sau {elapsed / 60:.2f} phút!")

        final_adapter_dir = output_dir / "final_adapter"
        print(f"[*] Lưu adapter hoàn chỉnh tại: {final_adapter_dir}...")
        trainer.model.save_pretrained(str(final_adapter_dir))
        tokenizer.save_pretrained(str(final_adapter_dir))
        print("[✓] Đã lưu thành công LoRA Adapter!")

    finally:
        if auto_pause_server and server_pid is not None:
            resume_llama_server(server_pid)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Huấn luyện QLoRA SFT cho M-Auto-Pilot từ bộ dữ liệu chuẩn mẫu Gemini 3.8 Flash."
    )
    parser.add_argument(
        "--dataset",
        type=str,
        default="work/sft_dataset/sharegpt_sft.jsonl",
        help="Đường dẫn file dataset ShareGPT JSONL.",
    )
    parser.add_argument(
        "--model-id",
        type=str,
        default="Qwen/Qwen2.5-7B-Instruct",
        help="HuggingFace model ID hoặc đường dẫn weights gốc để train LoRA.",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="work/lora_checkpoints",
        help="Thư mục lưu adapter checkpoints.",
    )
    parser.add_argument(
        "--epochs",
        type=int,
        default=1,
        help="Số lượt huấn luyện (epochs).",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=1,
        help="Kích thước batch trên GPU (Mặc định 1 cho an toàn VRAM 16GB).",
    )
    parser.add_argument(
        "--grad-accum",
        type=int,
        default=8,
        help="Số bước tích lũy gradient (Gradient accumulation steps).",
    )
    parser.add_argument(
        "--lr",
        type=float,
        default=2e-4,
        help="Tốc độ học (Learning rate).",
    )
    parser.add_argument(
        "--max-samples",
        type=int,
        default=None,
        help="Giới hạn số mẫu nếu muốn train thử nghiệm nhanh.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Chạy kiểm tra tính hợp lệ của dataset, GPU và pipeline mà không tải weights.",
    )
    parser.add_argument(
        "--no-pause-server",
        action="store_true",
        help="Không tự động tạm dừng llama-server.exe.",
    )

    args = parser.parse_args()
    project_root = Path(__file__).resolve().parents[1]
    dataset_path = project_root / args.dataset
    output_dir = project_root / args.output_dir

    if args.dry_run:
        run_dry_run_validation(dataset_path=dataset_path, model_id=args.model_id)
        return 0

    train_lora_sft(
        dataset_path=dataset_path,
        model_id=args.model_id,
        output_dir=output_dir,
        epochs=args.epochs,
        batch_size=args.batch_size,
        grad_accum=args.grad_accum,
        learning_rate=args.lr,
        max_samples=args.max_samples,
        auto_pause_server=not args.no_pause_server,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
