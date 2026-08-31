# M Auto Pilot Project State

## Separation rule

M Auto Pilot và AI Video Localizer là hai ứng dụng riêng.

- M Auto Pilot sở hữu repo này, UI, tools, chats, runtime files, models và builds.
- AI Video Localizer là external target application.
- M Auto Pilot chỉ inspect/control target qua adapter và generic automation tools.
- M Auto Pilot không import target modules và không sửa target source tree.
- Model GGUF và llama-server được đọc chung từ `D:\AI-Video-Localizer\models` / `D:\AI-Video-Localizer\tools\llama.cpp`; không copy vào repo.

## Locations

- Source (repo Git): `D:\Vibe Code\M-Auto-Pilot`
- Runtime state (EXE): `D:\M-Auto-Pilot`
- Build output: `D:\Vibe Code\M-Auto-Pilot\dist\M Auto Pilot.exe`
- Desktop executable: `D:\OneDrive\Desktop\M Auto Pilot.exe`
- External target workspace: `D:\AI-Video-Localizer`
- External target executable: `D:\OneDrive\Desktop\AI Video Localizer.exe`

## Implemented

- Generic web research with search fallback and source extraction.
- Browser automation (Playwright) và Windows UI Automation (pywinauto).
- Controlled `.exe` launch trong approved directories.
- AI Video Localizer adapter (status + launch).
- Coding tools: read/search/edit, git status/diff, compile/test, checkpoint/rollback.
- Screen capture + OCR (RapidOCR CPU), process/log tools, GPU resource manager.
- MCP server (stdio, 48 tool) + MCP client tùy chọn.
- DeepSeek Harness sidecar launcher (Web UI 3080, kết nối Qwen local 8090 + MCP).
- Chat UI kiểu trợ lý: bong bóng, markdown, streaming từng token, 3 chế độ (Trợ lý cá nhân / Coding Agent / Auto Pilot), lịch sử chat ghim/đổi tên/xóa.
- Model duy nhất: **Qwen3.8-27B-UD-IQ3_S** — đã bỏ Q4/Q6/Qwen3-14B khỏi phần mềm; mọi profile cũ quy về IQ3_S. Đã xóa file `Qwen3.8-27B-UD-Q4_K_M.gguf` và `Qwen3.8-27B-UD-Q6_K_M.gguf` khỏi ổ D (~36.8 GB). Agent cổng 8090, tách pipeline 8080.

## Verification (2026-09-01)

- compileall toàn bộ source: PASS.
- `scripts/test_local_agent.py` (tool loop 48 tool + profile): PASS — profile cũ (q6/q4) quy về `qwen38_iq3s`.
- UI smoke test (offscreen): PASS — 3 chế độ, không còn bộ chọn model, chats.json nạp được.
- Model resolution: chỉ `Qwen3.8-27B-UD-IQ3_S.gguf` tại `D:\AI-Video-Localizer\models`; llama-server tìm thấy.
- Markdown renderer: PASS (h1, bold, inline code, link, ul/ol, blockquote, code block, escape).
- Build PyInstaller: đang chạy bản mới `dist\M Auto Pilot.exe`.

## Runtime notes

- EXE frozen dùng `M_AUTO_PILOT_ROOT = D:\M-Auto-Pilot` (đã tạo: work/auto_pilot/chats.json + resource_state.json, giữ 4 chat cũ).
- Model path fallback: `M_AUTO_PILOT_MODELS_DIR` (mặc định `D:\AI-Video-Localizer\models`).
- llama-server fallback: `M_AUTO_PILOT_LLAMA_SERVER` (mặc định `D:\AI-Video-Localizer\tools\llama.cpp\llama-server.exe`).
- Agent streaming: `_chat` stream từng token, fallback non-stream khi endpoint không hỗ trợ.
- Chưa nên chạy Q4/Q6 cùng lúc với pipeline dịch trên RTX 4070 SUPER 12 GB; dùng GPU status kiểm tra VRAM.

## Next priorities

1. Smoke test EXE mới trên Desktop với model IQ3_S (chat + tool).
2. Nếu cần: tự động hạ pipeline 8080 khi chọn Q6.
3. Mở rộng computer-use (screenshot → grounding model 7B theo nhu cầu).
