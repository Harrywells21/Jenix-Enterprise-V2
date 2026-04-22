# JENIX Enterprise — Windows Universal Installer
# Run in PowerShell as Administrator

$ErrorActionPreference = 'Stop'
$RELEASES = "https://github.com/Harrywells21/Jenix-Enterprise/releases/download/v1.0.0"
$DIR = "$env:LOCALAPPDATA\JenixAgent"

Write-Host ""
Write-Host "╔══════════════════════════════════════════════╗" -f Cyan
Write-Host "║     JENIX Enterprise — Universal Installer   ║" -f Cyan  
Write-Host "╚══════════════════════════════════════════════╝" -f Cyan
Write-Host ""

# Step 1 - Detect Windows
Write-Host "[1/5] Detected OS: Windows $([System.Environment]::OSVersion.Version)" -f Green

# Step 2 - Check Python
Write-Host "[2/5] Checking Python..." -f Yellow
$python = $null
foreach ($p in @("python","python3","py")) {
    try { $v=& $p --version 2>&1; if($v -match "Python 3"){$python=$p;break} } catch {}
}
if (-not $python) {
    Write-Host "      Installing Python 3.11..." -f Yellow
    $tmp="$env:TEMP\py.exe"
    Invoke-WebRequest "https://www.python.org/ftp/python/3.11.0/python-3.11.0-amd64.exe" -OutFile $tmp
    Start-Process $tmp -Args "/quiet InstallAllUsers=1 PrependPath=1 Include_pip=1" -Wait
    $env:PATH=[System.Environment]::GetEnvironmentVariable("PATH","Machine")
    $python="python"
    Write-Host "      Python installed!" -f Green
} else {
    Write-Host "      Found: $( & $python --version 2>&1 )" -f Green
}

# Step 3 - Install dependencies
Write-Host "[3/5] Installing dependencies..." -f Yellow
& $python -m pip install websockets psutil requests --quiet
Write-Host "      Done!" -f Green

# Step 4 - Download agent
Write-Host "[4/5] Downloading JENIX Agent..." -f Yellow
New-Item -ItemType Directory -Force -Path $DIR | Out-Null
try {
    Invoke-WebRequest "$RELEASES/JenixAgent-windows.exe" -OutFile "$DIR\JenixAgent.exe"
} catch {
    # Fallback: download Python script version
    Invoke-WebRequest "$RELEASES/jenix_agent.py" -OutFile "$DIR\jenix_agent.py"
    Write-Host "      Using Python script version" -f Yellow
}
Write-Host "      Downloaded!" -f Green

# Step 5 - Desktop shortcut + auto-start
Write-Host "[5/5] Setting up shortcuts..." -f Yellow

# Desktop shortcut
$WshShell = New-Object -ComObject WScript.Shell
$Shortcut = $WshShell.CreateShortcut("$env:USERPROFILE\Desktop\JENIX Agent.lnk")
if (Test-Path "$DIR\JenixAgent.exe") {
    $Shortcut.TargetPath = "$DIR\JenixAgent.exe"
} else {
    $Shortcut.TargetPath = $python
    $Shortcut.Arguments = "$DIR\jenix_agent.py"
}
$Shortcut.Description = "JENIX Enterprise Agent"
$Shortcut.Save()

# Auto-start on login
$regPath = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run"
if (Test-Path "$DIR\JenixAgent.exe") {
    Set-ItemProperty -Path $regPath -Name "JenixAgent" -Value "$DIR\JenixAgent.exe"
} else {
    Set-ItemProperty -Path $regPath -Name "JenixAgent" -Value "$python `"$DIR\jenix_agent.py`""
}

Write-Host ""
Write-Host "╔══════════════════════════════════════════════╗" -f Green
Write-Host "║   ✅ JENIX Agent Installed!                  ║" -f Green
Write-Host "║                                              ║" -f Green
Write-Host "║   • Desktop shortcut created                 ║" -f Green
Write-Host "║   • Starts automatically on Windows login    ║" -f Green
Write-Host "║   • Double-click 'JENIX Agent' on Desktop    ║" -f Green
Write-Host "╚══════════════════════════════════════════════╝" -f Green
Write-Host ""

# Launch now
$launch = Read-Host "Launch JENIX Agent now? [Y/n]"
if ($launch -ne 'n' -and $launch -ne 'N') {
    if (Test-Path "$DIR\JenixAgent.exe") {
        Start-Process "$DIR\JenixAgent.exe"
    } else {
        Start-Process $python -ArgumentList "$DIR\jenix_agent.py" -WindowStyle Normal
    }
    Write-Host "✓ JENIX Agent launched!" -f Green
}
