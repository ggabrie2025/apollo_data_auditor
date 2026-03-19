#!/usr/bin/env python3
"""
Test owner_domain sur Windows Server
Valide RAW_COLLECTION_SPEC_V1 - champ owner_domain (4 bytes)
"""

import apollo_io_native as aio
import os

print("=" * 50)
print("TEST owner_domain - RAW_COLLECTION_SPEC_V1")
print("=" * 50)

# 1. Verify struct size
size = aio.raw_metadata_size()
print(f"\n1. Struct size: {size} bytes")
assert size == 156, f"FAILED: Expected 156, got {size}"
print("   OK")

# 2. Test system files (should have owner_domain if AD joined)
test_paths = [
    r"C:\Windows\System32\config\SAM",
    r"C:\Windows\System32\drivers\etc\hosts",
    r"C:\Users\Administrator\NTUSER.DAT",
    r"C:\Program Files",
]

print("\n2. Testing owner_domain on system files:")
for path in test_paths:
    if os.path.exists(path):
        try:
            raw = aio.collect_raw_metadata(path, zone=1)
            meta = aio.parse_raw_metadata(raw)
            print(f"   {path}")
            print(f"      owner_domain: {meta['owner_domain']} (hex: {meta['owner_domain']:08x})")
            print(f"      size: {meta['size']}, mode: {meta['mode']}")
        except Exception as e:
            print(f"   {path} - ERROR: {e}")
    else:
        print(f"   {path} - NOT FOUND")

# 3. Batch test on C:\Users
print("\n3. Batch scan C:\\Users (first 50 files):")
files = []
for root, dirs, filenames in os.walk(r"C:\Users"):
    for f in filenames:
        files.append(os.path.join(root, f))
        if len(files) >= 50:
            break
    if len(files) >= 50:
        break

if files:
    batch = aio.collect_raw_batch(files)
    print(f"   Collected: {len(batch)} files")

    # Check owner_domain distribution
    domains = {}
    for raw in batch:
        meta = aio.parse_raw_metadata(raw)
        od = meta['owner_domain']
        domains[od] = domains.get(od, 0) + 1

    print(f"   Unique owner_domains: {len(domains)}")
    for od, count in sorted(domains.items(), key=lambda x: -x[1])[:5]:
        print(f"      {od:08x}: {count} files")

# 4. Summary
print("\n" + "=" * 50)
print("VALIDATION:")
print("- Si owner_domain = 0 partout: VM non jointe AD (normal)")
print("- Si owner_domain != 0: AD domain hash detecte")
print("=" * 50)
