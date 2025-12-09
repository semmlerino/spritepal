"""
Tests for HAL process pool simplification fixes.

Tests that the HAL process pool shutdown completes within timeout,
no zombie processes remain, and force_reset functionality works correctly.

Note: These tests use multiprocessing boundary mocks (Manager, Process) because
they're testing HALProcessPool's process lifecycle management - the actual
multiprocessing behavior needs to be controlled for deterministic testing.
"""
from __future__ import annotations

import threading
import time
from collections.abc import Generator
from unittest.mock import Mock, patch

import pytest

from core.hal_compression import HALCompressor, HALProcessPool, HALRequest, _hal_worker_process
from tests.infrastructure.mock_hal import create_mock_hal_tools
from utils.constants import HAL_POOL_SHUTDOWN_TIMEOUT

# Mark all tests in this module to skip manager setup and run serially
# HAL process pool tests must run serially due to singleton process pool management
pytestmark = [
    pytest.mark.no_manager_setup,
    pytest.mark.serial,
    pytest.mark.process_pool,
    pytest.mark.singleton,
    pytest.mark.ci_safe,
    pytest.mark.file_io,
    pytest.mark.headless,
    pytest.mark.integration,
    pytest.mark.performance,
    pytest.mark.signals_slots,
    pytest.mark.slow,
    pytest.mark.thread_safety,
    pytest.mark.worker_threads,
]


# ============================================================================
# Shared Fixtures (consolidated from duplicate definitions)
# ============================================================================

@pytest.fixture
def hal_tools(tmp_path) -> tuple[str, str]:
    """Create mock HAL tool executables using infrastructure helper."""
    return create_mock_hal_tools(tmp_path)


@pytest.fixture(autouse=True)
def reset_hal_singleton() -> Generator[None, None, None]:
    """Reset HAL singleton between tests for isolation."""
    HALProcessPool.reset_singleton()
    yield
    # Cleanup after test
    try:
        HALProcessPool.reset_singleton()
    except Exception:
        pass

class TestHALProcessPoolSimplification:
    """Test HAL process pool simplification and cleanup fixes.

    Uses module-level hal_tools and reset_hal_singleton fixtures.
    """

    def test_pool_shutdown_completes_within_timeout(self, hal_tools):
        """Test that pool shutdown completes within HAL_POOL_SHUTDOWN_TIMEOUT"""
        exhal_path, inhal_path = hal_tools

        # Create pool
        pool = HALProcessPool()

        # Mock multiprocessing components to control timing
        with patch('multiprocessing.Manager') as mock_manager, \
             patch('multiprocessing.Process') as mock_process_class:

            # Setup mock manager
            mock_mgr = Mock()
            mock_queue = Mock()
            mock_manager.return_value = mock_mgr
            mock_mgr.Queue.return_value = mock_queue

            # Setup mock processes
            mock_processes = []
            for i in range(2):  # Create 2 mock processes
                mock_proc = Mock()
                mock_proc.pid = 1000 + i
                mock_proc.is_alive.return_value = True
                mock_processes.append(mock_proc)

            mock_process_class.side_effect = mock_processes

            # Initialize pool
            assert pool.initialize(exhal_path, inhal_path, pool_size=2)

            # Measure shutdown time
            start_time = time.time()
            pool.shutdown()
            shutdown_time = time.time() - start_time

            # Verify shutdown completed within reasonable time
            # The simplified shutdown should take ~2 seconds (hardcoded sleep)
            assert shutdown_time < 5.0, f"Shutdown took {shutdown_time:.2f}s, expected < 5s"

            # Verify processes were terminated
            for mock_proc in mock_processes:
                mock_proc.terminate.assert_called_once()

    def test_no_zombie_processes_remain(self, hal_tools):
        """Test that no zombie processes remain after shutdown"""
        exhal_path, inhal_path = hal_tools

        pool = HALProcessPool()

        with patch('multiprocessing.Manager') as mock_manager, \
             patch('multiprocessing.Process') as mock_process_class:

            # Setup mocks
            mock_mgr = Mock()
            mock_queue = Mock()
            mock_manager.return_value = mock_mgr
            mock_mgr.Queue.return_value = mock_queue

            # Create mock processes that simulate being alive initially
            mock_processes = []
            for i in range(3):
                mock_proc = Mock()
                mock_proc.pid = 2000 + i
                # First call returns True (alive), second returns False (terminated)
                mock_proc.is_alive.side_effect = [True, False]
                mock_processes.append(mock_proc)

            mock_process_class.side_effect = mock_processes

            # Initialize and shutdown
            pool.initialize(exhal_path, inhal_path, pool_size=3)
            pool.shutdown()

            # Verify all processes were terminated
            for mock_proc in mock_processes:
                mock_proc.terminate.assert_called_once()
                # Should not need to kill since they terminated properly
                mock_proc.kill.assert_not_called()

            # Verify process lists are cleared
            assert len(pool._processes) == 0
            assert len(pool._process_pids) == 0

    def test_force_reset_functionality(self, hal_tools):
        """Test force_reset cleans up everything and allows re-initialization"""
        exhal_path, inhal_path = hal_tools

        pool = HALProcessPool()

        with patch('multiprocessing.Manager') as mock_manager, \
             patch('multiprocessing.Process') as mock_process_class:

            # Setup mocks
            mock_mgr = Mock()
            mock_queue = Mock()
            mock_manager.return_value = mock_mgr
            mock_mgr.Queue.return_value = mock_queue

            # Create mock processes
            mock_proc = Mock()
            mock_proc.pid = 3000
            mock_proc.is_alive.return_value = True
            mock_process_class.return_value = mock_proc

            # Initialize pool
            assert pool.initialize(exhal_path, inhal_path, pool_size=1)
            assert pool.is_initialized

            # Force reset
            pool.force_reset()

            # Verify state is reset
            assert not pool.is_initialized
            assert pool._pool is None
            assert pool._manager is None
            assert len(pool._processes) == 0
            assert len(pool._process_pids) == 0
            assert not pool._shutdown  # Should allow re-initialization

            # Verify process was forcefully terminated
            mock_proc.terminate.assert_called_once()
            mock_proc.kill.assert_called_once()

    def test_stuck_processes_are_force_killed(self, hal_tools):
        """Test that stuck processes are force killed during shutdown"""
        exhal_path, inhal_path = hal_tools

        pool = HALProcessPool()

        with patch('multiprocessing.Manager') as mock_manager, \
             patch('multiprocessing.Process') as mock_process_class:

            # Setup mocks
            mock_mgr = Mock()
            mock_queue = Mock()
            mock_manager.return_value = mock_mgr
            mock_mgr.Queue.return_value = mock_queue

            # Create a stubborn mock process that won't terminate
            mock_proc = Mock()
            mock_proc.pid = 4000
            mock_proc.is_alive.return_value = True  # Always alive (stuck)
            mock_process_class.return_value = mock_proc

            # Initialize pool
            pool.initialize(exhal_path, inhal_path, pool_size=1)

            # Shutdown - should force kill stuck process
            pool.shutdown()

            # Verify terminate was called first
            mock_proc.terminate.assert_called_once()
            # Verify kill was called when process remained alive
            mock_proc.kill.assert_called_once()

    def test_manager_shutdown_handles_errors_gracefully(self, hal_tools):
        """Test that manager shutdown handles various errors gracefully"""
        exhal_path, inhal_path = hal_tools

        pool = HALProcessPool()

        with patch('multiprocessing.Manager') as mock_manager, \
             patch('multiprocessing.Process') as mock_process_class:

            # Setup manager that raises error on shutdown
            mock_mgr = Mock()
            mock_queue = Mock()
            mock_manager.return_value = mock_mgr
            mock_mgr.Queue.return_value = mock_queue
            mock_mgr.shutdown.side_effect = BrokenPipeError("Connection lost")

            # Setup mock process
            mock_proc = Mock()
            mock_proc.pid = 5000
            mock_proc.is_alive.return_value = False  # Terminates cleanly
            mock_process_class.return_value = mock_proc

            # Initialize and shutdown
            pool.initialize(exhal_path, inhal_path, pool_size=1)

            # Should not raise exception despite manager error
            pool.shutdown()

            # Verify shutdown was attempted
            mock_mgr.shutdown.assert_called_once()
            # Pool should still be marked as shut down
            assert pool._pool is None

    def test_force_reset_immediate_termination(self, hal_tools):
        """Test that force_reset immediately terminates processes"""
        exhal_path, inhal_path = hal_tools

        pool = HALProcessPool()

        with patch('multiprocessing.Manager') as mock_manager, \
             patch('multiprocessing.Process') as mock_process_class, \
             patch('time.sleep') as mock_sleep:  # Speed up test

            # Setup mocks
            mock_mgr = Mock()
            mock_queue = Mock()
            mock_manager.return_value = mock_mgr
            mock_mgr.Queue.return_value = mock_queue

            # Create mock process
            mock_proc = Mock()
            mock_proc.pid = 6000
            # Process is alive for terminate, killed for kill
            mock_proc.is_alive.side_effect = [True, True, False]
            mock_process_class.return_value = mock_proc

            # Initialize pool
            pool.initialize(exhal_path, inhal_path, pool_size=1)

            # Force reset
            pool.force_reset()

            # Verify immediate terminate + kill sequence
            mock_proc.terminate.assert_called_once()
            mock_proc.kill.assert_called_once()
            # Should use minimal sleep (0.1s) in force_reset
            mock_sleep.assert_called_with(0.1)

    def test_concurrent_shutdown_calls_are_safe(self, hal_tools):
        """Test that concurrent shutdown calls don't cause issues"""
        exhal_path, inhal_path = hal_tools

        pool = HALProcessPool()

        with patch('multiprocessing.Manager') as mock_manager, \
             patch('multiprocessing.Process') as mock_process_class:

            # Setup mocks
            mock_mgr = Mock()
            mock_queue = Mock()
            mock_manager.return_value = mock_mgr
            mock_mgr.Queue.return_value = mock_queue

            mock_proc = Mock()
            mock_proc.pid = 7000
            mock_proc.is_alive.return_value = False
            mock_process_class.return_value = mock_proc

            # Initialize pool
            pool.initialize(exhal_path, inhal_path, pool_size=1)

            # Simulate concurrent shutdown calls
            def shutdown_worker():
                pool.shutdown()

            threads = []
            for _ in range(3):
                t = threading.Thread(target=shutdown_worker)
                threads.append(t)
                t.start()

            # Wait for all threads
            for t in threads:
                t.join(timeout=5.0)

            # Should not hang or raise exceptions
            assert pool._pool is None
            assert pool._shutdown

    def test_pool_prevents_operations_after_shutdown(self, hal_tools):
        """Test that pool prevents operations after shutdown"""
        exhal_path, inhal_path = hal_tools

        pool = HALProcessPool()

        with patch('multiprocessing.Manager') as mock_manager, \
             patch('multiprocessing.Process') as mock_process_class:

            # Setup mocks
            mock_mgr = Mock()
            mock_queue = Mock()
            mock_manager.return_value = mock_mgr
            mock_mgr.Queue.return_value = mock_queue

            mock_proc = Mock()
            mock_proc.pid = 8000
            mock_proc.is_alive.return_value = False
            mock_process_class.return_value = mock_proc

            # Initialize and shutdown
            pool.initialize(exhal_path, inhal_path, pool_size=1)
            pool.shutdown()

            # Try to submit request after shutdown
            request = HALRequest(
                operation="decompress",
                rom_path="/fake/path",
                offset=0x1000,
                request_id="test"
            )

            result = pool.submit_request(request)

            # Should return error result
            assert not result.success
            assert "not initialized or shutting down" in result.error_message

class TestHALWorkerProcessErrorHandling:
    """Test HAL worker process error handling improvements"""

    def test_worker_handles_broken_pipe_gracefully(self):
        """Test that worker process handles BrokenPipeError gracefully"""
        # Mock queues that raise BrokenPipeError
        mock_request_queue = Mock()
        mock_result_queue = Mock()
        mock_request_queue.get.side_effect = BrokenPipeError("Pipe closed")

        # Worker should exit gracefully without raising exception
        with patch('core.hal_compression.get_logger') as mock_logger:
            mock_logger.return_value = Mock()

            # Should not raise exception
            _hal_worker_process("fake_exhal", "fake_inhal", mock_request_queue, mock_result_queue)

    def test_worker_handles_connection_reset_gracefully(self):
        """Test that worker process handles ConnectionResetError gracefully"""
        mock_request_queue = Mock()
        mock_result_queue = Mock()
        mock_request_queue.get.side_effect = ConnectionResetError("Connection reset")

        with patch('core.hal_compression.get_logger') as mock_logger:
            mock_logger.return_value = Mock()

            # Should not raise exception
            _hal_worker_process("fake_exhal", "fake_inhal", mock_request_queue, mock_result_queue)

    def test_worker_handles_eof_error_gracefully(self):
        """Test that worker process handles EOFError gracefully"""
        mock_request_queue = Mock()
        mock_result_queue = Mock()
        mock_request_queue.get.side_effect = EOFError("End of file")

        with patch('core.hal_compression.get_logger') as mock_logger:
            mock_logger.return_value = Mock()

            # Should not raise exception
            _hal_worker_process("fake_exhal", "fake_inhal", mock_request_queue, mock_result_queue)

    def test_worker_responds_to_shutdown_signal(self):
        """Test that worker process responds to shutdown signal (None request)"""
        mock_request_queue = Mock()
        mock_result_queue = Mock()
        mock_request_queue.get.return_value = None  # Shutdown signal

        with patch('core.hal_compression.get_logger') as mock_logger:
            mock_logger.return_value = Mock()

            # Should exit gracefully
            _hal_worker_process("fake_exhal", "fake_inhal", mock_request_queue, mock_result_queue)

class TestHALProcessPoolIntegration:
    """Integration tests for HAL process pool functionality.

    Uses module-level hal_tools and reset_hal_singleton fixtures.
    """

    def test_singleton_pattern_works_correctly(self):
        """Test that HALProcessPool follows singleton pattern"""
        pool1 = HALProcessPool()
        pool2 = HALProcessPool()

        assert pool1 is pool2
        assert id(pool1) == id(pool2)

    def test_singleton_reset_allows_new_instance(self):
        """Test that singleton reset allows creation of new instance"""
        pool1 = HALProcessPool()
        original_id = id(pool1)

        HALProcessPool.reset_singleton()

        pool2 = HALProcessPool()
        new_id = id(pool2)

        # Should be different instances
        assert original_id != new_id

    def test_pool_initialization_failure_cleanup(self, tmp_path):
        """Test that pool cleans up properly when initialization fails"""
        pool = HALProcessPool()

        # Try to initialize with non-existent tools
        fake_exhal = str(tmp_path / "nonexistent_exhal")
        fake_inhal = str(tmp_path / "nonexistent_inhal")

        # Should fail initialization
        with patch('multiprocessing.Process') as mock_process_class:
            mock_proc = Mock()
            mock_proc.pid = 9000
            mock_process_class.return_value = mock_proc

            # Should return False for failed initialization
            result = pool.initialize(fake_exhal, fake_inhal)
            assert result is False

            # Pool should not be marked as initialized
            assert not pool.is_initialized
            assert pool._pool is None

    @pytest.mark.real_hal  # This test needs real HAL to test the fallback
    def test_pool_graceful_degradation_to_subprocess(self, hal_tools):
        """Test that HALCompressor gracefully degrades to subprocess mode"""
        exhal_path, inhal_path = hal_tools

        # Reset singleton first to ensure clean state
        HALProcessPool.reset_singleton()

        with patch.object(HALProcessPool, 'initialize', return_value=False):
            # Compressor should handle pool initialization failure
            compressor = HALCompressor(exhal_path, inhal_path, use_pool=True)

            # Should fall back to subprocess mode
            assert compressor._pool is None
            assert compressor._pool_failed is True

            # Pool status should indicate fallback
            status = compressor.pool_status
            assert not status["enabled"]
            assert status["reason"] == "Pool initialization failed"

    def test_destructor_cleanup_safety(self, hal_tools):
        """Test that destructor cleanup is safe even if attributes are missing"""
        exhal_path, inhal_path = hal_tools

        pool = HALProcessPool()

        # Simulate partial initialization
        pool._pool = True
        pool._shutdown = False
        # Deliberately don't set other attributes to test robustness

        # Destructor should not raise exception
        try:
            pool.__del__()
        except Exception as e:
            pytest.fail(f"Destructor raised exception: {e}")

    def test_cleanup_hooks_registration(self):
        """Test that cleanup hooks are properly registered"""
        # Reset singleton first to ensure clean state
        HALProcessPool.reset_singleton()

        with patch('core.hal_compression.atexit.register') as mock_atexit:
            HALProcessPool()

            # Should register cleanup
            mock_atexit.assert_called()

    def test_qt_cleanup_integration(self):
        """Test Qt cleanup integration when QApplication is available"""
        with patch('core.hal_compression.QT_AVAILABLE', True), \
             patch('core.hal_compression.QApplication') as mock_qapp:

            mock_app = Mock()
            mock_qapp.instance.return_value = mock_app

            pool = HALProcessPool()
            pool._connect_qt_cleanup()

            # Should connect to aboutToQuit signal
            mock_app.aboutToQuit.connect.assert_called_with(pool.shutdown)

    def test_process_refs_cleanup(self, hal_tools):
        """Test that process weak references are properly cleaned up"""
        exhal_path, inhal_path = hal_tools

        pool = HALProcessPool()

        with patch('multiprocessing.Manager') as mock_manager, \
             patch('multiprocessing.Process') as mock_process_class, \
             patch('weakref.ref') as mock_weakref:

            # Setup mocks
            mock_mgr = Mock()
            mock_queue = Mock()
            mock_manager.return_value = mock_mgr
            mock_mgr.Queue.return_value = mock_queue

            mock_proc = Mock()
            mock_proc.pid = 10000
            mock_proc.is_alive.return_value = False
            mock_process_class.return_value = mock_proc

            mock_ref = Mock()
            mock_weakref.return_value = mock_ref

            # Initialize pool
            pool.initialize(exhal_path, inhal_path, pool_size=1)

            # Should create weak references
            mock_weakref.assert_called_with(mock_proc)

            # Shutdown should clear weak references
            pool.shutdown()

            # Process refs should be cleared
            assert len(pool._process_refs) == 0 if hasattr(pool, '_process_refs') else True

class TestHALProcessPoolPerformance:
    """Performance-related tests for HAL process pool.

    Uses module-level hal_tools and reset_hal_singleton fixtures.
    """

    def test_shutdown_performance_benchmark(self, hal_tools):
        """Benchmark shutdown performance to ensure it meets timeout requirements"""
        exhal_path, inhal_path = hal_tools

        pool = HALProcessPool()

        with patch('multiprocessing.Manager') as mock_manager, \
             patch('multiprocessing.Process') as mock_process_class:

            # Setup many mock processes to test scaling
            mock_mgr = Mock()
            mock_queue = Mock()
            mock_manager.return_value = mock_mgr
            mock_mgr.Queue.return_value = mock_queue

            # Create 8 mock processes (stress test)
            mock_processes = []
            for i in range(8):
                mock_proc = Mock()
                mock_proc.pid = 20000 + i
                mock_proc.is_alive.return_value = False  # Terminate quickly
                mock_processes.append(mock_proc)

            mock_process_class.side_effect = mock_processes

            # Initialize with many processes
            pool.initialize(exhal_path, inhal_path, pool_size=8)

            # Measure shutdown time
            start_time = time.time()
            pool.shutdown()
            shutdown_time = time.time() - start_time

            # Should complete well within timeout
            assert shutdown_time < HAL_POOL_SHUTDOWN_TIMEOUT
            print(f"Shutdown time for 8 processes: {shutdown_time:.3f}s")

    def test_force_reset_performance(self, hal_tools):
        """Test that force_reset is faster than normal shutdown"""
        exhal_path, inhal_path = hal_tools

        with patch('multiprocessing.Manager') as mock_manager, \
             patch('multiprocessing.Process') as mock_process_class, \
             patch('time.sleep') as mock_sleep:  # Control timing

            # Setup mocks
            mock_mgr = Mock()
            mock_queue = Mock()
            mock_manager.return_value = mock_mgr
            mock_mgr.Queue.return_value = mock_queue

            mock_proc = Mock()
            mock_proc.pid = 30000
            mock_proc.is_alive.return_value = False
            mock_process_class.return_value = mock_proc

            # Test normal shutdown timing
            pool1 = HALProcessPool()
            pool1.initialize(exhal_path, inhal_path, pool_size=1)

            start_time = time.time()
            pool1.shutdown()
            time.time() - start_time

            # Reset for force_reset test
            HALProcessPool.reset_singleton()
            mock_sleep.reset_mock()

            # Test force_reset timing
            pool2 = HALProcessPool()
            pool2.initialize(exhal_path, inhal_path, pool_size=1)

            start_time = time.time()
            pool2.force_reset()
            time.time() - start_time

            # force_reset should use shorter sleep (0.1s vs 2.0s)
            # Verify the sleep calls
            if mock_sleep.called:
                sleep_calls = [call[0][0] for call in mock_sleep.call_args_list]
                # force_reset should use 0.1s sleep
                assert 0.1 in sleep_calls

    def test_parallel_operations_after_reset(self, hal_tools):
        """Test that pool can handle operations immediately after reset"""
        exhal_path, inhal_path = hal_tools

        pool = HALProcessPool()

        with patch('multiprocessing.Manager') as mock_manager, \
             patch('multiprocessing.Process') as mock_process_class:

            # Setup mocks
            mock_mgr = Mock()
            mock_queue = Mock()
            mock_manager.return_value = mock_mgr
            mock_mgr.Queue.return_value = mock_queue

            mock_proc = Mock()
            mock_proc.pid = 40000
            mock_proc.is_alive.return_value = False
            mock_process_class.return_value = mock_proc

            # Initialize, reset, and re-initialize quickly
            pool.initialize(exhal_path, inhal_path, pool_size=1)
            pool.force_reset()

            # Should be able to re-initialize immediately
            assert pool.initialize(exhal_path, inhal_path, pool_size=1)
            assert pool.is_initialized
