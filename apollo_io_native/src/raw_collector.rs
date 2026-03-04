//! Raw File Metadata Collector - RAW_COLLECTION_SPEC_V1 Implementation
//!
//! Reference: /Users/admin/Projet_APOLLO_DATA_AUDITOR/docs/technical/RAW_COLLECTION_SPEC_V1.md
//! Target: Windows Server + Linux
//! Struct size: 156 bytes (validated)

use pyo3::prelude::*;
use pyo3::types::{PyBytes, PyDict};
use std::fs;
use std::path::Path;
use std::io::Read;

// SHA256 hashing (import without Digest trait to avoid conflict with PyO3)
use sha2::Sha256;
use sha2::digest::Digest as Sha2Digest;

/// PII Detection Flags (32 bits = 32 types)
/// Reference: RAW_COLLECTION_SPEC_V1.md Section 3.2
pub mod pii_flags {
    pub const EMAIL: u32 = 1 << 0;
    pub const PHONE_FR: u32 = 1 << 1;
    pub const PHONE_INTL: u32 = 1 << 2;
    pub const IBAN: u32 = 1 << 3;
    pub const CREDIT_CARD: u32 = 1 << 4;
    pub const SSN_FR: u32 = 1 << 5;      // NIR
    pub const PASSPORT: u32 = 1 << 6;
    pub const IP_ADDRESS: u32 = 1 << 7;
    pub const MAC_ADDRESS: u32 = 1 << 8;
    pub const DATE_BIRTH: u32 = 1 << 9;
    pub const ADDRESS_FR: u32 = 1 << 10;
    pub const NAME_PATTERN: u32 = 1 << 11;
    pub const MEDICAL_ID: u32 = 1 << 12;
    pub const API_KEY: u32 = 1 << 13;
    pub const PASSWORD_HASH: u32 = 1 << 14;
    pub const JWT_TOKEN: u32 = 1 << 15;
    // 16-31: Reserved for future PII types
}

/// Raw File Metadata - 156 bytes packed struct
///
/// Tier 1: OS Metadata (100 bytes)
/// Tier 2: Content Metadata (52 bytes)
/// + owner_domain (4 bytes)
#[repr(C, packed)]
#[derive(Clone, Copy)]
pub struct RawFileMetadata {
    // Tier 1: OS Metadata (100 bytes)
    pub path_hash: [u8; 32],      // SHA256 of path (anonymized)
    pub size: u64,                 // File size in bytes
    pub mtime: u64,                // Modification time (unix timestamp)
    pub ctime: u64,                // Creation time (unix timestamp)
    pub atime: u64,                // Access time (unix timestamp)
    pub mode: u16,                 // Unix permissions (0 on Windows for basic)
    pub uid: u32,                  // User ID (0 on Windows)
    pub gid: u32,                  // Group ID (0 on Windows)
    pub inode: u64,                // Inode (file_index on Windows)
    pub nlink: u16,                // Hard link count
    pub dev: u32,                  // Device ID
    pub extension: [u8; 8],        // File extension (truncated)
    pub depth: u8,                 // Directory depth
    pub zone: u8,                  // Zone ID (SmartSampler)
    pub is_hidden: u8,             // 1 if hidden, 0 otherwise
    pub is_symlink: u8,            // 1 if symlink, 0 otherwise

    // Tier 2: Content Metadata (52 bytes)
    pub content_hash: [u8; 32],    // SHA256 of first 64KB
    pub magic_bytes: u32,          // First 4 bytes of file
    pub entropy: f32,              // Shannon entropy (0.0-8.0)
    pub is_binary: u8,             // 1 if binary, 0 if text
    pub encoding: u8,              // Encoding ID (0=unknown, 1=utf8, 2=utf16, etc.)
    pub pii_flags: u32,            // Bitmask of detected PII types
    pub pii_count: u16,            // Total PII matches count
    pub pii_density: f32,          // PII matches per KB

    // Added field (validated)
    pub owner_domain: u32,         // xxhash32 of AD domain (0 on Linux)
}

// Compile-time size validation
const _: () = assert!(std::mem::size_of::<RawFileMetadata>() == 156);

impl RawFileMetadata {
    /// Create empty/default metadata
    pub fn empty() -> Self {
        Self {
            path_hash: [0u8; 32],
            size: 0,
            mtime: 0,
            ctime: 0,
            atime: 0,
            mode: 0,
            uid: 0,
            gid: 0,
            inode: 0,
            nlink: 0,
            dev: 0,
            extension: [0u8; 8],
            depth: 0,
            zone: 0,
            is_hidden: 0,
            is_symlink: 0,
            content_hash: [0u8; 32],
            magic_bytes: 0,
            entropy: 0.0,
            is_binary: 0,
            encoding: 0,
            pii_flags: 0,
            pii_count: 0,
            pii_density: 0.0,
            owner_domain: 0,
        }
    }

    /// Serialize to bytes (156 bytes)
    pub fn to_bytes(&self) -> Vec<u8> {
        unsafe {
            let ptr = self as *const Self as *const u8;
            std::slice::from_raw_parts(ptr, 156).to_vec()
        }
    }

    /// Deserialize from bytes
    pub fn from_bytes(data: &[u8]) -> Option<Self> {
        if data.len() < 156 {
            return None;
        }
        unsafe {
            let ptr = data.as_ptr() as *const Self;
            Some(ptr.read_unaligned())
        }
    }
}

/// Collect raw metadata for a single file
///
/// # Arguments
/// * `path` - File path to collect metadata from
/// * `zone` - Zone ID from SmartSampler (0 if unknown)
///
/// # Returns
/// RawFileMetadata struct with all fields populated
pub fn collect_metadata(path: &Path, zone: u8) -> std::io::Result<RawFileMetadata> {
    let mut meta = RawFileMetadata::empty();

    // Path hash (anonymization)
    let path_str = path.to_string_lossy();
    let mut hasher = Sha256::new();
    Sha2Digest::update(&mut hasher, path_str.as_bytes());
    meta.path_hash.copy_from_slice(&hasher.finalize());

    // OS metadata via stat
    let file_meta = fs::symlink_metadata(path)?;

    meta.size = file_meta.len();
    meta.is_symlink = if file_meta.file_type().is_symlink() { 1 } else { 0 };

    // Platform-specific metadata
    #[cfg(unix)]
    {
        use std::os::unix::fs::MetadataExt;
        meta.mtime = file_meta.mtime() as u64;
        meta.ctime = file_meta.ctime() as u64;
        meta.atime = file_meta.atime() as u64;
        meta.mode = file_meta.mode() as u16;
        meta.uid = file_meta.uid();
        meta.gid = file_meta.gid();
        meta.inode = file_meta.ino();
        meta.nlink = file_meta.nlink() as u16;
        meta.dev = file_meta.dev() as u32;
        meta.owner_domain = 0; // No AD on Unix
    }

    #[cfg(windows)]
    {
        use std::os::windows::fs::MetadataExt;
        // Windows timestamps are in 100-nanosecond intervals since 1601
        // Convert to Unix timestamp
        const WINDOWS_TICK: u64 = 10_000_000;
        const SEC_TO_UNIX_EPOCH: u64 = 11_644_473_600;

        let to_unix = |win_time: u64| -> u64 {
            if win_time == 0 { return 0; }
            (win_time / WINDOWS_TICK).saturating_sub(SEC_TO_UNIX_EPOCH)
        };

        meta.mtime = to_unix(file_meta.last_write_time());
        meta.ctime = to_unix(file_meta.creation_time());
        meta.atime = to_unix(file_meta.last_access_time());
        meta.mode = 0; // No Unix permissions on Windows
        meta.uid = 0;
        meta.gid = 0;
        // file_index/number_of_links/volume_serial_number require unstable
        // windows_by_handle feature — use 0 defaults for cross-compilation
        meta.inode = 0;
        meta.nlink = 1;
        meta.dev = 0;

        // Hidden file detection on Windows
        let attrs = file_meta.file_attributes();
        const FILE_ATTRIBUTE_HIDDEN: u32 = 0x2;
        if attrs & FILE_ATTRIBUTE_HIDDEN != 0 {
            meta.is_hidden = 1;
        }

        // owner_domain: TODO - implement AD SID lookup
        // For now, use 0 (will be implemented with windows-rs crate)
        meta.owner_domain = 0;
    }

    // Extension (max 8 bytes)
    if let Some(ext) = path.extension() {
        let ext_str = ext.to_string_lossy();
        let ext_bytes = ext_str.as_bytes();
        let len = std::cmp::min(ext_bytes.len(), 8);
        meta.extension[..len].copy_from_slice(&ext_bytes[..len]);
    }

    // Depth (count path components)
    meta.depth = path.components().count() as u8;

    // Zone from SmartSampler
    meta.zone = zone;

    // Hidden file detection (Unix)
    #[cfg(unix)]
    {
        if let Some(name) = path.file_name() {
            if name.to_string_lossy().starts_with('.') {
                meta.is_hidden = 1;
            }
        }
    }

    // Content analysis (only for regular files, not symlinks)
    if file_meta.is_file() && meta.is_symlink == 0 {
        if let Ok(mut file) = fs::File::open(path) {
            let mut buffer = vec![0u8; 65536]; // 64KB
            let bytes_read = file.read(&mut buffer).unwrap_or(0);

            if bytes_read > 0 {
                let content = &buffer[..bytes_read];

                // Content hash (SHA256 of first 64KB)
                let mut hasher = Sha256::new();
                Sha2Digest::update(&mut hasher, content);
                meta.content_hash.copy_from_slice(&hasher.finalize());

                // Magic bytes (first 4 bytes)
                if bytes_read >= 4 {
                    meta.magic_bytes = u32::from_le_bytes([
                        content[0], content[1], content[2], content[3]
                    ]);
                }

                // Entropy calculation
                meta.entropy = calculate_entropy(content);

                // Binary detection (null byte in first 8KB)
                let check_len = std::cmp::min(bytes_read, 8192);
                meta.is_binary = if content[..check_len].contains(&0) { 1 } else { 0 };

                // Encoding detection
                meta.encoding = detect_encoding(content);

                // PII detection (basic patterns)
                let (flags, count) = detect_pii(content);
                meta.pii_flags = flags;
                meta.pii_count = count;
                meta.pii_density = if bytes_read > 0 {
                    (count as f32) / (bytes_read as f32 / 1024.0)
                } else {
                    0.0
                };
            }
        }
    }

    Ok(meta)
}

/// Calculate Shannon entropy (0.0 = uniform, 8.0 = random/encrypted)
fn calculate_entropy(data: &[u8]) -> f32 {
    if data.is_empty() {
        return 0.0;
    }

    let mut freq = [0u32; 256];
    for &byte in data {
        freq[byte as usize] += 1;
    }

    let len = data.len() as f32;
    let mut entropy: f32 = 0.0;

    for &count in &freq {
        if count > 0 {
            let p = count as f32 / len;
            entropy -= p * p.log2();
        }
    }

    entropy
}

/// Detect encoding from content
/// Returns: 0=unknown, 1=utf8, 2=utf16le, 3=utf16be, 4=ascii, 5=latin1
fn detect_encoding(data: &[u8]) -> u8 {
    if data.is_empty() {
        return 0;
    }

    // Check BOM
    if data.len() >= 3 && data[0] == 0xEF && data[1] == 0xBB && data[2] == 0xBF {
        return 1; // UTF-8 BOM
    }
    if data.len() >= 2 {
        if data[0] == 0xFF && data[1] == 0xFE {
            return 2; // UTF-16 LE
        }
        if data[0] == 0xFE && data[1] == 0xFF {
            return 3; // UTF-16 BE
        }
    }

    // Check if valid UTF-8
    if std::str::from_utf8(data).is_ok() {
        // Check if pure ASCII
        if data.iter().all(|&b| b < 128) {
            return 4; // ASCII
        }
        return 1; // UTF-8
    }

    // Likely Latin-1 or other single-byte encoding
    5
}

/// Detect PII patterns in content
/// Returns: (flags bitmask, total count)
fn detect_pii(data: &[u8]) -> (u32, u16) {
    let mut flags: u32 = 0;
    let mut count: u16 = 0;

    // Convert to string for regex-like matching
    let text = match std::str::from_utf8(data) {
        Ok(s) => s,
        Err(_) => return (0, 0), // Skip binary content
    };

    // Email pattern (simple)
    let email_count = text.matches('@').count();
    if email_count > 0 {
        flags |= pii_flags::EMAIL;
        count += email_count.min(u16::MAX as usize) as u16;
    }

    // French phone (06/07)
    let phone_patterns = ["06 ", "07 ", "06.", "07.", "+33"];
    for pattern in &phone_patterns {
        let matches = text.matches(pattern).count();
        if matches > 0 {
            flags |= pii_flags::PHONE_FR;
            count += matches.min(u16::MAX as usize) as u16;
        }
    }

    // IBAN pattern (FR followed by digits)
    if text.contains("FR") && text.chars().filter(|c| c.is_ascii_digit()).count() > 20 {
        flags |= pii_flags::IBAN;
        count += 1;
    }

    // Credit card (16 consecutive digits or 4x4)
    let digit_sequences: Vec<&str> = text.split(|c: char| !c.is_ascii_digit())
        .filter(|s| s.len() >= 13 && s.len() <= 19)
        .collect();
    if !digit_sequences.is_empty() {
        flags |= pii_flags::CREDIT_CARD;
        count += digit_sequences.len().min(u16::MAX as usize) as u16;
    }

    // API Key patterns
    let api_patterns = ["api_key", "apikey", "api-key", "secret_key", "access_token"];
    for pattern in &api_patterns {
        if text.to_lowercase().contains(pattern) {
            flags |= pii_flags::API_KEY;
            count += 1;
            break;
        }
    }

    // JWT Token pattern
    if text.contains("eyJ") && text.matches('.').count() >= 2 {
        flags |= pii_flags::JWT_TOKEN;
        count += 1;
    }

    (flags, count)
}

// ============ PyO3 Exports ============

/// Collect raw metadata for a single file
///
/// Args:
///     path: File path to analyze
///     zone: Zone ID from SmartSampler (default 0)
///
/// Returns:
///     bytes: 156-byte packed struct
#[pyfunction]
#[pyo3(signature = (path, zone=0))]
pub fn collect_raw_metadata(py: Python<'_>, path: &str, zone: u8) -> PyResult<Py<PyBytes>> {
    let path = Path::new(path);

    match collect_metadata(path, zone) {
        Ok(meta) => Ok(PyBytes::new_bound(py, &meta.to_bytes()).into()),
        Err(e) => Err(pyo3::exceptions::PyIOError::new_err(e.to_string())),
    }
}

/// Collect raw metadata for multiple files in parallel
///
/// Args:
///     paths: List of file paths
///     zones: Optional list of zone IDs (same length as paths)
///
/// Returns:
///     List[bytes]: List of 156-byte packed structs
#[pyfunction]
#[pyo3(signature = (paths, zones=None))]
pub fn collect_raw_batch(
    py: Python<'_>,
    paths: Vec<String>,
    zones: Option<Vec<u8>>,
) -> PyResult<Vec<Py<PyBytes>>> {
    use rayon::prelude::*;

    let zones = zones.unwrap_or_else(|| vec![0; paths.len()]);

    let results: Vec<_> = paths
        .par_iter()
        .zip(zones.par_iter())
        .map(|(path, &zone)| {
            collect_metadata(Path::new(path), zone)
                .map(|m| m.to_bytes())
                .unwrap_or_else(|_| RawFileMetadata::empty().to_bytes())
        })
        .collect();

    Ok(results
        .into_iter()
        .map(|bytes| PyBytes::new_bound(py, &bytes).into())
        .collect())
}

/// Parse raw metadata bytes back to a Python dict
///
/// Args:
///     data: 156-byte packed struct
///
/// Returns:
///     dict: Parsed metadata fields
#[pyfunction]
pub fn parse_raw_metadata(py: Python<'_>, data: &[u8]) -> PyResult<PyObject> {
    let meta = RawFileMetadata::from_bytes(data)
        .ok_or_else(|| pyo3::exceptions::PyValueError::new_err("Invalid data length (expected 156 bytes)"))?;

    let dict = PyDict::new_bound(py);

    // Copy all values to avoid packed struct alignment issues
    // Tier 1: OS
    let path_hash = meta.path_hash;
    let size = meta.size;
    let mtime = meta.mtime;
    let ctime = meta.ctime;
    let atime = meta.atime;
    let mode = meta.mode;
    let uid = meta.uid;
    let gid = meta.gid;
    let inode = meta.inode;
    let nlink = meta.nlink;
    let dev = meta.dev;
    let extension = meta.extension;
    let depth = meta.depth;
    let zone = meta.zone;
    let is_hidden = meta.is_hidden;
    let is_symlink = meta.is_symlink;

    // Tier 2: Content
    let content_hash = meta.content_hash;
    let magic_bytes = meta.magic_bytes;
    let entropy = meta.entropy;
    let is_binary = meta.is_binary;
    let encoding = meta.encoding;
    let pii_flags = meta.pii_flags;
    let pii_count = meta.pii_count;
    let pii_density = meta.pii_density;
    let owner_domain = meta.owner_domain;

    // Set dict items
    dict.set_item("path_hash", hex::encode(path_hash))?;
    dict.set_item("size", size)?;
    dict.set_item("mtime", mtime)?;
    dict.set_item("ctime", ctime)?;
    dict.set_item("atime", atime)?;
    dict.set_item("mode", mode)?;
    dict.set_item("uid", uid)?;
    dict.set_item("gid", gid)?;
    dict.set_item("inode", inode)?;
    dict.set_item("nlink", nlink)?;
    dict.set_item("dev", dev)?;
    dict.set_item("extension", String::from_utf8_lossy(&extension).trim_end_matches('\0').to_string())?;
    dict.set_item("depth", depth)?;
    dict.set_item("zone", zone)?;
    dict.set_item("is_hidden", is_hidden != 0)?;
    dict.set_item("is_symlink", is_symlink != 0)?;

    dict.set_item("content_hash", hex::encode(content_hash))?;
    dict.set_item("magic_bytes", format!("{:08x}", magic_bytes))?;
    dict.set_item("entropy", entropy)?;
    dict.set_item("is_binary", is_binary != 0)?;
    dict.set_item("encoding", encoding)?;
    dict.set_item("pii_flags", pii_flags)?;
    dict.set_item("pii_count", pii_count)?;
    dict.set_item("pii_density", pii_density)?;
    dict.set_item("owner_domain", owner_domain)?;

    Ok(dict.into())
}

/// Get the raw metadata struct size (should be 156)
#[pyfunction]
pub fn raw_metadata_size() -> usize {
    std::mem::size_of::<RawFileMetadata>()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_struct_size() {
        assert_eq!(std::mem::size_of::<RawFileMetadata>(), 156);
    }

    #[test]
    fn test_round_trip() {
        let meta = RawFileMetadata::empty();
        let bytes = meta.to_bytes();
        assert_eq!(bytes.len(), 156);

        let parsed = RawFileMetadata::from_bytes(&bytes).unwrap();
        let size = parsed.size;
        let entropy = parsed.entropy;
        assert_eq!(size, 0);
        assert_eq!(entropy, 0.0);
    }

    #[test]
    fn test_entropy_calculation() {
        // All zeros = 0 entropy
        let zeros = vec![0u8; 1000];
        assert_eq!(calculate_entropy(&zeros), 0.0);

        // Random-like data = high entropy
        let random: Vec<u8> = (0..=255).cycle().take(1024).collect();
        let entropy = calculate_entropy(&random);
        assert!(entropy > 7.9); // Should be close to 8.0
    }
}
