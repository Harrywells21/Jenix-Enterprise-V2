#!/bin/bash
# JENIX Agent Installer
# Usage: curl -sSL http://YOUR_SERVER:8000/install | bash -s -- --server http://YOUR_SERVER:8000

set -e

JENIX_SERVER="http://localhost:8000"

# Parse args
while [[ "$#" -gt 0 ]]; do
    case $1 in
        --server) JENIX_SERVER="$2"; shift ;;
    esac
    shift
done

echo "╔══════════════════════════════════════╗"
echo "║   JENIX Agent Installer v1.0         ║"
echo "╚══════════════════════════════════════╝"
echo ""
echo "[*] Server: $JENIX_SERVER"
echo "[*] Installing dependencies..."

# Detect distro
if command -v apt-get &>/dev/null; then
    sudo apt-get update -qq
    sudo apt-get install -y -qq python3 python3-pip
elif command -v yum &>/dev/null; then
    sudo yum install -y python3 python3-pip -q
fi

# Install Python deps
pip3 install psutil websockets --break-system-packages -q 2>/dev/null || \
pip3 install psutil websockets -q

# Create agent directory
AGENT_DIR="/opt/jenix-agent"
sudo mkdir -p $AGENT_DIR
sudo chown $USER:$USER $AGENT_DIR

# Download agent files
echo "[*] Downloading agent..."
curl -sSL "$JENIX_SERVER/static/agent.py"     -o $AGENT_DIR/agent.py
curl -sSL "$JENIX_SERVER/static/collector.py" -o $AGENT_DIR/collector.py
curl -sSL "$JENIX_SERVER/static/executor.py"  -o $AGENT_DIR/executor.py

# Write env
echo "JENIX_SERVER=$JENIX_SERVER" > $AGENT_DIR/.env

# Create systemd service
sudo tee /etc/systemd/system/jenix-agent.service > /dev/null << SVCEOF
[Unit]
Description=JENIX Agent
After=network.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$AGENT_DIR
EnvironmentFile=$AGENT_DIR/.env
ExecStart=/usr/bin/python3 $AGENT_DIR/agent.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
SVCEOF

sudo systemctl daemon-reload
sudo systemctl enable jenix-agent
sudo systemctl start  jenix-agent

echo ""
echo "✅ JENIX Agent installed and running!"
echo "   Check status: sudo systemctl status jenix-agent"
echo "   View logs:    sudo journalctl -u jenix-agent -f"
