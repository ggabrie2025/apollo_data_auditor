#!/usr/bin/env python3
"""
Apollo Agent V1.5 - Database CLI Entry Point
=============================================

Standalone CLI for database scanning with PII detection.
Exports JSON for Hub Cloud processing.

Usage:
    python3 -m agent.main_db --config db.json -o result.json
    python3 -m agent.main_db --config db.json -o result.json --no-pii

Version: 1.5.0
Date: 2025-12-17
"""

import argparse
import asyncio
import json
import sys
import logging
from pathlib import Path
from datetime import datetime
from dataclasses import asdict

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

from agent.version import VERSION  # Single source of truth


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        prog="apollo-agent-db",
        description="Apollo Data Auditor - Database Scanner CLI"
    )

    parser.add_argument(
        "--config",
        required=True,
        help="Path to DB config JSON file"
    )
    parser.add_argument(
        "-o", "--output",
        required=True,
        help="Output JSON file path"
    )
    parser.add_argument(
        "--no-pii",
        action="store_true",
        help="Skip PII detection"
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {VERSION}"
    )

    return parser.parse_args()


def table_to_dict(table) -> dict:
    """
    Convert TableMetadata to dict for JSON serialization.

    IMPORTANT: This conversion ensures all fields are properly serialized,
    including nested dataclasses and optional fields.
    """
    return {
        "name": table.name,
        "schema": table.schema,
        "row_count": table.row_count,
        "columns": table.columns,
        "size_bytes": table.size_bytes,
        # PII detection
        "pii_detected": table.pii_detected,
        "pii_types": table.pii_types,
        "pii_columns": table.pii_columns,
        # Structure metadata
        "primary_keys": table.primary_keys,
        "foreign_keys": table.foreign_keys,
        "indexes": table.indexes,
        # Quality metrics
        "null_percentage": table.null_percentage,
        "duplicate_count": table.duplicate_count,
        "completeness_score": table.completeness_score,
        # V1.4 Enhanced metrics
        "last_updated": table.last_updated,
        "orphan_rows": int(table.orphan_rows) if table.orphan_rows is not None else None,
        "idx_scan_count": int(float(table.idx_scan_count)) if table.idx_scan_count is not None else None,  # Fix: convert scientific notation
        "invalid_type_count": int(table.invalid_type_count) if table.invalid_type_count is not None else None,
        # V1.5 Smart sampling
        "zone": table.zone,
        "sample_rate": table.sample_rate,
        "sample_size": table.sample_size,
        # V1.7: Audit datapath fields
        "schema_doc": table.schema_doc,
        "has_audit_columns": table.has_audit_columns,
        # V1.8: Permissions & Encryption
        "encrypted": table.encrypted,
        "grants": table.grants,
        # Sprint 86B Niveau 2: PG stats
        "n_dead_tup": table.n_dead_tup,
        "n_live_tup": table.n_live_tup,
        "seq_scan_count": table.seq_scan_count,
        "last_vacuum": table.last_vacuum,
    }


async def run_database_scan(config: dict, output_path: str, skip_pii: bool = False) -> int:
    """
    Run database scan and write results to JSON.

    Returns:
        0 if success, 1 if error
    """
    # Import here to avoid circular imports and ensure proper module loading
    try:
        from agent.core.db_scanner import DBScanner, DBScanConfig
    except ImportError:
        # Fallback for running from agent directory
        from core.db_scanner import DBScanner, DBScanConfig

    # Build scanner config
    # CORRECTION solution-architect: Use DBScanConfig (not DBScannerConfig)
    scanner_config = DBScanConfig(
        db_type=config['db_type'],
        host=config['host'],
        port=config['port'],
        database=config['database'],
        username=config.get('username', ''),
        password=config.get('password', ''),
        ssl=config.get('ssl', False),
        timeout=config.get('timeout', 30),
        enable_pii=not skip_pii,
        # V1.5: Smart sampling enabled by default
        enable_smart_sampling=config.get('enable_smart_sampling', True),
    )

    # Create scanner
    scanner = DBScanner(scanner_config)

    try:
        # Run scan
        logger.info(f"Starting database scan: {config['db_type']}://{config['host']}/{config['database']}")
        result = await scanner.scan()

        # Check scan status
        if result.status == "error":
            logger.error(f"Scan failed: {result.error}")
            output = {
                "source_type": "databases",
                "version": VERSION,
                "timestamp": datetime.now().isoformat(),
                "status": "error",
                "error": result.error,
                "summary": {
                    "tables_count": 0,
                    "total_rows": 0,
                    "tables_with_pii": 0,
                    "pii_types_found": []
                },
                "tables": []
            }
            exit_code = 1
        else:
            # Build success output
            # CORRECTION solution-architect: Convert TableMetadata -> dict
            output = {
                "source_type": "databases",
                "version": VERSION,
                "scan_id": result.scan_id,
                "timestamp": result.scan_timestamp,
                "status": "success",
                "error": None,
                "connection": {
                    "db_type": result.db_type,
                    "host": result.host,
                    "database": result.database,
                },
                "summary": {
                    "tables_count": result.tables_count,
                    "total_rows": result.total_rows,
                    "total_size_bytes": result.total_size_bytes,
                    "tables_with_pii": result.tables_with_pii,
                    "pii_types_found": result.pii_types_found,
                    # Differential stats
                    "differential_mode": result.differential_mode,
                    "tables_scanned": result.tables_scanned,
                    "tables_skipped": result.tables_skipped,
                    "reduction_percent": result.reduction_percent,
                    # Governance metrics (Sprint 18 - PostgreSQL, MongoDB, MySQL)
                    "governance_metrics": result.governance_metrics,
                },
                "tables": [table_to_dict(t) for t in result.tables],
                "duration_seconds": result.duration_seconds,
                # Lineage metadata (Sprint 21)
                "views": result.views,
                "triggers": result.triggers,
                "procedures": result.procedures,
            }

            logger.info(
                f"Scan complete: {result.tables_count} tables, "
                f"{result.tables_with_pii} with PII, "
                f"duration: {result.duration_seconds:.2f}s"
            )
            exit_code = 0

    except Exception as e:
        logger.exception(f"Unexpected error during scan: {e}")
        output = {
            "source_type": "databases",
            "version": VERSION,
            "timestamp": datetime.now().isoformat(),
            "status": "error",
            "error": str(e),
            "summary": {
                "tables_count": 0,
                "total_rows": 0,
                "tables_with_pii": 0,
                "pii_types_found": []
            },
            "tables": []
        }
        exit_code = 1

    # Write output JSON
    try:
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(output, f, indent=2, default=str)
        logger.info(f"Results written to {output_path}")
    except Exception as e:
        logger.error(f"Failed to write output: {e}")
        # Print to stdout as fallback
        print(json.dumps(output, indent=2, default=str))
        exit_code = 1

    return exit_code


def main():
    """Main CLI entry point."""
    args = parse_args()

    # Read config file
    config_path = Path(args.config)
    if not config_path.exists():
        logger.error(f"Config file not found: {args.config}")
        sys.exit(1)

    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in config file: {e}")
        sys.exit(1)

    # Validate required fields
    required_fields = ['db_type', 'host', 'port', 'database']
    missing = [f for f in required_fields if f not in config]
    if missing:
        logger.error(f"Missing required config fields: {missing}")
        sys.exit(1)

    # Validate db_type - DYNAMIQUE depuis CONNECTOR_REGISTRY (ZERO hardcode)
    try:
        from agent.core.db_connectors import get_valid_db_types
        valid_db_types = get_valid_db_types()
    except ImportError:
        from core.db_connectors import get_valid_db_types
        valid_db_types = get_valid_db_types()

    if config['db_type'] not in valid_db_types:
        logger.error(f"Invalid db_type: {config['db_type']}. Must be one of: {valid_db_types}")
        sys.exit(1)

    # Run scan
    exit_code = asyncio.run(run_database_scan(
        config=config,
        output_path=args.output,
        skip_pii=args.no_pii
    ))

    sys.exit(exit_code)


if __name__ == '__main__':
    main()
