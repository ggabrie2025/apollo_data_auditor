"""
DBSmartSampler - Zone-aware sampling pour DB
Équivalent du SmartSampler FILES (fingerprint.py:306-376)

Architecture:
- Zones sensibles (RH, Finance, Users): 100% sampling
- Zones normales (métier standard): 30% sampling
- Zones archives (logs, backups): 5% sampling

Cohérence avec FILES SmartSampler (backend/src/unstructured/fingerprint.py)
"""

from typing import Tuple


class DBSmartSampler:
    """
    Sampling intelligent basé sur sensibilité + taille table

    Zones détection:
    - SENSITIVE (100%): schemas/tables RH, Finance, Users, Customers
    - NORMAL (30%): tables métier standard
    - ARCHIVE (5%): logs, backups, audit trails

    Adaptatif selon taille:
    - Petites tables (<1k rows): 100% (stats fiables)
    - Tables moyennes (1k-1M): rate × row_count
    - Grandes tables (>1M): rate × row_count, cap à max_sample
    """

    # Schemas sensibles (100% sampling)
    SENSITIVE_SCHEMAS = {
        "rh", "payroll", "customers", "finance", "users", "hr", "employee",
        "personal", "personnel", "compensation", "banking", "account"
    }

    # Tables sensibles (100% sampling)
    SENSITIVE_TABLES = {
        "users", "customers", "employees", "salaries", "payments", "accounts",
        "transactions", "invoices", "contracts", "clients", "personnel"
    }

    # Patterns archives (5% sampling)
    ARCHIVE_PATTERNS = {
        "log", "archive", "backup", "audit", "history", "tmp", "temp",
        "old", "deprecated", "snapshot", "staging", "test"
    }

    def __init__(self, min_sample: int = 1000, max_sample: int = 100_000):
        """
        Initialize DBSmartSampler

        Args:
            min_sample: Minimum rows to sample (ensures statistical validity)
            max_sample: Maximum rows to sample (cap for huge tables)
        """
        self.min_sample = min_sample
        self.max_sample = max_sample

    def get_sample_size(self, table_name: str, schema: str, row_count: int) -> int:
        """
        Calculate adaptive sample size based on zone + table size

        Args:
            table_name: Table name
            schema: Schema name (can be None)
            row_count: Total rows in table

        Returns:
            Sample size (number of rows to profile)

        Examples:
            >>> sampler = DBSmartSampler(min_sample=1000, max_sample=100_000)
            >>> sampler.get_sample_size("users", "public", 500)
            500  # Small sensitive table: 100%

            >>> sampler.get_sample_size("users", "public", 50_000)
            50_000  # Sensitive: 100%

            >>> sampler.get_sample_size("products", "public", 10_000)
            3_000  # Normal: 30% × 10k

            >>> sampler.get_sample_size("access_logs", "public", 10_000_000)
            50_000  # Archive: 5% × 10M = 500k → cap 100k → min 1k → 50k
        """
        rate = self._get_zone_rate(table_name, schema)

        # Small tables: sample everything (statistical validity)
        if row_count <= self.min_sample:
            return row_count

        # Medium tables (1k-1M): apply rate
        if row_count < 1_000_000:
            sample = int(row_count * rate)
        else:
            # Large tables (>1M): apply rate with cap
            sample = int(row_count * rate)
            sample = min(sample, self.max_sample)

        # Ensure minimum for stats validity
        return max(sample, self.min_sample)

    def _get_zone_rate(self, table_name: str, schema: str) -> float:
        """
        Determine sampling rate based on sensitivity zone

        Args:
            table_name: Table name
            schema: Schema name (can be None)

        Returns:
            Sampling rate (0.05 | 0.30 | 1.0)
        """
        table_lower = table_name.lower()
        schema_lower = schema.lower() if schema else ""

        # Zone Sensitive = 100%
        if schema_lower in self.SENSITIVE_SCHEMAS:
            return 1.0
        if any(s in table_lower for s in self.SENSITIVE_TABLES):
            return 1.0

        # Zone Archive = 5%
        if any(p in table_lower for p in self.ARCHIVE_PATTERNS):
            return 0.05

        # Zone Normal = 30% (default)
        return 0.30

    def get_zone(self, table_name: str, schema: str) -> str:
        """
        Get zone name for reporting/logging

        Args:
            table_name: Table name
            schema: Schema name

        Returns:
            Zone name ("SENSITIVE" | "NORMAL" | "ARCHIVE")
        """
        rate = self._get_zone_rate(table_name, schema)
        if rate >= 1.0:
            return "SENSITIVE"
        elif rate <= 0.05:
            return "ARCHIVE"
        else:
            return "NORMAL"

    def get_sample_info(
        self,
        table_name: str,
        schema: str,
        row_count: int
    ) -> Tuple[int, str, float]:
        """
        Get complete sampling info (size + zone + rate)

        Args:
            table_name: Table name
            schema: Schema name
            row_count: Total rows

        Returns:
            Tuple (sample_size, zone, rate)

        Example:
            >>> sampler = DBSmartSampler()
            >>> sampler.get_sample_info("users", "public", 50_000)
            (50_000, "SENSITIVE", 1.0)
        """
        sample_size = self.get_sample_size(table_name, schema, row_count)
        zone = self.get_zone(table_name, schema)
        rate = self._get_zone_rate(table_name, schema)

        return (sample_size, zone, rate)
