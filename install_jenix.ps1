# JENIX Enterprise — Windows Universal Installer
$ErrorActionPreference = 'Stop'

if (-not $env:JENIX_SERVER) {
    Write-Error "JENIX_SERVER is not set. Run as: `$env:JENIX_SERVER='http://YOUR_SERVER:8000'; iwr -useb `$env:JENIX_SERVER/install/windows | iex"
    exit 1
}
$InstallUrl = "$($env:JENIX_SERVER)/install/windows"

$currentPrincipal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $currentPrincipal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Host "Administrator rights required -- requesting elevation..."
    $siteEnv = if ($env:JENIX_SITE_ID) { "`$env:JENIX_SITE_ID='$($env:JENIX_SITE_ID)'; " } else { "" }
    $relaunch = "`$env:JENIX_SERVER='$($env:JENIX_SERVER)'; $siteEnv" + "iwr -useb '$InstallUrl' | iex"
    Start-Process powershell.exe -Verb RunAs -ArgumentList @('-NoProfile','-ExecutionPolicy','Bypass','-Command',$relaunch)
    exit
}

$JenixDir = "$env:ProgramData\JENIX"
$LogsDir  = "$JenixDir\logs"
New-Item -ItemType Directory -Force -Path $JenixDir | Out-Null
New-Item -ItemType Directory -Force -Path $LogsDir  | Out-Null

Write-Host "[1/5] Preparing NSSM (Windows service wrapper)..."
$NssmExe = "$JenixDir\nssm.exe"
if (-not (Test-Path $NssmExe)) {
    try {
        $zipPath = "$env:TEMP\nssm.zip"
        Invoke-WebRequest "https://nssm.cc/release/nssm-2.24.zip" -OutFile $zipPath
        Expand-Archive -Path $zipPath -DestinationPath "$env:TEMP\nssm_extract" -Force
        Copy-Item "$env:TEMP\nssm_extract\nssm-2.24\win64\nssm.exe" -Destination $NssmExe -Force
        Remove-Item $zipPath, "$env:TEMP\nssm_extract" -Recurse -Force
    } catch {
        Write-Error "Failed to download/extract NSSM: $_"
        exit 1
    }
} else {
    Write-Host "      Found existing $NssmExe"
}

Write-Host "[2/5] Downloading JENIX Agent from $($env:JENIX_SERVER)..."
$AgentExe = "$JenixDir\JenixAgent-windows.exe"
try {
    Invoke-WebRequest "$($env:JENIX_SERVER)/agent-binary/windows" -OutFile $AgentExe
} catch {
    Write-Error "Failed to download agent binary from $($env:JENIX_SERVER)/agent-binary/windows: $_"
    exit 1
}

Write-Host "[3/5] Writing server configuration..."
Set-Content -Path "$JenixDir\server_url" -Value $env:JENIX_SERVER -NoNewline
if ($env:JENIX_SITE_ID) {
    Set-Content -Path "$JenixDir\site_id" -Value $env:JENIX_SITE_ID -NoNewline
}

Write-Host "[4/5] Registering Windows Service via NSSM..."
& $NssmExe status JenixAgent 2>$null | Out-Null
if ($LASTEXITCODE -eq 0) {
    Write-Host "      Existing JenixAgent service found -- stopping and removing for a clean reinstall..."
    & $NssmExe stop JenixAgent 2>$null | Out-Null
    & $NssmExe remove JenixAgent confirm 2>$null | Out-Null
}
& $NssmExe install JenixAgent $AgentExe
& $NssmExe set JenixAgent AppDirectory $JenixDir
& $NssmExe set JenixAgent DisplayName "JENIX Agent"
& $NssmExe set JenixAgent ObjectName LocalSystem
& $NssmExe set JenixAgent Start SERVICE_AUTO_START
& $NssmExe set JenixAgent AppExit Default Restart
& $NssmExe set JenixAgent AppEnvironmentExtra "JENIX_SERVER=$($env:JENIX_SERVER)"
& $NssmExe set JenixAgent AppStdout "$LogsDir\agent.log"
& $NssmExe set JenixAgent AppStderr "$LogsDir\agent.log"

Write-Host "[5/5] Starting service..."
& $NssmExe start JenixAgent
Start-Sleep -Seconds 2
$status = & $NssmExe status JenixAgent
Write-Host ""
Write-Host "JENIX Agent installed. Service status: $status"
Write-Host "Config/logs: $JenixDir"
Write-Host "It will register with $($env:JENIX_SERVER) and appear in the dashboard once approved."
