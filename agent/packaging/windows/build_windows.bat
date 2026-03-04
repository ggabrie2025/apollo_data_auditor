@echo off
REM =============================================================================
REM Apollo Agent V1.7.R - Windows Build Script (Nuitka)
REM =============================================================================
REM
REM Prerequisites:
REM     pip install nuitka ordered-set zstandard
REM     Visual C++ Build Tools (or Visual Studio)
REM
REM Usage:
REM     cd agent\packaging\windows
REM     build_windows.bat
REM
REM Output:
REM     dist\apollo-agent.exe
REM
REM Copyright: (c) 2025-2026 Gilles Gabriel <gilles.gabriel@noos.fr>
REM =============================================================================

set PYTHONUTF8=1

REM Resolve paths
set SCRIPT_DIR=%~dp0
set PACKAGING_DIR=%SCRIPT_DIR%..
set AGENT_DIR=%PACKAGING_DIR%\..

echo === Apollo Agent Build Script (Nuitka - Windows) ===
echo Agent directory: %AGENT_DIR%

REM Check Nuitka
python -m nuitka --version >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo ERROR: Nuitka not found. Install with: pip install nuitka ordered-set zstandard
    exit /b 1
)

REM Clean previous builds
echo.
echo Cleaning previous builds...
if exist "%SCRIPT_DIR%dist" rmdir /S /Q "%SCRIPT_DIR%dist"
if exist "%SCRIPT_DIR%build" rmdir /S /Q "%SCRIPT_DIR%build"

REM Build with Nuitka
echo.
echo Building with Nuitka (this may take 5-15 minutes on first build)...
python -m nuitka ^
    --standalone ^
    --onefile ^
    --output-dir="%SCRIPT_DIR%dist" ^
    --output-filename=apollo-agent.exe ^
    --include-data-files="%AGENT_DIR%\config\exclusions.yaml=config/exclusions.yaml" ^
    --include-data-files="%AGENT_DIR%\VERSION=VERSION" ^
    --include-module=yaml ^
    --include-module=ldap3 ^
    --include-module=requests ^
    --include-module=pymongo ^
    --include-module=psycopg2 ^
    --include-module=mysql.connector ^
    --include-module=pyodbc ^
    --include-module=certifi ^
    --include-module=apollo_io_native ^
    --include-package=agent.core ^
    --include-package=agent.models ^
    --include-package=agent.observability ^
    --include-package=agent.ui ^
    --nofollow-import-to=tkinter ^
    --nofollow-import-to=unittest ^
    --nofollow-import-to=pydoc ^
    --enable-console ^
    --company-name="Apollo Data Auditor" ^
    --product-name="Apollo Agent" ^
    --file-version=1.7.0.0 ^
    --product-version=1.7.0.0 ^
    --file-description="Apollo Data Auditor Agent" ^
    --copyright="(c) 2025-2026 Gilles Gabriel" ^
    --windows-icon-from-ico="%SCRIPT_DIR%apollo_icon.ico" ^
    "%AGENT_DIR%\main.py"

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo === BUILD FAILED ===
    exit /b 1
)

REM Check output
if exist "%SCRIPT_DIR%dist\apollo-agent.exe" (
    echo.
    echo === BUILD SUCCESS ===
    for %%A in ("%SCRIPT_DIR%dist\apollo-agent.exe") do echo Size: %%~zA bytes
    echo.
    echo Test with:
    echo   dist\apollo-agent.exe --version
    echo   dist\apollo-agent.exe C:\path\to\scan --preview
) else (
    echo.
    echo === BUILD FAILED - No output file ===
    exit /b 1
)
