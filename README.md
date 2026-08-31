# M Auto Pilot

M Auto Pilot là trợ lý cá nhân chạy hoàn toàn cục bộ trên máy tính: trò chuyện, lập trình (coding agent), nghiên cứu web, điều khiển Windows/trình duyệt và điều khiển AI Video Localizer — dùng model **Qwen3.8-27B** qua llama.cpp (OpenAI-compatible).

## Phần mềm tách biệt

M Auto Pilot và AI Video Localizer là hai ứng dụng riêng:

- M Auto Pilot sở hữu controller, UI, tools, chats, runtime và build output.
- AI Video Localizer là ứng dụng ngoài được M Auto Pilot điều khiển qua adapter.
- M Auto Pilot không import code của AI Video Localizer và không sửa source của nó.
- Model GGUF và llama-server được đọc chung từ `D:\AI-Video-Localizer\models` và `D:\AI-Video-Localizer\tools\llama.cpp` (có thể ghi đè bằng `M_AUTO_PILOT_MODELS_DIR` / `M_AUTO_PILOT_LLAMA_SERVER`).

## Vị trí

| Thành phần | Đường dẫn |
|---|---|
| Source (repo Git) | `D:\Vibe Code\M-Auto-Pilot` |
| Runtime state (EXE dùng) | `D:\M-Auto-Pilot` (work/, logs/, chats) |
| Model GGUF (dùng chung) | `D:\AI-Video-Localizer\models` |
| llama.cpp | `D:\AI-Video-Localizer\tools\llama.cpp\llama-server.exe` |
| EXE build | `D:\Vibe Code\M-Auto-Pilot\dist\M Auto Pilot.exe` |
| EXE trên Desktop | `D:\OneDrive\Desktop\M Auto Pilot.exe` |
| Target workspace | `D:\AI-Video-Localizer` |

## Model

M Auto Pilot chỉ chạy **một model duy nhất: Qwen3.8-27B-UD-IQ3_S** (`Qwen3.8-27B-UD-IQ3_S.gguf`, bản lượng hóa nhẹ, hợp GPU 12–16 GB). Không còn Q4/Q6/14B — mọi profile cũ đều quy về model này.

Agent chạy trên cổng 8090, tách biệt với pipeline dịch 8080 của AI Video Localizer. Bấm **GPU status** để xem VRAM trước khi dùng.

## Cách chạy

Từ source:

```powershell
Set-Location D:\Vibe Code\M-Auto-Pilot
& D:\AI-Video-Localizer\.venv\Scripts\python.exe scripts\run_auto_pilot_gui.py
```

Từ EXE: mở `M Auto Pilot.exe` trên Desktop (runtime state tại `D:\M-Auto-Pilot`).

CLI agent:

```powershell
& D:\AI-Video-Localizer\.venv\Scripts\python.exe scripts\run_local_agent.py "Liệt kê project"
# hoặc hội thoại: gõ 'exit' để thoát
```

## Giao diện

- Chat dạng bong bóng, render markdown, streaming câu trả lời từng chữ.
- Chế độ: **Trợ lý cá nhân**, **Coding Agent**, **Auto Pilot**.
- Lịch sử chat (ghim / đổi tên / xóa), lưu tại `work\auto_pilot\chats.json`.
- Nút **GPU status** và **DeepSeek Harness** (Web UI tại `http://127.0.0.1:3080`).

## Khả năng

1. Nghiên cứu web: tìm kiếm, mở nguồn, trích xuất nội dung.
2. Browser automation: mở, snapshot, click, type, extract, screenshot, đóng.
3. Windows UI Automation: danh sách cửa sổ, cây control, click/type/phím.
4. Coding: đọc/tìm/sửa file, git status/diff, compile/test, checkpoint/rollback.
5. Tải video: Bilibili/YouTube/Douyin; điều khiển AI Video Localizer qua adapter.
6. Screen capture + OCR (RapidOCR, chạy CPU).
7. Quản lý tiến trình, log runtime, resource GPU.
8. MCP server/client (42+ tool nội bộ, nạp MCP ngoài tùy chọn).

## Build EXE

```powershell
Set-Location D:\Vibe Code\M-Auto-Pilot
& D:\AI-Video-Localizer\.venv\Scripts\python.exe -m PyInstaller "M Auto Pilot.spec" --noconfirm
Copy-Item "dist\M Auto Pilot.exe" "D:\OneDrive\Desktop\M Auto Pilot.exe" -Force
```

## Kiểm thử

```powershell
& D:\AI-Video-Localizer\.venv\Scripts\python.exe scripts\test_local_agent.py
```
