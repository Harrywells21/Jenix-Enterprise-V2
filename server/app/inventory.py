"""
JENIX Enterprise v3.0 — Asset Inventory & CMDB Export
Builds normalized asset records, detects network topology,
exports to CSV / JSON / ServiceNow / Jira Assets formats.
"""

import csv
import io
import ipaddress
import json
from datetime import datetime
from typing import Dict, List, Optional


# ── Build asset record ────────────────────────────────────────────────────────

def build_asset(node: dict, metrics: dict) -> dict:
    cpu    = metrics.get("cpu",      {})
    mem    = metrics.get("memory",   {})
    disks  = metrics.get("disks",    [])
    net    = metrics.get("network",  [])
    svcs   = metrics.get("services", [])
    ports  = metrics.get("ports",    [])
    os_i   = metrics.get("os_info",  {})

    ifaces = []
    for iface in net:
        addrs = [a.get("address", "") for a in iface.get("addresses", []) if a.get("address")]
        ifaces.append({
            "name":       iface.get("name"),
            "is_up":      iface.get("is_up", False),
            "speed_mbps": iface.get("speed_mbps", 0),
            "addresses":  addrs,
        })

    volumes = [{
        "device":     d.get("device"),
        "mountpoint": d.get("mountpoint"),
        "fstype":     d.get("fstype"),
        "total_gb":   round(d.get("total", 0) / 1073741824, 1),
        "used_gb":    round(d.get("used",  0) / 1073741824, 1),
        "free_gb":    round(d.get("free",  0) / 1073741824, 1),
        "percent":    d.get("percent", 0),
    } for d in disks]

    return {
        "asset_id":          node["id"],
        "hostname":          node.get("hostname") or node.get("name"),
        "display_name":      node.get("name"),
        "ip_address":        node.get("ip_address"),
        "fqdn":              os_i.get("fqdn", node.get("hostname", "")),
        "os_type":           node.get("os_type", "Linux"),
        "os_name":           node.get("os_pretty") or os_i.get("os_pretty", ""),
        "os_version":        os_i.get("os_version", ""),
        "architecture":      os_i.get("arch", "x86_64"),
        "asset_type":        "server",
        "cpu_logical":       cpu.get("cpu_count", 0),
        "cpu_physical":      cpu.get("cpu_count_phys", 0),
        "cpu_freq_ghz":      round((cpu.get("cpu_freq", {}) or {}).get("max", 0) / 1000, 2),
        "ram_gb":            round(mem.get("ram_total", 0) / 1073741824, 1),
        "disk_total_gb":     round(sum(v["total_gb"] for v in volumes), 1),
        "volumes":           volumes,
        "network_interfaces":ifaces,
        "status":            "online" if node.get("is_online") else "offline",
        "health_score":      node.get("health_score", 0),
        "last_seen":         node.get("last_seen"),
        "registered_at":     node.get("registered_at"),
        "tags":              node.get("tags", []),
        "listening_ports":   [p.get("port") for p in ports],
        "running_services":  [s.get("name") for s in svcs if s.get("active") == "active" or s.get("status") == 4],
        "collected_at":      datetime.utcnow().isoformat(),
        "jenix_version":     "3.0.0",
    }


# ── Network topology detection ────────────────────────────────────────────────

def detect_topology(assets: List[dict]) -> dict:
    subnets:    Dict[str, List[str]] = {}
    svc_groups: Dict[str, List[str]] = {}
    gateways:   List[str]            = []
    edges:      List[dict]           = []

    for a in assets:
        ip = a.get("ip_address", "")
        if ip:
            try:
                net = str(ipaddress.IPv4Network(f"{ip}/24", strict=False))
                subnets.setdefault(net, []).append(a["asset_id"])
            except Exception:
                pass

        ports = set(a.get("listening_ports", []))
        ifaces = [i for i in a.get("network_interfaces", []) if i.get("is_up")]
        if {22, 80, 443}.issubset(ports) and len(ifaces) >= 1:
            gateways.append(a["asset_id"])

        for svc in a.get("running_services", []):
            svc_groups.setdefault(svc, []).append(a["asset_id"])

    # Subnet edges
    for subnet, ids in subnets.items():
        for i in range(len(ids)):
            for j in range(i + 1, len(ids)):
                edges.append({"source": ids[i], "target": ids[j], "type": "same_subnet", "subnet": subnet})

    # Service cluster edges
    for svc, ids in svc_groups.items():
        if len(ids) >= 2:
            for i in range(len(ids)):
                for j in range(i + 1, len(ids)):
                    edges.append({"source": ids[i], "target": ids[j], "type": "shared_service", "service": svc})

    return {
        "subnets":           subnets,
        "gateways":          gateways,
        "service_clusters":  {k: v for k, v in svc_groups.items() if len(v) >= 2},
        "edges":             edges[:300],
        "generated_at":      datetime.utcnow().isoformat(),
    }


# ── Risk score ────────────────────────────────────────────────────────────────

def risk_score(asset: dict, cve_summary: dict, compliance_score: int) -> dict:
    critical   = cve_summary.get("critical", 0)
    high       = cve_summary.get("high",     0)
    medium     = cve_summary.get("medium",   0)
    cve_risk   = min(40, critical * 10 + high * 5 + medium * 2)
    comp_risk  = max(0, 30 - round(compliance_score * 0.30))
    health     = asset.get("health_score", 100)
    health_risk= max(0, 20 - round(health * 0.20))
    port_risk  = min(10, len(asset.get("listening_ports", [])) // 3)
    total      = cve_risk + comp_risk + health_risk + port_risk
    level      = "critical" if total >= 60 else "high" if total >= 40 else "medium" if total >= 20 else "low"
    recs       = []
    if critical > 0: recs.append(f"URGENT: Patch {critical} critical CVE(s) immediately")
    if high     > 0: recs.append(f"Patch {high} high-severity CVE(s) within 72 hours")
    if compliance_score < 70: recs.append(f"Compliance {compliance_score}% below threshold — run hardening playbook")
    if not recs: recs.append("Asset within acceptable risk parameters")
    return {"asset_id": asset["asset_id"], "total": total, "level": level,
            "cve_risk": cve_risk, "comp_risk": comp_risk, "health_risk": health_risk,
            "port_risk": port_risk, "recommendations": recs}


# ── Export formats ────────────────────────────────────────────────────────────

_CSV_FIELDS = [
    "asset_id","hostname","display_name","ip_address","fqdn",
    "os_type","os_name","os_version","architecture","asset_type",
    "cpu_logical","cpu_physical","ram_gb","disk_total_gb",
    "status","health_score","last_seen","registered_at",
    "listening_ports","running_services","tags","collected_at",
]

def export_csv(assets: List[dict]) -> str:
    out = io.StringIO()
    w   = csv.DictWriter(out, fieldnames=_CSV_FIELDS, extrasaction="ignore")
    w.writeheader()
    for a in assets:
        row = {**a}
        for k in ("listening_ports", "running_services", "tags"):
            row[k] = ",".join(str(v) for v in (row.get(k) or []))
        w.writerow(row)
    return out.getvalue()


def export_json(assets: List[dict], topology: Optional[dict] = None) -> str:
    return json.dumps({
        "export_version": "1.0",
        "generator":      "JENIX Enterprise v3.0",
        "generated_at":   datetime.utcnow().isoformat(),
        "total":          len(assets),
        "assets":         assets,
        "topology":       topology or {},
    }, indent=2, default=str)


def export_servicenow(assets: List[dict]) -> List[dict]:
    records = []
    for a in assets:
        os_type = a.get("os_type", "Linux")
        table = ("cmdb_ci_win_server"  if os_type == "Windows" else
                 "cmdb_ci_mac_desktop" if os_type == "Darwin"  else
                 "cmdb_ci_linux_server")
        records.append({
            "_table":            table,
            "name":              a.get("hostname", ""),
            "host_name":         a.get("hostname", ""),
            "ip_address":        a.get("ip_address", ""),
            "fqdn":              a.get("fqdn", ""),
            "os":                a.get("os_name", ""),
            "os_version":        a.get("os_version", ""),
            "cpu_count":         a.get("cpu_logical", 0),
            "ram":               f"{a.get('ram_gb',0)} GB",
            "disk_space":        f"{a.get('disk_total_gb',0)} GB",
            "operational_status":"1" if a.get("status") == "online" else "2",
            "asset_tag":         a.get("asset_id", ""),
            "short_description": f"JENIX Managed — {a.get('os_type','Linux')}",
            "last_discovered":   a.get("collected_at", ""),
        })
    return records


def export_jira(assets: List[dict]) -> List[dict]:
    return [{
        "objectType": "Server",
        "attributes": {
            "Name":         a.get("hostname", ""),
            "IP Address":   a.get("ip_address", ""),
            "OS":           a.get("os_name", ""),
            "OS Type":      a.get("os_type", ""),
            "CPU Cores":    a.get("cpu_logical", 0),
            "RAM GB":       a.get("ram_gb", 0),
            "Disk GB":      a.get("disk_total_gb", 0),
            "Status":       a.get("status", ""),
            "Health Score": a.get("health_score", 0),
            "Tags":         ",".join(a.get("tags", [])),
            "JENIX ID":     a.get("asset_id", ""),
        }
    } for a in assets]
