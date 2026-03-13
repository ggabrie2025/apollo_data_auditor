"""
Apollo Agent - Exclusions Loader (V1.3)
=======================================

Loads exclusion rules from YAML - files only (no DB).
Simplified version for standalone agent.

Version: 1.3.0
Date: 2025-12-11
"""

import re
import fnmatch
from pathlib import Path
from typing import List, Optional, Dict, Any, Set

import yaml

# Compatible imports for both module and PyInstaller
try:
    from models.contracts import (
        ExclusionsConfig,
        FilesExclusions,
        FreemiumLimits,
        FileMetadata
    )
except ImportError:
    from agent.models.contracts import (
        ExclusionsConfig,
        FilesExclusions,
        FreemiumLimits,
        FileMetadata
    )


# Default config path (relative to module)
DEFAULT_CONFIG_PATH = Path(__file__).parent.parent / "config" / "exclusions.yaml"


def load_exclusions(config_path: Optional[Path] = None) -> ExclusionsConfig:
    """
    Load exclusions configuration from YAML file.

    Args:
        config_path: Path to exclusions.yaml (default: agent/config/)

    Returns:
        ExclusionsConfig with file exclusion rules
    """
    if config_path is None:
        config_path = DEFAULT_CONFIG_PATH

    config_path = Path(config_path)

    if not config_path.exists():
        print(f"[WARN] Config not found: {config_path}, using defaults")
        return ExclusionsConfig()

    with open(config_path, 'r', encoding='utf-8') as f:
        raw_config = yaml.safe_load(f)

    if raw_config is None:
        return ExclusionsConfig()

    return _parse_config(raw_config)


def _parse_config(raw: Dict[str, Any]) -> ExclusionsConfig:
    """Parse raw YAML dict into ExclusionsConfig (files only)."""
    config = ExclusionsConfig()

    # Parse files section
    files_raw = raw.get("files", {})
    if files_raw:
        config.files = FilesExclusions(
            extensions=set(files_raw.get("extensions", [])),
            paths=files_raw.get("paths", []),
            filename_patterns=files_raw.get("filename_patterns", []),
            max_file_bytes=files_raw.get("size", {}).get("max_file_mb", 100) * 1024 * 1024,
            min_file_bytes=files_raw.get("size", {}).get("min_file_bytes", 10)
        )

    # Parse freemium section
    free_raw = raw.get("freemium", {})
    if free_raw:
        config.freemium = FreemiumLimits(
            max_files=free_raw.get("max_files", 100),
            max_sources=free_raw.get("max_sources", 3)
        )

    # Parse custom section
    custom_raw = raw.get("custom", {})
    if custom_raw:
        config.custom_extensions = set(custom_raw.get("extensions", []))
        config.custom_paths = custom_raw.get("paths", [])

    return config


def should_exclude_file(
    file_meta: FileMetadata,
    config: ExclusionsConfig,
    compiled_patterns: Optional[list] = None
) -> tuple[bool, Optional[str]]:
    """
    Check if a file should be excluded.

    Args:
        file_meta: FileMetadata object
        config: ExclusionsConfig with exclusion rules

    Returns:
        Tuple of (should_exclude, reason)
    """
    # Check extension
    all_extensions = config.files.extensions | config.custom_extensions
    if file_meta.extension in all_extensions:
        return True, f"extension: {file_meta.extension}"

    # Check size limits
    if file_meta.size > config.files.max_file_bytes:
        size_mb = file_meta.size / (1024 * 1024)
        max_mb = config.files.max_file_bytes / (1024 * 1024)
        return True, f"size: {size_mb:.1f}MB > {max_mb:.0f}MB"

    if file_meta.size < config.files.min_file_bytes:
        return True, f"size: {file_meta.size} bytes < {config.files.min_file_bytes} min"

    # Check path patterns (glob) — normalize separators for cross-platform
    all_paths = config.files.paths + config.custom_paths
    normalized_path = file_meta.path.replace("\\", "/")
    for path_pattern in all_paths:
        normalized_pattern = path_pattern.replace("\\", "/")
        if fnmatch.fnmatch(normalized_path, normalized_pattern):
            return True, f"path pattern: {path_pattern}"

    # Check filename patterns (pre-compiled regex)
    compiled = compiled_patterns or []
    for pattern, pattern_str in compiled:
        if pattern.search(file_meta.name):
            return True, f"filename pattern: {pattern_str}"

    return False, None


def filter_files(
    files: List[FileMetadata],
    config: ExclusionsConfig
) -> tuple[List[FileMetadata], List[FileMetadata]]:
    """
    Filter files based on exclusion rules.

    Args:
        files: List of FileMetadata
        config: ExclusionsConfig

    Returns:
        Tuple of (included_files, excluded_files)
    """
    included = []
    excluded = []

    # Pre-compile regex patterns once (not per-file — fixes M-013)
    compiled_patterns = []
    for pattern_str in config.files.filename_patterns:
        try:
            compiled_patterns.append((re.compile(pattern_str), pattern_str))
        except re.error:
            continue

    for file_meta in files:
        should_exclude, reason = should_exclude_file(file_meta, config, compiled_patterns)

        if should_exclude:
            file_meta.excluded = True
            file_meta.exclusion_reason = reason
            excluded.append(file_meta)
        else:
            included.append(file_meta)

    return included, excluded


def get_exclusion_summary(config: ExclusionsConfig) -> Dict[str, Any]:
    """
    Get summary of exclusion rules for display.
    """
    return {
        "extensions_count": len(config.files.extensions) + len(config.custom_extensions),
        "extensions_sample": list(config.files.extensions)[:10],
        "path_patterns_count": len(config.files.paths) + len(config.custom_paths),
        "filename_patterns_count": len(config.files.filename_patterns),
        "max_file_mb": config.files.max_file_bytes // (1024 * 1024),
        "min_file_bytes": config.files.min_file_bytes,
        "freemium_max_files": config.freemium.max_files,
        "freemium_max_sources": config.freemium.max_sources
    }


def load_network_config(config_path: Optional[Path] = None) -> Dict[str, Any]:
    """
    Load network mount exclusion configuration from YAML.

    Args:
        config_path: Path to exclusions.yaml

    Returns:
        Dict with exclude_network_mounts (bool) and network_mount_types (list)
    """
    if config_path is None:
        config_path = DEFAULT_CONFIG_PATH

    config_path = Path(config_path)

    # Defaults
    default_config = {
        'exclude_network_mounts': True,
        'network_mount_types': ['nfs', 'nfs4', 'cifs', 'smbfs', 'fuse', 'sshfs', 's3fs']
    }

    if not config_path.exists():
        return default_config

    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            raw_config = yaml.safe_load(f)

        if raw_config is None:
            return default_config

        network_raw = raw_config.get('network', {})
        return {
            'exclude_network_mounts': network_raw.get('exclude_network_mounts', True),
            'network_mount_types': network_raw.get('network_mount_types', default_config['network_mount_types'])
        }
    except Exception:
        return default_config
