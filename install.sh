#!/bin/bash
set -e

echo "╔══════════════════════════════════════════╗"
echo "║     JENIX Enterprise — Safe Installer    ║"
echo "╚══════════════════════════════════════════╝"
echo ""

JENIX_DIR="$HOME/jenix-server"
BACKUP_DIR="$HOME/jenix-backups/$(date +%Y%m%d_%H%M%S)"

# ── Step 1: Backup existing data ─────────────────────────────────────────────
if [ -d "$JENIX_DIR" ]; then
    echo "[1/6] Backing up existing data..."
    mkdir -p "$BACKUP_DIR"
    [ -f "$JENIX_DIR/server/jenix.db" ] && cp "$JENIX_DIR/server/jenix.db" "$BACKUP_DIR/"
    [ -f "$JENIX_DIR/server/static/index.html" ] && cp "$JENIX_DIR/server/static/index.html" "$BACKUP_DIR/"
    echo "      Backup saved to: $BACKUP_DIR"
else
    echo "[1/6] Fresh install — no existing data to backup"
    mkdir -p "$JENIX_DIR"
fi

# ── Step 2: Check dependencies ────────────────────────────────────────────────
echo "[2/6] Checking dependencies..."
command -v python3 &>/dev/null || { echo "ERROR: Python3 required"; exit 1; }
command -v git &>/dev/null || { echo "ERROR: Git required"; exit 1; }
echo "      Python3: $(python3 --version)"
echo "      Git: $(git --version)"

# ── Step 3: Clone/update repo ─────────────────────────────────────────────────
echo "[3/6] Getting latest JENIX code..."
if [ -d "$JENIX_DIR/.git" ]; then
    cd "$JENIX_DIR"
    git pull origin main
    echo "      Updated to latest version"
else
    git clone https://github.com/Harrywells21/Jenix-Enterprise.git "$JENIX_DIR"
    cd "$JENIX_DIR"
    echo "      Cloned successfully"
fi

# ── Step 4: Setup Python environment ─────────────────────────────────────────
echo "[4/6] Setting up Python environment..."
cd "$JENIX_DIR"
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip --quiet
pip install fastapi uvicorn websockets psutil requests bcrypt python-jose sqlalchemy aiofiles python-multipart --quiet
echo "      Dependencies installed"

# ── Step 5: Restore user data ─────────────────────────────────────────────────
echo "[5/6] Checking for existing user data..."
if [ -f "$BACKUP_DIR/jenix.db" ]; then
    cp "$BACKUP_DIR/jenix.db" "$JENIX_DIR/server/jenix.db"
    echo "      ✓ User database restored — no data lost"
else
    echo "      ✓ Fresh database will be created on first run"
fi

# ── Step 6: Create start script ───────────────────────────────────────────────
echo "[6/6] Creating start script..."
cat > "$JENIX_DIR/start.sh" << 'STARTEOF'
#!/bin/bash
cd "$(dirname "$0")"
source venv/bin/activate
cd server
echo "Starting JENIX Enterprise..."
echo "Dashboard: http://localhost:8000"
echo "Press Ctrl+C to stop"
uvicorn app.main:app --host 0.0.0.0 --port 8000
STARTEOF
chmod +x "$JENIX_DIR/start.sh"

echo ""
echo "╔══════════════════════════════════════════╗"
echo "║   ✅ JENIX Enterprise Ready!             ║"
echo "║                                          ║"
echo "║   To start:  bash ~/jenix-server/start.sh║"
echo "║   Dashboard: http://localhost:8000        ║"
echo "║   Default login: admin / admin123         ║"
echo "║                                          ║"
echo "║   ⚠ Change password after first login!   ║"
echo "╚══════════════════════════════════════════╝"
echo ""
