#!/bin/bash
# JENIX Enterprise — Universal One-Line Installer
# Detects OS automatically and installs the right agent

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo ""
echo "╔══════════════════════════════════════════════╗"
echo "║     JENIX Enterprise — Universal Installer   ║"
echo "╚══════════════════════════════════════════════╝"
echo ""

# ── Ask for the JENIX server address ────────────────────────────────────────
# The agent has no auto-discovery — it must be told where the server is.
if [ -z "$JENIX_SERVER" ]; then
    echo "Where is your JENIX Enterprise server running?"
    echo "  (e.g. http://192.168.1.10:8000 or https://jenix.yourcompany.com)"
    read -p "Server address [http://localhost:8000]: " SERVER_INPUT
    JENIX_SERVER="${SERVER_INPUT:-http://localhost:8000}"
fi
echo "Using JENIX server: $JENIX_SERVER"
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

    echo "[4/5] Installing JENIX Agent..."
    mkdir -p ~/.jenix
    cp "$SCRIPT_DIR/releases/JenixAgent-linux" ~/.jenix/JenixAgent
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
Environment=JENIX_SERVER=$JENIX_SERVER

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
    echo "║   • Connected to: $JENIX_SERVER"
    echo "╚══════════════════════════════════════════════╝"
    echo ""

    # Launch GUI immediately
    read -p "Launch JENIX Agent now? [Y/n] " -n 1 -r
    echo ""
    if [[ ! $REPLY =~ ^[Nn]$ ]]; then
        JENIX_SERVER="$JENIX_SERVER" ~/.jenix/JenixAgent &
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

    echo "[4/5] Installing JENIX Agent..."
    mkdir -p ~/.jenix
    if [ -f "$SCRIPT_DIR/releases/JenixAgent-macos" ]; then
        cp "$SCRIPT_DIR/releases/JenixAgent-macos" ~/.jenix/JenixAgent
    else
        cp "$SCRIPT_DIR/releases/JenixAgent-linux" ~/.jenix/JenixAgent
    fi
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
    <key>EnvironmentVariables</key>
    <dict>
        <key>JENIX_SERVER</key><string>$JENIX_SERVER</string>
    </dict>
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
    echo "║   • Connected to: $JENIX_SERVER"
    echo "║   • Check ~/.jenix/ for logs                 ║"
    echo "╚══════════════════════════════════════════════╝"
    echo ""

    read -p "Launch JENIX Agent now? [Y/n] " -n 1 -r
    echo ""
    if [[ ! $REPLY =~ ^[Nn]$ ]]; then
        JENIX_SERVER="$JENIX_SERVER" ~/.jenix/JenixAgent &
        echo "✓ JENIX Agent launched!"
    fi
    ;;

# ── Unknown ───────────────────────────────────────────────────────────────────
*)
    echo ""
    echo "⚠ Could not detect OS automatically."
    echo ""
    echo "Please run the agent manually from the releases/ folder"
    echo "included in this package, or contact support."
    echo ""
    echo "Windows users: Run this in PowerShell (Admin):"
    echo "  iwr -useb http://YOUR_SERVER:8000/api/agent/install/windows | iex"
    ;;
esac
