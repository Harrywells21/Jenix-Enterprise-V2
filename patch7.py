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

snapshot_replacements = [
    (
'''            r = subprocess.run(["sudo", "-n", "sysctl", "-w", f"{key}={val}"],
                                stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=5)''',
'''            r = subprocess.run(["sudo", "-n", "/usr/local/sbin/jenix-sysctl-restore", key, val],
                                stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=5)''',
        "rollback sysctl restore uses wrapper",
    ),
    (
'''                r = subprocess.run(["sudo", "-n", "apt-get", "install", "-y"] + missing,
                                    stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=300)''',
'''                r = subprocess.run(["sudo", "-n", "/usr/local/sbin/jenix-apt-reinstall"] + missing,
                                    stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=300)''',
        "rollback package reinstall uses wrapper",
    ),
]

executor_replacements = [
    (
'''    "boost": "echo '[BOOST] Applying performance boost...' && "
             "sudo -n sysctl -w vm.swappiness=10 && "
             "sudo -n sysctl -w net.core.rmem_max=16777216 && "
             "echo '[BOOST] Done.'",''',
'''    "boost": "echo '[BOOST] Applying performance boost...' && "
             "sudo -n /usr/local/sbin/jenix-sysctl-restore vm.swappiness 10 && "
             "sudo -n /usr/local/sbin/jenix-sysctl-restore net.core.rmem_max 16777216 && "
             "echo '[BOOST] Done.'",''',
        "boost uses same wrapper as rollback (single mechanism)",
    ),
]

patch("agent/snapshot.py", snapshot_replacements)
patch("agent/executor.py", executor_replacements)

import ast
for f in ["agent/executor.py", "agent/snapshot.py"]:
    ast.parse(open(f).read())
print("syntax OK")
