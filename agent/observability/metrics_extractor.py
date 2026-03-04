"""
Apollo Agent - Metrics Extractor
================================

Extract metrics from JSON scan reports.
Adapted from Sprint 37 extract_metrics.py

NON-DESTRUCTIF: Read-only access to JSON files.
ZERO OVERHEAD: Post-scan analysis only.

Version: 1.0.0
Copyright: (c) 2025 Gilles Gabriel - gilles.gabriel@noos.fr
"""

import json
import os
from datetime import datetime
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any

from .config import ObservabilityConfig, SENSITIVE_PII_TYPES


@dataclass
class FilesScanMetrics:
    """Metrics from a files scan report."""
    total_files: int = 0
    total_size_bytes: int = 0
    pii_files: int = 0
    pii_types: Dict[str, int] = field(default_factory=dict)
    extensions: Dict[str, int] = field(default_factory=dict)
    scan_duration_sec: float = 0.0
    files_per_second: float = 0.0
    sensitive_pii_count: int = 0  # High-risk PII types


@dataclass
class DatabaseScanMetrics:
    """Metrics from a database scan report."""
    total_tables: int = 0
    total_rows: int = 0
    total_columns: int = 0
    pii_columns: int = 0
    pii_tables: int = 0
    pii_types: Dict[str, int] = field(default_factory=dict)
    db_types: Dict[str, int] = field(default_factory=dict)
    scan_duration_sec: float = 0.0
    rows_per_second: float = 0.0


@dataclass
class CloudScanMetrics:
    """Metrics from a cloud scan report."""
    total_items: int = 0
    total_size_bytes: int = 0
    pii_items: int = 0
    cloud_sources: Dict[str, int] = field(default_factory=dict)
    scan_duration_sec: float = 0.0
    items_per_second: float = 0.0


@dataclass
class MetricsExtractionResult:
    """Complete metrics extraction result."""
    source_type: str
    file_path: str
    file_size_bytes: int
    file_size_mb: float
    analyzed_at: str
    metrics: Any  # FilesScanMetrics | DatabaseScanMetrics | CloudScanMetrics
    alerts: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON export."""
        result = {
            "source_type": self.source_type,
            "file_path": self.file_path,
            "file_size_bytes": self.file_size_bytes,
            "file_size_mb": self.file_size_mb,
            "analyzed_at": self.analyzed_at,
            "alerts": self.alerts,
        }

        if isinstance(self.metrics, FilesScanMetrics):
            result["metrics"] = {
                "total_files": self.metrics.total_files,
                "total_size_bytes": self.metrics.total_size_bytes,
                "total_size_gb": round(self.metrics.total_size_bytes / 1024**3, 2),
                "pii_files": self.metrics.pii_files,
                "pii_types": self.metrics.pii_types,
                "extensions": self.metrics.extensions,
                "scan_duration_sec": self.metrics.scan_duration_sec,
                "files_per_second": self.metrics.files_per_second,
                "sensitive_pii_count": self.metrics.sensitive_pii_count,
            }
        elif isinstance(self.metrics, DatabaseScanMetrics):
            result["metrics"] = {
                "total_tables": self.metrics.total_tables,
                "total_rows": self.metrics.total_rows,
                "total_columns": self.metrics.total_columns,
                "pii_columns": self.metrics.pii_columns,
                "pii_tables": self.metrics.pii_tables,
                "pii_types": self.metrics.pii_types,
                "db_types": self.metrics.db_types,
                "scan_duration_sec": self.metrics.scan_duration_sec,
                "rows_per_second": self.metrics.rows_per_second,
            }
        elif isinstance(self.metrics, CloudScanMetrics):
            result["metrics"] = {
                "total_items": self.metrics.total_items,
                "total_size_bytes": self.metrics.total_size_bytes,
                "pii_items": self.metrics.pii_items,
                "cloud_sources": self.metrics.cloud_sources,
                "scan_duration_sec": self.metrics.scan_duration_sec,
                "items_per_second": self.metrics.items_per_second,
            }

        return result


class MetricsExtractor:
    """
    JSON report metrics extractor.

    NON-DESTRUCTIF: Read-only access.
    USAGE: Post-scan analysis only.
    """

    def __init__(self, config: Optional[ObservabilityConfig] = None):
        self.config = config or ObservabilityConfig.from_env()

    def extract(self, json_file: str) -> Optional[MetricsExtractionResult]:
        """
        Extract metrics from JSON report.

        Args:
            json_file: Path to JSON file

        Returns:
            MetricsExtractionResult or None
        """
        if not os.path.exists(json_file):
            return None

        file_size = os.path.getsize(json_file)

        # Load JSON (READ-ONLY)
        with open(json_file, 'r') as f:
            data = json.load(f)

        # Detect source type
        source_type = data.get("source_type", "unknown")

        # Extract based on type
        if source_type == "files" or "files" in data:
            metrics = self._extract_files_metrics(data)
            source_type = "files"
        elif source_type == "database" or "tables" in data:
            metrics = self._extract_db_metrics(data)
            source_type = "database"
        elif source_type == "cloud":
            metrics = self._extract_cloud_metrics(data)
            source_type = "cloud"
        else:
            # Try to detect from content
            if "files" in data:
                metrics = self._extract_files_metrics(data)
                source_type = "files"
            else:
                return None

        # Generate alerts
        alerts = self._generate_alerts(metrics, source_type)

        return MetricsExtractionResult(
            source_type=source_type,
            file_path=json_file,
            file_size_bytes=file_size,
            file_size_mb=round(file_size / 1024 / 1024, 2),
            analyzed_at=datetime.now().isoformat(),
            metrics=metrics,
            alerts=alerts,
        )

    def _extract_files_metrics(self, data: Dict) -> FilesScanMetrics:
        """Extract metrics from files scan."""
        metrics = FilesScanMetrics()

        files = data.get("files", [])
        metrics.total_files = len(files)

        for f in files:
            # Size
            size = f.get("size", f.get("file_size", 0))
            metrics.total_size_bytes += size

            # Extension
            ext = f.get("extension", "unknown")
            metrics.extensions[ext] = metrics.extensions.get(ext, 0) + 1

            # PII
            if f.get("pii_detected", f.get("has_pii", False)):
                metrics.pii_files += 1
                for pii_type in f.get("pii_types", []):
                    metrics.pii_types[pii_type] = metrics.pii_types.get(pii_type, 0) + 1
                    if pii_type in SENSITIVE_PII_TYPES:
                        metrics.sensitive_pii_count += 1

        # Summary override
        if "summary" in data:
            summary = data["summary"]
            metrics.total_files = summary.get("total_files", metrics.total_files)
            metrics.total_size_bytes = summary.get("total_size_bytes", metrics.total_size_bytes)
            metrics.pii_files = summary.get("files_with_pii", metrics.pii_files)
            metrics.scan_duration_sec = summary.get("duration_seconds", 0)

        # Performance
        if metrics.scan_duration_sec > 0:
            metrics.files_per_second = round(
                metrics.total_files / metrics.scan_duration_sec, 2
            )

        return metrics

    def _extract_db_metrics(self, data: Dict) -> DatabaseScanMetrics:
        """Extract metrics from database scan."""
        metrics = DatabaseScanMetrics()

        tables = data.get("tables", data.get("results", []))

        for table in tables:
            metrics.total_tables += 1
            metrics.total_rows += table.get("row_count", 0)

            columns = table.get("columns", [])
            metrics.total_columns += len(columns)

            has_pii = False
            for col in columns:
                if col.get("has_pii", col.get("pii_detected", False)):
                    metrics.pii_columns += 1
                    has_pii = True
                    pii_type = col.get("pii_type", "unknown")
                    metrics.pii_types[pii_type] = metrics.pii_types.get(pii_type, 0) + 1

            if has_pii:
                metrics.pii_tables += 1

            # DB type
            db_type = table.get("db_type", data.get("db_type", "unknown"))
            metrics.db_types[db_type] = metrics.db_types.get(db_type, 0) + 1

        # Summary
        if "summary" in data:
            metrics.scan_duration_sec = data["summary"].get("duration_seconds", 0)

        # Performance
        if metrics.scan_duration_sec > 0:
            metrics.rows_per_second = round(
                metrics.total_rows / metrics.scan_duration_sec, 2
            )

        return metrics

    def _extract_cloud_metrics(self, data: Dict) -> CloudScanMetrics:
        """Extract metrics from cloud scan."""
        metrics = CloudScanMetrics()

        items = data.get("items", data.get("files", []))
        metrics.total_items = len(items)

        for item in items:
            metrics.total_size_bytes += item.get("size", 0)

            if item.get("has_pii", item.get("pii_detected", False)):
                metrics.pii_items += 1

            source = item.get("cloud_source", item.get("source_type", "unknown"))
            metrics.cloud_sources[source] = metrics.cloud_sources.get(source, 0) + 1

        if "summary" in data:
            metrics.scan_duration_sec = data["summary"].get("duration_seconds", 0)

        if metrics.scan_duration_sec > 0:
            metrics.items_per_second = round(
                metrics.total_items / metrics.scan_duration_sec, 2
            )

        return metrics

    def _generate_alerts(self, metrics: Any, source_type: str) -> List[str]:
        """Generate alerts based on metrics."""
        alerts = []

        if source_type == "files" and isinstance(metrics, FilesScanMetrics):
            # High PII risk
            if metrics.pii_files >= self.config.pii_high_risk_threshold:
                alerts.append(
                    f"HIGH_PII_RISK: {metrics.pii_files} files with PII detected"
                )

            # Sensitive PII types
            if metrics.sensitive_pii_count > 0:
                alerts.append(
                    f"SENSITIVE_PII: {metrics.sensitive_pii_count} sensitive PII occurrences"
                )

            # Low performance
            if (metrics.files_per_second > 0 and
                metrics.files_per_second < self.config.min_files_per_second):
                alerts.append(
                    f"LOW_PERFORMANCE: {metrics.files_per_second} files/sec "
                    f"(threshold: {self.config.min_files_per_second})"
                )

        elif source_type == "database" and isinstance(metrics, DatabaseScanMetrics):
            if metrics.pii_tables > 0:
                alerts.append(
                    f"DB_PII_DETECTED: {metrics.pii_tables} tables with PII columns"
                )

        return alerts


def extract_json_metrics(
    json_file: str,
    config: Optional[ObservabilityConfig] = None
) -> Optional[MetricsExtractionResult]:
    """
    Convenience function to extract metrics from JSON.

    Args:
        json_file: Path to JSON file
        config: Optional configuration

    Returns:
        MetricsExtractionResult or None
    """
    extractor = MetricsExtractor(config)
    return extractor.extract(json_file)
