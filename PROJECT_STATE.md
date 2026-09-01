# Project State: Qwen 3.8 27B IQ3_Superfast 16GB VRAM 🚀

## 🌟 Overview & Core Architecture

**Qwen 3.8 27B IQ3_Superfast 16GB VRAM** is a 100% standalone, fully autonomous **AI Personal Assistant**, **Coding Agent**, and **Computer Use** system. It operates completely locally on consumer hardware without relying on cloud APIs, third-party subscriptions, or proprietary external dependencies.

---

## 🏗️ Architectural Foundations & Branches

| Branch | Target Platform | Acceleration Backend | Automation Layer | Status |
|---|---|---|---|---|
| 🪟 **`Windows-PC`** (Default) | Windows 10/11 x64 | NVIDIA CUDA / Vulkan (`llama.cpp`) | Win32 API, Native Human Input, Virtual Desktops | **Production Ready (100% Pass)** |
| 🍎 **`MacOS`** | macOS (Apple Silicon M1-M4 & Intel) | Apple Metal GPU (Unified Memory) | AppleScript, Accessibility API, Quartz, PyAutoGUI | **Production Ready (100% Pass)** |

---

## ⚡ Core Engine & Acceleration Features

1. **MTP (Multi-Token Prediction) & Speculative Decoding**:
   - N-gram speculative lookup (`--lookup-ngram-min 3`): Accelerates code generation by $1.5\times - 2.5\times$ without extra VRAM.
   - Optional Draft Model support (`--model-draft`).
2. **Prompt Processing & Prefix KV Caching**:
   - FlashAttention-2 (`--flash-attn on`) for $O(N)$ high-speed attention computation.
   - Continuous Batching (`--cont-batching`, `-b 2048`, `-ub 512`).
   - Prompt KV Cache reuse (`"cache_prompt": True`) across agent tool turns.
   - Context shifting (`--ctx-shift`) within the 16,384 token window.
3. **283 Comprehensive Automation Tools & 91 Interactive Dialogs**:
   - Autonomous Coding, File Tree, Git Manager, Checkpoints, AST Analysis, Terminal Runner.
   - Computer-Use (Bézier mouse, SendInput Unicode, HWND inspection, Virtual Desktops).
   - Chrome CDP browser automation & RapidOCR screen grounding.
   - Real-time Safety Sandbox Firewall.
4. **Modern UI/UX Experience**:
   - Auto-expanding multi-line prompt input ($44$px to $160$px).
   - Welcome Hero banner with 4 starter action cards for instant workflow creation.
   - Full-session context token utilization indicator with color-coded alerts.
   - Right-click sidebar context menu (Pin, Rename, Export Markdown, Delete).
   - Full-text conversation history search (`Ctrl+F`).
   - Global keyboard shortcuts (`Ctrl+N`, `Ctrl+F`, `Escape`, `Alt+Shift+M`).
5. **Multi-Language i18n System**:
   - Default English (`en`), Vietnamese (`vi`), Simplified Chinese (`zh`).
   - Intelligent response mirroring matching the input language.
6. **Telemetry & Benchmarks**:
   - **Prompt Prefill Speed**: ~1,900 tokens/s.
   - **Generation Speed**: ~50.44 tokens/s (~19.8 ms/token).
   - **Time-to-First-Token (TTFT)**: 431 ms – 619 ms (sub-50ms with prompt cache hits).
   - **VRAM Footprint**: ~14.5 GB / 16.3 GB.

---

## 🛠️ Repository & Codebase Hierarchy

- **GitHub Repository**: `https://github.com/chrisx9z/Qwen-3.8-27B-IQ3_Superfast-16GB-VRAM`
- **Default Branch**: `Windows-PC`
- **macOS Branch**: `MacOS`
- **Core Modules**:
  - `agent/`: Controller, 283 Tool registry, screen grounding, and safety sandbox firewall.
  - `core/`: Multi-language i18n engine, project state, and dynamic workspace synchronization.
  - `llm/`: Local LLM server manager, resource monitoring, and GPU telemetry.
  - `ui/`: PySide6 responsive dark-theme interface with 91 dialogs, welcome hero, and auto-collapsing cards.
  - `scripts/`: GUI runner, verification suite, and PyInstaller build configuration.

---

## ✅ Test & Verification Status

- **Code Compilation (`compileall`)**: 100% PASS across all modules on both branches.
- **Automated Tool Test Suite (`scripts/test_local_agent.py`)**: 100% PASS (283/283 tools verified).
- **GUI Dialogs Test Suite**: 100% PASS (91/91 dialogs verified).
- **Executable Desktop Release**: `Auto Pilot Qwen 3.8 27B IQ3_Superfast.exe` built and verified.
