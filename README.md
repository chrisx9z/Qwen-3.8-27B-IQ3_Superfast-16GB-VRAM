# Qwen 3.8 27B IQ3_Superfast (macOS Edition) 🍎🚀

**Qwen 3.8 27B IQ3_Superfast** is an autonomous, local AI Assistant, Coding Agent, and Computer Use automation system — optimized for **macOS (Apple Silicon M1/M2/M3/M4 Metal Acceleration & Intel Mac)**.

---

## 🌟 macOS Highlights & Capabilities

- ⚡ **Apple Silicon Metal GPU Acceleration**: Harnesses Unified Memory on Apple M1/M2/M3/M4 chips via `llama.cpp` Metal backend for near-zero latency.
- 🎛️ **283 Automation Tools**: Includes macOS UI Automation (AppleScript, Accessibility API, Quartz), Chrome CDP automation, Vision OCR, and System Safety Firewall.
- 🌐 **Multi-Language System (i18n)**: English (Default), Tiếng Việt, 简体中文.
- ⌨️ **Global Shortcut**: **`Cmd + Shift + M`** or **`Ctrl + Shift + M`** to show/hide the assistant instantly from anywhere on macOS.

---

## 🚀 1-Click Setup & Launch on macOS

### Option A: Using the 1-Click Setup Script
```bash
# Clone the repository
git clone -b MacOS https://github.com/chrisx9z/Qwen-3.8-27B-IQ3_Superfast-16GB-VRAM.git
cd Qwen-3.8-27B-IQ3_Superfast-16GB-VRAM

# Make setup script executable and run
chmod +x setup_macos.sh
./setup_macos.sh
```

### Option B: Manual Setup via Homebrew & Python

```bash
# 1. Install llama.cpp with Apple Metal support
brew install llama.cpp

# 2. Setup Python environment
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 3. Start Auto Pilot GUI
python scripts/run_auto_pilot_gui.py
```

---

## 🧠 Model Configuration on macOS

Place your `Qwen3.8-27B-UD-IQ3_S.gguf` model in any of the following standard paths:
- `~/models/Qwen3.8-27B-UD-IQ3_S.gguf`
- `~/.auto_pilot/models/Qwen3.8-27B-UD-IQ3_S.gguf`
- `./models/Qwen3.8-27B-UD-IQ3_S.gguf`

Start `llama-server` manually if desired:
```bash
llama-server -m ~/models/Qwen3.8-27B-UD-IQ3_S.gguf --port 8080 -ngl 99 -c 16384 --flash-attn on
```
