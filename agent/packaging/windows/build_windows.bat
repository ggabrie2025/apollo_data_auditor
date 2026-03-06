@echo off
REM =============================================================================
REM Apollo Agent V1.7.R - Windows Build Script (PyInstaller)
REM =============================================================================
REM
REM Prerequisites:
REM     pip install pyinstaller
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
set ROOT_DIR=%AGENT_DIR%\..

echo === Apollo Agent Build Script (PyInstaller - Windows) ===
echo Agent directory: %AGENT_DIR%

REM Check PyInstaller
python -m PyInstaller --version >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo ERROR: PyInstaller not found. Install with: pip install pyinstaller
    exit /b 1
)

REM Clean previous builds
echo.
echo Cleaning previous builds...
if exist "%SCRIPT_DIR%dist" rmdir /S /Q "%SCRIPT_DIR%dist"
if exist "%SCRIPT_DIR%build" rmdir /S /Q "%SCRIPT_DIR%build"

REM Build with PyInstaller
echo.
echo Building with PyInstaller...
cd "%ROOT_DIR%"
python -m PyInstaller --onefile ^
    --name apollo-agent.exe ^
    --distpath "%SCRIPT_DIR%dist" ^
    --workpath "%SCRIPT_DIR%build" ^
    --add-data "agent\ui\static;agent\ui\static" ^
    --add-data "agent\config;agent\config" ^
    --hidden-import asyncpg ^
    --hidden-import aiomysql ^
    --hidden-import motor ^
    --hidden-import aioodbc ^
    --hidden-import msal ^
    --hidden-import aiohttp ^
    --hidden-import pybloom_live ^
    --hidden-import openpyxl ^
    --hidden-import uvicorn ^
    --hidden-import fastapi ^
    --hidden-import httpx ^
    --hidden-import pydantic ^
    --hidden-import yaml ^
    --hidden-import apollo_io_native ^
    agent\main.py

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
    echo   dist\apollo-agent.exe --serve
    echo   dist\apollo-agent.exe C:\path\to\scan --preview
) else (
    echo.
    echo === BUILD FAILED - No output file ===
    exit /b 1
)
