# JENIX Agent Installation Guide
Built by Aaditya Singh - aadisingh0121@gmail.com

## Method 1 - One-Line Installer (Recommended)

    curl -sSL http://YOUR_SERVER:8000/install.sh | bash -s -- --server http://YOUR_SERVER:8000

Replace YOUR_SERVER with your JENIX server IP or hostname.

## Method 2 - Manual Installation

Step 1 - Install Python dependencies
    pip3 install psutil websockets --break-system-packages

Step 2 - Create agent directory
    sudo mkdir -p /opt/jenix-agent
    sudo chown $USER:$USER /opt/jenix-agent

Step 3 - Download agent files
    SERVER=http://YOUR_SERVER:8000
    curl -sSL $SERVER/static/agent.py     -o /opt/jenix-agent/agent.py
    curl -sSL $SERVER/static/collector.py -o /opt/jenix-agent/collector.py
    curl -sSL $SERVER/static/executor.py  -o /opt/jenix-agent/executor.py

Step 4 - Run agent manually to test
    cd /opt/jenix-agent
    JENIX_SERVER=http://YOUR_SERVER:8000 python3 agent.py

You should see:
    [agent] Registering with server...
    [agent] Registered - machine_id=1
    [agent] Connected

Step 5 - Install as systemd service
    sudo systemctl enable jenix-agent
    sudo systemctl start jenix-agent

## Troubleshooting

Cannot reach server:
    curl http://YOUR_SERVER:8000/health
    sudo ufw allow 8000

Remove agent:
    sudo systemctl stop jenix-agent
    sudo systemctl disable jenix-agent
    sudo rm /etc/systemd/system/jenix-agent.service
    sudo rm -rf /opt/jenix-agent
    rm -rf ~/.jenix

## Supported OS
- Ubuntu 20.04+
- Linux Mint 21+
- Debian 11+
- CentOS 8+
- Fedora 36+
- Raspberry Pi OS
