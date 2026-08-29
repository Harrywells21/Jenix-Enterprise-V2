#!/usr/bin/env python3
"""
JENIX Script Signer — signs a script for the /exec command so an agent
will accept and run it. The private key NEVER leaves this local tool;
only the resulting signature gets pasted into the dashboard.

Usage:
    python3 tools/sign_script.py <path-to-private-key> <path-to-script-file>
    python3 tools/sign_script.py <path-to-private-key> --inline "echo hi"
"""
import sys, base64, json, argparse
from pathlib import Path
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("private_key_path")
    parser.add_argument("script_source", help="path to a script file, or use --inline")
    parser.add_argument("--inline", action="store_true", help="treat script_source as literal script text")
    args = parser.parse_args()

    priv_b64 = Path(args.private_key_path).read_text().strip()
    private_key = Ed25519PrivateKey.from_private_bytes(base64.b64decode(priv_b64))

    script = args.script_source if args.inline else Path(args.script_source).read_text()

    payload = json.dumps({"type": "exec", "script": script}, sort_keys=True, separators=(",", ":")).encode()
    signature = base64.b64encode(private_key.sign(payload)).decode()

    print("=" * 60)
    print("SCRIPT (paste into dashboard 'Run Signed Script' box):")
    print("-" * 60)
    print(script)
    print("=" * 60)
    print("SIGNATURE (paste into signature field):")
    print("-" * 60)
    print(signature)
    print("=" * 60)

if __name__ == "__main__":
    main()
