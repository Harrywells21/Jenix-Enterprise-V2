"""
JENIX Master Aggregator & Control Plane — polls and manages multiple
independent JENIX floor servers via their existing REST API. No changes
required on floor servers. Tokens are cached per floor and refreshed on
401, so we don't re-login on every request.

KNOWN LIMITATION (flag for hardening before production use at scale):
floors.json stores admin passwords in plaintext. For a real 40-floor
deployment, replace with per-floor read-only/operator service accounts
or API keys rather than full admin credentials.
"""
import json, asyncio, base64
from pathlib import Path
from fastapi import FastAPI, HTTPException, Body, Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
import httpx
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
import secrets, time
from fastapi import Request
from fastapi.responses import RedirectResponse, JSONResponse


app = FastAPI(title="JENIX Master Control Plane")
# === JENIX AUTH PATCH v1 ===
ADMIN_AUTH_FILE = Path(__file__).parent / "admin_auth.json"
SESSION_HOURS = 12
_sessions: dict[str, float] = {}  # token -> expiry epoch

def _load_admin_auth():
    if not ADMIN_AUTH_FILE.exists():
        return {"username": "admin@jenix.io", "password": "ChangeMe123!"}
    return json.loads(ADMIN_AUTH_FILE.read_text())

_EXEMPT_PATHS = {"/login", "/logout"}
_EXEMPT_PREFIXES = ("/static/",)

def _is_exempt(path: str) -> bool:
    return path in _EXEMPT_PATHS or path.startswith(_EXEMPT_PREFIXES)

@app.middleware("http")
async def require_session(request: Request, call_next):
    if _is_exempt(request.url.path):
        return await call_next(request)
    token = request.cookies.get("jenix_session")
    valid = token is not None and _sessions.get(token, 0) > time.time()
    if not valid:
        if request.url.path.startswith("/api/"):
            return JSONResponse({"detail": "Not authenticated"}, status_code=401)
        return RedirectResponse(url="/login")
    return await call_next(request)

@app.get("/login")
def login_page():
    return FileResponse(STATIC_DIR / "login.html")

@app.post("/login")
def login_submit(body: dict = Body(...)):
    creds = _load_admin_auth()
    if body.get("username") == creds["username"] and body.get("password") == creds["password"]:
        token = secrets.token_urlsafe(32)
        _sessions[token] = time.time() + SESSION_HOURS * 3600
        resp = JSONResponse({"ok": True})
        resp.set_cookie("jenix_session", token, httponly=True, samesite="lax",
                         max_age=SESSION_HOURS * 3600)
        return resp
    return JSONResponse({"detail": "Invalid username or password"}, status_code=401)

@app.get("/logout")
def logout(request: Request):
    token = request.cookies.get("jenix_session")
    if token:
        _sessions.pop(token, None)
    resp = RedirectResponse(url="/login")
    resp.delete_cookie("jenix_session")
    return resp


FLOORS_FILE = Path(__file__).parent / "floors.json"
STATIC_DIR  = Path(__file__).parent / "static"
TOPOLOGY_KEY_FILE = Path(__file__).parent / "topology_private.key"

def _load_topology_key():
    if not TOPOLOGY_KEY_FILE.exists():
        return None
    raw = base64.b64decode(TOPOLOGY_KEY_FILE.read_text().strip())
    return Ed25519PrivateKey.from_private_bytes(raw)

_topology_key = _load_topology_key()

def sign_reassignment(target_url: str) -> str:
    if _topology_key is None:
        raise HTTPException(status_code=500,
            detail="No topology_private.key on the master server — run "
                   "tools/jenix_topology_keygen.py and place the private key at "
                   "master/topology_private.key to enable node reassignment.")
    payload = json.dumps({"type": "reassign_server", "server_url": target_url},
                          sort_keys=True, separators=(",", ":")).encode()
    return base64.b64encode(_topology_key.sign(payload)).decode()

_token_cache: dict[str, str] = {}  # floor url -> token

FLOORS_SECRETS_FILE = Path(__file__).parent / "floors_secrets.json"

def get_floors() -> list[dict]:
    """floors.json holds only public topology (name, url). Credentials
    live in floors_secrets.json (gitignored, not committed) and are
    merged back in here at read time by matching on url."""
    floors = json.loads(FLOORS_FILE.read_text())
    if not FLOORS_SECRETS_FILE.exists():
        raise HTTPException(status_code=500,
            detail="master/floors_secrets.json is missing. Floor credentials "
                   "must live there now (not in floors.json) - see floors_secrets.json.example.")
    secrets_by_url = {s["url"]: s for s in json.loads(FLOORS_SECRETS_FILE.read_text())}
    merged = []
    for f in floors:
        s = secrets_by_url.get(f["url"])
        if not s:
            raise HTTPException(status_code=500,
                detail=f"No credentials found in floors_secrets.json for floor url {f['url']}")
        merged.append({**f, "username": s["username"], "password": s["password"]})
    return merged

def get_floor(idx: int) -> dict:
    floors = get_floors()
    if idx < 0 or idx >= len(floors):
        raise HTTPException(status_code=404, detail="Floor not found")
    return floors[idx]

async def get_token(client: httpx.AsyncClient, floor: dict) -> str:
    if floor["url"] in _token_cache:
        return _token_cache[floor["url"]]
    resp = await client.post(
        f"{floor['url']}/api/auth/login",
        data={"username": floor["username"], "password": floor["password"]},
        timeout=5.0,
    )
    resp.raise_for_status()
    token = resp.json()["access_token"]
    _token_cache[floor["url"]] = token
    return token

async def floor_request(floor: dict, method: str, path: str, **kwargs) -> httpx.Response:
    async with httpx.AsyncClient() as client:
        token = await get_token(client, floor)
        headers = kwargs.pop("headers", {})
        headers["Authorization"] = f"Bearer {token}"
        resp = await client.request(method, f"{floor['url']}{path}", headers=headers, timeout=10.0, **kwargs)
        if resp.status_code == 401:
            # token expired — refresh once and retry
            _token_cache.pop(floor["url"], None)
            token = await get_token(client, floor)
            headers["Authorization"] = f"Bearer {token}"
            resp = await client.request(method, f"{floor['url']}{path}", headers=headers, timeout=10.0, **kwargs)
        return resp

async def fetch_floor_summary(client: httpx.AsyncClient, idx: int, floor: dict) -> dict:
    try:
        token = await get_token(client, floor)
        headers = {"Authorization": f"Bearer {token}"}

        m_resp = await client.get(f"{floor['url']}/api/machines", headers=headers, timeout=5.0)
        m_resp.raise_for_status()
        machines = m_resp.json()

        pending = []
        try:
            p_resp = await client.get(f"{floor['url']}/api/machines/pending", headers=headers, timeout=5.0)
            if p_resp.status_code == 200:
                pending = p_resp.json()
        except Exception:
            pass

        online  = sum(1 for m in machines if m.get("status") == "online")
        offline = len(machines) - online

        return {
            "idx": idx, "name": floor["name"], "url": floor["url"], "reachable": True,
            "total": len(machines), "online": online, "offline": offline,
            "pending_count": len(pending),
            "machines": machines, "pending": pending,
        }
    except Exception as e:
        return {
            "idx": idx, "name": floor["name"], "url": floor["url"], "reachable": False,
            "error": str(e), "total": 0, "online": 0, "offline": 0,
            "pending_count": 0, "machines": [], "pending": [],
        }

@app.get("/api/aggregate")
async def aggregate():
    floors = get_floors()
    async with httpx.AsyncClient() as client:
        results = await asyncio.gather(*[fetch_floor_summary(client, i, f) for i, f in enumerate(floors)])
    return {
        "floors":           results,
        "grand_total":      sum(r["total"] for r in results),
        "grand_online":     sum(r["online"] for r in results),
        "grand_offline":    sum(r["offline"] for r in results),
        "grand_pending":    sum(r["pending_count"] for r in results),
        "floors_reachable": sum(1 for r in results if r["reachable"]),
        "floors_total":     len(results),
    }

@app.get("/api/floors/{idx}/machines/{machine_id}")
async def floor_machine_detail(idx: int, machine_id: int):
    floor = get_floor(idx)
    resp = await floor_request(floor, "GET", f"/api/machines/{machine_id}")
    if resp.status_code != 200:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    return resp.json()

@app.post("/api/floors/{idx}/machines/{machine_id}/approve")
async def floor_approve(idx: int, machine_id: int):
    floor = get_floor(idx)
    resp = await floor_request(floor, "POST", f"/api/machines/{machine_id}/approve")
    if resp.status_code != 200:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    return resp.json()

@app.post("/api/floors/{idx}/machines/{machine_id}/reject")
async def floor_reject(idx: int, machine_id: int):
    floor = get_floor(idx)
    resp = await floor_request(floor, "POST", f"/api/machines/{machine_id}/reject")
    if resp.status_code != 200:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    return resp.json()

@app.post("/api/floors/{idx}/machines/{machine_id}/command")
async def floor_command(idx: int, machine_id: int, body: dict = Body(...)):
    floor = get_floor(idx)
    resp = await floor_request(floor, "POST", f"/api/machines/{machine_id}/command", json=body)
    if resp.status_code >= 400:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    return resp.json()

@app.get("/api/floors/{idx}/machines/{machine_id}/command/{cmd_id}")
async def floor_command_status(idx: int, machine_id: int, cmd_id: int):
    floor = get_floor(idx)
    resp = await floor_request(floor, "GET", f"/api/machines/{machine_id}/command/{cmd_id}")
    if resp.status_code != 200:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    return resp.json()

@app.post("/api/floors/{idx}/machines/{machine_id}/reassign")
async def floor_reassign(idx: int, machine_id: int, body: dict = Body(...)):
    """Moves an already-enrolled, currently-online node from floor `idx`
    to a different floor. Signs the reassignment with the master's own
    topology key. The agent independently verifies both the signature
    and that the target URL is in its own baked-in trusted floor list
    before acting, so a compromised master can only ever move nodes
    between already-known floors, never to an arbitrary server."""
    source_floor = get_floor(idx)
    target_idx = body.get("target_floor_idx")
    if target_idx is None:
        raise HTTPException(status_code=400, detail="target_floor_idx is required")
    target_floor = get_floor(target_idx)
    target_url = target_floor["url"]

    signature = sign_reassignment(target_url)
    resp = await floor_request(source_floor, "POST", f"/api/machines/{machine_id}/command", json={
        "type": "reassign_server",
        "params": {"server_url": target_url},
        "signature": signature,
    })
    if resp.status_code >= 400:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    return resp.json()

# =====================================================================
# NEW: Fleet analytics/savings/command aggregation across all floors.
# Added to match dashboard/src/pages/Fleet.jsx's visual language on the
# master dashboard, using each floor's existing /api/analytics/* and
# /api/fleet/* routes (server/routes/analytics.py, server/routes/fleet.py)
# rather than inventing new fields.
# =====================================================================

@app.get("/api/analytics/fleet")
async def aggregate_fleet_overview():
    floors = get_floors()
    async with httpx.AsyncClient() as client:
        async def fetch(idx, floor):
            try:
                resp = await floor_request(floor, "GET", "/api/analytics/fleet")
                resp.raise_for_status()
                return idx, floor, resp.json(), None
            except Exception as e:
                return idx, floor, None, str(e)
        results = await asyncio.gather(*[fetch(i, f) for i, f in enumerate(floors)])

    ok_results = [(idx, floor, data) for idx, floor, data, err in results if data is not None]
    errors = [{"idx": idx, "name": floor["name"], "error": err}
              for idx, floor, data, err in results if err]

    total    = sum(d["total"]  for _, _, d in ok_results)
    online   = sum(d["online"] for _, _, d in ok_results)
    offline  = sum(d["offline"] for _, _, d in ok_results)

    # Weighted average across floors by each floor's machine count
    def weighted_avg(key):
        weighted_sum = sum(d[key] * d["total"] for _, _, d in ok_results if d["total"] > 0)
        weight_total = sum(d["total"] for _, _, d in ok_results if d["total"] > 0)
        return round(weighted_sum / weight_total, 1) if weight_total > 0 else 0

    machine_scores = []
    for idx, floor, d in ok_results:
        for ms in d["machine_scores"]:
            machine_scores.append({**ms, "floor_idx": idx, "floor_name": floor["name"]})
    machine_scores.sort(key=lambda x: x["score"])

    activity = []
    for idx, floor, d in ok_results:
        for a in d["activity"]:
            activity.append({**a, "floor_idx": idx, "floor_name": floor["name"]})
    activity.sort(key=lambda x: x["timestamp"], reverse=True)
    activity = activity[:20]

    return {
        "total": total, "online": online, "offline": offline,
        "avg_cpu": weighted_avg("avg_cpu"),
        "avg_ram": weighted_avg("avg_ram"),
        "avg_disk": weighted_avg("avg_disk"),
        "critical_alerts": sum(d["critical_alerts"] for _, _, d in ok_results),
        "warning_alerts":  sum(d["warning_alerts"]  for _, _, d in ok_results),
        "commands_24h":    sum(d["commands_24h"]    for _, _, d in ok_results),
        "hours_saved":     sum(d["hours_saved"]      for _, _, d in ok_results),
        "machine_scores": machine_scores,
        "activity": activity,
        "floor_errors": errors,  # floors that failed to report in; not silently dropped
    }

@app.get("/api/analytics/alerts/all")
async def aggregate_all_alerts():
    floors = get_floors()
    async with httpx.AsyncClient() as client:
        async def fetch(idx, floor):
            try:
                resp = await floor_request(floor, "GET", "/api/analytics/alerts/all")
                resp.raise_for_status()
                return [{**a, "floor_idx": idx, "floor_name": floor["name"]} for a in resp.json()]
            except Exception:
                return []
        results = await asyncio.gather(*[fetch(i, f) for i, f in enumerate(floors)])
    combined = [a for floor_alerts in results for a in floor_alerts]
    combined.sort(key=lambda x: x["timestamp"], reverse=True)
    return combined[:100]

@app.post("/api/analytics/alerts/mark-all-read")
async def aggregate_mark_all_read():
    floors = get_floors()
    async def mark(floor):
        try:
            resp = await floor_request(floor, "POST", "/api/analytics/alerts/mark-all-read")
            return resp.status_code == 200
        except Exception:
            return False
    results = await asyncio.gather(*[mark(f) for f in floors])
    return {"ok": all(results)}

@app.get("/api/analytics/savings")
async def aggregate_savings():
    floors = get_floors()
    async def fetch(floor):
        try:
            resp = await floor_request(floor, "GET", "/api/analytics/savings")
            resp.raise_for_status()
            return resp.json()
        except Exception:
            return None
    results = await asyncio.gather(*[fetch(f) for f in floors])
    ok_results = [r for r in results if r is not None]

    weekly_commands  = sum(r["weekly_commands"]  for r in ok_results)
    monthly_commands = sum(r["monthly_commands"] for r in ok_results)
    weekly_hours     = round(sum(r["weekly_hours"]  for r in ok_results), 1)
    monthly_hours    = round(sum(r["monthly_hours"] for r in ok_results), 1)
    weekly_saved     = round(sum(r["weekly_saved"]  for r in ok_results), 2)
    monthly_saved    = round(sum(r["monthly_saved"] for r in ok_results), 2)
    annual_savings   = round(monthly_saved * 12, 2)

    # Same constants each floor server uses (server/routes/analytics.py) —
    # not summed across floors, they're rate/target assumptions, not totals.
    license_cost = ok_results[0]["license_cost"] if ok_results else 65000
    hourly_rate  = ok_results[0]["hourly_rate"]  if ok_results else 45
    payback_months = round(license_cost / monthly_saved, 1) if monthly_saved > 0 else 999

    return {
        "weekly_commands": weekly_commands, "monthly_commands": monthly_commands,
        "weekly_hours": weekly_hours, "monthly_hours": monthly_hours,
        "weekly_saved": weekly_saved, "monthly_saved": monthly_saved,
        "annual_savings": annual_savings, "payback_months": payback_months,
        "license_cost": license_cost, "hourly_rate": hourly_rate,
    }

@app.get("/api/fleet/status")
async def aggregate_fleet_status():
    floors = get_floors()
    async with httpx.AsyncClient() as client:
        results = await asyncio.gather(*[fetch_floor_summary(client, i, f) for i, f in enumerate(floors)])
    return {
        "total":   sum(r["total"]   for r in results),
        "online":  sum(r["online"]  for r in results),
        "offline": sum(r["offline"] for r in results),
    }

@app.post("/api/fleet/command")
async def aggregate_fleet_command(body: dict = Body(...)):
    """Dispatches a fleet command either to every ONLINE machine on every
    reachable floor (default — machine_ids left empty per floor), or to an
    explicit filtered subset via body['targets'] = [{"floor_idx": int,
    "machine_ids": [int, ...]}, ...], built client-side from whatever is
    currently selected on the All Machines page. Targeting reuses the
    existing per-floor DB query (Machine.id.in_(...)) inside
    server/routes/fleet.py's fleet_command — never a per-machine HTTP
    fan-out from master, to avoid the FD-exhaustion pattern seen earlier
    in this project. Fully backward compatible: omitting 'targets'
    preserves the original all-online-machines behavior."""
    floors = get_floors()
    targets = body.get("targets")

    base_payload = {
        "type": body.get("type"),
        "params": body.get("params", {}),
        "passphrase": body.get("passphrase"),
        "script": body.get("script"),
        "signature": body.get("signature"),
    }

    async def dispatch(idx, floor, machine_ids):
        payload = {**base_payload, "machine_ids": machine_ids}
        try:
            resp = await floor_request(floor, "POST", "/api/fleet/command", json=payload)
            if resp.status_code >= 400:
                return {"idx": idx, "name": floor["name"], "ok": False, "error": resp.text}
            data = resp.json()
            return {"idx": idx, "name": floor["name"], "ok": True, **data}
        except Exception as e:
            return {"idx": idx, "name": floor["name"], "ok": False, "error": str(e)}

    if targets:
        target_map = {t["floor_idx"]: t.get("machine_ids", []) for t in targets}
        dispatch_list = [(i, f, target_map[i]) for i, f in enumerate(floors) if i in target_map]
    else:
        dispatch_list = [(i, f, []) for i, f in enumerate(floors)]

    results = await asyncio.gather(*[dispatch(i, f, mids) for i, f, mids in dispatch_list])
    total  = sum(r.get("total", 0)  for r in results if r["ok"])
    sent   = sum(r.get("sent", 0)   for r in results if r["ok"])
    failed = sum(r.get("failed", 0) for r in results if r["ok"]) + sum(1 for r in results if not r["ok"])

    return {"ok": True, "total": total, "sent": sent, "failed": failed, "per_floor": results}

@app.get("/api/floors/{idx}/install-command")
async def floor_install_command(idx: int):
    floor = get_floor(idx)
    resp = await floor_request(floor, "GET", "/api/machines/install-command")
    if resp.status_code != 200:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    return resp.json()

@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")

# =====================================================================
# NEW: Audit Log + Reports parity across all floors.
# =====================================================================

@app.get("/api/analytics/audit/logs")
async def aggregate_audit_logs():
    floors = get_floors()
    async def fetch(idx, floor):
        try:
            resp = await floor_request(floor, "GET", "/api/audit/logs")
            resp.raise_for_status()
            return [{**l, "floor_idx": idx, "floor_name": floor["name"]} for l in resp.json()]
        except Exception:
            return []
    results = await asyncio.gather(*[fetch(i, f) for i, f in enumerate(floors)])
    combined = [l for floor_logs in results for l in floor_logs]
    combined.sort(key=lambda x: x["timestamp"], reverse=True)
    return combined[:200]

@app.get("/api/analytics/commands/history")
async def aggregate_command_history():
    floors = get_floors()
    async def fetch(idx, floor):
        try:
            resp = await floor_request(floor, "GET", "/api/machines/history/all")
            resp.raise_for_status()
            return [{**c, "floor_idx": idx, "floor_name": floor["name"]} for c in resp.json()]
        except Exception:
            return []
    results = await asyncio.gather(*[fetch(i, f) for i, f in enumerate(floors)])
    combined = [c for floor_cmds in results for c in floor_cmds]
    combined.sort(key=lambda x: x["created_at"], reverse=True)
    return combined[:200]

@app.get("/api/analytics/schedules")
async def aggregate_schedules():
    floors = get_floors()
    async def fetch(idx, floor):
        try:
            resp = await floor_request(floor, "GET", "/api/schedules")
            resp.raise_for_status()
            return [{**s, "floor_idx": idx, "floor_name": floor["name"]} for s in resp.json()]
        except Exception:
            return []
    results = await asyncio.gather(*[fetch(i, f) for i, f in enumerate(floors)])
    combined = [s for floor_scheds in results for s in floor_scheds]
    return combined

@app.post("/api/floors/{idx}/schedules")
async def floor_create_schedule(idx: int, body: dict = Body(...)):
    floor = get_floor(idx)
    resp = await floor_request(floor, "POST", "/api/schedules", json=body)
    if resp.status_code >= 400:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    return resp.json()

@app.delete("/api/floors/{idx}/schedules/{schedule_id}")
async def floor_delete_schedule(idx: int, schedule_id: int):
    floor = get_floor(idx)
    resp = await floor_request(floor, "DELETE", f"/api/schedules/{schedule_id}")
    if resp.status_code >= 400:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    return resp.json()

@app.patch("/api/floors/{idx}/schedules/{schedule_id}/toggle")
async def floor_toggle_schedule(idx: int, schedule_id: int):
    floor = get_floor(idx)
    resp = await floor_request(floor, "PATCH", f"/api/schedules/{schedule_id}/toggle")
    if resp.status_code >= 400:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    return resp.json()

PRESETS_FILE = Path(__file__).parent / "presets.json"

def _load_presets() -> list:
    if not PRESETS_FILE.exists():
        return []
    try:
        with open(PRESETS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("presets", [])
    except Exception:
        return []

def _save_presets(presets: list):
    tmp = PRESETS_FILE.with_suffix(".json.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"presets": presets}, f, indent=2)
    tmp.replace(PRESETS_FILE)

ALLOWED_PRESET_TYPES = {"scan", "boost", "clean", "fix", "rollback", "exec"}

@app.get("/api/presets")
async def list_presets():
    return _load_presets()

@app.post("/api/presets")
async def create_preset(body: dict = Body(...)):
    command_type = body.get("command_type", "scan")
    if command_type not in ALLOWED_PRESET_TYPES:
        raise HTTPException(status_code=400, detail=f"Invalid command_type. Allowed: {ALLOWED_PRESET_TYPES}")
    script = body.get("script")
    signature = body.get("signature")
    if command_type == "exec" and (not script or not signature):
        raise HTTPException(status_code=400,
                            detail="'exec' presets require both 'script' and 'signature' "
                                   "(sign offline with tools/sign_script.py first — this server "
                                   "never signs or verifies scripts itself)")
    presets = _load_presets()
    preset = {
        "id":           secrets.token_hex(8),
        "name":         body.get("name") or "Untitled Preset",
        "description":  body.get("description", ""),
        "command_type": command_type,
        "params":       body.get("params") or {},
        "script":       script,
        "signature":    signature,
        "created_at":   time.time(),
    }
    presets.append(preset)
    _save_presets(presets)
    return preset

@app.put("/api/presets/{preset_id}")
async def update_preset(preset_id: str, body: dict = Body(...)):
    presets = _load_presets()
    for p in presets:
        if p["id"] == preset_id:
            command_type = body.get("command_type", p["command_type"])
            if command_type not in ALLOWED_PRESET_TYPES:
                raise HTTPException(status_code=400, detail=f"Invalid command_type. Allowed: {ALLOWED_PRESET_TYPES}")
            script = body.get("script", p.get("script"))
            signature = body.get("signature", p.get("signature"))
            if command_type == "exec" and (not script or not signature):
                raise HTTPException(status_code=400,
                                    detail="'exec' presets require both 'script' and 'signature'")
            p["name"]         = body.get("name", p["name"])
            p["description"]  = body.get("description", p["description"])
            p["command_type"] = command_type
            p["params"]       = body.get("params", p["params"])
            p["script"]       = script
            p["signature"]    = signature
            _save_presets(presets)
            return p
    raise HTTPException(status_code=404, detail="Preset not found")

@app.delete("/api/presets/{preset_id}")
async def delete_preset(preset_id: str):
    presets = _load_presets()
    new_presets = [p for p in presets if p["id"] != preset_id]
    if len(new_presets) == len(presets):
        raise HTTPException(status_code=404, detail="Preset not found")
    _save_presets(new_presets)
    return {"ok": True}

@app.post("/api/presets/{preset_id}/run")
async def run_preset(preset_id: str, body: dict = Body(...)):
    presets = _load_presets()
    preset = next((p for p in presets if p["id"] == preset_id), None)
    if not preset:
        raise HTTPException(status_code=404, detail="Preset not found")
    floor_idx = body.get("floor_idx")
    machine_id = body.get("machine_id")
    if floor_idx is None or machine_id is None:
        raise HTTPException(status_code=400, detail="floor_idx and machine_id are required")
    floor = get_floor(floor_idx)
    command_body = {
        "type":   preset["command_type"],
        "params": preset.get("params") or {},
    }
    if body.get("passphrase"):
        command_body["passphrase"] = body["passphrase"]
    if preset["command_type"] == "exec":
        command_body["script"]    = preset.get("script")
        command_body["signature"] = preset.get("signature")
    resp = await floor_request(floor, "POST", f"/api/machines/{machine_id}/command", json=command_body)
    if resp.status_code >= 400:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    return resp.json()

@app.get("/api/floors/{idx}/audit/logs/verify/{log_id}")
async def floor_verify_log(idx: int, log_id: int):
    floor = get_floor(idx)
    resp = await floor_request(floor, "GET", f"/api/audit/logs/verify/{log_id}")
    if resp.status_code != 200:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    return resp.json()

@app.get("/api/floors/{idx}/audit/logs/export")
async def floor_export_audit_csv(idx: int):
    floor = get_floor(idx)
    resp = await floor_request(floor, "GET", "/api/audit/logs/export")
    if resp.status_code != 200:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    return Response(
        content=resp.content,
        media_type="text/csv",
        headers={"Content-Disposition": resp.headers.get(
            "content-disposition", "attachment; filename=jenix_audit_export.csv")},
    )

@app.get("/api/analytics/reports")
async def aggregate_reports():
    floors = get_floors()
    async def fetch(idx, floor):
        try:
            resp = await floor_request(floor, "GET", "/api/reports")
            resp.raise_for_status()
            return [{**r, "floor_idx": idx, "floor_name": floor["name"]} for r in resp.json()]
        except Exception:
            return []
    results = await asyncio.gather(*[fetch(i, f) for i, f in enumerate(floors)])
    combined = [r for floor_reports in results for r in floor_reports]
    combined.sort(key=lambda x: x["created_at"], reverse=True)
    return combined

@app.post("/api/floors/{idx}/reports/{machine_id}")
async def floor_generate_report(idx: int, machine_id: int):
    floor = get_floor(idx)
    resp = await floor_request(floor, "POST", f"/api/reports/{machine_id}")
    if resp.status_code >= 400:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    return resp.json()

@app.post("/api/floors/{idx}/reports/fleet")
async def floor_generate_fleet_report(idx: int, body: dict = Body(default={})):
    floor = get_floor(idx)
    resp = await floor_request(floor, "POST", "/api/reports/fleet", json=body)
    if resp.status_code >= 400:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    return resp.json()

@app.post("/api/floors/{idx}/reports/audit")
async def floor_generate_audit_report(idx: int):
    floor = get_floor(idx)
    resp = await floor_request(floor, "POST", "/api/reports/audit")
    if resp.status_code >= 400:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    return resp.json()

@app.get("/api/floors/{idx}/reports/{report_id}/download")
async def floor_download_report(idx: int, report_id: int):
    floor = get_floor(idx)
    resp = await floor_request(floor, "GET", f"/api/reports/{report_id}/download")
    if resp.status_code != 200:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    return Response(
        content=resp.content,
        media_type="application/pdf",
        headers={"Content-Disposition": resp.headers.get(
            "content-disposition", "attachment; filename=jenix_report.pdf")},
    )

@app.delete("/api/floors/{idx}/reports/{report_id}")
async def floor_delete_report(idx: int, report_id: int):
    floor = get_floor(idx)
    resp = await floor_request(floor, "DELETE", f"/api/reports/{report_id}")
    if resp.status_code != 200:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    return resp.json()

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
