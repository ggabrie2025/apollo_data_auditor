"""
Apollo Agent V1.5 - Dependency Checker
=======================================

Vérifie dépendances AVANT scan (runtime, pas install).
Self-service client: message clair + instructions par OS.

Résout: Erreurs cryptiques ODBC/Oracle → Messages clairs + instructions

Date: 2025-12-28
Version: 1.0.0
Sprint: 33 (Phase 4 Dependency Management)
"""

from functools import lru_cache
from typing import Dict, List, Optional, Any
import platform
import logging

logger = logging.getLogger(__name__)


class DependencyChecker:
    """
    Vérifie dépendances système et Python pour chaque connecteur.

    Usage:
        checker = DependencyChecker()
        result = checker.check("sqlserver")
        if not result["ok"]:
            print(result["instructions"])

    Impact:
        - Sans checker: Erreur cryptique [IM002] → ticket support (30min)
        - Avec checker: Message clair + instructions → self-service (0min)
    """

    CONNECTORS: Dict[str, Dict[str, Any]] = {
        "postgresql": {
            "python": ["asyncpg"],
            "system": [],
            "install_cmd": "pip install asyncpg"
        },
        "mysql": {
            "python": ["aiomysql"],
            "system": [],
            "install_cmd": "pip install aiomysql"
        },
        "mongodb": {
            "python": ["motor"],
            "system": [],
            "install_cmd": "pip install motor"
        },
        "sqlserver": {
            "python": ["pyodbc"],
            "system": ["ODBC Driver 18 for SQL Server"],
            "install_cmd": {
                "Darwin": "brew install unixodbc && brew install msodbcsql18",
                "Linux": "curl https://packages.microsoft.com/keys/microsoft.asc | sudo apt-key add - && sudo apt-get update && sudo apt-get install -y msodbcsql18",
                "Windows": "Télécharger ODBC Driver 18 depuis https://learn.microsoft.com/en-us/sql/connect/odbc/download-odbc-driver-for-sql-server"
            }
        },
        "oracle": {
            "python": ["cx_Oracle"],
            "system": ["Oracle Instant Client"],
            "install_cmd": {
                "Darwin": "Voir https://oracle.github.io/odpi/doc/installation.html#macos",
                "Linux": "Voir https://oracle.github.io/odpi/doc/installation.html#linux",
                "Windows": "Télécharger Oracle Instant Client depuis https://www.oracle.com/database/technologies/instant-client.html"
            }
        }
    }

    def check(self, connector_type: str) -> Dict[str, Any]:
        """
        Vérifie les dépendances pour un connecteur.

        Args:
            connector_type: Type de connecteur (postgresql, mysql, mongodb, sqlserver, oracle)

        Returns:
            {"ok": True} si toutes dépendances présentes
            {"ok": False, "missing": [...], "os": "...", "instructions": "..."} sinon
        """
        logger.info(f"Checking dependencies for {connector_type}")

        spec = self.CONNECTORS.get(connector_type)
        if not spec:
            return {"ok": False, "error": f"Unknown connector: {connector_type}"}

        missing: List[str] = []

        # Check Python packages
        for pkg in spec["python"]:
            if not self._check_python_package(pkg):
                missing.append(f"Python: {pkg}")

        # Check system deps (connector-specific)
        if connector_type == "sqlserver":
            odbc_version = self._get_odbc_driver_version()
            if not odbc_version:
                missing.append("System: ODBC Driver 18 for SQL Server")
        elif connector_type == "oracle":
            if not self._check_oracle_client():
                missing.append("System: Oracle Instant Client")

        if missing:
            # Get OS-specific instructions
            os_name = platform.system()
            install_cmd = spec["install_cmd"]
            if isinstance(install_cmd, dict):
                instructions = install_cmd.get(os_name, install_cmd.get("Linux"))
            else:
                instructions = install_cmd

            return {
                "ok": False,
                "connector": connector_type,
                "missing": missing,
                "os": os_name,
                "instructions": instructions
            }

        return {"ok": True, "connector": connector_type}

    def check_all(self) -> Dict[str, Any]:
        """
        Vérifie les dépendances pour tous les connecteurs.

        Returns:
            Dict avec status par connecteur
        """
        results = {}
        for connector_type in self.CONNECTORS.keys():
            results[connector_type] = self.check(connector_type)

        all_ok = all(r.get("ok", False) for r in results.values())
        return {
            "all_ok": all_ok,
            "connectors": results
        }

    def _check_python_package(self, package_name: str) -> bool:
        """Vérifie si un package Python est installé."""
        try:
            __import__(package_name)
            return True
        except ImportError:
            return False

    def _get_odbc_driver_version(self) -> Optional[str]:
        """
        Retourne version ODBC Driver SQL Server ou None.

        Returns:
            Nom du driver (ex: "ODBC Driver 18 for SQL Server") ou None
        """
        try:
            import pyodbc
            drivers = pyodbc.drivers()
            for driver in drivers:
                if "SQL Server" in driver:
                    logger.debug(f"Found ODBC driver: {driver}")
                    return driver
            return None
        except ImportError:
            return None
        except Exception as e:
            logger.warning(f"Error checking ODBC drivers: {e}")
            return None

    def _check_oracle_client(self) -> bool:
        """Vérifie si Oracle Instant Client est installé."""
        try:
            import cx_Oracle
            version = cx_Oracle.clientversion()
            logger.debug(f"Found Oracle client version: {version}")
            return True
        except ImportError:
            return False
        except Exception:
            return False

    def get_connector_status(self, connector_type: str) -> str:
        """
        Retourne status lisible pour UI.

        Returns:
            "ready" | "missing_deps" | "unknown"
        """
        result = self.check(connector_type)
        if result.get("ok"):
            return "ready"
        elif "error" in result:
            return "unknown"
        else:
            return "missing_deps"


# Singleton pour éviter checks répétés
_checker_instance: Optional[DependencyChecker] = None


def get_dependency_checker() -> DependencyChecker:
    """Retourne instance singleton du DependencyChecker."""
    global _checker_instance
    if _checker_instance is None:
        _checker_instance = DependencyChecker()
    return _checker_instance


# Convenience functions
def check_connector_deps(connector_type: str) -> Dict[str, Any]:
    """Shortcut pour vérifier dépendances d'un connecteur."""
    return get_dependency_checker().check(connector_type)


def check_all_deps() -> Dict[str, Any]:
    """Shortcut pour vérifier toutes les dépendances."""
    return get_dependency_checker().check_all()
