//! Apollo I/O Native - High-performance I/O and Fingerprint module
//!
//! This module provides native Rust acceleration for:
//! - Parallel file reading (tokio async)
//! - Directory walking (walkdir)
//! - File stat batching
//! - xxhash64 fingerprinting
//! - BloomFilter for deduplication
//!
//! Designed as optional dependency for Apollo Agent v1.7+

use pyo3::prelude::*;

mod reader;
mod walker;
mod stat;
mod hasher;
mod bloom;
mod fingerprint;
mod platform;
mod raw_collector;

use reader::read_files_batch;
use walker::walk_directory;
use stat::stat_files_batch;
use hasher::{hash_files_xxhash, xxhash64_string, hash_path};
use fingerprint::{fingerprint_batch, deduplicate_fingerprints, fingerprint_stats, Fingerprint};
use bloom::BloomFilterWrapper;
use platform::{get_platform_info, is_io_uring_available, optimal_batch_size};
use raw_collector::{collect_raw_metadata, collect_raw_batch, parse_raw_metadata, raw_metadata_size};

/// Apollo I/O Native Python Module
///
/// Provides high-performance I/O operations with automatic fallback
/// to Python implementation if this module is not available.
#[pymodule]
fn apollo_io_native(m: &Bound<'_, PyModule>) -> PyResult<()> {
    // I/O functions
    m.add_function(wrap_pyfunction!(read_files_batch, m)?)?;
    m.add_function(wrap_pyfunction!(walk_directory, m)?)?;
    m.add_function(wrap_pyfunction!(stat_files_batch, m)?)?;

    // Hash functions
    m.add_function(wrap_pyfunction!(hash_files_xxhash, m)?)?;
    m.add_function(wrap_pyfunction!(xxhash64_string, m)?)?;
    m.add_function(wrap_pyfunction!(hash_path, m)?)?;

    // Fingerprint
    m.add_function(wrap_pyfunction!(fingerprint_batch, m)?)?;
    m.add_function(wrap_pyfunction!(deduplicate_fingerprints, m)?)?;
    m.add_function(wrap_pyfunction!(fingerprint_stats, m)?)?;
    m.add_class::<Fingerprint>()?;

    // BloomFilter
    m.add_class::<BloomFilterWrapper>()?;

    // Platform info
    m.add_function(wrap_pyfunction!(get_platform_info, m)?)?;
    m.add_function(wrap_pyfunction!(is_io_uring_available, m)?)?;
    m.add_function(wrap_pyfunction!(optimal_batch_size, m)?)?;

    // Raw Collector (RAW_COLLECTION_SPEC_V1)
    m.add_function(wrap_pyfunction!(collect_raw_metadata, m)?)?;
    m.add_function(wrap_pyfunction!(collect_raw_batch, m)?)?;
    m.add_function(wrap_pyfunction!(parse_raw_metadata, m)?)?;
    m.add_function(wrap_pyfunction!(raw_metadata_size, m)?)?;

    // Module metadata
    m.add("__version__", "0.1.0")?;
    m.add("__author__", "Apollo Team")?;

    Ok(())
}
