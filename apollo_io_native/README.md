# Apollo I/O Native

High-performance Rust module for Apollo Agent file scanning and fingerprinting.

## Features

- **Parallel File Reading** - tokio async I/O with configurable workers
- **Directory Walking** - Fast recursive enumeration with walkdir
- **Batch Stat** - Parallel file metadata retrieval with rayon
- **xxHash64 Hashing** - 3x faster than MD5, 10x faster than SHA256
- **BloomFilter** - O(1) deduplication with 10M capacity
- **Fingerprinting** - Lightweight metadata-only fingerprints

## Performance Gains

| Operation | Python | Rust | Gain |
|-----------|--------|------|------|
| File I/O (Linux) | baseline | +200% | 3x |
| File I/O (Windows) | baseline | +160% | 2.6x |
| xxHash | baseline | +300% | 4x |
| BloomFilter | baseline | +150% | 2.5x |
| **Global Scan** | baseline | **+70%** | 1.7x |

## Installation

### Prerequisites

```bash
# Install Rust
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh

# Install maturin
pip install maturin
```

### Build from source

```bash
cd apollo_io_native

# Development build (fast, for testing)
maturin develop

# Release build (optimized)
maturin build --release
pip install target/wheels/apollo_io_native-*.whl
```

## Usage

### Basic I/O

```python
from apollo_io_native import read_files_batch, walk_directory, stat_files_batch

# Walk directory
paths = walk_directory("/data", max_depth=10, skip_hidden=True)
print(f"Found {len(paths)} files")

# Read files in parallel
contents = read_files_batch(paths[:1000], max_bytes=65536, workers=8)
for path, data in contents:
    print(f"{path}: {len(data)} bytes")

# Get file stats
stats = stat_files_batch(paths)
for path, size, mtime in stats:
    print(f"{path}: {size} bytes, modified {mtime}")
```

### Hashing

```python
from apollo_io_native import hash_files_xxhash, xxhash64_string, hash_path

# Hash files
hashes = hash_files_xxhash(paths, max_bytes=0, workers=8)
for path, hash_hex in hashes:
    print(f"{path}: {hash_hex}")

# Hash a string
h = xxhash64_string("Hello, World!", seed=0)
print(f"Hash: {h}")

# Hash a path (for fingerprint)
path_hash = hash_path("/path/to/file.csv")
```

### BloomFilter

```python
from apollo_io_native import BloomFilterWrapper

# Create filter (10M capacity, 0.1% false positive rate)
bloom = BloomFilterWrapper(capacity=10_000_000, fp_rate=0.001)

# Add items
bloom.add("item1")
bloom.add_batch(["item2", "item3", "item4"])

# Check membership
if bloom.contains("item1"):
    print("item1 is probably in the set")

# Deduplication: get new items only
items = ["item1", "new_item1", "item2", "new_item2"]
new_items = bloom.filter_new(items)
print(f"New items: {new_items}")

# Check and add in one operation
is_new = bloom.check_and_add("item5")

# Stats
print(f"Count: {bloom.len()}")
print(f"Memory: {bloom.memory_bytes() / 1_000_000:.2f} MB")
```

### Fingerprinting

```python
from apollo_io_native import fingerprint_batch, deduplicate_fingerprints, fingerprint_stats

# Generate fingerprints
fingerprints = fingerprint_batch(paths)

for fp in fingerprints[:5]:
    print(f"{fp.path_hash}: {fp.size} bytes, zone={fp.zone}, ext={fp.extension}")

# Deduplicate by (size, extension)
unique = deduplicate_fingerprints(fingerprints)
print(f"Dedup: {len(fingerprints)} -> {len(unique)} ({100 - len(unique)*100/len(fingerprints):.1f}% removed)")

# Get statistics
stats = fingerprint_stats(fingerprints)
print(f"Total: {stats['total']} files, {stats['total_size_mb']:.2f} MB")
print(f"By zone: {stats['by_zone']}")
```

### Platform Info

```python
from apollo_io_native import get_platform_info, is_io_uring_available

info = get_platform_info()
print(f"OS: {info['os']}")
print(f"I/O Method: {info['io_method']}")
print(f"CPU Count: {info['cpu_count']}")
print(f"Recommended I/O workers: {info['recommended_io_workers']}")

if is_io_uring_available():
    print("io_uring is available (Linux 5.1+)")
```

## API Reference

### I/O Functions

| Function | Description |
|----------|-------------|
| `read_files_batch(paths, max_bytes, workers)` | Read files in parallel |
| `walk_directory(root, max_depth, skip_hidden)` | Recursive directory listing |
| `stat_files_batch(paths)` | Get file metadata in parallel |

### Hash Functions

| Function | Description |
|----------|-------------|
| `hash_files_xxhash(paths, max_bytes, workers)` | Hash files with xxHash64 |
| `xxhash64_string(data, seed)` | Hash a string |
| `xxhash64_bytes(data, seed)` | Hash bytes |
| `hash_path(path)` | Hash a path string |

### BloomFilter

| Method | Description |
|--------|-------------|
| `BloomFilterWrapper(capacity, fp_rate)` | Create new filter |
| `.add(item)` | Add single item |
| `.add_batch(items)` | Add multiple items |
| `.contains(item)` | Check membership |
| `.filter_new(items)` | Get items not in filter |
| `.check_and_add(item)` | Check and add atomically |
| `.len()` | Get item count |
| `.clear()` | Reset filter |
| `.memory_bytes()` | Get memory usage |

### Fingerprint

| Function | Description |
|----------|-------------|
| `fingerprint_batch(paths)` | Generate fingerprints |
| `deduplicate_fingerprints(fps)` | Remove duplicates |
| `fingerprint_stats(fps)` | Get statistics |

### Platform

| Function | Description |
|----------|-------------|
| `get_platform_info()` | Get runtime info |
| `is_io_uring_available()` | Check io_uring support |
| `optimal_batch_size(memory_mb)` | Calculate batch size |

## Fallback

If this module is not installed, Apollo Agent automatically falls back to Python implementation:

```python
try:
    from apollo_io_native import read_files_batch
    NATIVE_AVAILABLE = True
except ImportError:
    from agent.core.mmap_reader import read_files_mmap as read_files_batch
    NATIVE_AVAILABLE = False
```

## License

MIT License - Apollo Team
