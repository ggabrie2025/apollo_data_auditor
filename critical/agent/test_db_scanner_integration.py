"""
Tests DB Scanner Integration
=============================

Tests d'intégration pour agent/core/db_scanner.py
Requiert les bases de données locales actives.

Credentials:
- PostgreSQL 5433: db_postgres1 / apollo_user / apollo_pass_2025
- MySQL 3307: apollo_test / apollo_user / apollo_pass_2025

(c) 2025 Gilles Gabriel - gilles.gabriel@noos.fr
"""

import pytest
import asyncio
import socket

from agent.core.db_scanner import (
    DBScanner,
    DBScanConfig,
    DBScanResult,
    TableMetadata,
    scan_database,
)


# =============================================================================
# SKIP MARKERS
# =============================================================================

def is_port_open(host: str, port: int) -> bool:
    """Check if port is open."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1)
        result = sock.connect_ex((host, port))
        sock.close()
        return result == 0
    except:
        return False

PG_AVAILABLE = is_port_open("localhost", 5433)
MYSQL_AVAILABLE = is_port_open("localhost", 3307)

skip_if_no_pg = pytest.mark.skipif(not PG_AVAILABLE, reason="PostgreSQL not available")
skip_if_no_mysql = pytest.mark.skipif(not MYSQL_AVAILABLE, reason="MySQL not available")


# =============================================================================
# CONFIG
# =============================================================================

PG_CONFIG = DBScanConfig(
    db_type="postgresql",
    host="localhost",
    port=5433,
    database="db_postgres1",
    username="apollo_user",
    password="apollo_pass_2025"
)

MYSQL_CONFIG = DBScanConfig(
    db_type="mysql",
    host="localhost",
    port=3307,
    database="apollo_test",
    username="apollo_user",
    password="apollo_pass_2025"
)


# =============================================================================
# DATACLASS TESTS
# =============================================================================

class TestDBScanConfig:
    """Test DBScanConfig dataclass."""

    def test_config_creation(self):
        """Create DBScanConfig."""
        config = DBScanConfig(
            db_type="postgresql",
            host="localhost",
            port=5432,
            database="test",
            username="user",
            password="pass"
        )
        assert config.db_type == "postgresql"
        assert config.host == "localhost"

    def test_config_defaults(self):
        """Config has sensible defaults."""
        config = DBScanConfig(
            db_type="mysql",
            host="localhost",
            port=3306,
            database="test",
            username="user",
            password="pass"
        )
        assert config.ssl is False
        assert config.timeout == 60  # Sprint 142B: raised from 30 for beta (VPN latency)
        assert config.enable_pii is True
        assert config.sample_rows == 100


class TestTableMetadata:
    """Test TableMetadata dataclass."""

    def test_metadata_creation(self):
        """Create TableMetadata."""
        meta = TableMetadata(name="users")
        assert meta.name == "users"
        assert meta.row_count == 0
        assert meta.pii_detected is False

    def test_metadata_with_pii(self):
        """Create metadata with PII info."""
        meta = TableMetadata(
            name="customers",
            row_count=1000,
            pii_detected=True,
            pii_types=["email", "phone_fr"],
            pii_columns=["email", "telephone"]
        )
        assert meta.pii_detected is True
        assert "email" in meta.pii_types


class TestDBScanResult:
    """Test DBScanResult dataclass."""

    def test_result_creation(self):
        """Create DBScanResult."""
        result = DBScanResult(
            scan_id="test-123",
            db_type="postgresql",
            host="localhost",
            database="testdb",
            scan_timestamp="2025-01-08T12:00:00Z"
        )
        assert result.db_type == "postgresql"
        assert result.database == "testdb"
        assert result.tables_count == 0


# =============================================================================
# DATABASE SCANNER TESTS
# =============================================================================

class TestDBScanner:
    """Test DBScanner class."""

    def test_scanner_creation(self):
        """Create DBScanner instance."""
        scanner = DBScanner(PG_CONFIG)
        assert scanner is not None
        assert scanner.config == PG_CONFIG

    @skip_if_no_pg
    def test_scan_postgresql(self):
        """Scan PostgreSQL database."""
        async def _test():
            scanner = DBScanner(PG_CONFIG)
            result = await scanner.scan()
            assert result is not None
            assert isinstance(result, DBScanResult)
            assert result.db_type == "postgresql"
        asyncio.run(_test())

    @skip_if_no_mysql
    def test_scan_mysql(self):
        """Scan MySQL database."""
        async def _test():
            scanner = DBScanner(MYSQL_CONFIG)
            result = await scanner.scan()
            assert result is not None
            assert isinstance(result, DBScanResult)
            assert result.db_type == "mysql"
        asyncio.run(_test())


# =============================================================================
# SCAN DATABASE FUNCTION TESTS
# =============================================================================

class TestScanDatabaseFunction:
    """Test scan_database function."""

    @skip_if_no_pg
    def test_scan_database_pg(self):
        """Scan PostgreSQL with function."""
        async def _test():
            result = await scan_database(PG_CONFIG)
            assert result is not None
            assert isinstance(result, DBScanResult)
        asyncio.run(_test())

    @skip_if_no_mysql
    def test_scan_database_mysql(self):
        """Scan MySQL with function."""
        async def _test():
            result = await scan_database(MYSQL_CONFIG)
            assert result is not None
            assert isinstance(result, DBScanResult)
        asyncio.run(_test())

