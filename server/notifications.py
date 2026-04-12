"""
JENIX Notification Engine — Slack and Teams webhooks.
"""
import os, json
from urllib import request, error
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

SLACK_WEBHOOK  = os.getenv("SLACK_WEBHOOK",  "")
TEAMS_WEBHOOK  = os.getenv("TEAMS_WEBHOOK",  "")

def _post_json(url: str, payload: dict) -> bool:
    try:
        data = json.dumps(payload).encode()
        req  = request.Request(url, data=data,
                               headers={"Content-Type": "application/json"},
                               method="POST")
        with request.urlopen(req, timeout=5) as r:
            return r.status == 200
    except Exception as e:
        print(f"[notify] Webhook error: {e}")
        return False

def notify_slack(title: str, message: str, level: str = "warning"):
    if not SLACK_WEBHOOK:
        return
    color = "#f44336" if level == "critical" else \
            "#ffb300" if level == "warning"  else "#4caf50"
    payload = {
        "attachments": [{
            "color":  color,
            "title":  f"JENIX — {title}",
            "text":   message,
            "footer": "JENIX Enterprise",
            "ts":     __import__("time").time(),
        }]
    }
    _post_json(SLACK_WEBHOOK, payload)

def notify_teams(title: str, message: str, level: str = "warning"):
    if not TEAMS_WEBHOOK:
        return
    color = "attention" if level == "critical" else \
            "warning"   if level == "warning"  else "good"
    payload = {
        "type":        "message",
        "attachments": [{
            "contentType": "application/vnd.microsoft.card.adaptive",
            "content": {
                "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                "type":    "AdaptiveCard",
                "version": "1.4",
                "body": [
                    {"type": "TextBlock", "size": "Medium",
                     "weight": "Bolder", "text": f"🔔 JENIX — {title}"},
                    {"type": "TextBlock", "text": message,
                     "wrap": True, "color": color},
                ]
            }
        }]
    }
    _post_json(TEAMS_WEBHOOK, payload)

def notify_all(title: str, message: str, level: str = "warning"):
    notify_slack(title, message, level)
    notify_teams(title, message, level)

def notify_machine_offline(hostname: str, ip: str):
    notify_all(
        f"Machine Offline: {hostname}",
        f"⚠️ **{hostname}** ({ip}) has gone offline and is unreachable.",
        "critical"
    )

def notify_critical_alert(hostname: str, alert_type: str, message: str):
    notify_all(
        f"Critical Alert: {hostname}",
        f"🚨 **{hostname}** — {message}",
        "critical"
    )

def notify_command_done(hostname: str, cmd_type: str, status: str):
    level = "info" if status == "done" else "warning"
    notify_all(
        f"Command {status.upper()}: {hostname}",
        f"✅ **{cmd_type.upper()}** completed on **{hostname}** — Status: {status}",
        level
    )

def send_daily_summary(machines: list, online: int, alerts: int):
    msg = (
        f"📊 **Daily JENIX Summary**\n"
        f"• Total machines: {len(machines)}\n"
        f"• Online: {online} | Offline: {len(machines)-online}\n"
        f"• Unread alerts: {alerts}\n"
    )
    notify_all("Daily Fleet Summary", msg, "info")
