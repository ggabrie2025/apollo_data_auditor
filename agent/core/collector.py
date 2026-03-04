"""
Apollo Agent - File Collector (V1.3)
====================================

Pure stdlib file collector - NO external dependencies.
Uses os.walk for directory traversal.

Version: 1.3.0
Date: 2025-12-11
"""
from __future__ import annotations

import os
import sys
import hashlib
from pathlib import Path
from typing import List, Optional, Generator, Callable


def _is_hidden(filepath: Path, filename: str) -> bool:
    """Detect hidden files portably (Unix: dot-prefix, Windows: FILE_ATTRIBUTE_HIDDEN)."""
    if filename.startswith('.'):
        return True
    if sys.platform == 'win32':
        try:
            import ctypes
            attrs = ctypes.windll.kernel32.GetFileAttributesW(str(filepath))
            if attrs != -1 and attrs & 0x2:  # FILE_ATTRIBUTE_HIDDEN
                return True
        except Exception:
            pass
    return False

# Compatible imports for both module and PyInstaller
try:
    from models.contracts import FileMetadata, CollectorConfig, CollectorResult
except ImportError:
    from agent.models.contracts import FileMetadata, CollectorConfig, CollectorResult


def collect_files(
    root_path: str,
    config: Optional[CollectorConfig] = None,
    progress_callback: Optional[Callable[[int, str], None]] = None
) -> CollectorResult:
    """
    Collect file metadata from a directory tree.

    Pure stdlib implementation using os.walk.
    Does NOT read file contents - only metadata.

    Args:
        root_path: Root directory to scan
        config: Collection configuration (limits, depth, etc.)
        progress_callback: Optional callback(count, current_file) for progress

    Returns:
        CollectorResult with list of FileMetadata
    """
    if config is None:
        config = CollectorConfig()

    root = Path(root_path).resolve()
    if not root.exists():
        return CollectorResult(
            root_path=str(root),
            files=[],
            total_size=0,
            error=f"Path does not exist: {root}"
        )

    if not root.is_dir():
        return CollectorResult(
            root_path=str(root),
            files=[],
            total_size=0,
            error=f"Path is not a directory: {root}"
        )

    files: List[FileMetadata] = []
    total_size = 0
    errors: List[str] = []

    for file_meta in _walk_directory(root, config, progress_callback):
        if isinstance(file_meta, str):
            # Error message
            errors.append(file_meta)
            continue

        files.append(file_meta)
        total_size += file_meta.size

        if len(files) >= config.max_files:
            break

    return CollectorResult(
        root_path=str(root),
        files=files,
        total_size=total_size,
        errors=errors if errors else None
    )


def _walk_directory(
    root: Path,
    config: CollectorConfig,
    progress_callback: Optional[Callable[[int, str], None]] = None
) -> Generator[FileMetadata | str, None, None]:
    """
    Generator that yields FileMetadata for each file found.
    Yields error strings for files that couldn't be processed.
    """
    count = 0

    for dirpath, dirnames, filenames in os.walk(root, topdown=True, followlinks=False):
        current_dir = Path(dirpath)

        # Calculate depth
        try:
            depth = len(current_dir.relative_to(root).parts)
        except ValueError:
            depth = 0

        # Check max depth
        if depth > config.max_depth:
            dirnames.clear()  # Don't descend further
            continue

        # Filter hidden directories
        if config.skip_hidden:
            dirnames[:] = [d for d in dirnames if not d.startswith('.')]

        # Filter system directories
        dirnames[:] = [
            d for d in dirnames
            if d.lower() not in config.skip_dirs
        ]

        for filename in filenames:
            # Skip hidden files
            if config.skip_hidden and filename.startswith('.'):
                continue

            filepath = current_dir / filename

            try:
                # Use lstat first to detect symlinks, then stat for metadata
                is_symlink = filepath.is_symlink()
                stat = filepath.stat()

                # Skip if not a regular file
                if not filepath.is_file():
                    continue

                # Content analysis (reuses 4KB read for encrypted + entropy + magic)
                content_info = analyze_file_content(str(filepath))

                file_meta = FileMetadata(
                    path=str(filepath),
                    relative_path=str(filepath.relative_to(root)),
                    name=filename,
                    extension=filepath.suffix.lower(),
                    size=stat.st_size,
                    mtime=stat.st_mtime,
                    depth=depth,
                    uid=getattr(stat, 'st_uid', 0),
                    gid=getattr(stat, 'st_gid', 0),
                    mode=getattr(stat, 'st_mode', 0),
                    # Sprint 86A datalake: stat-based
                    ctime=getattr(stat, 'st_ctime', 0.0),
                    atime=getattr(stat, 'st_atime', 0.0),
                    inode=getattr(stat, 'st_ino', 0),
                    nlink=getattr(stat, 'st_nlink', 1),
                    # Sprint 86A datalake: path-based flags
                    is_hidden=_is_hidden(filepath, filename),
                    is_symlink=is_symlink,
                    # Sprint 86A datalake: content analysis
                    content_hash=content_info['content_hash'],
                    entropy=content_info['entropy'],
                    magic_bytes=content_info['magic_bytes'],
                    is_binary=content_info['is_binary'],
                    encoding=content_info['encoding'],
                    encrypted=content_info['encrypted'],
                )

                count += 1
                if progress_callback and count % 100 == 0:
                    progress_callback(count, str(filepath))

                yield file_meta

            except PermissionError:
                yield f"Permission denied: {filepath}"
            except OSError as e:
                yield f"OS error for {filepath}: {e}"


def compute_file_hash(filepath: str, algorithm: str = "md5") -> Optional[str]:
    """
    Compute hash of file contents.

    Args:
        filepath: Path to file
        algorithm: Hash algorithm (md5, sha256)

    Returns:
        Hex digest string or None on error
    """
    try:
        hasher = hashlib.new(algorithm)
        with open(filepath, 'rb') as f:
            # Read in chunks for large files
            for chunk in iter(lambda: f.read(8192), b''):
                hasher.update(chunk)
        return hasher.hexdigest()
    except (PermissionError, OSError):
        return None


def get_file_sample(filepath: str, max_bytes: int = 4096) -> Optional[bytes]:
    """
    Read first N bytes of file for content detection.

    Args:
        filepath: Path to file
        max_bytes: Maximum bytes to read

    Returns:
        Bytes content or None on error
    """
    try:
        with open(filepath, 'rb') as f:
            return f.read(max_bytes)
    except (PermissionError, OSError):
        return None


# =============================================================================
# FILE CONTENT ANALYSIS (Sprint 86A datalake + V1.7 encrypted detection)
# =============================================================================

# Magic bytes signatures for encrypted files
ENCRYPTED_SIGNATURES = {
    b'-----BEGIN PGP': 'pgp',           # PGP armored
    b'\x85\x02': 'pgp_binary',          # PGP binary packet
    b'\x8c\x0d': 'gpg',                 # GPG symmetric
    b'Salted__': 'openssl',             # OpenSSL enc
}

# Encoding IDs (compatible with Rust raw_collector.rs)
ENCODING_UNKNOWN = 0
ENCODING_UTF8 = 1
ENCODING_UTF16_LE = 2
ENCODING_UTF16_BE = 3
ENCODING_ASCII = 4
ENCODING_LATIN1 = 5


def analyze_file_content(filepath: str) -> dict:
    """
    Analyze file content for datalake fields. Single 4KB read per file.

    Returns dict with: encrypted, entropy, magic_bytes, is_binary, encoding, content_hash.
    Replaces detect_encrypted() — same logic plus additional fields.
    """
    import math
    from collections import Counter

    result = {
        'encrypted': False,
        'entropy': 0.0,
        'magic_bytes': '',
        'is_binary': False,
        'encoding': ENCODING_UNKNOWN,
        'content_hash': '',
    }

    sample = get_file_sample(filepath, max_bytes=4096)
    if not sample or len(sample) < 8:
        return result

    # Magic bytes: first 4 bytes as hex
    result['magic_bytes'] = sample[:4].hex()

    # Binary detection: null bytes in first 1KB
    check_len = min(len(sample), 1024)
    result['is_binary'] = b'\x00' in sample[:check_len]

    # Encoding detection (compatible with Rust)
    result['encoding'] = _detect_encoding(sample)

    # Shannon entropy (0.0-8.0)
    byte_counts = Counter(sample)
    length = len(sample)
    entropy = -sum(
        (count / length) * math.log2(count / length)
        for count in byte_counts.values()
    )
    result['entropy'] = round(entropy, 4)

    # Encrypted detection (V1.7 logic preserved)
    encrypted = False
    for sig, _type in ENCRYPTED_SIGNATURES.items():
        if sample.startswith(sig):
            encrypted = True
            break
    if not encrypted and sample[:4] == b'PK\x03\x04' and len(sample) > 7:
        flags = sample[6] | (sample[7] << 8)
        if flags & 0x01:
            encrypted = True
    if not encrypted and sample[:5] == b'%PDF-':
        if b'/Encrypt' in sample:
            encrypted = True
    if not encrypted and entropy > 7.5 and len(sample) >= 1024:
        encrypted = True
    result['encrypted'] = encrypted

    # Content hash: SHA256 of first 64KB (separate read for performance)
    result['content_hash'] = compute_content_hash(filepath)

    return result


def compute_content_hash(filepath: str, max_bytes: int = 65536) -> str:
    """SHA256 of first 64KB. Compatible with Rust raw_collector.rs."""
    try:
        h = hashlib.sha256()
        with open(filepath, 'rb') as f:
            data = f.read(max_bytes)
            if data:
                h.update(data)
                return h.hexdigest()
        return ''
    except (PermissionError, OSError):
        return ''


def _detect_encoding(data: bytes) -> int:
    """Detect encoding from BOM or content. Compatible with Rust raw_collector.rs."""
    if len(data) >= 3 and data[:3] == b'\xef\xbb\xbf':
        return ENCODING_UTF8
    if len(data) >= 2:
        if data[:2] == b'\xff\xfe':
            return ENCODING_UTF16_LE
        if data[:2] == b'\xfe\xff':
            return ENCODING_UTF16_BE
    # Check if valid UTF-8
    try:
        data[:1024].decode('utf-8')
        if all(b < 128 for b in data[:1024]):
            return ENCODING_ASCII
        return ENCODING_UTF8
    except UnicodeDecodeError:
        pass
    # High bytes present = likely Latin-1
    if any(b > 127 for b in data[:1024]):
        return ENCODING_LATIN1
    return ENCODING_UNKNOWN


def detect_encrypted(filepath: str) -> bool:
    """Legacy wrapper — calls analyze_file_content for backward compatibility."""
    return analyze_file_content(filepath)['encrypted']


# ============================================================================
# PARALLEL I/O (Added for optimization)
# ============================================================================

import os
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

logger = logging.getLogger(__name__)

IO_WORKERS = min(int(os.getenv('IO_WORKERS', 8)), 16)

def read_files_parallel(file_paths: list) -> dict:
    """Lecture parallèle I/O bound - ThreadPoolExecutor"""
    logger.info(f"[PARALLEL] Lecture {len(file_paths)} fichiers, {IO_WORKERS} workers")
    
    results = {}
    with ThreadPoolExecutor(max_workers=IO_WORKERS) as executor:
        futures = {executor.submit(read_single_file, fp): fp for fp in file_paths}
        for future in as_completed(futures):
            fp = futures[future]
            try:
                content = future.result()
                if content is not None:
                    results[fp] = content
            except Exception as e:
                logger.debug(f"Skip {fp}: {e}")
    
    logger.info(f"[PARALLEL] {len(results)} fichiers lus")
    return results

def read_single_file(filepath: str) -> bytes:
    """Lecture premiers 64KB pour PII"""
    try:
        with open(filepath, 'rb') as f:
            return f.read(65536)
    except Exception as e:
        logger.debug(f"Cannot read {filepath}: {e}")
        return None

