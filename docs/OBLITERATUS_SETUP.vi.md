# OBLITERATUS — Cài đặt & tích hợp M Auto Pilot

Repo: <https://github.com/elder-plinius/OBLITERATUS> (AGPL-3.0, Python, v0.1.3)
Mục đích: toolkit abliteration — tìm và loại bỏ "hướng từ chối" (refusal direction)
trong trọng số model open-weight, không cần train lại.

## 1. Vị trí cài đặt

| Thành phần | Đường dẫn |
|---|---|
| Source (git clone) | `D:\Vibe Code\M-Auto-Pilot\work\auto_pilot\external\OBLITERATUS` |
| Virtualenv riêng | `...\OBLITERATUS\.venv` (Python 3.12.10) |
| CLI | `...\OBLITERATUS\.venv\Scripts\obliteratus.exe` |
| Web UI (Gradio) | `http://127.0.0.1:7860` |
| Log do M Auto Pilot ghi | `work\auto_pilot\obliteratus_logs\` |
| Cache kiểm tra torch/CUDA | `work\auto_pilot\obliteratus_probe.json` |

Repo nằm trong `external/` nên M Auto Pilot coi đây là **ứng dụng ngoài** — không
import code và không sửa source của OBLITERATUS.

## 2. Đã cài gì

- `uv venv --python 3.12` → venv riêng, **không đụng** vào venv của AI Video Localizer.
- `uv pip install -e ".[spaces,quantization]"` → cài ở chế độ editable kèm Gradio UI
  và bitsandbytes (nạp model 8-bit/4-bit).
- Torch mặc định từ PyPI là bản CPU-only, đã cài lại bản CUDA:
  `uv pip install --upgrade torch --index-url https://download.pytorch.org/whl/cu132`
  → `torch 2.14.0+cu132`, CUDA 13.2, nhận GPU **RTX 5070 Ti 15.92 GB**.

| Gói | Phiên bản |
|---|---|
| torch | 2.14.0+cu132 (CUDA available: True) |
| transformers | 5.17.0 |
| gradio | 6.27.0 |
| bitsandbytes | 0.50.2 |
| datasets / accelerate / optuna | 5.0.1 / 1.15.0 / 4.9.0 |
| obliteratus | 0.1.3 |

## 3. Tool mới trong M Auto Pilot

Đăng ký tại `agent/tools.py`, điều khiển qua adapter `adapters/obliteratus.py`:

| Tool | Chức năng |
|---|---|
| `obliteratus_status` | Trạng thái cài đặt: thư mục, venv, CLI, UI đang chạy, cổng 7860 |
| `obliteratus_launch_ui` | Mở Gradio UI (chạy nền, ghi log), tham số `port`, `share` |
| `obliteratus_run` | Chạy CLI trong allowlist, tham số `command`, `args`, `background`, `timeout` |
| `obliteratus_stop` | Dừng tiến trình OBLITERATUS do adapter phát hiện |

Allowlist lệnh CLI: `obliterate`, `abliterate`, `blend`, `self-improve`,
`capability-check`, `restore-multimodal`, `run`, `models`, `presets`, `strategies`,
`info`, `gpu-calc`, `recommend`, `runs`, `report`, `aggregate`, `checkpoint`.
Bị loại trừ: `interactive` (cần TTY), `distributed` (worker ngoài), `tourney`.

`agent/controller.py` có nhóm từ khóa riêng: `obliteratus`, `abliterate`,
`abliteration`, `obliterate`, `guardrail`, `uncensored`, `không kiểm duyệt`,
`giải phóng model`, `liberate`, `pliny`, `xóa từ chối` — khi người dùng nhắc
tới các từ này, 4 tool trên được ưu tiên gửi cho model.

## 4. Cách dùng

Trong khung chat M Auto Pilot, ví dụ:

- "Kiểm tra OBLITERATUS đã cài chưa" → `obliteratus_status`
- "Mở giao diện OBLITERATUS" → `obliteratus_launch_ui` → mở http://127.0.0.1:7860
- "Liệt kê model nhỏ phù hợp" → `obliteratus_run` với `command=models`, `args=["--tier","small"]`
- "Abliterate Qwen/Qwen3-1.7B bằng method advanced, chạy nền" →
  `obliteratus_run` với `command=obliterate`,
  `args=["Qwen/Qwen3-1.7B","--method","advanced","--output-dir","./liberated"]`,
  `background=true`

Bằng tay (không qua app):

```powershell
$ob = "D:\Vibe Code\M-Auto-Pilot\work\auto_pilot\external\OBLITERATUS"
& "$ob\.venv\Scripts\obliteratus.exe" ui                 # Gradio UI
& "$ob\.venv\Scripts\obliteratus.exe" models --tier small
& "$ob\.venv\Scripts\obliteratus.exe" obliterate Qwen/Qwen3-1.7B --method advanced
```

## 5. Lưu ý tài nguyên & an toàn

- Abliteration cần tải trọng số model từ HuggingFace và chiếm VRAM lớn. Trên máy này
  llama-server Qwen3.8-27B (cổng 8090) đang chiếm phần lớn 16 GB VRAM — nên dừng/để
  trống GPU trước khi chạy pipeline lớn, hoặc dùng model nhỏ (tier SMALL) để thử.
- Model sau khi abliterate **đã bị gỡ cơ chế từ chối**; chỉ dùng cho nghiên cứu/
  red-team trên máy cá nhân, tự chịu trách nhiệm với nội dung sinh ra.
- Adapter chỉ chạy các lệnh trong allowlist, không truyền chuỗi qua shell, và giới hạn
  số tham số (≤ 40) — model không thể chạy lệnh hệ thống tùy ý qua tool này.
- `stop` chỉ dừng tiến trình có đường dẫn nằm trong thư mục cài OBLITERATUS.
