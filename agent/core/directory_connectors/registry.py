"""
Directory Connector Registry - Plugin System
=============================================

Pattern decorateur pour enregistrement automatique des connecteurs annuaire.
Meme pattern que db_connectors/registry.py adapte au contexte Directory.

Usage:
    @register_directory_connector
    class LDAPConnector(DirectoryConnector):
        METADATA = {...}
        CAPABILITIES = DirectoryCapabilities.CAN_LIST_USERS | ...

Sprint 87 — G6 Connecteur Active Directory / LDAP
Copyright: (c) 2025-2026 Gilles Gabriel <gilles.gabriel@noos.fr>
"""

from typing import Dict, Type, List, Optional, Any
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


# =============================================================================
# DIRECTORY CONNECTOR SPEC
# =============================================================================

@dataclass
class DirectoryConnectorSpec:
    """
    Specification complete d'un connecteur annuaire enregistre.

    Contient toutes les infos necessaires pour:
    - Autodiscovery (ports, dir_type)
    - Validation (capabilities, requires)
    - Instantiation (connector_class)
    """
    name: str                    # Nom affichage (LDAP, Azure AD, Okta, ...)
    dir_type: str                # Identifiant (ldap, azure_ad, okta, ...)
    connector_class: Type        # Classe du connecteur
    default_port: int            # Port par defaut
    ports_to_scan: List[int]     # Ports pour autodiscovery
    requires: List[str]          # Dependances Python
    capabilities: List[str]      # Capacites supportees

    def to_dict(self) -> Dict[str, Any]:
        """Serialisation pour API."""
        return {
            "name": self.name,
            "dir_type": self.dir_type,
            "default_port": self.default_port,
            "ports_to_scan": self.ports_to_scan,
            "requires": self.requires,
            "capabilities": self.capabilities
        }


# =============================================================================
# DIRECTORY REGISTRY (Singleton)
# =============================================================================

class DirectoryRegistry:
    """
    Registry singleton pour tous les connecteurs annuaire.

    Pattern Plugin: Les connecteurs s'enregistrent via @register_directory_connector.
    """
    _instance: Optional['DirectoryRegistry'] = None
    _connectors: Dict[str, DirectoryConnectorSpec] = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._connectors = {}
        return cls._instance

    def register(self, spec: DirectoryConnectorSpec) -> None:
        """Enregistre un connecteur annuaire."""
        if spec.dir_type in self._connectors:
            logger.warning(f"Directory connector {spec.dir_type} already registered, overwriting")
        self._connectors[spec.dir_type] = spec
        logger.debug(f"Registered directory connector: {spec.name} ({spec.dir_type})")

    def get(self, dir_type: str) -> Optional[DirectoryConnectorSpec]:
        """Recupere spec d'un connecteur par type."""
        return self._connectors.get(dir_type)

    def get_class(self, dir_type: str) -> Optional[Type]:
        """Recupere classe d'un connecteur par type."""
        spec = self.get(dir_type)
        return spec.connector_class if spec else None

    def list_all(self) -> List[DirectoryConnectorSpec]:
        """Liste tous les connecteurs annuaire enregistres."""
        return list(self._connectors.values())

    def list_by_capability(self, capability: str) -> List[DirectoryConnectorSpec]:
        """Liste connecteurs ayant une capacite specifique."""
        return [
            spec for spec in self._connectors.values()
            if capability in spec.capabilities
        ]

    def get_all_ports(self) -> List[Dict[str, Any]]:
        """Retourne tous les ports a scanner pour autodiscovery."""
        ports = []
        for spec in self._connectors.values():
            for port in spec.ports_to_scan:
                ports.append({
                    "dir_type": spec.dir_type,
                    "port": port,
                    "name": f"{spec.name} ({port})"
                })
        return ports

    def get_valid_dir_types(self) -> List[str]:
        """Retourne liste des dir_types valides."""
        return list(self._connectors.keys())

    def is_registered(self, dir_type: str) -> bool:
        """Verifie si un connecteur est enregistre."""
        return dir_type in self._connectors

    def clear(self) -> None:
        """Vide le registry (pour tests)."""
        self._connectors.clear()


# Global registry instance
directory_registry = DirectoryRegistry()


# =============================================================================
# DECORATOR @register_directory_connector
# =============================================================================

def register_directory_connector(cls: Type) -> Type:
    """
    Decorateur pour enregistrer automatiquement un connecteur annuaire.

    Usage:
        @register_directory_connector
        class LDAPConnector(DirectoryConnector):
            METADATA = {
                "dir_type": "ldap",
                "name": "LDAP / Active Directory",
                "default_port": 389,
                "ports_to_scan": [389, 636],
                "requires": ["ldap3"]
            }
            CAPABILITIES = (
                DirectoryCapabilities.CAN_LIST_USERS |
                DirectoryCapabilities.CAN_LIST_GROUPS
            )
    """
    if not hasattr(cls, 'METADATA') or not cls.METADATA:
        logger.warning(f"Directory connector {cls.__name__} has no METADATA, skipping registration")
        return cls

    metadata = cls.METADATA

    required = ['dir_type', 'name', 'default_port', 'ports_to_scan', 'requires']
    missing = [f for f in required if f not in metadata]
    if missing:
        logger.warning(f"Directory connector {cls.__name__} missing METADATA fields: {missing}")
        return cls

    capabilities = []
    if hasattr(cls, 'CAPABILITIES') and cls.CAPABILITIES:
        from .base import DirectoryCapabilities
        capabilities = [cap.name for cap in DirectoryCapabilities if cap in cls.CAPABILITIES]

    spec = DirectoryConnectorSpec(
        name=metadata['name'],
        dir_type=metadata['dir_type'],
        connector_class=cls,
        default_port=metadata['default_port'],
        ports_to_scan=metadata['ports_to_scan'],
        requires=metadata['requires'],
        capabilities=capabilities
    )

    directory_registry.register(spec)

    return cls


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

def get_all_directory_connectors_metadata() -> List[Dict[str, Any]]:
    """Retourne metadata de tous les connecteurs annuaire (pour API)."""
    return [spec.to_dict() for spec in directory_registry.list_all()]


def get_directory_connector_by_type(dir_type: str) -> Optional[Type]:
    """Retourne classe connecteur annuaire par type."""
    return directory_registry.get_class(dir_type)


def get_directory_ports_to_scan() -> List[Dict[str, Any]]:
    """Retourne ports annuaire a scanner pour autodiscovery."""
    return directory_registry.get_all_ports()


def get_valid_dir_types() -> List[str]:
    """Retourne liste des dir_types valides."""
    return directory_registry.get_valid_dir_types()
