"""
JENIX Enterprise v3.0 — AI Anomaly Detection Engine
Welford online statistics, Z-score anomaly scoring,
pattern detection (memory leak, swap thrash, CPU saturation).
Zero external ML dependencies — pure Python math.
"""

import math
import os
import uuid
from collections import defaultdict, deque
from datetime import datetime
from typing import Dict, List, Optional

# ── Per-node sliding window (288 = 24h @ 5-min intervals) ────────────────────
WINDOW        = 288
Z_THRESHOLD   = 2.8
MIN_SAMPLES   = 12

_windows:  Dict[str, Dict[str, deque]]       = defaultdict(lambda: defaultdict(lambda: deque(maxlen=WINDOW)))
_scores:   Dict[str, dict]                   = {}
_history:  Dict[str, List[dict]]             = defaultdict(list)


# ── Welford online mean/variance — O(1) per update ───────────────────────────
class W:
    __slots__ = ("n", "mean", "M2")

    def __init__(self):
        self.n = 0; self.mean = 0.0; self.M2 = 0.0

    def update(self, x: float):
        self.n += 1
        d = x - self.mean
        self.mean += d / self.n
        self.M2   += d * (x - self.mean)

    @property
    def var(self):  return self.M2 / (self.n - 1) if self.n > 1 else 0.0
    @property
    def std(self):  return math.sqrt(self.var)

    def z(self, x: float) -> float:
        return abs(x - self.mean) / self.std if self.std > 1e-4 else 0.0


_welford: Dict[str, Dict[str, W]] = defaultdict(lambda: defaultdict(W))


# ── Feature extraction ────────────────────────────────────────────────────────

def _extract(metrics: dict) -> Dict[str, float]:
    cpu   = metrics.get("cpu", {})
    mem   = metrics.get("memory", {})
    disks = metrics.get("disks", [])
    net   = metrics.get("network", [])
    procs = metrics.get("processes", [])

    disk_max = max((d.get("percent", 0) for d in disks), default=0)
    net_in   = sum(n.get("bytes_recv", 0) for n in net)
    net_out  = sum(n.get("bytes_sent", 0) for n in net)
    load_raw = cpu.get("load_avg") or {}
    if isinstance(load_raw, dict):
        load_1m = float(load_raw.get("1m", load_raw.get(1, 0)) or 0)
    else:
        load_1m = 0.0

    return {
        "cpu_percent":  float(cpu.get("cpu_percent", 0)),
        "ram_percent":  float(mem.get("ram_percent",  0)),
        "disk_max":     float(disk_max),
        "swap_percent": float(mem.get("swap_percent", 0)),
        "load_1m":      load_1m,
        "net_in":       float(net_in),
        "net_out":      float(net_out),
        "proc_count":   float(len(procs)),
        "top_cpu_proc": float(max((p.get("cpu_percent", 0) for p in procs), default=0)),
        "top_mem_proc": float(max((p.get("memory_percent", 0) for p in procs), default=0)),
    }


# ── Anomaly scorer ────────────────────────────────────────────────────────────

def score(node_id: str, features: Dict[str, float]) -> dict:
    ws        = _welford[node_id]
    z_scores  = {}
    anomalies = []

    for key, val in features.items():
        w  = ws[key]
        zv = w.z(val) if w.n >= MIN_SAMPLES else 0.0
        w.update(val)
        z_scores[key] = round(zv, 3)
        if zv >= Z_THRESHOLD:
            anomalies.append({
                "feature":        key,
                "value":          round(val, 2),
                "z_score":        round(zv, 3),
                "baseline_mean":  round(w.mean, 2),
                "baseline_std":   round(w.std,  2),
            })

    rms = math.sqrt(sum(z**2 for z in z_scores.values()) / max(len(z_scores), 1))
    is_anomaly = rms >= Z_THRESHOLD or len(anomalies) >= 2

    result = {
        "node_id":        node_id,
        "timestamp":      datetime.utcnow().isoformat(),
        "anomaly_score":  round(rms, 3),
        "is_anomaly":     is_anomaly,
        "anomalies":      anomalies,
        "feature_scores": z_scores,
        "samples_seen":   ws["cpu_percent"].n,
    }

    _scores[node_id] = result
    if is_anomaly:
        _history[node_id].append(result)
        if len(_history[node_id]) > 200:
            _history[node_id].pop(0)

    return result


# ── Pattern detectors ─────────────────────────────────────────────────────────

def _patterns(node_id: str) -> List[dict]:
    patterns = []
    ws       = _welford[node_id]
    win      = _windows[node_id]

    # Memory leak — RAM mean rising monotonically
    ram_hist = list(win["ram_percent"])
    if len(ram_hist) >= 20:
        half  = len(ram_hist) // 2
        f_avg = sum(ram_hist[:half]) / half
        s_avg = sum(ram_hist[half:]) / (len(ram_hist) - half)
        if s_avg > f_avg * 1.15:
            patterns.append({
                "type":        "memory_leak",
                "severity":    "high",
                "description": f"RAM trending up: {f_avg:.1f}% → {s_avg:.1f}% (sustained +15%)",
                "action":      "Inspect top memory consumers; check for leaks",
            })

    # Swap thrashing
    sw = ws["swap_percent"]
    if sw.n >= 10 and sw.mean > 40:
        patterns.append({
            "type":        "swap_thrashing",
            "severity":    "critical",
            "description": f"Sustained swap at {sw.mean:.1f}% — system is thrashing",
            "action":      "Add RAM or reduce memory-intensive workloads immediately",
        })

    # CPU saturation
    lw = ws["load_1m"]
    if lw.n >= 10 and lw.mean > 12:
        patterns.append({
            "type":        "cpu_saturation",
            "severity":    "warning",
            "description": f"Load average {lw.mean:.1f} exceeds CPU capacity",
            "action":      "Check for runaway processes or scale horizontally",
        })

    # Network spike
    nw = ws["net_in"]
    if nw.n >= MIN_SAMPLES and nw.std > 0:
        latest = list(win["net_in"])
        if latest and latest[-1] > nw.mean + 3 * nw.std:
            patterns.append({
                "type":        "network_spike",
                "severity":    "warning",
                "description": "Inbound network traffic 3σ above baseline",
                "action":      "Check for DDoS, data exfiltration, or runaway service",
            })

    return patterns


# ── Public API ────────────────────────────────────────────────────────────────

def process_metrics(node_id: str, metrics: dict) -> dict:
    features = _extract(metrics)
    for k, v in features.items():
        _windows[node_id][k].append(v)
    result = score(node_id, features)
    result["patterns"] = _patterns(node_id)
    return result


def get_baseline(node_id: str) -> dict:
    return {
        k: {"mean": round(w.mean, 2), "std": round(w.std, 2), "samples": w.n}
        for k, w in _welford[node_id].items()
    }


def get_fleet_anomalies() -> List[dict]:
    return [v for v in _scores.values() if v.get("is_anomaly")]


def get_history(node_id: str, limit: int = 50) -> List[dict]:
    return _history.get(node_id, [])[-limit:]


def reset_baseline(node_id: str):
    _welford.pop(node_id, None)
    _windows.pop(node_id, None)
    _scores.pop(node_id, None)
    _history.pop(node_id, None)


def suggest_playbooks(anomaly: dict, os_type: str) -> List[str]:
    fs = anomaly.get("feature_scores", {})
    ps = [p["type"] for p in anomaly.get("patterns", [])]
    out = []
    if fs.get("cpu_percent", 0) > 2.5 and os_type == "Linux":
        out.append("linux_high_cpu")
    if fs.get("ram_percent", 0) > 2.5:
        out.append(f"{'macos' if os_type=='Darwin' else 'windows' if os_type=='Windows' else 'linux'}_high_memory")
    if fs.get("disk_max", 0) > 2.5:
        out.append(f"{'macos' if os_type=='Darwin' else 'windows' if os_type=='Windows' else 'linux'}_disk_cleanup")
    if "swap_thrashing" in ps and os_type == "Linux":
        out.append("linux_high_memory")
    return list(dict.fromkeys(out))
