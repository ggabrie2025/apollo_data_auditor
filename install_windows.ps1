# =============================================================================
# Apollo Agent V1.7.R - Install Script (Windows)
# =============================================================================
#
# Usage:
#     # Option A — one-liner (PowerShell)
#     Invoke-WebRequest https://aiia-tech.com/download/install_windows.ps1 -OutFile install.ps1
#     .\install.ps1 -ApiKey YOUR_KEY
#
#     # Option B — avec elevation (C:\Program Files\)
#     .\install.ps1 -ApiKey YOUR_KEY -System
#
# Si ExecutionPolicy bloque le script :
#     Set-ExecutionPolicy RemoteSigned -Scope CurrentUser
#
# SmartScreen warning : clic droit sur apollo-agent.exe → Proprietes → Debloquer
# Ou : lancer le .exe → "More info" → "Run anyway"
#
# Binaires officiels distribues exclusivement via aiia-tech.com
#
# Copyright: (c) 2025-2026 Gilles Gabriel <contact@aiia-tech.com>
# =============================================================================

param(
    [string]$ApiKey    = "",
    [string]$HubUrl    = "https://apollo-cloud-api-production.up.railway.app",
    [switch]$System    = $false,   # Installer dans C:\Program Files\ (UAC requis)
    [switch]$NoVerify  = $false
)

$DownloadBase = "https://aiia-tech.com/download"
$BinaryName   = "apollo-agent.exe"

# Installation path
if ($System) {
    $InstallDir = "C:\Program Files\ApolloAgent"
} else {
    $InstallDir = "$env:LOCALAPPDATA\ApolloAgent"
}

$ConfigDir = "$env:APPDATA\Apollo"
$InstallBin = "$InstallDir\apollo-agent.exe"

Write-Host ""
Write-Host "=== Apollo Agent Installer (Windows) ===" -ForegroundColor Cyan
Write-Host ""

# Check OS
if ($env:OS -ne "Windows_NT") {
    Write-Host "Error: This installer supports Windows only." -ForegroundColor Red
    exit 1
}

# Elevation check for --system
if ($System) {
    $currentPrincipal = [Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()
    $isAdmin = $currentPrincipal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
    if (-not $isAdmin) {
        Write-Host "Error: --System requires Administrator privileges." -ForegroundColor Red
        Write-Host "Relancer PowerShell en tant qu'Administrateur, ou utiliser sans -System." -ForegroundColor Yellow
        exit 1
    }
}

$TmpBin  = "$env:TEMP\apollo-agent.exe"
$TmpSums = "$env:TEMP\SHA256SUMS.txt"

# Download binary
Write-Host "Downloading $BinaryName from aiia-tech.com..."
try {
    Invoke-WebRequest "$DownloadBase/$BinaryName" -OutFile $TmpBin -UseBasicParsing
} catch {
    Write-Host "Error: Download failed. Check https://aiia-tech.com/download" -ForegroundColor Red
    exit 1
}

# SHA256 verification
if ($NoVerify) {
    Write-Host "Warning: Integrity check skipped (-NoVerify). NOT recommended." -ForegroundColor Yellow
} else {
    Write-Host ""
    Write-Host "Verifying binary integrity..."
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

    Write-Host "Integrity check passed (SHA256 OK)" -ForegroundColor Green
}

# SmartScreen warning
Write-Host ""
Write-Host "Note SmartScreen:" -ForegroundColor Yellow
Write-Host "  Si Windows bloque l'execution : clic droit sur apollo-agent.exe"
Write-Host "  → Proprietes → Debloquer"
Write-Host "  Ou au premier lancement : 'More info' → 'Run anyway'"
Write-Host ""

# Install
Write-Host "Installing to $InstallDir..."
New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null
Copy-Item $TmpBin $InstallBin -Force

# Unblock downloaded file (removes NTFS Zone.Identifier alternate data stream)
Unblock-File $InstallBin

# Add to PATH (user scope, or system scope if --system)
$PathScope = if ($System) { "Machine" } else { "User" }
$CurrentPath = [Environment]::GetEnvironmentVariable("Path", $PathScope)
if ($CurrentPath -notlike "*ApolloAgent*") {
    [Environment]::SetEnvironmentVariable("Path", "$CurrentPath;$InstallDir", $PathScope)
    Write-Host "PATH mis a jour ($PathScope). Relancer PowerShell pour prendre effet."
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
    Write-Host "Config written to $ConfigDir\config.json"
}

# Cleanup
Remove-Item $TmpBin -ErrorAction SilentlyContinue
Remove-Item $TmpSums -ErrorAction SilentlyContinue

Write-Host ""
Write-Host "=== Installation complete ===" -ForegroundColor Green
Write-Host ""
Write-Host "Apollo Agent installed at $InstallBin"
Write-Host ""
Write-Host "Quick start (apres avoir relance PowerShell) :"
Write-Host "  apollo-agent --version"
Write-Host "  apollo-agent --serve          # UI on http://localhost:8052"
Write-Host "  apollo-agent C:\path\to\scan  # CLI scan"
Write-Host ""
if ($ApiKey -eq "") {
    Write-Host "Note: No API key configured. Edit $ConfigDir\config.json" -ForegroundColor Yellow
    Write-Host ""
}
Write-Host "Documentation: https://aiia-tech.com"
Write-Host "Support: contact@aiia-tech.com"
