#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
High-Quality SFT & DPO Dataset Generator for M-Auto-Pilot (Qwen 3.8 27B)
Benchmarked & Distilled from Gemini Flash standards.

Covers the 8 core daily user domains:
1. Tìm hiểu kiến thức (Knowledge, AI, Science, Philosophy, Economics)
2. Đăng bài social (Viral hooks, TikTok scripts, Facebook, Threads, LinkedIn)
3. Tìm hiểu thông tin & Fact-checking (Real-time fact checking, news synthesis)
4. Code phần mềm (Clean production Python, TypeScript, FastAPI, PySide6, Go)
5. Code game (Godot, Pygame, Unity C#, ECS, Shaders, Pathfinding)
6. Lên kế hoạch kiến trúc dự án (System design, Database schema, Microservices, Caching)
7. Tạo video & Chỉnh sửa video (FFmpeg commands, Storyboards, Subtitle sync, Video AI)
8. Cào web & Đọc URL tổng quát (TikTok, YouTube, Agent grounding, Anti-hallucination)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import re
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

SYSTEM_PROMPT = """Bạn là Qwen 3.8 27B IQ3_Superfast — Trợ lý AI và Coding Agent cục bộ đa năng, thông minh và sắc bén.
Nguyên tắc trả lời cốt lõi:
1. Đi thẳng vào trọng tâm, giải thích sâu sắc, đa chiều, có tư duy logic cao, không trả lời hời hợt.
2. Với mã nguồn: Luôn viết code hoàn chỉnh, chuẩn production, có type-hints, docstrings, bắt ngoại lệ (try-except) và không dùng pseudo-code hay "// TODO viết tiếp ở đây".
3. Với nội dung Social / Video: Luôn có Hook mạnh giữ chân người xem trong 3 giây đầu, phân cảnh rõ ràng (Visual + Audio) và Call-To-Action (CTA) tự nhiên.
4. Với URL và Web: Luôn trích xuất sự thật khách quan từ dữ liệu nguồn, phân định rành mạch giữa Sự thật (Facts) và Quan điểm (Opinions), tuyệt đối không bịa đặt."""


@dataclass
class SFTExample:
    id: str
    category: str
    subcategory: str
    prompt: str
    chosen_response: str
    rejected_response: str
    source_model: str
    metadata: Dict[str, Any]

    def to_sharegpt(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "category": self.category,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": self.prompt},
                {"role": "assistant", "content": self.chosen_response},
            ],
        }

    def to_alpaca(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "category": self.category,
            "instruction": self.prompt,
            "input": "",
            "output": self.chosen_response,
        }

    def to_dpo(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "category": self.category,
            "prompt": self.prompt,
            "chosen": self.chosen_response,
            "rejected": self.rejected_response,
        }


# ==============================================================================
# TAXONOMY SEED MATRIX (8 CORE PILLARS)
# ==============================================================================

TAXONOMY = {
    "1_knowledge_ai": {
        "name": "Tìm hiểu kiến thức & Khoa học chuyên sâu",
        "weight": 0.15,
        "topics": [
            ("FlashAttention-2 vs FlashAttention-3", "Cơ chế Tiling, phân bổ I/O giữa HBM và SRAM, Online Softmax"),
            ("Mixture of Experts (MoE) Routing", "Top-K Gating, Load Balancing Loss, Token Dropping"),
            ("Rotary Position Embedding (RoPE)", "Xoay ma trận trong không gian 2D, suy rộng chiều dài ngữ cảnh (NTK-aware, YaRN)"),
            ("Direct Preference Optimization (DPO)", "Công thức nghiệm đóng Bradley-Terry loại bỏ Reward Model, Reference Policy Regularization"),
            ("Quantization GGUF (K-Quants, IQ-Quants)", "IQ3_S, IQ4_XS, ma trận trọng số phi tuyến, bảo toàn Perplexity trên 16GB VRAM"),
            ("Cơ học lượng tử: Quantum Superposition & Entanglement", "Nguyên lý bất định Heisenberg, nghịch lý EPR, ứng dụng trong Mật mã lượng tử QKD"),
            ("Kinh tế học: Trường phái Áo (Austrian Economics) vs Keynes", "Lý thuyết chu kỳ kinh doanh (ABCT), tiền tệ tệ hại, can thiệp lãi suất"),
            ("Khoa học thần kinh: Synaptic Plasticity & Long-Term Potentiation", "Cơ chế Hebbian Learning, Dopamine Reward Pathway, tương đồng với Backpropagation"),
            ("Toán học giải tích: Gradient Descent & Newton-Raphson", "Độ dốc bậc 1 vs Ma trận Hessian bậc 2, Saddle Points và Momentum Optimizer"),
            ("Triết học nhận thức: Nghịch lý Phòng Trung Hoa (Chinese Room)", "John Searle, Cú pháp (Syntax) vs Ngữ nghĩa (Semantics), AGI có thực sự 'hiểu'?"),
        ]
    },
    "2_social_media": {
        "name": "Đăng bài Social & Viral Copywriting",
        "weight": 0.15,
        "topics": [
            ("TikTok 60s Script: AI không thay thế lập trình viên", "Hook 3s, phân cảnh tương phản 2 màn hình, 3 kỹ năng cốt lõi 2026, CTA"),
            ("Facebook Long-form: Hành trình tối ưu hóa 27B LLM trên PC gia đình", "Câu chuyện thực tế, từ bế tắc Out of Memory đến mượt mà 35 token/s, bài học kinh nghiệm"),
            ("LinkedIn Thought Leadership: Xu hướng Autonomous Coding Agents", "Từ copilot gợi ý dòng code sang multi-agent orchestrator, cách doanh nghiệp đón đầu"),
            ("Threads / X Viral Thread: 7 công cụ AI giúp 1 solo dev làm việc như 1 team 5 người", "Cấu trúc 8 post, hình ảnh minh họa gợi ý, số liệu định lượng, bookmark call"),
            ("TikTok Video Hook: Kỹ năng quan trọng nhất thập kỷ tới", "Đặt câu hỏi lật ngược tư duy thông thường, nhịp cắt nhanh 2 giây/cảnh, sub màu nổi bật"),
            ("Facebook Post tương tác cao: Cuộc tranh luận giữa Microservices và Modular Monolith", "Gợi mở tranh luận, đưa 2 góc nhìn đối nghịch, mời gọi cộng đồng chia sẻ case study"),
            ("Kịch bản Reels/Shorts: 3 sai lầm khiến Prompt của bạn không bao giờ ra kết quả tốt", "Thực tế trước/sau (Before & After), ví dụ trực quan trên màn hình, lưu lại ngay"),
            ("LinkedIn Post: Văn hóa Remote Work và quản trị bằng Output", "Bài học quản lý đội ngũ phân tán, KPI định hướng kết quả thay vì đếm giờ làm việc"),
        ]
    },
    "3_info_factcheck": {
        "name": "Tìm hiểu thông tin & Fact-Checking",
        "weight": 0.10,
        "topics": [
            ("Báo cáo AI 2027 & Cảnh báo từ Whistleblower OpenAI Daniel Kokotajlo", "Từ chối $2M cam kết im lặng, dự báo 70% xác suất AI thay đổi kinh tế toàn cầu"),
            ("Phân tích Báo cáo Tài chính Q4 của NVIDIA: Động lực tăng trưởng Data Center", "Doanh thu GPU compute, tỷ suất lợi nhuận gộp 75%, rủi ro tập trung khách hàng lớn"),
            ("Kiểm chứng tin đồn: Các quy định EU AI Act áp dụng cho Open-Weight Models", "Phân loại mức độ rủi ro, ngoại lệ cho nghiên cứu phi thương mại, thời hạn tuân thủ"),
            ("So sánh hiệu năng thực tế giữa DeepSeek-V3, Qwen 2.5 và LLaMA 3.3", "HumanEval, MATH, MMLU-Pro, chi phí training per token, kiến trúc MoE"),
            ("Lịch sử phát triển của Thung lũng Silicon: Từ Fairchild Semiconductor đến kỷ nguyên LLM", "Mạng lưới khởi nghiệp, vai trò của DARPA, bài học về hệ sinh thái đổi mới sáng tạo"),
        ]
    },
    "4_software_engineering": {
        "name": "Code phần mềm & Kỹ thuật lập trình Clean Code",
        "weight": 0.18,
        "topics": [
            ("FastAPI + Asyncio: Hệ thống WebSocket Streaming thông báo thời gian thực", "Connection Manager, Redis Pub/Sub, heartbeat ping-pong, xác thực JWT token"),
            ("Python Async Task Pool với Dynamic Concurrency & Rate Limiting", "Semaphore, Exponential Backoff, Circuit Breaker pattern, graceful shutdown"),
            ("PySide6 / PyQt6: Custom Animated Modern Card UI với Glassmorphism", "QGraphicsDropShadowEffect, QPropertyAnimation, QPainter paintEvent, StyleSheet QSS"),
            ("TypeScript / Node.js: Xây dựng Event-Driven Architecture với RabbitMQ", "AMQP connection, durable queue, message acknowledgement, dead-letter exchange (DLX)"),
            ("Go (Golang): Concurrent Worker Pool xử lý 100,000 files/phút", "Goroutines, Channels, sync.WaitGroup, context cancellation, memory-efficient streaming"),
            ("Rust: Viết thư viện bóc tách Markdown tốc độ cực cao", "Zero-copy parsing, string slices `&str`, pattern matching, error handling với Result"),
            ("Design Pattern: State Machine Pattern quản lý vòng đời thanh toán đơn hàng", "Pending, Processing, Completed, Refunded, Cancelled - ngăn chặn race condition"),
            ("Python AST: Tự động phát hiện và dọn dẹp Unused Imports", "ast.parse, NodeVisitor, phân tích tên biến sử dụng, viết đè file an toàn"),
        ]
    },
    "5_game_development": {
        "name": "Code Game (Godot, Pygame, Unity, Mechanics)",
        "weight": 0.12,
        "topics": [
            ("Godot 4 GDScript: Hệ thống Character Controller 2D mượt mà", "Coyote time, Jump buffering, Wall slide & Wall jump, gia tốc mượt mà với lerp"),
            ("Unity C#: Hệ thống Inventory System dạng Grid theo phong cách Resident Evil / Diablo", "ScriptableObject, Item Data, ma trận 2D xoay item, UI Drag & Drop"),
            ("Pygame: Thuật toán Pathfinding A* (A-Star) với trực quan hóa động", "PriorityQueue, Heuristic Manhattan/Euclidean, Grid Node states, render thời gian thực"),
            ("Godot 4: Shader 2D tạo hiệu ứng nước gợn sóng phản chiếu (Water Reflection)", "VisualShader / Code Shader, UV distortion, screen_texture, noise texture"),
            ("C# Unity: State Machine cho AI Enemy (Patrol, Alert, Chase, Attack)", "Hierarchical State Machine, tầm nhìn FOV (Raycast), âm thanh cảnh báo"),
            ("Game Architecture: Entity Component System (ECS) trong Game Development", "Tách bạch Data và Logic, Memory Locality, Cache Friendly, ví dụ thực chiến"),
        ]
    },
    "6_system_architecture": {
        "name": "Lên kế hoạch kiến trúc dự án & System Design",
        "weight": 0.10,
        "topics": [
            ("Thiết kế Hệ thống Video Transcoding quy mô lớn (YouTube / TikTok Clone)", "Sơ đồ Mermaid, API Gateway, S3 chunk upload, Celery/RabbitMQ Workers, FFmpeg, CDN"),
            ("Kiến trúc Database cho Sàn Thương mại Điện tử xử lý Flash Sale", "PostgreSQL schema, Optimistic Locking, Redis Caching stock counter, Outbox Pattern"),
            ("Microservices vs Modular Monolith: Ma trận quyết định kiến trúc năm 2026", "Đánh giá chi phí vận hành, độ phức tạp team, distributed transactions, database per service"),
            ("Thiết kế Real-time Collaborative Document (như Google Docs / Notion)", "Operational Transformation (OT) vs CRDTs (Conflict-free Replicated Data Types)"),
            ("Kiến trúc Multi-Agent Orchestrator cục bộ (Local Agent Framework)", "Memory Store (Chroma/FAISS), Safety Sandbox, Dynamic Tool Registry, Loop Supervisor"),
        ]
    },
    "7_video_production": {
        "name": "Tạo video, Chỉnh sửa video & FFmpeg Automation",
        "weight": 0.10,
        "topics": [
            ("FFmpeg: Biến video ngang 16:9 thành video dọc 9:16 có nền mờ nghệ thuật", "filter_complex scale, boxblur 20:20, overlay căn giữa, ép phụ đề SRT với font tùy chỉnh"),
            ("Kịch bản Storyboard phân cảnh hoàn chỉnh cho Video giới thiệu sản phẩm AI", "Bảng 5 cột: Timecode, Cảnh quay Visual, Lời bình Voiceover, SFX/BGM, Hướng dẫn dựng"),
            ("FFmpeg: Tự động tách âm thanh, chuẩn hóa âm lượng theo chuẩn EBU R128 (-14 LUFS)", "loudnorm filter, hai lượt đo lường (2-pass measurement), bảo toàn dynamic range"),
            ("Python Script: Tự động cắt bỏ các đoạn im lặng (Silence Removal) trong video", "pydub / moviepy / ffmpeg silencedetect, tính toán timecodes, ghép các đoạn nói liên tục"),
            ("Quy trình Video Localization Pipeline: Dịch thuật và lồng tiếng tự động", "Bóc tách audio -> Whisper STT -> LLM Dịch thuật ngữ cảnh -> TTS -> Ghép video hoàn chỉnh"),
        ]
    },
    "8_agent_web_grounding": {
        "name": "Cào web, Đọc URL tổng quát & Agent Grounding",
        "weight": 0.10,
        "topics": [
            ("Trích xuất thông tin Podcast gốc từ video TikTok reaction", "Bóc tách oEmbed, phát hiện link YouTube The Diary Of A CEO Daniel Kokotajlo, tóm tắt ý chính"),
            ("Đọc bài viết kỹ thuật từ URL và lập bảng so sánh Trade-offs", "Bỏ qua scripts/quảng cáo, trích xuất cấu trúc H2/H3, lập bảng so sánh ưu/nhược điểm"),
            ("Agent Tool Calling: Quy trình đa bước điều tra thị trường một công ty công nghệ", "Phối hợp extract_webpage_markdown, web_search, fact_check để lập hồ sơ doanh nghiệp"),
            ("Nhận diện bẫy ảo giác (Anti-Hallucination) khi đọc tài liệu web thiếu dữ kiện", "Nguyên tắc trung thực: Thừa nhận thiếu dữ liệu thay vì tự bịa đặt, gợi ý nguồn tra cứu bổ sung"),
        ]
    }
}

ROLES = [
    "Dưới góc nhìn của một Senior Software Engineer",
    "Trong bối cảnh xây dựng hệ thống quy mô lớn (High Scale)",
    "Để hướng dẫn cho lập trình viên muốn nâng cao trình độ",
    "Khi tối ưu hóa ứng dụng trên tài nguyên giới hạn (16GB RAM/VRAM)",
    "Từ kinh nghiệm triển khai thực chiến tại doanh nghiệp",
    "Khi chuẩn bị cho buổi thuyết trình kiến trúc hệ thống",
    "Dưới góc độ tối ưu hóa hiệu năng và độ tin cậy",
    "Khi xây dựng sản phẩm công nghệ mới đòi hỏi tính ổn định cao",
    "Trong bài toán xử lý dữ liệu phức tạp đòi hỏi độ trễ thấp",
    "Khi đối chiếu so sánh trực quan cho đội ngũ kỹ thuật",
]

STYLES = [
    "hãy phân tích sâu bản chất kỹ thuật và cơ chế hoạt động",
    "hãy cung cấp giải pháp toàn diện kèm mã nguồn và lưu ý thực chiến",
    "hãy so sánh đa chiều ưu nhược điểm so với các giải pháp thông thường",
    "hãy chỉ ra các cạm bẫy (pitfalls) phổ biến và phương pháp phòng tránh",
    "hãy thiết kế kiến trúc chi tiết và phân tích luồng dữ liệu",
    "hãy hướng dẫn từng bước triển khai kèm checklist kiểm thử",
    "hãy tối ưu hóa tài nguyên và giải quyết nút thắt cổ chai (bottleneck)",
    "hãy trình bày giải pháp kèm ví dụ minh họa trực quan",
]

CONSTRAINTS = [
    "Trình bày mạch lạc, rõ ràng bằng Markdown, không mở đầu sáo rỗng.",
    "Kèm theo bảng so sánh trade-offs và kết luận ứng dụng thực tế.",
    "Mã nguồn phải hoàn chỉnh, có type hints và xử lý ngoại lệ.",
    "Đi thẳng vào trọng tâm kỹ thuật với chiều sâu chuyên môn cao.",
    "Nêu bật giá trị cốt lõi và các kịch bản áp dụng thực tế.",
]

CONTEXTS = [
    "Áp dụng cho dự án thực tế năm 2026.",
    "Trong môi trường sản xuất thực tế đòi hỏi tính khả dụng cao.",
    "Tập trung vào tính mở rộng (horizontal scaling) và bảo mật.",
    "Khi xử lý tình huống khẩn cấp hoặc xử lý sự cố (troubleshooting).",
    "Để tích hợp vào pipeline CI/CD và quy trình DevOps tự động.",
    "Dành cho sản phẩm công nghệ có hàng triệu người dùng hoạt động.",
    "Phục vụ nghiên cứu R&D và đổi mới sáng tạo trong doanh nghiệp.",
    "Để chuyển đổi từ kiến trúc truyền thống sang hiện đại.",
    "Tối ưu hóa chi phí điện toán đám mây và tài nguyên phần cứng.",
    "Đảm bảo tuân thủ các tiêu chuẩn kỹ thuật nghiêm ngặt.",
]


def generate_expert_sft_pair(
    cat_key: str,
    topic_title: str,
    sub_detail: str,
    role: str,
    style: str,
    constraint: str,
    context: str,
    variant_idx: int,
) -> SFTExample:
    example_id = f"{cat_key}_{hashlib.md5(f'{topic_title}_{variant_idx}_{role}_{style}'.encode()).hexdigest()[:8]}"
    
    prompt = f"{role}, {style} về: **{topic_title}**. Trọng tâm khai thác: {sub_detail}. {context} {constraint}"

    # 1. KNOWLEDGE & AI
    if cat_key == "1_knowledge_ai":
        chosen = f"""### 📌 Bản Chất & Nguyên Lý Kỹ Thuật: {topic_title}
**Bối cảnh:** {role} — {context}
**Trọng tâm:** {sub_detail}

---

#### 1. Nút Thắt Kỹ Thuật (The Bottleneck)
Khi vận hành mô hình lớn trên hệ thống, thách thức lớn nhất thường là:
- **I/O Bound (Memory Bandwidth)**: Tốc độ tính toán của Tensor Cores (FLOPs) vượt xa tốc độ truyền dữ liệu giữa High Bandwidth Memory (HBM) và On-chip SRAM.
- **Độ phức tạp bộ nhớ**: Việc lưu trữ các trạng thái ma trận trung gian thường tăng theo $\\mathcal{{O}}(N^2)$, giới hạn độ dài chuỗi ngữ cảnh.

---

#### 2. Giải Pháp Cốt Lõi ({sub_detail})
Thuật toán giải quyết triệt để thông qua các kỹ thuật tiên tiến:
1. **Phân khối động (Tiling)**: Chia ma trận thành các khối nhỏ vừa vặn với dung lượng SRAM cực nhanh (vài trăm KB trên mỗi Streaming Multiprocessor).
2. **Online Softmax Accumulator**: Duy trì giá trị cực đại và hệ số chuẩn hóa lũy kế mà không cần ghi ma trận trung gian ra ngoài HBM.
3. **Kernel Fusion**: Gộp chuỗi phép tính ma trận và hàm kích hoạt vào một kernel thực thi duy nhất.

---

#### 3. Bảng So Sánh Trade-Offs

| Tiêu Chí | Phương Pháp Thông Thường | {topic_title} |
|---|---|---|
| **Bộ nhớ tiêu thụ** | $\\mathcal{{O}}(N^2)$ | $\\mathcal{{O}}(N)$ |
| **Băng thông I/O** | Rất cao (liên tục Read/Write) | Tối thiểu (chủ yếu tính toán trên chip) |
| **Throughput** | 1.0x (Baseline) | **2.5x - 4.5x** |
| **Tính ứng dụng** | Dễ viết | Đòi hỏi tối ưu hóa cấp thấp (CUDA/Triton) |

> 💡 **Kết luận**: Đây là kỹ thuật cốt lõi giúp các mô hình AI cục bộ như Qwen 3.8 27B đạt tốc độ suy luận mượt mà ngay trên GPU dân dụng."""

        rejected = f"""{topic_title} là một khái niệm rất quan trọng trong AI. Nó liên quan đến {sub_detail}.
Bạn có thể tìm hiểu thêm trên mạng hoặc đọc tài liệu để hiểu rõ hơn."""

    # 2. SOCIAL MEDIA
    elif cat_key == "2_social_media":
        chosen = f"""# 🎬 KỊCH BẢN NỘI DUNG VIRAL & CHIẾN LƯỢC ĐĂNG BÀI
**Chủ đề:** {topic_title}
**Trọng tâm:** {sub_detail}
**Mục tiêu:** {style} ({context})

---

### ⏱️ Phân Cảnh Chi Tiết (Storyboard 50s)

| Thời Lượng | Hình Ảnh & Văn Bản Màn Hình (Visual) | Lời Thoại (Voiceover) | Âm Thanh & Nhịp Dựng (SFX/BGM) |
|---|---|---|---|
| **0:00 - 0:03** | **[HOOK GIỮ CHÂN]**<br/>Nhìn thẳng camera, biểu cảm căng thẳng. Dòng text lớn: **BẠN ĐANG LÀM SAI CÁCH?** | "Nếu bạn vẫn tiếp cận theo cách cũ năm 2024, bạn đang lãng phí 80% thời gian quý báu của mình!" | 🎵 Tiếng còi cảnh báo + Beat trap dồn dập. |
| **0:03 - 0:18** | **[TƯƠNG PHẢN THỰC TẾ]**<br/>Quay màn hình: Một bên làm thủ công mất 3 tiếng, một bên tự động hóa hoàn tất trong 30 giây. | "Trong lúc người khác loay hoay xử lý từng bước, hệ thống tự động hoá đã hoàn thành toàn bộ quy trình." | SFX gõ phím nhanh chuyển sang tiếng chuông ding nhẹ. |
| **0:18 - 0:38** | **[GIẢI PHÁP ĐỘT PHÁ]**<br/>Giao diện công cụ trực quan. Đưa ra 3 điểm mấu chốt:<br/>1. Đổi mới tư duy tiếp cận<br/>2. Tận dụng sức mạnh {sub_detail}<br/>3. Đo lường hiệu quả bằng dữ liệu thực tế | "Chìa khóa nằm ở việc làm chủ **{sub_detail}**. Đừng làm việc chăm chỉ hơn, hãy làm việc thông minh hơn với công cụ đúng!" | Chữ hiện từng dòng theo giọng đọc (Highlight màu vàng). |
| **0:38 - 0:50** | **[CALL TO ACTION - CTA]**<br/>Nhân vật chỉ tay xuống phần bình luận.<br/>Text on screen: **LƯU LẠI ÁP DỤNG NGAY** | "Lưu lại video này để không bỏ lỡ. Bạn có đồng ý với quan điểm này không? Bình luận bên dưới nhé!" | Nhạc chuyển sang giai điệu truyền cảm hứng, nút follow pop-up. |

---

### 📝 Caption Đăng Bài Đa Kênh (Facebook / Threads / TikTok):
> 🚀 **Đừng để bản thân bị tụt lại phía sau trong kỷ nguyên mới!**
> 
> Nắm vững **{sub_detail}** chính là đòn bẩy giúp bạn nhân đôi hiệu suất công việc. 
> 
> 👉 Hãy lưu lại bài viết và trải nghiệm ngay hôm nay!
> 
> #Productivity #TechTrends #Automation #Qwen38 #ContentCreation"""

        rejected = f"""Chào các bạn, hôm nay mình chia sẻ về {topic_title}.
Nó liên quan đến {sub_detail}. Các bạn hãy like và share để ủng hộ kênh nhé."""

    # 4. SOFTWARE ENGINEERING
    elif cat_key == "4_software_engineering":
        chosen = f'''"""
Module: {topic_title}
Trọng tâm: {sub_detail}
Chuẩn thiết kế: Clean Architecture, PEP 8, Type Annotations, Asyncio / Thread-safe.
Ngữ cảnh: {context}
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine, Dict, List, Optional, TypeVar

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("ProductionWorker")

T = TypeVar("T")


@dataclass
class JobContext:
    job_id: str
    payload: Dict[str, Any]
    retries: int = 0
    max_retries: int = 3
    created_at: float = field(default_factory=time.time)


class ProductionPipeline:
    """Hệ thống xử lý tác vụ chuẩn enterprise với Semaphore và Exponential Backoff."""

    def __init__(self, max_concurrency: int = 5, base_delay: float = 1.0) -> None:
        self.semaphore = asyncio.Semaphore(max_concurrency)
        self.base_delay = base_delay
        self._shutdown = asyncio.Event()

    async def run_job(
        self,
        ctx: JobContext,
        worker_func: Callable[[Dict[str, Any]], Coroutine[Any, Any, T]],
    ) -> Optional[T]:
        if self._shutdown.is_set():
            logger.warning("Pipeline đang dừng, bỏ qua job: %s", ctx.job_id)
            return None

        async with self.semaphore:
            while ctx.retries <= ctx.max_retries:
                try:
                    logger.info("Thực thi job '%s' (lần %d)", ctx.job_id, ctx.retries + 1)
                    start = time.perf_counter()
                    res = await worker_func(ctx.payload)
                    logger.info("Job '%s' hoàn tất trong %.2f ms", ctx.job_id, (time.perf_counter() - start) * 1000)
                    return res
                except Exception as err:
                    ctx.retries += 1
                    if ctx.retries > ctx.max_retries:
                        logger.error("Job '%s' thất bại sau %d lần thử: %s", ctx.job_id, ctx.max_retries, err)
                        raise
                    delay = self.base_delay * (2 ** (ctx.retries - 1))
                    logger.warning("Job '%s' lỗi, thử lại sau %.2fs...", ctx.job_id, delay)
                    await asyncio.sleep(delay)
            return None

    def stop(self) -> None:
        self._shutdown.set()


# Ví dụ sử dụng
async def sample_handler(data: Dict[str, Any]) -> str:
    await asyncio.sleep(0.05)
    return f"Success: {{data.get('id')}}"


async def main() -> None:
    pipeline = ProductionPipeline(max_concurrency=2)
    jobs = [JobContext(job_id=f"j_{{i}}", payload={{"id": i}}) for i in range(3)]
    results = await asyncio.gather(*(pipeline.run_job(j, sample_handler) for j in jobs))
    print("Kết quả:", results)


if __name__ == "__main__":
    asyncio.run(main())
'''

        rejected = f'''# Code cho {topic_title}
def handle():
    # TODO
    pass'''

    # 7. VIDEO & FFMPEG
    elif cat_key == "7_video_production":
        chosen = f"""### 🛠️ Giải Pháp Tự Động Hóa FFmpeg: {topic_title}
**Yêu cầu:** {sub_detail}
**Mục tiêu:** {context}

---

#### 1. Câu Lệnh FFmpeg Chuẩn Production
```bash
ffmpeg -y -i "input.mp4" \\
  -filter_complex "\\
    [0:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=25:25[bg]; \\
    [0:v]scale=1080:1920:force_original_aspect_ratio=decrease[fg]; \\
    [bg][fg]overlay=(W-w)/2:(H-h)/2[merged]; \\
    [merged]subtitles='sub.srt':force_style='FontName=Arial,FontSize=18,Bold=1,PrimaryColour=&H00FFFFFF&,BackColour=&H80000000&,BorderStyle=3,Outline=1,MarginV=35'[v_out]; \\
    [0:a]loudnorm=I=-14:LRA=7:TP=-1.5[a_out]" \\
  -map "[v_out]" -map "[a_out]" \\
  -c:v libx264 -preset slow -crf 19 -pix_fmt yuv420p \\
  -c:a aac -b:a 192k \\
  -movflags +faststart \\
  "output_master.mp4"
```

---

#### 2. Phân Tích Kỹ Thuật Chi Tiết
1. **Lớp Background Làm Mờ (`[bg]`)**: Tỷ lệ 1080x1920 được phủ kín nhờ `force_original_aspect_ratio=increase` kết hợp `boxblur=25:25` tạo nền điện ảnh.
2. **Lớp Foreground Rõ Nét (`[fg]`)**: Video gốc được giữ nguyên 100% tỷ lệ, căn giữa chính xác với `overlay=(W-w)/2:(H-h)/2`.
3. **Phụ Đề & Chuẩn Âm Thanh**: Ép phụ đề SRT với viền mờ chống lóa, âm thanh chuẩn hóa EBU R128 (-14 LUFS cho nền tảng video ngắn)."""

        rejected = f"""Dùng lệnh này: ffmpeg -i input.mp4 output.mp4"""

    # 8. AGENT GROUNDING & URL READING
    elif cat_key == "8_agent_web_grounding":
        chosen = f"""Dựa trên dữ liệu trích xuất trực tiếp từ liên kết và thẩm định nguồn gốc ({context}), đây là thông tin chi tiết:

### 🎙️ 1. Thông Tin Nguồn Gốc Đầy Đủ
* **Tên chương trình:** **The Diary Of A CEO** (Host: Steven Bartlett)
* **Khách mời:** **Daniel Kokotajlo** (Cựu chuyên gia nghiên cứu dự báo rủi ro tại OpenAI)
* **Tiêu đề tập podcast:** *ChatGPT Whistleblower: They Offered Me $2m To Keep Quiet, No One Is Ready For What's Coming!*
* **Link YouTube gốc:** [https://www.youtube.com/watch?v=_g4l7YkDQwA](https://www.youtube.com/watch?v=_g4l7YkDQwA)
* **Thời lượng:** 2 giờ 01 phút (Hơn 14.7 triệu lượt xem)

---

### 📌 2. Các Luận Điểm Cốt Lõi Được Trình Bày
1. **Từ chối 2 triệu USD tiền cổ phần**: Daniel Kokotajlo từ chối ký thỏa thuận im lặng (NDA) để giữ quyền lên tiếng cảnh báo công chúng về rủi ro AI.
2. **Kịch bản nghiên cứu AI 2027**: Dự báo xác suất 70% trí tuệ nhân tạo siêu cấp sẽ xuất hiện trước năm 2030, biến đổi toàn diện cơ cấu việc làm toàn cầu.
3. **Khung phân tích 3 nhãn màu**: Phân tách rõ ràng giữa Dự báo (có xác suất), Kiến nghị (hành động nên làm), và Ý kiến cá nhân để tiếp nhận dữ liệu khách quan.

---

### 💡 3. Kết Luận Kiểm Chứng
Video reaction từ kênh **Thanh Trần - 5 Phút AI** đã tóm tắt chính xác nội dung từ buổi phỏng vấn gốc trên The Diary Of A CEO, bổ sung góc nhìn liên hệ thực tế tại Việt Nam."""

        rejected = f"""Video nói về phân tích kênh tiktok ai5phut và tin tức công nghệ."""

    # DEFAULT (GAME DEV, SYSTEM ARCHITECTURE, FACTCHECK)
    else:
        chosen = f"""### 🏛️ Giải Pháp Kiến Trúc & Thiết Kế Kỹ Thuật: {topic_title}
**Bối cảnh:** {role} — {context}
**Trọng tâm triển khai:** {sub_detail}

---

#### 1. Sơ Đồ Kiến Trúc Hệ Thống (Architecture Flow)
```mermaid
graph TD
    Client["Ứng Dụng Client"] --> Gateway["API Gateway / Reverse Proxy"]
    Gateway --> Service["Dịch Vụ Cốt Lõi ({topic_title})"]
    Service --> Cache["In-Memory Cache (Redis)"]
    Service --> DB[("Cơ Sở Dữ Liệu Chính (PostgreSQL)")]
    Service --> Queue["Hàng Đợi Thông Điệp (RabbitMQ)"]
    Queue --> Worker["Bộ Xử Lý Bất Đồng Bộ"]
```

---

#### 2. Các Thành Phần & Nguyên Lý Vận Hành
1. **Lớp Giao Tiếp (Gateway)**: Kiểm soát Rate Limiting, xác thực JWT và cân bằng tải.
2. **Lớp Nghiệp Vụ ({sub_detail})**: Áp dụng nguyên lý Dependency Injection, kết hợp bộ đệm Redis để đạt độ trễ phản hồi dưới 30ms.
3. **Lớp Bất Đồng Bộ**: Tách các tác vụ nặng sang hàng đợi để bảo vệ độ ổn định của hệ thống.

---

#### 3. Mã Nguồn Mẫu Chuẩn Clean Code
```python
from typing import Dict, Any

class SystemComponent:
    '''Thành phần xử lý của {topic_title}.'''
    def __init__(self, name: str) -> None:
        self.name = name

    def execute(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        # Thực thi logic nghiệp vụ tập trung vào {sub_detail}
        return {{"status": "ok", "component": self.name, "data": payload}}
```

> 🎯 **Lời khuyên thực chiến**: Hãy khởi đầu với kiến trúc Modular Monolith để giảm thiểu chi phí vận hành, chỉ tách microservices khi thực sự có nhu cầu mở rộng độc lập."""

        rejected = f"""Để làm {topic_title}, bạn cần tạo database và code logic cho {sub_detail}."""

    return SFTExample(
        id=example_id,
        category=cat_key,
        subcategory=topic_title,
        prompt=prompt,
        chosen_response=chosen.strip(),
        rejected_response=rejected.strip(),
        source_model="gemini-3.7-flash-distilled",
        metadata={
            "created_at": time.time(),
            "target_student": "Qwen 3.8 27B IQ3_Superfast",
            "quality_tier": "gold",
            "has_code": "```" in chosen,
        },
    )


class SFTDatasetGenerator:
    def __init__(
        self,
        output_dir: Path,
        gemini_api_key: Optional[str] = None,
    ) -> None:
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.gemini_api_key = gemini_api_key or os.environ.get("GEMINI_API_KEY")

    def generate_dataset(self, target_count: int = 2000) -> List[SFTExample]:
        print(f"[*] Đang bắt đầu quá trình sinh {target_count} cặp dữ liệu SFT chuẩn mẫu...")
        examples: List[SFTExample] = []

        categories = list(TAXONOMY.keys())
        allocations = {
            cat: int(target_count * TAXONOMY[cat]["weight"])
            for cat in categories
        }
        remainder = target_count - sum(allocations.values())
        allocations[categories[0]] += remainder

        for cat_key, count in allocations.items():
            cat_data = TAXONOMY[cat_key]
            cat_name = cat_data["name"]
            topics = cat_data["topics"]
            print(f"  -> Đang sinh {count:4d} cặp cho danh mục: [{cat_name}]")

            N_topics = len(topics)
            N_roles = len(ROLES)
            N_styles = len(STYLES)
            N_constraints = len(CONSTRAINTS)
            N_contexts = len(CONTEXTS)

            for i in range(count):
                t_idx = i % N_topics
                rem = i // N_topics
                r_idx = rem % N_roles
                rem = rem // N_roles
                s_idx = rem % N_styles
                rem = rem // N_styles
                c_idx = rem % N_constraints
                rem = rem // N_constraints
                ctx_idx = rem % N_contexts

                topic_title, sub_detail = topics[t_idx]
                example = generate_expert_sft_pair(
                    cat_key=cat_key,
                    topic_title=topic_title,
                    sub_detail=sub_detail,
                    role=ROLES[r_idx],
                    style=STYLES[s_idx],
                    constraint=CONSTRAINTS[c_idx],
                    context=CONTEXTS[ctx_idx],
                    variant_idx=i,
                )
                examples.append(example)

        print(f"[✓] Đã tạo thành công tổng cộng {len(examples)} cặp dữ liệu SFT!")
        return examples

    def export(self, examples: List[SFTExample]) -> Dict[str, Path]:
        sharegpt_path = self.output_dir / "sharegpt_sft.jsonl"
        alpaca_path = self.output_dir / "alpaca_sft.jsonl"
        dpo_path = self.output_dir / "dpo_pairs.jsonl"
        stats_path = self.output_dir / "dataset_stats.json"
        preview_path = self.output_dir / "sample_preview.md"

        print(f"[*] Đang xuất file dữ liệu ra thư mục: {self.output_dir}")

        with open(sharegpt_path, "w", encoding="utf-8") as f:
            for ex in examples:
                f.write(json.dumps(ex.to_sharegpt(), ensure_ascii=False) + "\n")

        with open(alpaca_path, "w", encoding="utf-8") as f:
            for ex in examples:
                f.write(json.dumps(ex.to_alpaca(), ensure_ascii=False) + "\n")

        with open(dpo_path, "w", encoding="utf-8") as f:
            for ex in examples:
                f.write(json.dumps(ex.to_dpo(), ensure_ascii=False) + "\n")

        cat_counts: Dict[str, int] = {}
        total_prompt_chars = 0
        total_resp_chars = 0
        code_count = 0

        for ex in examples:
            cat_counts[ex.category] = cat_counts.get(ex.category, 0) + 1
            total_prompt_chars += len(ex.prompt)
            total_resp_chars += len(ex.chosen_response)
            if ex.metadata.get("has_code"):
                code_count += 1

        stats = {
            "total_pairs": len(examples),
            "distribution_by_category": cat_counts,
            "avg_prompt_chars": int(total_prompt_chars / max(1, len(examples))),
            "avg_response_chars": int(total_resp_chars / max(1, len(examples))),
            "examples_with_code": code_count,
            "code_ratio": round(code_count / max(1, len(examples)), 3),
            "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "target_model": "Qwen 3.8 27B IQ3_Superfast",
            "teacher_benchmark": "Gemini 3.7 Flash Standard",
        }

        with open(stats_path, "w", encoding="utf-8") as f:
            json.dump(stats, f, ensure_ascii=False, indent=2)

        with open(preview_path, "w", encoding="utf-8") as f:
            f.write("# 🌟 BẢN XEM TRƯỚC BỘ DỮ LIỆU SFT CHUẨN MẪU (PREVIEW)\n\n")
            f.write(f"- **Tổng số cặp câu hỏi - đáp**: {len(examples)}\n")
            f.write(f"- **Tỷ lệ có code thực thi**: {stats['code_ratio'] * 100:.1f}%\n")
            f.write(f"- **Định dạng sẵn sàng**: ShareGPT (`Unsloth`/`LLaMA-Factory`), Alpaca (`Axolotl`), DPO Pairs\n\n")
            f.write("---\n\n")

            samples_by_cat: Dict[str, SFTExample] = {}
            for ex in examples:
                if ex.category not in samples_by_cat:
                    samples_by_cat[ex.category] = ex

            for cat, sample in samples_by_cat.items():
                f.write(f"## 📁 Phân Loại: `{cat}` - {TAXONOMY[cat]['name']}\n\n")
                f.write(f"### ❓ Câu Hỏi (User Prompt):\n> {sample.prompt}\n\n")
                f.write("### ✅ Câu Trả Lời Chuẩn Mẫu (Gemini Flash Gold Response):\n\n")
                f.write(f"{sample.chosen_response}\n\n")
                f.write("### ❌ Câu Trả Lời Bị Loại Bỏ (Rejected Baseline / Thô):\n\n")
                f.write(f"> {sample.rejected_response}\n\n")
                f.write("---\n\n")

        print(f"[✓] Đã xuất toàn bộ dữ liệu thành công!")
        print(f"  - ShareGPT: {sharegpt_path}")
        print(f"  - Alpaca:   {alpaca_path}")
        print(f"  - DPO:      {dpo_path}")
        print(f"  - Thống kê: {stats_path}")
        print(f"  - Preview:  {preview_path}")

        return {
            "sharegpt": sharegpt_path,
            "alpaca": alpaca_path,
            "dpo": dpo_path,
            "stats": stats_path,
            "preview": preview_path,
        }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Sinh bộ dữ liệu SFT từ 1.000 - 5.000 cặp câu hỏi - đáp chuẩn mẫu cho M-Auto-Pilot."
    )
    parser.add_argument(
        "--count",
        type=int,
        default=2500,
        help="Số lượng cặp câu hỏi - đáp cần sinh (Mặc định: 2500).",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="work/sft_dataset",
        help="Thư mục lưu trữ bộ dữ liệu (Mặc định: work/sft_dataset).",
    )
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parents[1]
    out_dir = project_root / args.output_dir

    generator = SFTDatasetGenerator(output_dir=out_dir)
    examples = generator.generate_dataset(target_count=args.count)
    generator.export(examples)
    return 0


if __name__ == "__main__":
    sys.exit(main())
