#!/usr/bin/env python3
"""
Apollo Agent V1.7.R - UI Server (Rust Hybrid)
==============================================

FastAPI server for Agent Cloud UI with subprocess-based scanning.

Architecture:
- Subprocess pattern: CLI calls via python3 -m agent.main / agent.main_db
- Triple validation: returncode + file exists + status check
- SSE progress streaming
- Hub integration (mode cloud)

Port: 8052 (Agent Cloud UI)

Usage:
    python3 -m agent.ui.server
    uvicorn agent.ui.server:app --port 8052

Version: 1.7.R (Rust Hybrid Module)
Date: 2026-01-07
"""

import asyncio
import json
import logging
import logging.handlers
import os
import re
import socket
import subprocess
import sys
import tempfile
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any, Literal

import requests
from dotenv import load_dotenv
from fastapi import FastAPI, BackgroundTasks, HTTPException, Request
from fastapi.responses import StreamingResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

def _write_secure_temp(filepath: str, content: str) -> None:
    """Write file with restricted permissions (0o600 Unix, ACL-restricted Windows)."""
    fd = os.open(filepath, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w', encoding='utf-8') as f:
        f.write(content)
    if sys.platform == 'win32':
        try:
            username = os.environ.get('USERNAME', '')
            if username:
                subprocess.run(['icacls', filepath, '/inheritance:r',
                                '/grant:r', f'{username}:(R,W)'],
                               capture_output=True, timeout=5)
        except Exception:
            pass  # Best effort on Windows


# Dynamic connector registry (autodiscovery)
from agent.core.db_connectors import get_ports_to_scan, get_all_connectors_metadata

# Observability module (Sprint 38)
from agent.observability import get_health_status

# Load .env from backend/ (Sprint 20: HUB_API_KEY for multi-tenant)
_env_path = Path(__file__).parent.parent.parent / "backend" / ".env"
if _env_path.exists():
    load_dotenv(_env_path)

LOG_DIR = os.path.expanduser("~/apollo-agent-logs")
os.makedirs(LOG_DIR, exist_ok=True)
LOG_FILE = os.path.join(LOG_DIR, "agent.log")

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.handlers.RotatingFileHandler(
            LOG_FILE, maxBytes=10_000_000, backupCount=3, encoding="utf-8"
        ),
    ]
)
logger = logging.getLogger(__name__)
logger.info(f"Logs writing to {LOG_FILE}")

# ============================================================================
# CONFIGURATION
# ============================================================================

from agent.version import VERSION  # Single source of truth
DEFAULT_PORT = 8052
PORT_RANGE_END = 8099


def _find_free_port(start: int = DEFAULT_PORT, end: int = PORT_RANGE_END) -> int:
    """Find a free port in the range [start, end]. Raises RuntimeError if none available."""
    for port in range(start, end + 1):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    raise RuntimeError(f"No free port found in range {start}-{end}")


PORT = DEFAULT_PORT  # Will be resolved at startup in main()

# Sprint 101: Track whether infra scan has been sent this session
_infra_sent = False

# Agent mode: "local" (standalone) or "cloud" (send to Hub)
AGENT_MODE = os.getenv("AGENT_MODE", "cloud")

# Hub configuration (for cloud mode)
HUB_URL = os.getenv("HUB_URL", "https://apollo-cloud-api-production.up.railway.app")
HUB_API_KEY = os.getenv("HUB_API_KEY", "")

# Sprint 91: Active API key — set at login, used for all Hub calls
_active_api_key = HUB_API_KEY


def _get_active_key() -> str:
    """Return the active API key (set at login, fallback to .env)."""
    return _active_api_key or HUB_API_KEY


def _silent_infra_scan():
    """
    Silent infrastructure scan — runs once per session after login.
    Collects hardware inventory (disks, RAID, network, backup agents)
    and sends to Hub as source_type="infra". Non-blocking, failure = warning only.
    Sprint 101 original, refactored to run at login (not tied to FILES scan).
    """
    global _infra_sent
    if _infra_sent:
        return
    if AGENT_MODE != "cloud" or not _get_active_key():
        return
    try:
        from agent.core.infra_scanner import scan_infrastructure
        logger.info("[INFRA] Silent infrastructure scan starting...")
        infra_data = scan_infrastructure(source_path=None)
        infra_payload = {
            "source_type": "infra",
            "version": VERSION,
            "timestamp": datetime.now().isoformat(),
            "status": "success",
            "error": None,
            "scores": None,
            "infra_summary": infra_data,
        }
        hub_resp, elapsed, err = send_to_hub(infra_payload, "infra")
        if hub_resp:
            _infra_sent = True
            logger.info(f"[INFRA] Sent to Hub in {elapsed:.1f}s: report_id={hub_resp.get('report_id')}")
        else:
            logger.warning(f"[INFRA] Hub send failed (non-blocking): {err}")
    except Exception as e:
        logger.warning(f"[INFRA] Silent scan failed (non-blocking): {e}")


# Timeouts (in seconds) - Sprint 37 large scale tests
TIMEOUT_FILES = 36000  # 10 hours for large NFS scans (350K+ files, 6TB+)
TIMEOUT_DB = 7200      # 2 hours for large databases (45M+ rows)

# Agent root directory (for subprocess cwd)
AGENT_ROOT = Path(__file__).parent.parent.parent.absolute()

# Frozen binary detection (PyInstaller)
_IS_FROZEN = getattr(sys, 'frozen', False)


def _build_scan_cmd(module: str, extra_args: list) -> list:
    """Build subprocess command, adapting for frozen binary (PyInstaller).

    In source mode:  ['python3', '-m', 'agent.main_db', '--config', ...]
    In frozen mode:  ['./apollo-agent', '--mode', 'db', '--config', ...]
    """
    if _IS_FROZEN:
        mode_map = {
            "agent.main": "files",
            "agent.main_db": "db",
            "agent.main_directory": "directory",
            "agent.main_app": "app",
        }
        mode = mode_map.get(module, "files")
        return [sys.executable, "--mode", mode] + extra_args
    else:
        return [sys.executable, "-m", module] + extra_args


# ============================================================================
# TIER ENFORCEMENT (Sprint 88B - Free Tier)
# ============================================================================

# Tiers that unlock DB and Cloud connectors
PAID_TIERS = {"starter", "business", "enterprise"}


def _get_current_tier() -> str:
    """Get current client tier from Hub /hub/me. Returns 'free' on any error."""
    if AGENT_MODE != "cloud" or not _get_active_key():
        return "free"
    try:
        resp = requests.get(
            f"{HUB_URL}/api/v1/hub/me",
            headers={"X-API-Key": _get_active_key()},
            timeout=5
        )
        if resp.status_code == 200:
            data = resp.json()
            subscription = data.get("subscription") or {}
            return subscription.get("tier", "free")
    except Exception:
        pass
    return "free"


def check_tier_or_403(feature: str = "databases"):
    """Raise HTTP 403 if current tier is free. Admin keys bypass."""
    if _get_active_key() and _get_active_key().startswith("admin_"):
        return  # Admin bypass
    tier = _get_current_tier()
    if tier not in PAID_TIERS:
        raise HTTPException(
            status_code=403,
            detail=f"Database and Cloud connectors require Starter tier or above. "
                   f"Current tier: {tier}. "
                   f"Upgrade at apollo.aiia-tech.com, then reconnect with your new API key."
        )


# ============================================================================
# ERROR COLLECTOR (Sprint 39 - UI Error Panel)
# ============================================================================

@dataclass
class ErrorEntry:
    """Single error entry for UI display."""
    timestamp: str
    level: str  # ERROR, WARNING
    source: str  # files, db, cloud, hub
    message: str


class ErrorCollector:
    """
    Collects errors per session with auto-rotation.

    - deque(maxlen=100) prevents memory leak
    - In-memory only (acceptable for 2-3x/month usage)
    """

    def __init__(self, max_errors: int = 100):
        self._errors: deque = deque(maxlen=max_errors)

    def add(self, level: str, source: str, message: str) -> None:
        """Add an error entry."""
        self._errors.append(ErrorEntry(
            timestamp=datetime.now().isoformat(),
            level=level,
            source=source,
            message=message[:500]  # Truncate long messages
        ))

    def get_all(self) -> List[dict]:
        """Get all errors as list of dicts."""
        return [
            {
                "timestamp": e.timestamp,
                "level": e.level,
                "source": e.source,
                "message": e.message
            }
            for e in self._errors
        ]

    def get_by_level(self, level: str) -> List[dict]:
        """Filter errors by level (ERROR, WARNING)."""
        return [e for e in self.get_all() if e["level"] == level]

    def count(self) -> int:
        """Total error count."""
        return len(self._errors)

    def clear(self) -> None:
        """Clear all errors."""
        self._errors.clear()


# Error collectors per session
error_collectors: Dict[str, ErrorCollector] = {}


def format_eta(seconds: float) -> str:
    """Format ETA as human readable string (shared by FILES/DATABASES/CLOUD)."""
    if seconds < 60:
        return f"{int(seconds)}s"
    elif seconds < 3600:
        return f"{int(seconds // 60)}m {int(seconds % 60)}s"
    else:
        hours = int(seconds // 3600)
        mins = int((seconds % 3600) // 60)
        return f"{hours}h {mins}m"


def collect_error(session_id: str, level: str, source: str, message: str) -> None:
    """Helper to add error to session's collector."""
    if session_id not in error_collectors:
        error_collectors[session_id] = ErrorCollector()
    error_collectors[session_id].add(level, source, message)


# ============================================================================
# MODELS
# ============================================================================

class FilesAuditRequest(BaseModel):
    sources: List[str]  # List of paths to scan
    excluded_sources: List[str] = []  # Names to exclude (opt-out)


class DbSource(BaseModel):
    db_type: str  # postgresql, mysql, mongodb
    host: str
    port: int
    database: str
    username: str = ""
    password: str = ""


class DbAuditRequest(BaseModel):
    sources: List[DbSource]
    excluded_sources: List[str] = []


class CloudCredentials(BaseModel):
    """Azure AD credentials for OneDrive/SharePoint access."""
    tenant_id: str
    client_id: str
    client_secret: str


class CloudAuditRequest(BaseModel):
    """Request to start cloud (OneDrive/SharePoint) audit."""
    tenant_id: str
    client_id: str
    client_secret: str
    drive_id: str = "me"  # "me" for default OneDrive
    cloud_path: str = "/"  # Root folder by default


class DirectorySource(BaseModel):
    """LDAP/AD directory connection parameters."""
    host: str
    port: int = 389
    bind_dn: str = ""
    bind_password: str = ""
    base_dn: str = ""
    use_ssl: bool = False


class DirectoryAuditRequest(BaseModel):
    """Request to start directory (LDAP/AD) audit."""
    host: str
    port: int = 389
    bind_dn: str = ""
    bind_password: str = ""
    base_dn: str = ""
    use_ssl: bool = False


class AppAuditRequest(BaseModel):
    """Request to start app connector (ERP/CRM/SaaS) audit."""
    app_type: str
    api_token: str = ""
    api_url: str = ""
    use_2026_api: bool = True


@dataclass
class AuditSession:
    """In-memory audit session state."""
    session_id: str
    audit_type: Literal["files", "databases", "cloud", "directory", "app"]
    status: Literal["running", "complete", "error"] = "running"
    progress: int = 0
    current_step: str = ""
    stats: Dict[str, Any] = field(default_factory=dict)
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    hub_report_id: Optional[str] = None
    hub_errors: List[str] = field(default_factory=list)  # Sprint 16: Track Hub send failures
    created_at: datetime = field(default_factory=datetime.now)


# Session storage (in-memory)
sessions: Dict[str, AuditSession] = {}
MAX_SESSIONS = 50
SESSION_TTL = timedelta(hours=1)

# Active subprocess tracking (for abort functionality)
active_processes: Dict[str, subprocess.Popen] = {}


def _evict_old_sessions():
    """Remove completed/error sessions older than TTL, then enforce max count."""
    now = datetime.now()
    # Phase 1: TTL eviction — remove finished sessions older than 1h
    expired = [
        sid for sid, s in sessions.items()
        if s.status in ("complete", "error") and (now - s.created_at) > SESSION_TTL
    ]
    for sid in expired:
        del sessions[sid]
    # Phase 2: LRU eviction — if still over max, remove oldest first
    if len(sessions) >= MAX_SESSIONS:
        by_age = sorted(sessions.items(), key=lambda kv: kv[1].created_at)
        to_remove = len(sessions) - MAX_SESSIONS + 1
        for sid, _ in by_age[:to_remove]:
            if sessions[sid].status != "running":
                del sessions[sid]

# ============================================================================
# FASTAPI APP
# ============================================================================

app = FastAPI(
    title="Apollo Agent Cloud V1.7.R",
    description="UI for Agent file and database scanning",
    version=VERSION
)

# Static files (UI)
static_dir = Path(__file__).parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


# ============================================================================
# AUTH MIDDLEWARE — KI-078: protect LAN-exposed endpoints
# ============================================================================
_PUBLIC_PATHS = frozenset({"/", "/health", "/api/v2/set-api-key"})


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    """Require active API key for all non-public endpoints."""
    path = request.url.path

    # Static files, public endpoints — pass through
    if path.startswith("/static") or path in _PUBLIC_PATHS:
        return await call_next(request)

    # Before login, no key set — allow (user must configure first)
    active_key = _get_active_key()
    if not active_key:
        return await call_next(request)

    # Check auth: X-API-Key header or apollo_api_key cookie
    req_key = (
        request.headers.get("X-API-Key")
        or request.cookies.get("apollo_api_key")
    )
    if req_key != active_key:
        return JSONResponse(
            status_code=401,
            content={"detail": "Unauthorized. Please login first."}
        )

    return await call_next(request)


# ============================================================================
# HEALTH & INFO
# ============================================================================

@app.get("/health")
async def health():
    """Health check endpoint with observability metrics."""
    # Get detailed health from observability module
    health_status = get_health_status()

    return {
        "status": health_status.status,
        "version": VERSION,
        "mode": AGENT_MODE,
        "hub_url": HUB_URL if AGENT_MODE == "cloud" else None,
        "uptime_seconds": round(health_status.uptime_seconds, 2),
        "platform": health_status.platform,
        "python_version": health_status.python_version,
        "scan": {
            "in_progress": health_status.scan_in_progress,
            "current_files": health_status.current_scan_files,
        },
        "checks": health_status.checks,
        "warnings": health_status.warnings,
    }


@app.get("/api/v2/errors/{session_id}")
async def get_session_errors(session_id: str):
    """
    Get errors for a specific session.

    Returns structured error list for UI Error Panel display.
    """
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")

    collector = error_collectors.get(session_id)
    errors = collector.get_all() if collector else []

    return {
        "session_id": session_id,
        "error_count": len(errors),
        "errors": errors,
    }


@app.get("/")
async def root():
    """Serve main UI."""
    index_path = static_dir / "index.html"
    if index_path.exists():
        return FileResponse(str(index_path))
    return {"message": "Apollo Agent Cloud V1.7.R", "docs": "/docs"}


@app.post("/api/v2/scan/abort")
async def abort_scan():
    """
    Abort any running scan (FILES or DB).

    Terminates active subprocess and marks session as aborted.
    Returns: {"status": "aborted"} or {"status": "no_active_scan"}
    """
    aborted_any = False

    # Terminate any active processes (asyncio.subprocess.Process)
    for session_id, process in list(active_processes.items()):
        try:
            if process.returncode is None:  # Process is still running
                logger.info(f"[ABORT] Terminating process for session {session_id}")
                process.terminate()
                try:
                    # Wait up to 5 seconds for graceful termination
                    await asyncio.wait_for(process.wait(), timeout=5)
                except asyncio.TimeoutError:
                    logger.warning(f"[ABORT] Force killing process {session_id}")
                    process.kill()
                    await process.wait()
                aborted_any = True

                # Update session status
                base_session_id = session_id.split("_db_")[0]  # Handle DB sub-sessions
                if base_session_id in sessions:
                    sessions[base_session_id].status = "error"
                    sessions[base_session_id].error = "Scan aborted by user"

        except Exception as e:
            logger.error(f"[ABORT] Error terminating process: {e}")

        # Remove from active processes
        if session_id in active_processes:
            del active_processes[session_id]

    # Also mark any running sessions as aborted
    for session_id, session in sessions.items():
        if session.status == "running":
            session.status = "error"
            session.error = "Scan aborted by user"
            collect_error(session_id, "WARNING", session.audit_type, "Scan aborted by user")
            aborted_any = True

    if aborted_any:
        logger.info("[ABORT] Scan aborted successfully")
        return {"status": "aborted"}
    else:
        logger.info("[ABORT] No active scan to abort")
        return {"status": "no_active_scan"}


@app.get("/api/v2/hub-client-info")
async def get_hub_client_info():
    """
    Get Hub client info for footer connection indicator.

    Returns:
        - connected: bool (true if Hub reachable and auth OK)
        - name: str (client name from Hub /me endpoint)
        - hub_url: str (Hub URL for display)

    Used by Agent UI footer to show "Connected: ClientName | Hub: Online"
    """
    if AGENT_MODE != "cloud" or not _get_active_key():
        return {
            "connected": False,
            "name": None,
            "hub_url": None,
            "reason": "Agent not in cloud mode or no API key"
        }

    try:
        response = requests.get(
            f"{HUB_URL}/api/v1/hub/me",
            headers={"X-API-Key": _get_active_key()},
            timeout=5
        )

        if response.status_code == 200:
            data = response.json()
            # Sprint 88B: read subscription tier from /hub/me
            subscription = data.get("subscription") or {}
            return {
                "connected": True,
                "name": data.get("client_name", "Unknown"),
                "hub_url": HUB_URL,
                "tier": subscription.get("tier", "free"),
                "sources_limit": subscription.get("sources_limit", 2),
                "is_admin": data.get("is_admin", False)
            }
        else:
            logger.warning(f"[HUB] /me returned {response.status_code}")
            return {
                "connected": False,
                "name": None,
                "hub_url": HUB_URL,
                "reason": f"Auth error: {response.status_code}"
            }

    except requests.exceptions.Timeout:
        logger.error("[HUB] Connection timeout")
        return {"connected": False, "name": None, "hub_url": HUB_URL, "reason": "Timeout"}

    except requests.exceptions.RequestException as e:
        logger.error(f"[HUB] Connection error: {e}")
        return {"connected": False, "name": None, "hub_url": HUB_URL, "reason": "Connection failed"}


# ============================================================================
# Sprint 91: API key propagation — browser → server
# ============================================================================

@app.post("/api/v2/set-api-key")
async def set_api_key(request: Request):
    """
    Sprint 91: Validate and activate an API key from the browser.

    The browser sends the key entered at login. The server validates it
    against Hub /me BEFORE accepting it. This ensures _active_api_key
    always holds a valid, Hub-verified key.
    """
    global _active_api_key
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    api_key = body.get("api_key", "").strip()
    if not api_key:
        raise HTTPException(status_code=400, detail="api_key is required")

    # Validate via Hub /me — the key MUST be accepted by Hub
    try:
        response = requests.get(
            f"{HUB_URL}/api/v1/hub/me",
            headers={"X-API-Key": api_key},
            timeout=5
        )
        if response.status_code != 200:
            logger.warning(f"[AUTH] set-api-key rejected by Hub: {response.status_code}")
            raise HTTPException(
                status_code=401,
                detail=f"Hub rejected this API key (status {response.status_code})"
            )
        hub_data = response.json()
    except requests.exceptions.RequestException as e:
        logger.error(f"[AUTH] Hub unreachable during set-api-key: {e}")
        raise HTTPException(status_code=502, detail="Cannot reach Hub to validate key")

    # Key validated — activate it
    _active_api_key = api_key
    subscription = hub_data.get("subscription") or {}
    client_name = hub_data.get("client_name", "Unknown")
    tier = subscription.get("tier", "free")
    logger.info(f"[AUTH] Active API key set for client '{client_name}' (tier={tier})")

    # Silent infra scan at login — non-blocking background thread
    import threading
    threading.Thread(target=_silent_infra_scan, daemon=True).start()

    resp = JSONResponse(content={
        "status": "ok",
        "client_name": client_name,
        "tier": tier,
        "is_admin": hub_data.get("is_admin", False)
    })
    resp.set_cookie(key="apollo_api_key", value=api_key, httponly=True, samesite="strict")
    return resp


@app.post("/api/v2/logout")
async def logout():
    """
    Sprint 91: Reset active API key on logout.

    Falls back to HUB_API_KEY from .env (installer default).
    Next login will require set-api-key again.
    """
    global _active_api_key
    _active_api_key = HUB_API_KEY
    logger.info("[AUTH] Logout — active API key reset to .env default")
    resp = JSONResponse(content={"status": "ok"})
    resp.delete_cookie(key="apollo_api_key")
    return resp


# ============================================================================
# DISCOVER ENDPOINTS
# ============================================================================

@app.get("/api/v2/discover/files")
async def discover_files():
    """
    Discover available file sources (folders in home directory).

    Returns:
        List of folders with metadata (files_count, accessible, default_excluded)
    """
    home = Path.home()
    sources = []

    # Large/system folders to exclude by default
    default_excluded = {
        'Library', 'Applications', '.Trash', 'node_modules',
        'venv', '.venv', '__pycache__', '.git', '.cache',
        'Caches', 'Logs', '.npm', '.docker'
    }

    try:
        for entry in sorted(home.iterdir()):
            if entry.is_dir():
                name = entry.name

                # Skip hidden folders (except explicitly useful ones)
                if name.startswith('.') and name not in {'.config', '.local'}:
                    continue

                # Check accessibility
                accessible = os.access(entry, os.R_OK)

                # Count files (limit scan depth for performance)
                files_count = 0
                if accessible:
                    try:
                        files_count = sum(1 for f in entry.iterdir() if f.is_file())
                    except PermissionError:
                        accessible = False

                sources.append({
                    "name": name,
                    "path": str(entry),
                    "files_count": files_count,
                    "accessible": accessible,
                    "default_excluded": name in default_excluded
                })
    except Exception as e:
        logger.error(f"Error discovering files: {e}")

    return {"sources": sources, "count": len(sources)}


@app.get("/api/db/connectors")
async def list_connectors():
    """
    Liste tous les connecteurs disponibles avec leurs métadonnées.

    Returns:
        Liste des METADATA de chaque connecteur enregistré.
        Utilisé par le frontend pour affichage dynamique.
    """
    return {"connectors": get_all_connectors_metadata()}


@app.get("/api/v2/discover/databases")
async def discover_databases():
    """
    Discover available database sources via port scanning.

    Auto-discover is available to ALL tiers (free included).
    Only the audit endpoint (POST /databases/audit) requires paid tier.

    DYNAMIQUE: Lit les ports depuis le registry des connecteurs.
    Ajouter un connecteur = autodiscovery automatique, ZERO modification UI.
    """
    # Ports dynamiques depuis le registry (plus de hardcode!)
    db_ports = get_ports_to_scan()

    sources = []

    for db in db_ports:
        # Quick socket connect test
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(0.5)

        try:
            result = sock.connect_ex(("127.0.0.1", db["port"]))
            if result == 0:
                sources.append({
                    "name": db["name"],
                    "db_type": db["db_type"],
                    "host": "localhost",
                    "port": db["port"],
                    "database": "",  # User will fill
                    "username": "",  # User will fill
                    "password": "",  # User will fill
                    "active": True
                })
        except Exception:
            pass
        finally:
            sock.close()

    return {"sources": sources, "count": len(sources)}


# ============================================================================
# FILES AUDIT
# ============================================================================

@app.post("/api/v2/files/audit")
async def start_files_audit(request: FilesAuditRequest, background_tasks: BackgroundTasks):
    """
    Start FILES audit via subprocess CLI.

    IMPORTANT: Uses subprocess pattern (NOT direct import) for isolation.
    """
    session_id = str(uuid.uuid4())

    # Filter out excluded sources
    sources = [s for s in request.sources if s not in request.excluded_sources]

    if not sources:
        raise HTTPException(status_code=400, detail="No sources to scan")

    # Create session
    session = AuditSession(
        session_id=session_id,
        audit_type="files",
        status="running",
        progress=0,
        current_step="Initializing..."
    )
    _evict_old_sessions()
    sessions[session_id] = session

    # Launch background task
    background_tasks.add_task(execute_files_audit, session_id, sources)

    return {"session_id": session_id, "status": "started", "sources_count": len(sources)}


async def execute_files_audit(session_id: str, sources: List[str]):
    """Execute FILES audit via subprocess CLI."""
    session = sessions[session_id]
    output_path = os.path.join(tempfile.gettempdir(), f"apollo_files_{session_id}.json")

    try:
        session.current_step = "Scanning files..."
        session.progress = 10

        # ================================================================
        # SUBPROCESS CLI - ASYNC (allows abort during execution)
        # ================================================================
        cmd = _build_scan_cmd("agent.main", sources + ["-o", output_path])

        logger.info(f"[FILES] Running: {' '.join(cmd[:5])}... -o {output_path}")

        # Use asyncio subprocess for true async (non-blocking)
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(AGENT_ROOT)
        )

        # Track for abort functionality
        active_processes[session_id] = process

        # ================================================================
        # STREAMING STDOUT WITH ETA (Sprint 39 - Progress Enhancement)
        # ================================================================
        # Regex patterns to parse CLI output
        pattern_found = re.compile(r'(\d+)\s*files?\s*(?:found|collected)', re.IGNORECASE)
        pattern_scanned = re.compile(r'(\d+)\s*files?\s*scanned', re.IGNORECASE)

        stdout_lines = []
        stderr_lines = []
        start_time = time.time()
        files_count = 0
        phase = "collecting"  # collecting -> scanning
        estimated_total = session.stats.get("files_discovered", 0) or 10000  # Fallback estimate

        async def read_stream(stream, lines_list, is_stdout=False):
            """Read stream by chunks (CLI uses print without newline)."""
            nonlocal files_count, phase, estimated_total
            buffer = ""

            while True:
                # Read chunks instead of lines (CLI uses end="")
                chunk = await stream.read(1024)
                if not chunk:
                    break

                decoded = chunk.decode('utf-8', errors='replace')
                buffer += decoded
                lines_list.append(decoded)

                if is_stdout:
                    # Parse files found/collected (search in accumulated buffer)
                    match_found = pattern_found.search(buffer)
                    if match_found:
                        files_count = int(match_found.group(1))
                        phase = "collecting"
                        if files_count > estimated_total:
                            estimated_total = files_count

                    # Parse files scanned
                    match_scanned = pattern_scanned.search(buffer)
                    if match_scanned:
                        files_count = int(match_scanned.group(1))
                        phase = "scanning"

                    # Calculate progress (10% -> 70%)
                    if files_count > 0 and estimated_total > 0:
                        raw_progress = files_count / estimated_total
                        session.progress = min(10 + int(raw_progress * 60), 70)

                        # Calculate ETA
                        elapsed = time.time() - start_time
                        if elapsed > 0.5 and files_count > 0:
                            throughput = files_count / elapsed
                            remaining = max(estimated_total - files_count, 0)
                            eta_seconds = remaining / throughput if throughput > 0 else 0
                            eta_str = format_eta(eta_seconds)
                            session.current_step = f"In progress... {session.progress}% - {files_count:,} fichiers - ETA: {eta_str}"
                        else:
                            session.current_step = f"In progress... {files_count:,} fichiers ({phase})"

                    # Keep buffer manageable (last 2KB)
                    if len(buffer) > 2048:
                        buffer = buffer[-1024:]

        try:
            # Read both streams concurrently with timeout
            await asyncio.wait_for(
                asyncio.gather(
                    read_stream(process.stdout, stdout_lines, is_stdout=True),
                    read_stream(process.stderr, stderr_lines, is_stdout=False)
                ),
                timeout=TIMEOUT_FILES
            )
            await process.wait()

            result = subprocess.CompletedProcess(
                args=cmd,
                returncode=process.returncode,
                stdout="\n".join(stdout_lines),
                stderr="\n".join(stderr_lines)
            )
        except asyncio.TimeoutError:
            process.kill()
            raise subprocess.TimeoutExpired(cmd, TIMEOUT_FILES)
        finally:
            # Remove from active processes
            if session_id in active_processes:
                del active_processes[session_id]

        session.progress = 70
        session.current_step = "Processing results..."

        # ================================================================
        # VALIDATION 1: Exit code
        # ================================================================
        if result.returncode != 0:
            logger.error(f"[FILES] CLI failed (exit {result.returncode}): {result.stderr}")
            raise Exception("Files scan failed. Check agent logs for details.")

        # ================================================================
        # VALIDATION 2: JSON exists
        # ================================================================
        if not os.path.exists(output_path):
            raise Exception(f"Output file not created: {output_path}")

        # ================================================================
        # LECTURE JSON - OBLIGATOIRE
        # ================================================================
        with open(output_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        # ================================================================
        # VALIDATION 3: Status check
        # ================================================================
        if data.get("status") == "error":
            raise Exception(f"Scan error: {data.get('error', 'Unknown')}")

        # ================================================================
        # EXTRACT STATS - OBLIGATOIRE (pas de "-")
        # ================================================================
        summary = data.get("summary", {})
        session.stats = {
            "files_discovered": summary.get("total_files", 0),
            "files_analyzed": summary.get("total_files", 0),
            "files_with_pii": summary.get("files_with_pii", 0),
            "total_size_bytes": summary.get("total_size_bytes", 0),
            "pii_by_type": summary.get("pii_by_type", {})
        }

        session.result = data
        session.progress = 90

        # ================================================================
        # POST HUB (si mode cloud)
        # ================================================================
        if AGENT_MODE == "cloud" and _get_active_key():
            session.current_step = "Sending to Hub..."
            hub_response, elapsed, error_msg = send_to_hub(data, "files")
            if hub_response:
                session.hub_report_id = hub_response.get("report_id")
                logger.info(f"[FILES] ✓ Sent to Hub in {elapsed:.1f}s: report_id={session.hub_report_id}")
            else:
                session.hub_errors.append(f"files: {error_msg}")
                collect_error(session_id, "ERROR", "hub", f"Files Hub send failed: {error_msg}")
                logger.error(f"[FILES] ❌ Hub send failed: {error_msg}")

        # Infra scan now runs at login (_silent_infra_scan via set_api_key)

        session.status = "complete"
        session.progress = 100
        session.current_step = "Complete"

        logger.info(f"[FILES] Audit complete: {session.stats}")

    except subprocess.TimeoutExpired:
        session.status = "error"
        session.error = f"Scan timeout ({TIMEOUT_FILES}s max)"
        collect_error(session_id, "ERROR", "files", f"Scan timeout ({TIMEOUT_FILES}s max)")
        logger.error(f"[FILES] Timeout after {TIMEOUT_FILES}s")

    except Exception as e:
        session.status = "error"
        session.error = "Scan failed. Check server logs for details."
        collect_error(session_id, "ERROR", "files", f"Audit failed: {e}")
        logger.exception(f"[FILES] Audit failed: {e}")

    finally:
        # Cleanup temp file (optional, keep for debugging)
        pass


# ============================================================================
# DATABASES AUDIT
# ============================================================================

@app.post("/api/v2/databases/audit")
async def start_databases_audit(request: DbAuditRequest, background_tasks: BackgroundTasks):
    """
    Start DATABASE audit via subprocess CLI.

    IMPORTANT: Uses subprocess pattern with triple validation.
    Sprint 88B: Requires paid tier (starter+). Free tier gets HTTP 403.
    """
    # Sprint 88B: tier enforcement
    check_tier_or_403("databases")

    session_id = str(uuid.uuid4())

    # Filter sources
    sources = [s for s in request.sources if s.database not in request.excluded_sources]

    if not sources:
        raise HTTPException(status_code=400, detail="No databases to scan")

    # Create session
    session = AuditSession(
        session_id=session_id,
        audit_type="databases",
        status="running",
        progress=0,
        current_step="Initializing..."
    )
    _evict_old_sessions()
    sessions[session_id] = session

    # Launch background task
    background_tasks.add_task(execute_databases_audit, session_id, [s.model_dump() for s in sources])

    return {"session_id": session_id, "status": "started", "databases_count": len(sources)}


async def execute_databases_audit(session_id: str, sources: List[dict]):
    """Execute DATABASE audit via subprocess CLI."""
    session = sessions[session_id]

    all_results = []
    total_tables = 0
    total_pii = 0
    errors = []
    start_time = time.time()  # Sprint 39: ETA calculation

    try:
        for idx, db_config in enumerate(sources):
            db_name = db_config.get('database', f'db_{idx}')
            session.progress = int((idx / len(sources)) * 80)

            # Sprint 39: Progress with ETA (same pattern as FILES)
            elapsed = time.time() - start_time
            if idx > 0 and elapsed > 0:
                avg_time_per_db = elapsed / idx
                remaining_dbs = len(sources) - idx
                eta_seconds = avg_time_per_db * remaining_dbs
                eta_str = format_eta(eta_seconds)
                session.current_step = f"In progress... {db_name} ({idx+1}/{len(sources)}) - {total_tables} tables - ETA: {eta_str}"
            else:
                session.current_step = f"In progress... {db_name} ({idx+1}/{len(sources)})"

            # Write temp config (owner-only permissions to protect credentials)
            config_path = os.path.join(tempfile.gettempdir(), f"apollo_db_config_{session_id}_{idx}.json")
            output_path = os.path.join(tempfile.gettempdir(), f"apollo_db_{session_id}_{idx}.json")

            _write_secure_temp(config_path, json.dumps(db_config))

            try:
                # ================================================================
                # SUBPROCESS CLI - OBLIGATOIRE
                # ================================================================
                cmd = _build_scan_cmd("agent.main_db", ["--config", config_path, "-o", output_path])

                logger.info(f"[DB] Running: {' '.join(cmd)}")

                # Use Popen for tracking (allows abort)
                process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    cwd=str(AGENT_ROOT)
                )

                # Track for abort functionality (use session_id + db index)
                process_key = f"{session_id}_db_{idx}"
                active_processes[process_key] = process

                try:
                    stdout, stderr = process.communicate(timeout=TIMEOUT_DB)
                    result = subprocess.CompletedProcess(
                        args=cmd,
                        returncode=process.returncode,
                        stdout=stdout,
                        stderr=stderr
                    )
                finally:
                    # Remove from active processes
                    if process_key in active_processes:
                        del active_processes[process_key]

                # VALIDATION 1: Exit code
                if result.returncode != 0:
                    logger.error(f"[DB] {db_name}: CLI failed - {result.stderr[:500]}")
                    errors.append(f"{db_name}: CLI failed. Check server logs for details.")
                    continue

                # VALIDATION 2: JSON exists
                if not os.path.exists(output_path):
                    error_msg = f"{db_name}: Output not created"
                    logger.error(f"[DB] {error_msg}")
                    errors.append(error_msg)
                    continue

                # LECTURE JSON
                with open(output_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)

                # VALIDATION 3: Status check
                if data.get("status") == "error":
                    logger.error(f"[DB] {db_name}: {data.get('error', 'Unknown error')}")
                    errors.append(f"{db_name}: Scan returned error. Check server logs.")
                    continue

                # Success - add to results
                all_results.append(data)
                total_tables += data.get("summary", {}).get("tables_count", 0)
                total_pii += data.get("summary", {}).get("tables_with_pii", 0)

                logger.info(f"[DB] {db_name}: {data['summary']['tables_count']} tables scanned")

            except subprocess.TimeoutExpired:
                error_msg = f"{db_name}: Timeout ({TIMEOUT_DB}s)"
                logger.error(f"[DB] {error_msg}")
                errors.append(error_msg)

            except Exception as e:
                logger.error(f"[DB] {db_name}: {e}")
                errors.append(f"{db_name}: Unexpected error. Check server logs.")

            finally:
                # Cleanup config (security - contains password)
                if os.path.exists(config_path):
                    os.remove(config_path)

        # Build stats
        session.stats = {
            "tables_discovered": total_tables,
            "tables_analyzed": total_tables,
            "tables_with_pii": total_pii,
            "databases_scanned": len(all_results),
            "databases_failed": len(errors)
        }

        # Merge results
        session.result = {
            "source_type": "databases",
            "version": VERSION,
            "databases": all_results,
            "summary": session.stats,
            "errors": errors if errors else None
        }

        session.progress = 90

        # POST HUB (if cloud mode and we have results)
        # Sprint 16: Sequential with ACK, 1s pause, explicit logging
        if AGENT_MODE == "cloud" and _get_active_key() and all_results:
            session.current_step = "Sending to Hub..."
            sent_count = 0
            failed_sends = []
            total_elapsed = 0.0

            for i, db_result in enumerate(all_results):
                source = db_result.get('source_path', db_result.get('connection', {}).get('database', 'unknown'))
                tables_count = db_result.get('summary', {}).get('tables_count', '?')

                # Log start
                logger.info(f"[HUB] Sending {source} ({tables_count} tables)...")
                session.current_step = f"Sending to Hub: {source}..."

                # Send with timing
                hub_response, elapsed, error_msg = send_to_hub(db_result, "databases")
                total_elapsed += elapsed

                if hub_response:
                    session.hub_report_id = hub_response.get("report_id")
                    sent_count += 1
                    logger.info(f"[HUB] ✓ {source} in {elapsed:.1f}s -> report_id={hub_response.get('report_id')}")
                else:
                    failed_sends.append(source)
                    session.hub_errors.append(f"{source}: {error_msg}")
                    collect_error(session_id, "ERROR", "hub", f"DB Hub send failed ({source}): {error_msg}")
                    if "TIMEOUT" in (error_msg or ""):
                        logger.error(f"[HUB] ⏱️ TIMEOUT after {elapsed:.1f}s: {source}")
                    else:
                        logger.error(f"[HUB] ❌ Failed: {source} - {error_msg}")

                # Pause 1s between sends (except last)
                if i < len(all_results) - 1:
                    time.sleep(1)

            # Final summary
            logger.info(f"[HUB] Result: {sent_count}/{len(all_results)} sent, {len(failed_sends)} failed (total {total_elapsed:.1f}s)")
            if failed_sends:
                logger.warning(f"[HUB] Failed sources: {failed_sends}")

        # Final status
        if all_results:
            session.status = "complete"
        elif errors:
            session.status = "error"
            session.error = "; ".join(errors[:3])  # First 3 errors
            for err in errors[:3]:
                collect_error(session_id, "ERROR", "db", err)
        else:
            session.status = "error"
            session.error = "No databases scanned"
            collect_error(session_id, "ERROR", "db", "No databases scanned")

        session.progress = 100
        session.current_step = "Complete"

        logger.info(f"[DB] Audit complete: {session.stats}")

    except Exception as e:
        session.status = "error"
        session.error = "Scan failed. Check server logs for details."
        collect_error(session_id, "ERROR", "db", f"Audit failed: {e}")
        logger.exception(f"[DB] Audit failed: {e}")


# ============================================================================
# CLOUD AUDIT (Sprint 35 - OneDrive/SharePoint)
# ============================================================================

TIMEOUT_CLOUD = 3600  # 1 hour for cloud scans (network latency)


@app.post("/api/v2/cloud/drives")
async def list_cloud_drives(request: CloudCredentials):
    """
    List available OneDrive/SharePoint drives.

    Uses Microsoft Graph API via agent.main --onedrive --list-drives.
    Returns list of drives with id, name, driveType.
    Auto-discover is available to ALL tiers (free included).
    Only the audit endpoint (POST /cloud/audit) requires paid tier.
    """
    try:
        # Use subprocess to call agent with list-drives (if implemented)
        # For now, authenticate and list drives via direct API call
        cmd = _build_scan_cmd("agent.main", [
            "--onedrive",
            "--tenant-id", request.tenant_id,
            "--client-id", request.client_id,
            "--client-secret", request.client_secret,
            "--list-drives"
        ])

        logger.info("[CLOUD] Listing drives...")

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
            cwd=str(AGENT_ROOT)
        )

        if result.returncode != 0:
            logger.error(f"[CLOUD] List drives failed: {result.stderr[:500]}")
            raise HTTPException(status_code=400, detail="Authentication failed. Check credentials and try again.")

        # Parse JSON output
        try:
            data = json.loads(result.stdout)
            drives = data.get("drives", [])
        except json.JSONDecodeError:
            drives = []

        return {"drives": drives, "count": len(drives)}

    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail="Connection timeout")
    except Exception as e:
        logger.error(f"[CLOUD] List drives error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@app.post("/api/v2/cloud/audit")
async def start_cloud_audit(request: CloudAuditRequest, background_tasks: BackgroundTasks):
    """
    Start CLOUD audit (OneDrive/SharePoint) via subprocess CLI.

    Uses agent.main with --onedrive flag.
    Sprint 88B: Requires paid tier (starter+). Free tier gets HTTP 403.
    """
    # Sprint 88B: tier enforcement
    check_tier_or_403("cloud")

    session_id = str(uuid.uuid4())

    # Create session
    session = AuditSession(
        session_id=session_id,
        audit_type="cloud",
        status="running",
        progress=0,
        current_step="Connecting to OneDrive..."
    )
    _evict_old_sessions()
    sessions[session_id] = session

    # Launch background task
    background_tasks.add_task(
        execute_cloud_audit,
        session_id,
        request.tenant_id,
        request.client_id,
        request.client_secret,
        request.drive_id,
        request.cloud_path
    )

    return {"session_id": session_id, "status": "started", "drive_id": request.drive_id}


async def execute_cloud_audit(
    session_id: str,
    tenant_id: str,
    client_id: str,
    client_secret: str,
    drive_id: str,
    cloud_path: str
):
    """Execute CLOUD audit via subprocess CLI."""
    session = sessions[session_id]
    output_path = os.path.join(tempfile.gettempdir(), f"apollo_cloud_{session_id}.json")

    try:
        session.current_step = "Authenticating with Azure AD..."
        session.progress = 10

        # ================================================================
        # SUBPROCESS CLI - ASYNC
        # ================================================================
        cmd = _build_scan_cmd("agent.main", [
            "--onedrive",
            "--tenant-id", tenant_id,
            "--client-id", client_id,
            "--client-secret", client_secret,
            "--drive-id", drive_id,
            "--onedrive-path", cloud_path,
            "-o", output_path
        ])

        logger.info(f"[CLOUD] Running: agent.main --onedrive --drive-id {drive_id} -o {output_path}")

        # Use asyncio subprocess for true async
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(AGENT_ROOT)
        )

        # Track for abort functionality
        active_processes[session_id] = process

        # ================================================================
        # STREAMING STDOUT WITH ETA (Sprint 39 - Same pattern as FILES)
        # ================================================================
        pattern_found = re.compile(r'(\d+)\s*files?\s*(?:found|collected|discovered)', re.IGNORECASE)
        pattern_scanned = re.compile(r'(\d+)\s*files?\s*scanned', re.IGNORECASE)

        stdout_lines = []
        stderr_lines = []
        start_time = time.time()
        files_count = 0
        phase = "listing"

        async def read_cloud_stream(stream, lines_list, is_stdout=False):
            """Read stream and update progress for CLOUD."""
            nonlocal files_count, phase
            buffer = ""

            while True:
                chunk = await stream.read(1024)
                if not chunk:
                    break

                decoded = chunk.decode('utf-8', errors='replace')
                buffer += decoded
                lines_list.append(decoded)

                if is_stdout:
                    # Parse files found
                    match_found = pattern_found.search(buffer)
                    if match_found:
                        files_count = int(match_found.group(1))
                        phase = "listing"

                    # Parse files scanned
                    match_scanned = pattern_scanned.search(buffer)
                    if match_scanned:
                        files_count = int(match_scanned.group(1))
                        phase = "scanning"

                    # Update progress with ETA
                    if files_count > 0:
                        session.progress = min(30 + int((files_count / max(files_count * 1.2, 100)) * 40), 70)
                        elapsed = time.time() - start_time
                        if elapsed > 1:
                            # Estimate ETA based on throughput
                            throughput = files_count / elapsed
                            # Assume ~20% more files to process
                            remaining = int(files_count * 0.2)
                            eta_seconds = remaining / throughput if throughput > 0 else 0
                            eta_str = format_eta(eta_seconds)
                            session.current_step = f"In progress... {files_count:,} fichiers cloud ({phase}) - ETA: {eta_str}"
                        else:
                            session.current_step = f"In progress... {files_count:,} fichiers cloud ({phase})"

                    # Keep buffer manageable
                    if len(buffer) > 2048:
                        buffer = buffer[-1024:]

        try:
            await asyncio.wait_for(
                asyncio.gather(
                    read_cloud_stream(process.stdout, stdout_lines, is_stdout=True),
                    read_cloud_stream(process.stderr, stderr_lines, is_stdout=False)
                ),
                timeout=TIMEOUT_CLOUD
            )
            await process.wait()

            result = subprocess.CompletedProcess(
                args=cmd,
                returncode=process.returncode,
                stdout="\n".join(stdout_lines),
                stderr="\n".join(stderr_lines)
            )
        except asyncio.TimeoutError:
            process.kill()
            raise subprocess.TimeoutExpired(cmd, TIMEOUT_CLOUD)
        finally:
            if session_id in active_processes:
                del active_processes[session_id]

        session.progress = 70

        # DIAG: dump subprocess stderr to agent.log for PII debug
        if stderr_lines:
            for line in stderr_lines:
                if "[DIAG" in line:
                    logger.warning(f"[CLOUD-DIAG] {line.strip()}")

        # ================================================================
        # VALIDATION 1: Exit code
        # ================================================================
        if result.returncode != 0:
            logger.error(f"[CLOUD] CLI failed (exit {result.returncode}): {result.stderr}")
            raise Exception("Cloud scan failed. Check agent logs for details.")

        # ================================================================
        # VALIDATION 2: JSON exists
        # ================================================================
        if not os.path.exists(output_path):
            raise Exception(f"Output file not created: {output_path}")

        # ================================================================
        # LECTURE JSON
        # ================================================================
        with open(output_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        # ================================================================
        # VALIDATION 3: Status check
        # ================================================================
        if data.get("status") == "error":
            raise Exception(f"Scan error: {data.get('error', 'Unknown')}")

        # ================================================================
        # EXTRACT STATS
        # ================================================================
        summary = data.get("summary", {})
        session.stats = {
            "files_count": summary.get("total_files", 0),
            "total_size": summary.get("total_size_bytes", 0),
            "shared_files_count": summary.get("shared_files_count", 0),
            "files_with_pii": summary.get("files_with_pii", 0)
        }

        session.result = data
        session.progress = 90

        # ================================================================
        # POST HUB (si mode cloud)
        # ================================================================
        if AGENT_MODE == "cloud" and _get_active_key():
            session.current_step = "Sending to Hub..."
            hub_response, elapsed, error_msg = send_to_hub(data, "cloud")
            if hub_response:
                session.hub_report_id = hub_response.get("report_id")
                logger.info(f"[CLOUD] ✓ Sent to Hub in {elapsed:.1f}s: report_id={session.hub_report_id}")
            else:
                session.hub_errors.append(f"cloud: {error_msg}")
                collect_error(session_id, "ERROR", "hub", f"Cloud Hub send failed: {error_msg}")
                logger.error(f"[CLOUD] ❌ Hub send failed: {error_msg}")

        session.status = "complete"
        session.progress = 100
        session.current_step = "Complete"

        logger.info(f"[CLOUD] Audit complete: {session.stats}")

    except subprocess.TimeoutExpired:
        session.status = "error"
        session.error = f"Cloud scan timeout ({TIMEOUT_CLOUD}s max)"
        collect_error(session_id, "ERROR", "cloud", f"Cloud scan timeout ({TIMEOUT_CLOUD}s max)")
        logger.error(f"[CLOUD] Timeout after {TIMEOUT_CLOUD}s")

    except Exception as e:
        session.status = "error"
        session.error = "Scan failed. Check server logs for details."
        collect_error(session_id, "ERROR", "cloud", f"Audit failed: {e}")
        logger.exception(f"[CLOUD] Audit failed: {e}")


@app.get("/api/v2/cloud/progress/{session_id}")
async def cloud_progress(session_id: str):
    """SSE progress stream for CLOUD audit."""
    return await stream_progress(session_id)


@app.get("/api/v2/cloud/results/{session_id}")
async def cloud_results(session_id: str):
    """Get CLOUD audit results."""
    return get_session_results(session_id)


# ============================================================================
# DIRECTORY AUDIT (Sprint 87 - LDAP/AD)
# ============================================================================

TIMEOUT_DIRECTORY = 300  # 5 minutes for LDAP queries


@app.post("/api/v2/directory/test")
async def test_directory_connection(request: DirectoryAuditRequest):
    """
    Test LDAP/AD connection (in-process, bounded size_limit=1).

    Returns: {"status": "ok", "directory_type": "ad"|"ldap"} or error.
    """
    from agent.core.directory_connectors import LDAPConnector

    config = {
        "host": request.host,
        "port": request.port,
        "bind_dn": request.bind_dn,
        "bind_password": request.bind_password,
        "base_dn": request.base_dn,
        "use_ssl": request.use_ssl,
        "timeout": 10,
    }

    connector = None
    try:
        connector = LDAPConnector(config)
        result = await asyncio.wait_for(connector.test_connection(), timeout=15.0)
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="Connection timeout (15s)")
    except Exception as e:
        logger.error(f"[DIRECTORY] Test connection error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if connector:
            try:
                await connector.disconnect()
            except Exception:
                pass

    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "Connection failed"))

    return {
        "status": "ok",
        "directory_type": result.get("directory_type", "unknown"),
        "message": f"Connected to {result.get('directory_type', 'directory')} at {request.host}:{request.port}",
    }


@app.post("/api/v2/directory/audit")
async def start_directory_audit(request: DirectoryAuditRequest, background_tasks: BackgroundTasks):
    """
    Start DIRECTORY audit (LDAP/AD) via subprocess CLI.

    Uses agent.main_directory with --config flag.
    """
    session_id = str(uuid.uuid4())

    # Create session
    session = AuditSession(
        session_id=session_id,
        audit_type="directory",
        status="running",
        progress=0,
        current_step="Connecting to directory..."
    )
    _evict_old_sessions()
    sessions[session_id] = session

    # Launch background task
    background_tasks.add_task(
        execute_directory_audit,
        session_id,
        request.model_dump()
    )

    return {"session_id": session_id, "status": "started", "host": request.host}


async def execute_directory_audit(session_id: str, config: dict):
    """Execute DIRECTORY audit via subprocess CLI."""
    session = sessions[session_id]
    config_path = os.path.join(tempfile.gettempdir(), f"apollo_dir_config_{session_id}.json")
    output_path = os.path.join(tempfile.gettempdir(), f"apollo_dir_{session_id}.json")

    try:
        session.current_step = "Connecting to LDAP/AD..."
        session.progress = 10

        # Write temp config (owner-only permissions to protect credentials)
        _write_secure_temp(config_path, json.dumps(config))

        # ================================================================
        # SUBPROCESS CLI
        # ================================================================
        cmd = _build_scan_cmd("agent.main_directory", ["--config", config_path, "-o", output_path])

        logger.info(f"[DIRECTORY] Running: agent.main_directory --config ... -o {output_path}")

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(AGENT_ROOT)
        )

        # Track for abort functionality
        active_processes[session_id] = process

        session.progress = 30
        session.current_step = "Querying directory..."

        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=TIMEOUT_DIRECTORY
            )
        except asyncio.TimeoutError:
            process.kill()
            raise subprocess.TimeoutExpired(cmd, TIMEOUT_DIRECTORY)
        finally:
            if session_id in active_processes:
                del active_processes[session_id]

        session.progress = 70
        session.current_step = "Processing results..."

        # ================================================================
        # VALIDATION 1: Exit code
        # ================================================================
        if process.returncode != 0:
            stderr_text = stderr.decode('utf-8', errors='replace') if stderr else ''
            logger.error(f"[DIRECTORY] CLI failed (exit {process.returncode}): {stderr_text}")
            raise Exception("Directory scan failed. Check agent logs for details.")

        # ================================================================
        # VALIDATION 2: JSON exists
        # ================================================================
        if not os.path.exists(output_path):
            raise Exception(f"Output file not created: {output_path}")

        # ================================================================
        # LECTURE JSON
        # ================================================================
        with open(output_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        # ================================================================
        # VALIDATION 3: Status check
        # ================================================================
        if data.get("status") == "error":
            raise Exception(f"Scan error: {data.get('error', 'Unknown')}")

        # ================================================================
        # EXTRACT STATS
        # ================================================================
        users = data.get("users_summary", {})
        groups = data.get("groups_summary", {})
        admins = data.get("admin_summary", {})
        session.stats = {
            "total_users": users.get("total", 0),
            "disabled_users": users.get("disabled_in_groups", 0),
            "dormant_users": users.get("dormant_90d", 0),
            "service_accounts": users.get("service_accounts", 0),
            "total_groups": groups.get("total", 0),
            "total_admins": admins.get("total_admins", 0),
        }

        session.result = data
        session.progress = 90

        # ================================================================
        # POST HUB (si mode cloud)
        # ================================================================
        if AGENT_MODE == "cloud" and _get_active_key():
            session.current_step = "Sending to Hub..."
            hub_response, elapsed, error_msg = send_to_hub(data, "directory")
            if hub_response:
                session.hub_report_id = hub_response.get("report_id")
                logger.info(f"[DIRECTORY] Sent to Hub in {elapsed:.1f}s: report_id={session.hub_report_id}")
            else:
                session.hub_errors.append(f"directory: {error_msg}")
                collect_error(session_id, "ERROR", "hub", f"Directory Hub send failed: {error_msg}")
                logger.error(f"[DIRECTORY] Hub send failed: {error_msg}")

        session.status = "complete"
        session.progress = 100
        session.current_step = "Complete"

        logger.info(f"[DIRECTORY] Audit complete: {session.stats}")

    except subprocess.TimeoutExpired:
        session.status = "error"
        session.error = f"Directory scan timeout ({TIMEOUT_DIRECTORY}s max)"
        collect_error(session_id, "ERROR", "directory", f"Timeout ({TIMEOUT_DIRECTORY}s)")
        logger.error(f"[DIRECTORY] Timeout after {TIMEOUT_DIRECTORY}s")

    except Exception as e:
        session.status = "error"
        session.error = "Scan failed. Check server logs for details."
        collect_error(session_id, "ERROR", "directory", f"Audit failed: {e}")
        logger.exception(f"[DIRECTORY] Audit failed: {e}")

    finally:
        # Cleanup config (security - contains bind password)
        if os.path.exists(config_path):
            os.remove(config_path)


@app.get("/api/v2/directory/progress/{session_id}")
async def directory_progress(session_id: str):
    """SSE progress stream for DIRECTORY audit."""
    return await stream_progress(session_id)


@app.get("/api/v2/directory/results/{session_id}")
async def directory_results(session_id: str):
    """Get DIRECTORY audit results."""
    return get_session_results(session_id)


# ============================================================================
# APP AUDIT (Sprint 89 - Pennylane / ERP / CRM / SaaS)
# ============================================================================

TIMEOUT_APP = 300  # 5 minutes for API queries + rate limiting


@app.post("/api/v2/app/test")
async def test_app_connection(request: AppAuditRequest):
    """
    Test app connector connection without full audit.

    Returns: {"status": "ok", "app_type": str, "company_name": str} or error.
    """
    config_path = os.path.join(tempfile.gettempdir(), f"apollo_app_test_{uuid.uuid4()}.json")

    try:
        config = {
            "app_type": request.app_type,
            "api_token": request.api_token,
        }
        if request.api_url:
            config["api_url"] = request.api_url
        config["use_2026_api"] = request.use_2026_api

        # Write temp config (owner-only permissions)
        _write_secure_temp(config_path, json.dumps(config))

        output_path = config_path.replace("_test_", "_test_out_")

        cmd = _build_scan_cmd("agent.main_app", ["--config", config_path, "-o", output_path])

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
            cwd=str(AGENT_ROOT)
        )

        if result.returncode != 0:
            logger.error(f"[APP] Test connection failed: {result.stderr[:500]}")
            raise HTTPException(status_code=400, detail="Connection failed. Check app_type, token, and API URL.")

        # Read result
        if os.path.exists(output_path):
            with open(output_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if data.get("status") == "error":
                logger.warning("[APP] Test returned error: %s", data.get("error", ""))
                raise HTTPException(status_code=400, detail="App test failed. Check configuration.")
            conn = data.get("connection", {})
            return {
                "status": "ok",
                "app_type": request.app_type,
                "company_name": conn.get("company_name", ""),
                "company_id": conn.get("company_id"),
            }
        else:
            raise HTTPException(status_code=500, detail="No output from test")

    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail="Connection timeout (30s)")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[APP] Test error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
    finally:
        for p in [config_path, config_path.replace("_test_", "_test_out_")]:
            if os.path.exists(p):
                os.remove(p)


@app.post("/api/v2/app/audit")
async def start_app_audit(request: AppAuditRequest, background_tasks: BackgroundTasks):
    """
    Start APP audit (ERP/CRM/SaaS) via subprocess CLI.

    Uses agent.main_app with --config flag.
    """
    session_id = str(uuid.uuid4())

    # Create session
    session = AuditSession(
        session_id=session_id,
        audit_type="app",
        status="running",
        progress=0,
        current_step=f"Connecting to {request.app_type}..."
    )
    _evict_old_sessions()
    sessions[session_id] = session

    # Launch background task
    background_tasks.add_task(
        execute_app_audit,
        session_id,
        request.model_dump()
    )

    return {"session_id": session_id, "status": "started", "app_type": request.app_type}


async def execute_app_audit(session_id: str, config: dict):
    """Execute APP audit via subprocess CLI."""
    session = sessions[session_id]
    config_path = os.path.join(tempfile.gettempdir(), f"apollo_app_config_{session_id}.json")
    output_path = os.path.join(tempfile.gettempdir(), f"apollo_app_{session_id}.json")

    try:
        session.current_step = f"Connecting to {config.get('app_type', 'app')}..."
        session.progress = 10

        # Write temp config (owner-only permissions to protect API token)
        _write_secure_temp(config_path, json.dumps(config))

        # ================================================================
        # SUBPROCESS CLI
        # ================================================================
        cmd = _build_scan_cmd("agent.main_app", ["--config", config_path, "-o", output_path])

        logger.info(f"[APP] Running: agent.main_app --config ... -o {output_path}")

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(AGENT_ROOT)
        )

        # Track for abort functionality
        active_processes[session_id] = process

        session.progress = 30
        session.current_step = "Scanning entities..."

        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=TIMEOUT_APP
            )
        except asyncio.TimeoutError:
            process.kill()
            raise subprocess.TimeoutExpired(cmd, TIMEOUT_APP)
        finally:
            if session_id in active_processes:
                del active_processes[session_id]

        session.progress = 70
        session.current_step = "Processing results..."

        # ================================================================
        # VALIDATION 1: Exit code
        # ================================================================
        if process.returncode != 0:
            stderr_text = stderr.decode('utf-8', errors='replace') if stderr else ''
            logger.error(f"[APP] CLI failed (exit {process.returncode}): {stderr_text}")
            raise Exception("App scan failed. Check agent logs for details.")

        # ================================================================
        # VALIDATION 2: JSON exists
        # ================================================================
        if not os.path.exists(output_path):
            raise Exception(f"Output file not created: {output_path}")

        # ================================================================
        # LECTURE JSON
        # ================================================================
        with open(output_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        # ================================================================
        # VALIDATION 3: Status check
        # ================================================================
        if data.get("status") == "error":
            raise Exception(f"Scan error: {data.get('error', 'Unknown')}")

        # ================================================================
        # EXTRACT STATS
        # ================================================================
        pii = data.get("pii_summary", {})
        fe = data.get("financial_exposure", {})
        session.stats = {
            "total_entities": pii.get("total_entities_scanned", 0),
            "total_records": pii.get("total_records", 0),
            "total_pii_values": pii.get("total_pii_values", 0),
            "highest_risk_entity": pii.get("highest_risk_entity", ""),
            "iban_count": fe.get("iban_count", 0),
        }

        session.result = data
        session.progress = 90

        # ================================================================
        # POST HUB (si mode cloud)
        # ================================================================
        if AGENT_MODE == "cloud" and _get_active_key():
            session.current_step = "Sending to Hub..."
            hub_response, elapsed, error_msg = send_to_hub(data, "app")
            if hub_response:
                session.hub_report_id = hub_response.get("report_id")
                logger.info(f"[APP] Sent to Hub in {elapsed:.1f}s: report_id={session.hub_report_id}")
            else:
                session.hub_errors.append(f"app: {error_msg}")
                collect_error(session_id, "ERROR", "hub", f"App Hub send failed: {error_msg}")
                logger.error(f"[APP] Hub send failed: {error_msg}")

        session.status = "complete"
        session.progress = 100
        session.current_step = "Complete"

        logger.info(f"[APP] Audit complete: {session.stats}")

    except subprocess.TimeoutExpired:
        session.status = "error"
        session.error = f"App scan timeout ({TIMEOUT_APP}s max)"
        collect_error(session_id, "ERROR", "app", f"Timeout ({TIMEOUT_APP}s)")
        logger.error(f"[APP] Timeout after {TIMEOUT_APP}s")

    except Exception as e:
        session.status = "error"
        session.error = "Scan failed. Check server logs for details."
        collect_error(session_id, "ERROR", "app", f"Audit failed: {e}")
        logger.exception(f"[APP] Audit failed: {e}")

    finally:
        # Cleanup config (security - contains API token)
        if os.path.exists(config_path):
            os.remove(config_path)


@app.get("/api/v2/app/progress/{session_id}")
async def app_progress(session_id: str):
    """SSE progress stream for APP audit."""
    return await stream_progress(session_id)


@app.get("/api/v2/app/results/{session_id}")
async def app_results(session_id: str):
    """Get APP audit results."""
    return get_session_results(session_id)


# ============================================================================
# PROGRESS & RESULTS
# ============================================================================

@app.get("/api/v2/files/progress/{session_id}")
async def files_progress(session_id: str):
    """SSE progress stream for FILES audit."""
    return await stream_progress(session_id)


@app.get("/api/v2/databases/progress/{session_id}")
async def databases_progress(session_id: str):
    """SSE progress stream for DATABASES audit."""
    return await stream_progress(session_id)


async def stream_progress(session_id: str):
    """Generate SSE progress events."""
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")

    async def event_generator():
        last_progress = -1

        while True:
            session = sessions.get(session_id)
            if not session:
                yield f"event: error\ndata: {json.dumps({'error': 'Session lost'})}\n\n"
                break

            # Send progress update if changed
            if session.progress != last_progress:
                data = {
                    "progress": session.progress,
                    "status": session.status,
                    "current_step": session.current_step,
                    "stats": session.stats if session.stats else None
                }
                yield f"event: progress\ndata: {json.dumps(data)}\n\n"
                last_progress = session.progress

            # Check if complete or error
            if session.status in ["complete", "error"]:
                final_data = {
                    "status": session.status,
                    "stats": session.stats,
                    "error": session.error,
                    "hub_report_id": session.hub_report_id,
                    # IMPORTANT: Include full result for export (same as sent to Hub)
                    "result": session.result
                }
                yield f"event: complete\ndata: {json.dumps(final_data)}\n\n"
                break

            await asyncio.sleep(0.5)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


@app.get("/api/v2/files/results/{session_id}")
async def files_results(session_id: str):
    """Get FILES audit results."""
    return get_session_results(session_id)


@app.get("/api/v2/databases/results/{session_id}")
async def databases_results(session_id: str):
    """Get DATABASES audit results."""
    return get_session_results(session_id)


@app.get("/api/v2/audit/result/{session_id}")
async def get_audit_result(session_id: str):
    """Get audit results (generic endpoint)."""
    return get_session_results(session_id)


def get_session_results(session_id: str) -> dict:
    """Get results for a session."""
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")

    session = sessions[session_id]

    return {
        "session_id": session_id,
        "audit_type": session.audit_type,
        "status": session.status,
        "stats": session.stats,
        "result": session.result,
        "error": session.error,
        "hub_report_id": session.hub_report_id
    }


# ============================================================================
# HUB INTEGRATION
# ============================================================================

def send_to_hub(data: dict, source_type: str) -> tuple[Optional[dict], float, Optional[str]]:
    """
    Send scan results to Hub Cloud with timing.

    Returns:
        Tuple of (response_dict, elapsed_seconds, error_message)
        - On success: ({"report_id": ...}, elapsed, None)
        - On failure: (None, elapsed, "error description")
    """
    import time
    start_time = time.time()

    if not _get_active_key():
        logger.warning("[HUB] No API key configured, skipping")
        return None, 0.0, "No API key configured"

    source_path = data.get('source_path', data.get('connection', {}).get('database', 'unknown'))

    try:
        response = requests.post(
            f"{HUB_URL}/api/v1/hub/ingest",
            json=data,
            headers={
                "X-API-Key": _get_active_key(),
                "Content-Type": "application/json"
            },
            timeout=120  # Sprint 16: 30 → 120 pour gros payloads
        )
        elapsed = time.time() - start_time

        if response.status_code == 200:
            return response.json(), elapsed, None
        else:
            error_msg = f"HTTP {response.status_code} - {response.text[:200]}"
            return None, elapsed, error_msg

    except requests.exceptions.Timeout:
        elapsed = time.time() - start_time
        return None, elapsed, f"TIMEOUT after {elapsed:.1f}s (limit 120s)"
    except requests.exceptions.ConnectionError as e:
        elapsed = time.time() - start_time
        return None, elapsed, f"CONNECTION ERROR: {e}"
    except Exception as e:
        elapsed = time.time() - start_time
        return None, elapsed, f"{type(e).__name__}: {e}"


# ============================================================================
# MAIN
# ============================================================================

def main():
    """Run the server with automatic port detection and browser launch."""
    import threading
    import webbrowser
    import uvicorn

    global PORT
    PORT = _find_free_port()

    logger.info(f"Starting Apollo Agent Cloud V{VERSION}")
    logger.info(f"Mode: {AGENT_MODE}")
    logger.info(f"Hub URL: {HUB_URL}")
    logger.info(f"Port: {PORT}")
    logger.info(f"Static dir: {static_dir}")

    url = f"http://localhost:{PORT}/static/login.html"
    print(f"\n  Apollo Agent V{VERSION} — UI starting on {url}\n")

    def _open_browser():
        """Wait for server to be ready, then open browser."""
        for _ in range(30):
            time.sleep(0.5)
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    if s.connect_ex(("127.0.0.1", PORT)) == 0:
                        webbrowser.open(url)
                        return
            except OSError:
                continue

    threading.Thread(target=_open_browser, daemon=True).start()

    uvicorn.run(
        "agent.ui.server:app",
        host="0.0.0.0",
        port=PORT,
        reload=False
    )


if __name__ == "__main__":
    main()
