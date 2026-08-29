"""
JENIX Topology Command Signature Verification
Used only for reassign_server — moving an already-enrolled node from
one floor to another. Deliberately a SEPARATE keypair from the fleet
exec key (agent/fleet_auth.py): this key lives on the master control
plane and signs reassignments automatically, so it is treated as
lower-trust than the buyer's offline exec key. To bound the blast
radius if it is ever compromised, the agent will only accept a
reassignment to a URL present in its own baked-in trusted floor list
(agent/_topology_floors_baked.py) — never an arbitrary URL, even with
a technically valid signature.
"""
import base64
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from cryptography.exceptions import InvalidSignature

try:
    from _topology_key_baked import TOPOLOGY_PUBLIC_KEY_B64
except ImportError:
    TOPOLOGY_PUBLIC_KEY_B64 = ""

try:
    from _topology_floors_baked import TRUSTED_FLOOR_URLS
except ImportError:
    TRUSTED_FLOOR_URLS = []

def _load_public_key():
    if not TOPOLOGY_PUBLIC_KEY_B64:
        return None
    try:
        raw = base64.b64decode(TOPOLOGY_PUBLIC_KEY_B64)
        return Ed25519PublicKey.from_public_bytes(raw)
    except Exception:
        return None

def verify_signature(payload_bytes: bytes, signature_b64: str) -> bool:
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

def _normalize(url: str) -> str:
    return url.strip().rstrip("/").lower()

def is_trusted_floor(url: str) -> bool:
    target = _normalize(url)
    return target in {_normalize(u) for u in TRUSTED_FLOOR_URLS}

def topology_signing_enabled() -> bool:
    return bool(TOPOLOGY_PUBLIC_KEY_B64) and bool(TRUSTED_FLOOR_URLS)
