#!/usr/bin/env bash
# ==============================================================================
# Auto Pilot Qwen 3.8 27B IQ3_Superfast - macOS Setup & Launcher Script
# Optimized for Apple Silicon (M1/M2/M3/M4) Metal Acceleration & Intel Mac
# ==============================================================================

set -e

echo "🍎 ========================================================"
echo "🍎  Auto Pilot Qwen 3.8 27B IQ3_Superfast (macOS Edition)"
echo "🍎 ========================================================"

# Detect Architecture
ARCH=$(uname -m)
if [ "$ARCH" = "arm64" ]; then
    echo "⚡ Detected Apple Silicon ($ARCH) - Metal GPU acceleration enabled!"
    BREW_PREFIX="/opt/homebrew"
else
    echo "⚡ Detected Intel Mac ($ARCH)"
    BREW_PREFIX="/usr/local"
fi

# Ensure Homebrew is in PATH
if [ -f "$BREW_PREFIX/bin/brew" ]; then
    eval "$($BREW_PREFIX/bin/brew shellenv)"
fi

# 1. Check Homebrew
if ! command -v brew &> /dev/null; then
    echo "⚠️ Homebrew not found. Please install Homebrew from https://brew.sh/"
    echo "Run: /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)""
fi

# 2. Check llama.cpp with Metal support
if ! command -v llama-server &> /dev/null; then
    echo "📦 Installing llama.cpp with Apple Metal GPU acceleration..."
    if command -v brew &> /dev/null; then
        brew install llama.cpp
    else
        echo "Please install llama.cpp using Homebrew: brew install llama.cpp"
    fi
fi

# 3. Create Model Directory
MODELS_DIR="$HOME/.auto_pilot/models"
mkdir -p "$MODELS_DIR"
mkdir -p "./models"
echo "📁 Models directory ready: $MODELS_DIR (or ./models)"

# 4. Create Python Virtual Environment
if [ ! -d ".venv" ]; then
    echo "🐍 Creating Python virtual environment..."
    python3 -m venv .venv
fi

source .venv/bin/activate

# 5. Install Dependencies
echo "📦 Installing Python dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

# 6. Create macOS Double-Clickable Launcher
cat << 'EOF' > launch_macos.command
#!/usr/bin/env bash
cd "$(dirname "$0")"
source .venv/bin/activate
python scripts/run_auto_pilot_gui.py
EOF
chmod +x launch_macos.command

# 7. Launch Auto Pilot GUI
echo "🚀 Starting Auto Pilot Qwen 3.8 27B IQ3_Superfast..."
python scripts/run_auto_pilot_gui.py
