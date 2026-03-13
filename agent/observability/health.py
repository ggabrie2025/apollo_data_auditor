"""
Apollo Agent - Health Status Module
====================================

Simple health check endpoint support.
Exposes agent status for external monitoring.

NON-DESTRUCTIF: Read-only status reporting.
ZERO OVERHEAD: Minimal computation, on-demand only.

Version: 1.0.0
Copyright: (c) 2025 Gilles Gabriel - gilles.gabriel@noos.fr
"""

import os
import sys
import time
import platform
from datetime import datetime
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from agent.version import VERSION  # Single source of truth


@dataclass
class HealthStatus:
    """Agent health status."""
    status: str  # "healthy", "degraded", "unhealthy"
    timestamp: str
    uptime_seconds: float
    version: str

    # System info
    platform: str
    python_version: str
    pid: int

    # Scan status
    scan_in_progress: bool = False
    current_scan_files: int = 0
    current_scan_duration: float = 0.0

    # Last scan info
    last_scan_completed: Optional[str] = None
    last_scan_files: int = 0
    last_scan_errors: int = 0

    # Checks
    checks: Dict[str, bool] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON response."""
        return {
            "status": self.status,
            "timestamp": self.timestamp,
            "uptime_seconds": round(self.uptime_seconds, 2),
            "version": self.version,
            "system": {
                "platform": self.platform,
                "python_version": self.python_version,
                "pid": self.pid,
            },
            "scan": {
                "in_progress": self.scan_in_progress,
                "current_files": self.current_scan_files,
                "current_duration_sec": round(self.current_scan_duration, 2),
            },
            "last_scan": {
                "completed": self.last_scan_completed,
                "files": self.last_scan_files,
                "errors": self.last_scan_errors,
            },
            "checks": self.checks,
            "warnings": self.warnings,
        }


# Global state for health tracking
_start_time: float = time.time()
_last_scan_completed: Optional[str] = None
_last_scan_files: int = 0
_last_scan_errors: int = 0
_scan_in_progress: bool = False
_current_scan_start: Optional[float] = None
_current_scan_files: int = 0


def get_agent_version() -> str:
    """Get agent version (from agent.version — single source of truth)."""
    return VERSION


def get_health_status() -> HealthStatus:
    """
    Get current agent health status.

    NON-DESTRUCTIF: Read-only operation.
    ZERO OVERHEAD: Minimal computation.

    Returns:
        HealthStatus instance
    """
    global _start_time, _last_scan_completed, _last_scan_files
    global _last_scan_errors, _scan_in_progress, _current_scan_start, _current_scan_files

    # Basic status
    status = HealthStatus(
        status="healthy",
        timestamp=datetime.now().isoformat(),
        uptime_seconds=time.time() - _start_time,
        version=get_agent_version(),
        platform=platform.system(),
        python_version=platform.python_version(),
        pid=os.getpid(),
        scan_in_progress=_scan_in_progress,
        current_scan_files=_current_scan_files,
        current_scan_duration=(
            time.time() - _current_scan_start
            if _current_scan_start else 0.0
        ),
        last_scan_completed=_last_scan_completed,
        last_scan_files=_last_scan_files,
        last_scan_errors=_last_scan_errors,
    )

    # Run health checks
    checks = {}
    warnings = []

    # Check 1: Python version >= 3.9
    py_version = tuple(map(int, platform.python_version().split('.')[:2]))
    checks["python_version"] = py_version >= (3, 9)
    if not checks["python_version"]:
        warnings.append(f"Python {platform.python_version()} < 3.9 recommended")

    # Check 2: Memory available (basic check)
    try:
        import psutil
        mem = psutil.virtual_memory()
        checks["memory_available"] = mem.available > 512 * 1024 * 1024  # 512MB
        if not checks["memory_available"]:
            warnings.append(f"Low memory: {mem.available // (1024*1024)}MB available")
    except ImportError:
        checks["memory_available"] = True  # Skip if psutil not available

    # Check 3: Disk space (basic check)
    try:
        import shutil
        total, used, free = shutil.disk_usage(os.path.abspath(os.sep))
        checks["disk_space"] = free > 1024 * 1024 * 1024  # 1GB
        if not checks["disk_space"]:
            warnings.append(f"Low disk: {free // (1024*1024*1024)}GB free")
    except Exception:
        checks["disk_space"] = True  # Skip on error

    # Check 4: No errors in last scan
    checks["last_scan_clean"] = _last_scan_errors == 0

    # Determine overall status
    status.checks = checks
    status.warnings = warnings

    if not all(checks.values()):
        status.status = "degraded"

    if not checks.get("memory_available", True) or not checks.get("disk_space", True):
        status.status = "unhealthy"

    return status


# Functions to update health state (called from agent)

def mark_scan_started() -> None:
    """Mark that a scan has started."""
    global _scan_in_progress, _current_scan_start, _current_scan_files
    _scan_in_progress = True
    _current_scan_start = time.time()
    _current_scan_files = 0


def update_scan_progress(files_scanned: int) -> None:
    """Update current scan progress."""
    global _current_scan_files
    _current_scan_files = files_scanned


def mark_scan_completed(files: int, errors: int) -> None:
    """Mark that a scan has completed."""
    global _scan_in_progress, _current_scan_start, _current_scan_files
    global _last_scan_completed, _last_scan_files, _last_scan_errors

    _scan_in_progress = False
    _current_scan_start = None
    _current_scan_files = 0

    _last_scan_completed = datetime.now().isoformat()
    _last_scan_files = files
    _last_scan_errors = errors
