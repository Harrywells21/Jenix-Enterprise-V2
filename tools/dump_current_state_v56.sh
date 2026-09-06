#!/bin/bash
set -uo pipefail
cd ~/Desktop/jenix/server || { echo "[ABORT] cannot cd to server dir"; exit 1; }

echo "=== SECTION 1: full audit_trail_report.py with line numbers ==="
cat -n routes/audit_trail_report.py

echo ""
echo "=== SECTION 2: confirm no patch script survives anywhere (broader search, no keyword filter) ==="
find ~/Desktop/jenix -maxdepth 3 -iname "*.py" -newer routes/reports.py 2>/dev/null | grep -v "server_venv"
echo "--- also check home dir and Downloads directly, in case it was saved outside the repo ---"
find ~/Downloads ~/Desktop -maxdepth 2 -iname "*patch*" 2>/dev/null
find ~/Downloads ~/Desktop -maxdepth 2 -iname "*narrative*" 2>/dev/null
find ~/Downloads ~/Desktop -maxdepth 2 -iname "*fingerprint*" 2>/dev/null

echo ""
echo "=== SECTION 3: confirm neither fix has already silently landed (sanity check before rebuilding a patch) ==="
grep -n "fingerprint" routes/audit_trail_report.py
echo "---"
grep -n "_window_and_date\|def build_executive_summary\|def notable_security_events" routes/audit_trail_report.py

echo ""
echo "=== SECTION 4: list existing .bak_* files for this file, to confirm nothing already ran ==="
ls -la routes/*.bak_* 2>/dev/null || echo "no .bak_* files found for routes/"

echo ""
echo "=== SECTION 5: current git status / diff, if this is a git repo, as another cross-check ==="
cd ~/Desktop/jenix
git status 2>/dev/null || echo "not a git repo or git unavailable here"
git diff routes/audit_trail_report.py 2>/dev/null | head -100 || echo "no diff available"

echo ""
echo "=== DONE — paste this ENTIRE output back ==="
