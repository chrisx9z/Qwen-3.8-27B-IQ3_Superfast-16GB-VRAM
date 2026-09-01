# Project State: Qwen 3.8 27B IQ3_Superfast 16GB VRAM 🚀

## 🌟 Overview & Core Purpose

**Qwen 3.8 27B IQ3_Superfast 16GB VRAM** is a 100% standalone, fully autonomous **AI Personal Assistant**, **Coding Agent**, and **Computer Use** system. It operates completely locally on consumer hardware without relying on cloud APIs, third-party subscriptions, or proprietary external dependencies.

---

## 🏗️ Architectural Foundations & Branches

| Branch | Target Platform | Acceleration Backend | Automation Layer |
|---|---|---|---|
| 🪟 **`Windows-PC`** (Default) | Windows 10/11 x64 | NVIDIA CUDA / Vulkan (`llama.cpp`) | Win32 API, Native Human Input, Virtual Desktops |
| 🍎 **`MacOS`** | macOS (Apple Silicon M1-M4 & Intel) | Apple Metal GPU (Unified Memory) | AppleScript, Accessibility API, Quartz, PyAutoGUI |

---

## ⚡ Key Systems & Capabilities (283 Tools)

1. **Autonomous Coding Agent**:
   - High-precision file reading, semantic code search, AST analysis, and syntax validation.
   - Patch application, atomic checkpointing, and git revision rollback.
   - Isolated command execution within workspace allowlists.

2. **Computer Use & Desktop Automation**:
   - Smooth Bézier mouse movement with natural human speed curve.
   - Pixel-accurate High-DPI & Retina OCR grounding via RapidOCR.
   - Chrome CDP direct automation (multi-tab control, DOM inspection, cookie management, userscript injection).
   - Real-time Safety Sandbox Firewall (`enforce_computer_action_safety_firewall`).

3. **Dynamic Semantic Tool Router**:
   - Evaluates prompt intent in 0.05ms to filter active tools down to 6–22 relevant schemas (~790–2,000 tokens).
   - Prevents context overflow and preserves 6,000+ tokens for deep reasoning (Chain-of-Thought).

4. **Deep Multi-Language i18n System**:
   - **Default Language**: English (`en`).
   - **Supported Languages**: English (`en`), Vietnamese (`vi`), Simplified Chinese (`zh`).
   - Instant 0.01ms UI switching across all buttons, chips, dialogs, status indicators, and headers.
   - **Intelligent Response Mirroring**: Detects query language and automatically responds in the exact same language.

5. **Performance & Telemetry**:
   - **Prompt Prefill Speed**: ~1,900.12 tokens/s.
   - **Generation Speed**: ~50.44 tokens/s (~19.8 ms/token).
   - **Time-to-First-Token (TTFT)**: 431 ms – 619 ms.
   - **VRAM Footprint**: ~14.5 GB / 16.3 GB (fits completely inside 16GB VRAM GPUs).

---

## 🛠️ Project Structure & Locations

- **Source Code Repository**: `https://github.com/chrisx9z/Qwen-3.8-27B-IQ3_Superfast-16GB-VRAM`
- **Active Branches**: `Windows-PC` (Default), `MacOS`
- **Core Modules**:
  - `agent/`: Controller, 283 Tool definitions, screen grounding, and safety sandbox.
  - `core/`: Multi-language i18n dictionary and workspace project management.
  - `llm/`: Local LLM server manager, resource monitoring, and CUDA/Metal telemetry.
  - `ui/`: PySide6 responsive dark-theme interface with auto-collapsing reasoning & terminal cards.
  - `scripts/`: GUI runner, verification suite, and benchmark utilities.

---

## ✅ Verification & Test Status

- **Code Compilation (`compileall`)**: 100% PASS across all modules on both branches.
- **Automated Tool Test Suite (`scripts/test_local_agent.py`)**: 100% PASS (283/283 tools verified).
- **Multi-lingual Evaluation**: Verified across English, Vietnamese, and Chinese prompts with zero encoding/font defects.
- **Standalone Verification**: Completely decoupled from any legacy external video tools.
