from fastapi import APIRouter, Request
from fastapi.responses import PlainTextResponse, FileResponse
import os

router = APIRouter()
SERVER = "http://192.168.56.102:8000"
AGENT = os.path.normpath(os.path.join(os.path.dirname(__file__), "../../agent/jenix_agent.py"))

@router.get("/api/agent/install/linux", response_class=PlainTextResponse)
async def install_linux():
    return f"""#!/bin/bash
set -e
SERVER="{SERVER}"
DIR="/opt/jenix-agent"
echo ""; echo "╔══════════════════════════════╗"; echo "║  JENIX Enterprise Agent Setup ║"; echo "╚══════════════════════════════╝"; echo ""
if ! command -v python3 &>/dev/null; then
    echo "[1/4] Installing Python3..."
    sudo apt-get update -qq && sudo apt-get install -y python3 python3-pip 2>/dev/null || sudo yum install -y python3 python3-pip 2>/dev/null
else
    echo "[1/4] Python3 found: $(python3 --version)"
fi
echo "[2/4] Installing dependencies..."
pip3 install websockets psutil requests --quiet --break-system-packages 2>/dev/null || pip3 install websockets psutil requests --quiet
echo "[3/4] Downloading agent..."
sudo mkdir -p $DIR
sudo curl -fsSL $SERVER/api/agent/download/agent -o $DIR/jenix_agent.py
echo "[4/4] Setting up auto-start service..."
sudo tee /etc/systemd/system/jenix-agent.service > /dev/null <<SERVICE
[Unit]
Description=JENIX Enterprise Agent
After=network-online.target
[Service]
ExecStart=python3 $DIR/jenix_agent.py --server $SERVER
Restart=always
RestartSec=15
[Install]
WantedBy=multi-user.target
SERVICE
sudo systemctl daemon-reload && sudo systemctl enable jenix-agent --quiet && sudo systemctl restart jenix-agent
echo ""; echo "✅ JENIX Agent installed! Your machine will appear at: $SERVER"; echo ""
"""

@router.get("/api/agent/install/macos", response_class=PlainTextResponse)
async def install_macos():
    return f"""#!/bin/bash
set -e
SERVER="{SERVER}"
DIR="$HOME/.jenix-agent"
PLIST="$HOME/Library/LaunchAgents/com.jenix.agent.plist"
echo ""; echo "╔══════════════════════════════╗"; echo "║  JENIX Enterprise Agent Setup ║"; echo "╚══════════════════════════════╝"; echo ""
command -v python3 &>/dev/null && echo "[1/4] Python3: $(python3 --version)" || (echo "[1/4] Install Python from python.org first" && exit 1)
echo "[2/4] Installing dependencies..."
pip3 install websockets psutil requests --quiet 2>/dev/null || pip install websockets psutil requests --quiet
echo "[3/4] Downloading agent..."
mkdir -p $DIR && curl -fsSL $SERVER/api/agent/download/agent -o $DIR/jenix_agent.py
echo "[4/4] Setting up auto-start..."
mkdir -p "$HOME/Library/LaunchAgents"
cat > $PLIST <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>Label</key><string>com.jenix.agent</string>
<key>ProgramArguments</key><array><string>/usr/bin/python3</string><string>$DIR/jenix_agent.py</string><string>--server</string><string>$SERVER</string></array>
<key>RunAtLoad</key><true/><key>KeepAlive</key><true/>
</dict></plist>
PLIST
launchctl unload $PLIST 2>/dev/null || true
launchctl load $PLIST
python3 $DIR/jenix_agent.py --server $SERVER &
echo ""; echo "✅ JENIX Agent installed! Your machine will appear at: $SERVER"; echo ""
"""

@router.get("/api/agent/install/windows", response_class=PlainTextResponse)
async def install_windows():
    return r"""
$ErrorActionPreference = 'Stop'
$SERVER = "http://192.168.56.102:8000"
$DIR = "$env:ProgramFiles\JenixAgent"
Write-Host ""; Write-Host "╔══════════════════════════════╗" -f Cyan
Write-Host "║  JENIX Enterprise Agent Setup ║" -f Cyan
Write-Host "╚══════════════════════════════╝" -f Cyan; Write-Host ""
Write-Host "[1/4] Checking Python..." -f Yellow
$python = $null
foreach ($p in @("python","python3","py")) { try { $v=& $p --version 2>&1; if($v -match "Python 3"){$python=$p;break} } catch {} }
if (-not $python) {
    Write-Host "      Installing Python 3.11..." -f Yellow
    $tmp="$env:TEMP\py.exe"
    Invoke-WebRequest "https://www.python.org/ftp/python/3.11.0/python-3.11.0-amd64.exe" -OutFile $tmp
    Start-Process $tmp -Args "/quiet InstallAllUsers=1 PrependPath=1 Include_pip=1" -Wait
    $env:PATH=[System.Environment]::GetEnvironmentVariable("PATH","Machine"); $python="python"
}
Write-Host "      OK: $( & $python --version 2>&1 )" -f Green
Write-Host "[2/4] Installing dependencies..." -f Yellow
& $python -m pip install websockets psutil requests wmi --quiet
Write-Host "      Done!" -f Green
Write-Host "[3/4] Downloading agent..." -f Yellow
New-Item -ItemType Directory -Force -Path $DIR | Out-Null
Invoke-WebRequest "$SERVER/api/agent/download/agent" -OutFile "$DIR\jenix_agent.py"
Write-Host "      Downloaded!" -f Green
Write-Host "[4/4] Setting up auto-start..." -f Yellow
$action=New-ScheduledTaskAction -Execute $python -Argument "$DIR\jenix_agent.py --server $SERVER"
$trigger=New-ScheduledTaskTrigger -AtStartup
$settings=New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
$principal=New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest
Register-ScheduledTask -TaskName "JenixAgent" -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Force | Out-Null
Start-Process -FilePath $python -ArgumentList "$DIR\jenix_agent.py --server $SERVER" -WindowStyle Hidden
Write-Host ""; Write-Host "╔══════════════════════════════════╗" -f Green
Write-Host "║  ✅ JENIX Agent Installed!        ║" -f Green
Write-Host "║  Check dashboard in 15 seconds    ║" -f Green
Write-Host "╚══════════════════════════════════╝" -f Green; Write-Host ""
"""

@router.get("/api/agent/download/agent")
@router.get("/api/agent/download/windows")
async def download_agent():
    if os.path.exists(AGENT):
        return FileResponse(AGENT, filename="jenix_agent.py", media_type="text/plain")
    return {"error": "Agent not found", "path": AGENT}

@router.post("/api/upload-static/{filename}")
async def upload_static(filename: str, request: Request):
    allowed = ['react.min.js','react-dom.min.js','prop-types.min.js','recharts.min.js']
    if filename not in allowed:
        return {"error": "Not allowed"}
    data = await request.body()
    path = os.path.join(os.path.dirname(__file__), "../static", filename)
    with open(path, "wb") as f:
        f.write(data)
    return {"ok": True, "file": filename, "size": len(data)}

@router.get("/api/agent/ping")
async def agent_ping():
    return {"status": "ok", "server": SERVER}
@router.get("/api/agent/install", response_class=PlainTextResponse)
@router.get("/install", response_class=PlainTextResponse)  
async def universal_install(request: Request):
    """Smart installer - detects OS from User-Agent and serves correct script"""
    ua = request.headers.get("user-agent", "").lower()
    
    if "powershell" in ua or "windows" in ua:
        # Redirect to Windows installer
        from fastapi.responses import RedirectResponse
        return RedirectResponse("/api/agent/install/windows")
    elif "darwin" in ua or "mac" in ua:
        return RedirectResponse("/api/agent/install/macos")  
    else:
        # Default to Linux
        return RedirectResponse("/api/agent/install/linux")
