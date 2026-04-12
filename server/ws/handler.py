import asyncio, json
from fastapi import WebSocket, WebSocketDisconnect
from datetime import datetime
from typing import Dict

_agents:     Dict[str, WebSocket] = {}
_dashboards: list[WebSocket]      = []

async def agent_endpoint(websocket: WebSocket, token: str):
    from db import SessionLocal, Machine, Metric, Alert
    from notifications import notify_critical_alert

    await websocket.accept()
    _agents[token] = websocket

    db = SessionLocal()
    try:
        m = db.query(Machine).filter(Machine.token == token).first()
        if not m:
            await websocket.close(code=4001)
            return
        m.status    = "online"
        m.last_seen = datetime.utcnow()
        db.commit()
        machine_id = m.id
        hostname   = m.hostname
    finally:
        db.close()

    print(f"[WS] Agent connected: {hostname} (machine_id={machine_id})")

    try:
        while True:
            raw  = await websocket.receive_text()
            data = json.loads(raw)
            msg_type = data.get("type")

            if msg_type == "metrics":
                db = SessionLocal()
                try:
                    m = db.query(Machine).filter(Machine.token == token).first()
                    if m:
                        m.last_seen = datetime.utcnow()
                        m.status    = "online"
                        metric = Metric(
                            machine_id = m.id,
                            cpu        = data.get("cpu",     0.0),
                            ram        = data.get("ram",     0.0),
                            disk       = data.get("disk",    0.0),
                            net_mb     = data.get("net_mb",  0.0),
                            disk_mb    = data.get("disk_mb", 0.0),
                        )
                        db.add(metric)

                        # Alert checks with notifications
                        alerts_to_add = []
                        cpu  = data.get("cpu",  0)
                        ram  = data.get("ram",  0)
                        disk = data.get("disk", 0)

                        if cpu > 85:
                            alerts_to_add.append(Alert(
                                machine_id=m.id, level="warning",
                                type="cpu",
                                message=f"CPU at {cpu:.1f}%"))
                            if cpu > 95:
                                asyncio.create_task(
                                    asyncio.to_thread(
                                        notify_critical_alert,
                                        m.hostname, "cpu",
                                        f"CPU at {cpu:.1f}%"
                                    ))
                        if ram > 85:
                            alerts_to_add.append(Alert(
                                machine_id=m.id, level="warning",
                                type="ram",
                                message=f"RAM at {ram:.1f}%"))
                        if disk > 90:
                            alerts_to_add.append(Alert(
                                machine_id=m.id, level="critical",
                                type="disk",
                                message=f"Disk at {disk:.1f}%"))
                            asyncio.create_task(
                                asyncio.to_thread(
                                    notify_critical_alert,
                                    m.hostname, "disk",
                                    f"Disk at {disk:.1f}%"
                                ))

                        for a in alerts_to_add:
                            db.add(a)
                        db.commit()

                        await _broadcast_dashboards({
                            "type":       "metrics",
                            "machine_id": m.id,
                            "hostname":   m.hostname,
                            "cpu":        cpu,
                            "ram":        ram,
                            "disk":       disk,
                            "net_mb":     data.get("net_mb",  0.0),
                            "disk_mb":    data.get("disk_mb", 0.0),
                            "timestamp":  datetime.utcnow().isoformat(),
                        })
                finally:
                    db.close()

            elif msg_type == "cmd_output":
                cmd_id = data.get("cmd_id")
                output = data.get("output", "")
                status = data.get("status", "running")
                db = SessionLocal()
                try:
                    from db import Command
                    cmd = db.query(Command)\
                            .filter(Command.id == cmd_id).first()
                    if cmd:
                        cmd.output    += output
                        cmd.status     = status
                        cmd.updated_at = datetime.utcnow()
                        db.commit()
                    await _broadcast_dashboards({
                        "type":   "cmd_output",
                        "cmd_id": cmd_id,
                        "output": output,
                        "status": status,
                    })
                finally:
                    db.close()

            elif msg_type == "ping":
                await websocket.send_text(json.dumps({"type": "pong"}))

    except WebSocketDisconnect:
        pass
    except Exception as e:
        print(f"[WS] Agent error: {e}")
    finally:
        _agents.pop(token, None)
        db = SessionLocal()
        try:
            m = db.query(Machine).filter(Machine.token == token).first()
            if m:
                m.status = "offline"
                db.commit()
                from notifications import notify_machine_offline
                asyncio.create_task(
                    asyncio.to_thread(
                        notify_machine_offline, m.hostname, m.ip
                    ))
                await _broadcast_dashboards({
                    "type":       "status",
                    "machine_id": m.id,
                    "status":     "offline",
                })
        finally:
            db.close()
        print(f"[WS] Agent disconnected: {hostname}")

async def dashboard_endpoint(websocket: WebSocket):
    await websocket.accept()
    _dashboards.append(websocket)
    print(f"[WS] Dashboard connected — total: {len(_dashboards)}")
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        if websocket in _dashboards:
            _dashboards.remove(websocket)

async def send_command(token: str, payload: dict) -> bool:
    ws = _agents.get(token)
    if not ws:
        return False
    try:
        await ws.send_text(json.dumps(payload))
        return True
    except Exception as e:
        print(f"[WS] send_command error: {e}")
        return False

async def _broadcast_dashboards(payload: dict):
    dead = []
    for ws in _dashboards:
        try:
            await ws.send_text(json.dumps(payload))
        except Exception:
            dead.append(ws)
    for ws in dead:
        if ws in _dashboards:
            _dashboards.remove(ws)

async def offline_watchdog():
    from db import SessionLocal, Machine, Alert
    from datetime import timedelta
    from notifications import notify_machine_offline
    while True:
        await asyncio.sleep(30)
        db = SessionLocal()
        try:
            cutoff = datetime.utcnow() - timedelta(seconds=35)
            stale  = db.query(Machine).filter(
                Machine.status == "online",
                Machine.last_seen < cutoff
            ).all()
            for m in stale:
                m.status = "offline"
                db.add(Alert(
                    machine_id=m.id, level="critical",
                    type="offline",
                    message=f"{m.hostname} went offline"))
                asyncio.create_task(
                    asyncio.to_thread(
                        notify_machine_offline, m.hostname, m.ip
                    ))
                await _broadcast_dashboards({
                    "type":       "status",
                    "machine_id": m.id,
                    "status":     "offline",
                })
            if stale:
                db.commit()
        except Exception as e:
            print(f"[watchdog] error: {e}")
        finally:
            db.close()
