"""
Fingerprint Backend - Auto-select best available method.

SPRINT_61: Rust native acceleration with Python fallback.

Priority:
1. Rust native - +300% hash, +150% bloom
2. Python (pybloom_live + hashlib)

Usage:
    from agent.core.fingerprint_backend import (
        fingerprint_batch,
        get_bloom_filter,
        hash_files_xxhash,
        get_backend
    )

    fps = fingerprint_batch(paths)
    bloom = get_bloom_filter(capacity=1_000_000)
    bloom.add("item")
"""

import logging
from typing import List, Dict, Optional, Any
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Backend detection
_BACKEND: str = "unknown"
_NATIVE = None


def _init_backend():
    """Initialize fingerprint backend - prefer Rust, fallback to Python."""
    global _BACKEND, _NATIVE

    try:
        import apollo_io_native as native
        _NATIVE = native
        _BACKEND = 'rust-native'
        logger.info("[Fingerprint] Rust backend loaded")
    except ImportError:
        _BACKEND = 'python'
        logger.info("[Fingerprint] Using Python backend (pybloom_live)")


# Initialize on module load
_init_backend()


# =============================================================================
# FINGERPRINT DATACLASS (Compatible with both backends)
# =============================================================================

@dataclass
class Fingerprint:
    """
    Lightweight fingerprint based on metadata only.
    Compatible with both Rust and Python backends.
    """
    path_hash: str
    size: int
    mtime: float
    extension: str
    zone: str
    path: str

    def to_dict(self) -> Dict:
        return {
            'path_hash': self.path_hash,
            'size': self.size,
            'mtime': self.mtime,
            'extension': self.extension,
            'zone': self.zone,
            'path': self.path
        }

    def dedup_key(self) -> str:
        """Key for deduplication: (size, extension)"""
        return f"{self.size}:{self.extension}"


# =============================================================================
# PUBLIC API
# =============================================================================

def fingerprint_batch(paths: List[str]) -> List[Fingerprint]:
    """
    Generate fingerprints for multiple files.

    Args:
        paths: List of file paths

    Returns:
        List[Fingerprint]
    """
    if _NATIVE:
        rust_fps = _NATIVE.fingerprint_batch(paths)
        # Convert Rust Fingerprint to Python Fingerprint
        return [
            Fingerprint(
                path_hash=fp.path_hash,
                size=fp.size,
                mtime=fp.mtime,
                extension=fp.extension,
                zone=fp.zone,
                path=fp.path
            )
            for fp in rust_fps
        ]
    else:
        return _fingerprint_batch_python(paths)


def deduplicate_fingerprints(fingerprints: List[Fingerprint]) -> List[Fingerprint]:
    """
    Deduplicate fingerprints by (size, extension).

    Returns one representative per group, prioritizing sensitive zones.

    NOTE: Always uses Python implementation (faster than Rust due to PyO3 overhead)
    """
    # Python dict is faster than Rust for this operation (no PyO3 conversion overhead)
    return _deduplicate_python(fingerprints)


def fingerprint_stats(fingerprints: List[Fingerprint]) -> Dict:
    """Get statistics for fingerprints."""
    if _NATIVE:
        rust_fps = [
            _NATIVE.Fingerprint(
                fp.path_hash, fp.size, fp.mtime,
                fp.extension, fp.zone, fp.path
            )
            for fp in fingerprints
        ]
        return dict(_NATIVE.fingerprint_stats(rust_fps))
    else:
        return _fingerprint_stats_python(fingerprints)


def hash_files_xxhash(
    paths: List[str],
    max_bytes: int = 0,
    workers: int = 8
) -> List[tuple]:
    """
    Hash files using xxHash64.

    Args:
        paths: List of file paths
        max_bytes: Max bytes to hash (0 = entire file)
        workers: Number of parallel workers

    Returns:
        List[(path, hash_hex)]
    """
    if _NATIVE:
        return _NATIVE.hash_files_xxhash(paths, max_bytes, workers)
    else:
        return _hash_files_python(paths, max_bytes)


def xxhash64_string(data: str, seed: int = 0) -> str:
    """Hash a string using xxHash64."""
    if _NATIVE:
        return _NATIVE.xxhash64_string(data, seed)
    else:
        import hashlib
        # Fallback to SHA256 truncated (not xxhash but consistent)
        h = hashlib.sha256(data.encode()).hexdigest()
        return h[:16]


def hash_path(path: str) -> str:
    """Hash a path string."""
    if _NATIVE:
        return _NATIVE.hash_path(path)
    else:
        return xxhash64_string(path, 0)


# =============================================================================
# BLOOM FILTER
# =============================================================================

class BloomFilterWrapper:
    """
    BloomFilter wrapper - uses Rust or Python backend.
    """

    def __init__(self, capacity: int = 10_000_000, fp_rate: float = 0.001):
        self.capacity = capacity
        self.fp_rate = fp_rate

        if _NATIVE:
            self._bloom = _NATIVE.BloomFilterWrapper(capacity, fp_rate)
            self._backend = 'rust'
        else:
            from pybloom_live import BloomFilter
            self._bloom = BloomFilter(capacity=capacity, error_rate=fp_rate)
            self._backend = 'python'
            self._count = 0

    def add(self, item: str):
        """Add item to filter."""
        if self._backend == 'rust':
            self._bloom.add(item)
        else:
            self._bloom.add(item)
            self._count += 1

    def add_batch(self, items: List[str]):
        """Add multiple items."""
        if self._backend == 'rust':
            self._bloom.add_batch(items)
        else:
            for item in items:
                self._bloom.add(item)
                self._count += 1

    def contains(self, item: str) -> bool:
        """Check if item might be in filter."""
        if self._backend == 'rust':
            return self._bloom.contains(item)
        else:
            return item in self._bloom

    def filter_new(self, items: List[str]) -> List[str]:
        """Return items NOT in filter (definitely new)."""
        if self._backend == 'rust':
            return self._bloom.filter_new(items)
        else:
            return [item for item in items if item not in self._bloom]

    def check_and_add(self, item: str) -> bool:
        """Check and add - returns True if new."""
        if self._backend == 'rust':
            return self._bloom.check_and_add(item)
        else:
            is_new = item not in self._bloom
            if is_new:
                self._bloom.add(item)
                self._count += 1
            return is_new

    def len(self) -> int:
        """Get item count."""
        if self._backend == 'rust':
            return self._bloom.len()
        else:
            return self._count

    def clear(self):
        """Reset filter."""
        if self._backend == 'rust':
            self._bloom.clear()
        else:
            from pybloom_live import BloomFilter
            self._bloom = BloomFilter(capacity=self.capacity, error_rate=self.fp_rate)
            self._count = 0

    def memory_bytes(self) -> int:
        """Get memory usage estimate."""
        if self._backend == 'rust':
            return self._bloom.memory_bytes()
        else:
            # Estimate for pybloom
            return int(self.capacity * 10 / 8)  # ~10 bits per item


def get_bloom_filter(capacity: int = 10_000_000, fp_rate: float = 0.001) -> BloomFilterWrapper:
    """Create a new BloomFilter."""
    return BloomFilterWrapper(capacity, fp_rate)


def get_backend() -> str:
    """Return current fingerprint backend name."""
    return _BACKEND


# =============================================================================
# PYTHON FALLBACK IMPLEMENTATIONS
# =============================================================================

def _fingerprint_batch_python(paths: List[str]) -> List[Fingerprint]:
    """Python fallback for fingerprint generation."""
    import os
    import hashlib
    from pathlib import Path

    SENSITIVE_ZONES = {
        "rh", "hr", "clients", "customers", "customer", "finance", "legal",
        "juridique", "personnel", "paie", "salaires", "salaire", "wages",
        "contracts", "contrats", "confidential", "confidentiel", "private", "prive"
    }
    ARCHIVE_ZONES = {
        "backup", "archive", "old", "archives", "backups", "historique",
        "history", "trash", "temp", "tmp", "cache"
    }

    def detect_zone(path: str) -> str:
        path_lower = path.lower()
        parts = set(Path(path_lower).parts)
        if parts & SENSITIVE_ZONES:
            return "sensitive"
        if parts & ARCHIVE_ZONES:
            return "archive"
        return "normal"

    results = []
    for path in paths:
        try:
            st = os.stat(path)
            if not os.path.isfile(path):
                continue

            path_hash = hashlib.sha256(path.encode()).hexdigest()[:16]
            ext = Path(path).suffix.lower() or ".no_ext"

            results.append(Fingerprint(
                path_hash=path_hash,
                size=st.st_size,
                mtime=st.st_mtime,
                extension=ext,
                zone=detect_zone(path),
                path=path
            ))
        except (OSError, PermissionError):
            pass

    return results


def _deduplicate_python(fingerprints: List[Fingerprint]) -> List[Fingerprint]:
    """Python fallback for deduplication."""
    from collections import defaultdict

    groups = defaultdict(list)
    for fp in fingerprints:
        key = fp.dedup_key()
        groups[key].append(fp)

    priority = {"sensitive": 0, "normal": 1, "archive": 2}
    representatives = []
    for fps in groups.values():
        fps.sort(key=lambda x: priority.get(x.zone, 1))
        representatives.append(fps[0])

    return representatives


def _fingerprint_stats_python(fingerprints: List[Fingerprint]) -> Dict:
    """Python fallback for stats."""
    from collections import Counter

    total = len(fingerprints)
    total_size = sum(fp.size for fp in fingerprints)
    by_zone = dict(Counter(fp.zone for fp in fingerprints))
    by_ext = dict(Counter(fp.extension for fp in fingerprints).most_common(10))

    return {
        "total": total,
        "total_size_bytes": total_size,
        "total_size_mb": total_size / 1_000_000,
        "by_zone": by_zone,
        "by_extension_top10": by_ext
    }


def _hash_files_python(paths: List[str], max_bytes: int) -> List[tuple]:
    """Python fallback for file hashing."""
    import hashlib

    results = []
    for path in paths:
        try:
            with open(path, 'rb') as f:
                if max_bytes > 0:
                    data = f.read(max_bytes)
                else:
                    data = f.read()
                h = hashlib.sha256(data).hexdigest()[:16]
                results.append((path, h))
        except (OSError, PermissionError):
            pass

    return results
