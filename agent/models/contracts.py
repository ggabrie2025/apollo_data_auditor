"""
Apollo Agent - Data Contracts (V1.3)
====================================

Dataclasses for type safety - pure stdlib.
Files only (no DB contracts).

Version: 1.3.0
Date: 2025-12-11
"""

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any, Set


# =============================================================================
# FILE METADATA
# =============================================================================

@dataclass
class FileMetadata:
    """Metadata for a single file (no content)."""
    path: str
    relative_path: str
    name: str
    extension: str
    size: int
    mtime: float
    depth: int
    # Unix permissions (os.stat)
    uid: int = 0
    gid: int = 0
    mode: int = 0
    # Timestamps (os.stat) — Sprint 86A datalake
    ctime: float = 0.0
    atime: float = 0.0
    # Filesystem metadata (os.stat) — Sprint 86A datalake
    inode: int = 0
    nlink: int = 1
    # File flags — Sprint 86A datalake
    is_hidden: bool = False
    is_symlink: bool = False
    # Content analysis — Sprint 86A datalake
    content_hash: str = ""
    entropy: float = 0.0
    magic_bytes: str = ""
    is_binary: bool = False
    encoding: int = 0
    # Optional fields set by scanner
    pii_detected: bool = False
    pii_types: List[str] = field(default_factory=list)
    pii_count: int = 0
    pii_density: float = 0.0
    excluded: bool = False
    exclusion_reason: Optional[str] = None
    encrypted: bool = False
    owner_domain: int = 0
    zone: str = ""  # sensitive/normal/archive — from fingerprint


@dataclass
class CollectorConfig:
    """Configuration for file collection."""
    max_files: int = 100_000
    max_depth: int = 15
    skip_hidden: bool = True
    skip_dirs: Set[str] = field(default_factory=lambda: {
        '__pycache__', 'node_modules', '.git', '.svn',
        '.hg', 'venv', '.venv', 'env', '.env',
        'dist', 'build', '.cache', '.tmp'
    })


@dataclass
class CollectorResult:
    """Result of file collection."""
    root_path: str
    files: List[FileMetadata]
    total_size: int
    error: Optional[str] = None
    errors: Optional[List[str]] = None


# =============================================================================
# EXCLUSIONS CONFIG
# =============================================================================

@dataclass
class FilesExclusions:
    """File exclusion rules."""
    extensions: Set[str] = field(default_factory=set)
    paths: List[str] = field(default_factory=list)
    filename_patterns: List[str] = field(default_factory=list)
    max_file_bytes: int = 100 * 1024 * 1024  # 100 MB
    min_file_bytes: int = 10


@dataclass
class FreemiumLimits:
    """Freemium tier limits."""
    max_files: int = 100
    max_sources: int = 3


@dataclass
class ExclusionsConfig:
    """Complete exclusions configuration (files only)."""
    files: FilesExclusions = field(default_factory=FilesExclusions)
    freemium: FreemiumLimits = field(default_factory=FreemiumLimits)
    custom_extensions: Set[str] = field(default_factory=set)
    custom_paths: List[str] = field(default_factory=list)


# =============================================================================
# PII DETECTION
# =============================================================================

@dataclass
class PIIMatch:
    """A single PII detection match."""
    type: str  # email, phone_fr, iban, ssn_fr
    value_preview: str  # First 4 chars + "..."
    line_number: Optional[int] = None
    confidence: float = 1.0


@dataclass
class PIIScanResult:
    """Result of PII scan on a file."""
    file_path: str
    has_pii: bool
    pii_types: List[str]
    pii_count: int
    matches: List[PIIMatch] = field(default_factory=list)
    scan_error: Optional[str] = None
    estimated_data_subjects: int = 0


# =============================================================================
# EXPORT OUTPUT
# =============================================================================

@dataclass
class ScanSummary:
    """Summary statistics for export."""
    total_files: int
    total_size_bytes: int
    files_with_pii: int
    pii_by_type: Dict[str, int]
    excluded_count: int
    error_count: int
    # Scan metadata (D148-D157) — enrichir le payload Hub
    scan_duration_seconds: float = 0.0
    dedup_ratio: float = 0.0
    unchanged_files_count: int = 0
    disk_total_bytes: int = 0
    disk_free_bytes: int = 0
    zone_distribution: Optional[Dict[str, int]] = None
    total_reduction_percent: float = 0.0
    original_files_count: int = 0
    sample_ratio: float = 0.0
    is_differential: bool = False
    # KI-101: estimated data subjects (distinct identifier count)
    estimated_data_subjects: int = 0
    data_subjects_method: str = ""
    data_subjects_identifiers_used: List[str] = field(default_factory=list)
    data_subjects_fallback: bool = False


@dataclass
class AgentOutput:
    """Complete output from agent scan."""
    version: str
    scan_id: str
    timestamp: str
    source_path: str
    summary: ScanSummary
    files: List[Dict[str, Any]]  # Serialized FileMetadata
    config_used: Dict[str, Any]
    scanned_paths: Optional[List[str]] = None  # NEW: All paths (null if single)
    scanned_paths_count: int = 1  # NEW: Count for stats
    errors: Optional[List[str]] = None
    # Agent identity (bugfix — colonnes existantes en Railway, jamais peuplées)
    agent_hostname: str = ""
    agent_os: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Convert to JSON-serializable dict."""
        result = {
            "source_type": "files",  # REQUIRED by Hub V1.4.1
            "version": self.version,
            "scan_id": self.scan_id,
            "timestamp": self.timestamp,
            "source_path": self.source_path,
            "summary": {
                "total_files": self.summary.total_files,
                "total_size_bytes": self.summary.total_size_bytes,
                "files_with_pii": self.summary.files_with_pii,
                "pii_by_type": self.summary.pii_by_type,
                "excluded_count": self.summary.excluded_count,
                "error_count": self.summary.error_count,
                # D148-D157: scan metadata
                "scan_duration_seconds": self.summary.scan_duration_seconds,
                "dedup_ratio": self.summary.dedup_ratio,
                "unchanged_files_count": self.summary.unchanged_files_count,
                "disk_total_bytes": self.summary.disk_total_bytes,
                "disk_free_bytes": self.summary.disk_free_bytes,
                "zone_distribution": self.summary.zone_distribution,
                "total_reduction_percent": self.summary.total_reduction_percent,
                "original_files_count": self.summary.original_files_count,
                "sample_ratio": self.summary.sample_ratio,
                "is_differential": self.summary.is_differential,
                # KI-101: estimated data subjects
                "estimated_data_subjects": self.summary.estimated_data_subjects,
                "data_subjects_method": self.summary.data_subjects_method,
                "data_subjects_identifiers_used": self.summary.data_subjects_identifiers_used,
                "data_subjects_fallback": self.summary.data_subjects_fallback,
            },
            "files": self.files,
            "config_used": self.config_used,
            "errors": self.errors,
            # Agent identity (bugfix)
            "agent_hostname": self.agent_hostname,
            "agent_os": self.agent_os,
        }

        # NEW: Add multi-path metadata if applicable
        if self.scanned_paths and len(self.scanned_paths) > 1:
            result["scanned_paths"] = self.scanned_paths
            result["scanned_paths_count"] = self.scanned_paths_count

        return result
