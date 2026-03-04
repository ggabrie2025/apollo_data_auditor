# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec file for Apollo Agent V1.7.R — Windows

Usage:
    cd agent/packaging/windows
    pyinstaller apollo_agent_win.spec --clean --noconfirm

Output:
    dist/apollo-agent.exe

Copyright: (c) 2025-2026 aiia-tech.com
"""

import sys
import os
from pathlib import Path

SPEC_DIR = Path(SPECPATH) if 'SPECPATH' in dir() else Path(os.getcwd())
AGENT_ROOT = SPEC_DIR.parent.parent.resolve()  # windows/ -> packaging/ -> agent/
REPO_ROOT = AGENT_ROOT.parent.resolve()  # agent/ -> repo root

block_cipher = None

a = Analysis(
    [str(AGENT_ROOT / 'main.py')],
    pathex=[str(REPO_ROOT)],
    # OBLIGATOIRE: module Rust natif — INTERDIT de livrer sans Rust
    # Compile par maturin: cd apollo_io_native && maturin build --release
    # Output: apollo_io_native.pyd dans site-packages ou target/
    binaries=[(str(REPO_ROOT / 'apollo_io_native.pyd'), '.')],
    datas=[
        (str(AGENT_ROOT / 'config' / 'exclusions.yaml'), 'config'),
        (str(AGENT_ROOT / 'core'), 'agent/core'),
        (str(AGENT_ROOT / 'models'), 'agent/models'),
        (str(AGENT_ROOT / 'observability'), 'agent/observability'),
        (str(AGENT_ROOT / 'ui'), 'agent/ui'),
        (str(AGENT_ROOT / 'main_app.py'), 'agent'),
        (str(AGENT_ROOT / 'main_directory.py'), 'agent'),
        (str(AGENT_ROOT / 'main_infra.py'), 'agent'),
        (str(AGENT_ROOT / 'version.py'), 'agent'),
    ],
    hiddenimports=[
        'yaml',
        'concurrent.futures',
        'shutil',
        'platform',
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
        'agent.core.onedrive_collector',
        'agent.core.dependency_checker',
        'agent.core.db_scanner',
        'agent.core.db_sampler',
        'agent.core.db_differential',
        'agent.core.db_snapshot',
        'agent.core.db_connectors',
        'agent.core.db_connectors.postgresql',
        'agent.core.db_connectors.mysql',
        'agent.core.db_connectors.mongodb',
        'agent.core.db_connectors.sqlserver',
        'agent.core.db_connectors.registry',
        'agent.core.directory_connectors',
        'agent.core.directory_connectors.ldap_connector',
        'agent.core.directory_connectors.registry',
        'agent.core.infra_scanner',
        'agent.core.app_connectors',
        'agent.core.app_connectors.base',
        'agent.core.app_connectors.pennylane_connector',
        'agent.core.app_connectors.registry',
        'agent.main_app',
        'agent.main_directory',
        'agent.main_infra',
        'agent.models.contracts',
        'agent.observability.health',
        'agent.observability.config',
        'agent.ui.server',
        'uvicorn',
        'fastapi',
        'starlette',
        'pydantic',
        'dotenv',
        'asyncpg',
        'aiomysql',
        'pymongo',
        'motor',
        'ldap3',
        'requests',
        'certifi',
        'apollo_io_native',
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
    strip=False,  # Windows does not support strip
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    version_info=None,
)
