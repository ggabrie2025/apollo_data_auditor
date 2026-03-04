"""
Apollo Agent - JSON Exporter (V1.3)
===================================

Export scan results to JSON for Hub Cloud.
Metadata only - no file contents.

Version: 1.3.0
Date: 2025-12-11
"""

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict, Any, Optional

# Compatible imports for both module and PyInstaller
try:
    from models.contracts import (
        FileMetadata,
        ScanSummary,
        AgentOutput,
        ExclusionsConfig
    )
except ImportError:
    from agent.models.contracts import (
        FileMetadata,
        ScanSummary,
        AgentOutput,
        ExclusionsConfig
    )


from agent.version import VERSION  # Single source of truth


def create_scan_output(
    source_path: str,
    files: List[FileMetadata],
    excluded_files: List[FileMetadata],
    pii_by_type: Dict[str, int],
    config: ExclusionsConfig,
    errors: Optional[List[str]] = None,
    scanned_paths: Optional[List[str]] = None,  # NEW (Sprint 29)
    scanned_paths_count: int = 1  # NEW (Sprint 29)
) -> AgentOutput:
    """
    Create complete scan output for export.

    Args:
        source_path: Primary source path (first in scan_paths)
        files: List of included FileMetadata
        excluded_files: List of excluded FileMetadata
        pii_by_type: Count of files with each PII type
        config: ExclusionsConfig used
        errors: Optional list of errors
        scanned_paths: All paths scanned (multi-path support)
        scanned_paths_count: Number of paths scanned

    Returns:
        AgentOutput ready for JSON export
    """
    # Calculate summary
    total_size = sum(f.size for f in files)
    files_with_pii = sum(1 for f in files if f.pii_detected)

    summary = ScanSummary(
        total_files=len(files),
        total_size_bytes=total_size,
        files_with_pii=files_with_pii,
        pii_by_type=pii_by_type,
        excluded_count=len(excluded_files),
        error_count=len(errors) if errors else 0
    )

    # Serialize files
    files_data = [_serialize_file(f) for f in files]

    # Config used
    config_used = {
        "extensions_excluded": list(config.files.extensions),
        "max_file_mb": config.files.max_file_bytes // (1024 * 1024),
        "min_file_bytes": config.files.min_file_bytes,
        "path_patterns": config.files.paths,
        "filename_patterns": config.files.filename_patterns
    }

    return AgentOutput(
        version=VERSION,
        scan_id=str(uuid.uuid4()),
        timestamp=datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
        source_path=source_path,
        scanned_paths=scanned_paths,  # NEW (Sprint 29)
        scanned_paths_count=scanned_paths_count,  # NEW (Sprint 29)
        summary=summary,
        files=files_data,
        config_used=config_used,
        errors=errors
    )


def _serialize_file(file_meta: FileMetadata) -> Dict[str, Any]:
    """Serialize FileMetadata to dict."""
    return {
        "path": file_meta.path,
        "relative_path": file_meta.relative_path,
        "name": file_meta.name,
        "extension": file_meta.extension,
        "size": file_meta.size,
        "mtime": file_meta.mtime,
        "depth": file_meta.depth,
        "uid": file_meta.uid,
        "gid": file_meta.gid,
        "mode": file_meta.mode,
        # Sprint 86A datalake: stat-based
        "ctime": file_meta.ctime,
        "atime": file_meta.atime,
        "inode": file_meta.inode,
        "nlink": file_meta.nlink,
        # Sprint 86A datalake: flags
        "is_hidden": file_meta.is_hidden,
        "is_symlink": file_meta.is_symlink,
        # Sprint 86A datalake: content analysis
        "content_hash": file_meta.content_hash,
        "entropy": file_meta.entropy,
        "magic_bytes": file_meta.magic_bytes,
        "is_binary": file_meta.is_binary,
        "encoding": file_meta.encoding,
        # Scanner results
        "pii_detected": file_meta.pii_detected,
        "pii_types": file_meta.pii_types,
        "pii_count": file_meta.pii_count,
        "pii_density": file_meta.pii_density,
        "encrypted": file_meta.encrypted,
        "owner_domain": file_meta.owner_domain,
        "zone": file_meta.zone,
    }


def export_to_json(
    output: AgentOutput,
    filepath: str,
    pretty: bool = True
) -> str:
    """
    Export AgentOutput to JSON file.

    Args:
        output: AgentOutput to export
        filepath: Path for output JSON file
        pretty: Whether to format with indentation

    Returns:
        Path to created file
    """
    data = output.to_dict()

    indent = 2 if pretty else None

    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=indent, ensure_ascii=False)

    return filepath


def export_to_string(output: AgentOutput, pretty: bool = False) -> str:
    """
    Export AgentOutput to JSON string.

    Args:
        output: AgentOutput to export
        pretty: Whether to format with indentation

    Returns:
        JSON string
    """
    data = output.to_dict()
    indent = 2 if pretty else None
    return json.dumps(data, indent=indent, ensure_ascii=False)


def generate_output_filename(source_path: str) -> str:
    """
    Generate output filename based on source path.

    Format: apollo_scan_{source_name}_{timestamp}.json
    """
    source_name = Path(source_path).name or "root"
    # Clean name for filename
    safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in source_name)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"apollo_scan_{safe_name}_{timestamp}.json"


def generate_output_filename_multipath(
    primary_path: str,
    paths_count: int
) -> str:
    """
    Generate filename for multi-path scans.

    Format: apollo_report_multipath_{count}sources_{timestamp}.json

    Args:
        primary_path: Primary source path (for reference, not used in filename)
        paths_count: Number of paths scanned

    Returns:
        Filename string

    Examples:
        2 paths:    apollo_report_multipath_2sources_20251227_143000.json
        20 paths:   apollo_report_multipath_20sources_20251227_143000.json
        100 paths:  apollo_report_multipath_100sources_20251227_143000.json
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # Keep filename short and predictable
    return f"apollo_report_multipath_{paths_count}sources_{timestamp}.json"


def create_minimal_output(
    source_path: str,
    total_files: int,
    files_with_pii: int,
    pii_by_type: Dict[str, int]
) -> Dict[str, Any]:
    """
    Create minimal output for quick preview/stdout.

    Returns dict ready for JSON serialization.
    """
    return {
        "version": VERSION,
        "timestamp": datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
        "source": source_path,
        "total_files": total_files,
        "files_with_pii": files_with_pii,
        "pii_by_type": pii_by_type
    }
