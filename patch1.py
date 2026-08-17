import sys

def patch(path, replacements):
    with open(path, "r") as f:
        content = f.read()
    for old, new, label in replacements:
        count = content.count(old)
        if count != 1:
            print(f"FAILED on {path} [{label}]: found {count} occurrences (expected 1)")
            print("---- looking for ----")
            print(old)
            sys.exit(1)
        content = content.replace(old, new)
    with open(path, "w") as f:
        f.write(content)
    print(f"Patched {path} OK ({len(replacements)} change(s))")

# ---- Bug 1: server/routes/agents.py ----
agents_replacements = [
    (
'''    if existing:
        existing.os_name   = body.os_name
        existing.kernel    = body.kernel
        existing.status    = "online"
        existing.last_seen = datetime.utcnow()
        db.commit()
        return {"token": existing.token, "machine_id": existing.id}''',
'''    if existing:
        existing.os_name   = body.os_name
        existing.kernel    = body.kernel
        existing.status    = "offline"  # WS handler (agent_endpoint) sets "online" once truly connected
        existing.last_seen = datetime.utcnow()
        db.commit()
        return {"token": existing.token, "machine_id": existing.id}''',
        "existing-machine register status"
    ),
    (
'''    machine = Machine(
        hostname=body.hostname, ip=body.ip,
        os_name=body.os_name,  kernel=body.kernel,
        token=token, status="online"
    )''',
'''    machine = Machine(
        hostname=body.hostname, ip=body.ip,
        os_name=body.os_name,  kernel=body.kernel,
        token=token, status="offline"  # WS handler (agent_endpoint) sets "online" once truly connected
    )''',
        "new-machine register status"
    ),
]
patch("server/routes/agents.py", agents_replacements)

# ---- Bug 2: server/ws/handler.py ----
handler_replacements = [
    (
'''                finally:
                    db.close()

            elif msg_type == "snapshot":''',
'''                finally:
                    db.close()

            elif msg_type == "cmd_output":
                cmd_id       = data.get("cmd_id")
                output_chunk = data.get("output", "")
                status       = data.get("status", "running")
                db = SessionLocal()
                try:
                    from db import Command
                    cmd = db.query(Command)\\
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

            elif msg_type == "snapshot":''',
        "cmd_output handler branch"
    ),
]
patch("server/ws/handler.py", handler_replacements)

print("ALL PATCHES APPLIED")
