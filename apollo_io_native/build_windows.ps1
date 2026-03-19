# =============================================================================
# Apollo IO Native - Windows Build Script
# Run as Administrator in PowerShell
# =============================================================================

Write-Host "=== Apollo IO Native - Windows Build ===" -ForegroundColor Cyan

# 1. Check/Install Chocolatey
if (!(Get-Command choco -ErrorAction SilentlyContinue)) {
    Write-Host "Installing Chocolatey..." -ForegroundColor Yellow
    Set-ExecutionPolicy Bypass -Scope Process -Force
    [System.Net.ServicePointManager]::SecurityProtocol = [System.Net.ServicePointManager]::SecurityProtocol -bor 3072
    iex ((New-Object System.Net.WebClient).DownloadString('https://community.chocolatey.org/install.ps1'))
}

# 2. Install Python 3.12
Write-Host "Installing Python 3.12..." -ForegroundColor Yellow
choco install python312 -y
refreshenv

# 3. Install Rust
Write-Host "Installing Rust..." -ForegroundColor Yellow
choco install rustup.install -y
refreshenv
rustup default stable

# 4. Install maturin
Write-Host "Installing maturin..." -ForegroundColor Yellow
pip install maturin

# 5. Build
Write-Host "Building apollo_io_native..." -ForegroundColor Yellow
cd $PSScriptRoot
maturin build --release

# 6. Install wheel
Write-Host "Installing wheel..." -ForegroundColor Yellow
$wheel = Get-ChildItem -Path "target\wheels\*.whl" | Select-Object -First 1
pip install $wheel.FullName --force-reinstall

# 7. Test
Write-Host "Testing..." -ForegroundColor Yellow
python -c @"
import apollo_io_native as aio
print(f'raw_metadata_size: {aio.raw_metadata_size()}')
assert aio.raw_metadata_size() == 156, 'FAILED: size != 156'
print('OK - 156 bytes')

# Test collect
raw = aio.collect_raw_metadata('C:\\Windows\\System32\\drivers\\etc\\hosts')
meta = aio.parse_raw_metadata(raw)
print(f'hosts file: size={meta[\"size\"]}, entropy={meta[\"entropy\"]:.2f}')
print('OK - collect works')

# Test owner_domain
print(f'owner_domain: {meta[\"owner_domain\"]}')
print('BUILD SUCCESS')
"@

Write-Host "=== Build Complete ===" -ForegroundColor Green
Write-Host "Wheel location: target\wheels\" -ForegroundColor Cyan
