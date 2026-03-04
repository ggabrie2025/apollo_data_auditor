//! BloomFilter wrapper for deduplication
//!
//! Provides O(1) membership testing for deduplication

use pyo3::prelude::*;
use bloomfilter::Bloom;
use parking_lot::Mutex;
use std::sync::Arc;

/// Default capacity: 10 million items
const DEFAULT_CAPACITY: usize = 10_000_000;

/// Default false positive rate: 0.1%
const DEFAULT_FP_RATE: f64 = 0.001;

/// BloomFilter wrapper for Python
///
/// Thread-safe BloomFilter for O(1) deduplication checks
///
/// # Example
/// ```python
/// from apollo_io_native import BloomFilterWrapper
///
/// bloom = BloomFilterWrapper(capacity=1000000, fp_rate=0.001)
/// bloom.add("item1")
/// bloom.add("item2")
///
/// print(bloom.contains("item1"))  # True
/// print(bloom.contains("item3"))  # False (probably)
/// print(bloom.len())  # 2
/// ```
#[pyclass]
pub struct BloomFilterWrapper {
    inner: Arc<Mutex<Bloom<String>>>,
    capacity: usize,
    fp_rate: f64,
    count: Arc<Mutex<usize>>,
}

#[pymethods]
impl BloomFilterWrapper {
    /// Create a new BloomFilter
    ///
    /// # Arguments
    /// * `capacity` - Expected number of items (default: 10,000,000)
    /// * `fp_rate` - False positive rate (default: 0.001 = 0.1%)
    #[new]
    #[pyo3(signature = (capacity=None, fp_rate=None))]
    pub fn new(capacity: Option<usize>, fp_rate: Option<f64>) -> Self {
        let capacity = capacity.unwrap_or(DEFAULT_CAPACITY);
        let fp_rate = fp_rate.unwrap_or(DEFAULT_FP_RATE);

        let bloom = Bloom::new_for_fp_rate(capacity, fp_rate);

        BloomFilterWrapper {
            inner: Arc::new(Mutex::new(bloom)),
            capacity,
            fp_rate,
            count: Arc::new(Mutex::new(0)),
        }
    }

    /// Add an item to the BloomFilter
    pub fn add(&self, item: &str) {
        let mut bloom = self.inner.lock();
        bloom.set(&item.to_string());
        let mut count = self.count.lock();
        *count += 1;
    }

    /// Add multiple items at once
    pub fn add_batch(&self, items: Vec<String>) {
        let mut bloom = self.inner.lock();
        let mut count = self.count.lock();
        for item in items {
            bloom.set(&item);
            *count += 1;
        }
    }

    /// Check if an item might be in the BloomFilter
    ///
    /// Returns:
    /// - True: Item might be present (with fp_rate probability of false positive)
    /// - False: Item is definitely not present
    pub fn contains(&self, item: &str) -> bool {
        let bloom = self.inner.lock();
        bloom.check(&item.to_string())
    }

    /// Check multiple items and return which ones are NOT in the filter
    ///
    /// Useful for deduplication: returns items that are definitely new
    pub fn filter_new(&self, items: Vec<String>) -> Vec<String> {
        let bloom = self.inner.lock();
        items
            .into_iter()
            .filter(|item| !bloom.check(item))
            .collect()
    }

    /// Check and add: returns True if item was new, False if already present
    pub fn check_and_add(&self, item: &str) -> bool {
        let mut bloom = self.inner.lock();
        let item_str = item.to_string();

        if bloom.check(&item_str) {
            false // Already present (probably)
        } else {
            bloom.set(&item_str);
            let mut count = self.count.lock();
            *count += 1;
            true // New item
        }
    }

    /// Get number of items added
    pub fn len(&self) -> usize {
        *self.count.lock()
    }

    /// Check if filter is empty
    pub fn is_empty(&self) -> bool {
        *self.count.lock() == 0
    }

    /// Get filter capacity
    pub fn capacity(&self) -> usize {
        self.capacity
    }

    /// Get false positive rate
    pub fn fp_rate(&self) -> f64 {
        self.fp_rate
    }

    /// Clear the filter
    pub fn clear(&self) {
        let mut bloom = self.inner.lock();
        *bloom = Bloom::new_for_fp_rate(self.capacity, self.fp_rate);
        let mut count = self.count.lock();
        *count = 0;
    }

    /// Get memory usage estimate in bytes
    pub fn memory_bytes(&self) -> usize {
        let bloom = self.inner.lock();
        (bloom.number_of_bits() / 8) as usize
    }

    /// String representation
    fn __repr__(&self) -> String {
        format!(
            "BloomFilterWrapper(count={}, capacity={}, fp_rate={}, memory_mb={:.2})",
            self.len(),
            self.capacity,
            self.fp_rate,
            self.memory_bytes() as f64 / 1_000_000.0
        )
    }
}

/// Create a new BloomFilter (convenience function)
#[pyfunction]
#[pyo3(signature = (capacity=None, fp_rate=None))]
pub fn create_bloom_filter(capacity: Option<usize>, fp_rate: Option<f64>) -> BloomFilterWrapper {
    BloomFilterWrapper::new(capacity, fp_rate)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_bloom_basic() {
        let bloom = BloomFilterWrapper::new(Some(1000), Some(0.01));

        bloom.add("hello");
        bloom.add("world");

        assert!(bloom.contains("hello"));
        assert!(bloom.contains("world"));
        assert!(!bloom.contains("foo")); // Should not be present
        assert_eq!(bloom.len(), 2);
    }

    #[test]
    fn test_bloom_check_and_add() {
        let bloom = BloomFilterWrapper::new(Some(1000), Some(0.01));

        assert!(bloom.check_and_add("item1")); // New
        assert!(!bloom.check_and_add("item1")); // Already present
        assert!(bloom.check_and_add("item2")); // New
    }

    #[test]
    fn test_bloom_filter_new() {
        let bloom = BloomFilterWrapper::new(Some(1000), Some(0.01));

        bloom.add("existing1");
        bloom.add("existing2");

        let items = vec![
            "existing1".to_string(),
            "new1".to_string(),
            "existing2".to_string(),
            "new2".to_string(),
        ];

        let new_items = bloom.filter_new(items);
        assert_eq!(new_items.len(), 2);
        assert!(new_items.contains(&"new1".to_string()));
        assert!(new_items.contains(&"new2".to_string()));
    }

    #[test]
    fn test_bloom_clear() {
        let bloom = BloomFilterWrapper::new(Some(1000), Some(0.01));

        bloom.add("item");
        assert_eq!(bloom.len(), 1);

        bloom.clear();
        assert_eq!(bloom.len(), 0);
        assert!(!bloom.contains("item"));
    }
}
