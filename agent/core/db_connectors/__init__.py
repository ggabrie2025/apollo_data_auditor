"""
Apollo Agent V1.5 - Database Connectors (Phase 1 Industrialisation)
====================================================================

Architecture Plugin avec Registry et Capabilities.

Structure:
- base.py: DatabaseConnector ABC + ConnectorCapabilities + DependencyError
- registry.py: @register_connector decorator + ConnectorRegistry singleton
- validator.py: ConnectorValidator pour health checks
- postgresql.py, mysql.py, mongodb.py, sqlserver.py: Connecteurs

Usage:
    from agent.core.db_connectors import registry, PostgreSQLConnector

    # Via registry
    spec = registry.get("postgresql")
    connector = spec.connector_class(config)

    # Via import direct
    connector = PostgreSQLConnector(config)

Date: 2025-12-13
Updated: 2025-12-28 (Phase 1 Industrialisation)
"""

# =============================================================================
# BASE CLASSES & TYPES
# =============================================================================
from .base import (
    DatabaseConnector,
    DependencyError,
    ConnectorCapabilities
)

# =============================================================================
# REGISTRY & DECORATOR
# =============================================================================
from .registry import (
    registry,
    register_connector,
    ConnectorSpec,
    ConnectorRegistry,
    # Convenience functions (backward compatibility)
    get_all_connectors_metadata,
    get_connector_by_type,
    get_ports_to_scan,
    get_valid_db_types
)

# =============================================================================
# VALIDATOR
# =============================================================================
from .validator import (
    ConnectorValidator,
    ValidationResult,
    HealthReport,
    validate_connection,
    health_check_all
)

# =============================================================================
# CONNECTORS (imports trigger @register_connector)
# =============================================================================
from .postgresql import PostgreSQLConnector
from .mysql import MySQLConnector
from .mongodb import MongoDBConnector
from .sqlserver import SQLServerConnector

# Legacy compatibility
CONNECTOR_CLASSES = [
    PostgreSQLConnector,
    MySQLConnector,
    MongoDBConnector,
    SQLServerConnector,
]


__all__ = [
    # Base
    "DatabaseConnector",
    "DependencyError",
    "ConnectorCapabilities",
    # Registry
    "registry",
    "register_connector",
    "ConnectorSpec",
    "ConnectorRegistry",
    # Validator
    "ConnectorValidator",
    "ValidationResult",
    "HealthReport",
    "validate_connection",
    "health_check_all",
    # Connectors
    "PostgreSQLConnector",
    "MySQLConnector",
    "MongoDBConnector",
    "SQLServerConnector",
    # Legacy
    "CONNECTOR_CLASSES",
    "get_all_connectors_metadata",
    "get_connector_by_type",
    "get_ports_to_scan",
    "get_valid_db_types",
]
