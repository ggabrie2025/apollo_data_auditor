"""
Pennylane App Connector
========================
First AppConnector adapter - scans Pennylane API V2 for PII in accounting entities.

Auth V1: Bearer token (Company API Token, read-only).
Architecture ready for OAuth 2.0 (same API after auth).

Pagination: cursor-based with use_2026_api_changes=true.
Rate limiting: 25 req/5s, proactive slowdown on ratelimit-remaining < 3.

Ref: ~/api_pennylane/OPENAPI_SPEC_NOTES.md
     ~/api_pennylane/ENDPOINTS_GET_INVENTORY.md
     ~/api_pennylane/PIEGES_ET_SOLUTIONS.md

Copyright: (c) 2025-2026 Gilles Gabriel <gilles.gabriel@noos.fr>
"""

import time
import logging
from typing import Dict, Any, List, Optional

import httpx

from .base import AppConnector, AppCapabilities
from .registry import register_app_connector

logger = logging.getLogger(__name__)


# =============================================================================
# KNOWN PII FIELDS — Static mapping per entity type
# =============================================================================
# Ref: ~/api_pennylane/ENDPOINTS_GET_INVENTORY.md

KNOWN_PII_FIELDS = {
    "customers": {
        "name": "name",
        "emails": "email",
        "phone": "phone",
        "billing_iban": "iban",
        "vat_number": "vat",
        "reg_no": "siret",
        "billing_address": "address",
        "delivery_address": "address",
    },
    "suppliers": {
        "name": "name",
        "emails": "email",
        "iban": "iban",
        "vat_number": "vat",
        "reg_no": "siren",
        "postal_address": "address",
    },
    "customer_invoices": {
        "label": "name",
        "filename": "name",
        "pdf_invoice_free_text": "free_text",
    },
    "supplier_invoices": {
        "label": "name",
    },
    "products": {
        "description": "free_text",
    },
    "ledger_entries": {
        "label": "name",
        "ledger_attachment_filename": "name",
    },
    "ledger_entry_lines": {
        "label": "free_text",
    },
    "transactions": {
        "label": "name",
    },
    "bank_accounts": {
        "iban": "iban",
    },
}

# Endpoints to scan (entity_type -> API path)
ENTITY_ENDPOINTS = {
    "customers": "/customers",
    "suppliers": "/suppliers",
    "customer_invoices": "/customer_invoices",
    "supplier_invoices": "/supplier_invoices",
    "products": "/products",
    "ledger_entries": "/ledger_entries",
    "ledger_entry_lines": "/ledger_entry_lines",
    "transactions": "/transactions",
    "bank_accounts": "/bank_accounts",
}


# =============================================================================
# PENNYLANE CONNECTOR
# =============================================================================

@register_app_connector
class PennylaneConnector(AppConnector):
    """Pennylane API V2 connector for PII audit."""

    METADATA = {
        "app_type": "pennylane",
        "name": "Pennylane",
        "category": "accounting",
        "auth_method": "bearer",
        "base_url": "https://app.pennylane.com/api/external/v2",
        "rate_limit": 5,  # Conservative: 25 req / 5s = 5 req/s
        "requires": ["httpx"],
    }

    CAPABILITIES = (
        AppCapabilities.CAN_LIST_CUSTOMERS
        | AppCapabilities.CAN_LIST_SUPPLIERS
        | AppCapabilities.CAN_LIST_INVOICES
        | AppCapabilities.CAN_LIST_PRODUCTS
        | AppCapabilities.CAN_LIST_TRANSACTIONS
        | AppCapabilities.CAN_LIST_LEDGER_ENTRIES
        | AppCapabilities.CAN_SCAN_PII
    )

    # Rate limiting constants (official: 25 req / 5s per token)
    _MIN_DELAY = 0.2          # 1 req / 200ms max
    _SLOWDOWN_THRESHOLD = 3   # Proactive slowdown when remaining < 3

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.api_url = (config.get("api_url") or self.METADATA["base_url"]).rstrip("/")
        self.api_token = config.get("api_token", "")
        self.use_2026_api = config.get("use_2026_api", True)
        self._last_request_time = 0.0
        self._client: Optional[httpx.Client] = None

    # -------------------------------------------------------------------------
    # HTTP Client
    # -------------------------------------------------------------------------

    def _get_client(self) -> httpx.Client:
        """Lazy-init httpx client with auth headers."""
        if self._client is None:
            self._client = httpx.Client(
                base_url=self.api_url,
                headers={
                    "Authorization": f"Bearer {self.api_token}",
                    "Accept": "application/json",
                },
                timeout=self.timeout,
            )
        return self._client

    def _get(self, endpoint: str, params: Dict[str, Any] = None) -> Dict[str, Any]:
        """HTTP GET with rate limiting. Returns parsed JSON."""
        # Enforce minimum delay between requests
        now = time.monotonic()
        elapsed = now - self._last_request_time
        if elapsed < self._MIN_DELAY:
            time.sleep(self._MIN_DELAY - elapsed)

        client = self._get_client()
        response = client.get(endpoint, params=params or {})
        self._last_request_time = time.monotonic()

        # Proactive rate limit slowdown
        remaining = int(response.headers.get("ratelimit-remaining", 25))
        if remaining < self._SLOWDOWN_THRESHOLD:
            logger.info(f"Rate limit low ({remaining} remaining), slowing down")
            time.sleep(1.0)

        # Handle 429 Too Many Requests
        if response.status_code == 429:
            wait = int(response.headers.get("retry-after", 5))
            logger.warning(f"Rate limited (429), waiting {wait}s")
            time.sleep(wait)
            # Retry once
            response = client.get(endpoint, params=params or {})
            self._last_request_time = time.monotonic()

        response.raise_for_status()
        return response.json()

    # -------------------------------------------------------------------------
    # Pagination — cursor-based (2026 API)
    # -------------------------------------------------------------------------

    async def _paginate(self, endpoint: str) -> List[dict]:
        """Cursor-based pagination, limit=100, with 2026 API changes."""
        items = []
        cursor = None
        while True:
            params: Dict[str, Any] = {"limit": 100}
            if self.use_2026_api:
                params["use_2026_api_changes"] = "true"
            if cursor:
                params["cursor"] = cursor
            resp = self._get(endpoint, params)
            items.extend(resp.get("items", []))
            if not resp.get("has_more"):
                break
            cursor = resp.get("next_cursor")
            if not cursor:
                break
        return items

    # -------------------------------------------------------------------------
    # Abstract method implementations
    # -------------------------------------------------------------------------

    async def test_connection(self) -> Dict[str, Any]:
        """Test connection via GET /me. Returns company info + scopes."""
        try:
            data = self._get("/me")
            company = data.get("company", {})
            scopes = data.get("scopes", [])
            return {
                "success": True,
                "company_id": company.get("id"),
                "company_name": company.get("name", ""),
                "scopes": scopes,
                "message": f"Connected to {company.get('name', 'unknown')}",
            }
        except httpx.HTTPStatusError as e:
            return {
                "success": False,
                "error": f"HTTP {e.response.status_code}",
                "message": f"Connection failed: HTTP {e.response.status_code}",
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "message": f"Connection failed: {e}",
            }

    async def list_entities(self) -> List[Dict[str, Any]]:
        """List available entity types by probing each endpoint."""
        entities = []
        for entity_type, endpoint in ENTITY_ENDPOINTS.items():
            try:
                params: Dict[str, Any] = {"limit": 1}
                if self.use_2026_api:
                    params["use_2026_api_changes"] = "true"
                resp = self._get(endpoint, params)
                has_more = resp.get("has_more", False)
                item_count = len(resp.get("items", []))
                pii_fields = list(KNOWN_PII_FIELDS.get(entity_type, {}).keys())
                entities.append({
                    "entity_type": entity_type,
                    "count": item_count if not has_more else -1,  # -1 = more than 1
                    "pii_fields": pii_fields,
                    "endpoint": endpoint,
                })
            except httpx.HTTPStatusError as e:
                if e.response.status_code in (403, 404):
                    logger.info(f"Skipping {entity_type}: HTTP {e.response.status_code}")
                else:
                    logger.warning(f"Error listing {entity_type}: {e}")
            except Exception as e:
                logger.warning(f"Error listing {entity_type}: {e}")
        return entities

    async def scan_entity(self, entity_type: str, sample_size: int = 0) -> Dict[str, Any]:
        """Scan one entity type for PII fields. Returns counters only, ZERO nominative data."""
        endpoint = ENTITY_ENDPOINTS.get(entity_type)
        if not endpoint:
            return {
                "entity_type": entity_type,
                "total_records": 0, "sampled": 0,
                "pii_detected": {}, "pii_density": 0.0,
                "field_inventory": [],
            }

        items = await self._paginate(endpoint)
        known_fields = KNOWN_PII_FIELDS.get(entity_type, {})

        pii_detected: Dict[str, int] = {}
        field_inventory: List[Dict[str, Any]] = []

        for field_name, pii_type in known_fields.items():
            populated = 0
            for item in items:
                value = item.get(field_name)
                if _is_populated(value):
                    populated += 1

            if populated > 0:
                pii_detected[pii_type] = pii_detected.get(pii_type, 0) + populated
                field_inventory.append({
                    "entity": entity_type,
                    "field": field_name,
                    "classification": pii_type,
                    "populated_count": populated,
                    "total_count": len(items),
                })

        total_pii = sum(pii_detected.values())
        total_records = len(items)
        pii_density = round(total_pii / max(total_records, 1), 4)

        return {
            "entity_type": entity_type,
            "total_records": total_records,
            "sampled": total_records,
            "pii_detected": pii_detected,
            "pii_density": pii_density,
            "field_inventory": field_inventory,
        }

    # -------------------------------------------------------------------------
    # Override get_pii_summary to add connection metadata
    # -------------------------------------------------------------------------

    async def get_pii_summary(self) -> Dict[str, Any]:
        """Full scan with Pennylane-specific connection metadata."""
        conn_info = await self.test_connection()
        result = await super().get_pii_summary()

        # Add connection metadata
        result["connection"] = {
            "api_url": self.api_url,
            "company_id": conn_info.get("company_id"),
            "company_name": conn_info.get("company_name", ""),
        }

        return result

    # -------------------------------------------------------------------------
    # Cleanup
    # -------------------------------------------------------------------------

    def close(self):
        """Close HTTP client and clear credentials."""
        if self._client:
            self._client.close()
            self._client = None
        self.api_token = ""

    async def disconnect(self):
        """Async cleanup (calls close)."""
        self.close()
        await super().disconnect()


# =============================================================================
# HELPERS
# =============================================================================

def _is_populated(value: Any) -> bool:
    """Check if a field value is populated (non-null, non-empty)."""
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, list):
        return len(value) > 0
    if isinstance(value, dict):
        return any(v for v in value.values() if v)
    return bool(value)
