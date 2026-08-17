import asyncio
from fastapi import FastAPI, WebSocket, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse, HTMLResponse
from contextlib import asynccontextmanager
import os

from db import init_db
from ws.handler         import agent_endpoint, dashboard_endpoint, offline_watchdog
from scheduler          import init_scheduler
from cleanup            import run_cleanup
from backup             import run_backup_scheduler
from security           import SECURITY_HEADERS, rate_limit_api

from routes.auth            import router as auth_router
from routes.agents          import router as agents_router
from routes.commands        import router as commands_router
from routes.metrics         import router as metrics_router
from routes.reports         import router as reports_router
from routes.schedules       import router as schedules_router
from routes.license         import router as license_router
from routes.analytics       import router as analytics_router
from routes.fleet           import router as fleet_router
from routes.audit           import router as audit_router
from routes.cve             import router as cve_router
from routes.notify_settings import router as notify_router
from routes.whitelabel      import router as whitelabel_router
from routes.uptime          import router as uptime_router
from routes.backup          import router as backup_router

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    print("✅ Database ready")
    asyncio.create_task(offline_watchdog())
    print("✅ Offline watchdog started")
    init_scheduler()
    print("✅ Scheduler started")
    asyncio.create_task(run_cleanup())
    print("✅ Cleanup job scheduled (every 6h)")
    asyncio.create_task(run_backup_scheduler())
    print("✅ Backup scheduler started (every 24h)")
    print("✅ JENIX Enterprise v2.0 running")
    yield
    print("[server] Shutting down...")

app = FastAPI(
    title       = "JENIX Enterprise API",
    description = """
## JENIX Enterprise — Linux Infrastructure Management Platform

Built by **Aaditya Singh** · aadisingh0121@gmail.com

### Authentication
All endpoints (except `/health`, `/whitelabel/public`, `/machines/register`)
require a Bearer JWT token obtained from `POST /auth/login`.

### Roles
- **Admin** — Full access including user management and license
- **Operator** — Can run commands and generate reports
- **Viewer** — Read-only access to dashboards and metrics

### WebSocket Endpoints
- `ws://server/ws/agent/{token}` — Agent connection
- `ws://server/ws/dashboard` — Dashboard live updates
    """,
    version     = "2.0.0",
    lifespan    = lifespan,
    docs_url    = "/docs",
    redoc_url   = "/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins     = ["*"],
    allow_credentials = True,
    allow_methods     = ["*"],
    allow_headers     = ["*"],
)

@app.middleware("http")
async def security_middleware(request: Request, call_next):
    client_ip = request.client.host if request.client else "unknown"
    if not rate_limit_api(client_ip):
        return JSONResponse(status_code=429,
            content={"detail": "Too many requests. Slow down."})
    response = await call_next(request)
    for k, v in SECURITY_HEADERS.items():
        response.headers[k] = v
    return response

for router in [
    auth_router, agents_router, commands_router,
    metrics_router, reports_router, schedules_router,
    license_router, analytics_router, fleet_router,
    audit_router, cve_router, notify_router,
    whitelabel_router, uptime_router, backup_router,
]:
    app.include_router(router, prefix="/api")

@app.websocket("/ws/agent/{token}")
async def ws_agent(websocket: WebSocket, token: str):
    await agent_endpoint(websocket, token)

@app.websocket("/ws/dashboard")
async def ws_dashboard(websocket: WebSocket):
    await dashboard_endpoint(websocket)

static_dir = os.path.join(os.path.dirname(__file__), "static")
os.makedirs(static_dir, exist_ok=True)

@app.get("/install")
def installer():
    from fastapi.responses import RedirectResponse
    return RedirectResponse("/static/install.sh")

@app.get("/dashboard", include_in_schema=False)
@app.get("/dashboard/{full_path:path}", include_in_schema=False)
def serve_dashboard(full_path: str = ""):
    from fastapi.responses import FileResponse
    index_path = os.path.join(static_dir, "index.html")
    return FileResponse(index_path)

app.mount("/static", StaticFiles(directory=static_dir), name="static")

@app.get("/health", tags=["System"])
def health():
    """Health check endpoint — returns server status and version."""
    return {
        "status":  "ok",
        "app":     "JENIX Enterprise",
        "version": "2.0.0",
        "time":    __import__("datetime").datetime.utcnow().isoformat()
    }

# ✅ Landing page as server root
@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def root():
    return """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>JENIX Enterprise</title>
  <style>
    * { box-sizing:border-box; margin:0; padding:0; }
    body {
      background:#0d0d1a; color:#e0e0e0;
      font-family:'Segoe UI',sans-serif;
      min-height:100vh; display:flex;
      flex-direction:column; align-items:center;
      justify-content:center; text-align:center;
      padding:40px;
    }
    .logo { color:#00bcd4; font-size:52px; font-weight:900;
            letter-spacing:6px; margin-bottom:8px; }
    .sub  { color:#333; font-size:12px; letter-spacing:3px;
            margin-bottom:32px; }
    h1    { font-size:28px; font-weight:700; color:#fff;
            margin-bottom:12px; }
    p     { color:#666; font-size:15px; max-width:500px;
            line-height:1.7; margin-bottom:40px; }
    .btns { display:flex; gap:12px; justify-content:center;
            flex-wrap:wrap; }
    .btn-primary {
      padding:12px 32px; background:#00bcd4; color:#000;
      border:none; border-radius:8px; font-size:15px;
      font-weight:700; cursor:pointer; text-decoration:none;
      display:inline-block;
    }
    .btn-secondary {
      padding:12px 32px; background:transparent; color:#aaa;
      border:1px solid #2a2a3e; border-radius:8px;
      font-size:15px; font-weight:600; cursor:pointer;
      text-decoration:none; display:inline-block;
    }
    .stats {
      display:flex; gap:32px; margin-top:48px;
      justify-content:center; flex-wrap:wrap;
    }
    .stat { color:#555; font-size:13px; }
    .stat span { display:block; color:#00bcd4; font-size:20px;
                 font-weight:800; margin-bottom:4px; }
    .footer { position:fixed; bottom:20px; color:#222;
              font-size:11px; }
  </style>
</head>
<body>
  <div class="logo">JENIX</div>
  <div class="sub">ENTERPRISE v2.0</div>
  <h1>Linux Infrastructure Management</h1>
  <p>
    One dashboard. Unlimited Linux servers.<br/>
    Scan, fix, secure and monitor your entire fleet
    from a single browser tab.
  </p>
  <div class="btns">
    <a href="/dashboard" class="btn-primary">
      Open Dashboard →
    </a>
    <a href="/docs" class="btn-secondary">
      API Docs
    </a>
  </div>
  <div class="stats">
    <div class="stat"><span>∞</span>Servers</div>
    <div class="stat"><span>1-Click</span>Fleet Ops</div>
    <div class="stat"><span>SHA-256</span>Audit Logs</div>
    <div class="stat"><span>Perpetual</span>License</div>
  </div>
  <div class="footer">
    Built by Aaditya Singh · aadisingh0121@gmail.com
  </div>
</body>
</html>"""
