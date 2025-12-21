"""
Comprehensive tests for AsyncROMCache - Non-blocking cache operations

Tests focus on:
1. Async load/save operations without blocking main thread
2. Worker thread lifecycle and error handling
3. Memory cache behavior and LRU eviction
4. Cache file format validation and corruption handling
5. Performance characteristics and response timing
6. Thread safety and concurrent access patterns
7. Cache expiration and cleanup
"""
from __future__ import annotations

import json
import tempfile
import time
from pathlib import Path
from unittest.mock import Mock

import pytest
from PySide6.QtCore import QMutexLocker, QThread
from PySide6.QtWidgets import QApplication

from core.async_rom_cache import AsyncROMCache, CacheWorker
from tests.fixtures.timeouts import SHORT, cleanup_timeout, dialog_timeout, signal_timeout, worker_timeout

# Mark tests that create QApplication instances for serial execution
# parallel_unsafe: Tests create AsyncROMCache with worker threads that use shared
# cache directories and can conflict in parallel execution
pytestmark = [
    pytest.mark.headless,
    pytest.mark.integration,
    pytest.mark.slow,
    pytest.mark.allows_registry_state,
    pytest.mark.parallel_unsafe,
]

class TestCacheWorker:
    """Test the CacheWorker background thread functionality"""

    def setup_method(self):
        """Set up test fixtures"""
        # Ensure QApplication exists for Qt event processing
        if not QApplication.instance():
            self.app = QApplication([])
        else:
            self.app = QApplication.instance()

        self.temp_dir = Path(tempfile.mkdtemp())
        self.worker = CacheWorker(self.temp_dir)

        # Also create AsyncROMCache for some tests
        self.mock_rom_cache = Mock()
        self.mock_rom_cache.cache_dir = str(self.temp_dir)
        self.async_cache = AsyncROMCache(self.mock_rom_cache)

        # Process events to ensure worker thread is ready
        self.app.processEvents()
    def teardown_method(self):
        """Clean up test fixtures"""
        if hasattr(self, 'async_cache'):
            # Explicitly shutdown to stop the worker thread before deleting
            self.async_cache.shutdown(timeout=cleanup_timeout())
        if hasattr(self, 'worker'):
            self.worker.stop()
        # Clean up temp directory
        import shutil
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_worker_initialization(self):
        """Test worker initializes correctly"""
        assert self.worker.cache_dir == self.temp_dir
        assert not self.worker._stop_requested.is_set()

        # Signal connections should be available
        assert hasattr(self.worker, 'data_loaded')
        assert hasattr(self.worker, 'load_error')
        assert hasattr(self.worker, 'save_complete')

    def test_save_and_load_cache_file(self, qtbot):
        """Test complete save->load cycle"""
        cache_key = "test_sprite_12345678_00200000"
        test_data = b"\x01\x02\x03\x04" * 100  # 400 bytes of test data
        metadata = {"width": 128, "height": 128, "format": "4bpp"}

        # Connect signal spy
        with qtbot.wait_signal(self.worker.save_complete, timeout=signal_timeout(SHORT)) as blocker:
            self.worker.save_to_cache(cache_key, test_data, metadata)

        # Verify save completed successfully
        args = blocker.args
        assert args[0] == cache_key  # cache_key
        assert args[1] is True       # success

        # Verify file was created
        cache_file = self.temp_dir / f"{cache_key}.cache"
        assert cache_file.exists()
        assert cache_file.stat().st_size > len(test_data)  # Should be larger due to metadata

        # Test loading the cached data
        request_id = "load_test_123"
        with qtbot.wait_signal(self.worker.data_loaded, timeout=signal_timeout(SHORT)) as blocker:
            self.worker.load_from_cache(request_id, cache_key)

        # Verify loaded data matches
        args = blocker.args
        assert args[0] == request_id
        assert args[1] == test_data
        loaded_metadata = args[2]
        assert loaded_metadata["width"] == 128
        assert loaded_metadata["height"] == 128
        assert loaded_metadata["format"] == "4bpp"
        assert "timestamp" in loaded_metadata

    def test_load_nonexistent_cache(self, qtbot):
        """Test loading from non-existent cache file"""
        request_id = "missing_test_456"
        cache_key = "nonexistent_key"

        with qtbot.wait_signal(self.worker.load_error, timeout=signal_timeout(SHORT)) as blocker:
            self.worker.load_from_cache(request_id, cache_key)

        args = blocker.args
        assert args[0] == request_id
        assert "Cache miss" in args[1]

    def test_corrupted_cache_file_handling(self, qtbot):
        """Test handling of corrupted cache files"""
        cache_key = "corrupted_test"
        cache_file = self.temp_dir / f"{cache_key}.cache"

        # Create corrupted cache file (invalid metadata size)
        cache_file.write_bytes(b"\xFF\xFF\xFF\xFF" + b"invalid_json")

        request_id = "corrupt_test_789"
        with qtbot.wait_signal(self.worker.load_error, timeout=signal_timeout(SHORT)) as blocker:
            self.worker.load_from_cache(request_id, cache_key)

        args = blocker.args
        assert args[0] == request_id
        # Should get error about corrupted cache file
        # The signal emits "Cache corrupted" for corrupted metadata
        assert any(keyword in args[1].lower() for keyword in ["corrupted", "invalid", "cache"])

    def test_expired_cache_cleanup(self, qtbot):
        """Test that expired cache files are cleaned up"""
        cache_key = "expired_test"
        test_data = b"old_data"

        # Create cache file with old timestamp
        old_metadata = {"timestamp": time.time() - 90000}  # 25 hours ago
        cache_file = self.temp_dir / f"{cache_key}.cache"

        with open(cache_file, "wb") as f:
            meta_json = json.dumps(old_metadata).encode()
            f.write(len(meta_json).to_bytes(4, "little"))
            f.write(meta_json)
            f.write(test_data)

        request_id = "expired_test_321"
        with qtbot.wait_signal(self.worker.load_error, timeout=signal_timeout(SHORT)) as blocker:
            self.worker.load_from_cache(request_id, cache_key)

        # Should get cache expired error
        args = blocker.args
        assert args[0] == request_id
        assert "Cache expired" in args[1]

        # Cache file should be deleted
        assert not cache_file.exists()

    def test_worker_stop_mechanism(self):
        """Test worker stop request handling"""
        assert not self.worker._stop_requested.is_set()

        self.worker.stop()
        assert self.worker._stop_requested.is_set()

        # Operations should be skipped when stopped
        # Note: We can't easily test the actual skipping without QTimer integration
        # but we can verify the flag is set

    def test_atomic_file_writing(self, qtbot):
        """Test that cache files are written atomically"""
        cache_key = "atomic_test"
        test_data = b"atomic_data" * 1000  # Larger data to increase write time
        metadata = {"test": "atomic"}

        with qtbot.wait_signal(self.worker.save_complete, timeout=signal_timeout()) as blocker:
            self.worker.save_to_cache(cache_key, test_data, metadata)

        # Verify no .tmp file remains
        temp_file = self.temp_dir / f"{cache_key}.tmp"
        assert not temp_file.exists()

        # Final cache file should exist and be valid
        cache_file = self.temp_dir / f"{cache_key}.cache"
        assert cache_file.exists()

        # Verify file is not corrupted by attempting to load
        request_id = "atomic_load_test"
        with qtbot.wait_signal(self.worker.data_loaded, timeout=signal_timeout(SHORT)) as blocker:
            self.worker.load_from_cache(request_id, cache_key)

        args = blocker.args
        assert args[1] == test_data

class TestAsyncROMCache:
    """Test the AsyncROMCache coordination and async interface"""

    def setup_method(self):
        """Set up test fixtures"""
        self.temp_dir = Path(tempfile.mkdtemp())
        self.mock_rom_cache = Mock()
        self.mock_rom_cache.cache_dir = str(self.temp_dir)

        # Create AsyncROMCache with mock ROM cache
        self.async_cache = AsyncROMCache(self.mock_rom_cache)

    def teardown_method(self):
        """Clean up test fixtures"""
        if hasattr(self, 'async_cache'):
            # Explicitly shutdown to stop the worker thread before deleting
            self.async_cache.shutdown(timeout=cleanup_timeout())
            del self.async_cache
        # Clean up temp directory
        import shutil
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_initialization_with_rom_cache(self):
        """Test proper initialization with ROM cache"""
        assert self.async_cache.cache_dir == self.temp_dir
        assert self.async_cache._worker_thread.isRunning()
        assert self.async_cache._memory_cache_max == 10
        assert len(self.async_cache._memory_cache) == 0
        assert len(self.async_cache._save_queue) == 0

    def test_initialization_without_rom_cache(self, monkeypatch):
        """Test fallback initialization without ROM cache"""
        # Clear the env var to test the true fallback path
        monkeypatch.delenv("SPRITEPAL_CACHE_DIR", raising=False)

        cache_without_rom = AsyncROMCache(None)
        try:
            expected_dir = Path.home() / ".spritepal_cache"
            assert cache_without_rom.cache_dir == expected_dir
        finally:
            # Must shutdown properly to avoid thread conflicts in parallel execution
            cache_without_rom.shutdown(timeout=cleanup_timeout())

    def test_memory_cache_hit(self, qtbot):
        """Test memory cache hit provides instant response"""
        rom_path = "/test/rom.sfc"
        offset = 0x200000
        request_id = "memory_hit_test"

        # Pre-populate memory cache
        cache_key = self.async_cache._generate_cache_key(rom_path, offset)
        test_data = b"cached_data"
        metadata = {"source": "memory"}

        with QMutexLocker(self.async_cache._request_mutex):
            self.async_cache._memory_cache[cache_key] = (test_data, metadata, time.time())

        # Request should hit memory cache immediately
        with qtbot.wait_signal(self.async_cache.cache_ready, timeout=100) as blocker:
            self.async_cache.get_cached_async(rom_path, offset, request_id)

        # Verify immediate response
        args = blocker.args
        assert args[0] == request_id
        assert args[1] == test_data
        assert args[2] == metadata

    def test_memory_cache_expiration(self, qtbot):
        """Test expired memory cache entries are removed"""
        rom_path = "/test/rom.sfc"
        offset = 0x200000
        request_id = "memory_expire_test"

        # Add expired entry to memory cache
        cache_key = self.async_cache._generate_cache_key(rom_path, offset)
        old_timestamp = time.time() - 400  # 400 seconds ago (expired)

        with QMutexLocker(self.async_cache._request_mutex):
            self.async_cache._memory_cache[cache_key] = (b"expired", {}, old_timestamp)

        # Request should not hit expired cache, should emit cache_error (miss)
        with qtbot.wait_signal(self.async_cache.cache_error, timeout=signal_timeout(SHORT)):
            self.async_cache.get_cached_async(rom_path, offset, request_id)

        # Expired entry should be removed from memory cache
        with QMutexLocker(self.async_cache._request_mutex):
            assert cache_key not in self.async_cache._memory_cache

    def test_memory_cache_lru_eviction(self, qtbot):
        """Test LRU eviction when memory cache exceeds limit"""
        # Set small cache limit for testing
        self.async_cache._memory_cache_max = 3

        # Add entries to exceed limit
        for i in range(5):
            data = f"data_{i}".encode()
            metadata = {"index": i}

            self.async_cache.save_cached_async(f"/rom_{i}.sfc", i * 0x1000, data, metadata)

        # Wait for memory cache operations to complete using condition check
        def cache_has_entries() -> bool:
            with QMutexLocker(self.async_cache._request_mutex):
                return len(self.async_cache._memory_cache) > 0

        qtbot.waitUntil(cache_has_entries, timeout=signal_timeout(SHORT))

        # Should only have the most recent 3 entries
        with QMutexLocker(self.async_cache._request_mutex):
            assert len(self.async_cache._memory_cache) <= 3
            # Most recent entries should be preserved
            assert any("data_4" in str(values) for values in self.async_cache._memory_cache.values())

    def test_batch_save_queuing(self):
        """Test that multiple saves are batched efficiently"""
        initial_queue_size = len(self.async_cache._save_queue)

        # Add multiple save requests rapidly
        for i in range(5):
            self.async_cache.save_cached_async(
                f"/test/rom_{i}.sfc",
                i * 0x1000,
                f"data_{i}".encode(),
                {"batch_test": i}
            )

        # Queue should accumulate requests
        with QMutexLocker(self.async_cache._save_mutex):
            assert len(self.async_cache._save_queue) > initial_queue_size
            assert self.async_cache._save_timer.isActive()

    def test_large_batch_immediate_flush(self, qtbot):
        """Test immediate flush when batch size exceeds threshold"""
        # Add requests up to flush threshold
        for i in range(10):  # Should trigger immediate flush at 10 items
            self.async_cache.save_cached_async(
                f"/test/batch_{i}.sfc",
                i * 0x1000,
                b"batch_data",
                {"immediate": True}
            )

        # Wait for queue to be flushed using condition check
        def queue_flushed() -> bool:
            with QMutexLocker(self.async_cache._save_mutex):
                return len(self.async_cache._save_queue) < 10

        qtbot.waitUntil(queue_flushed, timeout=signal_timeout(SHORT))

        with QMutexLocker(self.async_cache._save_mutex):
            # Queue should be empty or much smaller after immediate flush
            assert len(self.async_cache._save_queue) < 10

    def test_cache_key_generation(self):
        """Test cache key generation consistency"""
        rom_path1 = "/test/rom.sfc"
        rom_path2 = "/different/path.sfc"
        offset1 = 0x200000
        offset2 = 0x300000

        # Same inputs should generate same key
        key1a = self.async_cache._generate_cache_key(rom_path1, offset1)
        key1b = self.async_cache._generate_cache_key(rom_path1, offset1)
        assert key1a == key1b

        # Different inputs should generate different keys
        key2 = self.async_cache._generate_cache_key(rom_path1, offset2)
        key3 = self.async_cache._generate_cache_key(rom_path2, offset1)

        assert key1a != key2
        assert key1a != key3
        assert key2 != key3

        # Keys should contain offset in hex format
        assert f"{offset1:08x}" in key1a
        assert f"{offset2:08x}" in key2

    def test_concurrent_request_handling(self, qtbot):
        """Test thread safety with concurrent requests"""
        rom_path = "/test/concurrent.sfc"

        # Submit multiple concurrent requests
        request_ids = []
        for i in range(5):
            request_id = f"concurrent_{i}"
            request_ids.append(request_id)
            self.async_cache.get_cached_async(rom_path, i * 0x1000, request_id)

        # All requests should either succeed or fail gracefully
        # (cache misses expected since no data pre-populated)
        # Wait for all 5 cache_error signals
        received_ids = []

        def collect_error(request_id: str, error: str) -> None:
            received_ids.append(request_id)

        self.async_cache.cache_error.connect(collect_error)

        # Wait for all errors to be received
        qtbot.wait_until(lambda: len(received_ids) == 5, timeout=signal_timeout())

        # Verify all request IDs were received
        assert set(received_ids) == set(request_ids)

        # No requests should be left pending
        with QMutexLocker(self.async_cache._request_mutex):
            for req_id in request_ids:
                assert req_id not in self.async_cache._pending_requests

    def test_memory_cache_clear(self, qtbot):
        """Test memory cache clearing"""
        # Populate memory cache
        for i in range(3):
            self.async_cache.save_cached_async(
                f"/test/clear_{i}.sfc",
                i * 0x1000,
                b"clear_test",
                {}
            )

        # Wait for cache to populate using condition check
        def cache_populated() -> bool:
            with QMutexLocker(self.async_cache._request_mutex):
                return len(self.async_cache._memory_cache) > 0

        qtbot.waitUntil(cache_populated, timeout=signal_timeout(SHORT))

        # Verify cache has entries
        with QMutexLocker(self.async_cache._request_mutex):
            initial_count = len(self.async_cache._memory_cache)
            assert initial_count > 0

        # Clear cache
        self.async_cache.clear_memory_cache()

        # Verify cache is empty
        with QMutexLocker(self.async_cache._request_mutex):
            assert len(self.async_cache._memory_cache) == 0

    @pytest.mark.performance
    def test_response_time_characteristics(self, qtbot):
        """Test that cached responses are fast enough for real-time use"""
        rom_path = "/test/performance.sfc"
        offset = 0x200000
        request_id = "perf_test"

        # Pre-populate memory cache for fastest response
        cache_key = self.async_cache._generate_cache_key(rom_path, offset)
        test_data = b"performance_data"
        metadata = {"perf_test": True}

        with QMutexLocker(self.async_cache._request_mutex):
            self.async_cache._memory_cache[cache_key] = (test_data, metadata, time.time())

        # Measure response time
        start_time = time.perf_counter()

        with qtbot.wait_signal(self.async_cache.cache_ready, timeout=100) as blocker:
            self.async_cache.get_cached_async(rom_path, offset, request_id)

        response_time = time.perf_counter() - start_time

        # Memory cache hits should be very fast (< 10ms for real-time feel)
        assert response_time < 0.01, f"Response time too slow: {response_time:.3f}s"

        # Verify correct data returned
        args = blocker.args
        assert args[1] == test_data

    def test_worker_thread_lifecycle(self):
        """Test worker thread starts and stops properly"""
        # Worker thread should be running after initialization
        assert self.async_cache._worker_thread.isRunning()

        # Worker should be moved to the thread
        assert self.async_cache._worker.thread() == self.async_cache._worker_thread

        # Thread should be dedicated (not main thread)
        assert self.async_cache._worker_thread != QThread.currentThread()

class TestAsyncROMCacheIntegration:
    """Integration tests for AsyncROMCache with real file system operations"""

    def setup_method(self):
        """Set up integration test environment"""
        self.temp_dir = Path(tempfile.mkdtemp())
        self.mock_rom_cache = Mock()
        self.mock_rom_cache.cache_dir = str(self.temp_dir)
        self.async_cache = AsyncROMCache(self.mock_rom_cache)

    def teardown_method(self):
        """Clean up integration test environment"""
        if hasattr(self, 'async_cache'):
            # Explicitly shutdown to stop the worker thread before deleting
            self.async_cache.shutdown(timeout=cleanup_timeout())
            del self.async_cache
        import shutil
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_full_cache_cycle_integration(self, qtbot):
        """Test complete save->load->verify cycle with real file I/O"""
        rom_path = "/test/integration.sfc"
        offset = 0x200000
        test_data = b"\x00\x01\x02\x03" * 256  # 1KB test data
        metadata = {
            "width": 128,
            "height": 128,
            "palette": 8,
            "format": "4bpp"
        }

        # Step 1: Save data asynchronously and wait for completion
        cache_key = self.async_cache._generate_cache_key(rom_path, offset)

        # Connect to worker's save_complete signal to wait for actual disk write
        with qtbot.wait_signal(self.async_cache._worker.save_complete, timeout=dialog_timeout()) as save_blocker:
            self.async_cache.save_cached_async(rom_path, offset, test_data, metadata)
            # Force immediate flush to trigger save
            self.async_cache._flush_save_queue()

        # Verify save completed successfully
        save_args = save_blocker.args
        assert save_args[0] == cache_key  # cache_key
        assert save_args[1] is True       # success

        # Step 2: Clear memory cache to force disk read
        self.async_cache.clear_memory_cache()

        # Step 3: Request cached data
        request_id = "integration_test"
        with qtbot.wait_signal(self.async_cache.cache_ready, timeout=signal_timeout()) as blocker:
            self.async_cache.get_cached_async(rom_path, offset, request_id)

        # Step 4: Verify loaded data matches saved data
        args = blocker.args
        assert args[0] == request_id
        assert args[1] == test_data
        loaded_metadata = args[2]
        assert loaded_metadata["width"] == 128
        assert loaded_metadata["height"] == 128
        assert loaded_metadata["palette"] == 8
        assert loaded_metadata["format"] == "4bpp"
        assert "timestamp" in loaded_metadata

        # Step 5: Verify cache file exists on disk
        cache_key = self.async_cache._generate_cache_key(rom_path, offset)
        cache_file = self.temp_dir / f"{cache_key}.cache"
        assert cache_file.exists()
        assert cache_file.stat().st_size > len(test_data)

    @pytest.mark.performance
    def test_cache_performance_under_load(self, qtbot):
        """Test cache performance with multiple concurrent operations"""
        rom_path = "/test/load_test.sfc"

        # Generate test data set
        test_data_set = []
        for i in range(20):
            offset = 0x200000 + (i * 0x1000)
            data = f"load_test_{i}".encode() * 50  # ~550 bytes each
            metadata = {"test_index": i, "size": len(data)}
            test_data_set.append((offset, data, metadata))

        # Step 1: Save multiple items in parallel
        start_time = time.perf_counter()

        # Count expected save operations
        expected_saves = len(test_data_set)
        save_count = 0

        def count_saves(cache_key: str, success: bool):
            nonlocal save_count
            if success:
                save_count += 1

        # Connect to save completion signal
        self.async_cache._worker.save_complete.connect(count_saves)

        try:
            # Submit all save operations
            for offset, data, metadata in test_data_set:
                self.async_cache.save_cached_async(rom_path, offset, data, metadata)

            # Force flush to trigger saves
            self.async_cache._flush_save_queue()

            # Wait for all saves to complete
            qtbot.wait_until(lambda: save_count >= expected_saves, timeout=worker_timeout())
            save_time = time.perf_counter() - start_time

        finally:
            self.async_cache._worker.save_complete.disconnect(count_saves)

        # Step 2: Clear memory cache and load all items
        self.async_cache.clear_memory_cache()

        load_start_time = time.perf_counter()
        load_signals = []

        # Submit all load requests
        for i, (offset, _, _) in enumerate(test_data_set):
            request_id = f"load_test_{i}"
            self.async_cache.get_cached_async(rom_path, offset, request_id)
            load_signals.append(self.async_cache.cache_ready)

        # Wait for all loads to complete
        with qtbot.wait_signals(load_signals[:10], timeout=worker_timeout()):  # Test first 10
            pass

        load_time = time.perf_counter() - load_start_time

        # Performance assertions
        assert save_time < 3.0, f"Save operations too slow: {save_time:.3f}s"
        assert load_time < 2.0, f"Load operations too slow: {load_time:.3f}s"

        # Verify memory cache is populated after loads
        with QMutexLocker(self.async_cache._request_mutex):
            assert len(self.async_cache._memory_cache) > 0

    def test_error_handling_and_recovery(self, qtbot):
        """Test error handling and recovery from various failure modes"""
        rom_path = "/test/error_test.sfc"

        # Test 1: Request non-existent cache
        request_id_1 = "nonexistent_test"
        with qtbot.wait_signal(self.async_cache.cache_error, timeout=signal_timeout(SHORT)) as blocker:
            self.async_cache.get_cached_async(rom_path, 0x999999, request_id_1)

        args = blocker.args
        assert args[0] == request_id_1
        assert "miss" in args[1].lower() or "error" in args[1].lower()

        # Test 2: Save and load should still work after error
        offset = 0x200000
        test_data = b"recovery_test"
        metadata = {"recovery": True}

        # Wait for save to complete properly
        cache_key = self.async_cache._generate_cache_key(rom_path, offset)
        with qtbot.wait_signal(self.async_cache._worker.save_complete, timeout=dialog_timeout()) as save_blocker:
            self.async_cache.save_cached_async(rom_path, offset, test_data, metadata)
            self.async_cache._flush_save_queue()

        # Verify save completed successfully
        save_args = save_blocker.args
        assert save_args[0] == cache_key
        assert save_args[1] is True

        self.async_cache.clear_memory_cache()

        request_id_2 = "recovery_test"
        with qtbot.wait_signal(self.async_cache.cache_ready, timeout=signal_timeout()) as blocker:
            self.async_cache.get_cached_async(rom_path, offset, request_id_2)

        # Should successfully recover and load data
        args = blocker.args
        assert args[0] == request_id_2
        assert args[1] == test_data

    def test_cache_directory_creation(self):
        """Test automatic cache directory creation"""
        # Test with non-existent directory
        non_existent_dir = self.temp_dir / "nested" / "cache" / "path"
        mock_cache = Mock()
        mock_cache.cache_dir = str(non_existent_dir)

        # Should create directory structure
        cache_instance = AsyncROMCache(mock_cache)
        assert cache_instance.cache_dir.exists()
        assert cache_instance.cache_dir.is_dir()

        del cache_instance


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
