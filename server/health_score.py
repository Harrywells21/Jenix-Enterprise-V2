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


SEV_ORDER = {"CRITICAL": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1, "UNKNOWN": 0}


def calculate_compliance_score(cve_severity_counts: dict, unresolved_alerts: dict,
                                audit_tamper_detected: bool, audit_unverifiable_count: int,
                                total_machines: int, offline_machines: int,
                                unscanned_machines: int) -> dict:
    """
    Fleet-wide security posture score. Real signals only:
      - cve_severity_counts: {"CRITICAL": n, "HIGH": n, "MEDIUM": n, "LOW": n} from latest scan per machine
      - unresolved_alerts: {"critical": n, "warning": n} fleet-wide, is_read=False
      - audit_tamper_detected: True if ANY sampled AuditLog row's content_hash fails verification
      - audit_unverifiable_count: rows with no content_hash at all (pre-hardening, not itself a failure)
      - total_machines / offline_machines / unscanned_machines: fleet composition

    Does NOT claim to certify against any specific framework (SOC 2, HIPAA, ISO 27001, CIS) -
    those require real control-by-control audits this system cannot perform. This is a
    posture score from data JENIX actually has.
    """
    score = 100
    breakdown = []

    crit_cve = cve_severity_counts.get("CRITICAL", 0)
    high_cve = cve_severity_counts.get("HIGH", 0)
    med_cve  = cve_severity_counts.get("MEDIUM", 0)

    if crit_cve:
        penalty = min(crit_cve * 8, 35)
        score -= penalty
        breakdown.append({"factor": "CVE - Critical", "impact": -penalty,
                           "detail": f"{crit_cve} critical CVE finding(s) in latest scans"})
    if high_cve:
        penalty = min(high_cve * 4, 20)
        score -= penalty
        breakdown.append({"factor": "CVE - High", "impact": -penalty,
                           "detail": f"{high_cve} high-severity CVE finding(s) in latest scans"})
    if med_cve:
        penalty = min(med_cve * 1, 10)
        score -= penalty
        breakdown.append({"factor": "CVE - Medium", "impact": -penalty,
                           "detail": f"{med_cve} medium-severity CVE finding(s) in latest scans"})

    crit_alerts = unresolved_alerts.get("critical", 0)
    warn_alerts = unresolved_alerts.get("warning", 0)
    if crit_alerts:
        penalty = min(crit_alerts * 5, 20)
        score -= penalty
        breakdown.append({"factor": "Unresolved Alerts", "impact": -penalty,
                           "detail": f"{crit_alerts} unresolved critical alert(s) fleet-wide"})
    if warn_alerts:
        penalty = min(warn_alerts * 1, 10)
        score -= penalty
        breakdown.append({"factor": "Unresolved Alerts", "impact": -penalty,
                           "detail": f"{warn_alerts} unresolved warning(s) fleet-wide"})

    if audit_tamper_detected:
        score -= 30
        breakdown.append({"factor": "Audit Integrity", "impact": -30,
                           "detail": "Content-hash mismatch detected in sampled audit log rows"})
    elif audit_unverifiable_count:
        score -= 5
        breakdown.append({"factor": "Audit Integrity", "impact": -5,
                           "detail": f"{audit_unverifiable_count} audit row(s) predate hash hardening"})

    if total_machines:
        offline_ratio = offline_machines / total_machines
        if offline_ratio > 0.2:
            score -= 10
            breakdown.append({"factor": "Fleet Availability", "impact": -10,
                               "detail": f"{offline_machines}/{total_machines} machines offline"})
    if unscanned_machines:
        penalty = min(unscanned_machines * 3, 15)
        score -= penalty
        breakdown.append({"factor": "Scan Coverage", "impact": -penalty,
                           "detail": f"{unscanned_machines} machine(s) never CVE-scanned"})

    score = max(0, min(100, score))

    if score >= 85:
        grade = "Strong"
        color = "#4caf50"
    elif score >= 60:
        grade = "Needs Attention"
        color = "#ffb300"
    else:
        grade = "At Risk"
        color = "#f44336"

    return {
        "score":     score,
        "grade":     grade,
        "color":     color,
        "breakdown": breakdown,
    }
