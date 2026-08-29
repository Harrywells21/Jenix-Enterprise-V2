#!/usr/bin/env python3
"""
JENIX Topology Key + Trusted-Floor-List Baking Tool

Run BEFORE building the agent with PyInstaller, once per deployment,
and again any time floors.json's floor list changes (floor added,
removed, or re-IP'd). Bakes into the agent:
  - the topology PUBLIC key   -> agent/_topology_key_baked.py
  - the trusted floor URLs    -> agent/_topology_floors_baked.py

The topology PRIVATE key never goes near this bake step or the agent
binary — it stays on the master control plane only.

Usage:
  python3 tools/bake_topology.py <topology_public_key_path_or_b64> <floors.json_path>

After running this, rebuild:
  cd agent && pyinstaller JenixAgentCLI.spec --clean
"""
import sys, json, base64
from pathlib import Path

AGENT_DIR         = Path(__file__).resolve().parent.parent / "agent"
KEY_BAKED_FILE     = AGENT_DIR / "_topology_key_baked.py"
FLOORS_BAKED_FILE  = AGENT_DIR / "_topology_floors_baked.py"

def resolve_key(arg: str) -> str:
    p = Path(arg)
    return p.read_text().strip() if p.exists() else arg.strip()

def validate_b64_ed25519_pubkey(b64_str: str) -> bool:
    try:
        decoded = base64.b64decode(b64_str, validate=True)
    except Exception:
        return False
    return len(decoded) == 32

def main():
    if len(sys.argv) != 3:
        print("Usage: python3 bake_topology.py <topology_public_key_path_or_b64> <floors.json_path>")
        sys.exit(1)

    key_arg, floors_path = sys.argv[1], sys.argv[2]
    key_b64 = resolve_key(key_arg)
    if not validate_b64_ed25519_pubkey(key_b64):
        print("[bake_topology] ERROR: not a valid 32-byte base64 Ed25519 public key. Refusing to bake.")
        sys.exit(1)

    floors = json.loads(Path(floors_path).read_text())
    urls = sorted({f["url"].strip().rstrip("/") for f in floors if f.get("url")})
    if not urls:
        print("[bake_topology] ERROR: no floor URLs found in floors.json — refusing to bake an empty allowlist.")
        sys.exit(1)

    if not AGENT_DIR.exists():
        print(f"[bake_topology] ERROR: agent dir not found at {AGENT_DIR}")
        sys.exit(1)

    KEY_BAKED_FILE.write_text(
        f'TOPOLOGY_PUBLIC_KEY_B64 = "{key_b64}"  '
        f'# baked by tools/bake_topology.py — buyer-specific, do not commit\n'
    )
    FLOORS_BAKED_FILE.write_text(
        '# baked by tools/bake_topology.py from floors.json — buyer-specific, do not commit\n'
        '# rebake + rebuild any time floors.json changes (floor added/removed/re-IP\'d)\n'
        f'TRUSTED_FLOOR_URLS = {json.dumps(urls, indent=4)}\n'
    )

    print(f"[bake_topology] Wrote {KEY_BAKED_FILE}")
    print(f"[bake_topology] Wrote {FLOORS_BAKED_FILE} with {len(urls)} trusted floor URL(s):")
    for u in urls:
        print(f"    - {u}")
    print()
    print("[bake_topology] Next step: cd agent && pyinstaller JenixAgentCLI.spec --clean")

if __name__ == "__main__":
    main()
