#!/usr/bin/env python3
"""
Apollo Agent V1.7.R - Windows Build Script (Nuitka - Programmatic)

Alternative to build_windows.bat for CI/CD or cross-platform invocation.
Uses Nuitka's Python API for more control over the build process.

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
DIST_DIR = SCRIPT_DIR / "dist"


def build(test_mode: bool = False):
    """Build Apollo Agent with Nuitka."""
    os.environ["PYTHONUTF8"] = "1"

    cmd = [
        sys.executable, "-m", "nuitka",
        "--standalone",
        "--onefile",
        f"--output-dir={DIST_DIR}",
        "--output-filename=apollo-agent.exe",
        # Data files
        f"--include-data-files={AGENT_DIR / 'config' / 'exclusions.yaml'}=config/exclusions.yaml",
        f"--include-data-files={AGENT_DIR / 'VERSION'}=VERSION",
        # UI static files (HTML, JS, CSS, assets) — required for --serve mode
        f"--include-data-dir={AGENT_DIR / 'ui' / 'static'}=agent/ui/static",
        # Modules to include
        "--include-module=yaml",
        "--include-module=ldap3",
        "--include-module=requests",
        "--include-module=asyncpg",
        "--include-module=aiomysql",
        "--include-module=pymongo",
        "--include-module=motor",
        "--include-module=pyodbc",
        "--include-module=certifi",
        "--include-module=apollo_io_native",
        # UI server dependencies (--serve mode)
        "--include-module=uvicorn",
        "--include-module=fastapi",
        "--include-module=pydantic",
        "--include-module=dotenv",
        "--include-module=starlette",
        # Packages
        "--include-package=agent.core",
        "--include-package=agent.models",
        "--include-package=agent.observability",
        "--include-package=agent.ui",
        # Excludes
        "--nofollow-import-to=tkinter",
        "--nofollow-import-to=unittest",
        "--nofollow-import-to=pydoc",
        # Windows metadata
        "--windows-console-mode=force",
        "--company-name=Apollo Data Auditor",
        "--product-name=Apollo Agent",
        "--file-version=1.7.0.0",
        "--product-version=1.7.0.0",
        "--file-description=Apollo Data Auditor Agent",
        "--copyright=(c) 2025-2026 Gilles Gabriel",
        # Entry point
        str(AGENT_DIR / "main.py"),
    ]

    icon = SCRIPT_DIR / "apollo_icon.ico"
    if icon.exists():
        cmd.insert(-1, f"--windows-icon-from-ico={icon}")

    print(f"Building Apollo Agent with Nuitka...")
    print(f"Agent dir: {AGENT_DIR}")
    print(f"Output: {DIST_DIR / 'apollo-agent.exe'}")
    print()

    result = subprocess.run(cmd, cwd=str(AGENT_DIR.parent))

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
