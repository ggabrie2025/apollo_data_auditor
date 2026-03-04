# Apollo IO Native - Build Guide

## Module Info

- **Type:** PyO3 Python Extension Module (cdylib)
- **Python:** 3.13+
- **Rust:** 1.93+

## Build Instructions

### Prerequisites

```bash
# Install Rust
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
source ~/.cargo/env

# Install maturin
pip3 install maturin
```

### Build

**IMPORTANT:** `cargo test` NE FONCTIONNE PAS directement car c'est un module PyO3 extension.

```bash
# Correct: Use maturin
cd apollo_io_native
maturin build --release

# Output: target/wheels/apollo_io_native-*.whl
```

### Install

```bash
# Python 3.13 (Homebrew)
/opt/homebrew/opt/python@3.13/bin/python3.13 -m pip install \
    target/wheels/apollo_io_native-0.1.0-cp313-cp313-macosx_11_0_arm64.whl \
    --force-reinstall --break-system-packages
```

### Test

```python
import apollo_io_native as aio

# Platform info
print(aio.get_platform_info())

# Hash
print(aio.xxhash64_string("test", 0))

# BloomFilter
bf = aio.BloomFilterWrapper(1000, 0.01)
bf.add("key")
print(bf.contains("key"))  # True

# Walk directory
files = aio.walk_directory("/tmp", 10)
print(f"Found {len(files)} files")
```

## Probleme Resolu (2026-01-28)

### Erreur

```
cargo test
error: linking with `cc` failed: exit status: 1
Undefined symbols for architecture arm64:
  "_PyBytes_AsString", "_PyErr_GetRaisedException", ...
```

### Cause

PyO3 avec feature `extension-module` attend que les symboles Python soient resolus au runtime (quand Python charge le module), pas au link time.

`cargo test` essaie de linker un binaire standalone, ce qui echoue car les symboles Python ne sont pas disponibles.

### Solution

Utiliser `maturin build` au lieu de `cargo build/test`:

```bash
# WRONG
cargo test  # Linker error

# CORRECT
maturin build --release
python3 -c "import apollo_io_native; print('OK')"
```

## Available Functions

| Function | Description |
|----------|-------------|
| `get_platform_info()` | OS, arch, version, features |
| `optimal_batch_size()` | Recommended batch size for I/O |
| `xxhash64_string(s, seed)` | Hash string with xxhash64 |
| `hash_files_xxhash(paths)` | Batch hash files |
| `walk_directory(path, depth)` | Fast directory listing |
| `stat_files_batch(paths)` | Batch file stats |
| `BloomFilterWrapper(cap, fp)` | Probabilistic set membership |
| `fingerprint_batch(paths)` | Generate file fingerprints |
| `deduplicate_fingerprints(fps)` | Remove duplicates |
| `collect_raw_metadata(path, zone)` | RAW_COLLECTION_SPEC_V1 - 156 bytes/file |
| `collect_raw_batch(paths, zones)` | Parallel raw metadata collection |
| `parse_raw_metadata(data)` | Parse 156 bytes to dict |
| `raw_metadata_size()` | Returns 156 |

## Performance

| Operation | Python | Rust | Speedup |
|-----------|--------|------|---------|
| Fingerprint 10K files | 3.2s | 0.098s | **32.7x** |
| BloomFilter 100K ops | 1.37s | 0.1s | **13.7x** |
| Raw metadata 156 bytes | N/A | Native | Cross-platform |

## RAW_COLLECTION_SPEC_V1 (2026-01-28)

```python
import apollo_io_native as aio

# Verify struct size
assert aio.raw_metadata_size() == 156

# Collect single file (156 bytes)
raw = aio.collect_raw_metadata("/path/to/file", zone=5)

# Parse back to dict
meta = aio.parse_raw_metadata(raw)
print(f"Size: {meta['size']}, Entropy: {meta['entropy']:.2f}")

# Batch collection (parallel with rayon)
files = ["/file1", "/file2", "/file3"]
zones = [1, 2, 3]
batch = aio.collect_raw_batch(files, zones)
```

**Reference:** `docs/technical/RAW_COLLECTION_SPEC_V1.md`

---

**Version:** 0.1.0
**Date:** 2026-01-28
