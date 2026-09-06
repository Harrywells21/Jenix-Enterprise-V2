#!/bin/bash
set -uo pipefail
cd ~/Desktop/jenix/server || { echo "[ABORT] cannot cd to server dir"; exit 1; }

echo "=== SECTION 1: real Alert model definition in db.py ==="
grep -n "class Alert" db.py
echo "--- full class body (40 lines after match) ---"
grep -n "class Alert" db.py | head -1 | cut -d: -f1 | xargs -I{} sed -n '{},+40p' db.py

echo ""
echo "=== SECTION 2: confirm no existing alert CSV/export route anywhere ==="
grep -rn "alerts/csv\|alert.*csv\|csv.*alert" routes/ 2>/dev/null || echo "no matches"

echo ""
echo "=== SECTION 3: how alerts are queried elsewhere (real column names used in practice) ==="
grep -n "db.query(Alert)" routes/*.py

echo ""
echo "=== SECTION 4: real Alert row sample via sqlite3, to see actual populated columns/values ==="
python3 -c "
import sqlite3
conn = sqlite3.connect('/home/aadi/Desktop/jenix/server/jenix.db')
cur = conn.cursor()
cur.execute('PRAGMA table_info(alerts)')
print('Columns:', cur.fetchall())
cur.execute('SELECT * FROM alerts ORDER BY id DESC LIMIT 3')
for row in cur.fetchall():
    print(row)
conn.close()
"

echo ""
echo "=== DONE — paste this ENTIRE output back ==="
