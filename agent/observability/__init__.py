"""
Apollo Agent - Observability Module (V1.0)
==========================================

Non-destructive monitoring and metrics collection.
Zero runtime performance impact - post-processing only.

Version: 1.0.0
Date: 2026-01-07
Sprint: 38
Copyright: (c) 2025 Gilles Gabriel - gilles.gabriel@noos.fr
"""

from .log_analyzer import LogAnalyzer, analyze_log_file
from .metrics_extractor import MetricsExtractor, extract_json_metrics
from .health import HealthStatus, get_health_status
from .config import ObservabilityConfig

__all__ = [
    'LogAnalyzer',
    'analyze_log_file',
    'MetricsExtractor',
    'extract_json_metrics',
    'HealthStatus',
    'get_health_status',
    'ObservabilityConfig',
]

from agent.version import VERSION  # Single source of truth
