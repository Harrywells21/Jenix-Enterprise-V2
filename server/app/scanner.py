"""
JENIX Enterprise — CVE Scanner Engine
Scans packages against OSV.dev + OS-specific security checks
"""

import asyncio
import json
import platform
import re
import subprocess
from datetime import datetime
from typing import List, Dict, Any

import httpx

OSV_BATCH_URL = "https://api.osv.dev/v1/querybatch"
OSV_QUERY_URL = "https://api.osv.dev/v1/query"


# ── Package collectors ─────────────────────────────────────────────────────

def get_packages_linux() -> List[Dict]:
    packages = []
    # dpkg (Debian/Ubuntu)
    try:
        result = subprocess.run(
            ["dpkg-query", "-W", "-f=${Package}\t${Version}\t${Architecture}\n"],
            capture_output=True, text=True, timeout=30
        )
        for line in result.stdout.splitlines():
            parts = line.strip().split("\t")
            if len(parts) >= 2:
                packages.append({"name": parts[0], "version": parts[1],
                                  "ecosystem": "Debian"})
    except Exception:
        pass
    # rpm (RHEL/CentOS)
    if not packages:
        try:
            result = subprocess.run(
                ["rpm", "-qa", "--queryformat", "%{NAME}\t%{VERSION}\n"],
                capture_output=True, text=True, timeout=30
            )
            for line in result.stdout.splitlines():
                parts = line.strip().split("\t")
                if len(parts) == 2:
                    packages.append({"name": parts[0], "version": parts[1],
                                      "ecosystem": "Red Hat"})
        except Exception:
            pass
    # pip packages
    try:
        result = subprocess.run(
            ["pip3", "list", "--format=json"],
            capture_output=True, text=True, timeout=15
        )
        for pkg in json.loads(result.stdout):
            packages.append({"name": pkg["name"], "version": pkg["version"],
                              "ecosystem": "PyPI"})
    except Exception:
        pass
    return packages

def get_packages_macos() -> List[Dict]:
    packages = []
    # Homebrew
    try:
        result = subprocess.run(
            ["brew", "list", "--versions"],
            capture_output=True, text=True, timeout=30
        )
        for line in result.stdout.splitlines():
            parts = line.strip().split()
            if len(parts) >= 2:
                packages.append({"name": parts[0], "version": parts[1],
                                  "ecosystem": "Homebrew"})
    except Exception:
        pass
    # pip
    try:
        result = subprocess.run(
            ["pip3", "list", "--format=json"],
            capture_output=True, text=True, timeout=15
        )
        for pkg in json.loads(result.stdout):
            packages.append({"name": pkg["name"], "version": pkg["version"],
                              "ecosystem": "PyPI"})
    except Exception:
        pass
    return packages

def get_packages_windows() -> List[Dict]:
    packages = []
    # winget
    try:
        result = subprocess.run(
            ["winget", "list", "--source", "winget"],
            capture_output=True, text=True, timeout=30
        )
        for line in result.stdout.splitlines()[2:]:
            parts = line.strip().split()
            if len(parts) >= 2:
                packages.append({"name": parts[0], "version": parts[-1],
                                  "ecosystem": "winget"})
    except Exception:
        pass
    # pip
    try:
        result = subprocess.run(
            ["pip", "list", "--format=json"],
            capture_output=True, text=True, timeout=15
        )
        for pkg in json.loads(result.stdout):
            packages.append({"name": pkg["name"], "version": pkg["version"],
                              "ecosystem": "PyPI"})
    except Exception:
        pass
    return packages

def get_installed_packages() -> List[Dict]:
    system = platform.system()
    if system == "Linux":
        return get_packages_linux()
    elif system == "Darwin":
        return get_packages_macos()
    elif system == "Windows":
        return get_packages_windows()
    return []


# ── OSV.dev CVE lookup ─────────────────────────────────────────────────────

async def query_osv_batch(packages: List[Dict]) -> List[Dict]:
    """Query OSV.dev for CVEs in batches of 100."""
    findings = []
    batch_size = 100

    async with httpx.AsyncClient(timeout=30) as client:
        for i in range(0, len(packages), batch_size):
            batch = packages[i:i + batch_size]
            queries = []
            for pkg in batch:
                ecosystem = pkg.get("ecosystem", "PyPI")
                queries.append({
                    "package": {
                        "name":      pkg["name"],
                        "ecosystem": ecosystem,
                        "version":   pkg.get("version", ""),
                    }
                })
            try:
                resp = await client.post(OSV_BATCH_URL,
                                         json={"queries": queries})
                if resp.status_code == 200:
                    data = resp.json()
                    for idx, result in enumerate(data.get("results", [])):
                        vulns = result.get("vulns", [])
                        if vulns:
                            pkg = batch[idx]
                            for v in vulns:
                                severity = get_severity(v)
                                findings.append({
                                    "package":     pkg["name"],
                                    "version":     pkg.get("version", ""),
                                    "ecosystem":   pkg.get("ecosystem", ""),
                                    "cve_id":      v.get("id", ""),
                                    "aliases":     v.get("aliases", []),
                                    "severity":    severity,
                                    "summary":     v.get("summary", ""),
                                    "details":     v.get("details", "")[:500],
                                    "published":   v.get("published", ""),
                                    "link":        f"https://osv.dev/vulnerability/{v.get('id','')}",
                                })
            except Exception as e:
                print(f"[CVE] OSV batch error: {e}")

    return findings

def get_severity(vuln: dict) -> str:
    """Extract highest severity from a vuln record."""
    severity_map = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
    highest = "LOW"
    for s in vuln.get("severity", []):
        level = s.get("type", "LOW").upper()
        if level in severity_map:
            if severity_map.get(level, 9) < severity_map.get(highest, 9):
                highest = level
    # Check database_specific
    for db in vuln.get("database_specific", {}).get("severity", []):
        level = str(db).upper()
        if level in severity_map:
            if severity_map.get(level, 9) < severity_map.get(highest, 9):
                highest = level
    return highest


# ── OS security checks ─────────────────────────────────────────────────────

def run_linux_security_checks() -> List[Dict]:
    checks = []

    def check(name, cmd, pass_if_empty=True, severity="medium"):
        try:
            result = subprocess.run(cmd, shell=True, capture_output=True,
                                    text=True, timeout=10)
            output = result.stdout.strip()
            passed = (not output) if pass_if_empty else bool(output)
            checks.append({"name": name, "passed": passed,
                            "output": output[:300], "severity": severity})
        except Exception as e:
            checks.append({"name": name, "passed": False,
                            "output": str(e), "severity": severity})

    check("SSH root login disabled",
          "grep -E '^PermitRootLogin yes' /etc/ssh/sshd_config", True, "critical")
    check("Password auth disabled",
          "grep -E '^PasswordAuthentication yes' /etc/ssh/sshd_config", True, "high")
    check("Empty password accounts",
          "awk -F: '($2==\"\"){print $1}' /etc/shadow 2>/dev/null", True, "critical")
    check("SUID files (non-standard)",
          "find / -perm -4000 -type f 2>/dev/null | grep -v -E '^/(usr/bin|usr/sbin|bin|sbin)'",
          True, "high")
    check("World-writable dirs",
          "find / -xdev -type d -perm -0002 -not -path '/proc/*' 2>/dev/null | head -5",
          True, "medium")
    check("Firewall active",
          "systemctl is-active ufw || systemctl is-active firewalld 2>/dev/null",
          False, "high")
    check("Unattended upgrades enabled",
          "dpkg -l unattended-upgrades 2>/dev/null | grep '^ii'", False, "medium")
    check("Core dumps disabled",
          "grep -E '^\\* hard core 0' /etc/security/limits.conf", False, "low")
    return checks

def run_macos_security_checks() -> List[Dict]:
    checks = []

    def check(name, cmd, pass_if_empty=True, severity="medium"):
        try:
            result = subprocess.run(cmd, shell=True, capture_output=True,
                                    text=True, timeout=10)
            output = result.stdout.strip()
            passed = (not output) if pass_if_empty else bool(output)
            checks.append({"name": name, "passed": passed,
                            "output": output[:300], "severity": severity})
        except Exception as e:
            checks.append({"name": name, "passed": False,
                            "output": str(e), "severity": severity})

    check("Firewall enabled",
          "defaults read /Library/Preferences/com.apple.alf globalstate 2>/dev/null | grep -v '^0$'",
          False, "high")
    check("SIP enabled",
          "csrutil status 2>/dev/null | grep -i enabled", False, "critical")
    check("FileVault enabled",
          "fdesetup status 2>/dev/null | grep -i 'FileVault is On'", False, "critical")
    check("Gatekeeper enabled",
          "spctl --status 2>/dev/null | grep assessments", False, "high")
    check("Remote login disabled",
          "systemsetup -getremotelogin 2>/dev/null | grep -i off", False, "medium")
    check("Automatic updates enabled",
          "defaults read /Library/Preferences/com.apple.SoftwareUpdate AutomaticCheckEnabled 2>/dev/null | grep 1",
          False, "medium")
    return checks

def run_windows_security_checks() -> List[Dict]:
    checks = []

    def ps_check(name, ps_cmd, pass_if_output=True, severity="medium"):
        try:
            result = subprocess.run(
                ["powershell", "-NoProfile", "-Command", ps_cmd],
                capture_output=True, text=True, timeout=15
            )
            output = result.stdout.strip()
            passed = bool(output) if pass_if_output else not bool(output)
            checks.append({"name": name, "passed": passed,
                            "output": output[:300], "severity": severity})
        except Exception as e:
            checks.append({"name": name, "passed": False,
                            "output": str(e), "severity": severity})

    ps_check("Windows Defender enabled",
             "(Get-MpComputerStatus).AntivirusEnabled", True, "critical")
    ps_check("Windows Firewall active",
             "(Get-NetFirewallProfile | Where-Object {$_.Enabled}).Name", True, "high")
    ps_check("Windows Update service running",
             "(Get-Service wuauserv).Status", True, "medium")
    ps_check("BitLocker enabled",
             "manage-bde -status C: | Select-String 'Protection On'", True, "critical")
    ps_check("Guest account disabled",
             "(Get-LocalUser Guest).Enabled | Where-Object {$_ -eq $false}", True, "high")
    ps_check("SMBv1 disabled",
             "(Get-WindowsOptionalFeature -Online -FeatureName SMB1Protocol).State | Where-Object {$_ -eq 'Disabled'}",
             True, "high")
    ps_check("UAC enabled",
             "Get-ItemProperty HKLM:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Policies\\System | Select-Object -ExpandProperty EnableLUA",
             True, "high")
    return checks

def run_security_checks() -> List[Dict]:
    system = platform.system()
    if system == "Linux":
        return run_linux_security_checks()
    elif system == "Darwin":
        return run_macos_security_checks()
    elif system == "Windows":
        return run_windows_security_checks()
    return []


# ── Main scan runner ───────────────────────────────────────────────────────

async def run_full_scan(node_id: str) -> Dict[str, Any]:
    """Run a full CVE + security scan on this machine."""
    started = datetime.utcnow()
    packages = get_installed_packages()
    cve_findings = await query_osv_batch(packages)
    security_checks = run_security_checks()

    summary = {
        "critical": sum(1 for f in cve_findings if f["severity"] == "CRITICAL"),
        "high":     sum(1 for f in cve_findings if f["severity"] == "HIGH"),
        "medium":   sum(1 for f in cve_findings if f["severity"] == "MEDIUM"),
        "low":      sum(1 for f in cve_findings if f["severity"] == "LOW"),
    }

    return {
        "node_id":         node_id,
        "scanned_at":      started.isoformat(),
        "duration_secs":   (datetime.utcnow() - started).seconds,
        "total_packages":  len(packages),
        "cve_findings":    cve_findings,
        "security_checks": security_checks,
        "summary":         summary,
        "score":           max(0, 100 - summary["critical"] * 20
                                      - summary["high"] * 5
                                      - summary["medium"] * 2
                                      - summary["low"]),
    }
