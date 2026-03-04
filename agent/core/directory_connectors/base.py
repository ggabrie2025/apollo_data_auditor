"""
Directory Connector Base Class
Abstract class pour tous les connecteurs annuaire (AD, LDAP, Azure AD, Okta...).

Architecture: Meme pattern plugin que db_connectors (METADATA, Capabilities, Registry).
Difference: Un annuaire n'est pas une DB. Les methodes exposent users/groups/policy,
pas schemas/tables/columns.

Sprint 87 — G6 Connecteur Active Directory / LDAP
Copyright: (c) 2025-2026 Gilles Gabriel <gilles.gabriel@noos.fr>
"""

from abc import ABC, abstractmethod
from enum import Flag, auto
from typing import Dict, Any, List, Optional
import logging

logger = logging.getLogger(__name__)


# =============================================================================
# EXCEPTIONS
# =============================================================================

class DirectoryDependencyError(Exception):
    """
    Exception levee quand dependances systeme/Python manquantes.
    Contient instructions self-service pour resolution.
    """

    def __init__(self, message: str, missing: List[str] = None, instructions: str = None):
        self.missing = missing or []
        self.instructions = instructions or ""
        super().__init__(message)

    def __str__(self):
        base = super().__str__()
        if self.instructions:
            return f"{base}\n\nInstructions:\n{self.instructions}"
        return base


# =============================================================================
# CONNECTOR CAPABILITIES
# =============================================================================

class DirectoryCapabilities(Flag):
    """Flags indiquant les capacites d'un connecteur annuaire."""
    CAN_LIST_USERS = auto()
    CAN_LIST_GROUPS = auto()
    CAN_READ_POLICY = auto()
    CAN_READ_ADMINS = auto()
    CAN_READ_SERVICE_ACCOUNTS = auto()


# =============================================================================
# DIRECTORY CONNECTOR ABC
# =============================================================================

class DirectoryConnector(ABC):
    """
    Classe abstraite pour connecteurs annuaire.

    Tous connecteurs doivent implementer:
    - test_connection()
    - get_users_summary()
    - get_groups_summary()
    - get_password_policy()
    - get_admin_summary()

    Chaque sous-classe DOIT definir METADATA:
    METADATA = {
        "dir_type": str,        # Identifiant (ldap, azure_ad, okta)
        "name": str,            # Nom affichage UI
        "default_port": int,    # Port par defaut
        "ports_to_scan": list,  # Ports a scanner pour autodiscovery
        "requires": list        # Dependances Python
    }

    CONTRAT INDUSTRIEL: scores=None. L'agent envoie des compteurs agreges,
    ZERO donnee nominative. Le scoring est fait cote Cloud.
    """

    METADATA: Dict[str, Any] = {}
    CAPABILITIES: DirectoryCapabilities = DirectoryCapabilities(0)

    # Keys that must never appear in logs
    _SENSITIVE_KEYS = frozenset({
        "password", "bind_password", "api_key", "client_secret",
        "token", "access_token", "private_key", "secret", "credential",
    })

    def __init__(self, config: Dict[str, Any]):
        """
        Args:
            config: Configuration connexion (host, port, bind_dn, bind_password, base_dn, use_ssl)

        Raises:
            DirectoryDependencyError: Si dependances manquantes
        """
        self._validate_dependencies()
        self.config = config
        self._sanitized_config = self._sanitize_config(config)
        self.connection = None
        self.timeout = config.get("timeout", 30)

    def _sanitize_config(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Sanitize configuration (remove sensitive data from logs)."""
        sanitized = config.copy()
        for key in sanitized:
            if key.lower() in self._SENSITIVE_KEYS:
                sanitized[key] = "***REDACTED***"
        return sanitized

    def _validate_dependencies(self) -> None:
        """Verifie que toutes les dependances du connecteur sont presentes."""
        if not self.METADATA:
            return
        # Subclasses override this with specific checks
        pass

    def has_capability(self, capability: DirectoryCapabilities) -> bool:
        """Verifie si le connecteur supporte une capacite."""
        return bool(self.CAPABILITIES & capability)

    def get_capabilities_list(self) -> List[str]:
        """Retourne la liste des capacites supportees."""
        return [cap.name for cap in DirectoryCapabilities if cap in self.CAPABILITIES]

    @abstractmethod
    async def test_connection(self) -> Dict[str, Any]:
        """
        Test connexion annuaire.

        Returns:
            {"success": bool, "users_count": int, "message": str, "error": str (opt)}
        """
        pass

    @abstractmethod
    async def get_users_summary(self) -> Dict[str, Any]:
        """
        Compteurs agreges utilisateurs (ZERO donnee nominative).

        Returns:
            {
                "total": int,
                "active": int,
                "dormant_90d": int,
                "service_accounts": int,
                "pwd_no_expire": int,
                "disabled_in_groups": int,
            }
        """
        pass

    @abstractmethod
    async def get_groups_summary(self) -> Dict[str, Any]:
        """
        Compteurs agreges groupes.

        Returns:
            {
                "total": int,
                "empty_groups": int,
                "large_groups_50plus": int,
            }
        """
        pass

    @abstractmethod
    async def get_password_policy(self) -> Dict[str, Any]:
        """
        Politique mot de passe du domaine.

        Returns:
            {
                "min_length": int,
                "history": int,
                "lockout": int,
                "max_age_days": int | None,
            }
        """
        pass

    @abstractmethod
    async def get_admin_summary(self) -> Dict[str, Any]:
        """
        Compteurs agreges comptes privilegies.

        Returns:
            {
                "total_admins": int,
                "admin_ratio": float,
                "admin_groups": List[str],
            }
        """
        pass

    async def collect_all(self) -> Dict[str, Any]:
        """
        Collecte complete pour transmission au Cloud.
        Respecte le contrat: compteurs agreges, scores=None.

        Returns:
            {
                "source_type": "directory",
                "source_subtype": str,  # ldap, azure_ad, etc.
                "users_summary": {...},
                "admin_summary": {...},
                "password_policy": {...},
                "groups_summary": {...},
                "scores": None,
            }
        """
        users = await self.get_users_summary()
        admins = await self.get_admin_summary()
        policy = await self.get_password_policy()
        groups = await self.get_groups_summary()

        return {
            "source_type": "directory",
            "source_subtype": self.METADATA.get("dir_type", "unknown"),
            "users_summary": users,
            "admin_summary": admins,
            "password_policy": policy,
            "groups_summary": groups,
            "scores": None,  # CONTRAT INDUSTRIEL
        }

    async def disconnect(self):
        """Fermeture connexion + nettoyage credentials (ZERO STORAGE)."""
        if self.connection:
            try:
                await self._close_connection()
                logger.info("Directory connection closed")
            except Exception as e:
                logger.error(f"Error closing directory connection: {e}")
            finally:
                self.connection = None
                self.config = None  # SECURITY: Clear credentials

    async def _close_connection(self):
        """Fermeture connexion (implementation specifique)."""
        pass
