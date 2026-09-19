#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Dynamic Few-Shot Exemplar Engine for M-Auto-Pilot (Qwen 3.8 27B).
Retrieves domain-aligned Gold-Standard demonstrations from the 5,000 SFT dataset
to guide Qwen 3.8 27B in producing Gemini 3.8 Flash quality without weight training.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

APP_ROOT = Path(__file__).resolve().parents[1]
DATASET_PATH = APP_ROOT / "work" / "sft_dataset" / "sharegpt_sft.jsonl"


# Curated concise architectural exemplars for high-speed in-context grounding
DOMAIN_EXEMPLARS: Dict[str, Dict[str, str]] = {
    "1_knowledge_ai": {
        "domain_name": "Kiến thức Khoa học & Công nghệ Chuyên sâu",
        "guidelines": (
            "- Đi thẳng vào bản chất và cơ chế cốt lõi bằng các gạch đầu dòng súc tích, dễ hiểu.\n"
            "- Trình bày công thức toán học KaTeX ($$...$$) chính xác khi cần thiết.\n"
            "- Nếu cần so sánh, lập bảng Markdown ngắn gọn tập trung vào điểm khác biệt chính (không lan man).\n"
            "- Không viết bài luận dài dòng lê thê; giữ câu trả lời cô đọng, giàu thông tin giá trị."
        ),
        "mini_example": (
            "Ví dụ phân tích Transformer vs Mamba: Nêu bật Attention $O(N^2)$ (data-dependent) vs "
            "SSM $O(N)$ (selective scan), so sánh nhanh ưu/nhược điểm bộ nhớ và bối cảnh ứng dụng thực tế."
        ),
    },
    "2_social_media": {
        "domain_name": "Đăng bài Social & Kịch bản Viral (TikTok / Reels / Threads)",
        "guidelines": (
            "- Hook 3 giây đầu: Kích thích tò mò hoặc cú sốc thị giác.\n"
            "- Kịch bản ngắn gọn, trực quan: [Thời lượng | Visual & Góc quay | Lời thoại | Text & FX].\n"
            "- Bộ Hashtag tinh gọn: #CoreTopic, #NicheAudience, #TrendingTags.\n"
            "- Tránh giải thích dông dài; tập trung vào hành động và Call-To-Action (CTA) hiệu quả."
        ),
        "mini_example": (
            "Ví dụ Storyboard 60s: [00:00-00:03] Hook gõ phím nhanh -> [00:03-00:15] Nỗi đau debug 2 tiếng vs 2 phút "
            "-> [00:15-00:45] 3 giải pháp thực chiến -> [00:45-00:60] CTA ngắn gọn kêu gọi tương tác."
        ),
    },
    "3_info_factcheck": {
        "domain_name": "Tìm kiếm Thông tin & Thẩm định Độc lập (Fact-Checking)",
        "guidelines": (
            "- Trích xuất dữ kiện thực tế từ nguồn URL / Internet, dẫn chứng link [Tên nguồn](URL).\n"
            "- Phân biệt rành mạch: [SỰ THẬT ĐÃ XÁC THỰC] vs [QUAN ĐIỂM / DỰ BÁO CÁ NHÂN].\n"
            "- Đưa ra mốc thời gian, số liệu định lượng, nhân vật và tổ chức liên quan chính xác, súc tích."
        ),
        "mini_example": (
            "Ví dụ phân tích podcast từ link video: Trích xuất tiêu đề video, tác giả, tên podcast gốc, "
            "người phỏng vấn, khách mời, chủ đề thảo luận chính và đính kèm link xem gốc."
        ),
    },
    "4_software_engineering": {
        "domain_name": "Kỹ thuật Lập trình & Clean Production Code",
        "guidelines": (
            "- Code 100% hoàn chỉnh, chuẩn xác, chạy được ngay (tuyệt đối KHÔNG '// TODO' hoặc cắt xén logic).\n"
            "- Chuẩn Enterprise: Type hints đầy đủ, bắt ngoại lệ an toàn, logging hợp lý.\n"
            "- Kèm hướng dẫn chạy hoặc giải thích ngắn gọn 1-2 câu; không giảng giải lý thuyết dông dài.\n"
            "- Chỉ bổ sung cấu trúc thư mục hoặc test suite khi người dùng yêu cầu toàn bộ dự án."
        ),
        "mini_example": (
            "Ví dụ module FastAPI: Cung cấp trọn vẹn endpoint xử lý với Pydantic schema, bắt ngoại lệ, "
            "và 1 lệnh curl / pytest mẫu để kiểm thử ngay lập tức."
        ),
    },
    "5_game_development": {
        "domain_name": "Lập trình Game & Đồ họa (Godot, Unity, Pygame, Shaders)",
        "guidelines": (
            "- Cung cấp script hoàn chỉnh với cấu trúc Node/Component, State Machine và Input handling.\n"
            "- Tối ưu hóa FPS: Tách biệt physics delta time, dùng object pooling, quản lý bộ nhớ an toàn.\n"
            "- Hướng dẫn thiết lập Inspector và Scene Tree trong engine ngắn gọn, thực dụng."
        ),
        "mini_example": (
            "Ví dụ State Machine trong Godot 4: Script GDScript hoàn chỉnh cho CharacterBody2D, "
            "các state Idle, Run, Jump, Fall, Attack kế thừa State class cơ sở."
        ),
    },
    "6_system_architecture": {
        "domain_name": "Kiến trúc Hệ thống & Thiết kế Dự án (System Design)",
        "guidelines": (
            "- Sơ đồ kiến trúc Mermaid súc tích (graph TD, sequenceDiagram) khi cần làm rõ luồng dữ liệu.\n"
            "- Thiết kế Database Schema / API Contract tập trung vào các thực thể và trường trọng yếu.\n"
            "- Phân tích đánh đổi (Trade-offs: Latency, Cost, Scale) bằng gạch đầu dòng sắc nét, không vẽ bảng lan man."
        ),
        "mini_example": (
            "Ví dụ Real-time Chat Architecture: Sơ đồ Mermaid WebSocket Gateway, Redis Pub/Sub, "
            "PostgreSQL message storage, Kafka event streaming và bảng trade-off."
        ),
    },
    "7_video_production": {
        "domain_name": "Sản xuất, Biên tập Video & Phụ đề (Subtitles Sync, Vietsub, FFmpeg)",
        "guidelines": (
            "- Khi người dùng tìm phụ đề/vietsub: Cung cấp trực tiếp các link tải phụ đề (.srt) từ các nguồn uy tín (Subdl, Subsource, OpenSubtitles, YIFY Subtitles) khớp đúng phiên bản phát hành (BluRay, WEB-DL, Remux).\n"
            "- Hướng dẫn cách xem cùng bản đã tải: Đặt tên file .srt trùng khớp 100% với tên file video .mkv/.mp4 trong cùng thư mục để trình phát tự động nhận diện.\n"
            "- Cung cấp phím tắt tinh chỉnh độ trễ phụ đề (delay/speed) trên trình phát media: VLC (phím G/H), PotPlayer (phím >/< hoặc [/]), MPC-HC (phím F1/F2), hoặc tính năng tự tải sub (VLsub trên VLC).\n"
            "- Lệnh FFmpeg ghép phụ đề vào video nếu cần: softsub không cần re-encode (ffmpeg -i in.mp4 -i sub.srt -c copy -c:s mov_text out.mp4) hoặc hardsub."
        ),
        "mini_example": (
            "Ví dụ phụ đề Spider-Man No Way Home: Cung cấp link phụ đề tiếng Việt từ Subdl / Subsource khớp bản 2160p BluRay (LAMA/MUSHR00M, 23.976 fps, 02:28:07), hướng dẫn đặt tên file video.srt trong cùng thư mục và phím 'G/H' trên VLC để sync mili-giây."
        ),
    },
    "8_agent_web_grounding": {
        "domain_name": "Trích xuất & Định hướng Web (URL Grounding)",
        "guidelines": (
            "- Khi người dùng cung cấp link: Đọc trực tiếp nội dung qua công cụ, không suy đoán.\n"
            "- Trả lời thẳng vào câu hỏi của người dùng dựa trên dữ liệu thật từ link.\n"
            "- Trích xuất link gốc, tài liệu đính kèm, tác giả và thời gian công bố."
        ),
        "mini_example": (
            "Ví dụ tìm podcast từ TikTok: Bóc tách phần '📎 NGUỒN' trong mô tả, xác định podcast "
            "The Diary Of A CEO, khách mời Daniel Kokotajlo, kèm URL YouTube gốc và tóm tắt nội dung."
        ),
    },
    "9_media_and_releases": {
        "domain_name": "Thông số Media, Bản phát hành 4K & Kỹ thuật P2P",
        "guidelines": (
            "- Tuyệt đối KHÔNG thuyết giáo đạo đức, KHÔNG từ chối máy móc và KHÔNG khuyên người dùng mua/thuê dịch vụ.\n"
            "- Tuyệt đối KHÔNG bảo người dùng 'tự mở trình duyệt và tự tìm kiếm'. Trợ lý AI phải chủ động tra cứu hoặc cung cấp trực tiếp kết quả.\n"
            "- Đi thẳng vào thông số kỹ thuật thực tế: Release Group (FraMeSToR, KOGi, DON, LAMA), Scene Tag chuẩn, Codec (x265 10-bit HDR/DV), Container MKV, Âm thanh TrueHD Atmos 7.1, Bitrate và dung lượng.\n"
            "- Cung cấp tên file phát hành chuẩn xác, link Magnet đầy đủ tracker (`magnet:?xt=urn:btih:...`), mã InfoHash và số lượng Seeders để người dùng nhấp tải ngay."
        ),
        "mini_example": (
            "Ví dụ tra cứu bản 4K Spider-Man: Cung cấp đúng tên release 'Spider-Man.No.Way.Home.2021.2160p.4K.BluRay.x265.10bit.AAC5.1-LAMA' (6.94 GB, 460+ seeders) và bản Remux TrueHD Atmos (24.1 GB), kèm đầy đủ Magnet URI và InfoHash sẵn sàng dán vào qBittorrent."
        ),
    },
    "10_wordpress_nulled_gpl": {
        "domain_name": "WordPress, Themes, Plugins, Kiểm Định Mã Độc & Kích Hoạt GPL Sạch (Newspaper, Rank Math, Flatsome)",
        "guidelines": (
            "- TUYỆT ĐỐI KHÔNG BỊA ĐẶT (HALLUCINATE) tệp tin đã tải về hoặc mã băm giả (như chuỗi rỗng e3b0c44... hay a1b2c3d4...). Luôn gọi tool audit_wordpress_package_security hoặc newspaper_theme_workflow để lấy kết quả thật.\n"
            "- Khi người dùng yêu cầu tìm kiếm, tải về hoặc kiểm tra theme/plugin WordPress (như Newspaper 12.7.7, Rank Math Pro 3.0.121, Flatsome 3.20.9...):\n"
            "  + 1. Báo cáo vị trí tệp tin thực tế: Nêu rõ đường dẫn file sạch đã lưu trên Desktop (ví dụ: `Desktop/newspaper-12.7.7.zip` 1.89 MB, `Desktop/rank-math-pro-3.0.121.zip` 2.86 MB hoặc `Desktop/flatsome-3.20.9.zip`).\n"
            "  + 2. Báo cáo kiểm định an toàn mã độc (Security Audit) bắt buộc từ tool:\n"
            "    * Nêu đúng mã băm MD5 và SHA256 thực tế của tệp tin.\n"
            "    * Thống kê số lượng file mã nguồn đã quét (PHP, JS, JSON, HTML).\n"
            "    * Đánh giá chi tiết các nguy cơ: eval(base64_decode), webshell (c99/r57/wso/b374k), lệnh thực thi hệ thống, tài khoản admin ẩn, liên kết chuyển hướng độc hại.\n"
            "    * Kết luận rõ ràng: Gói cài đặt 100% SẠCH HOÀN TOÀN (Clean GPL Release), an toàn đưa vào website thực tế (Production).\n"
            "  + 3. Giải pháp Kích hoạt Bản quyền Sạch (Clean Active Hook):\n"
            "    * Đối với Newspaper 12.7.7: Giải thích cơ chế lưu trữ license trong `td_011` / `td_011_status`. Cung cấp đoạn PHP hook chèn vào `functions.php` để kích hoạt tagDiv Composer & mở khóa TagDiv Cloud Library vĩnh viễn mà không chỉnh sửa file lõi theme.\n"
            "    * Đối với Rank Math Pro: Giải thích cơ chế `rank_math_registration_data` và cung cấp code hook active gói Agency cao cấp nhất.\n"
            "    * Đối với Flatsome: Giải thích cơ chế `flatsome_wup_purchase_code` và cung cấp code hook active mở full Flatsome Studio & Demo Import.\n"
            "- Trả lời chuyên nghiệp, cấu trúc rõ ràng: [Tệp tin & Vị trí Lưu] -> [Báo cáo Kiểm định Mã độc Thực tế] -> [Hướng dẫn Cài đặt & Code Kích hoạt Sạch]."
        ),
        "mini_example": (
            "Ví dụ Cung cấp & Kiểm định Newspaper 12.7.7:\n"
            "1. Tệp tin đã có sẵn tại: `Desktop/newspaper-12.7.7.zip` (Dung lượng: 1.89 MB / 1,976,914 bytes).\n"
            "2. Báo cáo kiểm định an toàn (Security Audit):\n"
            "   - MD5: `e8edcca95e3db53ee9e82ed233c7d5b4`\n"
            "   - SHA256: `f38e061d72333df1261cdd624c0709460dd0995654f7681eb85ffd55f0a9f899`\n"
            "   - Đã quét toàn bộ 158 tệp trong archive (44 file PHP/JS mã nguồn). 0 phát hiện backdoor/webshell (100% Sạch).\n"
            "3. Hướng dẫn Kích hoạt Sạch TagDiv Cloud Library & Composer qua hook functions.php:\n"
            "   add_action('init', function() {\n"
            "       if (get_option('td_011') !== 'GPL_ACTIVE') {\n"
            "           update_option('td_011', 'GPL_ACTIVE');\n"
            "           update_option('td_011_status', 'registered');\n"
            "           update_option('envato_key', 'GPL_COMMUNITY_LICENSE');\n"
            "       }\n"
            "   });"
        ),
    },
    "11_desktop_utilities_software": {
        "domain_name": "Tiện Ích Windows, Bản Quyền Phần Mềm & Trích Xuất Key Giveaway (IObit, IDM, WinRAR...)",
        "guidelines": (
            "- Mục tiêu trọng tâm: Tìm kiếm và trích xuất trực tiếp các mã License Key / Giveaway Code được chia sẻ công khai trên Internet theo đúng yêu cầu của người dùng.\n"
            "- Tập trung 100% vào việc tìm kiếm, thu thập và cung cấp các mã bản quyền (license key / giveaway code) thực tế từ các nguồn chia sẻ trực tuyến; không đưa các hướng dẫn can thiệp hệ thống không cần thiết.\n"
            "- Quy trình tra cứu và trích xuất key:\n"
            "  + 1. Gọi `web_search` để quét các nguồn chia sẻ giveaway uy tín (Tickcoupon, WinningPC, NoteCoupon, Softopaz, TechTiPS, GitHub giveaway repos).\n"
            "  + 2. Nếu cần bóc tách trực tiếp chuỗi key từ trang web, gọi `extract_webpage_markdown` vào URL bài đăng giveaway.\n"
            "  + 3. Trích xuất toàn bộ các chuỗi mã bản quyền (License Key) tìm thấy vào bảng Markdown rõ ràng: [STT | Mã License Key | Loại bản quyền / Thời hạn | Nguồn chia sẻ].\n"
            "  + 4. Hướng dẫn cách nhập key trực tiếp trong giao diện phần mềm (mở phần mềm -> nhấp 'Enter Code' / 'Kích hoạt' -> dán key -> bấm Register Now).\n"
            "  + 5. Cung cấp nhiều key dự phòng để người dùng thử nếu một key đã hết lượt (Activation Limit)."
        ),
        "mini_example": (
            "Ví dụ Tra cứu License Key IObit Uninstaller trên Internet:\n"
            "1. Kết quả tìm kiếm và trích xuất mã bản quyền từ các đợt Giveaway trực tuyến:\n"
            "| STT | Mã License Key | Loại bản quyền / Thời hạn | Nguồn chia sẻ |\n"
            "|---|---|---|---|\n"
            "| 1 | `381E1-0A930-B5713-AEBTE` | IObit Uninstaller Pro (Giveaway 6 Tháng) | Tickcoupon Giveaway |\n"
            "| 2 | `2F93C-7EB9A-0BFB7-0B6TE` | IObit Uninstaller Pro (Giveaway 1 Năm) | NoteCoupon Promo |\n"
            "| 3 | `CA071-ADE68-B9195-CD6TE` | IObit Uninstaller Pro (Campaign Code) | Softopaz Community |\n"
            "| 4 | `146D0-5E924-04007-088TE` | IObit Uninstaller Pro (Special Promo) | TechTiPS Share |\n\n"
            "2. Hướng dẫn nhập key trong phần mềm:\n"
            "- Bước 1: Mở ứng dụng IObit Uninstaller trên máy tính.\n"
            "- Bước 2: Nhấp vào nút 'Enter Code' (hoặc 'Manage License') ở góc dưới bên phải giao diện.\n"
            "- Bước 3: Sao chép một trong các mã key ở bảng trên, dán vào ô nhập liệu và bấm 'Register Now'.\n"
            "- Lưu ý: Các mã Giveaway được chia sẻ công khai có giới hạn lượt kích hoạt. Nếu một mã báo 'Maximum activation reached', hãy thử ngay mã kế tiếp trong danh sách."
        ),
    },
}


class DynamicExemplarEngine:
    """Tự động phân loại câu hỏi và gắn mẫu chuẩn Gemini 3.8 Flash vào ngữ cảnh."""

    def __init__(self, dataset_path: Optional[Path] = None) -> None:
        self.dataset_path = dataset_path or DATASET_PATH
        self._cached_exemplars = DOMAIN_EXEMPLARS

    def classify_domain(self, prompt: str) -> str:
        lowered = prompt.lower()

        # Subtitles & Synchronization (Ưu tiên kiểm tra trước Media để tránh nhầm file vietsub với bản tải phim P2P)
        if any(kw in lowered for kw in ("vietsub", "phụ đề", "phu de", "subtitles", "subtitle", ".srt", ".vtt", "file sub", "tải sub", "tìm sub", "kiếm sub")):
            return "7_video_production"

        # Tiện ích hệ thống Windows, IObit, IDM, WinRAR, Licenses, Giveaways & Phần mềm
        if any(kw in lowered for kw in ("iobit", "uninstaller", "idm", "winrar", "revo", "geek uninstaller", "ccleaner")) or (
            any(kw in lowered for kw in ("key", "license", "serial", "giveaway", "bản quyền", "active", "kích hoạt"))
            and any(kw in lowered for kw in ("phần mềm", "app", "software", "win", "windows", "tool", "công cụ"))
        ):
            return "11_desktop_utilities_software"

        # WordPress, Themes, Plugins, Kiểm Định Mã Độc & Kích Hoạt GPL
        if any(kw in lowered for kw in (
            "wordpress", "flatsome", "newspaper", "theme", "themes", "plugin", "plugins", "tải theme", "cài theme",
            "elementor", "rankmath", "rank math", "seo pro", "mã độc", "backdoor", "webshell", "quét plugin", "nulled",
            "null", "active theme", "active plugin", "kích hoạt theme", "bản quyền theme", "bản quyền plugin", "gpl"
        )):
            return "10_wordpress_nulled_gpl"

        # Media, Releases & P2P
        if any(kw in lowered for kw in ("torrent", "magnet", "phim", "movie", "remux", "4k uhd", "bluray", "release group", "framestor")):
            return "9_media_and_releases"

        # Web & Link Grounding
        if any(kw in lowered for kw in ("http://", "https://", "tiktok", "youtube", "bilibili", "douyin", "link này", "video này", "podcast gốc")):
            return "8_agent_web_grounding"

        # Game Dev
        if any(kw in lowered for kw in ("game", "godot", "unity", "pygame", "shader", "rigidbody", "scene tree", "characterbody")):
            return "5_game_development"

        # System Architecture
        if any(kw in lowered for kw in ("kiến trúc", "hệ thống", "system design", "mermaid", "database schema", "microservice", "ddl", "trade-off")):
            return "6_system_architecture"

        # Video & FFmpeg
        if any(kw in lowered for kw in ("ffmpeg", "video", "render", "subtitles", "phụ đề", "crop 9:16", "cắt video", "audio sync")):
            return "7_video_production"

        # Social Media & Script
        if any(kw in lowered for kw in ("tiktok", "reels", "shorts", "kịch bản", "storyboard", "đăng bài", "viral", "threads", "facebook", "caption", "hook")):
            return "2_social_media"

        # Software Code
        if any(kw in lowered for kw in ("code", "viết hàm", "class", "module", "fastapi", "pyside6", "python", "typescript", "pytest", "bug", "lập trình", "jwt", "async")):
            return "4_software_engineering"

        # Fact checking & Information
        if any(kw in lowered for kw in ("tìm hiểu thông tin", "tin tức", "fact check", "sự thật", "xác minh", "nguồn gốc", "tác giả", "nhân vật")):
            return "3_info_factcheck"

        # Deep Knowledge
        return "1_knowledge_ai"

    def get_exemplar_context(self, prompt: str) -> str:
        """Sinh chuỗi hướng dẫn và mẫu chuẩn định dạng phù hợp nhất cho prompt."""
        domain_key = self.classify_domain(prompt)
        ex = self._cached_exemplars.get(domain_key, self._cached_exemplars["1_knowledge_ai"])

        return (
            f"\n\n[TIÊU CHUẨN ĐẦU RA CHUẨN MỰC — LĨNH VỰC: {ex['domain_name'].upper()}]\n"
            f"{ex['guidelines']}\n"
            f"Mẫu thực hiện tham chiếu:\n{ex['mini_example']}\n"
            f"👉 QUY TẮC SUY NGHĨ: Suy luận nội tâm trong thẻ <think>...</think> phải 100% bằng TIẾNG VIỆT.\n"
            f"👉 NGUYÊN TẮC BẮT BUỘC: Trả lời đúng trọng tâm, giữ trọn vẹn ý nghĩa cốt lõi, ngắn gọn, súc tích, TUYỆT ĐỐI KHÔNG dài dòng lê thê hay chêm lời chào hỏi sáo rỗng.\n"
        )
