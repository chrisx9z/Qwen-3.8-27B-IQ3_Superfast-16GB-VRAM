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

Mặc định là **Qwen3.8-27B-UD-IQ3_S** (bản lượng hóa nhẹ, chạy gọn trên GPU 12 GB), chọn được trong giao diện:

| Profile | Model | Dùng khi |
|---|---|---|
| IQ3_S · mặc định | `Qwen3.8-27B-UD-IQ3_S.gguf` | Hội thoại, coding, tool calling hằng ngày |
| Q4 · cân bằng | `Qwen3.8-27B-UD-Q4_K_M.gguf` | Yêu cầu chất lượng cao hơn |
| Q6 · suy luận sâu | `Qwen3.8-27B-UD-Q6_K_M.gguf` | Lập kế hoạch phức tạp, phân tích sâu |
| Qwen3 14B · nhanh | `Qwen3-14B-Q4_K_M.gguf` | Câu hỏi ngắn, cần phản hồi nhanh |

Agent chạy trên cổng 8090, tách biệt với pipeline dịch 8080 của AI Video Localizer. Với GPU 12 GB không nên chạy Q4/Q6 cùng lúc với pipeline; bấm **GPU status** để xem VRAM trước khi chọn model nặng.

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
# hoặc hội thoại: /iq3s, /q4, /q6 ở đầu request
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
