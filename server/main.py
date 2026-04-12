import asyncio
from fastapi import FastAPI, WebSocket, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
import os

from db import init_db
from ws.handler         import agent_endpoint, dashboard_endpoint, offline_watchdog
from scheduler          import init_scheduler
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

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    print("✅ Database ready")
    asyncio.create_task(offline_watchdog())
    print("✅ Offline watchdog started")
    init_scheduler()
    print("✅ Scheduler started")
    print("✅ JENIX Enterprise v2.0 running")
    yield
    print("[server] Shutting down...")

app = FastAPI(
    title       = "JENIX Enterprise",
    description = "Multi-node Linux system management",
    version     = "2.0.0",
    lifespan    = lifespan,
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
            content={"detail": "Too many requests"})
    response = await call_next(request)
    for k, v in SECURITY_HEADERS.items():
        response.headers[k] = v
    return response

# ── All routes ─────────────────────────────────────────────────────────────
for router in [
    auth_router, agents_router, commands_router,
    metrics_router, reports_router, schedules_router,
    license_router, analytics_router, fleet_router,
    audit_router, cve_router, notify_router,
    whitelabel_router, uptime_router,
]:
    app.include_router(router)

# ── WebSocket ──────────────────────────────────────────────────────────────
@app.websocket("/ws/agent/{token}")
async def ws_agent(websocket: WebSocket, token: str):
    await agent_endpoint(websocket, token)

@app.websocket("/ws/dashboard")
async def ws_dashboard(websocket: WebSocket):
    await dashboard_endpoint(websocket)

# ── Static ─────────────────────────────────────────────────────────────────
static_dir = os.path.join(os.path.dirname(__file__), "static")
os.makedirs(static_dir, exist_ok=True)
app.mount("/static", StaticFiles(directory=static_dir), name="static")

@app.get("/install")
def installer():
    from fastapi.responses import RedirectResponse
    return RedirectResponse("/static/install.sh")

@app.get("/health")
def health():
    return {"status": "ok", "app": "JENIX Enterprise",
            "version": "2.0.0"}

@app.get("/")
def root():
    return {"app": "JENIX Enterprise", "version": "2.0.0",
            "docs": "/docs"}
