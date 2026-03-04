#!/usr/bin/env python3
"""
Apollo Agent V1.7.R - App Connector CLI Entry Point
====================================================

Standalone CLI for ERP/CRM/SaaS application scanning (Pennylane, etc.).
Exports JSON for Hub Cloud processing (scores=None).

Usage:
    python3 -m agent.main_app --config app.json -o result.json

Config JSON format (Pennylane):
    {
        "app_type": "pennylane",
        "api_token": "your_bearer_token",
        "api_url": "https://app.pennylane.com/api/external/v2",
        "use_2026_api": true
    }

Sprint 89 — Pennylane Connector
Copyright: (c) 2025-2026 Gilles Gabriel <gilles.gabriel@noos.fr>
"""

import argparse
import asyncio
import json
import sys
import logging
from pathlib import Path
from datetime import datetime

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

from agent.version import VERSION


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        prog="apollo-agent-app",
        description="Apollo Data Auditor - App Connector (ERP/CRM/SaaS) Scanner CLI"
    )

    parser.add_argument(
        "--config",
        required=True,
        help="Path to app connector config JSON file"
    )
    parser.add_argument(
        "-o", "--output",
        required=True,
        help="Output JSON file path"
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {VERSION}"
    )

    return parser.parse_args()


async def run_app_scan(config: dict, output_path: str) -> int:
    """
    Run app connector scan and write results to JSON.

    Returns:
        0 if success, 1 if error
    """
    from agent.core.app_connectors.registry import get_app_connector_by_type, get_valid_app_types

    app_type = config.get("app_type", "")
    connector_class = get_app_connector_by_type(app_type)

    if connector_class is None:
        valid = get_valid_app_types()
        logger.error(f"Unknown app_type '{app_type}'. Valid types: {valid}")
        return 1

    connector = connector_class(config)

    try:
        # Test connection first
        logger.info(f"Connecting to {app_type}...")
        conn_result = await connector.test_connection()
        if not conn_result.get("success"):
            raise ConnectionError(conn_result.get("message", "Connection failed"))

        logger.info(f"Connected: {conn_result.get('message', '')}")

        # Full PII scan
        logger.info(f"Scanning {app_type} entities for PII...")
        result = await connector.get_pii_summary()

        # Build output (same format as Hub expects)
        output = {
            "source_type": "app",
            "source_subtype": app_type,
            "version": VERSION,
            "timestamp": datetime.now().isoformat(),
            "status": "success",
            "error": None,
            **result,
        }

        pii = result.get("pii_summary", {})
        logger.info(
            f"Scan complete: {pii.get('total_entities_scanned', 0)} entities, "
            f"{pii.get('total_records', 0)} records, "
            f"{pii.get('total_pii_values', 0)} PII values detected"
        )
        exit_code = 0

    except Exception as e:
        logger.exception(f"App scan failed: {e}")
        output = {
            "source_type": "app",
            "source_subtype": app_type,
            "version": VERSION,
            "timestamp": datetime.now().isoformat(),
            "status": "error",
            "error": str(e),
            "entities_scanned": [],
            "pii_summary": {},
            "financial_exposure": {},
            "field_inventory": [],
            "scores": None,
        }
        exit_code = 1

    finally:
        try:
            await connector.disconnect()
        except Exception:
            pass

    # Write output JSON
    try:
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(output, f, indent=2, default=str)
        logger.info(f"Results written to {output_path}")
    except Exception as e:
        logger.error(f"Failed to write output: {e}")
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
    required_fields = ['app_type']
    missing = [f for f in required_fields if f not in config]
    if missing:
        logger.error(f"Missing required config fields: {missing}")
        sys.exit(1)

    # Run scan
    exit_code = asyncio.run(run_app_scan(
        config=config,
        output_path=args.output,
    ))

    sys.exit(exit_code)


if __name__ == '__main__':
    main()
