"""
App Connector Registry - Plugin System
========================================
Decorator-based registration for app connectors (ERP/CRM/SaaS).
Same pattern as directory_connectors/registry.py.

Usage:
    @register_app_connector
    class PennylaneConnector(AppConnector):
        METADATA = {...}
        CAPABILITIES = AppCapabilities.CAN_LIST_CUSTOMERS | ...

Copyright: (c) 2025-2026 Gilles Gabriel <gilles.gabriel@noos.fr>
"""

from typing import Dict, Type, List, Optional, Any
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


@dataclass
class AppConnectorSpec:
    name: str
    app_type: str
    category: str
    auth_method: str
    connector_class: Type
    base_url: str
    rate_limit: int
    requires: List[str]
    capabilities: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "app_type": self.app_type,
            "category": self.category,
            "auth_method": self.auth_method,
            "base_url": self.base_url,
            "rate_limit": self.rate_limit,
            "requires": self.requires,
            "capabilities": self.capabilities,
        }


class AppRegistry:
    """Singleton registry for app connectors. Same pattern as DirectoryRegistry."""
    _instance: Optional['AppRegistry'] = None
    _connectors: Dict[str, AppConnectorSpec] = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._connectors = {}
        return cls._instance

    def register(self, spec: AppConnectorSpec) -> None:
        if spec.app_type in self._connectors:
            logger.warning(f"App connector {spec.app_type} already registered, overwriting")
        self._connectors[spec.app_type] = spec
        logger.debug(f"Registered app connector: {spec.name} ({spec.app_type})")

    def get(self, app_type: str) -> Optional[AppConnectorSpec]:
        return self._connectors.get(app_type)

    def get_class(self, app_type: str) -> Optional[Type]:
        spec = self.get(app_type)
        return spec.connector_class if spec else None

    def list_all(self) -> List[AppConnectorSpec]:
        return list(self._connectors.values())

    def list_by_category(self, category: str) -> List[AppConnectorSpec]:
        return [s for s in self._connectors.values() if s.category == category]

    def get_valid_app_types(self) -> List[str]:
        return list(self._connectors.keys())

    def is_registered(self, app_type: str) -> bool:
        return app_type in self._connectors

    def clear(self) -> None:
        self._connectors.clear()


# Global registry instance
app_registry = AppRegistry()


def register_app_connector(cls: Type) -> Type:
    """Decorator to register an app connector class in the global registry."""
    if not hasattr(cls, 'METADATA') or not cls.METADATA:
        logger.warning(f"App connector {cls.__name__} has no METADATA, skipping registration")
        return cls

    metadata = cls.METADATA
    required = ['app_type', 'name', 'category', 'auth_method', 'base_url', 'rate_limit', 'requires']
    missing = [f for f in required if f not in metadata]
    if missing:
        logger.warning(f"App connector {cls.__name__} missing METADATA fields: {missing}")
        return cls

    capabilities = []
    if hasattr(cls, 'CAPABILITIES') and cls.CAPABILITIES:
        from .base import AppCapabilities
        capabilities = [cap.name for cap in AppCapabilities if cap in cls.CAPABILITIES]

    spec = AppConnectorSpec(
        name=metadata['name'],
        app_type=metadata['app_type'],
        category=metadata['category'],
        auth_method=metadata['auth_method'],
        connector_class=cls,
        base_url=metadata['base_url'],
        rate_limit=metadata['rate_limit'],
        requires=metadata['requires'],
        capabilities=capabilities,
    )

    app_registry.register(spec)
    return cls


# ============================================================================
# Convenience functions (same pattern as directory_connectors/registry.py)
# ============================================================================

def get_all_app_connectors_metadata() -> List[Dict[str, Any]]:
    return [spec.to_dict() for spec in app_registry.list_all()]


def get_app_connector_by_type(app_type: str) -> Optional[Type]:
    return app_registry.get_class(app_type)


def get_valid_app_types() -> List[str]:
    return app_registry.get_valid_app_types()
