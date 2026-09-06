#!/bin/bash
set -e
TS=$(date +%Y%m%d_%H%M%S)
SERVER_DIR=~/Desktop/jenix/server
AGENT_DIR=~/Desktop/jenix/agent
REPO_ROOT=~/Desktop/jenix

echo "=================================================================="
echo "PART A — BACKUPS"
echo "=================================================================="
cp "$SERVER_DIR/db.py"              "$SERVER_DIR/db.py.bak_sites_${TS}"
cp "$SERVER_DIR/main.py"            "$SERVER_DIR/main.py.bak_sites_${TS}"
cp "$SERVER_DIR/routes/agents.py"   "$SERVER_DIR/routes/agents.py.bak_sites_${TS}"
cp "$AGENT_DIR/agent.py"            "$AGENT_DIR/agent.py.bak_sites_${TS}"
cp "$REPO_ROOT/install_jenix.sh"    "$REPO_ROOT/install_jenix.sh.bak_sites_${TS}"
echo "Backed up 5 files with suffix _sites_${TS}"

echo ""
echo "=================================================================="
echo "PART B — PATCH db.py (Site model + machines.site_id migration)"
echo "=================================================================="
python3 - << 'PYEOF'
path = "/home/aadi/Desktop/jenix/server/db.py"
src = open(path).read()

# 1. Insert Site model before class Metric(Base):
anchor1 = "class Metric(Base):"
assert src.count(anchor1) == 1, f"anchor1 matched {src.count(anchor1)} times, expected 1"
site_model = '''class Site(Base):
    __tablename__ = "sites"
    id         = Column(Integer, primary_key=True, index=True)
    name       = Column(String, unique=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


'''
src = src.replace(anchor1, site_model + anchor1, 1)

# 2. Add site_id column to Machine model
anchor2 = '    redirect_target_url    = Column(String, nullable=True)  # set by approve-with-redirect; agent told to reconnect elsewhere, then this row is deleted\n'
assert src.count(anchor2) == 1, f"anchor2 matched {src.count(anchor2)} times, expected 1"
new2 = anchor2 + '    site_id     = Column(Integer, nullable=True)  # optional Site grouping, no enforced FK (matches redirect_target_url convention)\n'
src = src.replace(anchor2, new2, 1)

# 3. Add site_id migration to _migrate_schema()
anchor3 = '''        if "last_risk_at" not in cols:
            conn.exec_driver_sql("ALTER TABLE machines ADD COLUMN last_risk_at DATETIME")
            conn.commit()
            print("✅ Migrated: added machines.last_risk_at")

        audit_cols = [row[1] for row in conn.exec_driver_sql("PRAGMA table_info(audit_logs)").fetchall()]'''
assert src.count(anchor3) == 1, f"anchor3 matched {src.count(anchor3)} times, expected 1"
new3 = '''        if "last_risk_at" not in cols:
            conn.exec_driver_sql("ALTER TABLE machines ADD COLUMN last_risk_at DATETIME")
            conn.commit()
            print("✅ Migrated: added machines.last_risk_at")
        if "site_id" not in cols:
            conn.exec_driver_sql("ALTER TABLE machines ADD COLUMN site_id INTEGER")
            conn.commit()
            print("✅ Migrated: added machines.site_id")

        audit_cols = [row[1] for row in conn.exec_driver_sql("PRAGMA table_info(audit_logs)").fetchall()]'''
src = src.replace(anchor3, new3, 1)

open(path, "w").write(src)
print("db.py patched: Site model + site_id column + migration all applied (3/3 anchors matched exactly once)")
PYEOF

echo ""
echo "--- re-verify db.py anchors landed exactly once ---"
grep -c "class Site(Base):" "$SERVER_DIR/db.py"
grep -c "site_id     = Column(Integer, nullable=True)" "$SERVER_DIR/db.py"
grep -c "Migrated: added machines.site_id" "$SERVER_DIR/db.py"

echo ""
echo "=================================================================="
echo "PART C — CREATE routes/sites.py (new file)"
echo "=================================================================="
cat > "$SERVER_DIR/routes/sites.py" << 'SITESEOF'
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from db import get_db, Site, Machine
from auth import get_current_user, require_admin, User

router = APIRouter(prefix="/sites", tags=["sites"])

class SiteCreate(BaseModel):
    name: str

@router.get("")
def list_sites(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    sites = db.query(Site).order_by(Site.name).all()
    result = []
    for s in sites:
        count = db.query(Machine).filter(Machine.site_id == s.id).count()
        result.append({"id": s.id, "name": s.name, "machine_count": count})
    return result

@router.post("")
def create_site(body: SiteCreate, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    existing = db.query(Site).filter(Site.name == body.name).first()
    if existing:
        raise HTTPException(status_code=400, detail="A site with this name already exists")
    site = Site(name=body.name)
    db.add(site); db.commit(); db.refresh(site)
    return {"id": site.id, "name": site.name}

@router.delete("/{site_id}")
def delete_site(site_id: int, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    site = db.query(Site).filter(Site.id == site_id).first()
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")
    db.query(Machine).filter(Machine.site_id == site_id).update({"site_id": None})
    db.delete(site); db.commit()
    return {"status": "deleted"}
SITESEOF
echo "Created routes/sites.py"

echo ""
echo "=================================================================="
echo "PART D — WIRE routes/sites.py into main.py"
echo "=================================================================="
python3 - << 'PYEOF'
path = "/home/aadi/Desktop/jenix/server/main.py"
src = open(path).read()

anchor1 = "from routes.backup          import router as backup_router"
assert src.count(anchor1) == 1, f"anchor1 matched {src.count(anchor1)} times, expected 1"
src = src.replace(anchor1, anchor1 + "\nfrom routes.sites           import router as sites_router", 1)

anchor2 = '''for router in [
    auth_router, agents_router, commands_router,
    metrics_router, reports_router, schedules_router,
    license_router, analytics_router, fleet_router,
    audit_router, cve_router, notify_router,
    whitelabel_router, uptime_router, backup_router,
]:'''
assert src.count(anchor2) == 1, f"anchor2 matched {src.count(anchor2)} times, expected 1"
new2 = anchor2.replace("whitelabel_router, uptime_router, backup_router,\n]:",
                        "whitelabel_router, uptime_router, backup_router,\n    sites_router,\n]:")
src = src.replace(anchor2, new2, 1)

open(path, "w").write(src)
print("main.py patched: sites_router imported and added to router list (2/2 anchors matched exactly once)")
PYEOF

echo ""
echo "--- re-verify main.py anchors ---"
grep -c "from routes.sites" "$SERVER_DIR/main.py"
grep -c "sites_router," "$SERVER_DIR/main.py"

echo ""
echo "=================================================================="
echo "PART E — PATCH routes/agents.py (MachineRegister, register(), ApproveIn, approve_machine(), MachineOut, get_install_command, import)"
echo "=================================================================="
python3 - << 'PYEOF'
path = "/home/aadi/Desktop/jenix/server/routes/agents.py"
src = open(path).read()

# 1. import Site
anchor1 = "from db import get_db, Machine, AuditLog, hash_passphrase"
assert src.count(anchor1) == 1, f"anchor1 matched {src.count(anchor1)} times"
src = src.replace(anchor1, "from db import get_db, Machine, AuditLog, hash_passphrase, Site", 1)

# 2. MachineRegister gets site_id
anchor2 = '''class MachineRegister(BaseModel):
    hostname: str
    ip:       str
    os_name:  str = ""
    kernel:   str = ""
    token:    str | None = None  # cached token from a prior registration, if any -
                                  # used as the primary identity key to prevent
                                  # duplicate rows from IP drift or hostname collisions'''
assert src.count(anchor2) == 1, f"anchor2 matched {src.count(anchor2)} times"
new2 = anchor2 + '\n    site_id:  int | None = None  # optional Site to pre-assign at install time'
src = src.replace(anchor2, new2, 1)

# 3. MachineOut gets site_id
anchor3 = '''class MachineOut(BaseModel):
    id:        int
    hostname:  str
    ip:        str
    os_name:   str
    kernel:    str
    status:    str
    last_seen: datetime'''
assert src.count(anchor3) == 1, f"anchor3 matched {src.count(anchor3)} times"
new3 = anchor3.replace("    kernel:    str\n", "    kernel:    str\n    site_id:   int | None = None\n")
src = src.replace(anchor3, new3, 1)

# 4. register(): set site_id on new-machine creation
anchor4 = '''    machine = Machine(
        hostname=body.hostname, ip=body.ip,
        os_name=body.os_name,  kernel=body.kernel,
        token=token, status="pending"  # requires admin approval before it can connect over WS
    )'''
assert src.count(anchor4) == 1, f"anchor4 matched {src.count(anchor4)} times"
new4 = '''    machine = Machine(
        hostname=body.hostname, ip=body.ip,
        os_name=body.os_name,  kernel=body.kernel,
        token=token, status="pending",  # requires admin approval before it can connect over WS
        site_id=body.site_id  # from install-time ?site_id= param, if any; only applied on genuine first-time creation
    )'''
src = src.replace(anchor4, new4, 1)

# 5. ApproveIn gets site_id
anchor5 = "class ApproveIn(BaseModel):\n    redirect_target_url: str | None = None"
assert src.count(anchor5) == 1, f"anchor5 matched {src.count(anchor5)} times"
new5 = anchor5 + "\n    site_id: int | None = None  # optional override/confirm at approval time"
src = src.replace(anchor5, new5, 1)

# 6. approve_machine(): apply site_id override before setting status
anchor6 = '    m.status = "offline"  # ready to connect; WS handler sets "online" once it actually does\n    db.commit()'
assert src.count(anchor6) == 1, f"anchor6 matched {src.count(anchor6)} times"
new6 = '''    if body.site_id is not None:
        m.site_id = body.site_id
    m.status = "offline"  # ready to connect; WS handler sets "online" once it actually does
    db.commit()'''
src = src.replace(anchor6, new6, 1)

# 7. get_install_command(): accept optional site_id, validate, env-prefix the command
anchor7 = '''@router.get("/install-command")
def get_install_command(request: Request,
                        _: User = Depends(require_admin)):
    """Returns the real, working one-liner for the dashboard's Add Node
    modal. Points at the actual GET /install route (server/main.py),
    which serves install_jenix.sh directly."""
    server_addr = request.url.hostname
    server_port = request.url.port or 8000
    scheme      = request.url.scheme
    base        = f"{scheme}://{server_addr}:{server_port}"
    return {
        "command": f"curl -sSL {base}/install | bash",
        "note": "Run on the target Linux/macOS machine. It installs the "
                "agent, registers with this server, and the machine will "
                "appear below awaiting approval.",
    }'''
assert src.count(anchor7) == 1, f"anchor7 matched {src.count(anchor7)} times"
new7 = '''@router.get("/install-command")
def get_install_command(request: Request,
                        site_id: int | None = None,
                        db: Session = Depends(get_db),
                        _: User = Depends(require_admin)):
    """Returns the real, working one-liner for the dashboard's Add Node
    modal. Points at the actual GET /install route (server/main.py),
    which serves install_jenix.sh directly. If site_id is given, it's
    validated and env-var-prefixed onto the bash process reading the
    piped script, so install_jenix.sh can pick it up as $JENIX_SITE_ID."""
    if site_id is not None:
        site = db.query(Site).filter(Site.id == site_id).first()
        if not site:
            raise HTTPException(status_code=404, detail="Site not found")
    server_addr = request.url.hostname
    server_port = request.url.port or 8000
    scheme      = request.url.scheme
    base        = f"{scheme}://{server_addr}:{server_port}"
    if site_id is not None:
        command = f"curl -sSL {base}/install | JENIX_SITE_ID={site_id} bash"
    else:
        command = f"curl -sSL {base}/install | bash"
    return {
        "command": command,
        "note": "Run on the target Linux/macOS machine. It installs the "
                "agent, registers with this server, and the machine will "
                "appear below awaiting approval.",
    }'''
src = src.replace(anchor7, new7, 1)

open(path, "w").write(src)
print("agents.py patched: all 7 anchors matched exactly once and applied")
PYEOF

echo ""
echo "--- re-verify agents.py anchors ---"
grep -c "from db import get_db, Machine, AuditLog, hash_passphrase, Site" "$SERVER_DIR/routes/agents.py"
grep -c "site_id:  int | None = None  # optional Site to pre-assign" "$SERVER_DIR/routes/agents.py"
grep -c "site_id:   int | None = None" "$SERVER_DIR/routes/agents.py"
grep -c "site_id=body.site_id  # from install-time" "$SERVER_DIR/routes/agents.py"
grep -c "site_id: int | None = None  # optional override/confirm" "$SERVER_DIR/routes/agents.py"
grep -c "if body.site_id is not None:" "$SERVER_DIR/routes/agents.py"
grep -c "JENIX_SITE_ID={site_id}" "$SERVER_DIR/routes/agents.py"

echo ""
echo "=================================================================="
echo "PART F — py_compile + real import test (BEFORE touching the live server)"
echo "=================================================================="
cd "$SERVER_DIR"
source ~/Desktop/jenix/server_venv/bin/activate
python3 -m py_compile db.py routes/agents.py routes/sites.py main.py
echo "py_compile: clean"
python3 -c "import main" && echo "real import test: clean (main.py imports with no tracebacks)"

echo ""
echo "=================================================================="
echo "PART G — RESTART FLOOR 1 (disciplined sequence, script-file based)"
echo "=================================================================="
cat > /tmp/restart_floor1.sh << 'RESTARTEOF'
#!/bin/bash
set -e
PID=$(lsof -ti :8000 -sTCP:LISTEN || echo "")
if [ -n "$PID" ]; then
    kill "$PID"
    sleep 1
    if lsof -ti :8000 -sTCP:LISTEN > /dev/null 2>&1; then
        kill -9 "$PID"
        sleep 1
    fi
fi
echo "Old Floor 1 process stopped (or was not running)"
cd /home/aadi/Desktop/jenix/server
source /home/aadi/Desktop/jenix/server_venv/bin/activate
setsid nohup uvicorn main:app --host 0.0.0.0 --port 8000 > /tmp/floor1_sites_restart.log 2>&1 < /dev/null &
disown
sleep 4
NEWPID=$(lsof -ti :8000 -sTCP:LISTEN || echo "")
echo "New Floor 1 PID: $NEWPID"
curl -s -m 5 -o /dev/null -w "curl /health http_code: %{http_code}\n" http://localhost:8000/health
echo "--- full startup log ---"
cat /tmp/floor1_sites_restart.log
RESTARTEOF
bash -n /tmp/restart_floor1.sh && echo "restart script syntax OK"
bash /tmp/restart_floor1.sh

echo ""
echo "=================================================================="
echo "PART H — VERIFY /api/sites IS REALLY WIRED (unauthenticated 401/403 expected, NOT 404)"
echo "=================================================================="
curl -s -m 5 -o /dev/null -w "GET /api/sites (no auth) http_code: %{http_code}\n" http://localhost:8000/api/sites

echo ""
echo "=================================================================="
echo "PART I — PATCH agent.py (install-time site_id plumbing on the agent side)"
echo "=================================================================="
python3 - << 'PYEOF'
path = "/home/aadi/Desktop/jenix/agent/agent.py"
src = open(path).read()

anchor1 = 'SERVER_FILE  = Path.home() / ".jenix" / "server_url"\n'
assert src.count(anchor1) == 1, f"anchor1 matched {src.count(anchor1)} times"
src = src.replace(anchor1, anchor1 + 'SITE_FILE    = Path.home() / ".jenix" / "site_id"\n', 1)

anchor2 = '''    info = get_system_info()
    if cached_token:
        info["token"] = cached_token'''
assert src.count(anchor2) == 1, f"anchor2 matched {src.count(anchor2)} times"
new2 = '''    info = get_system_info()
    if cached_token:
        info["token"] = cached_token
    if SITE_FILE.exists():
        try:
            info["site_id"] = int(SITE_FILE.read_text().strip())
        except ValueError:
            pass'''
src = src.replace(anchor2, new2, 1)

open(path, "w").write(src)
print("agent.py patched: 2/2 anchors matched exactly once")
PYEOF

echo ""
echo "--- re-verify agent.py anchors ---"
grep -c 'SITE_FILE    = Path.home' "$AGENT_DIR/agent.py"
grep -c 'info\["site_id"\] = int(SITE_FILE.read_text' "$AGENT_DIR/agent.py"

echo ""
echo "=================================================================="
echo "PART J — PATCH install_jenix.sh (capture \$JENIX_SITE_ID, write ~/.jenix/site_id)"
echo "=================================================================="
python3 - << 'PYEOF'
path = "/home/aadi/Desktop/jenix/install_jenix.sh"
src = open(path).read()

anchor = 'echo "Using JENIX server: $JENIX_SERVER"\necho ""\n'
assert src.count(anchor) == 1, f"anchor matched {src.count(anchor)} times"
new = '''echo "Using JENIX server: $JENIX_SERVER"
echo ""

if [ -n "$JENIX_SITE_ID" ]; then
    mkdir -p ~/.jenix
    echo "$JENIX_SITE_ID" > ~/.jenix/site_id
    echo "Site ID: $JENIX_SITE_ID (will be sent at registration)"
fi

'''
src = src.replace(anchor, new, 1)

open(path, "w").write(src)
print("install_jenix.sh patched: 1/1 anchor matched exactly once")
PYEOF

echo ""
echo "--- re-verify install_jenix.sh anchor ---"
grep -c "JENIX_SITE_ID" "$REPO_ROOT/install_jenix.sh"
bash -n "$REPO_ROOT/install_jenix.sh" && echo "install_jenix.sh syntax OK"

echo ""
echo "=================================================================="
echo "PART K — REBUILD + REDEPLOY THE AGENT BINARY (real code changed in agent.py)"
echo "=================================================================="
cd "$AGENT_DIR"
python3 -m py_compile agent.py && echo "agent.py py_compile: clean"
OLD_HASH=$(sha256sum ~/.jenix/JenixAgent 2>/dev/null | awk '{print $1}' || echo "none")
echo "Currently running agent binary hash: $OLD_HASH"
pyinstaller JenixAgentCLI.spec --noconfirm
NEW_HASH=$(sha256sum dist/JenixAgent | awk '{print $1}')
echo "Newly built binary hash: $NEW_HASH"
if [ "$NEW_HASH" == "$OLD_HASH" ]; then
    echo "ABORT: new hash matches old running hash — build did not pick up the real change"
    exit 1
fi
cp ~/.jenix/JenixAgent ~/.jenix/JenixAgent.bak_sites_${TS}
echo "Backed up old agent binary to ~/.jenix/JenixAgent.bak_sites_${TS}"
sudo systemctl stop jenix-agent
sleep 1
cp dist/JenixAgent ~/.jenix/JenixAgent
chmod +x ~/.jenix/JenixAgent
sudo systemctl start jenix-agent
sleep 3
sudo systemctl status jenix-agent --no-pager | head -20

echo ""
echo "=================================================================="
echo "PART L — REQUEST: real Fleet.jsx pending-approval section + Sidebar.jsx (needed for real Sites UI next round, not guessed)"
echo "=================================================================="
grep -n "pending\|Pending\|approve\|Approve\|install-command\|installCommand" ~/Desktop/jenix/dashboard/src/pages/Fleet.jsx | head -60
echo ""
echo "--- full Sidebar.jsx (need real nav structure to add a Sites link) ---"
cat ~/Desktop/jenix/dashboard/src/components/Sidebar.jsx
