//! Batch file stat operations
//!
//! Provides parallel stat() calls for file metadata retrieval

use pyo3::prelude::*;
use rayon::prelude::*;
use std::fs;
use std::path::Path;
use std::time::UNIX_EPOCH;

/// File stat result tuple: (path, size, mtime)
pub type StatResult = (String, u64, f64);

/// Get file stats (size, mtime) for multiple files in parallel
///
/// # Arguments
/// * `paths` - List of file paths
///
/// # Returns
/// List of tuples (path, size_bytes, mtime_unix_timestamp)
/// Only returns entries for files that could be stat'd successfully
///
/// # Example
/// ```python
/// from apollo_io_native import stat_files_batch
/// stats = stat_files_batch(["/path/to/file1", "/path/to/file2"])
/// for path, size, mtime in stats:
///     print(f"{path}: {size} bytes, modified {mtime}")
/// ```
#[pyfunction]
pub fn stat_files_batch(
    py: Python<'_>,
    paths: Vec<String>,
) -> PyResult<Vec<StatResult>> {
    // Release GIL during I/O
    py.allow_threads(|| {
        stat_files_parallel(paths)
    })
}

/// Parallel stat implementation using rayon
fn stat_files_parallel(paths: Vec<String>) -> PyResult<Vec<StatResult>> {
    let results: Vec<StatResult> = paths
        .par_iter()
        .filter_map(|path| stat_single_file(path))
        .collect();

    Ok(results)
}

/// Stat a single file
fn stat_single_file(path: &str) -> Option<StatResult> {
    let path_obj = Path::new(path);

    // Get metadata
    let metadata = fs::metadata(path_obj).ok()?;

    // Skip directories
    if !metadata.is_file() {
        return None;
    }

    // Get size
    let size = metadata.len();

    // Get mtime as Unix timestamp
    let mtime = metadata
        .modified()
        .ok()?
        .duration_since(UNIX_EPOCH)
        .ok()?
        .as_secs_f64();

    Some((path.to_string(), size, mtime))
}

/// Extended stat with additional metadata
#[pyfunction]
pub fn stat_files_extended(
    py: Python<'_>,
    paths: Vec<String>,
) -> PyResult<Vec<(String, u64, f64, bool, bool)>> {
    py.allow_threads(|| {
        let results: Vec<_> = paths
            .par_iter()
            .filter_map(|path| {
                let path_obj = Path::new(path);
                let metadata = fs::metadata(path_obj).ok()?;

                if !metadata.is_file() {
                    return None;
                }

                let size = metadata.len();
                let mtime = metadata
                    .modified()
                    .ok()?
                    .duration_since(UNIX_EPOCH)
                    .ok()?
                    .as_secs_f64();

                let readonly = metadata.permissions().readonly();

                // Check if executable (Unix only)
                #[cfg(unix)]
                let executable = {
                    use std::os::unix::fs::PermissionsExt;
                    metadata.permissions().mode() & 0o111 != 0
                };
                #[cfg(not(unix))]
                let executable = false;

                Some((path.to_string(), size, mtime, readonly, executable))
            })
            .collect();

        Ok(results)
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::Write;
    use tempfile::NamedTempFile;

    #[test]
    fn test_stat_single_file() {
        let mut temp = NamedTempFile::new().unwrap();
        temp.write_all(b"Hello, World!").unwrap();
        let path = temp.path().to_str().unwrap();

        let result = stat_single_file(path);
        assert!(result.is_some());

        let (_, size, mtime) = result.unwrap();
        assert_eq!(size, 13); // "Hello, World!" = 13 bytes
        assert!(mtime > 0.0);
    }

    #[test]
    fn test_stat_files_parallel() {
        let mut temps = Vec::new();
        let mut paths = Vec::new();

        for i in 0..10 {
            let mut temp = NamedTempFile::new().unwrap();
            write!(temp, "Content {}", i).unwrap();
            paths.push(temp.path().to_str().unwrap().to_string());
            temps.push(temp);
        }

        let results = stat_files_parallel(paths).unwrap();
        assert_eq!(results.len(), 10);
    }
}
