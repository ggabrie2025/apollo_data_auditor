"""
Apollo Agent - Observability Configuration
==========================================

Centralized configuration for observability features.
All parameters configurable via environment variables.

NON-DESTRUCTIF: Configuration only, no runtime overhead.

Copyright: (c) 2025 Gilles Gabriel - gilles.gabriel@noos.fr
"""

import os
import tempfile
from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class ObservabilityConfig:
    """Observability module configuration."""

    # Health check settings
    health_check_interval_sec: int = 60
    health_endpoint_enabled: bool = True

    # Log analysis settings
    max_log_size_mb: int = 100
    max_errors_stored: int = 50
    max_warnings_stored: int = 50

    # Metrics extraction settings
    metrics_output_dir: str = os.path.join(tempfile.gettempdir(), "apollo_metrics")

    # Alert thresholds
    error_rate_threshold: float = 0.05  # 5% error rate triggers alert
    warning_rate_threshold: float = 0.10  # 10% warning rate
    min_files_per_second: float = 10.0  # Performance baseline

    # PII detection thresholds
    pii_high_risk_threshold: int = 100  # Files with PII

    @classmethod
    def from_env(cls) -> 'ObservabilityConfig':
        """Load configuration from environment variables."""
        return cls(
            health_check_interval_sec=int(
                os.getenv('APOLLO_HEALTH_INTERVAL', '60')
            ),
            health_endpoint_enabled=os.getenv(
                'APOLLO_HEALTH_ENABLED', '1'
            ) == '1',
            max_log_size_mb=int(
                os.getenv('APOLLO_MAX_LOG_MB', '100')
            ),
            metrics_output_dir=os.getenv(
                'APOLLO_METRICS_DIR', os.path.join(tempfile.gettempdir(), 'apollo_metrics')
            ),
            error_rate_threshold=float(
                os.getenv('APOLLO_ERROR_THRESHOLD', '0.05')
            ),
            min_files_per_second=float(
                os.getenv('APOLLO_MIN_FPS', '10.0')
            ),
        )


# Log patterns for analysis (from Sprint 37)
LOG_PATTERNS: Dict[str, str] = {
    # Agent lifecycle
    'agent_start': r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}),\d+ - INFO - Starting Apollo Agent.*V([\d.]+)',
    'agent_mode': r'INFO - Mode: (\w+)',

    # Scan events
    'scan_start': r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}).*(?:Scan started|Starting scan|BEGIN SCAN)',
    'scan_end': r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}).*(?:Scan completed|Scan finished|END SCAN)',

    # Progress metrics
    'files_scanned': r'(?:Scanned|Processed|Found)\s*(\d+)\s*files',
    'files_total': r'Total files[:\s]+(\d+)',
    'files_progress': r'(\d+)/(\d+)\s*files',

    # Database metrics
    'records_scanned': r'(?:Scanned|Processed|Found)\s*(\d+)\s*(?:records|rows)',
    'tables_scanned': r'(?:Scanned|Processed)\s*(\d+)\s*tables',

    # PII detection
    'pii_found': r'(?:Found|Detected)\s*(\d+)\s*PII',
    'pii_files': r'(\d+)\s*files with PII',

    # Errors and warnings
    'error': r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}).*(?:ERROR|Error|FAILED|Failed)(.*?)$',
    'warning': r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}).*(?:WARNING|Warning)(.*?)$',

    # Duration
    'duration': r'(?:duration|elapsed|took)[:\s]*(\d+(?:\.\d+)?)\s*(?:seconds|sec|s)',

    # Session tracking
    'session_id': r'session_id[:\s]*["\']?([a-zA-Z0-9-]+)["\']?',
}


# Sensitive PII types for alerting
SENSITIVE_PII_TYPES: List[str] = [
    'SSN',
    'CREDIT_CARD',
    'IBAN',
    'PASSPORT',
    'MEDICAL_ID',
    'BANK_ACCOUNT',
]
