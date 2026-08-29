#!/usr/bin/env python3
"""
JENIX Topology Key Generator — separate from the fleet exec key.

This keypair signs ONLY reassign_server commands (moving an enrolled
node from one floor to another). The PRIVATE key lives on the master
control plane (master/topology_private.key) and is used by
master_server.py to auto-sign reassignments so the dashboard action is
genuinely one-click. Blast radius if this key ever leaks is bounded by
each agent's baked-in trusted floor allowlist (see tools/bake_topology.py)
— it can only ever move nodes between already-known floors, never to an
arbitrary URL.

Run ONCE per deployment.
"""
import sys, base64
from pathlib import Path
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization

def main():
    out_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".")
    out_dir.mkdir(parents=True, exist_ok=True)

    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key()

    priv_bytes = private_key.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption(),
    )
    pub_bytes = public_key.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )

    priv_b64 = base64.b64encode(priv_bytes).decode()
    pub_b64 = base64.b64encode(pub_bytes).decode()

    priv_path = out_dir / "jenix_topology_private.key"
    pub_path = out_dir / "jenix_topology_public.key"

    priv_path.write_text(priv_b64 + "\n")
    pub_path.write_text(pub_b64 + "\n")
    priv_path.chmod(0o600)

    print(f"[topology-keygen] Private key: {priv_path} (mode 600 — this goes on the MASTER server only, master/topology_private.key)")
    print(f"[topology-keygen] Public key:  {pub_path} (bake this into agents with tools/bake_topology.py)")
    print()
    print(f"Public key (base64): {pub_b64}")

if __name__ == "__main__":
    main()
