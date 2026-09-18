# OBLITERATUS — tích hợp vào M Auto Pilot (abliteration / bỏ kiểm duyệt model)

Repo gốc: <https://github.com/elder-plinius/OBLITERATUS> (AGPL-3.0, Python, v0.1.3)
Mục tiêu: đưa khả năng **abliteration** (loại bỏ "hướng từ chối" trong trọng số model)
thành **tính năng bên trong M Auto Pilot** — không phải một app riêng phải mở thủ công.

---

## 1. Đã cài gì, ở đâu

| Thành phần | Đường dẫn |
|---|---|
| Source OBLITERATUS | `work\auto_pilot\external\OBLITERATUS` |
| Venv riêng (Python 3.12.10) | `...\OBLITERATUS\.venv` |
| CLI | `...\.venv\Scripts\obliteratus.exe` |
| Web UI (tùy chọn) | `http://127.0.0.1:7860` |
| Log pipeline/UI/tải model | `work\auto_pilot\obliteratus_logs\` |
| Converter GGUF (llama.cpp) | `work\auto_pilot\tools\convert_hf_to_gguf.py` + `tools\conversion\` |
| Tiến trình tải GGUF | `work\auto_pilot\gguf_download.json` |
| Model đang được chọn | `work\auto_pilot\active_model.json` |

Đã cài: `torch 2.14.0+cu132` (CUDA 13.2, RTX 5070 Ti 15.92 GB), `transformers 5.17`,
`gradio 6.27`, `bitsandbytes 0.50.2`, `optuna`, `datasets`, `accelerate`, `gguf`, `sentencepiece`.

---

## 2. QUAN TRỌNG: model của bạn là GGUF (IQ3_S) — không abliterate trực tiếp được

Model đang chạy của M Auto Pilot là **`Qwen3.8-27B-UD-IQ3_S.gguf`** (GGUF, ~11 GB, llama.cpp).
Abliteration thao tác trên **trọng số HuggingFace (safetensors)** — không sửa được file GGUF
tại chỗ. Vì vậy có 3 đường đi:

### Đường A — Dùng bản 27B đã abliterate sẵn (khuyên dùng cho máy này) ✅
Đã tải sẵn về máy:
`D:\AI-Video-Localizer\models\Huihui-Qwen3.8-27B-abliterated-UD-IQ3_S.gguf` (~11.1 GB)
— cùng chuẩn quant **UD-IQ3_S** với model hiện tại, cùng base Qwen3.8-27B
(repo: `huihui-ai/Huihui-Qwen3.8-27B-abliterated-GGUF`).

Các lựa chọn khác cùng cỡ:
- `OBLITERATUS/Qwen3.8-27B-OBLITERATED` — bản chính thức do OBLITERATUS phát hành (IQ4_XS / Q3_K_M / Q4_K_M)
- `0bserverx/Qwen3.8-27B-Heretic-Abliterated-Uncensored-GGUF` — có `RVN-IQ3_S.gguf` và bản multilingual
- `orcarouter/Qwen3.8-27B-Uncensored-GGUF`, `RentedNoodle/...-IQ3_XXS-Uncensored`

### Đường B — Tự abliterate tại chỗ (chỉ với model ≤ 4B trên máy này)
Đo bằng `obliteratus gpu-calc` trên 1 GPU 16 GB:

| Model | VRAM cần | Kết luận |
|---|---|---|
| Qwen3.8-27B | 58.5 GB | ❌ cần **5 GPU** 16 GB |
| Qwen3-14B | 35.4 GB | ❌ cần 3 GPU |
| Qwen3-8B | 19.7 GB | ❌ cần 2 GPU (thử `--quantization 4bit` để hạ) |
| **Qwen3-4B** | **10.6 GB** | ✅ **chạy được trên 1 GPU 16 GB** |

Sau khi liberate xong (thư mục HF), dùng `obliteratus_export_gguf` để convert sang GGUF
+ quantize (ví dụ `IQ3_S`) rồi `obliteratus_activate_model`.

### Đường C — 27B bản gốc (nếu muốn tự tay làm)
Cần ≥ 5×16 GB VRAM (hoặc thuê GPU/Colab/HF Spaces ZeroGPU của repo), sau đó tải kết quả về,
convert GGUF và quantize như đường B. Không khả thi trên RTX 5070 Ti đơn lẻ.

---

## 3. 12 tool đã đăng ký trong M Auto Pilot

Adapter: `adapters/obliteratus.py` · Đăng ký: `agent/tools.py` · Định tuyến: `agent/controller.py`

| Tool | Việc |
|---|---|
| `obliteratus_status` | Trạng thái cài đặt (venv, CLI, UI, cổng 7860) |
| `obliteratus_fit_check` | Ước lượng VRAM + kết luận model có chạy được trên máy này |
| `obliteratus_liberate` | **Pipeline đầy đủ**: tải model → probe → trích hướng từ chối → loại bỏ → lưu |
| `obliteratus_progress` | Đọc log tiến trình của run đang chạy |
| `obliteratus_export_gguf` | Convert model đã liberate (HF) → GGUF, tùy chọn quantize |
| `obliteratus_list_gguf` | Liệt kê file GGUF của một repo HuggingFace |
| `obliteratus_install_gguf` | Tải GGUF đã abliterate về (có resume, ghi % tiến trình) |
| `obliteratus_download_progress` | Xem % tải + model đang chọn |
| `obliteratus_activate_model` | Chuyển M Auto Pilot sang GGUF đã chọn (ghi config + tạo launcher) |
| `obliteratus_run` | Chạy CLI allowlist (obliterate/models/presets/info/gpu-calc/report…) |
| `obliteratus_launch_ui` | Mở Gradio UI (tùy chọn, không bắt buộc) |
| `obliteratus_stop` | Dừng tiến trình OBLITERATUS |

Từ khóa kích hoạt nhóm tool này: `obliteratus`, `abliterate`, `abliteration`,
`obliterate`, `refusal`, `guardrail`, `uncensored`, `không kiểm duyệt`,
`giải phóng model`, `liberate`, `pliny`, `xóa từ chối`.

---

## 4. Cách dùng trong khung chat M Auto Pilot

```
"Model Qwen3.8-27B của tôi có abliterate được trên máy này không?"
   → obliteratus_fit_check

"Tải bản Qwen3.8-27B đã abliterate bản IQ3_S về máy"
   → obliteratus_install_gguf(repo_id="huihui-ai/Huihui-Qwen3.8-27B-abliterated-GGUF",
                              filename="Huihui-Qwen3.8-27B-abliterated-UD-IQ3_S.gguf")

"Đang tải bao nhiêu % rồi?"
   → obliteratus_download_progress

"Chuyển M Auto Pilot sang model vừa tải"
   → obliteratus_activate_model(gguf_path="D:\\AI-Video-Localizer\\models\\Huihui-...IQ3_S.gguf")

"Abliterate Qwen3-4B bằng method advanced rồi đóng gói GGUF IQ3_S"
   → obliteratus_liberate(model="Qwen/Qwen3-4B", method="advanced")
   → obliteratus_progress → obliteratus_export_gguf(model_dir=..., quant="IQ3_S")
```

Bằng tay:

```powershell
$ob = "D:\Vibe Code\M-Auto-Pilot\work\auto_pilot\external\OBLITERATUS"
& "$ob\.venv\Scripts\obliteratus.exe" gpu-calc Qwen/Qwen3-4B --gpu-mem 16
& "$ob\.venv\Scripts\obliteratus.exe" obliterate Qwen/Qwen3-4B --method advanced --output-dir liberated/qwen3-4b
```

---

## 5. Đã kiểm chứng (2026-09-18)

- Cài đặt + CUDA: `torch 2.14.0+cu132`, `cuda.is_available()=True`, GPU RTX 5070 Ti.
- CLI: `--help`, `models --tier small`, `gpu-calc` chạy đúng.
- **Pipeline abliteration thật chạy qua tool của app**: `obliteratus_liberate` với
  `Qwen/Qwen3-0.6B` (CPU) → tạo `liberated/demo-qwen3-0.6b/model.safetensors` (1.14 GB)
  + `abliteration_metadata.json`.
- 12 tool hiển thị trong registry (tổng 318 tool), `obliteratus_fit_check` trả đúng
  kết luận cho 27B (5 GPU) và 4B (1 GPU).
- Tải GGUF đã abliterate: 11.13 GB, có resume, ghi % vào `gguf_download.json`.
- `scripts/test_local_agent.py` (regression) PASS sau khi thêm tool.

---

## 6. Lưu ý

- Abliteration **không** sửa quy tắc an toàn của chính M Auto Pilot (allowlist tool,
  giới hạn đường dẫn, xác nhận thao tác nguy hiểm) — nó chỉ tác động lên model.
- Model sau khi liberate đã mất cơ chế từ chối gốc; bạn tự chịu trách nhiệm với nội dung
  sinh ra. Nên giữ lại model gốc để đối chiếu/khôi phục.
- Model 27B abliterate có thể giảm nhẹ chất lượng suy luận so với bản gốc (đánh đổi
  thường gặp của abliteration) — nên thử và so sánh trước khi dùng thường xuyên.
- `M_AUTO_PILOT_MODEL_PATH` là biến quyết định model llama-server nạp; launcher do
  `obliteratus_activate_model` tạo sẽ set biến này, không ghi đè model gốc.
