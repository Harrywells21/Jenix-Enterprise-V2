"""
JENIX Enterprise Server — main.py
FastAPI app with REST + WebSocket
"""
import asyncio
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from db import init_db
from ws.handler import agent_endpoint, dashboard_endpoint, offline_watchdog
from routes.auth     import router as auth_router
from routes.agents   import router as agents_router
from routes.commands import router as commands_router
from routes.metrics  import router as metrics_router
from routes.reports  import router as reports_router

# ── Lifespan ───────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    init_db()
    print("✅ Database ready")
    asyncio.create_task(offline_watchdog())
    print("✅ Offline watchdog started")
    print("✅ JENIX Enterprise Server running")
    yield
    # Shutdown
    print("[server] Shutting down...")

# ── App ────────────────────────────────────────────────────────────────────
app = FastAPI(
    title       = "JENIX Enterprise",
    description = "Multi-node Linux system management platform",
    version     = "1.0.0",
    lifespan    = lifespan,
)

# ── CORS — allow dashboard to talk to server ───────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins     = ["*"],
    allow_credentials = True,
    allow_methods     = ["*"],
    allow_headers     = ["*"],
)

# ── REST routes ────────────────────────────────────────────────────────────
app.include_router(auth_router)
app.include_router(agents_router)
app.include_router(commands_router)
app.include_router(metrics_router)
app.include_router(reports_router)

# ── WebSocket routes ───────────────────────────────────────────────────────
from fastapi import WebSocket

@app.websocket("/ws/agent/{token}")
async def ws_agent(websocket: WebSocket, token: str):
    await agent_endpoint(websocket, token)

@app.websocket("/ws/dashboard")
async def ws_dashboard(websocket: WebSocket):
    await dashboard_endpoint(websocket)

# ── Health check ───────────────────────────────────────────────────────────
@app.get("/health")
def health():
    return {"status": "ok", "app": "JENIX Enterprise", "version": "1.0.0"}

# ── Root ───────────────────────────────────────────────────────────────────
@app.get("/")
def root():
    return {
        "app":     "JENIX Enterprise Server",
        "version": "1.0.0",
        "docs":    "/docs",
        "health":  "/health",
    }
