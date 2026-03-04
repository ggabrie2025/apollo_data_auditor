//! Platform detection and info
//!
//! Provides runtime platform information for debugging and optimization

use pyo3::prelude::*;
use pyo3::types::PyDict;

/// Get platform information
///
/// # Returns
/// Dictionary with platform details:
/// - os: Operating system name
/// - arch: CPU architecture
/// - io_method: I/O method used (tokio, io_uring, etc.)
/// - version: Module version
/// - features: Enabled features
///
/// # Example
/// ```python
/// from apollo_io_native import get_platform_info
/// info = get_platform_info()
/// print(f"Running on {info['os']} with {info['io_method']}")
/// ```
#[pyfunction]
pub fn get_platform_info(py: Python<'_>) -> PyResult<PyObject> {
    let dict = PyDict::new_bound(py);

    // OS
    dict.set_item("os", std::env::consts::OS)?;

    // Architecture
    dict.set_item("arch", std::env::consts::ARCH)?;

    // OS Family
    dict.set_item("os_family", std::env::consts::FAMILY)?;

    // I/O method
    let io_method = get_io_method();
    dict.set_item("io_method", io_method)?;

    // Module version
    dict.set_item("version", env!("CARGO_PKG_VERSION"))?;

    // Features
    let features = get_enabled_features();
    dict.set_item("features", features)?;

    // CPU count
    dict.set_item("cpu_count", num_cpus())?;

    // Recommended workers
    dict.set_item("recommended_io_workers", recommended_io_workers())?;
    dict.set_item("recommended_cpu_workers", recommended_cpu_workers())?;

    Ok(dict.into())
}

/// Get the I/O method used on this platform
fn get_io_method() -> &'static str {
    #[cfg(all(target_os = "linux", feature = "io_uring"))]
    {
        "io_uring"
    }

    #[cfg(all(target_os = "linux", not(feature = "io_uring")))]
    {
        "tokio-epoll"
    }

    #[cfg(target_os = "macos")]
    {
        "tokio-kqueue"
    }

    #[cfg(target_os = "windows")]
    {
        "tokio-iocp"
    }

    #[cfg(not(any(target_os = "linux", target_os = "macos", target_os = "windows")))]
    {
        "tokio-poll"
    }
}

/// Get list of enabled features
fn get_enabled_features() -> Vec<&'static str> {
    let mut features = vec!["pyo3", "tokio", "rayon", "xxhash", "bloomfilter"];

    #[cfg(feature = "io_uring")]
    features.push("io_uring");

    features
}

/// Get CPU count
fn num_cpus() -> usize {
    std::thread::available_parallelism()
        .map(|p| p.get())
        .unwrap_or(4)
}

/// Recommended I/O workers (for network/disk bound operations)
fn recommended_io_workers() -> usize {
    let cpus = num_cpus();
    // I/O bound: can use more workers than CPUs
    (cpus * 2).min(32)
}

/// Recommended CPU workers (for compute bound operations)
fn recommended_cpu_workers() -> usize {
    let cpus = num_cpus();
    // CPU bound: use N-1 or N-2 to leave room for system
    (cpus.saturating_sub(1)).max(1).min(16)
}

/// Check if io_uring is available (Linux only)
#[pyfunction]
pub fn is_io_uring_available() -> bool {
    #[cfg(all(target_os = "linux", feature = "io_uring"))]
    {
        true
    }

    #[cfg(not(all(target_os = "linux", feature = "io_uring")))]
    {
        false
    }
}

/// Get optimal batch size based on available memory
#[pyfunction]
#[pyo3(signature = (available_memory_mb=None))]
pub fn optimal_batch_size(available_memory_mb: Option<usize>) -> usize {
    let memory_mb = available_memory_mb.unwrap_or(4096); // Default 4GB

    // Assume ~1KB per file metadata in batch
    // Use 10% of available memory for batching
    let batch_memory_mb = memory_mb / 10;
    let batch_size = batch_memory_mb * 1024; // KB to files

    batch_size.clamp(1000, 100_000)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_io_method() {
        let method = get_io_method();
        assert!(!method.is_empty());
    }

    #[test]
    fn test_features() {
        let features = get_enabled_features();
        assert!(features.contains(&"pyo3"));
        assert!(features.contains(&"tokio"));
    }

    #[test]
    fn test_num_cpus() {
        let cpus = num_cpus();
        assert!(cpus >= 1);
    }

    #[test]
    fn test_optimal_batch_size() {
        let batch_4gb = optimal_batch_size(Some(4096));
        let batch_1gb = optimal_batch_size(Some(1024));

        assert!(batch_4gb > batch_1gb);
        assert!(batch_4gb >= 1000);
        assert!(batch_4gb <= 100_000);
    }
}
