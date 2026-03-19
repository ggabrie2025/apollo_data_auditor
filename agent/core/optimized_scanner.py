"""
Apollo Agent - Optimized Scanner (Hybrid Architecture)
=======================================================

Pipeline optimisé:
1. Fingerprint + Dedup (Bloom filter O(1))
2. Sampling (SmartSampler)
3. Lecture parallèle (ThreadPool - I/O bound)
4. Scan PII parallèle (ProcessPool - CPU bound, bypass GIL)

Date: 2026-01-04
Version: 1.6.1-optimized
"""

import os
import sys
import logging
import hashlib
from pathlib import Path
from typing import List, Dict, Optional
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor, as_completed
from multiprocessing import cpu_count
import re

logger = logging.getLogger(__name__)

try:
    from agent.core.pii_scanner import PII_VALIDATORS, PII_PATTERNS as _PII_PATTERNS_STR
except ImportError:
    try:
        from core.pii_scanner import PII_VALIDATORS, PII_PATTERNS as _PII_PATTERNS_STR
    except ImportError:
        PII_VALIDATORS = {}
        _PII_PATTERNS_STR = {}

# ============================================================================
# CONFIGURATION
# ============================================================================

IO_WORKERS = min(int(os.getenv('IO_WORKERS', 8)), 16)
CPU_WORKERS = min(int(os.getenv('CPU_WORKERS', 4)), cpu_count() or 4)

# ============================================================================
# BLOOM FILTER (O(1) dedup)
# ============================================================================

try:
    from pybloom_live import BloomFilter
    BLOOM_AVAILABLE = True
except ImportError:
    BLOOM_AVAILABLE = False
    logger.warning("[OPT] pybloom_live not available, using set() for dedup")

# ============================================================================
# PARALLEL I/O (ThreadPool)
# ============================================================================

def read_single_file(filepath: str) -> tuple:
    """Read first 64KB of file for PII scanning"""
    try:
        with open(filepath, 'rb') as f:
            return (filepath, f.read(65536))
    except Exception as e:
        logger.debug(f"Cannot read {filepath}: {e}")
        return (filepath, None)

def read_files_parallel(file_paths: List[str]) -> Dict[str, bytes]:
    """Parallel file reading with ThreadPoolExecutor"""
    logger.info(f"[I/O] Reading {len(file_paths)} files with {IO_WORKERS} workers")
    
    results = {}
    with ThreadPoolExecutor(max_workers=IO_WORKERS) as executor:
        futures = [executor.submit(read_single_file, fp) for fp in file_paths]
        for future in as_completed(futures):
            try:
                filepath, content = future.result()
                if content is not None:
                    results[filepath] = content
            except Exception as e:
                logger.debug(f"Read error: {e}")
    
    logger.info(f"[I/O] Read {len(results)} files successfully")
    return results

# ============================================================================
# PARALLEL PII SCAN (ProcessPool - bypasses GIL)
# ============================================================================

def _derive_bytes_patterns(str_patterns: dict) -> dict:
    """
    Derive bytes PII_PATTERNS from the canonical string PII_PATTERNS.
    Preserves all flags (IGNORECASE, MULTILINE, etc.).
    Called once at module load.
    """
    derived = {}
    for key, compiled in str_patterns.items():
        try:
            derived[key] = re.compile(
                compiled.pattern.encode('utf-8'),
                compiled.flags & ~re.UNICODE
            )
        except Exception as e:
            logger.warning(f"[PII] Cannot derive bytes pattern for '{key}': {e}")
    return derived


PII_PATTERNS = _derive_bytes_patterns(_PII_PATTERNS_STR) if _PII_PATTERNS_STR else {}

def scan_pii_content(content: bytes) -> List[Dict]:
    """Scan content for PII patterns with deduplication by value"""
    found = []
    seen_values = set()

    for pii_type, pattern in PII_PATTERNS.items():
        matches = pattern.findall(content)
        if matches:
            validator = PII_VALIDATORS.get(pii_type)
            if validator is not None:
                matches = [m for m in matches if validator(m.decode('latin-1', errors='replace'))]

            # Deduplicate: filter out values we've already seen
            new_matches = [m for m in matches if m not in seen_values]
            seen_values.update(matches)

            # Count includes deduplicated matches, but type appears in output even if count=0
            if matches:
                found.append({'type': pii_type, 'count': len(new_matches)})

    return found

def scan_pii_chunk(chunk: List[tuple]) -> Dict[str, List]:
    """Scan PII on a chunk (runs in separate process)"""
    results = {}
    for filepath, content in chunk:
        if content:
            results[filepath] = scan_pii_content(content)
    return results

def scan_pii_parallel(file_contents: Dict[str, bytes]) -> Dict[str, List]:
    """Parallel PII scanning with ProcessPoolExecutor"""
    if not file_contents:
        return {}

    # PyInstaller frozen exe: ProcessPool workers re-exec the exe and crash
    # Fall back to sequential scanning in frozen mode
    if getattr(sys, 'frozen', False):
        logger.info(f"[CPU] Frozen exe detected, using sequential scan for {len(file_contents)} files")
        results = {}
        for filepath, content in file_contents.items():
            if content:
                results[filepath] = scan_pii_content(content)
        pii_count = sum(1 for r in results.values() if r)
        logger.info(f"[CPU] Found PII in {pii_count}/{len(results)} files")
        return results

    logger.info(f"[CPU] Scanning PII in {len(file_contents)} files with {CPU_WORKERS} workers")

    items = list(file_contents.items())
    chunk_size = max(1, len(items) // (CPU_WORKERS * 4))
    chunks = [items[i:i + chunk_size] for i in range(0, len(items), chunk_size)]

    results = {}
    try:
        with ProcessPoolExecutor(max_workers=CPU_WORKERS) as executor:
            futures = [executor.submit(scan_pii_chunk, chunk) for chunk in chunks]
            for future in as_completed(futures):
                try:
                    chunk_results = future.result(timeout=300)
                    results.update(chunk_results)
                except Exception as e:
                    logger.error(f"[CPU] Chunk error: {e}")
    except Exception as e:
        logger.error(f"[CPU] ProcessPool error, fallback sequential: {e}")
        for filepath, content in items:
            if content:
                results[filepath] = scan_pii_content(content)
    
    pii_count = sum(1 for r in results.values() if r)
    logger.info(f"[CPU] Found PII in {pii_count}/{len(results)} files")
    return results

