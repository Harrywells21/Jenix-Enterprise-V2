#!/bin/bash
# JENIX Enterprise — Universal One-Line Installer
# Detects OS automatically and installs the right agent

set -e

GITHUB="https://github.com/Harrywells21/Jenix-Enterprise"
RELEASES="https://github.com/Harrywells21/Jenix-Enterprise/releases/download/v1.0.0"

echo ""
echo "╔══════════════════════════════════════════════╗"
echo "║     JENIX Enterprise — Universal Installer   ║"
echo "╚══════════════════════════════════════════════╝"
echo ""

# ── Detect OS ─────────────────────────────────────────────────────────────────
detect_os() {
    if [[ "$OSTYPE" == "linux-gnu"* ]]; then
        echo "linux"
    elif [[ "$OSTYPE" == "darwin"* ]]; then
        echo "macos"
    elif [[ "$OSTYPE" == "msys"* ]] || [[ "$OSTYPE" == "cygwin"* ]]; then
        echo "windows"
    elif grep -qi microsoft /proc/version 2>/dev/null; then
        echo "windows"
    else
        echo "unknown"
    fi
}

OS=$(detect_os)
echo "[1/5] Detected OS: $OS"

case $OS in
# ── Linux ─────────────────────────────────────────────────────────────────────
linux)
    echo "[2/5] Checking Python3..."
    if ! command -v python3 &>/dev/null; then
        echo "      Installing Python3..."
        sudo apt-get update -qq && sudo apt-get install -y python3 python3-pip 2>/dev/null || \
        sudo yum install -y python3 python3-pip 2>/dev/null || \
        sudo dnf install -y python3 python3-pip 2>/dev/null
    else
        echo "      Found: $(python3 --version)"
    fi

    echo "[3/5] Installing dependencies..."
    pip3 install websockets psutil requests --quiet --break-system-packages 2>/dev/null || \
    pip3 install websockets psutil requests --quiet

    echo "[4/5] Downloading JENIX Agent..."
    mkdir -p ~/.jenix
    curl -fsSL "$RELEASES/JenixAgent-linux" -o ~/.jenix/JenixAgent
    chmod +x ~/.jenix/JenixAgent

    echo "[5/5] Setting up auto-start..."
    # Create desktop shortcut
    mkdir -p ~/Desktop
    cat > ~/Desktop/JenixAgent.desktop << DESKTOP
[Desktop Entry]
Name=JENIX Agent
Comment=JENIX Enterprise Agent
Exec=$HOME/.jenix/JenixAgent
Icon=network-wired
Terminal=false
Type=Application
Categories=Network;Security;
DESKTOP
    chmod +x ~/Desktop/JenixAgent.desktop

    # Create systemd service for background running
    if command -v systemctl &>/dev/null; then
        cat > /tmp/jenix-agent.service << SERVICE
[Unit]
Description=JENIX Enterprise Agent
After=network-online.target

[Service]
ExecStart=$HOME/.jenix/JenixAgent
Restart=always
RestartSec=10
Environment=DISPLAY=:0

[Install]
WantedBy=multi-user.target
SERVICE
        sudo mv /tmp/jenix-agent.service /etc/systemd/system/
        sudo systemctl daemon-reload
        sudo systemctl enable jenix-agent --quiet 2>/dev/null || true
    fi

    echo ""
    echo "╔══════════════════════════════════════════════╗"
    echo "║   ✅ JENIX Agent Installed!                  ║"
    echo "║                                              ║"
    echo "║   • Desktop shortcut created                 ║"
    echo "║   • Double-click JenixAgent on Desktop       ║"
    echo "║   • App will auto-discover your JENIX server ║"
    echo "╚══════════════════════════════════════════════╝"
    echo ""

    # Launch GUI immediately
    read -p "Launch JENIX Agent now? [Y/n] " -n 1 -r
    echo ""
    if [[ ! $REPLY =~ ^[Nn]$ ]]; then
        ~/.jenix/JenixAgent &
        echo "✓ JENIX Agent launched!"
    fi
    ;;

# ── macOS ─────────────────────────────────────────────────────────────────────
macos)
    echo "[2/5] Checking Python3..."
    if ! command -v python3 &>/dev/null; then
        echo "      Python3 not found."
        echo "      Please install Python from https://python.org first"
        echo "      Then run this installer again."
        exit 1
    else
        echo "      Found: $(python3 --version)"
    fi

    echo "[3/5] Installing dependencies..."
    pip3 install websockets psutil requests --quiet 2>/dev/null || \
    pip install websockets psutil requests --quiet

    echo "[4/5] Downloading JENIX Agent..."
    mkdir -p ~/.jenix
    curl -fsSL "$RELEASES/JenixAgent-macos" -o ~/.jenix/JenixAgent 2>/dev/null || \
    curl -fsSL "$RELEASES/JenixAgent-linux" -o ~/.jenix/JenixAgent
    chmod +x ~/.jenix/JenixAgent

    echo "[5/5] Setting up auto-start..."
    # Create LaunchAgent
    mkdir -p ~/Library/LaunchAgents
    cat > ~/Library/LaunchAgents/com.jenix.agent.plist << PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key><string>com.jenix.agent</string>
    <key>ProgramArguments</key>
    <array><string>$HOME/.jenix/JenixAgent</string></array>
    <key>RunAtLoad</key><true/>
    <key>KeepAlive</key><true/>
</dict>
</plist>
PLIST
    launchctl unload ~/Library/LaunchAgents/com.jenix.agent.plist 2>/dev/null || true
    launchctl load ~/Library/LaunchAgents/com.jenix.agent.plist

    echo ""
    echo "╔══════════════════════════════════════════════╗"
    echo "║   ✅ JENIX Agent Installed!                  ║"
    echo "║                                              ║"
    echo "║   • Agent starts automatically on login      ║"
    echo "║   • App will auto-discover your JENIX server ║"
    echo "║   • Check ~/.jenix/ for logs                 ║"
    echo "╚══════════════════════════════════════════════╝"
    echo ""

    read -p "Launch JENIX Agent now? [Y/n] " -n 1 -r
    echo ""
    if [[ ! $REPLY =~ ^[Nn]$ ]]; then
        ~/.jenix/JenixAgent &
        echo "✓ JENIX Agent launched!"
    fi
    ;;

# ── Unknown ───────────────────────────────────────────────────────────────────
*)
    echo ""
    echo "⚠ Could not detect OS automatically."
    echo ""
    echo "Please download the agent manually from:"
    echo "  $GITHUB/releases"
    echo ""
    echo "Windows users: Run this in PowerShell (Admin):"
    echo "  iwr -useb http://YOUR_SERVER:8000/api/agent/install/windows | iex"
    ;;
esac
