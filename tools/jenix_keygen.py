#!/usr/bin/env python3
"""
JENIX Fleet Master Key Generator
Run this ONCE at deployment. Generates an Ed25519 keypair.

The PRIVATE key stays with the buyer/admin and signs fleet-wide commands
from their own tooling. JENIX's server never sees or stores it.

The PUBLIC key gets baked into the agent installer at build time so every
agent can independently verify a command's signature before executing it.
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

    priv_path = out_dir / "jenix_fleet_private.key"
    pub_path = out_dir / "jenix_fleet_public.key"

    priv_path.write_text(priv_b64 + "\n")
    pub_path.write_text(pub_b64 + "\n")
    priv_path.chmod(0o600)

    print(f"[jenix-keygen] Private key: {priv_path} (mode 600 — keep secret, never commit, never send to JENIX)")
    print(f"[jenix-keygen] Public key:  {pub_path} (bake this into the agent installer)")
    print()
    print(f"Public key (base64): {pub_b64}")

if __name__ == "__main__":
    main()
