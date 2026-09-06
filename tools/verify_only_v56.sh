#!/bin/bash
set -uo pipefail
cd ~/Desktop/jenix/server || { echo "[ABORT] cannot cd to server dir"; exit 1; }

echo "=== SECTION 1: py_compile check on both files ==="
python3 -m py_compile routes/audit_trail_report.py routes/reports.py
echo "py_compile exit: $?"

echo ""
echo "=== SECTION 2: real import test ==="
source ~/Desktop/jenix/server_venv/bin/activate
python3 -c "import routes.reports; print('IMPORT OK')"
echo "import test exit: $?"

echo ""
echo "=== SECTION 3: write scripted restart (file first, syntax-checked, never inline) ==="
cat > ~/Desktop/jenix/restart_floor1_v56.sh << 'RESTARTEOF'
#!/bin/bash
set -uo pipefail
OLDPID=$(lsof -ti :8000 -sTCP:LISTEN 2>/dev/null || echo "")
if [ -n "$OLDPID" ]; then
  echo "Killing old Floor 1 PID: $OLDPID"
  kill "$OLDPID" 2>/dev/null
  sleep 1
  if lsof -ti :8000 -sTCP:LISTEN >/dev/null 2>&1; then
    kill -9 "$OLDPID" 2>/dev/null
    sleep 1
  fi
else
  echo "No existing process on :8000"
fi
cd ~/Desktop/jenix/server
source ~/Desktop/jenix/server_venv/bin/activate
setsid nohup uvicorn main:app --host 0.0.0.0 --port 8000 > ~/Desktop/jenix/floor1_v56_restart.log 2>&1 < /dev/null &
disown
sleep 4
NEWPID=$(lsof -ti :8000 -sTCP:LISTEN 2>/dev/null || echo "NONE")
echo "New Floor 1 PID: $NEWPID"
curl -m 5 -s -o /dev/null -w "curl http status: %{http_code}\n" http://localhost:8000/
echo "--- FULL restart log (not tail) ---"
cat ~/Desktop/jenix/floor1_v56_restart.log
RESTARTEOF
bash -n ~/Desktop/jenix/restart_floor1_v56.sh
echo "restart script syntax check exit: $?"
bash ~/Desktop/jenix/restart_floor1_v56.sh

echo ""
echo "=== SECTION 4: real login ==="
LOGIN_RESP=$(curl -s -X POST http://localhost:8000/api/auth/login \
  -d "username=admin@jenix.io&password=admin123" \
  -H "Content-Type: application/x-www-form-urlencoded")
echo "Raw login response: $LOGIN_RESP"
TOKEN=$(echo "$LOGIN_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin).get('access_token',''))" 2>/dev/null || echo "")
if [ -z "$TOKEN" ]; then
  echo "[ABORT] Login failed — no token extracted. Stop here."
  exit 1
fi
echo "Token acquired (length: ${#TOKEN})"

echo ""
echo "=== SECTION 5: real POST /api/reports/audit against the SAME real 72-row dataset ==="
GEN_RESP=$(curl -s -X POST http://localhost:8000/api/reports/audit -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json")
echo "Raw generation response: $GEN_RESP"
REPORT_ID=$(echo "$GEN_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin).get('report_id',''))" 2>/dev/null || echo "")
echo "Report ID: $REPORT_ID"
if [ -z "$REPORT_ID" ]; then
  echo "[ABORT] No report_id returned — cannot proceed to download."
  exit 1
fi

echo ""
echo "=== SECTION 6: download the regenerated PDF via the confirmed download route ==="
curl -s -X GET "http://localhost:8000/api/reports/${REPORT_ID}/download" -H "Authorization: Bearer $TOKEN" -o ~/Desktop/jenix_audit_report_v56.pdf
ls -la ~/Desktop/jenix_audit_report_v56.pdf

echo ""
echo "=== SECTION 7: real GET /api/reports/audit/csv ==="
curl -s -X GET http://localhost:8000/api/reports/audit/csv -H "Authorization: Bearer $TOKEN" -o ~/Desktop/jenix_audit_export_v56.csv
ls -la ~/Desktop/jenix_audit_export_v56.csv

echo ""
echo "=== SECTION 8: page count sanity check via pypdf (already in venv) ==="
python3 -c "
from pypdf import PdfReader
r = PdfReader('/home/aadi/Desktop/jenix_audit_report_v56.pdf')
print(f'Page count: {len(r.pages)}')
"

echo ""
echo "=== DONE — paste this ENTIRE output back, then upload both files: ==="
echo "~/Desktop/jenix_audit_report_v56.pdf"
echo "~/Desktop/jenix_audit_export_v56.csv"
