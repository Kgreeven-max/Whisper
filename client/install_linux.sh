#!/bin/bash
# Meeting Transcriber - Linux Installation Script

set -e

echo "============================================================"
echo "Meeting Transcriber - Linux Installation"
echo "============================================================"
echo ""

# Detect distribution
if [ -f /etc/os-release ]; then
    . /etc/os-release
    DISTRO=$ID
else
    DISTRO="unknown"
fi

echo "Detected distribution: $DISTRO"
echo ""

# Check Python
if ! command -v python3 &> /dev/null; then
    echo "ERROR: Python 3 not found!"
    echo "Install with: sudo apt install python3 python3-pip (Ubuntu/Debian)"
    echo "Or: sudo dnf install python3 python3-pip (Fedora)"
    exit 1
fi

echo "Python version:"
python3 --version
echo ""

# Install system dependencies
echo "Installing system dependencies..."

case $DISTRO in
    ubuntu|debian)
        sudo apt update
        sudo apt install -y \
            python3-dev \
            python3-pip \
            python3-venv \
            portaudio19-dev \
            xdotool \
            libcairo2-dev \
            libgirepository1.0-dev \
            gir1.2-gtk-3.0
        ;;
    fedora|rhel|centos)
        sudo dnf install -y \
            python3-devel \
            python3-pip \
            portaudio-devel \
            xdotool \
            cairo-devel \
            gobject-introspection-devel \
            gtk3
        ;;
    arch|manjaro)
        sudo pacman -S --noconfirm \
            python-pip \
            portaudio \
            xdotool \
            cairo \
            gobject-introspection \
            gtk3
        ;;
    *)
        echo "Warning: Unknown distribution. Some dependencies may be missing."
        echo "Please install portaudio, xdotool, cairo, and GTK3 manually."
        read -p "Continue anyway? (y/n) " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            exit 1
        fi
        ;;
esac

# Create virtual environment
echo "Creating virtual environment..."
python3 -m venv venv
source venv/bin/activate

# Upgrade pip
pip install --upgrade pip

# Install Python requirements
echo "Installing Python dependencies..."
pip install -r requirements.txt

# Install Linux-specific packages
echo "Installing Linux-specific packages..."
pip install python-xlib

echo ""
echo "============================================================"
echo "Installation Complete!"
echo "============================================================"
echo ""
echo "To run the meeting monitor:"
echo "  source venv/bin/activate"
echo "  python3 meeting_monitor.py"
echo ""
echo "The app will appear in your system tray."
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
echo "  Run: ./setup_autostart_linux.sh"
echo ""
