#!/bin/bash
# ╔══════════════════════════════════════════════════════╗
# ║         JENIX Agent Installer v2.0                  ║
# ║  Usage: curl -sSL http://SERVER:8000/install.sh |   ║
# ║         bash -s -- --server http://SERVER:8000       ║
# ╚══════════════════════════════════════════════════════╝
set -e

JENIX_SERVER="http://localhost:8000"
AGENT_DIR="/opt/jenix-agent"
SERVICE_NAME="jenix-agent"

# ── Parse arguments ────────────────────────────────────────────────────────
while [[ "$#" -gt 0 ]]; do
    case $1 in
        --server) JENIX_SERVER="$2"; shift ;;
        --dir)    AGENT_DIR="$2";    shift ;;
        *) echo "Unknown arg: $1"; exit 1 ;;
    esac
    shift
done

echo ""
echo "╔══════════════════════════════════════════════╗"
echo "║        JENIX Agent Installer v2.0            ║"
echo "╚══════════════════════════════════════════════╝"
echo ""
echo "  Server : $JENIX_SERVER"
echo "  Install: $AGENT_DIR"
echo ""

# ── Check server reachable ─────────────────────────────────────────────────
echo "[1/6] Checking server connection..."
if ! curl -sf "$JENIX_SERVER/health" > /dev/null; then
    echo "❌ Cannot reach JENIX server at $JENIX_SERVER"
    echo "   Make sure the server is running and accessible."
    exit 1
fi
echo "      ✅ Server reachable"

# ── Detect distro + install Python ────────────────────────────────────────
echo "[2/6] Installing dependencies..."
if command -v apt-get &>/dev/null; then
    sudo apt-get update -qq
    sudo apt-get install -y -qq python3 python3-pip curl
elif command -v yum &>/dev/null; then
    sudo yum install -y python3 python3-pip curl -q
elif command -v dnf &>/dev/null; then
    sudo dnf install -y python3 python3-pip curl -q
else
    echo "⚠️  Unknown package manager. Please install Python 3 manually."
fi

# Install Python packages
pip3 install psutil websockets --break-system-packages -q 2>/dev/null || \
pip3 install psutil websockets -q
echo "      ✅ Dependencies installed"

# ── Create agent directory ─────────────────────────────────────────────────
echo "[3/6] Creating agent directory..."
sudo mkdir -p "$AGENT_DIR"
sudo chown "$USER:$USER" "$AGENT_DIR"
echo "      ✅ Directory: $AGENT_DIR"

# ── Download agent files ───────────────────────────────────────────────────
echo "[4/6] Downloading agent files..."
curl -sSL "$JENIX_SERVER/static/agent.py"     -o "$AGENT_DIR/agent.py"
curl -sSL "$JENIX_SERVER/static/collector.py" -o "$AGENT_DIR/collector.py"
curl -sSL "$JENIX_SERVER/static/executor.py"  -o "$AGENT_DIR/executor.py"
echo "JENIX_SERVER=$JENIX_SERVER" > "$AGENT_DIR/.env"
echo "      ✅ Agent files downloaded"

# ── Create systemd service ─────────────────────────────────────────────────
echo "[5/6] Creating systemd service..."
sudo tee /etc/systemd/system/$SERVICE_NAME.service > /dev/null << SVCEOF
[Unit]
Description=JENIX Agent — Linux Infrastructure Management
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$AGENT_DIR
Environment=JENIX_SERVER=$JENIX_SERVER
ExecStart=/usr/bin/python3 $AGENT_DIR/agent.py
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
SVCEOF

sudo systemctl daemon-reload
sudo systemctl enable $SERVICE_NAME
sudo systemctl start  $SERVICE_NAME
echo "      ✅ Service installed and started"

# ── Verify ─────────────────────────────────────────────────────────────────
echo "[6/6] Verifying installation..."
sleep 3
if sudo systemctl is-active --quiet $SERVICE_NAME; then
    echo "      ✅ Agent is running"
else
    echo "      ⚠️  Agent may have failed to start"
    echo "         Check: sudo journalctl -u $SERVICE_NAME -n 20"
fi

echo ""
echo "╔══════════════════════════════════════════════╗"
echo "║        ✅ JENIX Agent Installed!             ║"
echo "╚══════════════════════════════════════════════╝"
echo ""
echo "  Status : sudo systemctl status $SERVICE_NAME"
echo "  Logs   : sudo journalctl -u $SERVICE_NAME -f"
echo "  Stop   : sudo systemctl stop $SERVICE_NAME"
echo "  Remove : sudo systemctl disable $SERVICE_NAME"
echo ""
echo "  This machine should appear in your JENIX"
echo "  dashboard within 30 seconds."
echo ""
