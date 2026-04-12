"""
JENIX White Label System
Companies can customize branding per deployment.
"""
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session
from db import get_db
from auth import require_admin, get_current_user, User
import json, os

router = APIRouter(prefix="/whitelabel", tags=["whitelabel"])

WHITELABEL_FILE = os.path.join(
    os.path.dirname(__file__), "..", "whitelabel.json")

DEFAULT_CONFIG = {
    "company_name":   "JENIX Enterprise",
    "logo_text":      "JENIX",
    "logo_subtext":   "ENTERPRISE v2.0",
    "primary_color":  "#00bcd4",
    "accent_color":   "#ffb300",
    "sidebar_bg":     "#0d0d1a",
    "main_bg":        "#0d0d1a",
    "card_bg":        "#13131f",
    "powered_by":     True,
    "support_email":  "",
    "support_url":    "",
    "dashboard_title":"Fleet Command Center",
    "favicon_emoji":  "🖥",
}

def load_config() -> dict:
    if os.path.exists(WHITELABEL_FILE):
        try:
            with open(WHITELABEL_FILE) as f:
                stored = json.load(f)
                return {**DEFAULT_CONFIG, **stored}
        except Exception:
            pass
    return DEFAULT_CONFIG.copy()

def save_config(config: dict):
    with open(WHITELABEL_FILE, "w") as f:
        json.dump(config, f, indent=2)

class WhiteLabelConfig(BaseModel):
    company_name:   str  = "JENIX Enterprise"
    logo_text:      str  = "JENIX"
    logo_subtext:   str  = "ENTERPRISE v2.0"
    primary_color:  str  = "#00bcd4"
    accent_color:   str  = "#ffb300"
    sidebar_bg:     str  = "#0d0d1a"
    main_bg:        str  = "#0d0d1a"
    card_bg:        str  = "#13131f"
    powered_by:     bool = True
    support_email:  str  = ""
    support_url:    str  = ""
    dashboard_title:str  = "Fleet Command Center"
    favicon_emoji:  str  = "🖥"

@router.get("")
def get_whitelabel(_: User = Depends(get_current_user)):
    return load_config()

@router.get("/public")
def get_whitelabel_public():
    """Public endpoint — no auth needed for login page branding."""
    cfg = load_config()
    return {
        "company_name":  cfg["company_name"],
        "logo_text":     cfg["logo_text"],
        "logo_subtext":  cfg["logo_subtext"],
        "primary_color": cfg["primary_color"],
        "powered_by":    cfg["powered_by"],
        "favicon_emoji": cfg["favicon_emoji"],
    }

@router.post("")
def update_whitelabel(body: WhiteLabelConfig,
                      _: User = Depends(require_admin)):
    config = body.dict()
    save_config(config)
    return {"ok": True, "config": config}

@router.post("/reset")
def reset_whitelabel(_: User = Depends(require_admin)):
    if os.path.exists(WHITELABEL_FILE):
        os.remove(WHITELABEL_FILE)
    return {"ok": True, "config": DEFAULT_CONFIG}
