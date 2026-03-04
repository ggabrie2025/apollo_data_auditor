"""
Connector Registry - Plugin System (Phase 1 Industrialisation)
===============================================================

Pattern décorateur pour enregistrement automatique des connecteurs.

Usage:
    @register_connector
    class PostgreSQLConnector(DatabaseConnector):
        METADATA = {...}
        CAPABILITIES = ConnectorCapabilities.CAN_LIST | ...

Le connecteur est automatiquement enregistré au chargement du module.

Date: 2025-12-28
Version: 1.0.0
"""

from typing import Dict, Type, List, Optional, Any
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


# =============================================================================
# CONNECTOR SPEC (Metadata enrichie)
# =============================================================================

@dataclass
class ConnectorSpec:
    """
    Spécification complète d'un connecteur enregistré.

    Contient toutes les infos nécessaires pour:
    - Autodiscovery (ports, db_type)
    - Validation (capabilities, requires)
    - Instantiation (connector_class)
    """
    name: str                    # Nom affichage (PostgreSQL, MySQL, ...)
    db_type: str                 # Identifiant (postgresql, mysql, ...)
    connector_class: Type        # Classe du connecteur
    default_port: int            # Port par défaut
    ports_to_scan: List[int]     # Ports pour autodiscovery
    requires: List[str]          # Dépendances
    capabilities: List[str]      # Capacités supportées

    def to_dict(self) -> Dict[str, Any]:
        """Sérialisation pour API."""
        return {
            "name": self.name,
            "db_type": self.db_type,
            "default_port": self.default_port,
            "ports_to_scan": self.ports_to_scan,
            "requires": self.requires,
            "capabilities": self.capabilities
        }


# =============================================================================
# CONNECTOR REGISTRY (Singleton)
# =============================================================================

class ConnectorRegistry:
    """
    Registry singleton pour tous les connecteurs.

    Pattern Plugin: Les connecteurs s'enregistrent via @register_connector.
    Le registry centralise:
    - Liste des connecteurs disponibles
    - Factory pour instantiation
    - Metadata pour autodiscovery
    """
    _instance: Optional['ConnectorRegistry'] = None
    _connectors: Dict[str, ConnectorSpec] = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._connectors = {}
        return cls._instance

    def register(self, spec: ConnectorSpec) -> None:
        """
        Enregistre un connecteur.

        Args:
            spec: Spécification du connecteur
        """
        if spec.db_type in self._connectors:
            logger.warning(f"Connector {spec.db_type} already registered, overwriting")
        self._connectors[spec.db_type] = spec
        logger.debug(f"Registered connector: {spec.name} ({spec.db_type})")

    def get(self, db_type: str) -> Optional[ConnectorSpec]:
        """
        Récupère spec d'un connecteur par type.

        Args:
            db_type: Type (postgresql, mysql, ...)

        Returns:
            ConnectorSpec ou None
        """
        return self._connectors.get(db_type)

    def get_class(self, db_type: str) -> Optional[Type]:
        """
        Récupère classe d'un connecteur par type.

        Args:
            db_type: Type (postgresql, mysql, ...)

        Returns:
            Classe du connecteur ou None
        """
        spec = self.get(db_type)
        return spec.connector_class if spec else None

    def list_all(self) -> List[ConnectorSpec]:
        """Liste tous les connecteurs enregistrés."""
        return list(self._connectors.values())

    def list_by_capability(self, capability: str) -> List[ConnectorSpec]:
        """
        Liste connecteurs ayant une capacité spécifique.

        Args:
            capability: Nom de capacité (CAN_SCAN_PII, ...)

        Returns:
            Liste des ConnectorSpec
        """
        return [
            spec for spec in self._connectors.values()
            if capability in spec.capabilities
        ]

    def get_all_ports(self) -> List[Dict[str, Any]]:
        """
        Retourne tous les ports à scanner pour autodiscovery.

        Returns:
            Liste de {db_type, port, name}
        """
        ports = []
        for spec in self._connectors.values():
            for port in spec.ports_to_scan:
                ports.append({
                    "db_type": spec.db_type,
                    "port": port,
                    "name": f"{spec.name} ({port})"
                })
        return ports

    def get_valid_db_types(self) -> List[str]:
        """Retourne liste des db_types valides."""
        return list(self._connectors.keys())

    def is_registered(self, db_type: str) -> bool:
        """Vérifie si un connecteur est enregistré."""
        return db_type in self._connectors

    def clear(self) -> None:
        """Vide le registry (pour tests)."""
        self._connectors.clear()


# Global registry instance
registry = ConnectorRegistry()


# =============================================================================
# DECORATOR @register_connector
# =============================================================================

def register_connector(cls: Type) -> Type:
    """
    Décorateur pour enregistrer automatiquement un connecteur.

    Usage:
        @register_connector
        class PostgreSQLConnector(DatabaseConnector):
            METADATA = {
                "db_type": "postgresql",
                "name": "PostgreSQL",
                "default_port": 5432,
                "ports_to_scan": [5432, 5433],
                "requires": ["asyncpg"]
            }
            CAPABILITIES = (
                ConnectorCapabilities.CAN_LIST |
                ConnectorCapabilities.CAN_READ
            )

    Le connecteur est enregistré au chargement du module.
    """
    # Validate METADATA exists
    if not hasattr(cls, 'METADATA') or not cls.METADATA:
        logger.warning(f"Connector {cls.__name__} has no METADATA, skipping registration")
        return cls

    metadata = cls.METADATA

    # Validate required fields
    required = ['db_type', 'name', 'default_port', 'ports_to_scan', 'requires']
    missing = [f for f in required if f not in metadata]
    if missing:
        logger.warning(f"Connector {cls.__name__} missing METADATA fields: {missing}")
        return cls

    # Get capabilities
    capabilities = []
    if hasattr(cls, 'CAPABILITIES') and cls.CAPABILITIES:
        # Import here to avoid circular import
        from .base import ConnectorCapabilities
        capabilities = [cap.name for cap in ConnectorCapabilities if cap in cls.CAPABILITIES]

    # Create spec
    spec = ConnectorSpec(
        name=metadata['name'],
        db_type=metadata['db_type'],
        connector_class=cls,
        default_port=metadata['default_port'],
        ports_to_scan=metadata['ports_to_scan'],
        requires=metadata['requires'],
        capabilities=capabilities
    )

    # Register
    registry.register(spec)

    return cls


# =============================================================================
# CONVENIENCE FUNCTIONS (Backward compatibility)
# =============================================================================

def get_all_connectors_metadata() -> List[Dict[str, Any]]:
    """Retourne metadata de tous les connecteurs (pour API)."""
    return [spec.to_dict() for spec in registry.list_all()]


def get_connector_by_type(db_type: str) -> Optional[Type]:
    """Retourne classe connecteur par type."""
    return registry.get_class(db_type)


def get_ports_to_scan() -> List[Dict[str, Any]]:
    """Retourne ports à scanner pour autodiscovery."""
    return registry.get_all_ports()


def get_valid_db_types() -> List[str]:
    """Retourne liste des db_types valides."""
    return registry.get_valid_db_types()
