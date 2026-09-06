#!/bin/bash
set -uo pipefail

FLOOR1=~/Desktop/jenix/server
FLOOR2=~/Desktop/sales/jenix/server

echo "=== SECTION 1: does Floor 2 even have audit_trail_report.py yet? ==="
if [ -f "$FLOOR2/routes/audit_trail_report.py" ]; then
  echo "EXISTS on Floor 2"
  ls -la "$FLOOR2/routes/audit_trail_report.py"
else
  echo "DOES NOT EXIST on Floor 2 — this is a brand-new file this session, needs to be copied over wholesale"
fi

echo ""
echo "=== SECTION 2: diff reports.py Floor 1 vs Floor 2 (full diff, no truncation) ==="
diff -u "$FLOOR2/routes/reports.py" "$FLOOR1/routes/reports.py" > ~/Desktop/jenix/reports_floor_diff.txt
DIFF_LINES=$(wc -l < ~/Desktop/jenix/reports_floor_diff.txt)
echo "Diff is $DIFF_LINES lines. Full diff:"
cat ~/Desktop/jenix/reports_floor_diff.txt

echo ""
echo "=== SECTION 3: Floor 2's current reports.py imports, to check for pre-existing divergence ==="
head -15 "$FLOOR2/routes/reports.py"

echo ""
echo "=== SECTION 4: Floor 2's own _generate_pdf risk-band section, to check if Floor 2 already has different local edits ==="
grep -n "_risk_band\|def _generate_pdf\|def _scope_of" "$FLOOR2/routes/reports.py"

echo ""
echo "=== SECTION 5: Floor 2's git status, to see if IT has any uncommitted local changes we'd clobber ==="
cd ~/Desktop/sales/jenix
git status 2>/dev/null || echo "not a git repo or git unavailable here"

echo ""
echo "=== SECTION 6: Floor 2 venv / reportlab version check (v56 doc notes Floor 2 has its own separate venv, reportlab 4.2.2) ==="
if [ -d ~/Desktop/sales/jenix/server_venv ] || [ -d ~/Desktop/sales/jenix/venv ]; then
  find ~/Desktop/sales/jenix -maxdepth 1 -iname "*venv*"
else
  echo "No obvious venv dir found at expected location — will need to locate it before any restart"
fi

echo ""
echo "=== SECTION 7: confirm Floor 2's live port/process, so we know what to restart later ==="
lsof -i :8001 -sTCP:LISTEN 2>/dev/null || echo "nothing currently listening on :8001"

echo ""
echo "=== DONE — paste this ENTIRE output back ==="
