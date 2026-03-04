//! Directory walker using walkdir crate
//!
//! Provides high-performance recursive directory enumeration

use pyo3::prelude::*;
use std::path::Path;
use walkdir::WalkDir;

/// Walk a directory recursively and return all file paths
///
/// # Arguments
/// * `root` - Root directory path
/// * `max_depth` - Maximum recursion depth (default: 100)
/// * `skip_hidden` - Skip hidden files/directories (default: true)
///
/// # Returns
/// List of absolute file paths
///
/// # Example
/// ```python
/// from apollo_io_native import walk_directory
/// paths = walk_directory("/data", max_depth=10)
/// print(f"Found {len(paths)} files")
/// ```
#[pyfunction]
#[pyo3(signature = (root, max_depth=100, skip_hidden=true))]
pub fn walk_directory(
    py: Python<'_>,
    root: String,
    max_depth: usize,
    skip_hidden: bool,
) -> PyResult<Vec<String>> {
    // Release GIL during I/O
    py.allow_threads(|| {
        walk_directory_sync(&root, max_depth, skip_hidden)
    })
}

/// Synchronous directory walk implementation
fn walk_directory_sync(
    root: &str,
    max_depth: usize,
    skip_hidden: bool,
) -> PyResult<Vec<String>> {
    let root_path = Path::new(root);

    if !root_path.exists() {
        return Err(PyErr::new::<pyo3::exceptions::PyFileNotFoundError, _>(
            format!("Directory not found: {}", root)
        ));
    }

    if !root_path.is_dir() {
        return Err(PyErr::new::<pyo3::exceptions::PyNotADirectoryError, _>(
            format!("Not a directory: {}", root)
        ));
    }

    let mut paths = Vec::new();

    let walker = WalkDir::new(root)
        .max_depth(max_depth)
        .follow_links(false)
        .into_iter()
        .filter_entry(|e| {
            if skip_hidden {
                // Skip hidden files/dirs (starting with .)
                !e.file_name()
                    .to_str()
                    .map(|s| s.starts_with('.'))
                    .unwrap_or(false)
            } else {
                true
            }
        });

    for entry in walker.filter_map(|e| e.ok()) {
        if entry.file_type().is_file() {
            if let Some(path_str) = entry.path().to_str() {
                paths.push(path_str.to_string());
            }
        }
    }

    Ok(paths)
}

/// Walk directory and return file count only (faster for counting)
#[pyfunction]
#[pyo3(signature = (root, max_depth=100, skip_hidden=true))]
pub fn count_files(
    py: Python<'_>,
    root: String,
    max_depth: usize,
    skip_hidden: bool,
) -> PyResult<usize> {
    py.allow_threads(|| {
        let root_path = Path::new(&root);

        if !root_path.exists() || !root_path.is_dir() {
            return Ok(0);
        }

        let walker = WalkDir::new(&root)
            .max_depth(max_depth)
            .follow_links(false)
            .into_iter()
            .filter_entry(|e| {
                if skip_hidden {
                    !e.file_name()
                        .to_str()
                        .map(|s| s.starts_with('.'))
                        .unwrap_or(false)
                } else {
                    true
                }
            });

        let count = walker
            .filter_map(|e| e.ok())
            .filter(|e| e.file_type().is_file())
            .count();

        Ok(count)
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::fs::{self, File};
    use tempfile::TempDir;

    #[test]
    fn test_walk_directory() {
        // Create temp directory structure
        let temp_dir = TempDir::new().unwrap();
        let root = temp_dir.path();

        // Create files
        File::create(root.join("file1.txt")).unwrap();
        File::create(root.join("file2.txt")).unwrap();

        // Create subdirectory with files
        fs::create_dir(root.join("subdir")).unwrap();
        File::create(root.join("subdir/file3.txt")).unwrap();

        // Walk
        let root_str = root.to_str().unwrap().to_string();
        let paths = walk_directory_sync(&root_str, 100, false).unwrap();

        assert_eq!(paths.len(), 3);
    }

    #[test]
    fn test_skip_hidden() {
        let temp_dir = TempDir::new().unwrap();
        let root = temp_dir.path();

        File::create(root.join("visible.txt")).unwrap();
        File::create(root.join(".hidden")).unwrap();

        let root_str = root.to_str().unwrap().to_string();

        // With skip_hidden = true
        let paths = walk_directory_sync(&root_str, 100, true).unwrap();
        assert_eq!(paths.len(), 1);

        // With skip_hidden = false
        let paths = walk_directory_sync(&root_str, 100, false).unwrap();
        assert_eq!(paths.len(), 2);
    }
}
