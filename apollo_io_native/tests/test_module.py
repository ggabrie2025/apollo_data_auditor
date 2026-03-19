"""
Test suite for apollo_io_native module

Run with: pytest tests/test_module.py -v
"""

import os
import tempfile
import pytest

# Try to import the module
try:
    import apollo_io_native
    MODULE_AVAILABLE = True
except ImportError:
    MODULE_AVAILABLE = False
    apollo_io_native = None


# Skip all tests if module not compiled
pytestmark = pytest.mark.skipif(
    not MODULE_AVAILABLE,
    reason="apollo_io_native not compiled. Run 'maturin develop' first."
)


class TestPlatformInfo:
    """Test platform detection functions."""

    def test_get_platform_info(self):
        info = apollo_io_native.get_platform_info()

        assert "os" in info
        assert "arch" in info
        assert "io_method" in info
        assert "version" in info
        assert "cpu_count" in info

        assert info["cpu_count"] >= 1
        assert info["version"] == "0.1.0"

    def test_is_io_uring_available(self):
        result = apollo_io_native.is_io_uring_available()
        assert isinstance(result, bool)

    def test_optimal_batch_size(self):
        batch = apollo_io_native.optimal_batch_size(4096)
        assert 1000 <= batch <= 100_000


class TestWalker:
    """Test directory walking functions."""

    def test_walk_directory(self, tmp_path):
        # Create test files
        (tmp_path / "file1.txt").write_text("content1")
        (tmp_path / "file2.txt").write_text("content2")
        subdir = tmp_path / "subdir"
        subdir.mkdir()
        (subdir / "file3.txt").write_text("content3")

        paths = apollo_io_native.walk_directory(str(tmp_path))

        assert len(paths) == 3
        assert any("file1.txt" in p for p in paths)
        assert any("file3.txt" in p for p in paths)

    def test_walk_skip_hidden(self, tmp_path):
        (tmp_path / "visible.txt").write_text("visible")
        (tmp_path / ".hidden").write_text("hidden")

        # With skip_hidden=True
        paths = apollo_io_native.walk_directory(str(tmp_path), skip_hidden=True)
        assert len(paths) == 1

        # With skip_hidden=False
        paths = apollo_io_native.walk_directory(str(tmp_path), skip_hidden=False)
        assert len(paths) == 2

    def test_walk_max_depth(self, tmp_path):
        # Create nested structure
        level1 = tmp_path / "level1"
        level1.mkdir()
        level2 = level1 / "level2"
        level2.mkdir()

        (tmp_path / "root.txt").write_text("root")
        (level1 / "l1.txt").write_text("l1")
        (level2 / "l2.txt").write_text("l2")

        # Depth 1: root + level1
        paths = apollo_io_native.walk_directory(str(tmp_path), max_depth=1)
        assert len(paths) == 1  # Only root.txt

        # Depth 2: include level1
        paths = apollo_io_native.walk_directory(str(tmp_path), max_depth=2)
        assert len(paths) == 2

    def test_walk_nonexistent(self):
        with pytest.raises(FileNotFoundError):
            apollo_io_native.walk_directory("/nonexistent/path")


class TestReader:
    """Test file reading functions."""

    def test_read_files_batch(self, tmp_path):
        # Create test files
        files = []
        for i in range(5):
            f = tmp_path / f"file{i}.txt"
            f.write_text(f"content{i}")
            files.append(str(f))

        results = apollo_io_native.read_files_batch(files, max_bytes=1024, workers=2)

        assert len(results) == 5
        for path, content in results:
            assert b"content" in content

    def test_read_max_bytes(self, tmp_path):
        f = tmp_path / "large.txt"
        f.write_text("A" * 1000)

        results = apollo_io_native.read_files_batch([str(f)], max_bytes=100)

        assert len(results) == 1
        _, content = results[0]
        assert len(content) == 100

    def test_read_nonexistent(self):
        results = apollo_io_native.read_files_batch(["/nonexistent/file.txt"])
        assert len(results) == 0  # Graceful skip


class TestStat:
    """Test stat functions."""

    def test_stat_files_batch(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("Hello, World!")

        results = apollo_io_native.stat_files_batch([str(f)])

        assert len(results) == 1
        path, size, mtime = results[0]
        assert size == 13
        assert mtime > 0


class TestHasher:
    """Test hashing functions."""

    def test_hash_files_xxhash(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("Hello, World!")

        results = apollo_io_native.hash_files_xxhash([str(f)])

        assert len(results) == 1
        path, hash_hex = results[0]
        assert len(hash_hex) == 16  # 64 bits = 16 hex chars

    def test_xxhash64_string(self):
        h1 = apollo_io_native.xxhash64_string("hello", 0)
        h2 = apollo_io_native.xxhash64_string("hello", 0)
        h3 = apollo_io_native.xxhash64_string("world", 0)

        assert h1 == h2  # Same input = same hash
        assert h1 != h3  # Different input = different hash
        assert len(h1) == 16

    def test_hash_path(self):
        h = apollo_io_native.hash_path("/path/to/file.txt")
        assert len(h) == 16


class TestBloomFilter:
    """Test BloomFilter wrapper."""

    def test_basic_operations(self):
        bloom = apollo_io_native.BloomFilterWrapper(capacity=1000, fp_rate=0.01)

        bloom.add("item1")
        bloom.add("item2")

        assert bloom.contains("item1")
        assert bloom.contains("item2")
        assert not bloom.contains("item3")
        assert bloom.len() == 2

    def test_add_batch(self):
        bloom = apollo_io_native.BloomFilterWrapper()

        bloom.add_batch(["a", "b", "c", "d", "e"])

        assert bloom.len() == 5
        assert bloom.contains("c")

    def test_filter_new(self):
        bloom = apollo_io_native.BloomFilterWrapper()

        bloom.add("existing1")
        bloom.add("existing2")

        items = ["existing1", "new1", "existing2", "new2"]
        new_items = bloom.filter_new(items)

        assert len(new_items) == 2
        assert "new1" in new_items
        assert "new2" in new_items

    def test_check_and_add(self):
        bloom = apollo_io_native.BloomFilterWrapper()

        assert bloom.check_and_add("item") == True   # New
        assert bloom.check_and_add("item") == False  # Already present

    def test_clear(self):
        bloom = apollo_io_native.BloomFilterWrapper()

        bloom.add("item")
        assert bloom.len() == 1

        bloom.clear()
        assert bloom.len() == 0
        assert not bloom.contains("item")

    def test_memory(self):
        bloom = apollo_io_native.BloomFilterWrapper(capacity=1_000_000)
        memory_mb = bloom.memory_bytes() / 1_000_000

        # Should be around 1-2 MB for 1M capacity
        assert 0.5 < memory_mb < 5


class TestFingerprint:
    """Test fingerprint functions."""

    def test_fingerprint_batch(self, tmp_path):
        f = tmp_path / "test.csv"
        f.write_text("a,b,c")

        fps = apollo_io_native.fingerprint_batch([str(f)])

        assert len(fps) == 1
        fp = fps[0]
        assert fp.size == 5
        assert fp.extension == ".csv"
        assert fp.zone == "normal"
        assert len(fp.path_hash) == 16

    def test_zone_detection(self, tmp_path):
        # Sensitive zone
        rh_dir = tmp_path / "rh"
        rh_dir.mkdir()
        rh_file = rh_dir / "employees.csv"
        rh_file.write_text("data")

        fps = apollo_io_native.fingerprint_batch([str(rh_file)])
        assert fps[0].zone == "sensitive"

        # Archive zone
        backup_dir = tmp_path / "backup"
        backup_dir.mkdir()
        backup_file = backup_dir / "old.zip"
        backup_file.write_text("data")

        fps = apollo_io_native.fingerprint_batch([str(backup_file)])
        assert fps[0].zone == "archive"

    def test_deduplicate(self, tmp_path):
        # Create files with same size
        f1 = tmp_path / "file1.txt"
        f2 = tmp_path / "file2.txt"
        f1.write_text("AAAA")
        f2.write_text("BBBB")

        fps = apollo_io_native.fingerprint_batch([str(f1), str(f2)])
        unique = apollo_io_native.deduplicate_fingerprints(fps)

        # Same size + extension = deduplicated to 1
        assert len(unique) == 1

    def test_fingerprint_stats(self, tmp_path):
        for i in range(5):
            (tmp_path / f"file{i}.txt").write_text(f"content{i}")

        paths = [str(tmp_path / f"file{i}.txt") for i in range(5)]
        fps = apollo_io_native.fingerprint_batch(paths)
        stats = apollo_io_native.fingerprint_stats(fps)

        assert stats["total"] == 5
        assert "by_zone" in stats
        assert "normal" in stats["by_zone"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
