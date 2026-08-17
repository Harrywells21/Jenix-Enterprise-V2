import asyncio, json
from sqlalchemy.orm.exc import StaleDataError, ObjectDeletedError
from fastapi import WebSocket, WebSocketDisconnect
from datetime import datetime
from typing import Dict

_agents:     Dict[str, WebSocket] = {}
_dashboards: list[WebSocket]      = []

async def agent_endpoint(websocket: WebSocket, token: str):
    from db import SessionLocal, Machine, Metric, Alert
    from notifications import notify_critical_alert
    from alert_cooldown import should_create_alert

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

    print(f"[WS] Agent connected: {hostname} (id={machine_id})")

    try:
        while True:
            raw      = await websocket.receive_text()
            data     = json.loads(raw)
            msg_type = data.get("type")

            if msg_type == "metrics":
                db = SessionLocal()
                try:
                    m = db.query(Machine)\
                          .filter(Machine.token == token).first()
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

                        cpu  = data.get("cpu",  0)
                        ram  = data.get("ram",  0)
                        disk = data.get("disk", 0)
                        alerts_to_add = []

                        # CPU alert with cooldown
                        if cpu > 85 and should_create_alert(m.id, "cpu"):
                            level = "critical" if cpu > 95 else "warning"
                            alerts_to_add.append(Alert(
                                machine_id=m.id, level=level,
                                type="cpu",
                                message=f"CPU at {cpu:.1f}% on {m.hostname}"))
                            if cpu > 95:
                                asyncio.create_task(asyncio.to_thread(
                                    notify_critical_alert,
                                    m.hostname, "cpu",
                                    f"CPU at {cpu:.1f}%"))

                        # RAM alert with cooldown
                        if ram > 85 and should_create_alert(m.id, "ram"):
                            level = "critical" if ram > 95 else "warning"
                            alerts_to_add.append(Alert(
                                machine_id=m.id, level=level,
                                type="ram",
                                message=f"RAM at {ram:.1f}% on {m.hostname}"))

                        # Disk alert with cooldown
                        if disk > 90 and should_create_alert(m.id, "disk"):
                            alerts_to_add.append(Alert(
                                machine_id=m.id, level="critical",
                                type="disk",
                                message=f"Disk at {disk:.1f}% on {m.hostname}"))
                            asyncio.create_task(asyncio.to_thread(
                                notify_critical_alert,
                                m.hostname, "disk",
                                f"Disk at {disk:.1f}%"))

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

            elif msg_type == "command_result":
                cmd_id = data.get("command_id")
                result = data.get("data", {})
                exit_code = result.get("exit_code", -1)
                output_lines = result.get("output", [])
                output_text = "\n".join(output_lines) if isinstance(output_lines, list) else str(output_lines)
                status = "completed" if exit_code == 0 else "failed"
                db = SessionLocal()
                try:
                    from db import Command
                    cmd = db.query(Command)\
                            .filter(Command.id == cmd_id).first()
                    if cmd:
                        cmd.output     = output_text
                        cmd.status     = status
                        cmd.updated_at = datetime.utcnow()
                        db.commit()
                    await _broadcast_dashboards({
                        "type":      "command_result",
                        "cmd_id":    cmd_id,
                        "output":    output_text,
                        "status":    status,
                        "exit_code": exit_code,
                    })
                finally:
                    db.close()

            elif msg_type == "cmd_output":
                cmd_id       = data.get("cmd_id")
                output_chunk = data.get("output", "")
                status       = data.get("status", "running")
                db = SessionLocal()
                try:
                    from db import Command
                    cmd = db.query(Command)\
                            .filter(Command.id == cmd_id).first()
                    if cmd:
                        cmd.output     = (cmd.output or "") + output_chunk
                        cmd.status     = status
                        cmd.updated_at = datetime.utcnow()
                        db.commit()
                    await _broadcast_dashboards({
                        "type":   "command_result",
                        "cmd_id": cmd_id,
                        "output": output_chunk,
                        "status": status,
                    })
                finally:
                    db.close()

            elif msg_type == "snapshot":
                db = SessionLocal()
                try:
                    from db import Snapshot
                    m = db.query(Machine).filter(Machine.token == token).first()
                    if m:
                        db.merge(Snapshot(
                            id=data.get("snapshot_id"),
                            machine_id=m.id,
                            reason=data.get("reason", ""),
                        ))
                        db.commit()
                        await _broadcast_dashboards({
                            "type": "snapshot_created",
                            "machine_id": m.id,
                            "snapshot_id": data.get("snapshot_id"),
                            "reason": data.get("reason", ""),
                        })
                finally:
                    db.close()

            elif msg_type == "ping":
                await websocket.send_text(json.dumps({"type":"pong"}))

    except WebSocketDisconnect:
        pass
    except Exception as e:
        print(f"[WS] Agent error: {e}")
    finally:
        _agents.pop(token, None)
        db = SessionLocal()
        try:
            try:
                m = db.query(Machine)\
                      .filter(Machine.token == token).first()
                if m:
                    m.status = "offline"
                    db.commit()
                    from notifications import notify_machine_offline
                    from alert_cooldown import should_create_alert
                    if should_create_alert(m.id, "offline"):
                        asyncio.create_task(asyncio.to_thread(
                            notify_machine_offline, m.hostname, m.ip))
                    await _broadcast_dashboards({
                        "type":       "status",
                        "machine_id": m.id,
                        "status":     "offline",
                    })
            except (StaleDataError, ObjectDeletedError):
                db.rollback()
                print(f"[WS] Machine already removed before disconnect cleanup, skipping")

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
    from alert_cooldown import should_create_alert
    while True:
        await asyncio.sleep(30)
        db = SessionLocal()
        try:
            cutoff = datetime.utcnow() - timedelta(seconds=35)
            stale  = db.query(Machine).filter(
                Machine.status   == "online",
                Machine.last_seen < cutoff
            ).all()
            for m in stale:
                m.status = "offline"
                if should_create_alert(m.id, "offline"):
                    db.add(Alert(
                        machine_id=m.id, level="critical",
                        type="offline",
                        message=f"{m.hostname} went offline"))
                    asyncio.create_task(asyncio.to_thread(
                        notify_machine_offline, m.hostname, m.ip))
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
