#!/bin/bash
set -e

echo "╔══════════════════════════════════════════╗"
echo "║     JENIX Enterprise — Server Installer  ║"
echo "╚══════════════════════════════════════════╝"
echo ""
echo "Run this script from inside the extracted JENIX package."
echo ""

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "[1/4] Checking dependencies..."
command -v python3 &>/dev/null || { echo "ERROR: Python3 required"; exit 1; }
echo "      Python3: $(python3 --version)"

echo "[2/4] Setting up Python environment..."
python3 -m venv server_venv
source server_venv/bin/activate
pip install --upgrade pip --quiet
pip install -r server/requirements.txt --quiet
echo "      Dependencies installed"

echo "[3/4] Checking configuration..."
if [ ! -f "server/.env" ]; then
    cp server/.env.example server/.env
    echo "      Created server/.env from template — edit it to set SECRET_KEY, SMTP, etc."
else
    echo "      server/.env already exists — leaving it as-is"
fi

echo "[4/4] Creating start script..."
cat > start.sh << 'STARTEOF'
#!/bin/bash
cd "$(dirname "$0")"
source server_venv/bin/activate
cd server
echo "Starting JENIX Enterprise..."
echo "Dashboard: http://localhost:8000/dashboard"
echo "Press Ctrl+C to stop"
uvicorn main:app --host 0.0.0.0 --port 8000
STARTEOF
chmod +x start.sh

echo ""
echo "╔══════════════════════════════════════════╗"
echo "║   JENIX Enterprise Ready                 ║"
echo "║                                          ║"
echo "║   To start:  ./start.sh                  ║"
echo "║   Dashboard: http://localhost:8000/dashboard ║"
echo "║   Default login: admin@jenix.io          ║"
echo "║             / admin123                   ║"
echo "║                                          ║"
echo "║   Change the admin password after first  ║"
echo "║   login, and edit server/.env before     ║"
echo "║   exposing this to a network.            ║"
echo "╚══════════════════════════════════════════╝"
echo ""
