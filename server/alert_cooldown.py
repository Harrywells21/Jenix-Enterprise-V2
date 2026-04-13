"""
JENIX Alert Cooldown System
Prevents duplicate alerts within a cooldown window.
"""
from datetime import datetime, timedelta
from typing import Dict, Tuple

# key = (machine_id, alert_type) → last alert timestamp
_cooldown_store: Dict[Tuple[int, str], datetime] = {}

COOLDOWN_MINUTES = {
    "cpu":     30,
    "ram":     30,
    "disk":    60,
    "offline": 10,
    "port":    120,
}

def should_create_alert(machine_id: int,
                         alert_type: str) -> bool:
    """
    Returns True if enough time has passed since
    the last alert of this type for this machine.
    """
    key     = (machine_id, alert_type)
    now     = datetime.utcnow()
    cooldown = COOLDOWN_MINUTES.get(alert_type, 30)

    if key in _cooldown_store:
        last = _cooldown_store[key]
        if now - last < timedelta(minutes=cooldown):
            return False

    _cooldown_store[key] = now
    return True

def clear_cooldown(machine_id: int, alert_type: str):
    """Clear cooldown when alert is resolved."""
    key = (machine_id, alert_type)
    _cooldown_store.pop(key, None)

def get_cooldown_status() -> dict:
    """Debug view of current cooldowns."""
    now = datetime.utcnow()
    return {
        f"{mid}:{atype}": {
            "last_alert": ts.isoformat(),
            "cooldown_min": COOLDOWN_MINUTES.get(atype, 30),
            "expires_in_min": max(0, round(
                (COOLDOWN_MINUTES.get(atype, 30) -
                 (now - ts).total_seconds() / 60), 1
            ))
        }
        for (mid, atype), ts in _cooldown_store.items()
    }
