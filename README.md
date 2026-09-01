# Qwen 3.8 27B IQ3_Superfast 16GB VRAM 🚀

**Qwen 3.8 27B IQ3_Superfast 16GB VRAM** is a 100% standalone, fully autonomous **AI Personal Assistant**, **Coding Agent**, and **Computer Use** system. Powered by the high-speed **Qwen3.8-27B-UD-IQ3_S** model via `llama.cpp` (or any OpenAI-compatible server), it delivers cloud-grade intelligence locally on consumer GPUs (12–16GB VRAM) at ~50.4 tokens/s generation speed with zero cloud API dependencies.

---

## 🌟 Key Innovations & Architecture

### 1. ⚡ MTP (Multi-Token Prediction) & Prompt Processing Acceleration
- **FlashAttention-2 (`--flash-attn on`)**: Computes attention $2\times - 3\times$ faster during prompt evaluation while reducing KV cache VRAM footprint by up to $40\%$.
- **Prompt KV Cache Reuse (`"cache_prompt": True`)**: Reuses prefix KV cache across multi-turn agent loops, eliminating redundant prompt recalculations and dropping Time-to-First-Token (TTFT) to milliseconds.
- **Continuous Batching & Token Slots (`--cont-batching`, `-b 2048`, `-ub 512`)**: High-throughput parallel prompt ingestion on GPU Tensor/CUDA Cores.
- **N-gram Speculative Lookup Decoding (`--lookup-ngram-min 3`)**: Multi-token speculative decoding that accelerates code generation and structured outputs by $1.5\times - 2.5\times$ without consuming extra VRAM.
- **Context Shifting (`--ctx-shift`)**: Smooth automatic slot rotation when approaching the 16,384 token context window.

### 2. 🛠️ 283 Comprehensive Automation Tools & 91 Interactive UI Dialogs
- **Autonomous Coding Agent**: File AST analysis, atomic diff patching, unit test runner (Pytest), automatic git commit/push, and rollback checkpoints.
- **Computer-Use & Desktop Control**: Human-like Bézier curve mouse physics, native Unicode SendInput, HWND window hierarchy inspection, and virtual desktop isolation.
- **Chrome CDP Automation**: Direct Chrome DevTools Protocol interaction, multi-tab coordination, instant extension/userscript injection, and network idle observation.
- **RapidOCR Screen Grounding**: Pixel-accurate text & element detection on High-DPI/Retina displays.
- **Safety Sandbox Firewall**: Real-time action audit (`enforce_computer_action_safety_firewall`), preventing accidental destructive OS operations.

### 3. 🎨 Modern, High-Performance UI/UX
- **Auto-Expanding Multi-line Input**: Compact $44$px single-line input that smoothly expands up to $160$px for long code snippets and paragraphs.
- **Welcome Hero & Starter Action Cards**: Interactive starter prompts for REST API building, code auditing, pytest testing, and computer automation.
- **Real-time Context Token Counter**: Displays total session context utilization against the 16,384 token limit with dynamic color alerts.
- **Sidebar History & Context Menus**: Fast full-text search (`Ctrl+F`), Pin/Unpin, Rename, Export Markdown, and Delete with right-click menu.
- **Global Shortcuts**: `Ctrl+N` (New Chat), `Ctrl+F` (Search), `Escape` (Stop generation), and `Alt+Shift+M` (Global show/hide).

### 4. 🌐 Deep Multi-Language Support (i18n)
- **Default Language**: English (`en`).
- **Supported Languages**: English (`en`), Vietnamese (`vi`), Simplified Chinese (`zh`).
- **Intelligent Response Mirroring**: Detects query language and automatically answers in the exact same language.

---

## 🏗️ Platform & Branch Overview

| Branch | Target OS | Acceleration Backend | Automation Layer |
|---|---|---|---|
| 🪟 **`Windows-PC`** (Default) | Windows 10 / 11 x64 | NVIDIA CUDA / Vulkan (`llama.cpp`) | Win32 API, Native Human Input, Virtual Desktops |
| 🍎 **`MacOS`** | macOS (Apple Silicon M1–M4 & Intel) | Apple Metal GPU (Unified Memory) | AppleScript, Accessibility API, Quartz, PyAutoGUI |

---

## 🚀 Quick Start

### 1. Requirements
- Python 3.10+
- PySide6, requests, psutil, rapidocr_onnxruntime, playwright, pywinauto
- `llama-server` (or OpenAI-compatible endpoint at `http://127.0.0.1:8080/v1/chat/completions`)
- Model: `Qwen3.8-27B-UD-IQ3_S.gguf` (11.2 GB)

### 2. Run from Source:
```powershell
# Install dependencies
pip install -r requirements.txt

# Start Auto Pilot GUI
python scripts/run_auto_pilot_gui.py
```

### 3. Run Pre-built Desktop Executable:
Double click **`Auto Pilot Qwen 3.8 27B IQ3_Superfast.exe`** on Desktop.

### 4. Run Automated Verification Tests:
```powershell
python scripts/test_local_agent.py
```

---

## 📦 Build Standalone Desktop Executable

```powershell
python -m PyInstaller "M Auto Pilot.spec" --noconfirm
```

Output binary will be located at `dist/Auto Pilot Qwen 3.8 27B IQ3_Superfast.exe`.

---

## 🔗 Repository Links

- **GitHub Repository**: [Qwen-3.8-27B-IQ3_Superfast-16GB-VRAM](https://github.com/chrisx9z/Qwen-3.8-27B-IQ3_Superfast-16GB-VRAM)
- **Windows-PC Branch**: [Windows-PC](https://github.com/chrisx9z/Qwen-3.8-27B-IQ3_Superfast-16GB-VRAM/tree/Windows-PC)
- **MacOS Branch**: [MacOS](https://github.com/chrisx9z/Qwen-3.8-27B-IQ3_Superfast-16GB-VRAM/tree/MacOS)
