# Qwen 3.8 27B IQ3_Superfast 16GB VRAM 🚀

**Qwen 3.8 27B IQ3_Superfast 16GB VRAM** is an autonomous, fully local AI Assistant, Coding Agent, and Computer Use automation system. Powered by the high-speed **Qwen3.8-27B-UD-IQ3_S** model via `llama.cpp` (or any OpenAI-compatible endpoint), it provides high-performance local intelligence (~50.4 tokens/s on 16GB GPUs) without relying on cloud APIs.

---

## 🌟 Key Features & Innovations

1. **283 Comprehensive Automation Tools**:
   - **Computer Use & Windows Native**: Human-like Bézier mouse movements, Unicode SendInput typing, window hierarchy control (HWND), and background Virtual Desktops.
   - **Chrome CDP Automation**: Direct Chrome DevTools Protocol interaction, multi-tab coordination, instant userscript/extension injection (`inject_chrome_userscript_extension`), DOM mutation, and network idle observation.
   - **AI Vision OCR & Screen Grounding**: Pixel-accurate bounding box prediction on High-DPI/2K/4K displays, OCR text search & click, and semantic form auto-filling.
   - **Safety Sandbox Firewall**: Real-time action intent audit (`enforce_computer_action_safety_firewall`), preventing destructive OS actions.

2. **Dynamic Semantic Tool Router**:
   - Dynamically loads only 6–22 relevant tool schemas (~790–2,000 tokens) based on user intent.
   - Eliminates context window overflow errors and leaves 6,000+ tokens for deep reasoning (Chain-of-Thought).

3. **Multi-Language Support (i18n)**:
   - **Default UI Language**: English (`en`).
   - **Supported Languages**: English (`en`), Vietnamese (`vi`), Simplified Chinese (`zh`).
   - Instant language switching via the UI header bar.
   - **Intelligent Multi-lingual Response**: Automatically detects query language and responds in the exact same language.

4. **Refined & Responsive UI**:
   - Auto-resizing message bubbles with zero internal scrollbars.
   - Auto-collapsing reasoning blocks and execution terminal cards.
   - Built-in studio dialogs: `AllToolsCatalogDialog` (`/tools`), `ComputerUseStudioDialog`, `ComputerSafetyStudioDialog`, `ComputerMissionStudioDialog`.

---

## 🚀 Quick Start

### 1. Requirements
- Python 3.10+
- PySide6, requests, psutil, rapidocr_onnxruntime, playwright, pywinauto
- `llama-server` (or any OpenAI-compatible server at `http://127.0.0.1:8080/v1/chat/completions`)

### 2. Run from Source:
```powershell
# Install dependencies
pip install -r requirements.txt

# Start Auto Pilot GUI
python scripts/run_auto_pilot_gui.py
```

### 3. Run Pre-built Executable:
Launch `Auto Pilot Qwen 3.8 27B IQ3_Superfast.exe`. Use **`Alt + Shift + M`** to show/hide the window globally.

### 4. Run Automated Verification Tests:
```powershell
python scripts/test_local_agent.py
```

---

## 📦 Build Standalone Windows EXE

```powershell
python -m PyInstaller "M Auto Pilot.spec" --noconfirm
```

Output binary will be located at `dist/Auto Pilot Qwen 3.8 27B IQ3_Superfast.exe`.
