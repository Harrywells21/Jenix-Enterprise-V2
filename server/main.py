import asyncio
from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
import os

from db import init_db
from ws.handler   import agent_endpoint, dashboard_endpoint, offline_watchdog
from scheduler    import init_scheduler
from routes.auth      import router as auth_router
from routes.agents    import router as agents_router
from routes.commands  import router as commands_router
from routes.metrics   import router as metrics_router
from routes.reports   import router as reports_router
from routes.schedules import router as schedules_router
from routes.license   import router as license_router
from routes.analytics import router as analytics_router
from routes.fleet     import router as fleet_router
from routes.audit     import router as audit_router

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    print("✅ Database ready")
    asyncio.create_task(offline_watchdog())
    print("✅ Offline watchdog started")
    init_scheduler()
    print("✅ JENIX Enterprise Server running")
    yield
    print("[server] Shutting down...")

app = FastAPI(
    title       = "JENIX Enterprise",
    description = "Multi-node Linux system management platform",
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

# REST routes
app.include_router(auth_router)
app.include_router(agents_router)
app.include_router(commands_router)
app.include_router(metrics_router)
app.include_router(reports_router)
app.include_router(schedules_router)
app.include_router(license_router)
app.include_router(analytics_router)
app.include_router(fleet_router)
app.include_router(audit_router)

# WebSocket routes
@app.websocket("/ws/agent/{token}")
async def ws_agent(websocket: WebSocket, token: str):
    await agent_endpoint(websocket, token)

@app.websocket("/ws/dashboard")
async def ws_dashboard(websocket: WebSocket):
    await dashboard_endpoint(websocket)

# Static files
static_dir = os.path.join(os.path.dirname(__file__), "static")
os.makedirs(static_dir, exist_ok=True)
app.mount("/static", StaticFiles(directory=static_dir), name="static")

@app.get("/install")
def installer_redirect():
    from fastapi.responses import RedirectResponse
    return RedirectResponse("/static/install.sh")

@app.get("/health")
def health():
    return {"status": "ok", "app": "JENIX Enterprise", "version": "2.0.0"}

@app.get("/")
def root():
    return {"app": "JENIX Enterprise Server", "version": "2.0.0",
            "docs": "/docs", "health": "/health"}
