# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec file for Apollo Agent V1.7.R

Usage:
    cd agent/packaging/macos
    pyinstaller apollo_agent.spec --clean --noconfirm

Output:
    dist/apollo-agent (macOS/Linux)
"""

import sys
import os
from pathlib import Path

# Get agent root directory (SPECPATH is provided by PyInstaller)
SPEC_DIR = Path(SPECPATH) if 'SPECPATH' in dir() else Path(os.getcwd())
AGENT_ROOT = SPEC_DIR.parent.parent.resolve()  # macos/ → packaging/ → agent/
REPO_ROOT = AGENT_ROOT.parent.resolve()  # agent/ → repo root

block_cipher = None

a = Analysis(
    [str(AGENT_ROOT / 'main.py')],
    pathex=[str(REPO_ROOT)],  # repo root so 'from agent.xxx' works
    binaries=[],
    datas=[
        # Include config files
        (str(AGENT_ROOT / 'config' / 'exclusions.yaml'), 'config'),
        # Include Python source modules as agent package
        (str(AGENT_ROOT / 'core'), 'agent/core'),
        (str(AGENT_ROOT / 'models'), 'agent/models'),
        (str(AGENT_ROOT / 'observability'), 'agent/observability'),
        (str(AGENT_ROOT / 'ui'), 'agent/ui'),
        (str(AGENT_ROOT / 'version.py'), 'agent'),
    ],
    hiddenimports=[
        'yaml',
        'concurrent.futures',
        'shutil',
        'platform',
        # Agent package imports (from agent.xxx)
        'agent.version',
        'agent.core.collector',
        'agent.core.exclusions',
        'agent.core.pii_scanner',
        'agent.core.exporter',
        'agent.core.fingerprint',
        'agent.core.fingerprint_backend',
        'agent.core.io_backend',
        'agent.core.differential',
        'agent.core.snapshot',
        'agent.core.optimized_scanner',
        'agent.core.network_mount',
        'agent.models.contracts',
        'agent.observability.health',
        'agent.observability.config',
        'agent.ui.server',
        'uvicorn',
        'fastapi',
        'starlette',
        'pydantic',
        'dotenv',
        'asyncpg.pgproto.pgproto',
        'asyncpg.protocol.protocol',
        # Fallback imports (from core.xxx / models.xxx)
        'core.collector',
        'core.exclusions',
        'core.pii_scanner',
        'core.exporter',
        'models.contracts',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Exclude unnecessary stdlib modules for smaller binary
        'tkinter',
        'unittest',
        'pydoc',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='apollo-agent',
    debug=False,
    bootloader_ignore_signals=False,
    strip=True,  # Strip debug symbols
    upx=True,    # Compress with UPX if available
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

# macOS .app bundle (optional)
if sys.platform == 'darwin':
    app = BUNDLE(
        exe,
        name='Apollo Agent.app',
        icon=None,  # Add icon path here if available
        bundle_identifier='com.apollo.agent',
        info_plist={
            'CFBundleShortVersionString': '1.7.0',
            'CFBundleVersion': '1.7.0',
            'NSHighResolutionCapable': True,
        },
    )
