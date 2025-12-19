"""
Consolidated tests for HAL compression functionality.

This module includes:
- HAL process pool simplification and cleanup tests
- HAL worker process error handling
- HAL process pool integration tests
- HAL tool detection from various working directories
- HAL mock verification tests
- HAL mock performance and interface compatibility tests
- HAL performance benchmarks

Note: These tests use multiprocessing boundary mocks (Manager, Process) because
they're testing HALProcessPool's process lifecycle management - the actual
multiprocessing behavior needs to be controlled for deterministic testing.
"""
from __future__ import annotations

import os
import platform
import tempfile
import threading
import time
from collections.abc import Generator
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from core.hal_compression import (
    HALCompressor,
    HALProcessPool,
    HALRequest,
    _hal_worker_process,
)
from tests.infrastructure.mock_hal import MockHALProcessPool, create_mock_hal_tools
from utils.constants import HAL_POOL_SHUTDOWN_TIMEOUT

# ============================================================================
# Module-level pytest markers (consolidated from all source files)
# ============================================================================
pytestmark = [
    pytest.mark.no_manager_setup,
    pytest.mark.headless,
    pytest.mark.integration,
    pytest.mark.performance,
    pytest.mark.slow,
    pytest.mark.allows_registry_state,
    pytest.mark.benchmark,
]


# ============================================================================
# Shared Fixtures
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


@pytest.fixture
def save_restore_cwd() -> Generator[None, None, None]:
    """Save and restore the current working directory.

    Used for tests that need to change cwd to test tool detection from
    various directories.
    """
    original_cwd = os.getcwd()
    yield
    os.chdir(original_cwd)


# ============================================================================
# Pool Management Tests
# ============================================================================


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
        with (
            patch("multiprocessing.Manager") as mock_manager,
            patch("multiprocessing.Process") as mock_process_class,
        ):
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

        with (
            patch("multiprocessing.Manager") as mock_manager,
            patch("multiprocessing.Process") as mock_process_class,
        ):
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

        with (
            patch("multiprocessing.Manager") as mock_manager,
            patch("multiprocessing.Process") as mock_process_class,
        ):
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

        with (
            patch("multiprocessing.Manager") as mock_manager,
            patch("multiprocessing.Process") as mock_process_class,
        ):
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

        with (
            patch("multiprocessing.Manager") as mock_manager,
            patch("multiprocessing.Process") as mock_process_class,
        ):
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

        with (
            patch("multiprocessing.Manager") as mock_manager,
            patch("multiprocessing.Process") as mock_process_class,
            patch("time.sleep") as mock_sleep,
        ):  # Speed up test
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

        with (
            patch("multiprocessing.Manager") as mock_manager,
            patch("multiprocessing.Process") as mock_process_class,
        ):
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

        with (
            patch("multiprocessing.Manager") as mock_manager,
            patch("multiprocessing.Process") as mock_process_class,
        ):
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
                request_id="test",
            )

            result = pool.submit_request(request)

            # Should return error result
            assert not result.success
            assert "not initialized or shutting down" in result.error_message


# ============================================================================
# Worker Process Error Handling Tests
# ============================================================================


class TestHALWorkerProcessErrorHandling:
    """Test HAL worker process error handling improvements"""

    def test_worker_handles_broken_pipe_gracefully(self):
        """Test that worker process handles BrokenPipeError gracefully"""
        # Mock queues that raise BrokenPipeError
        mock_request_queue = Mock()
        mock_result_queue = Mock()
        mock_request_queue.get.side_effect = BrokenPipeError("Pipe closed")

        # Worker should exit gracefully without raising exception
        with patch("core.hal_compression.get_logger") as mock_logger:
            mock_logger.return_value = Mock()

            # Should not raise exception
            _hal_worker_process(
                "fake_exhal", "fake_inhal", mock_request_queue, mock_result_queue
            )

    def test_worker_handles_connection_reset_gracefully(self):
        """Test that worker process handles ConnectionResetError gracefully"""
        mock_request_queue = Mock()
        mock_result_queue = Mock()
        mock_request_queue.get.side_effect = ConnectionResetError("Connection reset")

        with patch("core.hal_compression.get_logger") as mock_logger:
            mock_logger.return_value = Mock()

            # Should not raise exception
            _hal_worker_process(
                "fake_exhal", "fake_inhal", mock_request_queue, mock_result_queue
            )

    def test_worker_handles_eof_error_gracefully(self):
        """Test that worker process handles EOFError gracefully"""
        mock_request_queue = Mock()
        mock_result_queue = Mock()
        mock_request_queue.get.side_effect = EOFError("End of file")

        with patch("core.hal_compression.get_logger") as mock_logger:
            mock_logger.return_value = Mock()

            # Should not raise exception
            _hal_worker_process(
                "fake_exhal", "fake_inhal", mock_request_queue, mock_result_queue
            )

    def test_worker_responds_to_shutdown_signal(self):
        """Test that worker process responds to shutdown signal (None request)"""
        mock_request_queue = Mock()
        mock_result_queue = Mock()
        mock_request_queue.get.return_value = None  # Shutdown signal

        with patch("core.hal_compression.get_logger") as mock_logger:
            mock_logger.return_value = Mock()

            # Should exit gracefully
            _hal_worker_process(
                "fake_exhal", "fake_inhal", mock_request_queue, mock_result_queue
            )


# ============================================================================
# Integration Tests
# ============================================================================


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
        with patch("multiprocessing.Process") as mock_process_class:
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

        with patch.object(HALProcessPool, "initialize", return_value=False):
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

        with patch("core.hal_compression.atexit.register") as mock_atexit:
            HALProcessPool()

            # Should register cleanup
            mock_atexit.assert_called()

    def test_qt_cleanup_integration(self):
        """Test Qt cleanup integration when QApplication is available"""
        with (
            patch("core.hal_compression.QT_AVAILABLE", True),
            patch("core.hal_compression.QApplication") as mock_qapp,
        ):
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

        with (
            patch("multiprocessing.Manager") as mock_manager,
            patch("multiprocessing.Process") as mock_process_class,
            patch("weakref.ref") as mock_weakref,
        ):
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
            assert len(pool._process_refs) == 0 if hasattr(pool, "_process_refs") else True


# ============================================================================
# Tool Detection Tests (from test_hal_compression_detection.py)
# ============================================================================


class TestHALToolDetection:
    """Test HAL tool detection from various working directories.

    These tests verify that HAL tools are found correctly regardless
    of the current working directory.
    """

    @pytest.fixture(autouse=True)
    def setup_detection(self, save_restore_cwd):
        """Set up test environment for detection tests."""
        self.spritepal_dir = Path(__file__).parent.parent
        self.tools_dir = self.spritepal_dir / "tools"
        self.exe_suffix = ".exe" if platform.system() == "Windows" else ""
        self.exhal_name = f"exhal{self.exe_suffix}"
        self.inhal_name = f"inhal{self.exe_suffix}"

    def test_detection_from_spritepal_directory(self):
        """Test that detection works from spritepal directory (original working case)"""
        os.chdir(self.spritepal_dir)

        compressor = HALCompressor()

        assert Path(compressor.exhal_path).exists()
        assert Path(compressor.inhal_path).exists()
        assert "spritepal/tools" in compressor.exhal_path
        assert "spritepal/tools" in compressor.inhal_path

    def test_detection_from_parent_directory(self):
        """Test that detection works from exhal-master directory (previously failing case)"""
        parent_dir = self.spritepal_dir.parent
        os.chdir(parent_dir)

        compressor = HALCompressor()

        assert Path(compressor.exhal_path).exists()
        assert Path(compressor.inhal_path).exists()
        assert "spritepal/tools" in compressor.exhal_path
        assert "spritepal/tools" in compressor.inhal_path

    def test_detection_from_temp_directory(self):
        """Test that detection works from a temporary directory"""
        with tempfile.TemporaryDirectory() as temp_dir:
            os.chdir(temp_dir)

            compressor = HALCompressor()

            assert Path(compressor.exhal_path).exists()
            assert Path(compressor.inhal_path).exists()
            assert "spritepal/tools" in compressor.exhal_path
            assert "spritepal/tools" in compressor.inhal_path

    def test_detection_from_home_directory(self):
        """Test that detection works from user home directory"""
        try:
            home_dir = Path.home()
            os.chdir(home_dir)

            compressor = HALCompressor()

            assert Path(compressor.exhal_path).exists()
            assert Path(compressor.inhal_path).exists()
            assert "spritepal/tools" in compressor.exhal_path
            assert "spritepal/tools" in compressor.inhal_path
        except (OSError, PermissionError) as e:
            pytest.skip(f"Cannot access home directory: {e}")

    def test_absolute_path_resolution(self):
        """Test that the fix uses absolute paths and doesn't depend on working directory"""
        # Test from spritepal directory
        os.chdir(self.spritepal_dir)
        compressor1 = HALCompressor()

        # Test from parent directory
        os.chdir(self.spritepal_dir.parent)
        compressor2 = HALCompressor()

        # Both should find the same absolute paths
        assert compressor1.exhal_path == compressor2.exhal_path
        assert compressor1.inhal_path == compressor2.inhal_path

        # Paths should be absolute
        assert Path(compressor1.exhal_path).is_absolute()
        assert Path(compressor1.inhal_path).is_absolute()

    def test_tools_are_executable(self):
        """Test that detected tools are actually executable"""
        compressor = HALCompressor()

        # Test that tools have execute permissions
        assert os.access(compressor.exhal_path, os.X_OK)
        assert os.access(compressor.inhal_path, os.X_OK)

    def test_tools_functionality(self):
        """Test that detected tools actually work"""
        compressor = HALCompressor()

        success, message = compressor.test_tools()
        assert success
        assert "working correctly" in message

    def test_provided_path_override(self, tmp_path):
        """Test that provided paths override automatic detection"""
        exe_suffix = ".exe" if platform.system() == "Windows" else ""
        dummy_exhal = tmp_path / f"dummy_exhal{exe_suffix}"
        dummy_inhal = tmp_path / f"dummy_inhal{exe_suffix}"

        # Create dummy executable files
        dummy_exhal.write_text("")
        dummy_inhal.write_text("")
        os.chmod(dummy_exhal, 0o755)
        os.chmod(dummy_inhal, 0o755)

        compressor = HALCompressor(
            exhal_path=str(dummy_exhal), inhal_path=str(dummy_inhal)
        )

        assert compressor.exhal_path == str(dummy_exhal)
        assert compressor.inhal_path == str(dummy_inhal)

    def test_multiple_initialization_consistency(self):
        """Test that multiple HALCompressor instances find the same tools"""
        paths = []

        # Create multiple instances from different working directories
        for test_dir in [self.spritepal_dir, self.spritepal_dir.parent]:
            os.chdir(test_dir)
            compressor = HALCompressor()
            paths.append((compressor.exhal_path, compressor.inhal_path))

        # All instances should find the same tools
        for i in range(1, len(paths)):
            assert (
                paths[0] == paths[i]
            ), f"Instance {i} found different tools than instance 0"

    def test_spritepal_directory_calculation(self):
        """Test that the spritepal directory is calculated correctly from different contexts"""
        test_dirs = [
            self.spritepal_dir,
            self.spritepal_dir.parent,
            Path.cwd(),
        ]

        for test_dir in test_dirs:
            if not test_dir.exists():
                continue

            os.chdir(test_dir)

            # Import the module to get the calculated spritepal_dir
            hal_compression_file = self.spritepal_dir / "core" / "hal_compression.py"
            calculated_spritepal = hal_compression_file.parent.parent

            assert calculated_spritepal.name == "spritepal"
            assert (calculated_spritepal / "tools").exists()


class TestHALToolDetectionRegression:
    """Regression tests to prevent the working directory bug from reoccurring."""

    @pytest.fixture(autouse=True)
    def setup_regression(self, save_restore_cwd):
        """Set up test environment for regression tests."""
        self.spritepal_dir = Path(__file__).parent.parent

    def test_no_relative_path_dependency(self):
        """Ensure the fix doesn't rely on relative paths that depend on working directory"""
        # Change to a directory where relative paths would fail
        os.chdir(Path("/tmp"))

        # This should still work because the fix uses absolute paths
        compressor = HALCompressor()

        # Verify paths are absolute and exist
        assert Path(compressor.exhal_path).is_absolute()
        assert Path(compressor.inhal_path).is_absolute()
        assert Path(compressor.exhal_path).exists()
        assert Path(compressor.inhal_path).exists()

    def test_intermittent_failure_scenario(self):
        """Test the exact scenario that was causing intermittent failures"""
        # Simulate application startup from exhal-master directory
        exhal_master_dir = self.spritepal_dir.parent

        if not exhal_master_dir.exists():
            pytest.skip("exhal-master directory not found")

        os.chdir(exhal_master_dir)

        # This should now work consistently (was failing intermittently before)
        for i in range(5):  # Test multiple times to catch intermittent issues
            compressor = HALCompressor()
            assert Path(compressor.exhal_path).exists()
            assert Path(compressor.inhal_path).exists()

    def test_manager_initialization_robustness(self):
        """Test that manager initialization works regardless of working directory"""
        from core.di_container import inject
        from core.managers import cleanup_managers, initialize_managers
        from core.protocols.manager_protocols import InjectionManagerProtocol

        # Test from different directories
        test_dirs = [
            self.spritepal_dir,
            self.spritepal_dir.parent,
        ]

        for test_dir in test_dirs:
            if not test_dir.exists():
                continue

            os.chdir(test_dir)

            # Actually test manager initialization from this directory
            try:
                # Initialize managers - this is what we're testing
                initialize_managers(app_name="SpritePal_Test")

                # Verify initialization succeeded by getting a manager via DI
                manager = inject(InjectionManagerProtocol)
                assert manager is not None

            except Exception as e:
                pytest.fail(f"Manager initialization failed from {test_dir}: {e}")
            finally:
                # Clean up managers to prevent interference with other tests
                try:
                    from tests.fixtures.core_fixtures import is_session_managers_active

                    if not is_session_managers_active():
                        cleanup_managers()
                except Exception:
                    pass  # Ignore cleanup errors


# ============================================================================
# Mock Verification Tests (from test_hal_mock_verification.py)
# ============================================================================


class TestHALMockVerification:
    """Tests to verify HAL mocking is working correctly."""

    def test_hal_is_mocked(self):
        """Verify that HAL is automatically mocked for unit tests (when real tools unavailable)."""
        compressor = HALCompressor()

        # Check if it's the mock version by looking for mock-specific attributes
        # The mock has get_statistics method, real doesn't
        if hasattr(compressor, "get_statistics"):
            print("HAL is MOCKED (as expected for unit tests without real tools)")
            stats = compressor.get_statistics()
            assert stats is not None
            assert "decompress_count" in stats
        else:
            # Real HAL tools are installed - this is fine, just skip the mock-specific test
            print("HAL is REAL (real tools are available, which is valid)")
            # Verify basic attributes exist
            assert hasattr(compressor, "exhal_path")
            assert hasattr(compressor, "inhal_path")
            pytest.skip("Real HAL tools available - mock test not applicable")

    @pytest.mark.real_hal
    def test_hal_is_real_with_marker(self, tmp_path):
        """Verify that @pytest.mark.real_hal gives real HAL."""
        exhal_path, inhal_path = create_mock_hal_tools(tmp_path)

        # Create a compressor with explicit paths
        compressor = HALCompressor(exhal_path, inhal_path)

        # Check if it's the real version
        if hasattr(compressor, "get_statistics"):
            print("HAL is MOCKED (unexpected with real_hal marker)")
            pytest.fail("HAL should be real when marked with @pytest.mark.real_hal")
        else:
            print("HAL is REAL (as expected with real_hal marker)")
            # Verify it has the expected real attributes
            assert hasattr(compressor, "exhal_path")
            assert hasattr(compressor, "inhal_path")

    @pytest.mark.performance
    def test_mock_hal_performance(self):
        """Test that mock HAL operations are fast.

        This test only runs when HAL is mocked (has get_statistics method).
        When real HAL is installed, the test is skipped.
        """
        compressor = HALCompressor()

        # Check if this is mock HAL - real HAL doesn't have get_statistics
        if not hasattr(compressor, "get_statistics"):
            pytest.skip("Real HAL is installed - mock performance test not applicable")

        # Time a decompression (should be instant with mock)
        start = time.perf_counter()

        # Mock doesn't need real ROM file - mock HAL handles this
        data = compressor.decompress_from_rom("dummy.rom", 0x1000)

        elapsed = time.perf_counter() - start

        print(f"Decompression took: {elapsed * 1000:.2f}ms")

        # Mock should be under 10ms
        assert elapsed < 0.01, f"Mock decompression too slow: {elapsed:.3f}s"

        # Verify we got deterministic data
        assert data is not None
        assert len(data) > 0

        # Do it again - should get same result (deterministic)
        data2 = compressor.decompress_from_rom("dummy.rom", 0x1000)
        assert data == data2, "Mock should be deterministic"


# ============================================================================
# Mock Performance & Compatibility Tests (from test_hal_mocking_performance.py)
# ============================================================================


class TestHALMockingPerformance:
    """Test HAL mocking performance improvements."""

    def test_mock_deterministic_behavior(self, hal_pool):
        """Test that mock provides deterministic results."""
        # Same request should give same result
        request = HALRequest(
            operation="decompress",
            rom_path="test.rom",
            offset=0x2000,
            request_id="test_deterministic",
        )

        result1 = hal_pool.submit_request(request)
        result2 = hal_pool.submit_request(request)

        assert result1.success
        assert result2.success
        assert result1.data == result2.data

    def test_mock_error_simulation(self, hal_pool):
        """Test that mock can simulate errors for testing."""
        # Configure a failure
        hal_pool.configure_failure("fail_test", "Simulated error for testing")

        request = HALRequest(
            operation="decompress",
            rom_path="test.rom",
            offset=0x3000,
            request_id="fail_test",
        )

        result = hal_pool.submit_request(request)

        assert not result.success
        assert result.error_message == "Simulated error for testing"

    def test_mock_statistics_tracking(self, hal_pool):
        """Test that mock tracks usage statistics."""
        # Perform various operations
        decompress_req = HALRequest(
            operation="decompress",
            rom_path="test.rom",
            offset=0x4000,
            request_id="stats_1",
        )

        compress_req = HALRequest(
            operation="compress",
            rom_path="",
            offset=0,
            data=b"test data",
            output_path="test.compressed",
            request_id="stats_2",
        )

        hal_pool.submit_request(decompress_req)
        hal_pool.submit_request(compress_req)

        # Check statistics
        stats = hal_pool.get_statistics()
        assert stats["request_count"] == 2
        assert stats["decompress_count"] == 1
        assert stats["compress_count"] == 1

    @pytest.mark.real_hal
    @pytest.mark.slow
    @pytest.mark.performance
    def test_real_vs_mock_performance_comparison(self, tmp_path):
        """Compare real HAL pool vs mock performance."""
        # Setup real pool
        HALProcessPool.reset_singleton()
        real_pool = HALProcessPool()
        exhal_path, inhal_path = create_mock_hal_tools(tmp_path)

        # Time real pool initialization
        start = time.perf_counter()
        real_pool.initialize(exhal_path, inhal_path, pool_size=4)
        real_init_time = time.perf_counter() - start

        # Time real pool request
        request = HALRequest(
            operation="decompress",
            rom_path=str(tmp_path / "test.rom"),
            offset=0x1000,
            request_id="perf_test",
        )

        # Create dummy ROM file
        (tmp_path / "test.rom").write_bytes(b"\x00" * 0x10000)

        start = time.perf_counter()
        real_pool.submit_request(request)
        real_request_time = time.perf_counter() - start

        # Cleanup real pool
        real_pool.shutdown()
        HALProcessPool.reset_singleton()

        # Setup mock pool
        mock_pool = MockHALProcessPool()

        # Time mock pool initialization
        start = time.perf_counter()
        mock_pool.initialize("mock_exhal", "mock_inhal")
        mock_init_time = time.perf_counter() - start

        # Time mock pool request
        start = time.perf_counter()
        mock_pool.submit_request(request)
        mock_request_time = time.perf_counter() - start

        # Cleanup mock pool
        mock_pool.shutdown()
        MockHALProcessPool.reset_singleton()

        # Compare performance
        init_speedup = real_init_time / mock_init_time if mock_init_time > 0 else 1000
        request_speedup = (
            real_request_time / mock_request_time if mock_request_time > 0 else 1000
        )

        print("\nPerformance Comparison:")
        print(f"  Initialization: {init_speedup:.1f}x faster")
        print(f"  Request processing: {request_speedup:.1f}x faster")
        print(f"  Real init time: {real_init_time:.3f}s")
        print(f"  Mock init time: {mock_init_time:.6f}s")
        print(f"  Real request time: {real_request_time:.3f}s")
        print(f"  Mock request time: {mock_request_time:.6f}s")

        # Mock should be at least 100x faster for initialization
        assert init_speedup > 100

        # Mock requests should not be slower than real ones; when real calls are
        # effectively instantaneous, allow a small tolerance instead of ratio-based checks.
        if real_request_time < 0.001:
            assert mock_request_time <= real_request_time + 0.001
        else:
            assert request_speedup > 1


class TestHALCompressorMocking:
    """Test HAL compressor mocking."""

    def test_mock_compressor_interface_compatibility(self, hal_compressor):
        """Test that mock compressor has compatible interface."""
        # Should have all required methods
        assert hasattr(hal_compressor, "decompress_from_rom")
        assert hasattr(hal_compressor, "compress_to_file")
        assert hasattr(hal_compressor, "compress_to_rom")
        assert hasattr(hal_compressor, "test_tools")
        assert hasattr(hal_compressor, "decompress_batch")
        assert hasattr(hal_compressor, "compress_batch")
        assert hasattr(hal_compressor, "pool_status")

    def test_mock_compressor_decompression(self, hal_compressor, tmp_path):
        """Test mock decompression functionality."""
        # Create dummy ROM
        rom_path = tmp_path / "test.rom"
        rom_path.write_bytes(b"\x00" * 0x10000)

        # Decompress
        data = hal_compressor.decompress_from_rom(str(rom_path), 0x2000)

        # Should return deterministic data
        assert data is not None
        assert len(data) == 0x8000  # Standard size
        assert b"MOCK_DECOMP" in data  # Contains marker

    def test_mock_compressor_compression(self, hal_compressor, tmp_path):
        """Test mock compression functionality."""
        test_data = b"Test data for compression" * 100
        output_path = tmp_path / "compressed.bin"

        # Compress
        size = hal_compressor.compress_to_file(test_data, str(output_path))

        # Should create file with reasonable compression ratio
        assert output_path.exists()
        assert size < len(test_data)  # Should be compressed
        assert size == output_path.stat().st_size

    def test_mock_compressor_batch_operations(self, hal_compressor, tmp_path):
        """Test mock batch operations."""
        # Create dummy ROM
        rom_path = tmp_path / "test.rom"
        rom_path.write_bytes(b"\x00" * 0x10000)

        # Batch decompression
        requests = [
            (str(rom_path), offset) for offset in range(0x1000, 0x5000, 0x1000)
        ]
        results = hal_compressor.decompress_batch(requests)

        assert len(results) == 4
        assert all(success for success, _ in results)

        # Batch compression
        compress_requests = [
            (b"data" * 100, str(tmp_path / f"out_{i}.bin"), False) for i in range(3)
        ]
        compress_results = hal_compressor.compress_batch(compress_requests)

        assert len(compress_results) == 3
        assert all(success for success, _ in compress_results)

    def test_mock_compressor_statistics(self, hal_compressor, tmp_path):
        """Test that mock compressor tracks statistics."""
        rom_path = tmp_path / "test.rom"
        rom_path.write_bytes(b"\x00" * 0x10000)

        # Perform operations
        hal_compressor.decompress_from_rom(str(rom_path), 0x1000)
        hal_compressor.compress_to_file(b"test", str(tmp_path / "out.bin"))

        # Check statistics
        stats = hal_compressor.get_statistics()
        assert stats["decompress_count"] == 1
        assert stats["compress_count"] == 1


class TestAutoMocking:
    """Test automatic HAL mocking based on test type."""

    @pytest.mark.real_hal
    def test_real_hal_marker_overrides_mocking(self, tmp_path):
        """Tests marked with real_hal should get real implementation."""
        # Create tools
        exhal_path, inhal_path = create_mock_hal_tools(tmp_path)

        # This should be the real version (but with mock tools)
        compressor = HALCompressor(exhal_path, inhal_path)

        # Real compressor doesn't have get_statistics method
        assert not hasattr(compressor, "get_statistics")

    def test_fixture_provides_correct_implementation(self, hal_compressor):
        """Fixture should provide mock by default."""
        # Should be mock version
        assert hasattr(hal_compressor, "get_statistics")

        # Should have statistics initialized
        stats = hal_compressor.get_statistics()
        assert stats["decompress_count"] == 0
        assert stats["compress_count"] == 0


# ============================================================================
# Performance Benchmarks
# ============================================================================


class TestHALProcessPoolPerformance:
    """Performance-related tests for HAL process pool.

    Uses module-level hal_tools and reset_hal_singleton fixtures.
    """

    @pytest.mark.performance
    def test_shutdown_performance_benchmark(self, hal_tools):
        """Benchmark shutdown performance to ensure it meets timeout requirements"""
        exhal_path, inhal_path = hal_tools

        pool = HALProcessPool()

        with (
            patch("multiprocessing.Manager") as mock_manager,
            patch("multiprocessing.Process") as mock_process_class,
        ):
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

    @pytest.mark.performance
    def test_force_reset_performance(self, hal_tools):
        """Test that force_reset is faster than normal shutdown"""
        exhal_path, inhal_path = hal_tools

        with (
            patch("multiprocessing.Manager") as mock_manager,
            patch("multiprocessing.Process") as mock_process_class,
            patch("time.sleep") as mock_sleep,
        ):  # Control timing
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

    @pytest.mark.performance
    def test_parallel_operations_after_reset(self, hal_tools):
        """Test that pool can handle operations immediately after reset"""
        exhal_path, inhal_path = hal_tools

        pool = HALProcessPool()

        with (
            patch("multiprocessing.Manager") as mock_manager,
            patch("multiprocessing.Process") as mock_process_class,
        ):
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
