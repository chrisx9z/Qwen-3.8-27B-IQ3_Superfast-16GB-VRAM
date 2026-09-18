# Qwen 3.8 27B IQ3_Superfast 16GB VRAM 🚀 (M-Auto-Pilot)

**Qwen 3.8 27B IQ3_Superfast 16GB VRAM** là hệ thống trợ lý AI cá nhân, lập trình tự động và điều khiển máy tính (Computer Use) chạy độc lập 100% cục bộ trên phần cứng người dùng. Vận hành trên mô hình tối ưu **Qwen3.8-27B-UD-IQ3_S** qua backend `llama.cpp` (hoặc các endpoint tương thích OpenAI), hệ thống đạt tốc độ sinh mã ~50.4 tokens/giây trên GPU thông thường (12–16GB VRAM) mà không cần bất kỳ dịch vụ đám mây hay API bên ngoài nào.

---

## 🌟 Tính Năng & Kiến Trúc Nổi Bật

### 1. ⚡ MTP (Multi-Token Prediction) & Tăng Tốc Xử Lý Prompt
- **FlashAttention-2 (`--flash-attn on`)**: Tăng tốc đánh giá prompt gấp $2\times - 3\times$, giảm bộ nhớ đệm KV cache tới $40\%$.
- **Tái Sử Dụng Prompt KV Cache (`"cache_prompt": True`)**: Tái sử dụng prefix KV cache qua các lượt đối thoại công cụ, loại bỏ tính toán lặp lại và đưa thời gian ra token đầu tiên (TTFT) về mức mili-giây.
- **Continuous Batching (`--cont-batching`, `-b 2048`, `-ub 512`)**: Xử lý song song thông lượng cao trên nhân Tensor / CUDA Cores.
- **N-gram Speculative Lookup Decoding (`--lookup-ngram-min 3`)**: Tăng tốc sinh code và dữ liệu cấu trúc từ $1.5\times - 2.5\times$ mà không tiêu hao thêm VRAM.
- **Context Shifting (`--ctx-shift`)**: Tự động xoay chuyển ngữ cảnh mượt mà khi tiến gần giới hạn 16,384 tokens.

### 2. 🛠️ 302+ Công Cụ Tự Động Hóa Toàn Diện & 91 Hộp Thoại Trực Quan
- **Lập Trình Tự Động (Autonomous Coding)**: Phân tích cú pháp AST, vá file nguyên tử (diff/patch), chạy kiểm thử tự động (pytest), quản lý git commit/push, tạo điểm khôi phục checkpoint.
- **Điều Khiển Máy Tính (Computer-Use)**: Di chuyển chuột mô phỏng vật lý đường cong Bézier, gửi phím Unicode SendInput chuẩn Win32, theo dõi cây cửa sổ HWND và màn hình ảo.
- **Chrome CDP Automation**: Kết nối trực tiếp Chrome DevTools Protocol, quản lý đa tab, tự động chèn extension / userscript và giám sát sự kiện mạng.
- **Định Vị Màn Hình RapidOCR**: Nhận diện văn bản và phần tử ảnh chính xác trên màn hình độ phân giải cao High-DPI / Retina.
- **Tường Lửa An Toàn (Safety Sandbox Firewall)**: Giám sát thời gian thực mọi thao tác (`enforce_computer_action_safety_firewall`), ngăn chặn các lệnh nguy hiểm.

### 3. 🛡️ Quy Trình Kiểm Định & Tiếp Nhận Gói WordPress / Theme An Toàn
Hệ thống tích hợp quy trình chuyên dụng cách ly và phân tích mã độc gói tệp (`newspaper_theme_workflow`):
- **Tách Biệt Nghiên Cứu và Tải Về**: Tự động tra cứu thông tin bản quyền chính thức từ nhà phát hành (tagDiv / ThemeForest), kiên quyết từ chối tìm kiếm hoặc tải các bản nulled, crack, license-bypass chứa rủi ro backdoor.
- **Bảo Vệ SSRF & Khu Vực Cách Ly (Quarantine)**: Chỉ tải qua giao thức HTTPS vào thư mục cách ly chuyên biệt (`work/quarantine/<scan_id>`), chặn toàn bộ địa chỉ loopback (127.0.0.1), mạng nội bộ RFC 1918, link-local và cloud metadata (169.254.169.254), đồng thời kiểm tra an toàn từng bước chuyển hướng (redirect hops).
- **Kiểm Soát Tệp Nén Chống DoS / Zip Bomb**: Giới hạn tải tối đa 200 MB, 10.000 tệp tin, 500 MB giải nén, tỷ lệ nén tối đa 15:1, độ sâu thư mục tối đa 10 tầng. Tự động loại bỏ tấn công zip-slip thoát thư mục, đường dẫn tuyệt đối, ký tự null, tên thiết bị đặc biệt của Windows (CON, PRN, AUX, NUL, COM1-9, LPT1-9), symlink và file thực thi nhị phân (.exe, .bat, .sh...).
- **Phân Tích Tĩnh PHP / JS Sâu**: Quét phát hiện chữ ký webshell, thực thi mã động (`eval(base64_decode...)`), chèn tài khoản admin ẩn, cấp quyền bí mật và ngụy trang đuôi mở rộng kép (`.png.php`).
- **Theo Dõi Nguồn Gốc Kép & Quét Diệt Virus (Defender / ClamAV)**: Phân định rạch ròi nguồn gốc (`OFFICIAL_AUTHENTIC`, `UNVERIFIED_THIRD_PARTY`, `KNOWN_PIRATE_SOURCE`) với trạng thái an ninh (`VERIFIED_CLEAN`, `SUSPICIOUS_WARNING`, `MALICIOUS_BLOCKED`). Tệp không rõ nguồn gốc không bao giờ được cấp chứng nhận `VERIFIED_CLEAN`. Gọi trực tiếp Microsoft Defender hoặc ClamAV qua mảng đối số an toàn, không qua shell.

---

## 🚀 Hướng Dẫn Cài Đặt & Chạy

### 1. Yêu Cầu Hệ Thống:
- Windows 10/11 x64 hoặc macOS (Apple Silicon / Intel).
- GPU NVIDIA (12–16GB VRAM) hoặc Apple Silicon Unified Memory.
- Python 3.10 – 3.14.
- Mô hình: `Qwen3.8-27B-UD-IQ3_S.gguf` chạy tại `http://127.0.0.1:8080/v1/chat/completions`.

### 2. Khởi Chạy Từ Mã Nguồn:
```powershell
# Cài đặt thư viện phụ thuộc
pip install -r requirements.txt

# Khởi chạy giao diện Auto Pilot
python scripts/run_auto_pilot_gui.py
```

### 3. Chạy Bản Đóng Gói Desktop:
Nhấp đúp vào **`Auto Pilot Qwen 3.8 27B IQ3_Superfast.exe`** trên màn hình Desktop.

### 4. Chạy Bộ Kiểm Thử Tự Động:
```powershell
# Kiểm thử toàn diện tác vụ agent
python scripts/test_local_agent.py

# Kiểm thử quy trình an toàn gói WordPress & Newspaper workflow
python scripts/test_wordpress_package_workflow.py

# Kiểm thử tích hợp runtime cách ly Agent-Reach & tường lửa SSRF / IPI
python scripts/test_agent_reach_integration.py
```

---

## 🌐 Tích Hợp Nghiên Cứu Độc Lập Agent-Reach

M-Auto-Pilot tích hợp adapter nghiên cứu công khai cách ly (`agent_reach_research`) vận hành trên runtime riêng biệt (`work/auto_pilot/external/agent_reach_runtime`):
- **Không Ô Nhiễm Dependencies**: Gói phụ thuộc Agent-Reach nằm độc lập trong runtime riêng, không sửa đổi `requirements.txt` hay `M Auto Pilot.spec` gốc.
- **Tường Lửa Chống SSRF & DNS-Rebinding**: Chặn đứng truy cập vào mạng nội bộ, loopback và metadata IP (`127.0.0.1`, `10.0.0.0/8`, `192.168.0.0/16`, `169.254.169.254`, `localhost`).
- **Phòng Ngự Tiêm Nhiễm Lệnh Gián Tiếp (IPI)**: Dữ liệu bóc tách được đóng khung rõ ràng để LLM không thực thi nhầm thành hướng dẫn hệ thống.
- **Chặn Đứng Các Tính Năng Nguy Hiểm**: Chặn trích xuất cookie trình duyệt, cấm lệnh cài đặt toàn cục (`agent-reach install --system`), và cấm đăng ký skill toàn cục.
- **Năng Lực Đã Xác Thực**: Đọc nội dung web qua Jina Reader, phân tích RSS/Atom feed và tìm kiếm video Bilibili công khai.

---

## 📦 Đóng Gói Ứng Dụng Desktop Độc Lập

```powershell
python -m PyInstaller "M Auto Pilot.spec" --noconfirm
```

Tệp thực thi đầu ra được lưu tại `dist/Auto Pilot Qwen 3.8 27B IQ3_Superfast.exe`.
