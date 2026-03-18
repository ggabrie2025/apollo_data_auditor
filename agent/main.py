#!/usr/bin/env python3
"""
Apollo Agent - CLI Entry Point (V1.3)
=====================================

Standalone agent for file scanning with PII detection.
Exports JSON for Hub Cloud processing.

Usage:
    python -m agent.main /path/to/scan -o output.json
    python -m agent.main /path/to/scan --preview
    python -m agent.main --version

Version: 1.3.0
Date: 2025-12-11
"""

# PyInstaller Windows: freeze_support MUST be called before any other imports
# to prevent child processes from re-executing the main script
import sys
import multiprocessing
if getattr(sys, 'frozen', False):
    multiprocessing.freeze_support()

# Windows UTF-8 fix — CP1252 ne supporte pas les caracteres Unicode
# Protege contre UnicodeEncodeError sur stdout/stderr (chemins accentes, symboles, etc.)
import io
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

import argparse
import json
from pathlib import Path
from datetime import datetime

# Imports compatible with both module and PyInstaller binary
try:
    # Try relative imports first (for PyInstaller)
    from core.collector import collect_files
    from core.exclusions import load_exclusions, filter_files, get_exclusion_summary, load_network_config
    from core.network_mount import is_network_mount
    from core.pii_scanner import scan_files_for_pii, get_pii_patterns_info
    from core.exporter import (
        create_scan_output,
        export_to_json,
        export_to_string,
        generate_output_filename,
        generate_output_filename_multipath,  # NEW (Sprint 29)
        create_minimal_output
    )
    from core.fingerprint import (
        generate_fingerprint,
        get_fingerprint_stats,
        FingerprintDeduplicator,
        SmartSampler,
        hash_path
    )
    from core.differential import get_files_to_scan
    from core.snapshot import load_snapshot, save_snapshot
    from core.onedrive_collector import (  # Sprint 35
        OneDriveCollector,
        collect_onedrive_files,
        check_cloud_dependencies,
        CloudCollectorResult,
        extract_text_from_bytes,  # Sprint 85
        MAX_DOWNLOAD_BYTES,       # Sprint 85
    )
    from core.pii_scanner import scan_text_for_pii  # Sprint 85
    from models.contracts import CollectorConfig
except ImportError:
    # Fallback for running as module (python -m agent.main)
    from agent.core.collector import collect_files
    from agent.core.exclusions import load_exclusions, filter_files, get_exclusion_summary, load_network_config
    from agent.core.network_mount import is_network_mount
    from agent.core.pii_scanner import scan_files_for_pii, get_pii_patterns_info, scan_text_for_pii  # Sprint 85
    from agent.core.exporter import (
        create_scan_output,
        export_to_json,
        export_to_string,
        generate_output_filename,
        generate_output_filename_multipath,  # NEW (Sprint 29)
        create_minimal_output
    )
    from agent.core.fingerprint import (
        generate_fingerprint,
        get_fingerprint_stats,
        FingerprintDeduplicator,
        SmartSampler,
        hash_path
    )
    from agent.core.differential import get_files_to_scan
    from agent.core.snapshot import load_snapshot, save_snapshot
    from agent.core.onedrive_collector import (  # Sprint 35
        OneDriveCollector,
        collect_onedrive_files,
        check_cloud_dependencies,
        CloudCollectorResult,
        extract_text_from_bytes,  # Sprint 85
        MAX_DOWNLOAD_BYTES,       # Sprint 85
    )
    from agent.models.contracts import CollectorConfig

# PARALLEL SCAN IMPORTS (Optimization 2026-01-04)
# Disable ProcessPool in frozen executables (PyInstaller) — workers re-exec the exe
# and crash with "unrecognized arguments: --multiprocessing-fork"
import os as _os
_is_frozen = getattr(sys, 'frozen', False)
PARALLEL_SCAN = _os.getenv("PARALLEL_SCAN", "0" if _is_frozen else "1") == "1"
if PARALLEL_SCAN:
    try:
        from core.optimized_scanner import read_files_parallel, scan_pii_parallel
        print("[OPT] Parallel scanning enabled (ThreadPool I/O + ProcessPool CPU)", file=sys.stderr)
    except ImportError:
        try:
            from agent.core.optimized_scanner import read_files_parallel, scan_pii_parallel
            print("[OPT] Parallel scanning enabled (ThreadPool I/O + ProcessPool CPU)", file=sys.stderr)
        except ImportError:
            PARALLEL_SCAN = False
            print("[OPT] Parallel scanning not available, using sequential", file=sys.stderr)


from agent.version import VERSION  # Single source of truth




# ============================================================================
# PARALLEL PII SCAN WRAPPER (Optimization 2026-01-04)
# ============================================================================

def scan_files_for_pii_parallel(files, progress_callback=None):
    """
    Parallel PII scanning wrapper.
    Uses ThreadPool for I/O + ProcessPool for CPU (bypasses GIL).
    """
    import logging
    logger = logging.getLogger(__name__)
    
    if not PARALLEL_SCAN:
        return scan_files_for_pii(files, progress_callback)
    
    logger.info(f"[OPT] Parallel PII scan: {len(files)} files")
    
    # Extract file paths
    file_paths = [f.path if hasattr(f, 'path') else str(f) for f in files]
    
    # Step 1: Parallel file reading
    logger.info("[OPT] Step 1: Parallel file reading...")
    file_contents = read_files_parallel(file_paths)
    
    # Step 2: Parallel PII scanning
    logger.info("[OPT] Step 2: Parallel PII scanning...")
    pii_results = scan_pii_parallel(file_contents)
    
    # Step 3: Update file objects with PII results
    pii_by_type = {}
    for file_obj in files:
        fp = file_obj.path if hasattr(file_obj, 'path') else str(file_obj)
        pii_found = pii_results.get(fp, [])
        
        if pii_found:
            file_obj.pii_detected = True
            file_obj.pii_types = [p['type'] for p in pii_found]
            file_obj.pii_count = sum(p['count'] for p in pii_found)
            
            for p in pii_found:
                pii_by_type[p['type']] = pii_by_type.get(p['type'], 0) + p['count']
        else:
            file_obj.pii_detected = False
            file_obj.pii_types = []
            file_obj.pii_count = 0
        
        if progress_callback and hasattr(file_obj, 'path'):
            progress_callback(len([f for f in files if hasattr(f, 'pii_detected')]), fp)
    
    files_with_pii = [f for f in files if getattr(f, 'pii_detected', False)]
    logger.info(f"[OPT] PII found in {len(files_with_pii)}/{len(files)} files")
    
    return files, pii_by_type


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        prog="apollo-agent",
        description="Apollo Data Auditor - Standalone Agent for File Scanning"
    )

    parser.add_argument(
        "paths",
        nargs="*",
        help="Path(s) to scan (can specify multiple)"
    )
    parser.add_argument(
        "-o", "--output",
        help="Output JSON file path (default: auto-generated)"
    )
    parser.add_argument(
        "-c", "--config",
        help="Path to exclusions.yaml config file"
    )
    parser.add_argument(
        "--preview",
        action="store_true",
        help="Preview mode: show what would be scanned without full scan"
    )
    parser.add_argument(
        "--no-pii",
        action="store_true",
        help="Skip PII scanning (faster)"
    )
    parser.add_argument(
        "--max-files",
        type=int,
        default=10000000,
        help="Maximum files to scan (default: 10M for enterprise)"
    )
    parser.add_argument(
        "--max-depth",
        type=int,
        default=15,
        help="Maximum directory depth (default: 15)"
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Minimal output"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON to stdout"
    )
    parser.add_argument(
        "-v", "--version",
        action="store_true",
        help="Show version and exit"
    )
    parser.add_argument(
        "--show-patterns",
        action="store_true",
        help="Show PII patterns and exit"
    )
    parser.add_argument(
        "--include-network-mounts",
        action="store_true",
        help="Include network mounts (NFS, SMB, CIFS) - excluded by default"
    )

    # Sprint 35: OneDrive/SharePoint arguments
    parser.add_argument(
        "--onedrive",
        action="store_true",
        help="Scan OneDrive/SharePoint instead of local files"
    )
    parser.add_argument(
        "--tenant-id",
        help="Azure AD Tenant ID (required for --onedrive)"
    )
    parser.add_argument(
        "--client-id",
        help="Azure AD Application (Client) ID (required for --onedrive)"
    )
    parser.add_argument(
        "--client-secret",
        help="Azure AD Client Secret (required for --onedrive)"
    )
    parser.add_argument(
        "--drive-id",
        default="me",
        help="OneDrive drive ID or 'me' for default (default: me)"
    )
    parser.add_argument(
        "--onedrive-path",
        default="/",
        help="OneDrive folder path to scan (default: /)"
    )
    parser.add_argument(
        "--list-drives",
        action="store_true",
        help="List available OneDrive/SharePoint drives and exit"
    )
    parser.add_argument(
        "--fetch-permissions",
        action="store_true",
        help="Fetch detailed permissions (grantees, roles) for shared files"
    )
    parser.add_argument(
        "--serve",
        action="store_true",
        help="Launch the web UI server (opens browser automatically)"
    )
    parser.add_argument(
        "--mode",
        choices=["files", "db", "cloud", "directory", "app"],
        help="Scanner mode for frozen binary subprocess routing"
    )

    args = parser.parse_args()

    # Handle version
    if args.version:
        print(f"Apollo Agent v{VERSION}")
        return 0

    # Handle --serve: launch the web UI
    if args.serve:
        from agent.ui.server import main as serve_main
        return serve_main()

    # Handle --mode: frozen binary subprocess routing (PyInstaller)
    # In frozen mode, server.py calls: apollo-agent --mode db --config ... -o ...
    # instead of: python -m agent.main_db --config ... -o ...
    if args.mode and args.mode != "files":
        remaining = sys.argv[sys.argv.index("--mode") + 2:]
        if args.mode == "db":
            from agent.main_db import main as db_main
            sys.argv = [sys.argv[0]] + remaining
            return db_main()
        elif args.mode == "directory":
            from agent.main_directory import main as directory_main
            sys.argv = [sys.argv[0]] + remaining
            return directory_main()
        elif args.mode == "app":
            from agent.main_app import main as app_main
            sys.argv = [sys.argv[0]] + remaining
            return app_main()
        elif args.mode == "infra":
            from agent.main_infra import main as infra_main
            sys.argv = [sys.argv[0]] + remaining
            return infra_main()
        elif args.mode == "cloud":
            sys.argv = [sys.argv[0]] + remaining
            args = parser.parse_args()

    # Handle show patterns
    if args.show_patterns:
        print("PII Patterns:")
        for name, desc in get_pii_patterns_info().items():
            print(f"  {name}: {desc}")
        return 0

    # Sprint 35: Handle OneDrive scan
    if args.onedrive or args.list_drives:
        # Validate credentials
        if not all([args.tenant_id, args.client_id, args.client_secret]):
            print("Error: --tenant-id, --client-id, and --client-secret are required for OneDrive", file=sys.stderr)
            return 1

        # Handle --list-drives (list and exit)
        if args.list_drives:
            return run_list_drives(args)

        return run_onedrive_scan(args)

    # Require at least one path for scan
    if not args.paths:
        parser.print_help()
        return 1

    # Load network mount config
    config_path = Path(args.config) if args.config else None
    network_config = load_network_config(config_path)
    exclude_network = network_config['exclude_network_mounts'] and not args.include_network_mounts
    network_fs_types = network_config['network_mount_types']

    # Validate all paths
    scan_paths = []
    skipped_network_paths = []
    for p in args.paths:
        scan_path = Path(p).resolve()
        if not scan_path.exists():
            print(f"Error: Path does not exist: {scan_path}", file=sys.stderr)
            return 1
        if not scan_path.is_dir():
            print(f"Error: Path is not a directory: {scan_path}", file=sys.stderr)
            return 1

        # Check for network mount (Linux/Windows only)
        if exclude_network and is_network_mount(str(scan_path), network_fs_types):
            print(f"[WARN] Network mount excluded: {scan_path}", file=sys.stderr)
            skipped_network_paths.append(scan_path)
            continue

        scan_paths.append(scan_path)

    # Check if any paths remain after network mount filtering
    if not scan_paths:
        if skipped_network_paths:
            print("Error: All paths are network mounts (use --include-network-mounts to force)", file=sys.stderr)
        else:
            print("Error: No valid paths to scan", file=sys.stderr)
        return 1

    # ============================================================================
    # NEW: Compute multi-path metadata (Sprint 29 - Option C)
    # ============================================================================
    primary_path = scan_paths[0]  # First path is primary
    scanned_paths_array = [str(p) for p in scan_paths] if len(scan_paths) > 1 else None
    scanned_paths_count = len(scan_paths)

    # Load exclusions config (reuse config_path from network config)
    config = load_exclusions(config_path)

    if not args.quiet:
        print(f"Apollo Agent v{VERSION}")
        if skipped_network_paths:
            print(f"Network mounts excluded: {len(skipped_network_paths)}")
        if scanned_paths_count == 1:
            print(f"Scanning: {primary_path}")
        else:
            print(f"Multi-path scan: {scanned_paths_count} sources")
            print(f"  Primary: {primary_path}")
            # Show first 5 paths
            for i, p in enumerate(scan_paths[1:6], start=2):
                print(f"  [{i}] {p}")
            if scanned_paths_count > 6:
                print(f"  ... and {scanned_paths_count - 6} more")
        print()

    # Preview mode
    if args.preview:
        return run_preview(scan_paths, config, args)

    # Full scan
    return run_scan(scan_paths, config, args, primary_path, scanned_paths_array, scanned_paths_count)


def run_preview(scan_paths: list, config, args) -> int:
    """Run preview mode - show what would be scanned."""
    if not args.quiet:
        print("=== PREVIEW MODE ===")
        print()

    # Show exclusion config
    summary = get_exclusion_summary(config)
    print("Exclusions Config:")
    print(f"  Extensions excluded: {summary['extensions_count']}")
    print(f"  Path patterns: {summary['path_patterns_count']}")
    print(f"  Max file size: {summary['max_file_mb']} MB")
    print(f"  Min file size: {summary['min_file_bytes']} bytes")
    print()

    # Quick collect (limited) from all paths
    collector_config = CollectorConfig(
        max_files=min(args.max_files, 1000),  # Limit for preview
        max_depth=args.max_depth
    )

    def progress(count, path):
        if not args.quiet:
            print(f"\r  Scanning... {count} files", end="", flush=True)

    all_files = []
    for scan_path in scan_paths:
        result = collect_files(str(scan_path), collector_config, progress)
        all_files.extend(result.files)

    if not args.quiet:
        print()

    # Filter
    included, excluded = filter_files(all_files, config)

    print(f"\nPreview Results (first {len(all_files)} files):")
    print(f"  Total found: {len(all_files)}")
    print(f"  Would include: {len(included)}")
    print(f"  Would exclude: {len(excluded)}")
    print(f"  Reduction: {len(excluded) / max(len(all_files), 1) * 100:.1f}%")

    if excluded and not args.quiet:
        print("\nSample excluded files:")
        for f in excluded[:5]:
            print(f"  - {f.name} ({f.exclusion_reason})")

    return 0


def run_scan(scan_paths: list, config, args, primary_path=None, scanned_paths_array=None, scanned_paths_count=1) -> int:
    """Run full scan with V1.5 optimizations."""
    # NEW (Sprint 29): Use provided primary_path if available, else first scan_path
    if primary_path is None:
        primary_path = scan_paths[0]
    start_time = datetime.now()

    # Collector config
    collector_config = CollectorConfig(
        max_files=args.max_files,
        max_depth=args.max_depth
    )

    # Step 1: Collect files from all paths
    if not args.quiet:
        print("Step 1/8: Collecting files...")

    def collect_progress(count, path):
        if not args.quiet and count % 500 == 0:
            print(f"\r  {count} files found...", end="", flush=True)

    all_collected_files = []
    for scan_path in scan_paths:
        result = collect_files(str(scan_path), collector_config, collect_progress)
        if result.error:
            print(f"Error scanning {scan_path}: {result.error}", file=sys.stderr)
            continue
        all_collected_files.extend(result.files)

    if not args.quiet:
        print(f"\r  {len(all_collected_files)} files collected from {len(scan_paths)} path(s)")

    if not all_collected_files:
        print("No files found to scan", file=sys.stderr)
        return 1

    # Create a mock result object for compatibility
    class MockResult:
        def __init__(self, files):
            self.files = files
            self.error = None
            self.errors = []
    result = MockResult(all_collected_files)

    # Step 2: Generate fingerprints (V1.5 - metadata only)
    if not args.quiet:
        print("Step 2/8: Generating fingerprints...")

    all_fingerprints = []
    for file in result.files:
        # Get file path from FileMetadata object
        file_path = file.path if hasattr(file, 'path') else str(file)
        fp = generate_fingerprint(file_path)
        if fp:
            all_fingerprints.append(fp)

    # Get fingerprint stats
    if all_fingerprints:
        fp_stats = get_fingerprint_stats(all_fingerprints)
        if not args.quiet:
            print(f"  {fp_stats['total']} fingerprints generated")
            zone_dist = fp_stats['by_zone']
            print(f"  Zones: SENSITIVE={zone_dist.get('sensitive', 0)}, "
                  f"NORMAL={zone_dist.get('normal', 0)}, "
                  f"ARCHIVE={zone_dist.get('archive', 0)}")
    else:
        if not args.quiet:
            print("  No fingerprints generated")
        # No files to process
        return 0

    # Build zone mapping for FileMetadata enrichment
    zone_by_path_hash = {}
    for fp in all_fingerprints:
        if hasattr(fp, 'path_hash') and hasattr(fp, 'zone'):
            zone_by_path_hash[fp.path_hash] = fp.zone

    # Step 2b: Deduplication (V1.5 - group by size + extension)
    if not args.quiet:
        print("Step 2b/8: Deduplication...")

    total_before_dedup = len(all_fingerprints)
    deduplicator = FingerprintDeduplicator()

    for fp in all_fingerprints:
        deduplicator.add(fp)

    dedup_fingerprints = deduplicator.get_representatives()
    dedup_stats = deduplicator.get_stats()
    dedup_ratio = dedup_stats['dedup_ratio']

    if not args.quiet:
        print(f"  {total_before_dedup} → {len(dedup_fingerprints)} files "
              f"(-{dedup_ratio*100:.1f}% duplicates)")
        print(f"  {dedup_stats['unique_groups']} unique groups")

    # Step 2c: Load previous snapshot (V1.5 - differential audit)
    if not args.quiet:
        print("Step 2c/8: Loading previous snapshot...")

    previous_snapshot = load_snapshot(str(primary_path))  # FIX (Sprint 29): Use primary_path, not last scan_path

    if previous_snapshot:
        if not args.quiet:
            print(f"  Previous snapshot loaded: {len(previous_snapshot)} files")
    else:
        if not args.quiet:
            print("  No previous snapshot - first audit")

    # Step 2d: Differential comparison (V1.5 - scan only new/modified)
    if not args.quiet:
        print("Step 2d/8: Differential comparison...")

    diff_result = get_files_to_scan(dedup_fingerprints, previous_snapshot)

    if not args.quiet:
        stats = diff_result.stats
        if diff_result.is_first_audit:
            print(f"  First audit - scanning all {stats['total']} files")
        else:
            print(f"  New: {stats['new']}, Modified: {stats['modified']}, "
                  f"Unchanged: {stats['unchanged']}, Deleted: {stats['deleted']}")
            print(f"  Scanning {stats['new'] + stats['modified']}/{stats['total']} files "
                  f"({(stats['new'] + stats['modified'])/max(stats['total'], 1)*100:.1f}%)")

    # Use files_to_scan from differential for remaining steps
    files_to_scan = diff_result.files_to_scan

    # Step 2e: Smart sampling (V1.5 - zone-based sampling)
    if not args.quiet:
        print("Step 2e/8: Smart sampling...")

    before_sampling = len(files_to_scan)
    sampler = SmartSampler()  # Uses defaults from fingerprint.py

    sampled_files = sampler.filter(files_to_scan)
    sample_ratio = 1 - (len(sampled_files) / before_sampling) if before_sampling > 0 else 0.0

    if not args.quiet:
        if before_sampling > 0:
            print(f"  {before_sampling} → {len(sampled_files)} files "
                  f"(-{sample_ratio*100:.1f}% via zone sampling)")
        else:
            print(f"  No files to sample")

    # Use sampled files for remaining steps
    files_to_process = sampled_files

    # Step 3: Filter collector files to sampled files only (V1.5 - carryover)
    if not args.quiet:
        print("Step 3/8: Filtering to sampled files...")

    # Build set of path_hashes to scan
    hashes_to_scan = set()
    for fp in files_to_process:
        if hasattr(fp, 'path_hash'):
            hashes_to_scan.add(fp.path_hash)

    # Filter collector files to only those needing scan
    original_count = len(result.files)
    filtered_files = []

    for file_meta in result.files:
        file_path = file_meta.path if hasattr(file_meta, 'path') else str(file_meta)
        path_hash = hash_path(file_path)
        if path_hash in hashes_to_scan:
            filtered_files.append(file_meta)

    if not args.quiet:
        print(f"  {original_count} collected → {len(filtered_files)} to scan "
              f"(carryover optimization)")

    # Propagate zone from fingerprint to FileMetadata
    for file_meta in filtered_files:
        file_path = file_meta.path if hasattr(file_meta, 'path') else str(file_meta)
        path_hash = hash_path(file_path)
        file_meta.zone = zone_by_path_hash.get(path_hash, "normal")

    # Step 4: Filter exclusions (on sampled files only)
    if not args.quiet:
        print("Step 4/8: Applying exclusions...")

    included, excluded = filter_files(filtered_files, config)

    if not args.quiet:
        print(f"  {len(included)} files included, {len(excluded)} excluded")

    # Step 5: PII scan (on sampled files only)
    pii_by_type = {}
    if not args.no_pii:
        if not args.quiet:
            print("Step 5/8: Scanning for PII...")

        def pii_progress(count, path):
            if not args.quiet and count % 100 == 0:
                print(f"\r  {count} files scanned...", end="", flush=True)

        # Use parallel scan if enabled
        if PARALLEL_SCAN:
            included, pii_by_type = scan_files_for_pii_parallel(included, pii_progress)
        else:
            included, pii_by_type = scan_files_for_pii(included, pii_progress)

        if not args.quiet:
            print(f"\r  PII scan complete: {len(included)} files")
    else:
        if not args.quiet:
            print("Step 5/8: PII scan skipped")

    # Step 6: Merge with unchanged files (V1.5 - carryover PII)
    if not args.quiet:
        print("Step 6/8: Merging with unchanged files...")

    unchanged_count = len(diff_result.files_unchanged)
    unchanged_with_pii = 0

    # Count unchanged files with previous PII
    for fp in diff_result.files_unchanged:
        if hasattr(fp, 'previous_pii') and fp.previous_pii:
            unchanged_with_pii += 1

    if not args.quiet:
        print(f"  {unchanged_count} unchanged files (carryover)")
        if unchanged_with_pii > 0:
            print(f"  {unchanged_with_pii} unchanged files had PII (reused)")

    # Step 7: Save snapshot (V1.5 - for next differential audit)
    if not args.quiet:
        print("Step 7/8: Saving snapshot...")

    source_name = primary_path.name or "unknown"  # FIX (Sprint 29): Use primary_path, not last scan_path
    snapshot_saved = save_snapshot(
        source_path=str(primary_path),  # FIX (Sprint 29): Use primary_path, not last scan_path
        source_name=source_name,
        fingerprints=all_fingerprints,  # Save ALL fingerprints, not just scanned
        scores=None  # Agent doesn't compute scores (Hub only)
    )

    if not args.quiet:
        if snapshot_saved:
            print(f"  Snapshot saved to cloud ({len(all_fingerprints)} files)")
        else:
            print("  Snapshot not saved (cloud not configured)")

    duration = (datetime.now() - start_time).total_seconds()

    # Compute scan metadata for Hub (D148-D157)
    total_reduction = 1 - (len(included) / max(original_count, 1))
    is_differential = not diff_result.is_first_audit

    # Disk usage of scanned path
    import shutil as _shutil
    try:
        _disk = _shutil.disk_usage(str(primary_path))
        disk_total_bytes, disk_free_bytes = _disk.total, _disk.free
    except Exception:
        disk_total_bytes, disk_free_bytes = 0, 0

    # Agent identity
    import platform as _platform
    agent_hostname = _platform.node()
    agent_os = _platform.system()

    # Create output
    output = create_scan_output(
        source_path=str(primary_path),  # FIX (Sprint 29): Use primary_path
        scanned_paths=scanned_paths_array,  # NEW (Sprint 29): All paths
        scanned_paths_count=scanned_paths_count,  # NEW (Sprint 29): Path count
        files=included,
        excluded_files=excluded,
        pii_by_type=pii_by_type,
        config=config,
        errors=result.errors
    )

    # Enrich summary with scan metadata (D148-D157)
    output.summary.scan_duration_seconds = round(duration, 2)
    output.summary.dedup_ratio = round(dedup_ratio, 4)
    output.summary.unchanged_files_count = unchanged_count
    output.summary.disk_total_bytes = disk_total_bytes
    output.summary.disk_free_bytes = disk_free_bytes
    output.summary.zone_distribution = dict(fp_stats['by_zone']) if all_fingerprints else None
    output.summary.total_reduction_percent = round(total_reduction, 4)
    output.summary.original_files_count = original_count
    output.summary.sample_ratio = round(sample_ratio, 4)
    output.summary.is_differential = is_differential

    # Agent identity (bugfix — colonnes existantes en Railway)
    output.agent_hostname = agent_hostname
    output.agent_os = agent_os

    # Output results
    if args.json:
        # JSON to stdout
        print(export_to_string(output, pretty=True))
    else:
        # Summary to stdout
        files_with_pii = sum(1 for f in included if f.pii_detected)

        if not args.quiet:
            print()
            print("=== SCAN COMPLETE ===")
            print(f"  Duration: {duration:.1f}s")
            print(f"  Files collected: {original_count}")
            print(f"  Files scanned: {len(included)} (after optimizations)")
            if unchanged_count > 0:
                print(f"  Unchanged files: {unchanged_count} (carryover)")
            print(f"  Overall reduction: {total_reduction*100:.1f}%")
            print(f"  Files excluded: {len(excluded)}")
            print(f"  Total size: {output.summary.total_size_bytes / 1024 / 1024:.1f} MB")
            print(f"  Files with PII: {files_with_pii}")
            if pii_by_type:
                print(f"  PII by type: {pii_by_type}")

        # Export to file
        if scanned_paths_count == 1:
            output_path = args.output or generate_output_filename(str(primary_path))
        else:
            output_path = args.output or generate_output_filename_multipath(
                primary_path=str(primary_path),
                paths_count=scanned_paths_count
            )
        export_to_json(output, output_path)

        if not args.quiet:
            print()
            print(f"Output saved to: {output_path}")

    return 0


# =============================================================================
# ONEDRIVE SCAN (Sprint 35)
# =============================================================================

def run_list_drives(args) -> int:
    """
    List available OneDrive/SharePoint drives and exit.

    Sprint 35: Used by UI to populate drive selector.
    """
    import asyncio
    import json

    try:
        from agent.core.onedrive_collector import OneDriveCollector
    except ImportError:
        from core.onedrive_collector import OneDriveCollector

    async def _list_drives():
        collector = OneDriveCollector(
            tenant_id=args.tenant_id,
            client_id=args.client_id,
            client_secret=args.client_secret
        )

        try:
            if not await collector.authenticate():
                return {"error": "Authentication failed", "drives": []}

            drives = await collector.list_drives()
            return {"drives": drives, "count": len(drives)}

        finally:
            await collector.close()

    try:
        result = asyncio.run(_list_drives())
        print(json.dumps(result))
        return 0 if "error" not in result else 1

    except Exception as e:
        print(json.dumps({"error": str(e), "drives": []}))
        return 1


def run_onedrive_scan(args) -> int:
    """
    Run OneDrive/SharePoint cloud scan.

    Sprint 35: Cloud data path using Microsoft Graph API.
    """
    import asyncio
    import uuid
    import json

    # Validate required arguments
    if not args.tenant_id or not args.client_id or not args.client_secret:
        print("Error: --onedrive requires --tenant-id, --client-id, and --client-secret", file=sys.stderr)
        print("  Example: python -m agent.main --onedrive --tenant-id xxx --client-id yyy --client-secret zzz", file=sys.stderr)
        return 1

    # Check dependencies
    if not check_cloud_dependencies():
        print("Error: Cloud dependencies not installed.", file=sys.stderr)
        print("  Run: pip install msal aiohttp", file=sys.stderr)
        return 1

    start_time = datetime.now()

    if not args.quiet:
        print(f"Apollo Agent v{VERSION} - OneDrive Scanner")
        print(f"Drive: {args.drive_id}")
        print(f"Path: {args.onedrive_path}")
        print()

    # Run async collection
    async def do_scan():
        try:
            from agent.core.onedrive_collector import OneDriveCollector, CloudCollectorResult, CloudFileMetadata
        except ImportError:
            from core.onedrive_collector import OneDriveCollector, CloudCollectorResult, CloudFileMetadata

        def progress(count, name):
            if not args.quiet and count % 100 == 0:
                print(f"\r  {count} files collected...", end="", flush=True)

        # Handle "all" drive_id - scan ALL available drives (opt-out pattern)
        if args.drive_id == "all":
            collector = OneDriveCollector(
                tenant_id=args.tenant_id,
                client_id=args.client_id,
                client_secret=args.client_secret,
                fetch_permissions=getattr(args, 'fetch_permissions', False)
            )

            if not await collector.authenticate():
                return CloudCollectorResult(source_type="cloud", error="Authentication failed")

            # Get all drives
            drives = await collector.list_drives()
            if not drives:
                await collector.close()
                return CloudCollectorResult(source_type="cloud", error="No drives found")

            if not args.quiet:
                print(f"  Scanning ALL {len(drives)} drives...")

            # Collect from all drives
            all_files = []
            total_size = 0
            shared_count = 0
            errors = []

            for i, drive in enumerate(drives):
                drive_id = drive.get("id")
                drive_name = drive.get("name", "Unknown")
                if not args.quiet:
                    print(f"\n  [{i+1}/{len(drives)}] Scanning: {drive_name}")

                try:
                    result = await collector.collect_files(
                        drive_id=drive_id,
                        folder_path=args.onedrive_path,
                        max_files=args.max_files // len(drives),  # Distribute limit
                        progress_callback=progress
                    )
                    all_files.extend(result.files)
                    total_size += result.total_size
                    shared_count += result.shared_files_count
                    if result.errors:
                        errors.extend(result.errors)
                except Exception as e:
                    errors.append(f"Drive {drive_name}: {str(e)}")

            await collector.close()

            return CloudCollectorResult(
                source_type="cloud",
                source_subtype="sharepoint",  # Multi-drive = SharePoint
                drive_id="all",
                tenant_id=args.tenant_id,
                root_path=args.onedrive_path,
                files=all_files,
                total_size=total_size,
                shared_files_count=shared_count,
                errors=errors if errors else None
            )
        else:
            # Single drive scan
            result = await collect_onedrive_files(
                tenant_id=args.tenant_id,
                client_id=args.client_id,
                client_secret=args.client_secret,
                drive_id=args.drive_id,
                folder_path=args.onedrive_path,
                max_files=args.max_files,
                progress_callback=progress,
                fetch_permissions=getattr(args, 'fetch_permissions', False)
            )
            return result

    result = asyncio.run(do_scan())

    if not args.quiet:
        print()

    if result.error:
        print(f"Error: {result.error}", file=sys.stderr)
        return 1

    # Build cloud-specific output
    scan_id = str(uuid.uuid4())
    timestamp = datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")

    # =========================================================================
    # Sprint 85: Cloud PII Scan — download content → extract text → scan PII
    # =========================================================================
    files_with_pii = 0
    pii_by_type = {}
    file_pii_results = {}  # {cloud_id: PIIScanResult}

    # Identify extractible files
    extractible_exts = {
        '.csv', '.txt', '.json', '.xml', '.html', '.htm',
        '.md', '.rst', '.log', '.sql', '.yaml', '.yml',
        '.xlsx', '.xls',
        '.py', '.js', '.ts', '.ini', '.cfg', '.conf', '.env', '.properties'
    }
    extractible_files = [
        f for f in result.files
        if f.extension.lower() in extractible_exts
        and f.size <= MAX_DOWNLOAD_BYTES
        and f.cloud_id
    ]

    if extractible_files and not args.quiet:
        print(f"  Scanning {len(extractible_files)} extractible files for PII...")

    # Async download + PII scan with rate limiting
    async def scan_cloud_pii():
        nonlocal files_with_pii

        try:
            from core.onedrive_collector import OneDriveCollector
        except ImportError:
            from agent.core.onedrive_collector import OneDriveCollector

        collector = OneDriveCollector(
            tenant_id=args.tenant_id,
            client_id=args.client_id,
            client_secret=args.client_secret
        )

        if not await collector.authenticate():
            print("  [PII] Warning: auth failed for content download", file=sys.stderr)
            return

        import logging
        pii_logger = logging.getLogger("agent.cloud_pii")

        sem = asyncio.Semaphore(5)  # Max 5 concurrent downloads
        scanned = 0
        scan_errors = {}

        async def scan_one(f):
            nonlocal scanned, files_with_pii
            async with sem:
                try:
                    content_bytes = await collector.download_file_content(
                        drive_id=f.drive_id or args.drive_id,
                        file_id=f.cloud_id,
                        max_bytes=MAX_DOWNLOAD_BYTES
                    )
                    # DIAG: log download result for every file
                    pii_logger.warning(f"[DIAG] {f.name}: download={'OK ' + str(len(content_bytes)) + 'B' if content_bytes else 'EMPTY'} (drive={f.drive_id}, id={f.cloud_id[:12] if f.cloud_id else 'None'})")
                    if not content_bytes:
                        scan_errors[f.name] = "download_empty"
                        return

                    text = extract_text_from_bytes(content_bytes, f.extension)
                    # DIAG: log extraction result
                    pii_logger.warning(f"[DIAG] {f.name}: extract={'OK ' + str(len(text)) + ' chars' if text else 'NONE'} ({len(content_bytes)}B, ext={f.extension})")
                    if not text:
                        scan_errors[f.name] = f"extraction_failed ({len(content_bytes)}B, ext={f.extension})"
                        return

                    pii_result = scan_text_for_pii(text, f.path)
                    # DIAG: log PII result for every file
                    pii_logger.warning(f"[DIAG] {f.name}: pii={pii_result.pii_count} has_pii={pii_result.has_pii} types={pii_result.pii_types}")
                    if pii_result.has_pii:
                        file_pii_results[f.cloud_id] = pii_result
                        files_with_pii += 1
                        for pt in pii_result.pii_types:
                            pii_by_type[pt] = pii_by_type.get(pt, 0) + 1

                    scanned += 1
                    if not args.quiet and scanned % 10 == 0:
                        print(f"\r  [PII] {scanned}/{len(extractible_files)} files scanned...", end="", flush=True)

                except Exception as e:
                    scan_errors[f.name] = f"exception: {e}"
                    pii_logger.error(f"[DIAG] {f.name}: EXCEPTION {type(e).__name__}: {e}")

        tasks = [scan_one(f) for f in extractible_files]
        await asyncio.gather(*tasks)
        await collector.close()

        if scan_errors:
            pii_logger.warning(f"[PII] {len(scan_errors)} files failed: {scan_errors}")
        if not args.quiet:
            msg = f"\n  [PII] Scan complete: {files_with_pii}/{scanned} files with PII detected"
            if scan_errors:
                msg += f" ({len(scan_errors)} errors: {', '.join(scan_errors.keys())})"
            print(msg)

    scan_errors = {}
    if extractible_files:
        asyncio.run(scan_cloud_pii())

    # Build output compatible with Hub Cloud
    cloud_output = {
        "source_type": "cloud",
        "version": VERSION,
        "scan_id": scan_id,
        "timestamp": timestamp,
        "source_path": f"onedrive://{args.drive_id}{args.onedrive_path}",
        "cloud_metadata": {
            "source_subtype": result.source_subtype,
            "tenant_id": result.tenant_id,
            "drive_id": result.drive_id
        },
        "summary": {
            "total_files": len(result.files),
            "total_size_bytes": result.total_size,
            "files_with_pii": files_with_pii,
            "pii_by_type": pii_by_type,
            "shared_files_count": result.shared_files_count,
            "excluded_count": 0,
            "error_count": len(result.errors) if result.errors else 0,
            "scan_errors": scan_errors if scan_errors else {},
            # Sprint 35: Cloud metadata required by Hub AgentCloudSummary
            "source_subtype": result.source_subtype,
            "drive_id": result.drive_id,
            "tenant_id": result.tenant_id
        },
        "files": [],
        "config_used": {
            "max_files": args.max_files,
            "max_file_mb": 10000000,
            "min_file_bytes": 0,
            "extensions_excluded": [],
            "path_patterns": [],
            "filename_patterns": [],
            "drive_id": args.drive_id,
            "folder_path": args.onedrive_path
        },
        "errors": result.errors
    }

    # Build files list with PII results (Sprint 85)
    for f in result.files:
        pii_result = file_pii_results.get(f.cloud_id)
        cloud_output["files"].append({
            "path": f.path,
            "relative_path": f.relative_path,
            "name": f.name,
            "extension": f.extension,
            "size": f.size,
            "mtime": f.mtime,
            "depth": f.depth,
            "item_id": f.cloud_id,  # Map cloud_id to item_id for Hub
            "drive_id": f.drive_id,
            "web_url": f.web_url,
            "is_shared": f.is_shared,
            "shared_scope": f.shared_scope,
            "shared_with": f.shared_with if hasattr(f, 'shared_with') and f.shared_with else [],
            # Sprint 86B: Graph API fields (parsed in onedrive_collector, now serialized)
            "ctime": f.ctime,
            "file_hash_sha1": f.file_hash_sha1,
            "mime_type": f.mime_type,
            "etag": f.etag,
            "ctag": f.ctag,
            "malware_detected": f.malware_detected,
            "malware_description": f.malware_description,
            "deleted_state": f.deleted_state,
            "created_by": f.created_by,
            "modified_by": f.modified_by,
            "retention_label": f.retention_label if hasattr(f, 'retention_label') else None,
            # PII detection (Sprint 85)
            "pii_detected": pii_result.has_pii if pii_result else False,
            "pii_types": pii_result.pii_types if pii_result else [],
            "pii_count": pii_result.pii_count if pii_result else 0
        })

    duration = (datetime.now() - start_time).total_seconds()

    # Output
    if args.json:
        print(json.dumps(cloud_output, indent=2))
    else:
        if not args.quiet:
            print()
            print("=== ONEDRIVE SCAN COMPLETE ===")
            print(f"  Duration: {duration:.1f}s")
            print(f"  Files collected: {len(result.files)}")
            print(f"  Total size: {result.total_size / 1024 / 1024:.1f} MB")
            print(f"  Shared files: {result.shared_files_count}")

        # Export to file
        output_path = args.output or f"onedrive_scan_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(cloud_output, f, indent=2, ensure_ascii=False)

        if not args.quiet:
            print()
            print(f"Output saved to: {output_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
