# JENIX Enterprise Agent Installer — Windows
# Run as Administrator in PowerShell:
# Set-ExecutionPolicy Bypass -Scope Process -Force
# .\install_windows.ps1

param(
    [string]$JenixServer  = "http://YOUR_SERVER_IP:8000",
    [string]$JenixApiKey  = "your_api_key_here",
    [string]$NodeName     = $env:COMPUTERNAME
)

$ErrorActionPreference = "Stop"
$InstallDir  = "C:\Program Files\JENIX\Agent"
$ConfigDir   = "C:\ProgramData\JENIX"
$ServiceName = "JENIXAgent"

Write-Host "=== JENIX Enterprise Agent Installer (Windows) ===" -ForegroundColor Cyan
Write-Host "Server: $JenixServer"
Write-Host "Node:   $NodeName"

# Check admin
if (-NOT ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole] "Administrator")) {
    Write-Error "Run this script as Administrator."
    exit 1
}

# Check/Install Python
$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) {
    Write-Host "Installing Python 3.11 via winget..." -ForegroundColor Yellow
    winget install Python.Python.3.11 --silent --accept-package-agreements
    $env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine")
}

# Install pip dependencies
Write-Host "Installing Python dependencies..."
python -m pip install --quiet psutil websockets requests pywin32

# Create directories
New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null
New-Item -ItemType Directory -Force -Path $ConfigDir  | Out-Null

# Download agent
Write-Host "Downloading agent..."
$headers = @{ "X-API-Key" = $JenixApiKey }
try {
    Invoke-WebRequest -Uri "$JenixServer/agent/jenix_agent.py" `
        -Headers $headers `
        -OutFile "$InstallDir\jenix_agent.py"
} catch {
    Write-Error "Failed to download agent. Ensure JENIX server is reachable: $_"
}

# Write config
$NodeId = [System.Guid]::NewGuid().ToString()
$wsServer = $JenixServer -replace "^http://", "ws://" -replace "^https://", "wss://"
$config = @{
    server_url = $wsServer
    node_id    = $NodeId
    node_name  = $NodeName
    api_key    = $JenixApiKey
} | ConvertTo-Json
$config | Set-Content "$ConfigDir\agent.conf" -Encoding UTF8

# Create wrapper bat
@"
@echo off
python "$InstallDir\jenix_agent.py"
"@ | Set-Content "$InstallDir\start_agent.bat" -Encoding ASCII

# Remove old service if exists
$existing = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
if ($existing) {
    Stop-Service -Name $ServiceName -Force -ErrorAction SilentlyContinue
    sc.exe delete $ServiceName | Out-Null
    Start-Sleep -Seconds 2
}

# Install as Windows Service using sc.exe
$pythonPath = (Get-Command python).Source
sc.exe create $ServiceName `
    binPath= "`"$pythonPath`" `"$InstallDir\jenix_agent.py`"" `
    start= auto `
    obj= LocalSystem `
    DisplayName= "JENIX Enterprise Agent" | Out-Null

sc.exe description $ServiceName "JENIX Enterprise infrastructure monitoring agent" | Out-Null
sc.exe failure $ServiceName reset= 60 actions= restart/5000/restart/10000/restart/30000 | Out-Null

Start-Service -Name $ServiceName

Write-Host ""
Write-Host "=== JENIX Agent installed successfully! ===" -ForegroundColor Green
Write-Host "Service status: $((Get-Service $ServiceName).Status)"
Write-Host "Logs: Event Viewer > Windows Logs > Application > Source: JENIXAgent"
Write-Host "Stop: Stop-Service JENIXAgent"
