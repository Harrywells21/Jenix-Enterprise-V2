"""
JENIX Health Score Engine
Calculates 0-100 score per machine based on multiple factors.
"""
from datetime import datetime, timedelta

def calculate_health_score(machine, metrics: list, alerts: list,
                            last_scan=None) -> dict:
    score = 100
    breakdown = []

    # ── CPU average ────────────────────────────────────────────────────────
    if metrics:
        avg_cpu = sum(m["cpu"] for m in metrics) / len(metrics)
        if avg_cpu > 95:
            score -= 25
            breakdown.append({"factor": "CPU", "impact": -25,
                               "detail": f"Critical CPU avg {avg_cpu:.1f}%"})
        elif avg_cpu > 85:
            score -= 15
            breakdown.append({"factor": "CPU", "impact": -15,
                               "detail": f"High CPU avg {avg_cpu:.1f}%"})
        elif avg_cpu > 70:
            score -= 5
            breakdown.append({"factor": "CPU", "impact": -5,
                               "detail": f"Elevated CPU avg {avg_cpu:.1f}%"})
    else:
        score -= 10
        breakdown.append({"factor": "CPU", "impact": -10,
                           "detail": "No metrics available"})

    # ── RAM average ────────────────────────────────────────────────────────
    if metrics:
        avg_ram = sum(m["ram"] for m in metrics) / len(metrics)
        if avg_ram > 95:
            score -= 20
            breakdown.append({"factor": "RAM", "impact": -20,
                               "detail": f"Critical RAM avg {avg_ram:.1f}%"})
        elif avg_ram > 85:
            score -= 10
            breakdown.append({"factor": "RAM", "impact": -10,
                               "detail": f"High RAM avg {avg_ram:.1f}%"})

    # ── Disk usage ─────────────────────────────────────────────────────────
    if metrics:
        avg_disk = sum(m["disk"] for m in metrics) / len(metrics)
        if avg_disk > 95:
            score -= 25
            breakdown.append({"factor": "Disk", "impact": -25,
                               "detail": f"Critical disk {avg_disk:.1f}%"})
        elif avg_disk > 85:
            score -= 15
            breakdown.append({"factor": "Disk", "impact": -15,
                               "detail": f"High disk {avg_disk:.1f}%"})
        elif avg_disk > 75:
            score -= 5
            breakdown.append({"factor": "Disk", "impact": -5,
                               "detail": f"Elevated disk {avg_disk:.1f}%"})

    # ── Active alerts ──────────────────────────────────────────────────────
    critical = [a for a in alerts if a["level"] == "critical" and not a["is_read"]]
    warnings = [a for a in alerts if a["level"] == "warning"  and not a["is_read"]]
    if critical:
        penalty = min(len(critical) * 10, 30)
        score -= penalty
        breakdown.append({"factor": "Alerts", "impact": -penalty,
                           "detail": f"{len(critical)} critical alerts"})
    if warnings:
        penalty = min(len(warnings) * 3, 10)
        score -= penalty
        breakdown.append({"factor": "Alerts", "impact": -penalty,
                           "detail": f"{len(warnings)} warnings"})

    # ── Machine offline ────────────────────────────────────────────────────
    if machine["status"] == "offline":
        score -= 20
        breakdown.append({"factor": "Status", "impact": -20,
                           "detail": "Machine is offline"})

    # ── Last scan ──────────────────────────────────────────────────────────
    if last_scan is None:
        score -= 10
        breakdown.append({"factor": "Scan", "impact": -10,
                           "detail": "Never scanned"})

    score = max(0, min(100, score))

    if score >= 80:
        grade = "Healthy"
        color = "#4caf50"
    elif score >= 50:
        grade = "Needs Attention"
        color = "#ffb300"
    else:
        grade = "Critical"
        color = "#f44336"

    return {
        "score":     score,
        "grade":     grade,
        "color":     color,
        "breakdown": breakdown,
    }
