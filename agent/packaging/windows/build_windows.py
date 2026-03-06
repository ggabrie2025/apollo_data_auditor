#!/usr/bin/env python3
"""
Apollo Agent V1.7.R - Windows Build Script (PyInstaller - Programmatic)

Alternative to build_windows.bat for CI/CD or cross-platform invocation.

Usage:
    python build_windows.py [--test]

Copyright: (c) 2025-2026 Gilles Gabriel <gilles.gabriel@noos.fr>
"""
import subprocess
import sys
import os
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
AGENT_DIR = SCRIPT_DIR.parent.parent  # agent/packaging/windows -> agent/
ROOT_DIR = AGENT_DIR.parent           # agent/ -> repo root
DIST_DIR = SCRIPT_DIR / "dist"


def build(test_mode: bool = False):
    """Build Apollo Agent with PyInstaller."""
    os.environ["PYTHONUTF8"] = "1"

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onefile",
        "--name", "apollo-agent.exe",
        f"--distpath={DIST_DIR}",
        f"--workpath={SCRIPT_DIR / 'build'}",
        # Data files
        f"--add-data={AGENT_DIR / 'ui' / 'static'};agent/ui/static",
        f"--add-data={AGENT_DIR / 'config'};agent/config",
        # Hidden imports
        "--hidden-import=asyncpg",
        "--hidden-import=aiomysql",
        "--hidden-import=motor",
        "--hidden-import=aioodbc",
        "--hidden-import=msal",
        "--hidden-import=aiohttp",
        "--hidden-import=pybloom_live",
        "--hidden-import=openpyxl",
        "--hidden-import=uvicorn",
        "--hidden-import=fastapi",
        "--hidden-import=httpx",
        "--hidden-import=pydantic",
        "--hidden-import=yaml",
        "--hidden-import=apollo_io_native",
        # Entry point
        str(AGENT_DIR / "main.py"),
    ]

    print("Building Apollo Agent with PyInstaller...")
    print(f"Agent dir: {AGENT_DIR}")
    print(f"Output: {DIST_DIR / 'apollo-agent.exe'}")
    print()

    result = subprocess.run(cmd, cwd=str(ROOT_DIR))

    if result.returncode != 0:
        print("\n=== BUILD FAILED ===")
        sys.exit(1)

    exe = DIST_DIR / "apollo-agent.exe"
    if exe.exists():
        size_mb = exe.stat().st_size / (1024 * 1024)
        print(f"\n=== BUILD SUCCESS ===")
        print(f"Binary: {exe}")
        print(f"Size: {size_mb:.1f} MB")

        if test_mode:
            print("\nRunning quick test...")
            test = subprocess.run([str(exe), "--version"], capture_output=True, text=True)
            print(f"Exit code: {test.returncode}")
            print(f"Output: {test.stdout}")
    else:
        print("\n=== BUILD FAILED - No output file ===")
        sys.exit(1)


if __name__ == "__main__":
    test = "--test" in sys.argv
    build(test_mode=test)
