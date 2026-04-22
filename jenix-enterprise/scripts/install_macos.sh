#!/bin/bash
set -e
JENIX_SERVER="${JENIX_SERVER:-http://YOUR_SERVER_IP:8000}"
JENIX_API_KEY="${JENIX_API_KEY:-your_api_key_here}"
NODE_NAME="${NODE_NAME:-$(hostname)}"
INSTALL_DIR="/opt/jenix-agent"
CONFIG_DIR="/etc/jenix"
PLIST_PATH="/Library/LaunchDaemons/com.jenix.agent.plist"

echo "=== JENIX Enterprise Agent Installer (macOS) ==="
echo "Server: $JENIX_SERVER"
echo "Node:   $NODE_NAME"

# Check for Homebrew (optional, for pip)
if ! command -v pip3 &>/dev/null; then
    if command -v brew &>/dev/null; then
        brew install python3
    else
        echo "Installing pip via ensurepip..."
        python3 -m ensurepip --upgrade
    fi
fi

# Install Python dependencies
pip3 install --quiet psutil websockets requests

# Create directories (needs sudo)
sudo mkdir -p "$INSTALL_DIR" "$CONFIG_DIR"

# Download agent
echo "Downloading agent..."
sudo curl -fsSL "$JENIX_SERVER/agent/jenix_agent.py" \
  -H "X-API-Key: $JENIX_API_KEY" \
  -o "$INSTALL_DIR/jenix_agent.py" || {
    echo "Download failed. Ensure JENIX server is reachable."; exit 1
}

# Write config
NODE_ID=$(python3 -c "import uuid; print(uuid.uuid4())")
sudo bash -c "cat > $CONFIG_DIR/agent.conf" << CONF
{
  "server_url": "ws://$(echo $JENIX_SERVER | sed 's|http://||;s|https://||')",
  "node_id": "$NODE_ID",
  "node_name": "$NODE_NAME",
  "api_key": "$JENIX_API_KEY"
}
CONF

# Create LaunchDaemon plist
sudo tee "$PLIST_PATH" > /dev/null << PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>com.jenix.agent</string>
  <key>ProgramArguments</key>
  <array>
    <string>/usr/bin/python3</string>
    <string>$INSTALL_DIR/jenix_agent.py</string>
  </array>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
  <key>StandardOutPath</key>
  <string>/var/log/jenix-agent.log</string>
  <key>StandardErrorPath</key>
  <string>/var/log/jenix-agent-error.log</string>
  <key>ThrottleInterval</key>
  <integer>10</integer>
</dict>
</plist>
PLIST

sudo launchctl load "$PLIST_PATH"

echo ""
echo "=== JENIX Agent installed successfully! ==="
echo "Logs:  tail -f /var/log/jenix-agent.log"
echo "Stop:  sudo launchctl unload $PLIST_PATH"
