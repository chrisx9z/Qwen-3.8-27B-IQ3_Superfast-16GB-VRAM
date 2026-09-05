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
            "- Giải thích từ Nguyên lý đầu tiên (First Principles: Bản chất -> Cơ chế vận hành -> Ứng dụng thực tế).\n"
            "- Trình bày công thức toán học KaTeX ($$...$$) chính xác nếu có.\n"
            "- Cung cấp bảng so sánh Markdown đa chiều (ít nhất 5-8 tiêu chí so sánh).\n"
            "- Kết thúc với mục '💡 Pro-Tip & Production Gotchas' (cạm bẫy thực tiễn & tối ưu cấp chuyên gia)."
        ),
        "mini_example": (
            "Ví dụ phân tích Transformer vs Mamba: Tách bạch rõ cơ chế Attention $O(N^2)$ (data-dependent) "
            "với State Space Model $O(N)$ (selective scan), lập bảng so sánh bộ nhớ/tính toán/retrieval, "
            "và nêu rõ các trường hợp ứng dụng thực tế."
        ),
    },
    "2_social_media": {
        "domain_name": "Đăng bài Social & Kịch bản Viral (TikTok / Reels / Threads)",
        "guidelines": (
            "- Hook 3 giây đầu: Bắt buộc kích thích tò mò hoặc cú sốc thị giác.\n"
            "- Bảng Storyboard 4 cột: [Thời lượng | Visual & Góc máy | Voiceover | Text Overlay & FX].\n"
            "- Bộ Hashtag 3 tầng: #CoreTopic, #NicheAudience, #TrendingTags.\n"
            "- Hướng dẫn chi tiết về ánh sáng, quay màn hình, pacing dựng video và Call-To-Action (CTA)."
        ),
        "mini_example": (
            "Ví dụ Storyboard 60s: [00:00-00:03] Hook gõ phím nhanh -> [00:03-00:15] Nỗi đau debug 2 tiếng vs 2 phút "
            "-> [00:15-00:45] 3 giải pháp thực chiến -> [00:45-00:60] CTA 2 chiều lưu video & comment."
        ),
    },
    "3_info_factcheck": {
        "domain_name": "Tìm kiếm Thông tin & Thẩm định Độc lập (Fact-Checking)",
        "guidelines": (
            "- Trích xuất dữ kiện thực tế từ nguồn URL / Internet, dẫn chứng link [Tên nguồn](URL).\n"
            "- Phân biệt rành mạch: [SỰ THẬT ĐÃ XÁC THỰC] vs [QUAN ĐIỂM / DỰ BÁO CÁ NHÂN].\n"
            "- Đưa ra mốc thời gian, số liệu định lượng, nhân vật và tổ chức liên quan chính xác."
        ),
        "mini_example": (
            "Ví dụ phân tích podcast từ link video: Trích xuất tiêu đề video, tác giả, tên podcast gốc, "
            "người phỏng vấn, khách mời, chủ đề thảo luận chính và đính kèm link xem gốc."
        ),
    },
    "4_software_engineering": {
        "domain_name": "Kỹ thuật Lập trình & Clean Production Code",
        "guidelines": (
            "- Code 100% hoàn chỉnh, chạy được ngay (Tuyệt đối KHÔNG viết tắt, KHÔNG '// TODO: implement here').\n"
            "- Chuẩn Enterprise: Type hints, Pydantic/FastAPI/Async, bắt ngoại lệ try/except/finally, logging.\n"
            "- Kèm theo cấu trúc thư mục dự án, requirements.txt và bộ test suite Pytest/AsyncClient.\n"
            "- Kết thúc với mục '💡 Pro-Tip & Production Gotchas'."
        ),
        "mini_example": (
            "Ví dụ module FastAPI: Cung cấp đủ config.py, db.py (SQLAlchemy 2.0 Async), models.py, schemas.py, "
            "auth.py (JWT access+refresh, Argon2), exception middleware và test_auth.py."
        ),
    },
    "5_game_development": {
        "domain_name": "Lập trình Game & Đồ họa (Godot, Unity, Pygame, Shaders)",
        "guidelines": (
            "- Cung cấp script hoàn chỉnh với cấu trúc Node/Component, State Machine và Input handling.\n"
            "- Tối ưu hóa FPS: Tách biệt physics delta time, dùng object pooling, quản lý bộ nhớ an toàn.\n"
            "- Hướng dẫn thiết lập Inspector và Scene Tree trong engine."
        ),
        "mini_example": (
            "Ví dụ State Machine trong Godot 4: Script GDScript hoàn chỉnh cho CharacterBody2D, "
            "các state Idle, Run, Jump, Fall, Attack kế thừa State class cơ sở."
        ),
    },
    "6_system_architecture": {
        "domain_name": "Kiến trúc Hệ thống & Thiết kế Dự án (System Design)",
        "guidelines": (
            "- Sơ đồ kiến trúc Mermaid rõ ràng (graph TD, sequenceDiagram, erDiagram).\n"
            "- Thiết kế Database Schema chi tiết (DDL / bảng trường kiểu dữ liệu, index, khóa ngoại).\n"
            "- Bảng phân tích đánh đổi (Trade-off Matrix: Latency vs Consistency, Cost vs Scalability).\n"
            "- Thiết kế API contract (RESTful/gRPC JSON payload) và Caching/Queue layer."
        ),
        "mini_example": (
            "Ví dụ Real-time Chat Architecture: Sơ đồ Mermaid WebSocket Gateway, Redis Pub/Sub, "
            "PostgreSQL message storage, Kafka event streaming và bảng trade-off."
        ),
    },
    "7_video_production": {
        "domain_name": "Sản xuất & Biên tập Video (FFmpeg Automation, Audio Sync)",
        "guidelines": (
            "- Lệnh FFmpeg chính xác 100% copy-paste chạy được ngay, giải thích từng cờ (flag).\n"
            "- Thiết lập codec tối ưu: libx264/libx265, crf, preset, bộ lọc scale, crop, drawtext.\n"
            "- Xử lý đồng bộ phụ đề SRT/ASS và cấu hình tỷ lệ khung hình (16:9 vs 9:16 dọc)."
        ),
        "mini_example": (
            "Ví dụ cắt video ngắn 9:16: ffmpeg -i in.mp4 -filter_complex '[0:v]scale=1080:1920:force_original_aspect_ratio=increase,boxblur=20:5[bg];[0:v]scale=1080:-1[fg];[bg][fg]overlay=(W-w)/2:(H-h)/2' -c:a copy out.mp4"
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
}


class DynamicExemplarEngine:
    """Tự động phân loại câu hỏi và gắn mẫu chuẩn Gemini 3.8 Flash vào ngữ cảnh."""

    def __init__(self, dataset_path: Optional[Path] = None) -> None:
        self.dataset_path = dataset_path or DATASET_PATH
        self._cached_exemplars = DOMAIN_EXEMPLARS

    def classify_domain(self, prompt: str) -> str:
        lowered = prompt.lower()

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
            f"\n\n[TIÊU CHUẨN ĐẦU RA GEMINI 3.8 FLASH — LĨNH VỰC: {ex['domain_name'].upper()}]\n"
            f"{ex['guidelines']}\n"
            f"Mẫu thực hiện tham chiếu:\n{ex['mini_example']}\n"
            f"👉 ÁP DỤNG NGAY: Trả lời câu hỏi của người dùng với phong cách, cấu trúc phân cấp, "
            f"đầy đủ 100% không viết tắt, và độ sâu sắc tương đương mẫu trên.\n"
        )
