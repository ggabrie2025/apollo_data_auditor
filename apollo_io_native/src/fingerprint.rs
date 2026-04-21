//! File fingerprinting module
//!
//! Generates lightweight fingerprints based on file metadata
//! Compatible with Python agent fingerprint.py

use pyo3::prelude::*;
use rayon::prelude::*;
use std::collections::HashSet;
use std::fs;
use std::path::Path;
use std::time::UNIX_EPOCH;
use xxhash_rust::xxh64::xxh64;

/// Sensitive zone keywords (business directories)
const SENSITIVE_ZONES: &[&str] = &[
    "rh", "hr", "clients", "customers", "customer", "finance", "legal",
    "juridique", "personnel", "paie", "salaires", "salaire", "wages",
    "contracts", "contrats", "confidential", "confidentiel", "private", "prive"
];

/// Archive zone keywords
const ARCHIVE_ZONES: &[&str] = &[
    "backup", "archive", "old", "archives", "backups", "historique",
    "history", "trash", "temp", "tmp", "cache"
];

/// File fingerprint - lightweight metadata-only fingerprint
#[pyclass]
#[derive(Clone, Debug)]
pub struct Fingerprint {
    #[pyo3(get)]
    pub path_hash: String,

    #[pyo3(get)]
    pub size: u64,

    #[pyo3(get)]
    pub mtime: f64,

    #[pyo3(get)]
    pub extension: String,

    #[pyo3(get)]
    pub zone: String,

    #[pyo3(get)]
    pub path: String,
}

#[pymethods]
impl Fingerprint {
    #[new]
    pub fn new(
        path_hash: String,
        size: u64,
        mtime: f64,
        extension: String,
        zone: String,
        path: String,
    ) -> Self {
        Fingerprint {
            path_hash,
            size,
            mtime,
            extension,
            zone,
            path,
        }
    }

    /// Convert to dictionary
    pub fn to_dict(&self, py: Python<'_>) -> PyResult<PyObject> {
        let dict = pyo3::types::PyDict::new(py);
        dict.set_item("path_hash", &self.path_hash)?;
        dict.set_item("size", self.size)?;
        dict.set_item("mtime", self.mtime)?;
        dict.set_item("extension", &self.extension)?;
        dict.set_item("zone", &self.zone)?;
        dict.set_item("path", &self.path)?;
        Ok(dict.into())
    }

    /// Dedup key: (size, extension) - used for grouping duplicates
    pub fn dedup_key(&self) -> String {
        format!("{}:{}", self.size, self.extension)
    }

    fn __repr__(&self) -> String {
        format!(
            "Fingerprint(path_hash='{}...', size={}, zone='{}')",
            &self.path_hash[..8.min(self.path_hash.len())],
            self.size,
            self.zone
        )
    }
}

/// Generate fingerprints for multiple files in parallel
///
/// # Arguments
/// * `paths` - List of file paths
///
/// # Returns
/// List of Fingerprint objects
///
/// # Example
/// ```python
/// from apollo_io_native import fingerprint_batch, Fingerprint
/// fingerprints = fingerprint_batch(["/path/to/file1", "/path/to/file2"])
/// for fp in fingerprints:
///     print(f"{fp.path_hash}: {fp.size} bytes, zone={fp.zone}")
/// ```
#[pyfunction]
pub fn fingerprint_batch(
    py: Python<'_>,
    paths: Vec<String>,
) -> PyResult<Vec<Fingerprint>> {
    py.allow_threads(|| {
        fingerprint_parallel(paths)
    })
}

/// Parallel fingerprint generation
fn fingerprint_parallel(paths: Vec<String>) -> PyResult<Vec<Fingerprint>> {
    let results: Vec<Fingerprint> = paths
        .par_iter()
        .filter_map(|path| generate_fingerprint(path))
        .collect();

    Ok(results)
}

/// Generate fingerprint for a single file
fn generate_fingerprint(path: &str) -> Option<Fingerprint> {
    let path_obj = Path::new(path);

    // Get metadata
    let metadata = fs::metadata(path_obj).ok()?;

    // Skip directories
    if !metadata.is_file() {
        return None;
    }

    // Path hash (xxhash64)
    let path_hash = format!("{:016x}", xxh64(path.as_bytes(), 0));

    // Size
    let size = metadata.len();

    // Mtime
    let mtime = metadata
        .modified()
        .ok()?
        .duration_since(UNIX_EPOCH)
        .ok()?
        .as_secs_f64();

    // Extension
    let extension = path_obj
        .extension()
        .and_then(|e| e.to_str())
        .map(|e| format!(".{}", e.to_lowercase()))
        .unwrap_or_else(|| ".no_ext".to_string());

    // Zone detection
    let zone = detect_zone(path);

    Some(Fingerprint {
        path_hash,
        size,
        mtime,
        extension,
        zone,
        path: path.to_string(),
    })
}

/// System paths to ignore for zone detection
const SYSTEM_PATHS: &[&str] = &[
    "private", "var", "folders", "tmp", "users", "home", "root"
];

/// Detect zone based on path keywords
fn detect_zone(path: &str) -> String {
    let path_lower = path.to_lowercase();
    let parts: HashSet<&str> = Path::new(&path_lower)
        .components()
        .filter_map(|c| c.as_os_str().to_str())
        // Skip system path components
        .filter(|p| !SYSTEM_PATHS.contains(p))
        .collect();

    // Priority: sensitive > archive > normal
    for zone in SENSITIVE_ZONES {
        if parts.contains(zone) {
            return "sensitive".to_string();
        }
    }

    for zone in ARCHIVE_ZONES {
        if parts.contains(zone) {
            return "archive".to_string();
        }
    }

    "normal".to_string()
}

/// Deduplicate fingerprints by (size, extension)
///
/// Returns one representative per group, prioritizing sensitive zones
#[pyfunction]
pub fn deduplicate_fingerprints(
    py: Python<'_>,
    fingerprints: Vec<Fingerprint>,
) -> PyResult<Vec<Fingerprint>> {
    py.allow_threads(|| {
        deduplicate_impl(fingerprints)
    })
}

/// Deduplication implementation
fn deduplicate_impl(fingerprints: Vec<Fingerprint>) -> PyResult<Vec<Fingerprint>> {
    use std::collections::HashMap;

    let mut groups: HashMap<String, Vec<Fingerprint>> = HashMap::new();

    // Group by dedup key
    for fp in fingerprints {
        let key = fp.dedup_key();
        groups.entry(key).or_default().push(fp);
    }

    // Select representative from each group
    // Priority: sensitive > normal > archive
    let zone_priority = |zone: &str| -> i32 {
        match zone {
            "sensitive" => 0,
            "normal" => 1,
            "archive" => 2,
            _ => 1,
        }
    };

    let representatives: Vec<Fingerprint> = groups
        .into_values()
        .map(|mut group| {
            group.sort_by_key(|fp| zone_priority(&fp.zone));
            group.remove(0)
        })
        .collect();

    Ok(representatives)
}

/// Get fingerprint statistics
#[pyfunction]
pub fn fingerprint_stats(
    py: Python<'_>,
    fingerprints: Vec<Fingerprint>,
) -> PyResult<PyObject> {
    let total = fingerprints.len();
    let total_size: u64 = fingerprints.iter().map(|fp| fp.size).sum();

    let mut by_zone: std::collections::HashMap<String, usize> = std::collections::HashMap::new();
    let mut by_extension: std::collections::HashMap<String, usize> = std::collections::HashMap::new();

    for fp in &fingerprints {
        *by_zone.entry(fp.zone.clone()).or_default() += 1;
        *by_extension.entry(fp.extension.clone()).or_default() += 1;
    }

    let dict = pyo3::types::PyDict::new(py);
    dict.set_item("total", total)?;
    dict.set_item("total_size_bytes", total_size)?;
    dict.set_item("total_size_mb", total_size as f64 / 1_000_000.0)?;

    let zone_dict = pyo3::types::PyDict::new(py);
    for (k, v) in by_zone {
        zone_dict.set_item(k, v)?;
    }
    dict.set_item("by_zone", zone_dict)?;

    // Top 10 extensions
    let mut ext_vec: Vec<_> = by_extension.into_iter().collect();
    ext_vec.sort_by(|a, b| b.1.cmp(&a.1));
    ext_vec.truncate(10);

    let ext_dict = pyo3::types::PyDict::new(py);
    for (k, v) in ext_vec {
        ext_dict.set_item(k, v)?;
    }
    dict.set_item("by_extension_top10", ext_dict)?;

    Ok(dict.into())
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::Write;
    use tempfile::NamedTempFile;

    #[test]
    fn test_detect_zone() {
        assert_eq!(detect_zone("/data/rh/employees.csv"), "sensitive");
        assert_eq!(detect_zone("/data/clients/list.xlsx"), "sensitive");
        assert_eq!(detect_zone("/backup/old/data.zip"), "archive");
        assert_eq!(detect_zone("/data/reports/monthly.pdf"), "normal");
    }

    #[test]
    fn test_generate_fingerprint() {
        let mut temp = NamedTempFile::new().unwrap();
        temp.write_all(b"Hello, World!").unwrap();
        let path = temp.path().to_str().unwrap();

        let fp = generate_fingerprint(path);
        assert!(fp.is_some());

        let fp = fp.unwrap();
        assert_eq!(fp.size, 13);
        assert_eq!(fp.path_hash.len(), 16);
    }

    #[test]
    fn test_dedup_key() {
        let fp = Fingerprint::new(
            "abc123".to_string(),
            1024,
            1234567890.0,
            ".csv".to_string(),
            "normal".to_string(),
            "/path/to/file.csv".to_string(),
        );

        assert_eq!(fp.dedup_key(), "1024:.csv");
    }
}
