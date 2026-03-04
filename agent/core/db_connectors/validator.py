"""
Connector Validator - Health Checks (Phase 1 Industrialisation)
================================================================

Validation des connexions et health checks pour tous les connecteurs.

Usage:
    validator = ConnectorValidator()
    result = await validator.test_connection("postgresql", config)
    report = await validator.run_health_check(configs)

Date: 2025-12-28
Version: 1.0.0
"""

from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field
from datetime import datetime, timezone
import time
import logging
import asyncio

logger = logging.getLogger(__name__)


# =============================================================================
# RESULT DATACLASSES
# =============================================================================

@dataclass
class ValidationResult:
    """Résultat de validation d'une connexion."""
    connector_name: str
    db_type: str
    success: bool
    latency_ms: float
    error: Optional[str] = None
    tables_count: Optional[int] = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> Dict[str, Any]:
        """Sérialisation pour API."""
        return {
            "connector": self.connector_name,
            "db_type": self.db_type,
            "success": self.success,
            "latency_ms": round(self.latency_ms, 2),
            "error": self.error,
            "tables_count": self.tables_count,
            "timestamp": self.timestamp.isoformat()
        }


@dataclass
class HealthReport:
    """Rapport de health check pour tous les connecteurs."""
    total: int
    healthy: int
    unhealthy: int
    results: List[ValidationResult]
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> Dict[str, Any]:
        """Sérialisation pour API."""
        return {
            "total": self.total,
            "healthy": self.healthy,
            "unhealthy": self.unhealthy,
            "health_percentage": round((self.healthy / self.total * 100) if self.total > 0 else 0, 1),
            "results": [r.to_dict() for r in self.results],
            "timestamp": self.timestamp.isoformat()
        }


# =============================================================================
# CONNECTOR VALIDATOR
# =============================================================================

class ConnectorValidator:
    """
    Validateur de connexions database.

    Permet de:
    - Tester une connexion spécifique
    - Exécuter un health check sur plusieurs connexions
    - Mesurer latence et collecter métriques
    """

    def __init__(self, timeout: float = 10.0):
        """
        Args:
            timeout: Timeout en secondes pour les tests de connexion
        """
        self.timeout = timeout

    async def test_connection(
        self,
        db_type: str,
        config: Dict[str, Any]
    ) -> ValidationResult:
        """
        Teste une connexion database.

        Args:
            db_type: Type de connecteur (postgresql, mysql, ...)
            config: Configuration de connexion

        Returns:
            ValidationResult avec success, latency, error
        """
        from .registry import registry
        from .base import DependencyError

        spec = registry.get(db_type)
        if not spec:
            return ValidationResult(
                connector_name="Unknown",
                db_type=db_type,
                success=False,
                latency_ms=0,
                error=f"Unknown connector type: {db_type}"
            )

        start_time = time.time()
        connector = None

        try:
            # Instantiate connector (will check dependencies)
            connector = spec.connector_class(config)

            # Test connection
            result = await asyncio.wait_for(
                connector.test_connection(),
                timeout=self.timeout
            )

            latency = (time.time() - start_time) * 1000

            return ValidationResult(
                connector_name=spec.name,
                db_type=db_type,
                success=result.get("success", False),
                latency_ms=latency,
                tables_count=result.get("tables_count"),
                error=result.get("error")
            )

        except DependencyError as e:
            return ValidationResult(
                connector_name=spec.name,
                db_type=db_type,
                success=False,
                latency_ms=0,
                error=f"Missing dependencies: {', '.join(e.missing)}"
            )

        except asyncio.TimeoutError:
            latency = (time.time() - start_time) * 1000
            return ValidationResult(
                connector_name=spec.name,
                db_type=db_type,
                success=False,
                latency_ms=latency,
                error=f"Connection timeout after {self.timeout}s"
            )

        except Exception as e:
            latency = (time.time() - start_time) * 1000
            logger.error(f"Connection test failed for {db_type}: {e}")
            return ValidationResult(
                connector_name=spec.name,
                db_type=db_type,
                success=False,
                latency_ms=latency,
                error=str(e)
            )

        finally:
            # Cleanup
            if connector:
                try:
                    await connector.disconnect()
                except Exception:
                    pass

    async def run_health_check(
        self,
        configs: Dict[str, Dict[str, Any]]
    ) -> HealthReport:
        """
        Exécute un health check sur plusieurs connexions.

        Args:
            configs: Dict {db_type: config} pour chaque connexion à tester

        Returns:
            HealthReport avec résultats agrégés
        """
        results: List[ValidationResult] = []

        # Run tests in parallel
        tasks = [
            self.test_connection(db_type, config)
            for db_type, config in configs.items()
        ]

        if tasks:
            completed = await asyncio.gather(*tasks, return_exceptions=True)
            for result in completed:
                if isinstance(result, ValidationResult):
                    results.append(result)
                elif isinstance(result, Exception):
                    logger.error(f"Health check task failed: {result}")

        healthy = sum(1 for r in results if r.success)

        return HealthReport(
            total=len(results),
            healthy=healthy,
            unhealthy=len(results) - healthy,
            results=results
        )

    async def quick_check(self, db_type: str, config: Dict[str, Any]) -> bool:
        """
        Check rapide: connexion OK ou non.

        Args:
            db_type: Type de connecteur
            config: Configuration

        Returns:
            True si connexion réussie
        """
        result = await self.test_connection(db_type, config)
        return result.success


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

async def validate_connection(db_type: str, config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Valide une connexion et retourne résultat sérialisé.

    Usage:
        result = await validate_connection("postgresql", config)
        if result["success"]:
            print(f"Connected in {result['latency_ms']}ms")
    """
    validator = ConnectorValidator()
    result = await validator.test_connection(db_type, config)
    return result.to_dict()


async def health_check_all(configs: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    """
    Health check sur toutes les connexions configurées.

    Usage:
        configs = {
            "postgresql": {"host": "localhost", ...},
            "mysql": {"host": "localhost", ...}
        }
        report = await health_check_all(configs)
        print(f"Healthy: {report['healthy']}/{report['total']}")
    """
    validator = ConnectorValidator()
    report = await validator.run_health_check(configs)
    return report.to_dict()
