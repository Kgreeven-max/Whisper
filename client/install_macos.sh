#!/bin/bash
# Meeting Transcriber - macOS Installation Script

set -e

echo "============================================================"
echo "Meeting Transcriber - macOS Installation"
echo "============================================================"
echo ""

# Check Python
if ! command -v python3 &> /dev/null; then
    echo "ERROR: Python 3 not found!"
    echo "Please install Python from https://www.python.org/"
    exit 1
fi

echo "Python version:"
python3 --version
echo ""

# Install Homebrew dependencies
echo "Checking Homebrew dependencies..."
if ! command -v brew &> /dev/null; then
    echo "Homebrew not found. Install from https://brew.sh/"
    echo "Or continue without Homebrew (may have limited functionality)"
    read -p "Continue? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
else
    echo "Installing portaudio..."
    brew install portaudio
fi

# Create virtual environment (recommended)
echo "Creating virtual environment..."
python3 -m venv venv
source venv/bin/activate

# Upgrade pip
pip install --upgrade pip

# Install requirements
echo "Installing Python dependencies..."
pip install -r requirements.txt

echo ""
echo "============================================================"
echo "Installation Complete!"
echo "============================================================"
echo ""
echo "To run the meeting monitor:"
echo "  source venv/bin/activate"
echo "  python3 meeting_monitor.py"
echo ""
echo "The app will appear in your menu bar."
echo ""
echo "Optional - Calendar Integration:"
echo "For Google Calendar:"
echo "  1. Place google_credentials.json in ~/.meeting-transcriber/"
echo "  2. Run: python3 calendar_integration.py google"
echo ""
echo "For Outlook/Teams Calendar:"
echo "  1. Set MS_CLIENT_ID environment variable"
echo "  2. Run: python3 calendar_integration.py outlook"
echo ""
echo "For automatic startup:"
echo "  Run: ./setup_autostart_macos.sh"
echo ""
