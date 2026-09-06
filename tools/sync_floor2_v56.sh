#!/bin/bash
set -uo pipefail

FLOOR1=~/Desktop/jenix/server
FLOOR2=~/Desktop/sales/jenix/server
TS=$(date +%Y%m%d_%H%M%S)

echo "=== SECTION 1: backup Floor 2's current reports.py before touching it ==="
cp "$FLOOR2/routes/reports.py" "$FLOOR2/routes/reports.py.bak_presync_${TS}"
ls -la "$FLOOR2/routes/reports.py.bak_presync_${TS}"

echo ""
echo "=== SECTION 2: copy audit_trail_report.py wholesale (new file, no Floor 2 version exists) ==="
cp "$FLOOR1/routes/audit_trail_report.py" "$FLOOR2/routes/audit_trail_report.py"
ls -la "$FLOOR2/routes/audit_trail_report.py"

echo ""
echo "=== SECTION 3: copy reports.py wholesale (diff showed zero Floor-2-specific divergence, Floor 2 strictly behind) ==="
cp "$FLOOR1/routes/reports.py" "$FLOOR2/routes/reports.py"
ls -la "$FLOOR2/routes/reports.py"

echo ""
echo "=== SECTION 4: confirm the copies are now byte-identical to Floor 1 ==="
diff "$FLOOR1/routes/reports.py" "$FLOOR2/routes/reports.py" && echo "reports.py: IDENTICAL"
diff "$FLOOR1/routes/audit_trail_report.py" "$FLOOR2/routes/audit_trail_report.py" && echo "audit_trail_report.py: IDENTICAL"

echo ""
echo "=== SECTION 5: py_compile check on Floor 2's OWN venv (reportlab 4.2.2, may differ from Floor 1) ==="
cd "$FLOOR2"
source ~/Desktop/sales/jenix/server_venv/bin/activate
python3 -m py_compile routes/reports.py routes/audit_trail_report.py
echo "py_compile exit: $?"

echo ""
echo "=== SECTION 6: real import test on Floor 2's venv ==="
python3 -c "import routes.reports; print('IMPORT OK on Floor 2')"
echo "import test exit: $?"

echo ""
echo "=== SECTION 7: scripted restart of Floor 2 (file first, never inline) ==="
cat > ~/Desktop/jenix/restart_floor2_v56.sh << 'RESTARTEOF'
#!/bin/bash
set -uo pipefail
OLDPID=$(lsof -ti :8001 -sTCP:LISTEN 2>/dev/null || echo "")
if [ -n "$OLDPID" ]; then
  echo "Killing old Floor 2 PID: $OLDPID"
  kill "$OLDPID" 2>/dev/null
  sleep 1
  if lsof -ti :8001 -sTCP:LISTEN >/dev/null 2>&1; then
    kill -9 "$OLDPID" 2>/dev/null
    sleep 1
  fi
else
  echo "No existing process on :8001"
fi
cd ~/Desktop/sales/jenix/server
source ~/Desktop/sales/jenix/server_venv/bin/activate
setsid nohup uvicorn main:app --host 0.0.0.0 --port 8001 > ~/Desktop/jenix/floor2_v56_restart.log 2>&1 < /dev/null &
disown
sleep 4
NEWPID=$(lsof -ti :8001 -sTCP:LISTEN 2>/dev/null || echo "NONE")
echo "New Floor 2 PID: $NEWPID"
curl -m 5 -s -o /dev/null -w "curl http status: %{http_code}\n" http://localhost:8001/
echo "--- FULL restart log (not tail) ---"
cat ~/Desktop/jenix/floor2_v56_restart.log
RESTARTEOF
bash -n ~/Desktop/jenix/restart_floor2_v56.sh
echo "restart script syntax check exit: $?"
bash ~/Desktop/jenix/restart_floor2_v56.sh

echo ""
echo "=== SECTION 8: real login on Floor 2 (form-encoded, same creds pattern) ==="
LOGIN_RESP=$(curl -s -X POST http://localhost:8001/api/auth/login \
  -d "username=admin@jenix.io&password=admin123" \
  -H "Content-Type: application/x-www-form-urlencoded")
echo "Raw login response: $LOGIN_RESP"
TOKEN=$(echo "$LOGIN_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin).get('access_token',''))" 2>/dev/null || echo "")
if [ -z "$TOKEN" ]; then
  echo "[NOTE] Login failed or returned no token on Floor 2 — may be expected if Floor 2 has no seeded admin/DB rows yet. Stopping generation test here; sync of files is still complete."
  exit 0
fi
echo "Token acquired (length: ${#TOKEN})"

echo ""
echo "=== SECTION 9: real POST /api/reports/audit on Floor 2, whatever real data it has ==="
GEN_RESP=$(curl -s -X POST http://localhost:8001/api/reports/audit -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json")
echo "Raw generation response: $GEN_RESP"

echo ""
echo "=== DONE — paste this ENTIRE output back ==="
