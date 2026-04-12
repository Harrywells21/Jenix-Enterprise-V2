"""
JENIX License System — generates and validates perpetual license keys.
"""
import hashlib, json, base64, os
from datetime import datetime
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

SECRET = os.getenv("SECRET_KEY", "jenix_secret")

def generate_license(company_name: str, max_nodes: int = -1,
                     is_perpetual: bool = True) -> str:
    payload = {
        "company":    company_name,
        "max_nodes":  max_nodes,
        "perpetual":  is_perpetual,
        "issued_at":  datetime.utcnow().isoformat(),
    }
    data     = json.dumps(payload, sort_keys=True)
    sig      = hashlib.sha256(f"{data}{SECRET}".encode()).hexdigest()[:16]
    encoded  = base64.b64encode(data.encode()).decode()
    return f"JENIX-{encoded}-{sig}".upper()

def validate_license(key: str) -> dict:
    try:
        key = key.strip()
        if not key.startswith("JENIX-"):
            return {"valid": False, "error": "Invalid key format"}
        parts = key[6:].rsplit("-", 1)
        if len(parts) != 2:
            return {"valid": False, "error": "Malformed key"}
        encoded, sig = parts
        data    = base64.b64decode(encoded.encode()).decode()
        expected = hashlib.sha256(
            f"{data}{SECRET}".encode()).hexdigest()[:16].upper()
        if sig != expected:
            return {"valid": False, "error": "Invalid signature"}
        payload = json.loads(data)
        return {
            "valid":       True,
            "company":     payload["company"],
            "max_nodes":   payload["max_nodes"],
            "perpetual":   payload["perpetual"],
            "issued_at":   payload["issued_at"],
        }
    except Exception as e:
        return {"valid": False, "error": str(e)}

def check_node_limit(max_nodes: int, current_nodes: int) -> bool:
    if max_nodes == -1:
        return True
    return current_nodes <= max_nodes
