#!/bin/bash
set -e
cd ~/Desktop/jenix/agent
source ~/Desktop/jenix/server_venv/bin/activate

echo "=== STEP 1: Build with PyInstaller (per E1: real invocation not recovered, using plain form) ==="
pyinstaller JenixAgentCLI.spec

echo ""
echo "=== STEP 2: Hash new build vs known stale hashes ==="
NEW_HASH=$(sha256sum dist/JenixAgent | awk '{print $1}')
echo "New build hash:      $NEW_HASH"
echo "Running binary hash: c0e239ee145f1b668b1fe07fceb78ec3e8254fd8b24272f2d613618ab553ec58 (stale, currently deployed)"
echo "Last dist hash:      c9c1f25657d336c2b361a94d5fb4917b82638c8f10eb60c539f9d6b787f0cb1b (stale, Sep 2 build, never deployed)"
if [ "$NEW_HASH" == "c0e239ee145f1b668b1fe07fceb78ec3e8254fd8b24272f2d613618ab553ec58" ] || [ "$NEW_HASH" == "c9c1f25657d336c2b361a94d5fb4917b82638c8f10eb60c539f9d6b787f0cb1b" ]; then
  echo "!!! WARNING: new build hash matches a STALE hash — this would be a no-op rebuild. STOPPING before deploy."
  exit 1
fi
echo "Confirmed: new build is a genuinely new artifact — proceeding to deploy."

echo ""
echo "=== STEP 3: Backup currently running binary before replacing (Text file busy otherwise) ==="
TS=$(date +%Y%m%d_%H%M%S)
cp ~/.jenix/JenixAgent ~/.jenix/JenixAgent.bak_predeploy_$TS
ls -la ~/.jenix/JenixAgent.bak_predeploy_$TS

echo ""
echo "=== STEP 4: Stop jenix-agent.service (must stop before replacing running binary) ==="
sudo systemctl stop jenix-agent.service
sleep 1
sudo systemctl is-active jenix-agent.service || echo "confirmed stopped"

echo ""
echo "=== STEP 5: Replace deployed binary with new build ==="
cp ~/Desktop/jenix/agent/dist/JenixAgent ~/.jenix/JenixAgent
chmod +x ~/.jenix/JenixAgent
sha256sum ~/.jenix/JenixAgent

echo ""
echo "=== STEP 6: Restart jenix-agent.service ==="
sudo systemctl start jenix-agent.service
sleep 3
sudo systemctl status jenix-agent.service --no-pager

echo ""
echo "=== STEP 7: Real journalctl output post-restart (full, not tail) ==="
sudo journalctl -u jenix-agent.service -n 200 --no-pager

echo ""
echo "=== STEP 8: Confirm machine id=1 DB row transitions to online with fresh last_seen ==="
sqlite3 /home/aadi/Desktop/jenix/server/jenix.db "SELECT id, hostname, status, last_seen FROM machines WHERE id=1;"

echo ""
echo "=== DEPLOY SCRIPT DONE ==="
