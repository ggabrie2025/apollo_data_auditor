"""
V1.5 Agent - Snapshot Management (FILES)

Simple wrapper for save/load snapshots to cloud.
Copié depuis backend/src/unstructured/v11/snapshot.py (V1.1)
Adapté pour Agent V1.5

Date: 2025-12-15
Version: 1.5.0
"""

import os
import hashlib
import logging
from typing import Dict, List, Any, Optional
from dataclasses import asdict

logger = logging.getLogger(__name__)


def _get_source_hash(source_path: str) -> str:
    """Generate consistent hash for source path identification."""
    return hashlib.sha256(source_path.encode('utf-8')).hexdigest()


def save_snapshot(
    source_path: str,
    source_name: str,
    fingerprints: List[Any],
    scores: Optional[Dict[str, Any]] = None
) -> bool:
    """
    Save fingerprints snapshot to cloud after audit.

    Args:
        source_path: Original source path (e.g., "/Users/admin/Documents")
        source_name: Anonymized name (e.g., "source_001")
        fingerprints: List of LightFingerprint objects from fingerprint.py
        scores: Optional audit scores to store with snapshot

    Returns:
        True if save successful, False otherwise
    """
    # Import cloud client (shared with backend V1.1)
    try:
        from ..cloud.client import save_snapshot_to_cloud, CloudAPIError
    except ImportError:
        # Fallback: inline HTTP implementation
        import requests
        logger.warning("[V1.5] Cloud client not available - using inline HTTP")

        cloud_url = os.getenv("CLOUD_API_URL") or os.getenv("APOLLO_CLOUD_API_URL")
        api_key = os.getenv("APOLLO_API_KEY") or os.getenv("CLOUD_API_KEY")

        if not cloud_url or not api_key:
            logger.warning("[V1.5] Cloud not configured - snapshot not saved")
            return False

        source_hash = _get_source_hash(source_path)

        # Convert LightFingerprint objects to Hub SnapshotFileModel format
        from datetime import datetime, timezone
        files_list = []
        total_size = 0
        for fp in fingerprints:
            if hasattr(fp, 'path_hash'):
                mtime_dt = datetime.fromtimestamp(fp.mtime, tz=timezone.utc).isoformat()
                files_list.append({
                    "path_hash": fp.path_hash,
                    "size_bytes": fp.size,
                    "mtime": mtime_dt,
                    "extension": fp.extension,
                    "zone": fp.zone,
                    "content_hash_partial": fp.content_hash_partial,
                    "previous_score": fp.previous_score,
                    "previous_pii_detected": fp.previous_pii,
                    "previous_tier": fp.previous_tier,
                })
                total_size += fp.size
            elif isinstance(fp, dict) and 'path_hash' in fp:
                entry = fp.copy()
                if 'size' in entry and 'size_bytes' not in entry:
                    entry['size_bytes'] = entry.pop('size')
                if 'previous_pii' in entry and 'previous_pii_detected' not in entry:
                    entry['previous_pii_detected'] = entry.pop('previous_pii')
                files_list.append(entry)
                total_size += entry.get('size_bytes', 0)

        # POST to Hub /api/v1/snapshots/save
        try:
            response = requests.post(
                f"{cloud_url}/api/v1/snapshots/save",
                headers={"X-API-Key": api_key},
                json={
                    "source_path_hash": source_hash,
                    "source_name": source_name,
                    "total_files": len(files_list),
                    "total_size_bytes": total_size,
                    "files": files_list,
                },
                timeout=30
            )
            response.raise_for_status()
            logger.info(f"[V1.5] Snapshot saved: {source_name} ({len(files_list):,} files)")
            return True
        except Exception as e:
            logger.error(f"[V1.5] Failed to save snapshot: {e}")
            return False

    cloud_url = os.getenv("CLOUD_API_URL") or os.getenv("APOLLO_CLOUD_API_URL")
    api_key = os.getenv("APOLLO_API_KEY") or os.getenv("CLOUD_API_KEY")

    if not cloud_url or not api_key:
        logger.warning("[V1.5] Cloud not configured - snapshot not saved")
        return False

    source_hash = _get_source_hash(source_path)

    # Convert fingerprints list to dict[path_hash -> fingerprint]
    fp_dict = {}
    for fp in fingerprints:
        if hasattr(fp, 'path_hash'):
            fp_dict[fp.path_hash] = fp
        elif isinstance(fp, dict) and 'path_hash' in fp:
            fp_dict[fp['path_hash']] = fp

    try:
        result = save_snapshot_to_cloud(
            cloud_api_url=cloud_url,
            api_key=api_key,
            source_path_hash=source_hash,
            source_name=source_name,
            fingerprints=fp_dict,
            scores=scores
        )
        logger.info(f"[V1.5] Snapshot saved: {source_name} ({len(fp_dict):,} files)")
        return result

    except CloudAPIError as e:
        logger.error(f"[V1.5] Failed to save snapshot: {e}")
        return False
    except Exception as e:
        logger.error(f"[V1.5] Unexpected error saving snapshot: {e}")
        return False


def load_snapshot(source_path: str) -> Optional[Dict[str, Dict]]:
    """
    Load previous snapshot from cloud for differential comparison.

    Args:
        source_path: Original source path

    Returns:
        Dict[path_hash -> fingerprint_dict] or None if no snapshot exists
    """
    # Import cloud client (shared with backend V1.1)
    try:
        from ..cloud.client import load_snapshot_from_cloud, CloudAPIError
    except ImportError:
        # Fallback: inline HTTP implementation
        import requests
        logger.warning("[V1.5] Cloud client not available - using inline HTTP")

        cloud_url = os.getenv("CLOUD_API_URL") or os.getenv("APOLLO_CLOUD_API_URL")
        api_key = os.getenv("APOLLO_API_KEY") or os.getenv("CLOUD_API_KEY")

        if not cloud_url or not api_key:
            logger.info("[V1.5] Cloud not configured - no snapshot available")
            return None

        source_hash = _get_source_hash(source_path)

        # Call cloud API
        try:
            response = requests.get(
                f"{cloud_url}/api/v1/snapshots/{source_hash}",
                headers={"X-API-Key": api_key},
                timeout=30
            )

            if response.status_code == 404:
                logger.info("[V1.5] No previous snapshot - first audit")
                return None

            response.raise_for_status()
            data = response.json()
            files_list = data.get("files", [])
            snapshot = {f["path_hash"]: f for f in files_list if "path_hash" in f}

            if snapshot:
                logger.info(f"[V1.5] Snapshot loaded: {len(snapshot):,} files")
            else:
                logger.info("[V1.5] No previous snapshot - first audit")

            return snapshot

        except Exception as e:
            logger.error(f"[V1.5] Failed to load snapshot: {e}")
            return None

    cloud_url = os.getenv("CLOUD_API_URL") or os.getenv("APOLLO_CLOUD_API_URL")
    api_key = os.getenv("APOLLO_API_KEY") or os.getenv("CLOUD_API_KEY")

    if not cloud_url or not api_key:
        logger.info("[V1.5] Cloud not configured - no snapshot available")
        return None

    source_hash = _get_source_hash(source_path)

    try:
        snapshot = load_snapshot_from_cloud(
            cloud_api_url=cloud_url,
            api_key=api_key,
            source_path_hash=source_hash
        )

        if snapshot:
            logger.info(f"[V1.5] Snapshot loaded: {len(snapshot):,} files")
        else:
            logger.info("[V1.5] No previous snapshot - first audit")

        return snapshot

    except CloudAPIError as e:
        logger.error(f"[V1.5] Failed to load snapshot: {e}")
        return None
    except Exception as e:
        logger.error(f"[V1.5] Unexpected error loading snapshot: {e}")
        return None
