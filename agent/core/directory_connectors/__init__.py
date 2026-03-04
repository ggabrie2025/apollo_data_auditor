"""
Apollo Agent V1.7.R - Directory Connectors (Sprint 87 — G6)
============================================================

Architecture Plugin avec Registry et Capabilities.
Meme pattern que db_connectors/ adapte au contexte annuaire (AD, LDAP, Azure AD, Okta...).

Structure:
- base.py: DirectoryConnector ABC + DirectoryCapabilities + DirectoryDependencyError
- registry.py: @register_directory_connector decorator + DirectoryRegistry singleton
- ldap_connector.py: Connecteur LDAP/AD on-prem via ldap3

Usage:
    from agent.core.directory_connectors import directory_registry, LDAPConnector

    # Via registry
    spec = directory_registry.get("ldap")
    connector = spec.connector_class(config)

    # Via import direct
    connector = LDAPConnector(config)

Sprint 87 — G6 Connecteur Active Directory / LDAP
Copyright: (c) 2025-2026 Gilles Gabriel <gilles.gabriel@noos.fr>
"""

# =============================================================================
# BASE CLASSES & TYPES
# =============================================================================
from .base import (
    DirectoryConnector,
    DirectoryDependencyError,
    DirectoryCapabilities
)

# =============================================================================
# REGISTRY & DECORATOR
# =============================================================================
from .registry import (
    directory_registry,
    register_directory_connector,
    DirectoryConnectorSpec,
    DirectoryRegistry,
    # Convenience functions
    get_all_directory_connectors_metadata,
    get_directory_connector_by_type,
    get_directory_ports_to_scan,
    get_valid_dir_types
)

# =============================================================================
# CONNECTORS (imports trigger @register_directory_connector)
# =============================================================================
from .ldap_connector import LDAPConnector


__all__ = [
    # Base
    "DirectoryConnector",
    "DirectoryDependencyError",
    "DirectoryCapabilities",
    # Registry
    "directory_registry",
    "register_directory_connector",
    "DirectoryConnectorSpec",
    "DirectoryRegistry",
    # Convenience
    "get_all_directory_connectors_metadata",
    "get_directory_connector_by_type",
    "get_directory_ports_to_scan",
    "get_valid_dir_types",
    # Connectors
    "LDAPConnector",
]
