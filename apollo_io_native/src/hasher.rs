//! xxHash64 file hashing
//!
//! Provides high-performance file hashing using xxHash algorithm
//! xxHash is ~3x faster than MD5 and ~10x faster than SHA256

use pyo3::prelude::*;
use rayon::prelude::*;
use std::fs::File;
use std::io::Read;
use std::path::Path;
use xxhash_rust::xxh64::{xxh64, Xxh64};

/// Buffer size for streaming hash (64KB - optimal for SSD)
const HASH_BUFFER_SIZE: usize = 64 * 1024;

/// Hash type alias
pub type HashResult = (String, String);

/// Compute xxHash64 for multiple files in parallel
///
/// # Arguments
/// * `paths` - List of file paths
/// * `max_bytes` - Maximum bytes to read for hashing (0 = entire file)
/// * `workers` - Number of parallel workers
///
/// # Returns
/// List of tuples (path, hash_hex_string)
///
/// # Example
/// ```python
/// from apollo_io_native import hash_files_xxhash
/// hashes = hash_files_xxhash(["/path/to/file1", "/path/to/file2"])
/// for path, hash_hex in hashes:
///     print(f"{path}: {hash_hex}")
/// ```
#[pyfunction]
#[pyo3(signature = (paths, max_bytes=0, workers=8))]
pub fn hash_files_xxhash(
    py: Python<'_>,
    paths: Vec<String>,
    max_bytes: usize,
    workers: usize,
) -> PyResult<Vec<HashResult>> {
    // Configure rayon thread pool
    let _ = rayon::ThreadPoolBuilder::new()
        .num_threads(workers.clamp(1, 32))
        .build_global();

    // Release GIL during computation
    py.allow_threads(|| {
        hash_files_parallel(paths, max_bytes)
    })
}

/// Parallel hash implementation
fn hash_files_parallel(paths: Vec<String>, max_bytes: usize) -> PyResult<Vec<HashResult>> {
    let results: Vec<HashResult> = paths
        .par_iter()
        .filter_map(|path| hash_single_file(path, max_bytes))
        .collect();

    Ok(results)
}

/// Hash a single file using streaming (no OOM on large files)
fn hash_single_file(path: &str, max_bytes: usize) -> Option<HashResult> {
    let path_obj = Path::new(path);

    if !path_obj.is_file() {
        return None;
    }

    let mut file = File::open(path_obj).ok()?;

    let hash = if max_bytes > 0 {
        // Read only first N bytes (small buffer OK)
        let mut buffer = vec![0u8; max_bytes];
        let bytes_read = file.read(&mut buffer).ok()?;
        buffer.truncate(bytes_read);
        xxh64(&buffer, 0)
    } else {
        // Streaming hash - fixed 64KB buffer (no OOM)
        let mut hasher = Xxh64::new(0);
        let mut buffer = [0u8; HASH_BUFFER_SIZE];

        loop {
            let bytes_read = file.read(&mut buffer).ok()?;
            if bytes_read == 0 {
                break;
            }
            hasher.update(&buffer[..bytes_read]);
        }

        hasher.digest()
    };

    let hash_hex = format!("{:016x}", hash);
    Some((path.to_string(), hash_hex))
}

/// Compute xxHash64 for raw bytes (utility function)
#[pyfunction]
pub fn xxhash64_bytes(data: &[u8], seed: u64) -> u64 {
    xxh64(data, seed)
}

/// Compute xxHash64 for a string
#[pyfunction]
pub fn xxhash64_string(data: &str, seed: u64) -> String {
    let hash = xxh64(data.as_bytes(), seed);
    format!("{:016x}", hash)
}

/// Hash a path string (for fingerprint path_hash)
#[pyfunction]
pub fn hash_path(path: &str) -> String {
    let hash = xxh64(path.as_bytes(), 0);
    format!("{:016x}", hash)
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::Write;
    use tempfile::NamedTempFile;

    #[test]
    fn test_hash_single_file() {
        let mut temp = NamedTempFile::new().unwrap();
        temp.write_all(b"Hello, World!").unwrap();
        let path = temp.path().to_str().unwrap();

        let result = hash_single_file(path, 0);
        assert!(result.is_some());

        let (_, hash) = result.unwrap();
        assert_eq!(hash.len(), 16); // 64 bits = 16 hex chars
    }

    #[test]
    fn test_hash_partial() {
        let mut temp = NamedTempFile::new().unwrap();
        temp.write_all(b"Hello, World! This is a longer content.").unwrap();
        let path = temp.path().to_str().unwrap();

        // Hash first 5 bytes only
        let result = hash_single_file(path, 5);
        assert!(result.is_some());

        let (_, hash_partial) = result.unwrap();

        // Hash entire file
        let result_full = hash_single_file(path, 0);
        let (_, hash_full) = result_full.unwrap();

        // Should be different
        assert_ne!(hash_partial, hash_full);
    }

    #[test]
    fn test_xxhash64_string() {
        let hash1 = xxhash64_string("hello", 0);
        let hash2 = xxhash64_string("hello", 0);
        let hash3 = xxhash64_string("world", 0);

        assert_eq!(hash1, hash2); // Same input = same hash
        assert_ne!(hash1, hash3); // Different input = different hash
    }

    #[test]
    fn test_hash_path() {
        let hash = hash_path("/path/to/file.txt");
        assert_eq!(hash.len(), 16);
    }

    #[test]
    fn test_streaming_hash_consistency() {
        // Create file larger than buffer size to test streaming
        let mut temp = NamedTempFile::new().unwrap();
        let large_content: Vec<u8> = (0..100_000).map(|i| (i % 256) as u8).collect();
        temp.write_all(&large_content).unwrap();
        let path = temp.path().to_str().unwrap();

        // Hash with streaming (full file)
        let result = hash_single_file(path, 0);
        assert!(result.is_some());

        let (_, hash_streaming) = result.unwrap();

        // Verify hash is deterministic (same content = same hash)
        let result2 = hash_single_file(path, 0);
        let (_, hash_streaming2) = result2.unwrap();
        assert_eq!(hash_streaming, hash_streaming2);

        // Verify hash length
        assert_eq!(hash_streaming.len(), 16);
    }
}
