#!/usr/bin/env python3
import asyncio, json, os, sys, signal
import websockets
from pathlib import Path

TOKEN_FILE   = Path.home() / ".jenix" / "agent.token"
MACHINE_FILE = Path.home() / ".jenix" / "agent.machine_id"
SERVER_URL   = os.getenv("JENIX_SERVER", "http://localhost:8000")
WS_URL       = SERVER_URL.replace("http://", "ws://").replace("https://", "wss://")
METRICS_INTERVAL = 2
RECONNECT_DELAY  = 5

_stop = False

def register_with_server() -> tuple[str, int]:
    import urllib.request
    from collector import get_system_info

    if TOKEN_FILE.exists() and MACHINE_FILE.exists():
        token      = TOKEN_FILE.read_text().strip()
        machine_id = int(MACHINE_FILE.read_text().strip())
        print(f"[agent] Using cached token: {token[:8]}... machine_id={machine_id}")
        return token, machine_id

    info    = get_system_info()
    payload = json.dumps(info).encode()
    req     = urllib.request.Request(
        f"{SERVER_URL}/api/machines/register",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    print(f"[agent] Registering with server: {SERVER_URL}")
    with urllib.request.urlopen(req, timeout=10) as resp:
        data       = json.loads(resp.read())
        token      = data["token"]
        machine_id = data["machine_id"]

    TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    TOKEN_FILE.write_text(token)
    MACHINE_FILE.write_text(str(machine_id))
    print(f"[agent] Registered — machine_id={machine_id} token={token[:8]}...")
    return token, machine_id

async def run_agent(token: str):
    from collector import collect_metrics
    from executor  import execute_command

    uri = f"{WS_URL}/ws/agent/{token}"
    print(f"[agent] Connecting to {uri}")

    try:
        collect_metrics()
    except Exception:
        pass

    async with websockets.connect(uri, ping_interval=20,
                                       ping_timeout=10) as ws:
        print("[agent] Connected ✅")

        # Send register message so server creates the node in DB
        from collector import get_system_info
        info = get_system_info()
        await ws.send(json.dumps({
            "type":      "register",
            "node_name": info.get("hostname", "unknown"),
            "os_type":   info.get("os_type", "Linux"),
            "os_info": {
                "hostname":  info.get("hostname", ""),
                "os_pretty": info.get("os_pretty", info.get("os_type", "Linux")),
            }
        }))
        print("[agent] Register message sent ✅")

        # Capture the running event loop here — in the async context
        loop = asyncio.get_running_loop()

        async def _send(payload: dict):
            try:
                await ws.send(json.dumps(payload))
            except Exception as e:
                print(f"[agent] send error: {e}")

        def _sync_send(payload: dict):
            # Safe to call from any thread — uses captured loop
            asyncio.run_coroutine_threadsafe(_send(payload), loop)

        async def _metrics_loop():
            while True:
                try:
                    metrics = collect_metrics()
                    await _send(metrics)
                except Exception as e:
                    print(f"[agent] metrics error: {e}")
                await asyncio.sleep(METRICS_INTERVAL)

        async def _recv_loop():
            async for raw in ws:
                try:
                    data     = json.loads(raw)
                    cmd_type = data.get("command") or data.get("cmd")
                    cmd_id   = data.get("command_id") or data.get("cmd_id")
                    params   = data.get("params") or {}
                    if "script" in data:
                        params["script"] = data["script"]
                    if "signature" in data:
                        params["signature"] = data["signature"]
                    if cmd_type and cmd_id:
                        print(f"[agent] Received command: {cmd_type} (id={cmd_id})")
                        execute_command(cmd_type, cmd_id, _sync_send, params)
                    elif data.get("type") == "pong":
                        pass
                except Exception as e:
                    print(f"[agent] recv error: {e}")

        await asyncio.gather(_metrics_loop(), _recv_loop())

async def main():
    while not _stop:
        try:
            token, _ = register_with_server()
            break
        except Exception as e:
            print(f"[agent] Registration failed: {e} — retrying in {RECONNECT_DELAY}s")
            await asyncio.sleep(RECONNECT_DELAY)

    while not _stop:
        try:
            await run_agent(token)
        except Exception as e:
            print(f"[agent] Disconnected: {e} — reconnecting in {RECONNECT_DELAY}s")
        await asyncio.sleep(RECONNECT_DELAY)

async def _run_with_signal_handling():
    loop = asyncio.get_running_loop()
    main_task = asyncio.ensure_future(main())

    _shutdown_requested = False
    def _request_shutdown():
        global _stop
        nonlocal _shutdown_requested
        if _shutdown_requested:
            return
        _shutdown_requested = True
        _stop = True
        print("[agent] Shutdown signal received — cancelling tasks")
        main_task.cancel()

    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, _request_shutdown)

    try:
        await main_task
    except asyncio.CancelledError:
        print("[agent] Shutdown complete — exiting cleanly")

if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(__file__))
    asyncio.run(_run_with_signal_handling())
