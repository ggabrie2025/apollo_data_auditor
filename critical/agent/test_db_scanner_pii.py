"""
Tests KI-103: db_scanner._detect_pii() — no double-counting per cell value.

Validates that the `break` fix (Option B) prevents a single cell value
from being classified under multiple overlapping PII types.

(c) 2025-2026 Gilles Gabriel - gilles.gabriel@noos.fr
"""

import asyncio
import unittest
from dataclasses import dataclass, field
from typing import List
from unittest.mock import MagicMock


@dataclass
class _TableMeta:
    name: str = "test_table"
    schema: str = "public"
    columns: list = field(default_factory=list)
    pii_detected: bool = False
    pii_types: List[str] = field(default_factory=list)
    pii_columns: List[str] = field(default_factory=list)


def _make_scanner(sample_data):
    """Build a minimal DbScanner with _detect_pii wired to fake sample data."""
    from agent.core.db_scanner import DBScanner as DbScanner
    from agent.core.pii_scanner import PII_PATTERNS

    cfg = MagicMock()
    cfg.sample_rows = 5
    cfg.enable_pii = True
    cfg.db_type = "mysql"

    scanner = DbScanner.__new__(DbScanner)
    scanner.config = cfg
    scanner.pii_patterns = PII_PATTERNS

    async def fake_get_sample(table):
        return sample_data

    scanner._get_sample_data = fake_get_sample
    return scanner


class TestDbScannerPiiDedup(unittest.TestCase):

    def test_french_iban_no_double_count(self):
        """KI-103: French IBAN must produce only 'iban', not 'iban' + 'iban_fr'."""
        scanner = _make_scanner([{"account_iban": "FR7630006000011234567890189"}])
        table = _TableMeta(columns=[{"name": "account_iban", "type": "varchar"}])
        asyncio.run(scanner._detect_pii([table]))
        self.assertIn("iban", table.pii_types)
        self.assertNotIn("iban_fr", table.pii_types)
        iban_types = [t for t in table.pii_types if t.startswith("iban")]
        self.assertEqual(len(iban_types), 1, f"Expected 1 iban-type, got: {table.pii_types}")

    def test_itin_no_ssn_double_count(self):
        """KI-103: ITIN (starts with 9) must produce exactly one IRS type, not ssn_us + itin_us."""
        scanner = _make_scanner([{"tax_id": "987-65-4321"}])
        table = _TableMeta(columns=[{"name": "tax_id", "type": "varchar"}])
        asyncio.run(scanner._detect_pii([table]))
        irs_types = [t for t in table.pii_types if t in ("ssn_us", "itin_us")]
        self.assertEqual(len(irs_types), 1, f"Expected 1 IRS type, got: {table.pii_types}")

    def test_distinct_pii_types_across_cells(self):
        """Different cells with different PII types must all be detected independently."""
        scanner = _make_scanner([{
            "email_col": "user@example.com",
            "iban_col": "FR7630006000011234567890189",
        }])
        table = _TableMeta(columns=[
            {"name": "email_col", "type": "varchar"},
            {"name": "iban_col", "type": "varchar"},
        ])
        asyncio.run(scanner._detect_pii([table]))
        self.assertIn("email", table.pii_types)
        self.assertIn("iban", table.pii_types)
        self.assertNotIn("iban_fr", table.pii_types)

    def test_no_pii_value_stays_clean(self):
        """Non-PII value must not trigger any detection."""
        scanner = _make_scanner([{"description": "Hello world no PII here"}])
        table = _TableMeta(columns=[{"name": "description", "type": "varchar"}])
        asyncio.run(scanner._detect_pii([table]))
        self.assertFalse(table.pii_detected)
        self.assertEqual(table.pii_types, [])


if __name__ == "__main__":
    unittest.main()
