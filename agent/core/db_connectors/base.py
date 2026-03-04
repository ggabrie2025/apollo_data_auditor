"""
Database Connector Base Class
Abstract class pour tous les connecteurs DB

Architecture modulaire: Chaque connecteur est AUTONOME.
- Vérifie ses propres dépendances au __init__
- L'UI ne sait rien des dépendances (découplé)
"""

from abc import ABC, abstractmethod
from enum import Flag, auto
from typing import Dict, Any, List, Optional
import logging

logger = logging.getLogger(__name__)


# =============================================================================
# EXCEPTIONS
# =============================================================================

class DependencyError(Exception):
    """
    Exception levée quand dépendances système/Python manquantes.

    Contient instructions self-service pour résolution.
    L'UI catch cette exception et affiche le message clair.
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
# CONNECTOR CAPABILITIES (Phase 1 - Industrialisation)
# =============================================================================

class ConnectorCapabilities(Flag):
    """
    Flags indiquant les capacités d'un connecteur.

    Usage:
        class PostgreSQLConnector(DatabaseConnector):
            CAPABILITIES = (
                ConnectorCapabilities.CAN_LIST |
                ConnectorCapabilities.CAN_READ |
                ConnectorCapabilities.CAN_SAMPLE |
                ConnectorCapabilities.CAN_SCAN_PII
            )

    Permet au système de savoir dynamiquement ce qu'un connecteur supporte.
    """
    # Capacités de base
    CAN_LIST = auto()           # Peut lister tables/collections
    CAN_READ = auto()           # Peut lire metadata (colonnes, types)
    CAN_SAMPLE = auto()         # Peut échantillonner données
    CAN_SCAN_PII = auto()       # Peut scanner PII

    # Capacités avancées
    CAN_STREAM = auto()         # Peut streamer résultats (large datasets)
    CAN_INCREMENTAL = auto()    # Supporte scan incrémental
    CAN_DIFFERENTIAL = auto()   # Supporte diff entre scans

    # Capacités spécifiques
    CAN_DETECT_SCHEMA = auto()  # Peut détecter changements schema
    CAN_EXECUTE_QUERY = auto()  # Peut exécuter requêtes custom


class DatabaseConnector(ABC):
    """
    Classe abstraite pour connecteurs database

    Tous connecteurs doivent implémenter:
    - test_connection()
    - is_read_only()
    - validate_permissions()
    - get_schemas()
    - get_tables()
    - get_columns()

    Chaque sous-classe DOIT définir METADATA (autodiscovery dynamique):
    METADATA = {
        "db_type": str,        # Identifiant (postgresql, mysql, sqlserver, mongodb)
        "name": str,           # Nom affichage UI
        "default_port": int,   # Port par défaut
        "ports_to_scan": list, # Ports à scanner pour autodiscovery
        "requires": list       # Dépendances (info only)
    }
    """

    # Métadonnées autodiscovery - À DÉFINIR dans chaque sous-classe
    METADATA: Dict[str, Any] = {}

    # Capacités du connecteur - À DÉFINIR dans chaque sous-classe
    CAPABILITIES: ConnectorCapabilities = ConnectorCapabilities(0)  # Aucune par défaut

    def __init__(self, config: Dict[str, Any]):
        """
        Initialisation connecteur

        Args:
            config: Configuration connexion (host, port, database, username, password, ssl)

        Raises:
            DependencyError: Si dépendances système/Python manquantes
        """
        # ARCHITECTURE MODULAIRE: Le connecteur vérifie SES propres dépendances
        self._validate_dependencies()

        self.config = config  # Stocker config original avec password réel
        self._sanitized_config = self._sanitize_config(config)  # Config sanitizé pour logs
        self.connection = None
        self.timeout = config.get("timeout", 30)  # 30 secondes default

    # Keys that must never appear in logs
    _SENSITIVE_KEYS = frozenset({
        "password", "api_key", "api_secret", "client_secret",
        "token", "access_token", "refresh_token", "bearer_token", "auth_token",
        "private_key", "ssl_cert", "ssl_key", "secret", "credential",
    })

    def _sanitize_config(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Sanitize configuration (remove sensitive data from logs)

        Args:
            config: Raw configuration

        Returns:
            Sanitized config
        """
        sanitized = config.copy()
        for key in sanitized:
            if key.lower() in self._SENSITIVE_KEYS:
                sanitized[key] = "***REDACTED***"
        return sanitized

    def _validate_dependencies(self) -> None:
        """
        Vérifie que toutes les dépendances du connecteur sont présentes.

        ARCHITECTURE MODULAIRE:
        - Chaque connecteur est AUTONOME
        - Il vérifie SES propres dépendances
        - L'UI ne sait rien des dépendances (découplé)

        Raises:
            DependencyError: Si dépendances manquantes, avec instructions self-service
        """
        if not self.METADATA:
            return  # Pas de metadata = pas de check (base class)

        db_type = self.METADATA.get('db_type')
        if not db_type:
            return

        # Import local pour éviter circular import
        try:
            from core.dependency_checker import check_connector_deps
        except ImportError:
            from agent.core.dependency_checker import check_connector_deps

        result = check_connector_deps(db_type)

        if not result.get('ok'):
            missing = result.get('missing', [])
            instructions = result.get('instructions', '')

            raise DependencyError(
                f"Missing dependencies for {self.METADATA.get('name', db_type)}: {', '.join(missing)}",
                missing=missing,
                instructions=instructions
            )

        logger.debug(f"Dependencies OK for {db_type}")

    def has_capability(self, capability: ConnectorCapabilities) -> bool:
        """
        Vérifie si le connecteur supporte une capacité.

        Args:
            capability: Capacité à vérifier

        Returns:
            True si supportée

        Usage:
            if connector.has_capability(ConnectorCapabilities.CAN_SCAN_PII):
                result = await connector.scan_pii()
        """
        return bool(self.CAPABILITIES & capability)

    def get_capabilities_list(self) -> List[str]:
        """
        Retourne la liste des capacités supportées (pour API/UI).

        Returns:
            Liste des noms de capacités: ["CAN_LIST", "CAN_READ", ...]
        """
        return [cap.name for cap in ConnectorCapabilities if cap in self.CAPABILITIES]

    @abstractmethod
    async def test_connection(self) -> Dict[str, Any]:
        """
        Test connexion database

        Returns:
            {
                "success": bool,
                "tables_count": int,
                "message": str,
                "error": str (optionnel si échec)
            }
        """
        pass

    @abstractmethod
    async def is_read_only(self) -> bool:
        """
        Vérification permissions READ-ONLY

        Returns:
            True si read-only, False si write permissions détectées
        """
        pass

    async def validate_permissions(self) -> Dict[str, Any]:
        """
        Validation permissions utilisateur

        INTERDIT: INSERT, UPDATE, DELETE, DROP, CREATE, ALTER, GRANT, REVOKE
        REQUIS: SELECT uniquement

        Returns:
            {
                "status": "ok|warning",
                "message": str,
                "forbidden_permissions": List[str]
            }
        """
        forbidden_permissions = [
            'INSERT', 'UPDATE', 'DELETE', 'DROP',
            'CREATE', 'ALTER', 'GRANT', 'REVOKE'
        ]

        try:
            user_permissions = await self._get_user_permissions()

            found_forbidden = []
            for perm in forbidden_permissions:
                if perm in user_permissions:
                    found_forbidden.append(perm)
                    logger.warning(f"Write permission detected: {perm}")

            if found_forbidden:
                return {
                    "status": "warning",
                    "message": f"Write permissions detected: {', '.join(found_forbidden)}",
                    "forbidden_permissions": found_forbidden
                }

            return {
                "status": "ok",
                "message": "Read-only validated",
                "forbidden_permissions": []
            }

        except Exception as e:
            logger.error(f"Permission validation error: {e}")
            return {
                "status": "error",
                "message": f"Could not validate permissions: {str(e)}",
                "forbidden_permissions": []
            }

    @abstractmethod
    async def _get_user_permissions(self) -> List[str]:
        """
        Récupération permissions utilisateur (implémentation DB-specific)

        Returns:
            Liste permissions (e.g., ['SELECT', 'INSERT'])
        """
        pass

    @abstractmethod
    async def get_schemas(self) -> List[str]:
        """
        Liste tous les schemas de la database

        Returns:
            Liste noms schemas
        """
        pass

    @abstractmethod
    async def get_tables(self, schema: str) -> List[str]:
        """
        Liste toutes les tables d'un schema

        Args:
            schema: Nom du schema

        Returns:
            Liste noms tables
        """
        pass

    @abstractmethod
    async def get_columns(self, schema: str, table: str) -> List[Dict[str, Any]]:
        """
        Description colonnes d'une table

        Args:
            schema: Nom du schema
            table: Nom de la table

        Returns:
            Liste colonnes avec metadata:
            [
                {
                    "name": str,
                    "type": str,
                    "nullable": bool,
                    "default": Any,
                    "primary_key": bool
                }
            ]
        """
        pass

    @abstractmethod
    async def get_primary_keys(self, schema: str, table: str) -> List[str]:
        """
        Récupération clés primaires

        Args:
            schema: Nom du schema
            table: Nom de la table

        Returns:
            Liste noms colonnes clés primaires
        """
        pass

    @abstractmethod
    async def get_foreign_keys(self, schema: str, table: str) -> List[Dict[str, Any]]:
        """
        Récupération clés étrangères

        Args:
            schema: Nom du schema
            table: Nom de la table

        Returns:
            Liste foreign keys:
            [
                {
                    "column": str,
                    "referenced_table": str,
                    "referenced_column": str
                }
            ]
        """
        pass

    @abstractmethod
    async def get_indexes(self, schema: str, table: str) -> List[Dict[str, Any]]:
        """
        Récupération indexes

        Args:
            schema: Nom du schema
            table: Nom de la table

        Returns:
            Liste indexes:
            [
                {
                    "name": str,
                    "columns": List[str],
                    "unique": bool
                }
            ]
        """
        pass

    @abstractmethod
    async def execute_query(self, query: str, *args) -> List[Dict[str, Any]]:
        """
        Execute arbitrary SELECT query (read-only)

        Args:
            query: SQL query string
            *args: Query parameters (for parameterized queries)

        Returns:
            List of row dicts: [{"col1": val1, "col2": val2}, ...]

        Raises:
            Exception: If query fails or contains non-SELECT operations
        """
        pass

    async def disconnect(self):
        """
        Fermeture connexion + nettoyage credentials (ZERO STORAGE)
        """
        if self.connection:
            try:
                await self._close_connection()
                logger.info("Connection closed")
            except Exception as e:
                logger.error(f"Error closing connection: {e}")
            finally:
                self.connection = None
                self.config = None  # 🔒 SECURITY: Clear credentials

    @abstractmethod
    async def _close_connection(self):
        """Fermeture connexion (implémentation DB-specific)"""
        pass
