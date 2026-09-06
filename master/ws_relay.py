"""
JENIX Master -- Cross-Floor WebSocket Relay

Master opens its own outbound WebSocket connection to each floor's
existing /ws/dashboard endpoint (the same endpoint floor 8000's React
dashboard already connects to) and re-broadcasts every event to
master's own connected browser clients over /ws/master-dashboard.

Chosen over a floor-push-to-master design: this requires ZERO changes
to floor-server code, and matches the existing master-polls/proxies-
floors trust direction already used everywhere else in this codebase
(Audit Log, Reports, Command History, Scheduling all follow the same
pattern -- master reads from floors, floors never push into master).

Each floor gets its own background asyncio task with reconnect and
exponential backoff, mirroring the same pattern already proven
reliable in the agent's own reconnect logic (agent/agent.py).
"""
import asyncio
import json
import websockets
from fastapi import WebSocket, WebSocketDisconnect

_master_dashboards: list[WebSocket] = []

MIN_BACKOFF = 1
MAX_BACKOFF = 30


async def master_dashboard_endpoint(websocket: WebSocket):
    await websocket.accept()
    _master_dashboards.append(websocket)
    print(f"[WS-relay] Master dashboard client connected -- total: {len(_master_dashboards)}")
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        if websocket in _master_dashboards:
            _master_dashboards.remove(websocket)


async def _broadcast_to_master_dashboards(payload: dict):
    dead = []
    for ws in _master_dashboards:
        try:
            await ws.send_text(json.dumps(payload))
        except Exception:
            dead.append(ws)
    for ws in dead:
        if ws in _master_dashboards:
            _master_dashboards.remove(ws)


def _floor_ws_url(floor: dict) -> str:
    url = floor["url"]
    if url.startswith("https://"):
        return "wss://" + url[len("https://"):] + "/ws/dashboard"
    if url.startswith("http://"):
        return "ws://" + url[len("http://"):] + "/ws/dashboard"
    raise ValueError(f"Unrecognized floor URL scheme: {url}")


async def _relay_one_floor(idx: int, floor: dict, get_ws_token_fn):
    """Runs forever: connects to one floor's /ws/dashboard, re-broadcasts
    every event (tagged with floor_idx/floor_name) to master's own
    connected browser clients, reconnects with backoff on disconnect.
    Fetches a fresh short-lived ws-token on every connect attempt --
    the un-tokened ws_url below is used for logging so a token is never
    printed."""
    ws_url = _floor_ws_url(floor)
    backoff = MIN_BACKOFF
    while True:
        try:
            ws_token = await get_ws_token_fn(floor)
            authed_url = f"{ws_url}?token={ws_token}"
            async with websockets.connect(authed_url, ping_interval=20, ping_timeout=20) as ws:
                print(f"[WS-relay] Connected to {floor['name']} ({ws_url})")
                backoff = MIN_BACKOFF  # reset after a successful connect
                async for raw in ws:
                    try:
                        data = json.loads(raw)
                    except Exception:
                        continue
                    data["floor_idx"] = idx
                    data["floor_name"] = floor["name"]
                    await _broadcast_to_master_dashboards(data)
        except Exception as e:
            print(f"[WS-relay] {floor['name']} disconnected/error: {e} -- retrying in {backoff}s")
        await asyncio.sleep(backoff)
        backoff = min(backoff * 2, MAX_BACKOFF)


async def start_relays(floors: list[dict], get_ws_token_fn):
    """Launches one background relay task per floor. Call once at
    startup with the result of master_server.get_floors() and
    master_server.get_ws_token."""
    tasks = [asyncio.create_task(_relay_one_floor(i, f, get_ws_token_fn)) for i, f in enumerate(floors)]
    print(f"[WS-relay] Started {len(tasks)} floor relay task(s)")
    return tasks
