"""
JENIX Enterprise — Alert Engine
Slack / Teams / Email with cooldown logic
"""

import asyncio
import os
from datetime import datetime, timedelta
from typing import Dict, Optional

import httpx
import aiosmtplib
from email.message import EmailMessage

SLACK_WEBHOOK   = os.getenv("SLACK_WEBHOOK_URL", "")
TEAMS_WEBHOOK   = os.getenv("TEAMS_WEBHOOK_URL", "")
SMTP_HOST       = os.getenv("SMTP_HOST", "")
SMTP_PORT       = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER       = os.getenv("SMTP_USER", "")
SMTP_PASS       = os.getenv("SMTP_PASS", "")
ALERT_FROM      = os.getenv("ALERT_FROM", "alerts@jenix.local")
ALERT_EMAILS    = os.getenv("ALERT_EMAILS", "").split(",")

CPU_THRESH      = int(os.getenv("ALERT_CPU_THRESHOLD",  "85"))
RAM_THRESH      = int(os.getenv("ALERT_RAM_THRESHOLD",  "85"))
DISK_THRESH     = int(os.getenv("ALERT_DISK_THRESHOLD", "90"))
COOLDOWN_MINS   = 15

# In-memory cooldown tracker  {node_id:alert_type -> last_sent datetime}
_cooldowns: Dict[str, datetime] = {}

def _on_cooldown(node_id: str, alert_type: str) -> bool:
    key = f"{node_id}:{alert_type}"
    last = _cooldowns.get(key)
    if last and (datetime.utcnow() - last) < timedelta(minutes=COOLDOWN_MINS):
        return True
    _cooldowns[key] = datetime.utcnow()
    return False


# ── Send functions ─────────────────────────────────────────────────────────

async def send_slack(message: str, severity: str = "warning"):
    if not SLACK_WEBHOOK:
        return
    color = {"critical": "#ff0000", "warning": "#ff9900", "info": "#36a64f"}.get(severity, "#888")
    payload = {
        "attachments": [{
            "color": color,
            "text":  message,
            "footer": "JENIX Enterprise",
            "ts":    int(datetime.utcnow().timestamp()),
        }]
    }
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(SLACK_WEBHOOK, json=payload)
    except Exception as e:
        print(f"[ALERT] Slack error: {e}")

async def send_teams(message: str, severity: str = "warning"):
    if not TEAMS_WEBHOOK:
        return
    color = {"critical": "FF0000", "warning": "FF9900", "info": "36A64F"}.get(severity, "888888")
    payload = {
        "@type":      "MessageCard",
        "@context":   "http://schema.org/extensions",
        "themeColor": color,
        "summary":    "JENIX Alert",
        "sections":   [{"activityTitle": "JENIX Enterprise Alert",
                        "activityText":  message}],
    }
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(TEAMS_WEBHOOK, json=payload)
    except Exception as e:
        print(f"[ALERT] Teams error: {e}")

async def send_email(subject: str, body: str):
    if not SMTP_HOST or not SMTP_USER:
        return
    for recipient in ALERT_EMAILS:
        recipient = recipient.strip()
        if not recipient:
            continue
        try:
            msg = EmailMessage()
            msg["From"]    = ALERT_FROM
            msg["To"]      = recipient
            msg["Subject"] = subject
            msg.set_content(body)
            await aiosmtplib.send(
                msg,
                hostname=SMTP_HOST, port=SMTP_PORT,
                username=SMTP_USER, password=SMTP_PASS,
                start_tls=True,
            )
        except Exception as e:
            print(f"[ALERT] Email error to {recipient}: {e}")


# ── Main alert dispatcher ──────────────────────────────────────────────────

async def check_and_alert(node_id: str, node_name: str, metrics: dict):
    """Check metrics thresholds and fire alerts if needed."""
    alerts_fired = []

    cpu  = metrics.get("cpu",    {}).get("cpu_percent", 0)
    ram  = metrics.get("memory", {}).get("ram_percent",  0)
    disks = metrics.get("disks", [])
    disk  = max((d.get("percent", 0) for d in disks), default=0)

    checks = [
        (cpu  > CPU_THRESH,  "cpu",   f"CPU at {cpu:.1f}%",    "warning" if cpu  < 95 else "critical"),
        (ram  > RAM_THRESH,  "ram",   f"RAM at {ram:.1f}%",    "warning" if ram  < 95 else "critical"),
        (disk > DISK_THRESH, "disk",  f"Disk at {disk:.1f}%",  "warning" if disk < 98 else "critical"),
    ]

    for triggered, alert_type, detail, severity in checks:
        if triggered and not _on_cooldown(node_id, alert_type):
            msg = f"[{severity.upper()}] {node_name}: {detail}"
            await asyncio.gather(
                send_slack(msg, severity),
                send_teams(msg, severity),
                send_email(f"JENIX Alert — {node_name}", msg),
            )
            alerts_fired.append({"type": alert_type, "message": msg,
                                  "severity": severity})

    return alerts_fired

async def send_offline_alert(node_id: str, node_name: str):
    if _on_cooldown(node_id, "offline"):
        return
    msg = f"[CRITICAL] {node_name}: Server is OFFLINE"
    await asyncio.gather(
        send_slack(msg, "critical"),
        send_teams(msg, "critical"),
        send_email(f"JENIX Alert — {node_name} OFFLINE", msg),
    )
