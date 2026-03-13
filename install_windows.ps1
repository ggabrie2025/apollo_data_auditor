# =============================================================================
# Apollo Agent V1.7.R - Install Script (Windows) — UI-Friendly
# =============================================================================
#
# Usage:
#     # Option A — one-liner (PowerShell)
#     Invoke-WebRequest https://aiia-tech.com/download/install_windows.ps1 -OutFile install.ps1
#     .\install.ps1
#
#     # Option B — with API key
#     .\install.ps1 -ApiKey YOUR_KEY
#
# Si ExecutionPolicy bloque le script :
#     Set-ExecutionPolicy RemoteSigned -Scope CurrentUser
#
# NO admin rights required — installs to %LOCALAPPDATA%\ApolloAgent\
# After install, auto-launches the UI agent and opens browser.
#
# Binaires officiels distribues exclusivement via aiia-tech.com
#
# Copyright: (c) 2025-2026 Gilles Gabriel <contact@aiia-tech.com>
# =============================================================================

param(
    [string]$ApiKey    = "",
    [string]$HubUrl    = "https://apollo-cloud-api-production.up.railway.app",
    [switch]$NoVerify  = $false,
    [switch]$NoLaunch  = $false
)

$DownloadBase = "https://aiia-tech.com/download"
$BinaryName   = "apollo-agent.exe"

# Install to user directory (NO admin required)
$InstallDir = "$env:LOCALAPPDATA\ApolloAgent"
$ConfigDir  = "$env:APPDATA\Apollo"
$InstallBin = "$InstallDir\apollo-agent.exe"

Write-Host ""
Write-Host "=== Apollo Agent Installer (Windows) ===" -ForegroundColor Cyan
Write-Host ""

# Check OS
if ($env:OS -ne "Windows_NT") {
    Write-Host "Error: This installer supports Windows only." -ForegroundColor Red
    exit 1
}

$TmpBin  = "$env:TEMP\apollo-agent.exe"
$TmpSums = "$env:TEMP\SHA256SUMS.txt"

# Download binary
Write-Host "  Downloading $BinaryName from aiia-tech.com..."
try {
    Invoke-WebRequest "$DownloadBase/$BinaryName" -OutFile $TmpBin -UseBasicParsing
} catch {
    Write-Host "Error: Download failed. Check https://aiia-tech.com/download" -ForegroundColor Red
    exit 1
}

# SHA256 verification
if ($NoVerify) {
    Write-Host "  Warning: Integrity check skipped (-NoVerify). NOT recommended." -ForegroundColor Yellow
} else {
    Write-Host ""
    Write-Host "  Verifying binary integrity..."
    try {
        Invoke-WebRequest "$DownloadBase/SHA256SUMS.txt" -OutFile $TmpSums -UseBasicParsing
    } catch {
        Write-Host "Error: Could not download SHA256SUMS.txt" -ForegroundColor Red
        Write-Host "Binary integrity cannot be verified. Aborting."
        Write-Host "Contact: contact@aiia-tech.com"
        exit 1
    }

    $SumsContent = Get-Content $TmpSums
    $ExpectedLine = $SumsContent | Where-Object { $_ -match "apollo-agent\.exe" }
    if (-not $ExpectedLine) {
        Write-Host "Error: apollo-agent.exe not found in SHA256SUMS.txt" -ForegroundColor Red
        Write-Host "Contact: contact@aiia-tech.com"
        exit 1
    }
    $Expected = ($ExpectedLine -split "\s+")[0].ToLower()
    $Actual   = (Get-FileHash $TmpBin -Algorithm SHA256).Hash.ToLower()

    if ($Expected -ne $Actual) {
        Write-Host ""
        Write-Host "======================================================" -ForegroundColor Red
        Write-Host "  BINARY INTEGRITY CHECK FAILED                      " -ForegroundColor Red
        Write-Host "  Do not execute this binary.                         " -ForegroundColor Red
        Write-Host "  Contact: contact@aiia-tech.com                      " -ForegroundColor Red
        Write-Host "======================================================" -ForegroundColor Red
        Write-Host ""
        Write-Host "  Expected: $Expected"
        Write-Host "  Actual:   $Actual"
        Write-Host ""
        exit 1
    }

    Write-Host "  Integrity check passed (SHA256 OK)" -ForegroundColor Green
}

# Install to user directory
Write-Host ""
Write-Host "  Installing to $InstallDir..."
New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null
Copy-Item $TmpBin $InstallBin -Force

# Unblock downloaded file (removes NTFS Zone.Identifier alternate data stream)
Unblock-File $InstallBin

# Add to PATH (user scope only, no admin needed)
$CurrentPath = [Environment]::GetEnvironmentVariable("Path", "User")
if ($CurrentPath -notlike "*ApolloAgent*") {
    [Environment]::SetEnvironmentVariable("Path", "$CurrentPath;$InstallDir", "User")
    # Also update current session
    $env:Path = "$env:Path;$InstallDir"
    Write-Host "  PATH updated (User scope)" -ForegroundColor Green
}

# Write config
if ($ApiKey -ne "") {
    New-Item -ItemType Directory -Force -Path $ConfigDir | Out-Null
    $Config = @{
        api_key = $ApiKey
        hub_url = $HubUrl
    } | ConvertTo-Json
    Set-Content "$ConfigDir\config.json" $Config
    # Restrict permissions (owner only)
    $Acl = Get-Acl "$ConfigDir\config.json"
    $Acl.SetAccessRuleProtection($true, $false)
    $Rule = New-Object System.Security.AccessControl.FileSystemAccessRule(
        $env:USERNAME, "FullControl", "Allow"
    )
    $Acl.SetAccessRule($Rule)
    Set-Acl "$ConfigDir\config.json" $Acl
    Write-Host "  Config written to $ConfigDir\config.json"
}

# Cleanup temp files
Remove-Item $TmpBin -ErrorAction SilentlyContinue
Remove-Item $TmpSums -ErrorAction SilentlyContinue

Write-Host ""
Write-Host "=== Installation complete ===" -ForegroundColor Green
Write-Host ""
Write-Host "  Apollo Agent installed at $InstallBin"
Write-Host ""

# Auto-launch UI agent + open browser (unless -NoLaunch)
if (-not $NoLaunch) {
    Write-Host "  Launching Apollo Agent UI..." -ForegroundColor Cyan
    Write-Host ""

    # Launch the agent in serve mode (it auto-opens browser to login.html)
    # The agent finds a free port (8052-8099) and opens the browser automatically
    Start-Process -FilePath $InstallBin -ArgumentList "--serve" -WindowStyle Hidden

    Write-Host "  Agent launched in background."
    Write-Host ""
    Write-Host "  Your browser should open automatically."
    Write-Host "  If not, open: http://localhost:8052"
    Write-Host ""
    if ($ApiKey -eq "") {
        Write-Host "  Enter your API key in the login page to start scanning." -ForegroundColor Yellow
        Write-Host "  No key yet? Request beta access at https://aiia-tech.com"
    }
    Write-Host ""
    Write-Host "  To relaunch later: apollo-agent --serve"
} else {
    Write-Host "  To launch the UI: apollo-agent --serve"
    Write-Host "  (opens browser automatically)"
}

Write-Host ""
Write-Host "  Documentation: https://aiia-tech.com"
Write-Host "  Support: contact@aiia-tech.com"
Write-Host ""
