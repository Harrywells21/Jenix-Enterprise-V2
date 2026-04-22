"""
JENIX Enterprise v3.0 — Custom Alert Rules Engine
9 built-in rules + full CRUD for custom rules.
Dotted field paths, array wildcards, AND/OR/ANY logic,
per-rule cooldowns, auto-playbook triggers, message templating.
"""

import operator
import re
import uuid
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional, Tuple

# ── Operator map ──────────────────────────────────────────────────────────────
OPS: Dict[str, Callable] = {
    ">": operator.gt, ">=": operator.ge,
    "<": operator.lt, "<=": operator.le,
    "==": operator.eq, "!=": operator.ne,
}

# ── Built-in rules ────────────────────────────────────────────────────────────
DEFAULT_RULES: List[dict] = [
    {
        "id": "rule_cpu_critical", "name": "CPU Critical (>95%)",
        "description": "Fires when CPU exceeds 95% on any online node",
        "enabled": True,
        "conditions": [{"field": "cpu.cpu_percent", "op": ">", "value": 95}],
        "logic": "AND", "severity": "critical", "cooldown_mins": 10,
        "channels": ["slack", "email", "teams"],
        "auto_playbook": "linux_high_cpu",
        "message_template": "🔴 {node_name} CPU at {cpu.cpu_percent:.1f}% — CRITICAL",
        "tags": ["performance", "cpu"],
    },
    {
        "id": "rule_cpu_warning", "name": "CPU Warning (>85%)",
        "enabled": True,
        "conditions": [{"field": "cpu.cpu_percent", "op": ">", "value": 85}],
        "logic": "AND", "severity": "warning", "cooldown_mins": 15,
        "channels": ["slack"],
        "auto_playbook": None,
        "message_template": "⚠️ {node_name} CPU at {cpu.cpu_percent:.1f}%",
        "tags": ["performance", "cpu"],
    },
    {
        "id": "rule_ram_critical", "name": "Memory Critical (>92%)",
        "enabled": True,
        "conditions": [{"field": "memory.ram_percent", "op": ">", "value": 92}],
        "logic": "AND", "severity": "critical", "cooldown_mins": 10,
        "channels": ["slack", "email", "teams"],
        "auto_playbook": "linux_high_memory",
        "message_template": "🔴 {node_name} RAM at {memory.ram_percent:.1f}% — CRITICAL",
        "tags": ["performance", "memory"],
    },
    {
        "id": "rule_ram_warning", "name": "Memory Warning (>85%)",
        "enabled": True,
        "conditions": [{"field": "memory.ram_percent", "op": ">", "value": 85}],
        "logic": "AND", "severity": "warning", "cooldown_mins": 15,
        "channels": ["slack"],
        "auto_playbook": None,
        "message_template": "⚠️ {node_name} RAM at {memory.ram_percent:.1f}%",
        "tags": ["performance", "memory"],
    },
    {
        "id": "rule_disk_critical", "name": "Disk Critical (>95%)",
        "enabled": True,
        "conditions": [{"field": "disks[*].percent", "op": ">", "value": 95}],
        "logic": "ANY", "severity": "critical", "cooldown_mins": 30,
        "channels": ["slack", "email", "teams"],
        "auto_playbook": "linux_disk_cleanup",
        "message_template": "🔴 {node_name} disk usage CRITICAL",
        "tags": ["disk", "storage"],
    },
    {
        "id": "rule_disk_warning", "name": "Disk Warning (>85%)",
        "enabled": True,
        "conditions": [{"field": "disks[*].percent", "op": ">", "value": 85}],
        "logic": "ANY", "severity": "warning", "cooldown_mins": 60,
        "channels": ["slack"],
        "auto_playbook": None,
        "message_template": "⚠️ {node_name} disk usage high",
        "tags": ["disk", "storage"],
    },
    {
        "id": "rule_swap_high", "name": "Swap Usage High (>50%)",
        "enabled": True,
        "conditions": [{"field": "memory.swap_percent", "op": ">", "value": 50}],
        "logic": "AND", "severity": "warning", "cooldown_mins": 20,
        "channels": ["slack"],
        "auto_playbook": None,
        "message_template": "⚠️ {node_name} swap at {memory.swap_percent:.1f}% — memory pressure",
        "tags": ["memory", "swap"],
    },
    {
        "id": "rule_many_ports", "name": "High Open Port Count (>30)",
        "enabled": True,
        "conditions": [{"field": "ports_count", "op": ">", "value": 30}],
        "logic": "AND", "severity": "info", "cooldown_mins": 1440,
        "channels": ["slack"],
        "auto_playbook": None,
        "message_template": "ℹ️ {node_name} has {ports_count} open ports — review recommended",
        "tags": ["security", "ports"],
    },
    {
        "id": "rule_offline", "name": "Node Offline",
        "enabled": True,
        "conditions": [{"field": "is_online", "op": "==", "value": False}],
        "logic": "AND", "severity": "critical", "cooldown_mins": 5,
        "channels": ["slack", "email", "teams"],
        "auto_playbook": None,
        "message_template": "🔴 {node_name} is OFFLINE",
        "tags": ["availability"],
    },
]

# ── State ─────────────────────────────────────────────────────────────────────
_rules: Dict[str, dict]    = {r["id"]: r for r in DEFAULT_RULES}
_cooldowns: Dict[str, datetime] = {}
_history: List[dict]           = []


# ── Field resolver ────────────────────────────────────────────────────────────

def _get_nested(data: dict, path: str) -> Any:
    parts = path.split(".")
    cur   = data
    for p in parts:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(p) if p in cur else cur.get(int(p) if p.isdigit() else p)
        if cur is None:
            return None
    return cur


def _resolve(data: dict, field: str) -> Any:
    # Virtual fields
    if field == "ports_count":
        return len(data.get("ports", []))
    if field == "is_online":
        return data.get("is_online", False)
    # Array wildcard: disks[*].percent
    if "[*]" in field:
        parts     = field.split("[*].")
        arr_key   = parts[0]
        sub_key   = parts[1] if len(parts) > 1 else ""
        items     = data.get(arr_key, [])
        if not sub_key:
            return items
        return [_get_nested(i, sub_key) for i in items if isinstance(i, dict)]
    return _get_nested(data, field)


# ── Condition evaluator ───────────────────────────────────────────────────────

def _eval_cond(cond: dict, metrics: dict) -> Tuple[bool, Any]:
    op  = OPS.get(cond["op"])
    val = cond["value"]
    if not op:
        return False, None
    resolved = _resolve(metrics, cond["field"])
    if resolved is None:
        return False, None
    if isinstance(resolved, list):
        for item in resolved:
            try:
                if item is not None and op(float(item), float(val)):
                    return True, item
            except (TypeError, ValueError):
                pass
        return False, resolved
    try:
        if isinstance(resolved, bool):
            return op(resolved, val), resolved
        return op(float(resolved), float(val)), resolved
    except (TypeError, ValueError):
        try:
            return op(str(resolved), str(val)), resolved
        except Exception:
            return False, resolved


# ── Flatten metrics for message template ─────────────────────────────────────

def _flatten(metrics: dict, prefix: str = "") -> dict:
    out = {}
    for k, v in metrics.items():
        key = f"{prefix}{k}"
        if isinstance(v, dict):
            out.update(_flatten(v, f"{key}."))
        elif isinstance(v, (int, float, bool)):
            out[key] = v
    out["ports_count"] = len(metrics.get("ports", []))
    return out


# ── Rule evaluator ────────────────────────────────────────────────────────────

def evaluate(node_id: str, node_name: str, node_os: str, metrics: dict) -> List[dict]:
    triggered = []

    for rule_id, rule in _rules.items():
        if not rule.get("enabled", True):
            continue

        conditions = rule.get("conditions", [])
        logic      = rule.get("logic", "AND")
        results    = [_eval_cond(c, metrics) for c in conditions]

        passed = (all(r[0] for r in results)  if logic in ("AND",)
                  else any(r[0] for r in results))

        if not passed:
            continue

        # Cooldown check
        ck       = f"{rule_id}:{node_id}"
        last     = _cooldowns.get(ck)
        cooldown = rule.get("cooldown_mins", 15)
        if last and (datetime.utcnow() - last) < timedelta(minutes=cooldown):
            continue

        # Format message
        flat = _flatten(metrics)
        flat["node_name"] = node_name
        try:
            msg = rule.get("message_template", "{node_name}: alert").format_map(
                defaultdict(lambda: "—", flat)
            )
        except Exception:
            msg = f"{node_name}: {rule['name']}"

        alert = {
            "alert_id":      str(uuid.uuid4()),
            "rule_id":       rule_id,
            "rule_name":     rule["name"],
            "node_id":       node_id,
            "node_name":     node_name,
            "node_os":       node_os,
            "severity":      rule["severity"],
            "message":       msg,
            "channels":      rule.get("channels", []),
            "auto_playbook": rule.get("auto_playbook"),
            "tags":          rule.get("tags", []),
            "fired_at":      datetime.utcnow().isoformat(),
        }

        _cooldowns[ck] = datetime.utcnow()
        _history.append(alert)
        if len(_history) > 5000:
            _history.pop(0)

        triggered.append(alert)

    return triggered


# ── CRUD ──────────────────────────────────────────────────────────────────────

def list_rules() -> List[dict]:
    return list(_rules.values())

def get_rule(rule_id: str) -> Optional[dict]:
    return _rules.get(rule_id)

def create_rule(rule: dict) -> dict:
    rule_id      = rule.get("id") or f"rule_{uuid.uuid4().hex[:8]}"
    rule["id"]   = rule_id
    _rules[rule_id] = rule
    return rule

def update_rule(rule_id: str, updates: dict) -> Optional[dict]:
    if rule_id not in _rules:
        return None
    _rules[rule_id].update({k: v for k, v in updates.items() if v is not None})
    return _rules[rule_id]

def delete_rule(rule_id: str) -> bool:
    default_ids = {r["id"] for r in DEFAULT_RULES}
    if rule_id in default_ids:
        return False
    return _rules.pop(rule_id, None) is not None

def toggle_rule(rule_id: str, enabled: bool) -> Optional[dict]:
    if rule_id not in _rules:
        return None
    _rules[rule_id]["enabled"] = enabled
    return _rules[rule_id]

def get_history(node_id: Optional[str] = None, severity: Optional[str] = None, limit: int = 100) -> List[dict]:
    h = _history
    if node_id:
        h = [a for a in h if a["node_id"] == node_id]
    if severity:
        h = [a for a in h if a["severity"] == severity]
    return list(reversed(h[-limit:]))

def get_stats() -> dict:
    from collections import Counter
    return {
        "total_fired":   len(_history),
        "by_rule":       dict(Counter(a["rule_id"]   for a in _history)),
        "by_severity":   dict(Counter(a["severity"]  for a in _history)),
        "by_node":       dict(Counter(a["node_id"]   for a in _history)),
        "active_cooldowns": len(_cooldowns),
    }
