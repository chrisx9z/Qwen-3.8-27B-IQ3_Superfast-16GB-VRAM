#!/usr/bin/env bash
# ==============================================================================
# Auto Pilot Qwen 3.8 27B IQ3_Superfast - macOS Setup & Launcher Script
# Optimized for Apple Silicon (M1/M2/M3/M4) Metal Acceleration & Intel Mac
# ==============================================================================

set -e

echo "🍎 Setting up Auto Pilot Qwen 3.8 27B IQ3_Superfast for macOS..."

# 1. Check Homebrew
if ! command -v brew &> /dev/null; then
    echo "⚠️ Homebrew not found. Please install Homebrew from https://brew.sh/"
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

# 3. Create Python Virtual Environment
if [ ! -d ".venv" ]; then
    echo "🐍 Creating Python virtual environment..."
    python3 -m venv .venv
fi

source .venv/bin/activate

# 4. Install Dependencies
echo "📦 Installing Python dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

# 5. Launch Auto Pilot GUI
echo "🚀 Starting Auto Pilot Qwen 3.8 27B IQ3_Superfast..."
python scripts/run_auto_pilot_gui.py
