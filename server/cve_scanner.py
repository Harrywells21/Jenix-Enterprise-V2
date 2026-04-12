"""
JENIX CVE Scanner — checks installed packages against known vulnerabilities.
Uses Ubuntu/Debian security advisories and OSV.dev API.
"""
import json, urllib.request, subprocess, os
from datetime import datetime

OSV_API = "https://api.osv.dev/v1/query"

def get_installed_packages() -> list[dict]:
    """Get list of installed packages via dpkg."""
    try:
        result = subprocess.run(
            ["dpkg-query", "-W", "-f=${Package}\t${Version}\n"],
            capture_output=True, text=True, timeout=10
        )
        packages = []
        for line in result.stdout.strip().split("\n"):
            if "\t" in line:
                name, version = line.split("\t", 1)
                packages.append({"name": name.strip(),
                                  "version": version.strip()})
        return packages[:50]  # Limit to 50 for performance
    except Exception as e:
        print(f"[cve] get_installed_packages error: {e}")
        return []

def check_package_osv(package_name: str,
                       version: str) -> list[dict]:
    """Query OSV.dev for vulnerabilities in a package."""
    try:
        payload = json.dumps({
            "package": {
                "name":      package_name,
                "ecosystem": "Debian"
            },
            "version": version
        }).encode()

        req = urllib.request.Request(
            OSV_API, data=payload,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=5) as r:
            data  = json.loads(r.read())
            vulns = data.get("vulns", [])
            result = []
            for v in vulns[:3]:  # Max 3 CVEs per package
                result.append({
                    "id":       v.get("id", "Unknown"),
                    "summary":  v.get("summary", "No summary")[:100],
                    "severity": _get_severity(v),
                    "url":      f"https://osv.dev/vulnerability/{v.get('id','')}",
                })
            return result
    except Exception:
        return []

def _get_severity(vuln: dict) -> str:
    try:
        severity = vuln.get("database_specific", {}).get("severity", "")
        if severity:
            return severity
        cvss = vuln.get("severity", [])
        if cvss:
            score = cvss[0].get("score", "")
            if score:
                score_val = float(score.split("/")[0].split(":")[-1]
                                  if "/" in str(score) else score)
                if score_val >= 9:   return "CRITICAL"
                if score_val >= 7:   return "HIGH"
                if score_val >= 4:   return "MEDIUM"
                return "LOW"
    except Exception:
        pass
    return "UNKNOWN"

def run_cve_scan(max_packages: int = 20) -> dict:
    """
    Run a CVE scan on installed packages.
    Returns summary + vulnerable packages list.
    """
    packages  = get_installed_packages()[:max_packages]
    results   = []
    total_vulns = 0

    for pkg in packages:
        vulns = check_package_osv(pkg["name"], pkg["version"])
        if vulns:
            total_vulns += len(vulns)
            results.append({
                "package":  pkg["name"],
                "version":  pkg["version"],
                "vulns":    vulns,
                "count":    len(vulns),
                "highest":  _highest_severity(vulns),
            })

    critical = sum(1 for r in results
                   for v in r["vulns"] if v["severity"] == "CRITICAL")
    high     = sum(1 for r in results
                   for v in r["vulns"] if v["severity"] == "HIGH")

    return {
        "scanned_at":         datetime.utcnow().isoformat(),
        "packages_scanned":   len(packages),
        "vulnerable_packages": len(results),
        "total_vulns":        total_vulns,
        "critical":           critical,
        "high":               high,
        "results":            results,
        "risk_level":         "CRITICAL" if critical > 0
                              else "HIGH" if high > 0
                              else "MEDIUM" if total_vulns > 0
                              else "LOW",
    }

def _highest_severity(vulns: list) -> str:
    order = {"CRITICAL":4, "HIGH":3, "MEDIUM":2, "LOW":1, "UNKNOWN":0}
    return max(vulns, key=lambda v: order.get(v["severity"], 0),
               default={"severity":"UNKNOWN"})["severity"]
