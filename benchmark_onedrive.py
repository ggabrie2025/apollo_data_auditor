#!/usr/bin/env python3
"""
SPRINT_61 - Benchmark OneDrive/SharePoint
==========================================

Compare Python vs Rust Hybrid performance on cloud I/O.
Network latency should reveal Rust async benefits.

Usage:
    python benchmark_onedrive.py
"""
import asyncio
import os
import sys
import time
from pathlib import Path

# Add agent to path
sys.path.insert(0, str(Path(__file__).parent))

# Credentials from environment (required)
TENANT_ID = os.environ.get("AZURE_TENANT_ID")
CLIENT_ID = os.environ.get("AZURE_CLIENT_ID")
CLIENT_SECRET = os.environ.get("AZURE_CLIENT_SECRET")


async def test_onedrive_collection():
    """Test OneDrive collection with metrics."""
    from agent.core.onedrive_collector import OneDriveCollector

    print("=" * 60)
    print("SPRINT_61 - OneDrive/SharePoint Benchmark")
    print("=" * 60)

    # Initialize collector
    collector = OneDriveCollector(
        tenant_id=TENANT_ID,
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET
    )

    # Authenticate
    print("\n[1/4] Authenticating with Microsoft Graph API...")
    t0 = time.perf_counter()
    auth_ok = await collector.authenticate()
    auth_time = time.perf_counter() - t0

    if not auth_ok:
        print("   FAILED: Authentication error")
        return
    print(f"   OK ({auth_time:.3f}s)")

    # List available drives
    print("\n[2/4] Listing SharePoint drives...")
    t0 = time.perf_counter()
    drives = await collector.list_drives()
    list_time = time.perf_counter() - t0
    print(f"   Found {len(drives)} drives ({list_time:.3f}s)")

    if not drives:
        print("   No drives found - check app permissions")
        await collector.close()
        return

    # Show drives
    print("\n   Available drives:")
    for i, d in enumerate(drives[:5]):
        print(f"   [{i+1}] {d['name']} ({d['driveType']})")
    if len(drives) > 5:
        print(f"   ... and {len(drives) - 5} more")

    # Collect from first drive
    drive_id = drives[0]["id"]
    drive_name = drives[0]["name"]

    print(f"\n[3/4] Collecting files from: {drive_name}")

    collected_count = 0
    def progress(count, filename):
        nonlocal collected_count
        collected_count = count
        if count % 500 == 0:
            print(f"   Progress: {count} files...")

    t0 = time.perf_counter()
    result = await collector.collect_files(
        drive_id=drive_id,
        folder_path="/",
        max_files=50000,  # Limit for test
        progress_callback=progress
    )
    collect_time = time.perf_counter() - t0

    print(f"   Collected: {len(result.files)} files")
    print(f"   Total size: {result.total_size / 1_000_000:.1f} MB")
    print(f"   Shared files: {result.shared_files_count}")
    print(f"   Time: {collect_time:.3f}s")

    if result.files:
        rate = len(result.files) / collect_time
        print(f"   Rate: {rate:.0f} files/sec")

    # Now test fingerprinting with Rust vs Python
    print("\n[4/4] Fingerprint Benchmark (Rust vs Python)")
    print("-" * 40)

    # Create paths from cloud files (simulated)
    cloud_paths = [f.path for f in result.files[:5000]]  # Limit to 5000

    if cloud_paths:
        # Test Rust fingerprint backend
        from agent.core.fingerprint_backend import (
            get_backend,
            BloomFilterWrapper,
            xxhash64_string
        )

        backend = get_backend()
        print(f"\n   Backend: {backend}")

        # Benchmark: BloomFilter
        print("\n   BloomFilter benchmark (Rust vs Python):")

        # Rust BloomFilter
        if "rust" in backend.lower():
            bloom_rust = BloomFilterWrapper(capacity=100_000, fp_rate=0.001)
            t0 = time.perf_counter()
            for p in cloud_paths:
                bloom_rust.add(p)
            rust_add_time = time.perf_counter() - t0

            t0 = time.perf_counter()
            hits = sum(1 for p in cloud_paths if bloom_rust.contains(p))
            rust_check_time = time.perf_counter() - t0

            print(f"   Rust BloomFilter:")
            print(f"     Add {len(cloud_paths)} items: {rust_add_time*1000:.2f}ms")
            print(f"     Check {len(cloud_paths)} items: {rust_check_time*1000:.2f}ms ({hits} hits)")
            print(f"     Rate: {len(cloud_paths)/rust_add_time/1000:.0f}K ops/sec")

        # Python pybloom (force Python backend for comparison)
        try:
            from pybloom_live import BloomFilter
            bloom_py = BloomFilter(capacity=100_000, error_rate=0.001)

            t0 = time.perf_counter()
            for p in cloud_paths:
                bloom_py.add(p)
            py_add_time = time.perf_counter() - t0

            t0 = time.perf_counter()
            hits_py = sum(1 for p in cloud_paths if p in bloom_py)
            py_check_time = time.perf_counter() - t0

            print(f"\n   Python pybloom:")
            print(f"     Add {len(cloud_paths)} items: {py_add_time*1000:.2f}ms")
            print(f"     Check {len(cloud_paths)} items: {py_check_time*1000:.2f}ms ({hits_py} hits)")
            print(f"     Rate: {len(cloud_paths)/py_add_time/1000:.0f}K ops/sec")

            if "rust" in backend.lower():
                speedup = py_add_time / rust_add_time
                print(f"\n   Rust speedup: {speedup:.1f}x faster")

        except ImportError:
            print("   pybloom_live not available for comparison")

        # XXHash benchmark
        print("\n   XXHash benchmark:")

        t0 = time.perf_counter()
        hashes = [xxhash64_string(p) for p in cloud_paths]
        hash_time = time.perf_counter() - t0

        print(f"   Hash {len(cloud_paths)} strings: {hash_time*1000:.2f}ms")
        print(f"   Rate: {len(cloud_paths)/hash_time/1000:.0f}K hashes/sec")

    # Cleanup
    await collector.close()

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Total files collected: {len(result.files)}")
    print(f"Total time: {auth_time + list_time + collect_time:.2f}s")
    print(f"Network I/O time: {collect_time:.2f}s ({len(result.files)/collect_time:.0f} files/sec)")

    if result.error:
        print(f"\nErrors: {result.error}")

    return result


async def benchmark_large_volume():
    """
    Benchmark on large volume - scan multiple SharePoint sites.
    """
    from agent.core.onedrive_collector import OneDriveCollector
    from agent.core.fingerprint_backend import (
        get_backend,
        BloomFilterWrapper,
        fingerprint_batch,
        deduplicate_fingerprints
    )

    print("=" * 60)
    print("SPRINT_61 - Large Volume Benchmark (Multi-Site)")
    print("=" * 60)

    collector = OneDriveCollector(
        tenant_id=TENANT_ID,
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET
    )

    if not await collector.authenticate():
        print("Authentication failed")
        return

    drives = await collector.list_drives()
    if not drives:
        print("No drives available")
        return

    print(f"\nScanning {len(drives)} SharePoint sites...")

    all_files = []
    total_time = 0

    for i, drive in enumerate(drives[:6]):  # Max 6 sites
        print(f"\n[{i+1}/{min(len(drives), 6)}] {drive['name']}")
        t0 = time.perf_counter()

        result = await collector.collect_files(
            drive_id=drive["id"],
            folder_path="/",
            max_files=100000
        )

        elapsed = time.perf_counter() - t0
        total_time += elapsed
        all_files.extend(result.files)

        print(f"   {len(result.files)} files, {result.total_size/1_000_000:.1f}MB ({elapsed:.2f}s)")

    await collector.close()

    print(f"\n{'='*60}")
    print(f"Total collected: {len(all_files)} files")
    print(f"Network I/O time: {total_time:.2f}s")
    print(f"Overall rate: {len(all_files)/total_time:.0f} files/sec")

    # Now benchmark fingerprint operations on collected metadata
    if all_files:
        print(f"\n{'='*60}")
        print("Fingerprint Operations Benchmark")
        print("="*60)

        backend = get_backend()
        print(f"Backend: {backend}")

        # Simulate local paths for fingerprinting
        paths = [f.path for f in all_files]

        # BloomFilter benchmark
        print(f"\nBloomFilter ({len(paths)} items):")
        bloom = BloomFilterWrapper(capacity=len(paths)*2)

        t0 = time.perf_counter()
        bloom.add_batch(paths)
        add_time = time.perf_counter() - t0

        t0 = time.perf_counter()
        new_items = bloom.filter_new(paths)
        filter_time = time.perf_counter() - t0

        print(f"  add_batch: {add_time*1000:.2f}ms ({len(paths)/add_time/1000:.0f}K/sec)")
        print(f"  filter_new: {filter_time*1000:.2f}ms ({len(paths)/filter_time/1000:.0f}K/sec)")

        # Dedup benchmark (simulated fingerprints)
        from agent.core.fingerprint_backend import Fingerprint

        fingerprints = [
            Fingerprint(
                path_hash=f.path[:16] if len(f.path) >= 16 else f.path.ljust(16, '0'),
                size=f.size,
                mtime=f.mtime,
                extension=f.extension or ".no_ext",
                zone="cloud",
                path=f.path
            )
            for f in all_files
        ]

        print(f"\nDedup ({len(fingerprints)} fingerprints):")
        t0 = time.perf_counter()
        deduped = deduplicate_fingerprints(fingerprints)
        dedup_time = time.perf_counter() - t0

        print(f"  Time: {dedup_time*1000:.2f}ms")
        print(f"  Rate: {len(fingerprints)/dedup_time/1000:.0f}K/sec")
        print(f"  Unique: {len(deduped)} / {len(fingerprints)}")


if __name__ == "__main__":
    print("\nRunning OneDrive benchmark...\n")

    # Run basic test
    asyncio.run(test_onedrive_collection())

    print("\n" + "="*60)
    print("Running multi-site large volume benchmark...")
    print("="*60)

    # Run large volume test
    asyncio.run(benchmark_large_volume())
