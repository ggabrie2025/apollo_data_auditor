//! Parallel file reader using tokio async runtime
//!
//! Provides high-performance batch file reading with:
//! - Configurable worker count
//! - Memory-efficient streaming
//! - Automatic error handling

use pyo3::prelude::*;
use pyo3::types::PyBytes;
use std::path::Path;
use std::sync::Arc;
use tokio::fs::File;
use tokio::io::AsyncReadExt;
use tokio::sync::Semaphore;

/// Read multiple files in parallel using tokio async runtime
///
/// # Arguments
/// * `paths` - List of file paths to read
/// * `max_bytes` - Maximum bytes to read per file (default: 65536)
/// * `workers` - Number of concurrent workers (default: 8)
///
/// # Returns
/// List of tuples (path, content) for successfully read files
///
/// # Example
/// ```python
/// from apollo_io_native import read_files_batch
/// results = read_files_batch(["/path/to/file1", "/path/to/file2"], 65536, 8)
/// for path, content in results:
///     print(f"{path}: {len(content)} bytes")
/// ```
#[pyfunction]
#[pyo3(signature = (paths, max_bytes=65536, workers=8))]
pub fn read_files_batch(
    py: Python<'_>,
    paths: Vec<String>,
    max_bytes: usize,
    workers: usize,
) -> PyResult<Vec<(String, Py<PyBytes>)>> {
    // Clamp workers to reasonable range
    let workers = workers.clamp(1, 32);

    // Release GIL during I/O operations
    let results = py.allow_threads(|| {
        read_files_async(paths, max_bytes, workers)
    })?;

    // Convert to Python bytes
    let py_results: Vec<(String, Py<PyBytes>)> = results
        .into_iter()
        .map(|(path, content)| {
            let py_bytes = PyBytes::new_bound(py, &content).unbind();
            (path, py_bytes)
        })
        .collect();

    Ok(py_results)
}

/// Internal async implementation
fn read_files_async(
    paths: Vec<String>,
    max_bytes: usize,
    workers: usize,
) -> PyResult<Vec<(String, Vec<u8>)>> {
    // Create tokio runtime
    let rt = tokio::runtime::Builder::new_multi_thread()
        .worker_threads(workers)
        .enable_all()
        .build()
        .map_err(|e| PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(
            format!("Failed to create tokio runtime: {}", e)
        ))?;

    // Run async read operations
    let results = rt.block_on(async {
        let semaphore = Arc::new(Semaphore::new(workers * 4));
        let mut handles = Vec::with_capacity(paths.len());

        for path in paths {
            let sem = semaphore.clone();
            let max_bytes = max_bytes;

            handles.push(tokio::spawn(async move {
                let _permit = sem.acquire().await.ok()?;
                read_single_file(&path, max_bytes).await
            }));
        }

        let mut results = Vec::with_capacity(handles.len());
        for handle in handles {
            if let Ok(Some((path, content))) = handle.await {
                results.push((path, content));
            }
        }
        results
    });

    Ok(results)
}

/// Read a single file asynchronously
async fn read_single_file(path: &str, max_bytes: usize) -> Option<(String, Vec<u8>)> {
    let path_obj = Path::new(path);

    // Skip if not a file
    if !path_obj.is_file() {
        return None;
    }

    // Open file
    let mut file = File::open(path_obj).await.ok()?;

    // Read up to max_bytes
    let mut buffer = vec![0u8; max_bytes];
    let bytes_read = file.read(&mut buffer).await.ok()?;
    buffer.truncate(bytes_read);

    Some((path.to_string(), buffer))
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::Write;
    use tempfile::NamedTempFile;

    #[test]
    fn test_read_single_file() {
        let rt = tokio::runtime::Runtime::new().unwrap();

        // Create temp file
        let mut temp = NamedTempFile::new().unwrap();
        temp.write_all(b"Hello, World!").unwrap();
        let path = temp.path().to_str().unwrap().to_string();

        // Read it
        let result = rt.block_on(read_single_file(&path, 1024));
        assert!(result.is_some());

        let (_, content) = result.unwrap();
        assert_eq!(content, b"Hello, World!");
    }

    #[test]
    fn test_read_files_async() {
        // Create temp files
        let mut temps = Vec::new();
        let mut paths = Vec::new();

        for i in 0..5 {
            let mut temp = NamedTempFile::new().unwrap();
            write!(temp, "Content {}", i).unwrap();
            paths.push(temp.path().to_str().unwrap().to_string());
            temps.push(temp);
        }

        // Read all
        let results = read_files_async(paths, 1024, 4).unwrap();
        assert_eq!(results.len(), 5);
    }
}
