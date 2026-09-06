#!/bin/bash
set -uo pipefail
cd ~/Desktop/jenix/server || { echo "[ABORT] cannot cd to server dir"; exit 1; }

echo "=== SECTION 1: locate Report B's real generation code ==="
echo "--- grep for _risk_band definition across routes/ ---"
grep -rn "_risk_band\|def _generate_pdf" routes/ 2>/dev/null
echo ""
echo "--- grep for the 3-tier risk band strings, to confirm which file is live ---"
grep -rln "MODERATE\|ELEVATED\|CRITICAL" routes/ 2>/dev/null

echo ""
echo "=== SECTION 2: full reports.py with line numbers (this is the real live file, re-pulled fresh) ==="
cat -n routes/reports.py

echo ""
echo "=== SECTION 3: confirm Report B route registration ==="
grep -n "@router\.\(get\|post\)" routes/reports.py

echo ""
echo "=== SECTION 4: any separate Report B module (in case _generate_pdf lives outside reports.py) ==="
find . -iname "*.py" | xargs grep -ln "SecurityAlerts\|Security Alerts\|Recommended Action" 2>/dev/null

echo ""
echo "=== SECTION 5: existing .bak_* files touching reports.py or any report-b-ish file, for history ==="
ls -la routes/*.bak_* 2>/dev/null

echo ""
echo "=== DONE — paste this ENTIRE output back ==="
