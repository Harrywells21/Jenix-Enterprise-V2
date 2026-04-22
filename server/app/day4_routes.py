"""
JENIX Enterprise v3.0 — Day 4 Enterprise API Routes
35 new endpoints under /api/v2/ wiring all enterprise modules.
Add to main.py with: from .day4_routes import router as d4; app.include_router(d4)
"""

import asyncio
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .models import (
    get_db, Node, User, ScanResult, ComplianceReport, AuditLog,
)
from .auth import (
    get_current_user, require_admin, require_operator, require_viewer,
    write_audit,
)

# ── Import Day 4 modules (graceful fallback if not yet copied) ─────────────────
try:
    from .anomaly      import process_metrics, get_baseline, get_fleet_anomalies, get_history as get_anomaly_history, reset_baseline, suggest_playbooks
    from .playbooks    import list_playbooks, get_run, get_run_history, execute_playbook, PLAYBOOKS
    from .compliance   import run_scan as run_compliance_scan, fleet_summary, FRAMEWORKS
    from .inventory    import build_asset, detect_topology, export_csv, export_json, export_servicenow, export_jira, risk_score
    from .rules_engine import evaluate, list_rules, get_rule, create_rule, update_rule, delete_rule, toggle_rule, get_history as get_alert_history, get_stats
    from .reports      import generate_report
    D4_LOADED = True
except ImportError as _e:
    D4_LOADED = False
    _D4_ERR   = str(_e)

router = APIRouter(prefix="/api/v2", tags=["enterprise-v2"])


def _d4_check():
    if not D4_LOADED:
        raise HTTPException(503, f"Day 4 modules not loaded: {_D4_ERR}. Copy day4 files to server/app/")


def _connected_agents():
    try:
        from .main import connected_agents
        return connected_agents
    except Exception:
        return {}


def _node_metrics():
    try:
        from .main import node_metrics
        return node_metrics
    except Exception:
        return {}


# ── Schemas ───────────────────────────────────────────────────────────────────

class PlaybookRunReq(BaseModel):
    playbook_id: str
    dry_run:     bool = False

class RuleCreateReq(BaseModel):
    name:             str
    description:      str = ""
    enabled:          bool = True
    conditions:       list
    logic:            str = "AND"
    severity:         str = "warning"
    cooldown_mins:    int = 15
    channels:         List[str] = ["slack"]
    auto_playbook:    Optional[str] = None
    message_template: str = "{node_name}: alert triggered"
    tags:             List[str] = []

class RuleUpdateReq(BaseModel):
    name:          Optional[str]       = None
    enabled:       Optional[bool]      = None
    severity:      Optional[str]       = None
    cooldown_mins: Optional[int]       = None
    conditions:    Optional[list]      = None
    channels:      Optional[List[str]] = None
    message_template: Optional[str]   = None

class IngestReq(BaseModel):
    metrics: dict


# ── Health ────────────────────────────────────────────────────────────────────

@router.get("/health")
async def v2_health():
    return {
        "status":    "ok",
        "version":   "3.0.0",
        "d4_loaded": D4_LOADED,
        "modules":   ["anomaly","playbooks","compliance","inventory","rules","reports"] if D4_LOADED else [],
        "timestamp": datetime.utcnow().isoformat(),
    }


# ── Anomaly detection ─────────────────────────────────────────────────────────

@router.get("/anomaly/fleet")
async def fleet_anomalies(_: User = Depends(require_viewer)):
    _d4_check()
    return get_fleet_anomalies()

@router.get("/anomaly/{node_id}/history")
async def anomaly_history(node_id: str, limit: int = 50, _: User = Depends(require_viewer)):
    _d4_check()
    return get_anomaly_history(node_id, limit)

@router.get("/anomaly/{node_id}/baseline")
async def node_baseline(node_id: str, _: User = Depends(require_viewer)):
    _d4_check()
    return get_baseline(node_id)

@router.post("/anomaly/{node_id}/ingest")
async def ingest_metrics(node_id: str, body: IngestReq, _: User = Depends(require_operator)):
    _d4_check()
    return process_metrics(node_id, body.metrics)

@router.post("/anomaly/{node_id}/reset")
async def reset_node_baseline(node_id: str, db: Session = Depends(get_db),
                               cu: User = Depends(require_admin)):
    _d4_check()
    reset_baseline(node_id)
    write_audit(db, "reset_baseline", f"Baseline reset for {node_id}", user_id=cu.id)
    return {"ok": True}

@router.get("/anomaly/{node_id}/suggest")
async def suggest(node_id: str, db: Session = Depends(get_db), _: User = Depends(require_viewer)):
    _d4_check()
    node = db.query(Node).filter(Node.id == node_id).first()
    if not node:
        raise HTTPException(404, "Node not found")
    hist = get_anomaly_history(node_id, limit=1)
    if not hist:
        return {"suggestions": [], "message": "No anomaly data yet"}
    return {"suggestions": suggest_playbooks(hist[0], node.os_type)}


# ── Playbooks ─────────────────────────────────────────────────────────────────

@router.get("/playbooks")
async def get_playbooks(os_filter: Optional[str] = None, _: User = Depends(require_viewer)):
    _d4_check()
    return list_playbooks(os_filter)

@router.get("/playbooks/{pb_id}")
async def get_playbook_detail(pb_id: str, _: User = Depends(require_viewer)):
    _d4_check()
    pb = PLAYBOOKS.get(pb_id)
    if not pb:
        raise HTTPException(404, "Playbook not found")
    return pb

@router.post("/nodes/{node_id}/playbooks/run")
async def run_playbook(node_id: str, body: PlaybookRunReq,
                       bg: BackgroundTasks,
                       db: Session = Depends(get_db),
                       cu: User = Depends(require_operator)):
    _d4_check()
    node = db.query(Node).filter(Node.id == node_id).first()
    if not node:
        raise HTTPException(404, "Node not found")

    agents = _connected_agents()
    ws     = agents.get(node_id)
    if not ws and not body.dry_run:
        raise HTTPException(503, "Node is offline")

    pb = PLAYBOOKS.get(body.playbook_id)
    if not pb:
        raise HTTPException(404, "Playbook not found")
    if node.os_type not in pb.get("os", []):
        raise HTTPException(400, f"Playbook {body.playbook_id} does not support {node.os_type}")

    write_audit(db, "playbook_run",
                f"Playbook {body.playbook_id} on {node.name} (dry={body.dry_run})",
                node_id=node_id, user_id=cu.id)

    async def _run():
        await execute_playbook(body.playbook_id, node_id, node.os_type, ws, dry_run=body.dry_run)

    bg.add_task(_run)
    return {"status": "started", "playbook_id": body.playbook_id, "node_id": node_id, "dry_run": body.dry_run}

@router.get("/nodes/{node_id}/playbooks/history")
async def playbook_node_history(node_id: str, limit: int = 20, _: User = Depends(require_viewer)):
    _d4_check()
    return get_run_history(node_id=node_id, limit=limit)

@router.get("/playbooks/runs/{run_id}")
async def run_status(run_id: str, _: User = Depends(require_viewer)):
    _d4_check()
    run = get_run(run_id)
    if not run:
        raise HTTPException(404, "Run not found")
    return run


# ── Compliance ────────────────────────────────────────────────────────────────

@router.get("/compliance/frameworks")
async def list_frameworks(_: User = Depends(require_viewer)):
    _d4_check()
    return list(FRAMEWORKS.values())

@router.post("/nodes/{node_id}/compliance/scan")
async def compliance_scan(node_id: str,
                           framework: str = Query("CIS", enum=["CIS","SOC2","HIPAA","PCI"]),
                           bg: BackgroundTasks = BackgroundTasks(),
                           db: Session = Depends(get_db),
                           cu: User = Depends(require_operator)):
    _d4_check()
    node = db.query(Node).filter(Node.id == node_id).first()
    if not node:
        raise HTTPException(404, "Node not found")

    async def _scan():
        result = await run_compliance_scan(node_id, node.os_type, framework)
        db2 = next(get_db())
        cr  = ComplianceReport(
            node_id=node_id, framework=framework,
            score=result["score"], passed=result["passed"],
            failed=result["failed"], findings=result["findings"],
        )
        db2.add(cr); db2.commit(); db2.close()

    bg.add_task(_scan)
    write_audit(db, "compliance_scan", f"Compliance {framework} scan on {node.name}",
                node_id=node_id, user_id=cu.id)
    return {"status": "started", "framework": framework, "node_id": node_id}

@router.get("/nodes/{node_id}/compliance/latest")
async def latest_compliance(node_id: str, db: Session = Depends(get_db),
                             _: User = Depends(require_viewer)):
    _d4_check()
    cr = (db.query(ComplianceReport)
            .filter(ComplianceReport.node_id == node_id)
            .order_by(ComplianceReport.generated_at.desc()).first())
    if not cr:
        return {"message": "No compliance reports yet — run a scan first"}
    return {
        "node_id": node_id, "framework": cr.framework,
        "generated_at": cr.generated_at.isoformat(),
        "score": cr.score, "passed": cr.passed, "failed": cr.failed,
        "findings": cr.findings or [],
        "failed_findings": [f for f in (cr.findings or []) if not f.get("passed")],
    }

@router.get("/compliance/fleet-summary")
async def fleet_comp_summary(db: Session = Depends(get_db), _: User = Depends(require_viewer)):
    _d4_check()
    reports = db.query(ComplianceReport).order_by(ComplianceReport.generated_at.desc()).limit(100).all()
    scans   = [{
        "node_id": r.node_id, "framework": r.framework,
        "score": r.score, "passed": r.passed, "failed": r.failed,
        "findings": r.findings or [],
        "failed_findings": [f for f in (r.findings or []) if not f.get("passed")],
        "total": r.passed + r.failed,
    } for r in reports]
    return fleet_summary(scans)


# ── Asset inventory ───────────────────────────────────────────────────────────

@router.get("/inventory")
async def get_inventory(db: Session = Depends(get_db), _: User = Depends(require_viewer)):
    _d4_check()
    nm    = _node_metrics()
    ca    = _connected_agents()
    nodes = db.query(Node).all()
    assets = []
    for n in nodes:
        nd = {
            "id": n.id, "name": n.name, "os_type": n.os_type,
            "os_pretty": n.os_pretty, "hostname": n.hostname,
            "ip_address": n.ip_address, "is_online": n.id in ca,
            "health_score": n.health_score,
            "last_seen": n.last_seen.isoformat() if n.last_seen else None,
            "registered_at": n.registered_at.isoformat() if n.registered_at else None,
            "tags": n.tags or [],
        }
        assets.append(build_asset(nd, nm.get(n.id, {})))
    return assets

@router.get("/inventory/topology")
async def get_topology(db: Session = Depends(get_db), _: User = Depends(require_viewer)):
    _d4_check()
    nm    = _node_metrics()
    nodes = db.query(Node).all()
    assets = [build_asset(
        {"id": n.id, "name": n.name, "os_type": n.os_type, "hostname": n.hostname,
         "ip_address": n.ip_address, "is_online": True, "health_score": n.health_score, "tags": n.tags or []},
        nm.get(n.id, {})
    ) for n in nodes]
    return detect_topology(assets)

@router.get("/inventory/export/csv")
async def export_inv_csv(db: Session = Depends(get_db), _: User = Depends(require_operator)):
    _d4_check()
    nm    = _node_metrics()
    nodes = db.query(Node).all()
    assets = [build_asset(
        {"id": n.id, "name": n.name, "os_type": n.os_type, "hostname": n.hostname,
         "ip_address": n.ip_address, "is_online": True, "health_score": n.health_score, "tags": n.tags or []},
        nm.get(n.id, {})
    ) for n in nodes]
    fn = f"jenix_inventory_{datetime.utcnow():%Y%m%d}.csv"
    return Response(export_csv(assets), media_type="text/csv",
                    headers={"Content-Disposition": f"attachment; filename={fn}"})

@router.get("/inventory/export/json")
async def export_inv_json(db: Session = Depends(get_db), _: User = Depends(require_operator)):
    _d4_check()
    nm    = _node_metrics()
    nodes = db.query(Node).all()
    assets = [build_asset(
        {"id": n.id, "name": n.name, "os_type": n.os_type, "hostname": n.hostname,
         "ip_address": n.ip_address, "is_online": True, "health_score": n.health_score, "tags": n.tags or []},
        nm.get(n.id, {})
    ) for n in nodes]
    topo = detect_topology(assets)
    fn   = f"jenix_inventory_{datetime.utcnow():%Y%m%d}.json"
    return Response(export_json(assets, topo), media_type="application/json",
                    headers={"Content-Disposition": f"attachment; filename={fn}"})

@router.get("/inventory/export/servicenow")
async def export_inv_snow(db: Session = Depends(get_db), _: User = Depends(require_operator)):
    _d4_check()
    nm    = _node_metrics()
    nodes = db.query(Node).all()
    assets = [build_asset(
        {"id": n.id, "name": n.name, "os_type": n.os_type, "hostname": n.hostname,
         "ip_address": n.ip_address, "is_online": True, "health_score": n.health_score, "tags": n.tags or []},
        nm.get(n.id, {})
    ) for n in nodes]
    return export_servicenow(assets)


# ── Alert rules engine ────────────────────────────────────────────────────────

@router.get("/rules")
async def get_rules(_: User = Depends(require_viewer)):
    _d4_check()
    return list_rules()

@router.get("/rules/stats")
async def rules_stats(_: User = Depends(require_viewer)):
    _d4_check()
    return get_stats()

@router.get("/rules/{rule_id}")
async def get_single_rule(rule_id: str, _: User = Depends(require_viewer)):
    _d4_check()
    r = get_rule(rule_id)
    if not r:
        raise HTTPException(404, "Rule not found")
    return r

@router.post("/rules")
async def add_rule(body: RuleCreateReq, db: Session = Depends(get_db),
                   cu: User = Depends(require_admin)):
    _d4_check()
    rule = create_rule(body.dict())
    write_audit(db, "create_rule", f"Created rule: {body.name}", user_id=cu.id)
    return rule

@router.put("/rules/{rule_id}")
async def update_existing_rule(rule_id: str, body: RuleUpdateReq,
                                db: Session = Depends(get_db),
                                cu: User = Depends(require_admin)):
    _d4_check()
    updates = {k: v for k, v in body.dict().items() if v is not None}
    rule    = update_rule(rule_id, updates)
    if not rule:
        raise HTTPException(404, "Rule not found")
    write_audit(db, "update_rule", f"Updated rule {rule_id}", user_id=cu.id)
    return rule

@router.delete("/rules/{rule_id}")
async def remove_rule(rule_id: str, db: Session = Depends(get_db),
                      cu: User = Depends(require_admin)):
    _d4_check()
    if not delete_rule(rule_id):
        raise HTTPException(400, "Cannot delete built-in rules or rule not found")
    write_audit(db, "delete_rule", f"Deleted rule {rule_id}", user_id=cu.id)
    return {"ok": True}

@router.post("/rules/{rule_id}/toggle")
async def toggle_existing(rule_id: str, enabled: bool,
                           db: Session = Depends(get_db),
                           cu: User = Depends(require_operator)):
    _d4_check()
    rule = toggle_rule(rule_id, enabled)
    if not rule:
        raise HTTPException(404, "Rule not found")
    write_audit(db, "toggle_rule", f"Rule {rule_id} → {'on' if enabled else 'off'}", user_id=cu.id)
    return rule

@router.get("/rules/alerts/history")
async def alert_history(node_id: Optional[str] = None,
                         severity: Optional[str] = None,
                         limit: int = 100,
                         _: User = Depends(require_viewer)):
    _d4_check()
    return get_alert_history(node_id=node_id, severity=severity, limit=limit)

@router.post("/rules/evaluate")
async def evaluate_metrics(node_id: str, node_name: str, node_os: str,
                            body: IngestReq,
                            _: User = Depends(require_operator)):
    _d4_check()
    return evaluate(node_id, node_name, node_os, body.metrics)


# ── PDF Reports ───────────────────────────────────────────────────────────────

@router.get("/nodes/{node_id}/report/pdf")
async def pdf_report(node_id: str,
                     framework: str = Query("CIS", enum=["CIS","SOC2","HIPAA","PCI"]),
                     db: Session = Depends(get_db),
                     cu: User = Depends(require_operator)):
    _d4_check()
    node = db.query(Node).filter(Node.id == node_id).first()
    if not node:
        raise HTTPException(404, "Node not found")

    nm      = _node_metrics()
    metrics = nm.get(node_id, {})

    scan_r = (db.query(ScanResult)
                .filter(ScanResult.node_id == node_id)
                .order_by(ScanResult.scanned_at.desc()).first())
    comp_r = (db.query(ComplianceReport)
                .filter(ComplianceReport.node_id == node_id)
                .order_by(ComplianceReport.generated_at.desc()).first())

    node_d = {
        "id": node.id, "name": node.name, "os_type": node.os_type,
        "os_pretty": node.os_pretty, "hostname": node.hostname,
        "ip_address": node.ip_address, "is_online": node.id in _connected_agents(),
        "health_score": node.health_score,
        "last_seen": node.last_seen.isoformat() if node.last_seen else None,
    }

    scan_d = {
        "score": max(0, 100 - (scan_r.critical_cve or 0)*20 - (scan_r.high_cve or 0)*5),
        "cve_findings": scan_r.findings or [],
        "summary": {"critical": scan_r.critical_cve, "high": scan_r.high_cve,
                     "medium": scan_r.medium_cve, "low": scan_r.low_cve},
    } if scan_r else None

    comp_d = {
        "framework": comp_r.framework, "score": comp_r.score,
        "passed": comp_r.passed, "failed": comp_r.failed,
        "risk_level": "low" if comp_r.score >= 85 else "medium" if comp_r.score >= 65 else "high",
        "findings": comp_r.findings or [],
        "failed_findings": [f for f in (comp_r.findings or []) if not f.get("passed")],
    } if comp_r else None

    # Get company name from brand settings
    try:
        from .models import BrandSettings
        brand = db.query(BrandSettings).first()
        company = brand.company_name if brand else "JENIX Enterprise"
    except Exception:
        company = "JENIX Enterprise"

    pdf = generate_report(node_d, metrics, scan_d, comp_d, None, company)

    write_audit(db, "generate_pdf", f"PDF report for {node.name}",
                node_id=node_id, user_id=cu.id)

    fn = f"jenix_report_{node.name}_{datetime.utcnow():%Y%m%d_%H%M}.pdf"
    return Response(pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f"attachment; filename={fn}"})
