"""
Apollo Agent V1.7.R - App Connectors (ERP/CRM/SaaS)
=====================================================
Plugin architecture with Registry and Capabilities.
Same pattern as directory_connectors/ adapted for business applications.

Structure:
- base.py: AppConnector ABC + AppCapabilities + AppDependencyError
- registry.py: @register_app_connector decorator + AppRegistry singleton
- pennylane_connector.py: Pennylane Company API V2

Ref: ~/apollo-cloud3/SPRINT_89/SPRINT_89_PENNYLANE_CONNECTOR.md

Copyright: (c) 2025-2026 Gilles Gabriel <gilles.gabriel@noos.fr>
"""

from .base import (
    AppConnector,
    AppDependencyError,
    AppCapabilities,
)

from .registry import (
    app_registry,
    register_app_connector,
    AppConnectorSpec,
    AppRegistry,
    get_all_app_connectors_metadata,
    get_app_connector_by_type,
    get_valid_app_types,
)

from .pennylane_connector import PennylaneConnector

__all__ = [
    # Base
    "AppConnector",
    "AppDependencyError",
    "AppCapabilities",
    # Registry
    "app_registry",
    "register_app_connector",
    "AppConnectorSpec",
    "AppRegistry",
    # Convenience
    "get_all_app_connectors_metadata",
    "get_app_connector_by_type",
    "get_valid_app_types",
    # Connectors
    "PennylaneConnector",
]
