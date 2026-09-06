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
    read -p "Server address [http://localhost:8000]: " SERVER_INPUT < /dev/tty
    JENIX_SERVER="${SERVER_INPUT:-http://localhost:8000}"
fi
echo "Using JENIX server: $JENIX_SERVER"
echo ""

if [ -n "$JENIX_SITE_ID" ]; then
    mkdir -p ~/.jenix
    echo "$JENIX_SITE_ID" > ~/.jenix/site_id
    echo "Site ID: $JENIX_SITE_ID (will be sent at registration)"
fi


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
    if ! curl -sf "$JENIX_SERVER/agent-binary/linux" -o ~/.jenix/JenixAgent; then
        echo "      ERROR: failed to download agent binary from $JENIX_SERVER/agent-binary/linux"
        echo "      Check that the JENIX server is reachable at that address."
        exit 1
    fi
    chmod +x ~/.jenix/JenixAgent
    echo "$JENIX_SERVER" > ~/.jenix/server_url

    echo "[4.5/5] Setting up scoped fleet-command helpers (boost/clean/fix)..."
    if command -v apt-get &>/dev/null; then
        sudo tee /usr/local/sbin/jenix-sysctl-restore > /dev/null << 'SYSCTLEOF'
#!/bin/bash
# JENIX scoped sysctl wrapper -- used by both boost and rollback.
# Usage: jenix-sysctl-restore <key> <value>
set -euo pipefail

ALLOWED_KEYS="vm.swappiness net.core.rmem_max"
key="${1:-}"
val="${2:-}"

if [ -z "$key" ] || [ -z "$val" ]; then
    echo "usage: jenix-sysctl-restore <key> <value>" >&2
    exit 2
fi

match=0
for k in $ALLOWED_KEYS; do
    [ "$k" = "$key" ] && match=1 && break
done
if [ "$match" -ne 1 ]; then
    echo "jenix-sysctl-restore: key not allowed: $key" >&2
    exit 3
fi

if ! [[ "$val" =~ ^[0-9]{1,10}$ ]]; then
    echo "jenix-sysctl-restore: value must be a plain non-negative integer: $val" >&2
    exit 4
fi

case "$key" in
    vm.swappiness)
        if [ "$val" -gt 100 ]; then
            echo "jenix-sysctl-restore: vm.swappiness out of bounds (0-100): $val" >&2
            exit 5
        fi
        ;;
    net.core.rmem_max)
        if [ "$val" -gt 1073741824 ]; then
            echo "jenix-sysctl-restore: net.core.rmem_max out of bounds (0-1GB): $val" >&2
            exit 5
        fi
        ;;
esac

exec /usr/sbin/sysctl -w "${key}=${val}"
SYSCTLEOF
        sudo chmod 755 /usr/local/sbin/jenix-sysctl-restore
        sudo chown root:root /usr/local/sbin/jenix-sysctl-restore

        sudo tee /usr/local/sbin/jenix-apt-reinstall > /dev/null << 'APTEOF'
#!/bin/bash
# JENIX scoped apt-get install wrapper -- used by rollback's package-reinstall step.
# Usage: jenix-apt-reinstall <pkg1> [pkg2 ...]
set -euo pipefail

if [ "$#" -eq 0 ]; then
    echo "usage: jenix-apt-reinstall <pkg> [pkg...]" >&2
    exit 2
fi
if [ "$#" -gt 50 ]; then
    echo "jenix-apt-reinstall: too many packages in one call (max 50): $#" >&2
    exit 6
fi

PKG_RE='^[a-z0-9][a-z0-9.+-]*$'
for pkg in "$@"; do
    if ! [[ "$pkg" =~ $PKG_RE ]]; then
        echo "jenix-apt-reinstall: rejected invalid package name: $pkg" >&2
        exit 3
    fi
done

exec /usr/bin/apt-get install -y "$@"
APTEOF
        sudo chmod 755 /usr/local/sbin/jenix-apt-reinstall
        sudo chown root:root /usr/local/sbin/jenix-apt-reinstall

        sudo tee /etc/sudoers.d/jenix-agent > /dev/null << SUDOEOF
$(whoami) ALL=(ALL) NOPASSWD: /usr/bin/apt-get autoremove -y
$(whoami) ALL=(ALL) NOPASSWD: /usr/bin/apt-get autoclean -y
$(whoami) ALL=(ALL) NOPASSWD: /usr/bin/journalctl --vacuum-time=7d
$(whoami) ALL=(ALL) NOPASSWD: /usr/bin/apt-get install -f -y
$(whoami) ALL=(ALL) NOPASSWD: /usr/bin/dpkg --configure -a
$(whoami) ALL=(ALL) NOPASSWD: /usr/local/sbin/jenix-sysctl-restore *
$(whoami) ALL=(ALL) NOPASSWD: /usr/local/sbin/jenix-apt-reinstall *
SUDOEOF
        sudo chmod 440 /etc/sudoers.d/jenix-agent
        sudo visudo -c -f /etc/sudoers.d/jenix-agent && echo "      sudoers syntax OK" || echo "      WARNING: sudoers syntax check failed, review before trusting this file"
        echo "      Scoped fleet-command helpers installed (boost/clean/fix now supported)"
    else
        echo "      No apt-get detected -- scoped helpers are Debian/Ubuntu-specific, skipping."
        echo "      boost/clean/fix will report 'not supported on this system' rather than failing silently."
    fi

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
User=$(whoami)
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
    echo "║   • Connected to: $JENIX_SERVER"
    echo "╚══════════════════════════════════════════════╝"
    echo ""

    # Launch GUI immediately
    read -p "Launch JENIX Agent now? [Y/n] " -n 1 -r < /dev/tty
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
    if ! curl -sf "$JENIX_SERVER/agent-binary/macos" -o ~/.jenix/JenixAgent; then
        echo "      macOS binary not available on server, falling back to Linux binary..."
        if ! curl -sf "$JENIX_SERVER/agent-binary/linux" -o ~/.jenix/JenixAgent; then
            echo "      ERROR: failed to download agent binary from $JENIX_SERVER"
            exit 1
        fi
    fi
    chmod +x ~/.jenix/JenixAgent
    echo "$JENIX_SERVER" > ~/.jenix/server_url

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

    read -p "Launch JENIX Agent now? [Y/n] " -n 1 -r < /dev/tty
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
