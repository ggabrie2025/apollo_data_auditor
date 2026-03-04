#!/usr/bin/env python3
"""
Apollo Agent V1.7.R - Directory CLI Entry Point
================================================

Standalone CLI for LDAP/AD directory scanning.
Exports JSON for Hub Cloud processing (scores=None).

Usage:
    python3 -m agent.main_directory --config dir.json -o result.json

Config JSON format:
    {
        "host": "ldap.example.com",
        "port": 389,
        "bind_dn": "cn=admin,dc=example,dc=com",
        "bind_password": "secret",
        "base_dn": "dc=example,dc=com",
        "use_ssl": false
    }

Sprint 87 — G6 Connecteur Active Directory / LDAP
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
        prog="apollo-agent-directory",
        description="Apollo Data Auditor - Directory (LDAP/AD) Scanner CLI"
    )

    parser.add_argument(
        "--config",
        required=True,
        help="Path to directory config JSON file"
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


async def run_directory_scan(config: dict, output_path: str) -> int:
    """
    Run directory scan and write results to JSON.

    Returns:
        0 if success, 1 if error
    """
    from agent.core.directory_connectors import LDAPConnector

    # Build connector (LDAPConnector takes a config dict)
    connector = LDAPConnector(config)

    try:
        # Collect all data (connect is implicit via _connect())
        logger.info(f"Scanning {config['host']}:{config.get('port', 389)}...")
        result = await connector.collect_all()

        # Build output (same format as Hub expects)
        output = {
            "source_type": "directory",
            "source_subtype": result.get("source_subtype", "ldap"),
            "version": VERSION,
            "timestamp": datetime.now().isoformat(),
            "status": "success",
            "error": None,
            "connection": {
                "host": config['host'],
                "port": config.get('port', 389),
                "base_dn": config.get('base_dn', ''),
                "use_ssl": config.get('use_ssl', False),
            },
            "users_summary": result.get("users_summary", {}),
            "admin_summary": result.get("admin_summary", {}),
            "password_policy": result.get("password_policy", {}),
            "groups_summary": result.get("groups_summary", {}),
            "scores": None,  # CONTRAT INDUSTRIEL: scoring cote Cloud
        }

        users = result.get("users_summary", {})
        logger.info(
            f"Scan complete: {users.get('total', 0)} users, "
            f"{result.get('groups_summary', {}).get('total', 0)} groups"
        )
        exit_code = 0

    except Exception as e:
        logger.exception(f"Directory scan failed: {e}")
        output = {
            "source_type": "directory",
            "source_subtype": "ldap",
            "version": VERSION,
            "timestamp": datetime.now().isoformat(),
            "status": "error",
            "error": "Directory scan failed",
            "connection": {
                "host": config['host'],
                "port": config.get('port', 389),
            },
            "users_summary": {},
            "admin_summary": {},
            "password_policy": {},
            "groups_summary": {},
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
    required_fields = ['host']
    missing = [f for f in required_fields if f not in config]
    if missing:
        logger.error(f"Missing required config fields: {missing}")
        sys.exit(1)

    # Run scan
    exit_code = asyncio.run(run_directory_scan(
        config=config,
        output_path=args.output,
    ))

    sys.exit(exit_code)


if __name__ == '__main__':
    main()
