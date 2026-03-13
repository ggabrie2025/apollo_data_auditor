"""
Apollo Agent V1.4 - Database Differential Detection
Detect new/modified/unchanged tables for optimization.

Date: 2025-12-13
"""

import hashlib
from dataclasses import dataclass
from typing import List


@dataclass
class DifferentialResult:
    """Result of differential comparison."""
    new_tables: List[str]
    modified_tables: List[str]
    unchanged_tables: List[str]
    total_tables: int = 0
    tables_to_scan: int = 0
    reduction_percent: float = 0.0


def get_tables_to_scan(
    current_tables: list,
    previous_snapshot: dict
) -> DifferentialResult:
    """Compare current tables with previous snapshot from Hub."""
    new_tables = []
    modified_tables = []
    unchanged_tables = []

    if not previous_snapshot:
        # No previous snapshot - scan all tables
        new_tables = [t.name for t in current_tables]
        return DifferentialResult(
            new_tables=new_tables,
            modified_tables=[],
            unchanged_tables=[],
            total_tables=len(current_tables),
            tables_to_scan=len(current_tables),
            reduction_percent=0.0
        )

    # Build previous fingerprints map
    previous_fps = {}
    for fp in previous_snapshot.get("fingerprints", []):
        key = f"{fp.get('schema', 'public')}.{fp['table_name']}"
        previous_fps[key] = fp

    # Compare each table
    for table in current_tables:
        key = f"{table.schema or 'public'}.{table.name}"
        prev_fp = previous_fps.get(key)

        if not prev_fp:
            new_tables.append(table.name)
        else:
            # Check if modified
            if (table.row_count != prev_fp["row_count"] or
                len(table.columns) != prev_fp["column_count"]):
                modified_tables.append(table.name)
            else:
                # Check column hash
                column_str = "|".join([f"{col['name']}:{col['type']}" for col in table.columns])
                current_hash = hashlib.sha256(column_str.encode()).hexdigest()[:32]

                if current_hash != prev_fp["column_hash"]:
                    modified_tables.append(table.name)
                else:
                    unchanged_tables.append(table.name)

    # Stats
    total = len(current_tables)
    to_scan = len(new_tables) + len(modified_tables)
    reduction = ((total - to_scan) / total * 100) if total > 0 else 0.0

    return DifferentialResult(
        new_tables=new_tables,
        modified_tables=modified_tables,
        unchanged_tables=unchanged_tables,
        total_tables=total,
        tables_to_scan=to_scan,
        reduction_percent=reduction
    )


def should_scan_table(table_name: str, diff_result: DifferentialResult) -> bool:
    """Check if a table should be scanned."""
    return (table_name in diff_result.new_tables or
            table_name in diff_result.modified_tables)
