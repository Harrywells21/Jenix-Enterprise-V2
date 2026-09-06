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
