"""
V1.5 Agent - Differential Audit Logic (FILES)

Comportement unique:
- Premier audit → scan tout
- Re-audit → scan uniquement new/modified

Copié depuis backend/src/unstructured/v11/differential.py (V1.1)
Adapté pour Agent V1.5 (sans scoring/LLM)

Date: 2025-12-15
Version: 1.5.0
"""

import logging
from typing import List, Dict, Any, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)

try:
    from .fingerprint import LightFingerprint, compare_fingerprints
except ImportError:
    # For standalone testing
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from core.fingerprint import LightFingerprint, compare_fingerprints


@dataclass
class DifferentialResult:
    """Result of differential analysis."""
    files_to_scan: List[Any]      # Files that need scanning (new + modified)
    files_unchanged: List[Any]    # Files unchanged (reuse previous scores)
    files_deleted: List[Any]      # Files deleted since last audit
    is_first_audit: bool          # True if no previous snapshot
    stats: Dict[str, int]         # Counts for logging


def get_files_to_scan(
    current_fingerprints: List[Any],
    previous_snapshot: Optional[Dict[str, Dict]]
) -> DifferentialResult:
    """
    Determine which files need scanning based on differential comparison.

    Comportement:
    - Si previous_snapshot is None → premier audit, scan tout
    - Sinon → compare et retourne uniquement new + modified

    Args:
        current_fingerprints: List of LightFingerprint from current scan
        previous_snapshot: Dict[path_hash -> fp_dict] from load_snapshot() or None

    Returns:
        DifferentialResult with files_to_scan and files_unchanged
    """
    # Premier audit - scan tout
    if previous_snapshot is None:
        logger.info("[V1.5] First audit - scanning all files")
        return DifferentialResult(
            files_to_scan=current_fingerprints,
            files_unchanged=[],
            files_deleted=[],
            is_first_audit=True,
            stats={
                "total": len(current_fingerprints),
                "new": len(current_fingerprints),
                "modified": 0,
                "unchanged": 0,
                "deleted": 0
            }
        )

    # Re-audit - comparaison différentielle
    from datetime import datetime

    # Convert current list to dict
    current_dict = {}
    for fp in current_fingerprints:
        if hasattr(fp, 'path_hash'):
            current_dict[fp.path_hash] = fp
        elif isinstance(fp, dict) and 'path_hash' in fp:
            current_dict[fp['path_hash']] = fp

    # Convert previous snapshot to LightFingerprint-like objects
    def parse_mtime(mtime_val):
        """Convert mtime to float timestamp (handles ISO string from cloud)."""
        if isinstance(mtime_val, (int, float)):
            return float(mtime_val)
        if isinstance(mtime_val, str):
            try:
                # ISO format from cloud: "2025-12-09T00:00:00Z"
                dt = datetime.fromisoformat(mtime_val.replace('Z', '+00:00'))
                return dt.timestamp()
            except Exception:
                return 0.0
        return 0.0

    previous_dict = {}
    for path_hash, fp_data in previous_snapshot.items():
        if isinstance(fp_data, dict):
            previous_dict[path_hash] = LightFingerprint(
                path_hash=fp_data.get('path_hash', path_hash),
                size=fp_data.get('size', 0),
                mtime=parse_mtime(fp_data.get('mtime', 0)),
                extension=fp_data.get('extension', ''),
                zone=fp_data.get('zone', 'normal'),
                previous_score=fp_data.get('previous_score'),
                previous_pii=fp_data.get('previous_pii'),
                previous_tier=fp_data.get('previous_tier')
            )
        else:
            previous_dict[path_hash] = fp_data

    # Compare
    diff = compare_fingerprints(current_dict, previous_dict)

    files_to_scan = diff["new"] + diff["modified"]
    files_unchanged = diff["unchanged"]
    files_deleted = diff["deleted"]

    stats = {
        "total": len(current_fingerprints),
        "new": len(diff["new"]),
        "modified": len(diff["modified"]),
        "unchanged": len(files_unchanged),
        "deleted": len(files_deleted)
    }

    logger.info(
        f"[V1.5] Differential: {stats['new']} new, {stats['modified']} modified, "
        f"{stats['unchanged']} unchanged, {stats['deleted']} deleted"
    )
    logger.info(
        f"[V1.5] Scanning {len(files_to_scan)}/{stats['total']} files "
        f"({len(files_to_scan)/stats['total']*100:.1f}%)"
    )

    return DifferentialResult(
        files_to_scan=files_to_scan,
        files_unchanged=files_unchanged,
        files_deleted=files_deleted,
        is_first_audit=False,
        stats=stats
    )


def merge_results(
    new_results: Dict[str, Any],
    unchanged_fingerprints: List[Any]
) -> Dict[str, Any]:
    """
    Merge new scan results with unchanged file scores from previous audit.

    Args:
        new_results: Results from scanning new/modified files
        unchanged_fingerprints: LightFingerprints with previous_score populated

    Returns:
        Merged results dict
    """
    # For unchanged files, we reuse their previous scores
    unchanged_count = 0
    unchanged_with_pii = 0

    for fp in unchanged_fingerprints:
        if hasattr(fp, 'previous_pii') and fp.previous_pii:
            unchanged_with_pii += 1
        unchanged_count += 1

    # Add unchanged stats to results
    if "differential_stats" not in new_results:
        new_results["differential_stats"] = {}

    new_results["differential_stats"]["unchanged_files"] = unchanged_count
    new_results["differential_stats"]["unchanged_with_pii"] = unchanged_with_pii

    return new_results
