from fastapi import APIRouter, Depends
from pydantic import BaseModel
from auth import require_admin, User
import os

router = APIRouter(prefix="/settings", tags=["settings"])

class NotifyConfig(BaseModel):
    slack_webhook:  str = ""
    teams_webhook:  str = ""
    alert_email:    str = ""
    smtp_host:      str = ""
    smtp_port:      int = 587
    smtp_user:      str = ""
    smtp_pass:      str = ""

@router.post("/notifications")
def update_notify(body: NotifyConfig,
                  _: User = Depends(require_admin)):
    env_path = os.path.join(
        os.path.dirname(__file__), "..", ".env")
    lines = []
    if os.path.exists(env_path):
        with open(env_path) as f:
            lines = f.readlines()

    updates = {
        "SLACK_WEBHOOK":  body.slack_webhook,
        "TEAMS_WEBHOOK":  body.teams_webhook,
        "ALERT_EMAIL":    body.alert_email,
        "SMTP_HOST":      body.smtp_host,
        "SMTP_PORT":      str(body.smtp_port),
        "SMTP_USER":      body.smtp_user,
    }
    if body.smtp_pass:
        updates["SMTP_PASS"] = body.smtp_pass

    # Update existing lines
    updated_keys = set()
    new_lines = []
    for line in lines:
        key = line.split("=")[0].strip()
        if key in updates:
            new_lines.append(f"{key}={updates[key]}\n")
            updated_keys.add(key)
        else:
            new_lines.append(line)

    # Add missing keys
    for key, val in updates.items():
        if key not in updated_keys:
            new_lines.append(f"{key}={val}\n")

    with open(env_path, "w") as f:
        f.writelines(new_lines)

    return {"ok": True, "message": "Notification settings updated"}

@router.get("/notifications")
def get_notify(_: User = Depends(require_admin)):
    from dotenv import dotenv_values
    env_path = os.path.join(
        os.path.dirname(__file__), "..", ".env")
    vals = dotenv_values(env_path)
    return {
        "slack_webhook": vals.get("SLACK_WEBHOOK", ""),
        "teams_webhook": vals.get("TEAMS_WEBHOOK", ""),
        "alert_email":   vals.get("ALERT_EMAIL",   ""),
        "smtp_host":     vals.get("SMTP_HOST",     ""),
        "smtp_port":     int(vals.get("SMTP_PORT", 587)),
        "smtp_user":     vals.get("SMTP_USER",     ""),
        "smtp_configured": bool(vals.get("SMTP_USER")),
        "slack_configured": bool(vals.get("SLACK_WEBHOOK")),
        "teams_configured": bool(vals.get("TEAMS_WEBHOOK")),
    }


class TestNotification(BaseModel):
    type: str = "slack"  # slack, teams, email

@router.post("/notifications/test")
def test_notification(body: TestNotification,
                      _: User = Depends(require_admin)):
    from notifications import notify_slack, notify_teams, send_alert_email
    try:
        if body.type == "slack":
            notify_slack(
                "JENIX Test Notification",
                "✅ Your Slack integration is working correctly!",
                "info"
            )
        elif body.type == "teams":
            notify_teams(
                "JENIX Test Notification",
                "✅ Your Teams integration is working correctly!",
                "info"
            )
        elif body.type == "email":
            send_alert_email(
                "JENIX Test Notification",
                "<b>✅ Your email integration is working correctly!</b>"
            )
        return {"ok": True, "message": f"Test {body.type} notification sent"}
    except Exception as e:
        return {"ok": False, "message": str(e)}
