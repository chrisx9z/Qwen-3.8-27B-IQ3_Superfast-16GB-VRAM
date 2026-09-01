# Auto Pilot Qwen 3.8 27B IQ3_Superfast

**Auto Pilot Qwen 3.8 27B IQ3_Superfast** là trợ lý cá nhân và Coding Agent chạy hoàn toàn cục bộ trên máy tính: trò chuyện tiếng Việt thông minh, lập trình tự động (Coding Agent), nghiên cứu web, điều khiển hệ điều hành Windows Win32 Native, tự động hóa trình duyệt Chrome DevTools Protocol (CDP) và điều khiển AI Video Localizer — tối ưu hóa trên mô hình **Qwen3.8-27B-UD-IQ3_S** qua `llama.cpp` (cổng 8080).

---

## 🌟 Điểm Nổi Bật & Tính Năng Đột Phá (283 Tools Chuyên Sâu)

1. **Hệ Sinh Thái 283 Tools Tự Động Hóa**:
   - **Computer Use & Windows Native**: Điều khiển chuột Bézier mượt mà như người thật, gõ tiếng Việt Unicode SendInput API, quản lý cây HWND và chuyển đổi Virtual Desktops ngầm không chiếm chuột.
   - **Chrome CDP Mastery**: Điều khiển đa tab, tiêm Userscript/Extension trực tiếp (`inject_chrome_userscript_extension`), quản lý Cookie, quan sát biến đổi DOM Mutation & Network Idle.
   - **Vision OCR & AI Screen Grounding**: Dự đoán Bounding Box tọa độ màn hình High-DPI/2K/4K, tìm kiếm văn bản qua OCR và tự động điền Form ngữ nghĩa thông minh.
   - **Safety Sandbox Firewall**: Tường lửa bảo vệ hệ thống (`enforce_computer_action_safety_firewall`), ngăn chặn 100% các hành vi xóa file hệ thống hoặc format ổ đĩa.
2. **Dynamic Semantic Tool Router**:
   - Tự động nạp động các công cụ cốt lõi (chỉ ~6-22 tools tương đương 790-2,000 tokens), triệt tiêu hoàn toàn lỗi tràn Context Window 8,192 tokens của LLM.
3. **Chuẩn Hóa UTF-8 Streaming 100%**:
   - Khắc phục triệt để lỗi vỡ font tiếng Việt (Mojibake), render markdown và suy luận mượt mà.
4. **Giao Diện Trực Quan & Tinh Gọn**:
   - Tự động co giãn bong bóng chat theo nội dung văn bản (`AutoResizingTextBrowser`).
   - Tự động thu gọn khối suy luận (Reasoning Card) và Terminal Logs.
   - Bộ studio chuyên sâu: `AllToolsCatalogDialog` (/tools), `ComputerUseStudioDialog`, `ComputerSafetyStudioDialog`, `ComputerMissionStudioDialog`.

---

## 🛠️ Vị Trí Thư Mục & Cấu Trúc Dự Án

| Thành phần | Đường dẫn |
|---|---|
| Mã nguồn (Git Repo) | `D:\Vibe Code\M-Auto-Pilot` |
| Runtime state (Logs, Chats, Checkpoints) | `work\auto_pilot\` |
| Model GGUF | `D:\AI-Video-Localizer\models\Qwen3.8-27B-UD-IQ3_S.gguf` |
| Llama Server | `http://127.0.0.1:8080/v1/chat/completions` |
| File EXE đóng gói | `D:\Vibe Code\M-Auto-Pilot\dist\M Auto Pilot.exe` |
| Shortcut Desktop | `D:\OneDrive\Desktop\M Auto Pilot.exe` |

---

## 🚀 Hướng Dẫn Khởi Chạy

### 1. Chạy từ mã nguồn:
```powershell
Set-Location "D:\Vibe Code\M-Auto-Pilot"
& "D:\AI-Video-Localizer\.venv\Scripts\python.exe" scripts\run_auto_pilot_gui.py
```

### 2. Chạy từ File thực thi EXE:
Mở file **`M Auto Pilot.exe`** ngay trên màn hình Desktop (hoặc nhấn phím tắt toàn hệ thống **`Alt + Shift + M`** để ẩn/hiện cửa sổ).

### 3. Kiểm thử tự động:
```powershell
& "D:\AI-Video-Localizer\.venv\Scripts\python.exe" scripts\test_local_agent.py
```

---

## 📦 Đóng Gói Thành Bản EXE Độc Lập

```powershell
Set-Location "D:\Vibe Code\M-Auto-Pilot"
& "D:\AI-Video-Localizer\.venv\Scripts\python.exe" -m PyInstaller "M Auto Pilot.spec" --noconfirm
Copy-Item "dist\M Auto Pilot.exe" "D:\OneDrive\Desktop\M Auto Pilot.exe" -Force
```
