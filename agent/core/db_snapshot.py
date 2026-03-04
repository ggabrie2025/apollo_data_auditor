"""
Apollo Agent V1.4 - Database Snapshot (Cloud Storage via Hub)
Save/load previous database state to/from Hub Cloud for differential scanning.

Architecture:
- Agent: Request/send snapshots via Hub API
- Hub: Store snapshots centralized (multi-agent, history, dashboard)

API:
- GET /api/v1/hub/snapshots/{source_id} → Load previous
- POST /api/v1/hub/ingest (includes snapshot) → Save new

Date: 2025-12-13
"""

import hashlib
import requests
from dataclasses import dataclass, asdict
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone


@dataclass
class TableFingerprint:
    """Fingerprint of a table for differential detection."""
    table_name: str
    schema: Optional[str]
    row_count: int
    column_count: int
    column_hash: str  # Hash of column names + types
    last_scan: str  # ISO timestamp


def create_table_fingerprint(table) -> TableFingerprint:
    """Create fingerprint for a table."""
    # Hash column names + types
    column_str = "|".join([f"{col['name']}:{col['type']}" for col in table.columns])
    column_hash = hashlib.md5(column_str.encode()).hexdigest()

    return TableFingerprint(
        table_name=table.name,
        schema=table.schema,
        row_count=table.row_count,
        column_count=len(table.columns),
        column_hash=column_hash,
        last_scan=datetime.now(timezone.utc).isoformat()
    )


def create_snapshot_data(
    db_type: str,
    host: str,
    database: str,
    tables: list  # List[TableMetadata]
) -> Dict[str, Any]:
    """Create snapshot data structure for Hub storage."""
    fingerprints = [asdict(create_table_fingerprint(t)) for t in tables]

    snapshot = {
        "db_type": db_type,
        "host": host,
        "database": database,
        "snapshot_timestamp": datetime.now(timezone.utc).isoformat(),
        "tables_count": len(tables),
        "fingerprints": fingerprints
    }

    return snapshot


def load_snapshot_from_hub(
    hub_url: str,
    api_key: str,
    source_id: str
) -> Optional[Dict[str, Any]]:
    """Load previous snapshot from Hub Cloud."""
    try:
        url = f"{hub_url}/api/v1/hub/snapshots/{source_id}"
        headers = {"X-API-Key": api_key}

        response = requests.get(url, headers=headers, timeout=10)

        if response.status_code == 404:
            # No previous snapshot (first scan)
            return None

        if response.status_code != 200:
            print(f"⚠️  Failed to load snapshot from Hub: {response.status_code}")
            return None

        return response.json()

    except Exception as e:
        print(f"⚠️  Error loading snapshot from Hub: {e}")
        return None


def get_source_id(db_type: str, host: str, database: str) -> str:
    """Generate unique source ID for a database."""
    source_str = f"{db_type}_{host}_{database}"
    return hashlib.md5(source_str.encode()).hexdigest()[:16]
