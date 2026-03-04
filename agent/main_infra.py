#!/usr/bin/env python3
"""
Apollo Agent V1.7.R - Infrastructure Scanner CLI Entry Point
=============================================================

Standalone CLI for server infrastructure scanning.
Exports JSON for Hub Cloud processing (scores=None).

Collects: disks (type, model, SMART), RAID, network speed, backup agents.
ZERO external dependency (uses native OS APIs only).

Usage:
    python3 -m agent.main_infra -o infra_result.json
    python3 -m agent.main_infra -o infra_result.json --source-path /data

Sprint 101 — Server Risk & Infrastructure Scanner
Copyright: (c) 2025-2026 Gilles Gabriel <gilles.gabriel@noos.fr>
"""

import argparse
import json
import sys
import logging
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
        prog="apollo-agent-infra",
        description="Apollo Data Auditor - Infrastructure Scanner CLI"
    )

    parser.add_argument(
        "-o", "--output",
        required=True,
        help="Output JSON file path"
    )
    parser.add_argument(
        "--source-path",
        default=None,
        help="Path to check disk usage for (default: root filesystem)"
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {VERSION}"
    )

    return parser.parse_args()


def run_infra_scan(output_path: str, source_path: str = None) -> int:
    """
    Run infrastructure scan and write results to JSON.

    Returns:
        0 if success, 1 if error
    """
    from agent.core.infra_scanner import scan_infrastructure

    try:
        logger.info("Starting infrastructure scan...")
        infra_data = scan_infrastructure(source_path=source_path)

        # Build output payload (same format as Hub expects)
        output = {
            "source_type": "infra",
            "version": VERSION,
            "timestamp": datetime.now().isoformat(),
            "status": "success",
            "error": None,
            "scores": None,
            "infra_summary": infra_data,
        }

        disks = infra_data.get("disks", [])
        backup = infra_data.get("backup_agents_detected", [])
        logger.info(
            f"Scan complete: {len(disks)} disks, "
            f"RAID={'yes' if infra_data.get('has_raid') else 'no'}, "
            f"network={infra_data.get('network_speed_mbps', '?')} Mbps, "
            f"backup agents={[a['name'] for a in backup] if backup else 'none'}"
        )
        exit_code = 0

    except Exception as e:
        logger.exception(f"Infrastructure scan failed: {e}")
        output = {
            "source_type": "infra",
            "version": VERSION,
            "timestamp": datetime.now().isoformat(),
            "status": "error",
            "error": str(e),
            "scores": None,
            "infra_summary": {},
        }
        exit_code = 1

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

    exit_code = run_infra_scan(
        output_path=args.output,
        source_path=args.source_path,
    )

    sys.exit(exit_code)


if __name__ == '__main__':
    main()
