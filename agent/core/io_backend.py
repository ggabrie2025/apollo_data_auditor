"""
I/O Backend - Auto-select best available method.

SPRINT_61: Rust native acceleration with Python fallback.

Priority:
1. Rust native (Linux/Windows) - +150-200%
2. Python mmap (all platforms) - +80%

Usage:
    from agent.core.io_backend import read_files_parallel, walk_directory, get_backend

    paths = walk_directory("/data", max_depth=10)
    contents = read_files_parallel(paths, max_bytes=65536)
    print(f"Backend: {get_backend()}")
"""

import sys
import os
import logging
from typing import Dict, List, Tuple, Optional

logger = logging.getLogger(__name__)

# Backend detection
_BACKEND: str = "unknown"
_NATIVE = None


def _init_backend():
    """Initialize I/O backend - prefer Rust, fallback to Python."""
    global _BACKEND, _NATIVE

    # macOS: Skip Rust in production, use Python directly
    # (Rust OK for dev/test but excluded from release builds)
    if sys.platform == 'darwin':
        # Try Rust anyway for dev/test
        try:
            import apollo_io_native as native
            _NATIVE = native
            _BACKEND = 'rust-native-dev'
            # get_platform_info may not exist in all versions
            if hasattr(native, 'get_platform_info'):
                info = native.get_platform_info()
                logger.info(f"[I/O] Rust backend (dev): {info['os']}/{info['arch']} via {info['io_method']}")
            else:
                logger.info("[I/O] Rust backend (dev) loaded")
            return
        except ImportError:
            pass
        _BACKEND = 'python-mmap'
        logger.info("[I/O] macOS - using Python mmap backend")
        return

    # Linux/Windows: Try Rust first
    try:
        import apollo_io_native as native
        _NATIVE = native
        _BACKEND = 'rust-native'
        if hasattr(native, 'get_platform_info'):
            info = native.get_platform_info()
            logger.info(f"[I/O] Rust backend: {info['os']}/{info['arch']} via {info['io_method']}")
        else:
            logger.info("[I/O] Rust backend loaded")
    except ImportError:
        _BACKEND = 'python-mmap'
        logger.info("[I/O] Rust module not available, using Python mmap")


# Initialize on module load
_init_backend()


# =============================================================================
# PUBLIC API
# =============================================================================

def read_files_parallel(
    paths: List[str],
    max_bytes: int = 65536,
    workers: int = 8
) -> Dict[str, bytes]:
    """
    Read files with best available backend.

    Args:
        paths: List of file paths to read
        max_bytes: Maximum bytes to read per file (default: 64KB)
        workers: Number of parallel workers (default: 8)

    Returns:
        Dict[path, bytes] - file contents
    """
    if _NATIVE:
        results = _NATIVE.read_files_batch(paths, max_bytes, workers)
        return {p: bytes(c) for p, c in results}
    else:
        return _read_files_python(paths, max_bytes)


def stat_files_parallel(paths: List[str]) -> Dict[str, Tuple[int, float]]:
    """
    Get file stats with best available backend.

    Args:
        paths: List of file paths

    Returns:
        Dict[path, (size, mtime)]
    """
    if _NATIVE:
        results = _NATIVE.stat_files_batch(paths)
        return {p: (s, m) for p, s, m in results}
    else:
        return _stat_files_python(paths)


def walk_directory(
    root: str,
    max_depth: int = 100,
    skip_hidden: bool = True
) -> List[str]:
    """
    Walk directory with best available backend.

    SPRINT_61 OPTIMIZATION: Always use Python os.walk (4.7x faster than Rust).
    PyO3 overhead for returning each path string dominates Rust parallel gains.

    Args:
        root: Root directory path
        max_depth: Maximum recursion depth (default: 100)
        skip_hidden: Skip hidden files/directories (default: True)

    Returns:
        List[path] - all file paths found
    """
    # Always use Python - 4.7x faster than Rust due to PyO3 overhead
    return _walk_directory_python(root, max_depth, skip_hidden)


def get_backend() -> str:
    """Return current I/O backend name."""
    return _BACKEND


def get_platform_info() -> Optional[Dict]:
    """Get platform info from Rust module (if available)."""
    if _NATIVE:
        return dict(_NATIVE.get_platform_info())
    return None


# =============================================================================
# PYTHON FALLBACK IMPLEMENTATIONS
# =============================================================================

def _read_files_python(paths: List[str], max_bytes: int) -> Dict[str, bytes]:
    """Python fallback for file reading."""
    import mmap

    result = {}
    for path in paths:
        try:
            with open(path, 'rb') as f:
                if max_bytes > 0:
                    # Use mmap for efficiency
                    size = os.path.getsize(path)
                    if size > 0:
                        with mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as mm:
                            result[path] = mm[:min(max_bytes, size)]
                    else:
                        result[path] = b''
                else:
                    result[path] = f.read()
        except (OSError, PermissionError):
            pass
    return result


def _stat_files_python(paths: List[str]) -> Dict[str, Tuple[int, float]]:
    """Python fallback for stat."""
    result = {}
    for p in paths:
        try:
            st = os.stat(p)
            result[p] = (st.st_size, st.st_mtime)
        except OSError:
            pass
    return result


def _walk_directory_python(
    root: str,
    max_depth: int,
    skip_hidden: bool
) -> List[str]:
    """Python fallback for directory walking."""
    paths = []
    root_depth = root.rstrip(os.sep).count(os.sep)

    for dirpath, dirnames, filenames in os.walk(root):
        # Check depth
        current_depth = dirpath.count(os.sep) - root_depth
        if current_depth >= max_depth:
            dirnames.clear()  # Don't recurse deeper
            continue

        # Skip hidden directories
        if skip_hidden:
            dirnames[:] = [d for d in dirnames if not d.startswith('.')]

        for filename in filenames:
            # Skip hidden files
            if skip_hidden and filename.startswith('.'):
                continue
            paths.append(os.path.join(dirpath, filename))

    return paths
