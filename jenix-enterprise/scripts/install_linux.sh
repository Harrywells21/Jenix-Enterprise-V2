#!/bin/bash
set -e
JENIX_SERVER="${JENIX_SERVER:-http://YOUR_SERVER_IP:8000}"
JENIX_API_KEY="${JENIX_API_KEY:-your_api_key_here}"
NODE_NAME="${NODE_NAME:-$(hostname)}"
INSTALL_DIR="/opt/jenix-agent"
CONFIG_DIR="/etc/jenix"

echo "=== JENIX Enterprise Agent Installer (Linux) ==="
echo "Server: $JENIX_SERVER"
echo "Node:   $NODE_NAME"

# Detect package manager
if command -v apt-get &>/dev/null; then
    PKG="apt-get install -y"
    apt-get update -qq
elif command -v yum &>/dev/null; then
    PKG="yum install -y"
elif command -v dnf &>/dev/null; then
    PKG="dnf install -y"
else
    echo "Unsupported package manager"; exit 1
fi

# Install Python if needed
if ! command -v python3 &>/dev/null; then
    $PKG python3 python3-pip
fi
if ! command -v pip3 &>/dev/null; then
    $PKG python3-pip
fi

# Install dependencies
pip3 install --quiet psutil websockets requests

# Create directories
mkdir -p "$INSTALL_DIR" "$CONFIG_DIR"

# Download agent
echo "Downloading agent..."
curl -fsSL "$JENIX_SERVER/agent/jenix_agent.py" -o "$INSTALL_DIR/jenix_agent.py" \
  -H "X-API-Key: $JENIX_API_KEY" || {
    echo "Download failed. Ensure JENIX server is reachable."
    exit 1
}

# Write config
NODE_ID=$(cat /proc/sys/kernel/random/uuid 2>/dev/null || python3 -c "import uuid; print(uuid.uuid4())")
cat > "$CONFIG_DIR/agent.conf" << CONF
{
  "server_url": "ws://$(echo $JENIX_SERVER | sed 's|http://||;s|https://||')",
  "node_id": "$NODE_ID",
  "node_name": "$NODE_NAME",
  "api_key": "$JENIX_API_KEY"
}
CONF

# Create systemd service
cat > /etc/systemd/system/jenix-agent.service << SERVICE
[Unit]
Description=JENIX Enterprise Agent
After=network.target
Wants=network-online.target

[Service]
Type=simple
ExecStart=/usr/bin/python3 $INSTALL_DIR/jenix_agent.py
Restart=always
RestartSec=10
Environment=PYTHONUNBUFFERED=1
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
SERVICE

systemctl daemon-reload
systemctl enable jenix-agent
systemctl start jenix-agent

echo ""
echo "=== JENIX Agent installed successfully! ==="
echo "Status: $(systemctl is-active jenix-agent)"
echo "Logs:   journalctl -u jenix-agent -f"
