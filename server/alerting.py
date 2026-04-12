"""
JENIX Alert Engine — monitors metrics and sends email alerts.
"""
import os, smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

SMTP_HOST  = os.getenv("SMTP_HOST",  "smtp.gmail.com")
SMTP_PORT  = int(os.getenv("SMTP_PORT", 587))
SMTP_USER  = os.getenv("SMTP_USER",  "")
SMTP_PASS  = os.getenv("SMTP_PASS",  "")
ALERT_EMAIL = os.getenv("ALERT_EMAIL", "")

def send_alert_email(subject: str, body: str):
    """Send an alert email. Silently fails if SMTP not configured."""
    if not SMTP_USER or not SMTP_PASS or not ALERT_EMAIL:
        print(f"[alert] Email not configured — skipping: {subject}")
        return
    try:
        msg = MIMEMultipart()
        msg["From"]    = SMTP_USER
        msg["To"]      = ALERT_EMAIL
        msg["Subject"] = f"[JENIX ALERT] {subject}"
        msg.attach(MIMEText(body, "html"))
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as s:
            s.starttls()
            s.login(SMTP_USER, SMTP_PASS)
            s.sendmail(SMTP_USER, ALERT_EMAIL, msg.as_string())
        print(f"[alert] Email sent: {subject}")
    except Exception as e:
        print(f"[alert] Email failed: {e}")

def check_and_alert(machine_id: int, hostname: str,
                    cpu: float, ram: float, disk: float):
    """Check metrics and create alerts if thresholds exceeded."""
    from db import SessionLocal, Alert
    db = SessionLocal()
    try:
        alerts_to_add = []
        if cpu > 85:
            alerts_to_add.append(Alert(
                machine_id=machine_id, level="warning",
                type="cpu", message=f"CPU at {cpu:.1f}% on {hostname}"))
            if cpu > 95:
                send_alert_email(
                    f"Critical CPU on {hostname}",
                    f"<b>{hostname}</b> CPU usage is at <b>{cpu:.1f}%</b>.<br>"
                    f"Please investigate immediately."
                )
        if ram > 85:
            alerts_to_add.append(Alert(
                machine_id=machine_id, level="warning",
                type="ram", message=f"RAM at {ram:.1f}% on {hostname}"))
            if ram > 95:
                send_alert_email(
                    f"Critical RAM on {hostname}",
                    f"<b>{hostname}</b> RAM usage is at <b>{ram:.1f}%</b>."
                )
        if disk > 90:
            alerts_to_add.append(Alert(
                machine_id=machine_id, level="critical",
                type="disk", message=f"Disk at {disk:.1f}% on {hostname}"))
            send_alert_email(
                f"Critical Disk on {hostname}",
                f"<b>{hostname}</b> disk usage is at <b>{disk:.1f}%</b>.<br>"
                f"Immediate action required."
            )
        for a in alerts_to_add:
            db.add(a)
        if alerts_to_add:
            db.commit()
    except Exception as e:
        print(f"[alerting] error: {e}")
    finally:
        db.close()
