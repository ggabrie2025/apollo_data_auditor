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

        # Convert fingerprints list to dict[path_hash -> fingerprint]
        fp_dict = {}
        for fp in fingerprints:
            if hasattr(fp, 'path_hash'):
                fp_dict[fp.path_hash] = asdict(fp) if hasattr(fp, 'to_dict') else fp.to_dict()
            elif isinstance(fp, dict) and 'path_hash' in fp:
                fp_dict[fp['path_hash']] = fp

        # Call cloud API
        try:
            response = requests.post(
                f"{cloud_url}/api/v1/snapshots",
                headers={"X-API-Key": api_key},
                json={
                    "source_path_hash": source_hash,
                    "source_name": source_name,
                    "fingerprints": fp_dict,
                    "scores": scores
                },
                timeout=30
            )
            response.raise_for_status()
            logger.info(f"[V1.5] Snapshot saved: {source_name} ({len(fp_dict):,} files)")
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
            snapshot = response.json().get("fingerprints", {})

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
