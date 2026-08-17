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

# ---- agent/executor.py ----
executor_replacements = [
    (
'''    if cmd_type in ("boost", "clean", "fix") and not sudo_available():
        send_fn({"type": "cmd_output", "cmd_id": cmd_id,
                 "output": "[JENIX] Passwordless sudo is not configured on this machine. "
                           "This command requires elevated privileges. See setup docs for the required sudoers rule.\\n",
                 "status": "failed"})
        return

    if cmd_type in ("clean", "fix") and shutil.which("apt-get") is None:''',
'''    if cmd_type in ("clean", "fix") and shutil.which("apt-get") is None:''',
        "remove flawed blanket sudo_available() precheck - scoped sudo -n calls in COMMAND_MAP already handle real permission errors correctly"
    ),
]
patch("agent/executor.py", executor_replacements)

# ---- agent/snapshot.py ----
snapshot_replacements = [
    (
'''    log(f"[ROLLBACK] Restoring point {snap_id} — taken {data['created_at']} ({data['reason']})\\n")

    if not sudo_available():
        log("[ROLLBACK] Passwordless sudo is not configured on this machine — "
            "cannot restore sysctl/package state. See setup docs for the required sudoers rule.\\n")
        return False

    for key, val in (data.get("sysctl") or {}).items():''',
'''    log(f"[ROLLBACK] Restoring point {snap_id} — taken {data['created_at']} ({data['reason']})\\n")

    for key, val in (data.get("sysctl") or {}).items():''',
        "remove flawed blanket sudo_available() precheck - individual sudo -n calls below already report real errors correctly"
    ),
]
patch("agent/snapshot.py", snapshot_replacements)

print("ALL PATCHES APPLIED")
