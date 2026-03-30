"""
Apollo Agent - Log Analyzer
===========================

Post-scan log analysis for metrics extraction.
Adapted from Sprint 37 analyze_agent_logs.py

NON-DESTRUCTIF: Read-only access to log files.
ZERO OVERHEAD: Only runs after scan completion.

Version: 1.0.0
Copyright: (c) 2025 Gilles Gabriel - gilles.gabriel@noos.fr
"""

import re
import os
from datetime import datetime
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any

from .config import LOG_PATTERNS, ObservabilityConfig


@dataclass
class ScanMetrics:
    """Metrics from a single scan."""
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    duration_seconds: float = 0.0
    files_scanned: int = 0
    records_scanned: int = 0
    pii_found: int = 0
    pii_files: int = 0
    source_type: str = "unknown"
    status: str = "unknown"
    session_id: Optional[str] = None
    files_per_second: float = 0.0
    records_per_second: float = 0.0


@dataclass
class LogAnalysisResult:
    """Complete log analysis result."""
    log_file: str
    log_size_bytes: int
    analyzed_at: str
    agent_version: Optional[str] = None
    agent_mode: Optional[str] = None
    scans: List[ScanMetrics] = field(default_factory=list)
    errors: List[Dict[str, Any]] = field(default_factory=list)
    warnings: List[Dict[str, Any]] = field(default_factory=list)
    total_lines: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON export."""
        return {
            "log_file": self.log_file,
            "log_size_bytes": self.log_size_bytes,
            "analyzed_at": self.analyzed_at,
            "agent_version": self.agent_version,
            "agent_mode": self.agent_mode,
            "total_lines": self.total_lines,
            "scans": [
                {
                    "start_time": s.start_time,
                    "end_time": s.end_time,
                    "duration_seconds": s.duration_seconds,
                    "files_scanned": s.files_scanned,
                    "records_scanned": s.records_scanned,
                    "pii_found": s.pii_found,
                    "pii_files": s.pii_files,
                    "source_type": s.source_type,
                    "status": s.status,
                    "session_id": s.session_id,
                    "files_per_second": s.files_per_second,
                    "records_per_second": s.records_per_second,
                }
                for s in self.scans
            ],
            "errors": self.errors,
            "warnings": self.warnings,
            "summary": self.get_summary(),
        }

    def get_summary(self) -> Dict[str, Any]:
        """Generate summary statistics."""
        completed = [s for s in self.scans if s.status == "completed"]
        total_files = sum(s.files_scanned for s in self.scans)
        total_records = sum(s.records_scanned for s in self.scans)
        total_duration = sum(s.duration_seconds for s in completed)

        return {
            "total_scans": len(self.scans),
            "completed_scans": len(completed),
            "total_files_scanned": total_files,
            "total_records_scanned": total_records,
            "total_duration_seconds": round(total_duration, 2),
            "total_errors": len(self.errors),
            "total_warnings": len(self.warnings),
            "avg_files_per_second": round(
                total_files / total_duration, 2
            ) if total_duration > 0 else 0,
            "avg_records_per_second": round(
                total_records / total_duration, 2
            ) if total_duration > 0 else 0,
        }


class LogAnalyzer:
    """
    Log file analyzer for Apollo Agent.

    NON-DESTRUCTIF: Read-only access.
    USAGE: Post-scan analysis only.
    """

    def __init__(self, config: Optional[ObservabilityConfig] = None):
        self.config = config or ObservabilityConfig.from_env()
        self._patterns = {k: re.compile(v) for k, v in LOG_PATTERNS.items()}

    def analyze(self, log_file: str) -> Optional[LogAnalysisResult]:
        """
        Analyze log file and extract metrics.

        Args:
            log_file: Path to log file

        Returns:
            LogAnalysisResult or None if file not found
        """
        if not os.path.exists(log_file):
            return None

        file_size = os.path.getsize(log_file)

        # Check size limit
        max_bytes = self.config.max_log_size_mb * 1024 * 1024
        if file_size > max_bytes:
            # TODO(KI-135): Read only last N MB for large files
            pass

        result = LogAnalysisResult(
            log_file=log_file,
            log_size_bytes=file_size,
            analyzed_at=datetime.now().isoformat(),
        )

        current_scan: Optional[ScanMetrics] = None
        scans: List[ScanMetrics] = []
        errors: List[Dict[str, Any]] = []
        warnings: List[Dict[str, Any]] = []

        # Read file (READ-ONLY)
        with open(log_file, 'r', errors='ignore') as f:
            lines = f.readlines()

        result.total_lines = len(lines)

        for line_num, line in enumerate(lines, 1):
            line = line.strip()
            if not line:
                continue

            # Agent version
            match = self._patterns['agent_start'].search(line)
            if match:
                result.agent_version = match.group(2)

            # Agent mode
            match = self._patterns['agent_mode'].search(line)
            if match:
                result.agent_mode = match.group(1)

            # Scan start
            match = self._patterns['scan_start'].search(line)
            if match:
                ts = self._parse_timestamp(match.group(1))
                if ts:
                    if current_scan and current_scan.status == "unknown":
                        current_scan.status = "interrupted"
                        scans.append(current_scan)

                    current_scan = ScanMetrics(
                        start_time=ts.isoformat(),
                        status="in_progress",
                    )

            # During scan - collect metrics
            if current_scan:
                self._extract_scan_metrics(line, current_scan)

            # Scan end
            match = self._patterns['scan_end'].search(line)
            if match and current_scan:
                ts = self._parse_timestamp(match.group(1))
                if ts and current_scan.start_time:
                    start_ts = datetime.fromisoformat(current_scan.start_time)
                    current_scan.end_time = ts.isoformat()
                    current_scan.duration_seconds = round(
                        (ts - start_ts).total_seconds(), 2
                    )
                    current_scan.status = "completed"

                    # Calculate performance
                    if current_scan.duration_seconds > 0:
                        if current_scan.files_scanned > 0:
                            current_scan.files_per_second = round(
                                current_scan.files_scanned / current_scan.duration_seconds,
                                2
                            )
                        if current_scan.records_scanned > 0:
                            current_scan.records_per_second = round(
                                current_scan.records_scanned / current_scan.duration_seconds,
                                2
                            )

                    scans.append(current_scan)
                    current_scan = None

            # Errors
            match = self._patterns['error'].search(line)
            if match:
                errors.append({
                    "timestamp": match.group(1),
                    "message": match.group(2).strip()[:200],
                    "line": line_num,
                })

            # Warnings
            match = self._patterns['warning'].search(line)
            if match:
                warnings.append({
                    "timestamp": match.group(1),
                    "message": match.group(2).strip()[:200],
                    "line": line_num,
                })

        # Handle unfinished scan
        if current_scan:
            current_scan.status = "in_progress"
            scans.append(current_scan)

        result.scans = scans
        result.errors = errors[-self.config.max_errors_stored:]
        result.warnings = warnings[-self.config.max_warnings_stored:]

        return result

    def _extract_scan_metrics(self, line: str, scan: ScanMetrics) -> None:
        """Extract metrics from a log line during scan."""
        # Files
        match = self._patterns['files_scanned'].search(line)
        if match:
            scan.files_scanned = max(scan.files_scanned, int(match.group(1)))
            scan.source_type = "files"

        match = self._patterns['files_total'].search(line)
        if match:
            scan.files_scanned = int(match.group(1))
            scan.source_type = "files"

        # Records/Tables
        match = self._patterns['records_scanned'].search(line)
        if match:
            scan.records_scanned = max(scan.records_scanned, int(match.group(1)))
            scan.source_type = "database"

        match = self._patterns['tables_scanned'].search(line)
        if match:
            scan.source_type = "database"

        # PII
        match = self._patterns['pii_found'].search(line)
        if match:
            scan.pii_found = int(match.group(1))

        match = self._patterns['pii_files'].search(line)
        if match:
            scan.pii_files = int(match.group(1))

        # Session
        match = self._patterns['session_id'].search(line)
        if match:
            scan.session_id = match.group(1)

    def _parse_timestamp(self, ts_str: str) -> Optional[datetime]:
        """Parse timestamp string to datetime."""
        formats = [
            '%Y-%m-%d %H:%M:%S',
            '%Y-%m-%dT%H:%M:%S',
        ]
        for fmt in formats:
            try:
                return datetime.strptime(ts_str.split(',')[0], fmt)
            except ValueError:
                continue
        return None


def analyze_log_file(
    log_file: str,
    config: Optional[ObservabilityConfig] = None
) -> Optional[LogAnalysisResult]:
    """
    Convenience function to analyze a log file.

    Args:
        log_file: Path to log file
        config: Optional configuration

    Returns:
        LogAnalysisResult or None
    """
    analyzer = LogAnalyzer(config)
    return analyzer.analyze(log_file)
