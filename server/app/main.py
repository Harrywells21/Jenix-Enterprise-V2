"""
JENIX Enterprise v3.0 — Main FastAPI Application
Cross-platform Linux / macOS / Windows fleet management
"""

import asyncio
import hashlib
import json
import os
import uuid
from datetime import datetime
from typing import Dict, List, Optional

from dotenv import load_dotenv
load_dotenv()

from fastapi import (
    FastAPI, WebSocket, WebSocketDisconnect, Depends,
    HTTPException, Request, Response, BackgroundTasks
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy.orm import Session
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from .models import (
    init_db, get_db, Node, User, MetricSnapshot,
    AuditLog, Alert, ScanResult, ScheduledJob,
    License, BrandSettings, ComplianceReport
)
from .auth import (
    hash_password, verify_password, create_token, decode_token,
    get_current_user, require_admin, require_operator, require_viewer,
    write_audit, generate_license_key, validate_license_key
)
from .alerts import check_and_alert, send_offline_alert
from .scanner import run_full_scan

# ── App setup ──────────────────────────────────────────────────────────────

limiter = Limiter(key_func=get_remote_address)
app = FastAPI(
    title="JENIX Enterprise",
    version="3.0.0",
    description="Cross-platform fleet management — Linux, macOS, Windows",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(GZipMiddleware, minimum_size=1000)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── In-memory state ────────────────────────────────────────────────────────

# node_id -> WebSocket connection
connected_agents: Dict[str, WebSocket] = {}
# node_id -> latest metrics dict
node_metrics:     Dict[str, dict]      = {}
# node_id -> list of dashboard WebSocket connections
dashboard_clients: Dict[str, List[WebSocket]] = {}

# ── Startup ────────────────────────────────────────────────────────────────

@app.on_event("startup")
async def startup():
    init_db()
    await seed_default_admin()
    print("[JENIX] Server started. Visit http://localhost:8000/api/docs")

async def seed_default_admin():
    db = next(get_db())
    try:
        if not db.query(User).filter(User.username == "admin").first():
            admin = User(
                id=str(uuid.uuid4()),
                username="admin",
                email="admin@jenix.local",
                password_hash=hash_password("admin123"),
                role="admin",
            )
            db.add(admin)
            db.commit()
            print("[JENIX] Default admin created. Username: admin | Password: admin123")
            print("[JENIX] CHANGE THIS PASSWORD IMMEDIATELY!")
    finally:
        db.close()

# ── Pydantic schemas ───────────────────────────────────────────────────────

class LoginRequest(BaseModel):
    username: str
    password: str

class UserCreate(BaseModel):
    username: str
    email: str
    password: str
    role: str = "viewer"

class CommandRequest(BaseModel):
    command:  str
    node_ids: List[str] = []  # empty = all online nodes

class BrandUpdate(BaseModel):
    company_name:  Optional[str] = None
    logo_text:     Optional[str] = None
    primary_color: Optional[str] = None
    sidebar_color: Optional[str] = None

class NodeTagUpdate(BaseModel):
    tags: List[str]

# ── Auth endpoints ─────────────────────────────────────────────────────────

@app.post("/api/auth/login")
@limiter.limit("10/minute")
async def login(request: Request, body: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == body.username).first()
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account disabled")
    user.last_login = datetime.utcnow()
    db.commit()
    token = create_token(user.id, user.username, user.role, user.tenant_id)
    write_audit(db, "login", f"User {user.username} logged in",
                user_id=user.id, ip=request.client.host)
    return {"token": token, "role": user.role, "username": user.username}

@app.post("/api/auth/users")
async def create_user(body: UserCreate, db: Session = Depends(get_db),
                      current_user: User = Depends(require_admin)):
    if db.query(User).filter(User.username == body.username).first():
        raise HTTPException(status_code=400, detail="Username exists")
    user = User(
        id=str(uuid.uuid4()),
        username=body.username,
        email=body.email,
        password_hash=hash_password(body.password),
        role=body.role,
    )
    db.add(user)
    db.commit()
    write_audit(db, "create_user", f"Created user {body.username}",
                user_id=current_user.id)
    return {"id": user.id, "username": user.username, "role": user.role}

@app.get("/api/auth/me")
async def me(current_user: User = Depends(get_current_user)):
    return {"id": current_user.id, "username": current_user.username,
            "role": current_user.role, "email": current_user.email}

# ── Node endpoints ─────────────────────────────────────────────────────────

@app.get("/api/nodes")
async def list_nodes(db: Session = Depends(get_db),
                     _: User = Depends(require_viewer)):
    nodes = db.query(Node).all()
    result = []
    for n in nodes:
        m = node_metrics.get(n.id, {})
        result.append({
            "id":           n.id,
            "name":         n.name,
            "os_type":      n.os_type,
            "os_pretty":    n.os_pretty or n.os_type,
            "hostname":     n.hostname,
            "ip_address":   n.ip_address,
            "is_online":    n.id in connected_agents,
            "health_score": n.health_score,
            "last_seen":    n.last_seen.isoformat() if n.last_seen else None,
            "tags":         n.tags or [],
            "cpu":          m.get("cpu",    {}).get("cpu_percent", 0),
            "ram":          m.get("memory", {}).get("ram_percent",  0),
            "disk":         max((d.get("percent", 0) for d in m.get("disks", [])), default=0),
        })
    return result

@app.get("/api/nodes/{node_id}")
async def get_node(node_id: str, db: Session = Depends(get_db),
                   _: User = Depends(require_viewer)):
    node = db.query(Node).filter(Node.id == node_id).first()
    if not node:
        raise HTTPException(status_code=404, detail="Node not found")
    metrics = node_metrics.get(node_id, {})
    return {
        "id":         node.id,
        "name":       node.name,
        "os_type":    node.os_type,
        "os_pretty":  node.os_pretty,
        "hostname":   node.hostname,
        "ip_address": node.ip_address,
        "is_online":  node_id in connected_agents,
        "health_score": node.health_score,
        "registered_at": node.registered_at.isoformat() if node.registered_at else None,
        "last_seen":  node.last_seen.isoformat() if node.last_seen else None,
        "tags":       node.tags or [],
        "extra_info": node.extra_info or {},
        "metrics":    metrics,
    }

@app.delete("/api/nodes/{node_id}")
async def delete_node(node_id: str, db: Session = Depends(get_db),
                      current_user: User = Depends(require_admin)):
    node = db.query(Node).filter(Node.id == node_id).first()
    if not node:
        raise HTTPException(status_code=404, detail="Node not found")
    db.delete(node)
    db.commit()
    write_audit(db, "delete_node", f"Deleted node {node.name}",
                node_id=node_id, user_id=current_user.id)
    return {"ok": True}

@app.put("/api/nodes/{node_id}/tags")
async def update_tags(node_id: str, body: NodeTagUpdate,
                      db: Session = Depends(get_db),
                      _: User = Depends(require_operator)):
    node = db.query(Node).filter(Node.id == node_id).first()
    if not node:
        raise HTTPException(status_code=404, detail="Node not found")
    node.tags = body.tags
    db.commit()
    return {"ok": True}

# ── Metrics history ────────────────────────────────────────────────────────

@app.get("/api/nodes/{node_id}/metrics/history")
async def metrics_history(node_id: str, hours: int = 24,
                           db: Session = Depends(get_db),
                           _: User = Depends(require_viewer)):
    from datetime import timedelta
    since = datetime.utcnow() - timedelta(hours=hours)
    snaps = (db.query(MetricSnapshot)
               .filter(MetricSnapshot.node_id == node_id,
                       MetricSnapshot.timestamp >= since)
               .order_by(MetricSnapshot.timestamp)
               .limit(500).all())
    return [{
        "timestamp":    s.timestamp.isoformat(),
        "cpu_percent":  s.cpu_percent,
        "ram_percent":  s.ram_percent,
        "disk_percent": s.disk_percent,
        "load_avg_1m":  s.load_avg_1m,
    } for s in snaps]

# ── Fleet commands ─────────────────────────────────────────────────────────

@app.post("/api/fleet/command")
async def fleet_command(body: CommandRequest, db: Session = Depends(get_db),
                        current_user: User = Depends(require_operator)):
    targets = body.node_ids if body.node_ids else list(connected_agents.keys())
    results = {}
    cmd_id  = str(uuid.uuid4())

    for node_id in targets:
        ws = connected_agents.get(node_id)
        if ws:
            try:
                await ws.send_text(json.dumps({
                    "type":       "command",
                    "command":    body.command,
                    "command_id": cmd_id,
                }))
                results[node_id] = "sent"
            except Exception:
                results[node_id] = "error"
        else:
            results[node_id] = "offline"

    write_audit(db, "fleet_command", f"Command: {body.command[:100]}",
                user_id=current_user.id)
    return {"command_id": cmd_id, "results": results}

@app.post("/api/nodes/{node_id}/command")
async def node_command(node_id: str, body: CommandRequest,
                       db: Session = Depends(get_db),
                       current_user: User = Depends(require_operator)):
    ws = connected_agents.get(node_id)
    if not ws:
        raise HTTPException(status_code=503, detail="Node offline")
    cmd_id = str(uuid.uuid4())
    await ws.send_text(json.dumps({
        "type":       "command",
        "command":    body.command,
        "command_id": cmd_id,
    }))
    write_audit(db, "node_command",
                f"Node {node_id}: {body.command[:100]}",
                node_id=node_id, user_id=current_user.id)
    return {"command_id": cmd_id, "status": "sent"}

# ── Scan endpoints ─────────────────────────────────────────────────────────

@app.post("/api/nodes/{node_id}/scan")
async def trigger_scan(node_id: str, background_tasks: BackgroundTasks,
                       db: Session = Depends(get_db),
                       current_user: User = Depends(require_operator)):
    node = db.query(Node).filter(Node.id == node_id).first()
    if not node:
        raise HTTPException(status_code=404, detail="Node not found")

    async def do_scan():
        result = await run_full_scan(node_id)
        sr = ScanResult(
            node_id=node_id,
            total_pkgs=result["total_packages"],
            critical_cve=result["summary"]["critical"],
            high_cve=result["summary"]["high"],
            medium_cve=result["summary"]["medium"],
            low_cve=result["summary"]["low"],
            findings=result["cve_findings"],
        )
        db2 = next(get_db())
        db2.add(sr)
        db2.commit()
        db2.close()

    background_tasks.add_task(do_scan)
    write_audit(db, "scan_triggered", f"Scan triggered for node {node_id}",
                node_id=node_id, user_id=current_user.id)
    return {"status": "scan_started"}

@app.get("/api/nodes/{node_id}/scan/latest")
async def latest_scan(node_id: str, db: Session = Depends(get_db),
                      _: User = Depends(require_viewer)):
    scan = (db.query(ScanResult)
              .filter(ScanResult.node_id == node_id)
              .order_by(ScanResult.scanned_at.desc())
              .first())
    if not scan:
        return {"message": "No scan results yet"}
    return {
        "scanned_at":   scan.scanned_at.isoformat(),
        "total_pkgs":   scan.total_pkgs,
        "critical_cve": scan.critical_cve,
        "high_cve":     scan.high_cve,
        "medium_cve":   scan.medium_cve,
        "low_cve":      scan.low_cve,
        "findings":     scan.findings or [],
    }

# ── Alerts ─────────────────────────────────────────────────────────────────

@app.get("/api/alerts")
async def list_alerts(resolved: bool = False, limit: int = 50,
                      db: Session = Depends(get_db),
                      _: User = Depends(require_viewer)):
    alerts = (db.query(Alert)
                .filter(Alert.resolved == resolved)
                .order_by(Alert.timestamp.desc())
                .limit(limit).all())
    return [{
        "id":        a.id,
        "node_id":   a.node_id,
        "severity":  a.severity,
        "type":      a.type,
        "message":   a.message,
        "timestamp": a.timestamp.isoformat(),
        "resolved":  a.resolved,
    } for a in alerts]

@app.post("/api/alerts/{alert_id}/resolve")
async def resolve_alert(alert_id: int, db: Session = Depends(get_db),
                        _: User = Depends(require_operator)):
    alert = db.query(Alert).filter(Alert.id == alert_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    alert.resolved    = True
    alert.resolved_at = datetime.utcnow()
    db.commit()
    return {"ok": True}

# ── Audit logs ─────────────────────────────────────────────────────────────

@app.get("/api/audit")
async def get_audit(limit: int = 100, db: Session = Depends(get_db),
                    _: User = Depends(require_admin)):
    logs = (db.query(AuditLog)
              .order_by(AuditLog.timestamp.desc())
              .limit(limit).all())
    return [{
        "id":         l.id,
        "node_id":    l.node_id,
        "user_id":    l.user_id,
        "action":     l.action,
        "detail":     l.detail,
        "timestamp":  l.timestamp.isoformat(),
        "ip_address": l.ip_address,
        "sha256":     l.sha256,
    } for l in logs]

# ── Branding ───────────────────────────────────────────────────────────────

@app.get("/api/brand")
async def get_brand(db: Session = Depends(get_db)):
    brand = db.query(BrandSettings).first()
    if not brand:
        return {"company_name": "JENIX Enterprise", "logo_text": "JENIX",
                "primary_color": "#6366f1", "sidebar_color": "#1e1e2e"}
    return {"company_name": brand.company_name, "logo_text": brand.logo_text,
            "primary_color": brand.primary_color, "sidebar_color": brand.sidebar_color}

@app.put("/api/brand")
async def update_brand(body: BrandUpdate, db: Session = Depends(get_db),
                       _: User = Depends(require_admin)):
    brand = db.query(BrandSettings).first()
    if not brand:
        brand = BrandSettings()
        db.add(brand)
    if body.company_name:  brand.company_name  = body.company_name
    if body.logo_text:     brand.logo_text     = body.logo_text
    if body.primary_color: brand.primary_color = body.primary_color
    if body.sidebar_color: brand.sidebar_color = body.sidebar_color
    brand.updated_at = datetime.utcnow()
    db.commit()
    return {"ok": True}

# ── License ────────────────────────────────────────────────────────────────

@app.post("/api/license/generate")
async def gen_license(company: str, node_limit: int = -1,
                      _: User = Depends(require_admin)):
    key = generate_license_key(company, node_limit)
    return {"license_key": key, "company": company, "node_limit": node_limit}

@app.post("/api/license/validate")
async def validate_license(key: str):
    return {"valid": validate_license_key(key)}

# ── Fleet stats ────────────────────────────────────────────────────────────

@app.get("/api/fleet/stats")
async def fleet_stats(db: Session = Depends(get_db),
                      current_user=Depends(get_current_user)):
    try:
        nodes   = db.query(Node).all()
        online  = [n for n in nodes if n.is_online]

        cpu_vals, ram_vals, disk_vals = [], [], []
        for n in online:
            try:
                m = n.last_metrics
                if isinstance(m, str):
                    import json as _json
                    m = _json.loads(m)
                if isinstance(m, dict):
                    cpu_vals.append(m.get("cpu",{}).get("cpu_percent",0) if isinstance(m.get("cpu"), dict) else m.get("cpu_percent", 0))
                    ram_vals.append(m.get("memory",{}).get("ram_percent",0) if isinstance(m.get("memory"), dict) else m.get("ram_percent", 0))
                    disks = m.get("disks", [])
                    if disks and isinstance(disks, list):
                        disk_vals.append(max((d.get("percent",0) if isinstance(d,dict) else 0) for d in disks))
            except Exception:
                pass

        avg_cpu  = round(sum(cpu_vals)  / max(len(cpu_vals), 1), 1)
        avg_ram  = round(sum(ram_vals)  / max(len(ram_vals), 1), 1)
        avg_disk = round(sum(disk_vals) / max(len(disk_vals), 1), 1)

        open_alerts = db.query(Alert).filter(Alert.resolved == False).count()

        os_breakdown = {}
        for n in nodes:
            os = n.os_type or "Unknown"
            os_breakdown[os] = os_breakdown.get(os, 0) + 1

        return {
            "total_nodes":    len(nodes),
            "online_nodes":   len(online),
            "offline_nodes":  len(nodes) - len(online),
            "avg_cpu":        avg_cpu,
            "avg_ram":        avg_ram,
            "avg_disk":       avg_disk,
            "open_alerts":    open_alerts,
            "os_breakdown":   os_breakdown,
            "commands_today": 0,
            "hours_saved":    round(len(online) * 1.2, 1),
            "estimated_savings": len(online) * 810,
            "fleet_uptime":   "99.9%",
            "total_machines": len(nodes),
            "online_machines": len(online),
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/install/linux")
async def install_linux():
    script_path = os.path.join(os.path.dirname(__file__), "../../scripts/install_linux.sh")
    if os.path.exists(script_path):
        return FileResponse(script_path, media_type="text/plain")
    return Response("# Linux installer not found", media_type="text/plain")

@app.get("/install/macos")
async def install_macos():
    script_path = os.path.join(os.path.dirname(__file__), "../../scripts/install_macos.sh")
    if os.path.exists(script_path):
        return FileResponse(script_path, media_type="text/plain")
    return Response("# macOS installer not found", media_type="text/plain")

@app.get("/install/windows")
async def install_windows():
    script_path = os.path.join(os.path.dirname(__file__), "../../scripts/install_windows.ps1")
    if os.path.exists(script_path):
        return FileResponse(script_path, media_type="text/plain")
    return Response("# Windows installer not found", media_type="text/plain")

@app.get("/agent/jenix_agent.py")
async def serve_agent():
    agent_path = os.path.join(os.path.dirname(__file__), "../../agent/jenix_agent.py")
    if os.path.exists(agent_path):
        return FileResponse(agent_path, media_type="text/plain")
    return Response("# Agent not found", media_type="text/plain")

# ── WebSocket: Agent connections ───────────────────────────────────────────

@app.websocket("/ws/agent/{node_id}")
async def agent_ws(websocket: WebSocket, node_id: str):
    await websocket.accept()
    connected_agents[node_id] = websocket
    db = next(get_db())

    try:
        async for raw in websocket.iter_text():
            msg = json.loads(raw)
            msg_type = msg.get("type")

            if msg_type == "register":
                os_info = msg.get("os_info", {})
                node = db.query(Node).filter(Node.id == node_id).first()
                if not node:
                    node = Node(id=node_id)
                    db.add(node)
                node.name      = msg.get("node_name", node_id)
                node.os_type   = msg.get("os_type", "Linux")
                node.os_pretty = os_info.get("os_pretty", msg.get("os_type", "Linux"))
                node.hostname  = os_info.get("hostname", "")
                node.is_online = True
                node.last_seen = datetime.utcnow()
                db.commit()
                await websocket.send_text(json.dumps({"type": "registered", "ok": True}))

            elif msg_type == "metrics":
                data = msg.get("data", {})
                node_metrics[node_id] = data

                # Update node online status
                node = db.query(Node).filter(Node.id == node_id).first()
                if node:
                    node.is_online = True
                    node.last_seen = datetime.utcnow()

                    # Calculate health score
                    cpu  = data.get("cpu",    {}).get("cpu_percent",   0)
                    ram  = data.get("memory", {}).get("ram_percent",    0)
                    disk = max((d.get("percent",0) for d in data.get("disks",[])), default=0)
                    score = 100
                    if cpu  > 90: score -= 30
                    elif cpu  > 75: score -= 15
                    if ram  > 90: score -= 30
                    elif ram  > 75: score -= 15
                    if disk > 95: score -= 25
                    elif disk > 85: score -= 10
                    node.health_score = max(0, score)
                    db.commit()

                # Save metric snapshot every 10th message (avoid DB bloat)
                snap_key = f"snap_count_{node_id}"
                count = node_metrics.get(snap_key, 0) + 1
                node_metrics[snap_key] = count
                if count % 10 == 0:
                    disks = data.get("disks", [])
                    snap = MetricSnapshot(
                        node_id=node_id,
                        cpu_percent=data.get("cpu",{}).get("cpu_percent",0),
                        ram_percent=data.get("memory",{}).get("ram_percent",0),
                        disk_percent=max((d.get("percent",0) for d in disks), default=0),
                        load_avg_1m=data.get("cpu",{}).get("load_avg",{}).get("1m") if data.get("cpu",{}).get("load_avg") else None,
                        raw=data,
                    )
                    db.add(snap)
                    db.commit()

                # Check alerts
                node = db.query(Node).filter(Node.id == node_id).first()
                node_name = node.name if node else node_id
                alerts_fired = await check_and_alert(node_id, node_name, data)
                for a in alerts_fired:
                    alert = Alert(node_id=node_id, severity=a["severity"],
                                  type=a["type"], message=a["message"])
                    db.add(alert)
                db.commit()

                # Broadcast to dashboard clients
                if node_id in dashboard_clients:
                    dead = []
                    for ws in dashboard_clients[node_id]:
                        try:
                            await ws.send_text(json.dumps({
                                "type": "metrics_update",
                                "node_id": node_id,
                                "data": data,
                            }))
                        except Exception:
                            dead.append(ws)
                    for ws in dead:
                        dashboard_clients[node_id].remove(ws)

            elif msg_type == "command_result":
                # Broadcast result to all dashboard clients
                for ws_list in dashboard_clients.values():
                    for ws in ws_list:
                        try:
                            await ws.send_text(json.dumps({
                                "type":       "command_result",
                                "node_id":    node_id,
                                "command_id": msg.get("command_id"),
                                "data":       msg.get("data"),
                            }))
                        except Exception:
                            pass

    except (WebSocketDisconnect, Exception) as e:
        print(f"[WS] Agent {node_id} disconnected: {e}")
    finally:
        connected_agents.pop(node_id, None)
        node_metrics.pop(node_id, None)
        db_close = next(get_db())
        node = db_close.query(Node).filter(Node.id == node_id).first()
        if node:
            node.is_online = False
            db_close.commit()
        db_close.close()
        node_name = node.name if node else node_id
        asyncio.create_task(
            send_offline_alert(node_id, node_name)
        )

# ── WebSocket: Dashboard clients ───────────────────────────────────────────

@app.websocket("/ws/dashboard")
async def dashboard_ws(websocket: WebSocket):
    await websocket.accept()
    # Subscribe to all nodes by default
    client_nodes = []

    try:
        async for raw in websocket.iter_text():
            msg = json.loads(raw)
            if msg.get("type") == "subscribe":
                node_id = msg.get("node_id")
                if node_id:
                    if node_id not in dashboard_clients:
                        dashboard_clients[node_id] = []
                    dashboard_clients[node_id].append(websocket)
                    client_nodes.append(node_id)
                    # Send current metrics immediately
                    if node_id in node_metrics:
                        await websocket.send_text(json.dumps({
                            "type":    "metrics_update",
                            "node_id": node_id,
                            "data":    node_metrics[node_id],
                        }))
            elif msg.get("type") == "subscribe_all":
                for nid, ws_list in dashboard_clients.items():
                    ws_list.append(websocket)
                    client_nodes.append(nid)
    except (WebSocketDisconnect, Exception):
        pass
    finally:
        for node_id in client_nodes:
            if node_id in dashboard_clients:
                try:
                    dashboard_clients[node_id].remove(websocket)
                except ValueError:
                    pass

# ── Health check ───────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {
        "status":          "ok",
        "version":         "3.0.0",
        "connected_agents": len(connected_agents),
        "timestamp":        datetime.utcnow().isoformat(),
    }

# ── Dashboard ─────────────────────────────────────────────────────────────────
import os as _jx_os
from fastapi.responses import HTMLResponse as _JXResponse

@app.get("/", response_class=_JXResponse)
async def serve_dashboard():
    _p = _jx_os.path.normpath(
        _jx_os.path.join(_jx_os.path.dirname(__file__), "../static", "index.html")
    )
    if _jx_os.path.exists(_p):
        with open(_p, encoding="utf-8") as _f:
            return _JXResponse(_f.read())
    return _JXResponse(
        "<html><body style='background:#070b14;color:#63b3ff;font-family:monospace;padding:40px'>"
        "<h1>JENIX Enterprise</h1><p><a href='/api/docs' style='color:#63b3ff'>Open API Docs</a></p>"
        "</body></html>"
    )

try:
    from fastapi.staticfiles import StaticFiles as _JXStatic
    _sd = _jx_os.path.normpath(_jx_os.path.join(_jx_os.path.dirname(__file__), "../static"))
    if _jx_os.path.exists(_sd):
        try:
            app.mount("/static", _JXStatic(directory=_sd), name="static")
        except RuntimeError:
            pass
except Exception:
    pass

try:
    from .day4_routes import router as _d4r
    app.include_router(_d4r)
    print("[JENIX] Day 4 enterprise modules loaded")
except Exception as _e:
    print(f"[JENIX] Day 4 optional: {_e}")

try:
    from .install_routes import router as _install_router
    app.include_router(_install_router)
    print("[JENIX] Install routes loaded")
except Exception as _e:
    print(f"[JENIX] Install routes error: {_e}")
@app.post("/api/upload-static/{filename}")
async def upload_static(filename: str, request: Request):
    import os
    allowed = ['react.min.js','react-dom.min.js','prop-types.min.js','recharts.min.js']
    if filename not in allowed:
        return {"error": "Not allowed"}
    data = await request.body()
    path = os.path.join(os.path.dirname(__file__), "../static", filename)
    with open(path, "wb") as f:
        f.write(data)
    return {"ok": True, "file": filename, "size": len(data)}
