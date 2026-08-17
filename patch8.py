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

fleet_replacements = [
    (
'''router = APIRouter(prefix="/fleet", tags=["fleet"])

ALLOWED = {"scan", "boost", "clean", "fix", "rollback"}

class FleetCommand(BaseModel):
    type:       str
    machine_ids: list[int] = []  # empty = all online machines
    params:     dict = {}''',
'''router = APIRouter(prefix="/fleet", tags=["fleet"])

ALLOWED = {"scan", "boost", "clean", "fix", "rollback"}
GATED   = {"boost", "clean", "fix", "rollback"}  # require node action passphrase, if one is set

class FleetCommand(BaseModel):
    type:       str
    machine_ids: list[int] = []  # empty = all online machines
    params:     dict = {}
    passphrase: str | None = None  # applied uniformly; machines with a different/no passphrase set are skipped, not bypassed''',
        "add GATED set + passphrase field",
    ),
    (
'''    results = []
    for m in machines:
        cmd = Command(''',
'''    from db import verify_passphrase
    results = []
    skipped_gated = []
    for m in machines:
        if body.type in GATED and m.action_passphrase_hash:
            if not body.passphrase or not verify_passphrase(body.passphrase, m.action_passphrase_hash):
                log = AuditLog(
                    machine_id = m.id,
                    user_id    = current_user.id,
                    action     = f"fleet_{body.type}_denied",
                    detail     = f"Fleet passphrase check failed for '{body.type}' on {m.hostname} by {current_user.name}",
                    status     = "critical"
                )
                db.add(log); db.commit()
                skipped_gated.append({"machine_id": m.id, "hostname": m.hostname,
                                       "reason": "passphrase required or incorrect"})
                continue
        cmd = Command(''',
        "skip gated machines that fail passphrase check",
    ),
    (
'''    return {
        "ok":           True,
        "total":        len(results),
        "sent":         sent_count,
        "failed":       failed_count,
        "results":      results,
    }''',
'''    return {
        "ok":            True,
        "total":         len(results),
        "sent":          sent_count,
        "failed":        failed_count,
        "results":       results,
        "skipped_gated": skipped_gated,
    }''',
        "surface skipped machines in response",
    ),
]

patch("server/routes/fleet.py", fleet_replacements)

import ast
ast.parse(open("server/routes/fleet.py").read())
print("syntax OK")
