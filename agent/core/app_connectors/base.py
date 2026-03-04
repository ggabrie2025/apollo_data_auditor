"""
App Connector Base Class
=========================
Abstract class for all application connectors (ERP, CRM, SaaS).
Pennylane, Sage, HubSpot, Salesforce...

Architecture: Same plugin pattern as directory_connectors (METADATA, Capabilities, Registry).
An AppConnector scans business entities (customers, suppliers, invoices) for PII,
returning aggregated counters only (scores=None).

Ref: ~/apollo-cloud3/SPRINT_89/SPRINT_89_PENNYLANE_CONNECTOR.md

Copyright: (c) 2025-2026 Gilles Gabriel <gilles.gabriel@noos.fr>
"""

from abc import ABC, abstractmethod
from enum import Flag, auto
from typing import Dict, Any, List
import logging

logger = logging.getLogger(__name__)


# =============================================================================
# EXCEPTIONS
# =============================================================================

class AppDependencyError(Exception):
    """
    Raised when system/Python dependencies are missing.
    Contains self-service instructions for resolution.
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

class AppCapabilities(Flag):
    """Flags indicating app connector capabilities."""
    CAN_LIST_CUSTOMERS = auto()
    CAN_LIST_SUPPLIERS = auto()
    CAN_LIST_INVOICES = auto()
    CAN_LIST_PRODUCTS = auto()
    CAN_LIST_TRANSACTIONS = auto()
    CAN_LIST_LEDGER_ENTRIES = auto()
    CAN_SCAN_PII = auto()


# =============================================================================
# APP CONNECTOR ABC
# =============================================================================

class AppConnector(ABC):
    """
    Abstract base class for application connectors (ERP/CRM/SaaS).

    Subclasses MUST define:
        METADATA = {
            "app_type": str,       # "pennylane", "sage", "hubspot"
            "name": str,           # Display name
            "category": str,       # "accounting", "crm", "erp", "hr"
            "auth_method": str,    # "bearer", "oauth2", "api_key"
            "base_url": str,       # Default API base URL
            "rate_limit": int,     # Max requests per second
            "requires": list,      # Python dependencies
        }
        CAPABILITIES = AppCapabilities(0)

    INDUSTRIAL CONTRACT: scores=None. Agent sends aggregated counters,
    ZERO nominative data. Scoring done server-side on Cloud.
    """

    METADATA: Dict[str, Any] = {}
    CAPABILITIES: AppCapabilities = AppCapabilities(0)

    # Keys that must never appear in logs
    _SENSITIVE_KEYS = frozenset({
        "password", "api_token", "api_key", "client_secret",
        "token", "access_token", "private_key", "secret", "credential",
        "bind_password",
    })

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self._sanitized_config = self._sanitize_config(config)
        self.timeout = config.get("timeout", 30)

    def _sanitize_config(self, config: Dict[str, Any]) -> Dict[str, Any]:
        sanitized = config.copy()
        for key in sanitized:
            if key.lower() in self._SENSITIVE_KEYS:
                sanitized[key] = "***REDACTED***"
        return sanitized

    def has_capability(self, capability: AppCapabilities) -> bool:
        return bool(self.CAPABILITIES & capability)

    def get_capabilities_list(self) -> List[str]:
        return [cap.name for cap in AppCapabilities if cap in self.CAPABILITIES]

    # -------------------------------------------------------------------------
    # Abstract methods — each subclass MUST implement
    # -------------------------------------------------------------------------

    @abstractmethod
    async def test_connection(self) -> Dict[str, Any]:
        """Test connection. Returns: {"success": bool, "message": str, ...}"""
        pass

    @abstractmethod
    async def list_entities(self) -> List[Dict[str, Any]]:
        """List available entity types with counts.
        Returns: [{"entity_type": str, "count": int, "pii_fields": [...]}]
        """
        pass

    @abstractmethod
    async def scan_entity(self, entity_type: str, sample_size: int = 100) -> Dict[str, Any]:
        """Scan one entity type for PII. Returns counters only.
        Returns: {
            "entity_type": str, "total_records": int, "sampled": int,
            "pii_detected": {type: count}, "pii_density": float,
            "field_inventory": [...]
        }
        """
        pass

    # -------------------------------------------------------------------------
    # Aggregation — uses abstract methods, can be overridden
    # -------------------------------------------------------------------------

    async def get_pii_summary(self) -> Dict[str, Any]:
        """Full PII scan: all entities. Returns aggregated result, scores=None."""
        entities = await self.list_entities()
        entities_scanned = []
        pii_by_type: Dict[str, int] = {}
        pii_by_entity: Dict[str, int] = {}
        total_records = 0
        total_pii = 0
        field_inventory = []
        financial_exposure = {
            "iban_count": 0,
            "iban_unprotected": 0,
            "bank_data_entities": 0,
        }

        for entity_info in entities:
            entity_type = entity_info["entity_type"]
            scan = await self.scan_entity(entity_type)
            entities_scanned.append(scan)

            entity_pii_total = sum(scan.get("pii_detected", {}).values())
            pii_by_entity[entity_type] = entity_pii_total
            total_records += scan.get("total_records", 0)
            total_pii += entity_pii_total

            for pii_type, count in scan.get("pii_detected", {}).items():
                pii_by_type[pii_type] = pii_by_type.get(pii_type, 0) + count

            field_inventory.extend(scan.get("field_inventory", []))

            # Financial exposure tracking
            iban_count = scan.get("pii_detected", {}).get("iban", 0)
            if iban_count > 0:
                financial_exposure["iban_count"] += iban_count
                financial_exposure["iban_unprotected"] += iban_count
                financial_exposure["bank_data_entities"] += 1

        highest_risk = max(pii_by_entity, key=pii_by_entity.get) if pii_by_entity else None

        return {
            "source_type": "app",
            "source_subtype": self.METADATA.get("app_type", "unknown"),
            "app_summary": {
                "name": self.METADATA.get("name", ""),
                "category": self.METADATA.get("category", ""),
                "entities_count": len(entities),
            },
            "entities_scanned": entities_scanned,
            "pii_summary": {
                "total_entities_scanned": len(entities),
                "total_records": total_records,
                "total_pii_fields": len(field_inventory),
                "total_pii_values": total_pii,
                "pii_by_type": pii_by_type,
                "pii_by_entity": pii_by_entity,
                "highest_risk_entity": highest_risk,
            },
            "financial_exposure": financial_exposure,
            "field_inventory": field_inventory,
            "scores": None,  # INDUSTRIAL CONTRACT
        }

    async def disconnect(self):
        """Cleanup. Override in subclass if needed."""
        self.config = None  # SECURITY: Clear credentials
