"""
JENIX Fleet Command Signature Verification
Agents use this to verify a fleet-wide command was signed by the buyer's
own master private key before executing it. The agent never has access
to the private key — only this baked-in public key.

FLEET_PUBLIC_KEY_B64 gets set at install/build time (see tools/jenix_keygen.py).
Leave it empty to disable fleet-signed command support on this agent.
"""
import base64
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from cryptography.exceptions import InvalidSignature

try:
    from _fleet_key_baked import FLEET_PUBLIC_KEY_B64
except ImportError:
    FLEET_PUBLIC_KEY_B64 = ""  # no key baked in — fleet signing disabled

def _load_public_key():
    if not FLEET_PUBLIC_KEY_B64:
        return None
    try:
        raw = base64.b64decode(FLEET_PUBLIC_KEY_B64)
        return Ed25519PublicKey.from_public_bytes(raw)
    except Exception:
        return None

def verify_signature(payload_bytes: bytes, signature_b64: str) -> bool:
    """True only if signature_b64 is a valid Ed25519 signature of
    payload_bytes made by the buyer's master private key."""
    pubkey = _load_public_key()
    if pubkey is None:
        return False
    try:
        sig = base64.b64decode(signature_b64)
    except Exception:
        return False
    try:
        pubkey.verify(sig, payload_bytes)
        return True
    except InvalidSignature:
        return False
    except Exception:
        return False

def fleet_signing_enabled() -> bool:
    return bool(FLEET_PUBLIC_KEY_B64)
