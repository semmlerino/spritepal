"""
Real Component Factory for type-safe testing with actual components.

This factory creates real managers and components for integration testing,
providing proper type safety without unsafe cast() operations.

USAGE:
    from tests.infrastructure.real_component_factory import RealComponentFactory

    @pytest.fixture
    def real_factory(isolated_managers, tmp_path):
        # isolated_managers ensures managers are initialized
        with RealComponentFactory() as factory:
            yield factory

    def test_extraction(real_factory):
        manager = real_factory.create_extraction_manager()
        result = manager.extract_sprites(params)

BENEFITS:
- No unsafe cast() operations needed
- Real components with actual behavior
- Type checker can verify all operations
- Better integration testing
- Consistent test data from DataRepository
- Proper test isolation (no global state pollution)
"""

from __future__ import annotations

import contextlib
import os
import tempfile
import uuid
import warnings
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar

from PySide6.QtCore import QObject, QThread
from PySide6.QtWidgets import QApplication, QWidget

from core.managers import is_initialized
from core.managers.application_state_manager import ApplicationStateManager
from core.managers.core_operations_manager import CoreOperationsManager
from core.services.rom_cache import ROMCache
from ui.common import WorkerManager
from ui.main_window import MainWindow

from .data_repository import DataRepository, get_test_data_repository

if TYPE_CHECKING:
    from core.rom_extractor import ROMExtractor
    from core.tile_renderer import TileRenderer
    from core.workers import ROMExtractionWorker, VRAMExtractionWorker

class RealComponentFactory:
    """
    Factory for creating real components for testing.

    Provides:
    - Real managers with test data injection
    - Type-safe component creation
    - Proper lifecycle management
    - Integration with DataRepository
    """

    FAIL_ON_LEAKS: ClassVar[bool] = True

    def __init__(
        self,
        *,
        data_repository: DataRepository | None = None,
        settings_dir: Path | None = None,
        fail_on_leaks: bool | None = None,
        manage_registry: bool = False,
    ):
        """
        Initialize the real component factory.

        Args:
            data_repository: Optional test data repository to use
            settings_dir: Optional directory for test settings files.
                         If not provided, a temp directory will be created
                         and cleaned up when cleanup() is called.
            fail_on_leaks: If True, raise AssertionError on resource leaks.
                          If False, emit warnings instead.
                          If None, uses FAIL_ON_LEAKS class variable (default: True).
            manage_registry: If True, this factory takes ownership of the manager
                           lifecycle and will reset it during cleanup(). Use this when
                           the factory is used standalone without manager fixtures.
                           Default: False (manager lifecycle owned by test fixtures).

        Note:
            Managers must be initialized before using this factory.
            Use the `isolated_managers` or `session_managers` fixture to ensure
            managers are properly initialized.
        """
        self._data_repo = data_repository or get_test_data_repository()
        self._temp_dirs: list[Path] = []
        self._created_components: list[QObject] = []
        self._fail_on_leaks = fail_on_leaks if fail_on_leaks is not None else self.FAIL_ON_LEAKS
        self._leaked_resources: list[str] = []
        self._manage_registry = manage_registry
        self._initialized_registry = False  # Track if we initialized it

        # Verify managers are initialized (done by isolated_managers/session_managers fixtures)
        if not is_initialized():
            raise ValueError(
                "RealComponentFactory requires managers to be initialized. "
                "Use isolated_managers or session_managers fixture."
            )
        # Use UUID for guaranteed uniqueness (id() can be reused after object deletion)
        self._unique_id = str(uuid.uuid4())

        # Set up isolated settings directory
        # Priority: explicit arg > SPRITEPAL_SETTINGS_DIR env var > tempfile
        if settings_dir is not None:
            self._settings_dir = settings_dir
        else:
            env_settings = os.environ.get("SPRITEPAL_SETTINGS_DIR")
            if env_settings:
                # Under xdist, use a unique subdir per factory instance
                self._settings_dir = Path(env_settings) / f"factory_{self._unique_id}"
                self._settings_dir.mkdir(parents=True, exist_ok=True)
            else:
                # Create temp settings dir for isolation
                self._settings_dir = Path(tempfile.mkdtemp(prefix="spritepal_settings_"))
                self._temp_dirs.append(self._settings_dir)

        self._settings_path = self._settings_dir / ".testapp_settings.json"

        # Ensure QApplication exists for Qt components
        if QApplication.instance() is None:
            self._app = QApplication([])
        else:
            # Type-safe alternative to cast() - QApplication.instance() can return None
            # but we've already checked it's not None above
            app_instance = QApplication.instance()
            assert app_instance is not None, "QApplication instance should exist"
            self._app = app_instance

        # manager_registry is now required - no fallback to global singleton
        # This ensures proper test isolation and prevents global state pollution

    def _get_extraction_manager_from_registry(self) -> CoreOperationsManager:
        """Get extraction manager (CoreOperationsManager) via AppContext."""
        from core.app_context import get_app_context
        return get_app_context().core_operations_manager

    def _get_injection_manager_from_registry(self) -> CoreOperationsManager:
        """Get injection manager (CoreOperationsManager) via AppContext."""
        from core.app_context import get_app_context
        return get_app_context().core_operations_manager

    def _get_session_manager_from_registry(self) -> ApplicationStateManager:
        """Get session manager (ApplicationStateManager) via AppContext."""
        from core.app_context import get_app_context
        return get_app_context().application_state_manager

    def create_extraction_manager(self, with_test_data: bool = True) -> CoreOperationsManager:
        """
        Get extraction manager (CoreOperationsManager) from registry.

        Args:
            with_test_data: Kept for API compatibility (no-op). Tests should get
                data from DataRepository and pass paths to manager methods directly.

        Returns:
            Real CoreOperationsManager instance from registry
        """
        # Note: with_test_data is intentionally unused. Test data injection via
        # private fields was removed - tests should use DataRepository directly.
        _ = with_test_data
        return self._get_extraction_manager_from_registry()

    def create_injection_manager(self, with_test_data: bool = True) -> CoreOperationsManager:
        """
        Get injection manager (CoreOperationsManager) from registry.

        Args:
            with_test_data: Kept for API compatibility (no-op). Tests should get
                data from DataRepository and pass paths to manager methods directly.

        Returns:
            Real CoreOperationsManager instance from registry
        """
        # Note: with_test_data is intentionally unused. Test data injection via
        # private fields was removed - tests should use DataRepository directly.
        _ = with_test_data
        return self._get_injection_manager_from_registry()

    def create_session_manager(self, app_name: str = "TestApp") -> ApplicationStateManager:
        """
        Get session manager (ApplicationStateManager) from registry.

        Args:
            app_name: Kept for API compatibility (no-op). Session manager is
                pre-configured in the registry.

        Returns:
            Real ApplicationStateManager instance from registry
        """
        # Note: app_name is intentionally unused. Session manager is pre-configured
        # in the registry with proper isolation settings.
        _ = app_name
        return self._get_session_manager_from_registry()

    def create_main_window(self, with_managers: bool = True) -> MainWindow:
        """
        Create a real MainWindow for testing.

        Args:
            with_managers: Whether to initialize with real managers

        Returns:
            Real MainWindow instance
        """
        if with_managers:
            # Ensure managers are initialized with isolated settings
            from core.managers import initialize_managers

            if not is_initialized():
                initialize_managers("TestApp", settings_path=self._settings_path)

        # B.7: Create MainWindow with explicit AppContext dependencies
        from core.app_context import get_app_context

        ctx = get_app_context()
        window = MainWindow(
            settings_manager=ctx.application_state_manager,
            rom_cache=ctx.rom_cache,
            session_manager=ctx.application_state_manager,  # type: ignore[arg-type]  # Protocol vs concrete type mismatch
        )
        self._created_components.append(window)

        # Inject test data paths if needed
        if with_managers:
            test_data = self._data_repo.get_vram_extraction_data("medium")

            # Set up extraction panel with test paths
            if hasattr(window, "extraction_panel") and window.extraction_panel:
                panel = window.extraction_panel
                if hasattr(panel, "vram_input") and panel.vram_input:
                    panel.vram_input.setText(test_data["vram_path"])
                if hasattr(panel, "cgram_input") and panel.cgram_input:
                    panel.cgram_input.setText(test_data["cgram_path"])

        return window

    def create_extraction_worker(self, params: dict[str, Any] | None = None, worker_type: str = "vram") -> VRAMExtractionWorker | ROMExtractionWorker:
        """
        Create a real extraction worker for testing.

        Args:
            params: Optional extraction parameters
            worker_type: Type of worker - "vram" or "rom"

        Returns:
            Real VRAMExtractionWorker or ROMExtractionWorker instance
        """
        from core.app_context import get_app_context
        from core.workers import ROMExtractionWorker, VRAMExtractionWorker

        if params is None:
            if worker_type == "vram":
                params = self._data_repo.get_vram_extraction_data("small")
            else:
                params = self._data_repo.get_rom_extraction_data("small")

        extraction_manager = get_app_context().core_operations_manager

        if worker_type == "vram":
            worker = VRAMExtractionWorker(params, extraction_manager=extraction_manager)
        else:
            worker = ROMExtractionWorker(params, extraction_manager=extraction_manager)

        self._created_components.append(worker)

        return worker

    def create_rom_cache(self, cache_dir: Path | None = None) -> ROMCache:
        """
        Create a real ROM cache for testing.

        Args:
            cache_dir: Optional cache directory

        Returns:
            Real ROMCache instance
        """
        if cache_dir is None:
            # Priority: SPRITEPAL_CACHE_DIR env var > tempfile
            env_cache = os.environ.get("SPRITEPAL_CACHE_DIR")
            if env_cache:
                # Under xdist, use a unique subdir per factory instance
                cache_dir = Path(env_cache) / f"cache_{self._unique_id}"
                cache_dir.mkdir(parents=True, exist_ok=True)
            else:
                cache_dir = Path(tempfile.mkdtemp(prefix="spritepal_cache_"))
                self._temp_dirs.append(cache_dir)

        # Create mock settings manager that returns appropriate values
        from unittest.mock import MagicMock
        mock_settings = MagicMock()
        mock_settings.get_cache_enabled.return_value = True
        mock_settings.get_cache_location.return_value = str(cache_dir)

        cache = ROMCache(state_manager=mock_settings, cache_dir=str(cache_dir))

        return cache

    def create_file_dialogs(self) -> dict[str, Any]:
        """
        Create mock file dialog functions for testing.

        Returns:
            Dictionary of mock file dialog functions configured with test data
        """
        from unittest.mock import Mock

        # Get test data paths from repository
        vram_data = self._data_repo.get_vram_extraction_data("small")
        self._data_repo.get_rom_extraction_data("small")

        return {
            "getOpenFileName": Mock(return_value=(vram_data["vram_path"], "Memory dump (*.dmp)")),
            "getSaveFileName": Mock(return_value=(str(Path(tempfile.gettempdir()) / "output.png"), "PNG files (*.png)")),
            "getExistingDirectory": Mock(return_value=str(Path(tempfile.gettempdir()))),
        }

    def create_tile_renderer(self) -> TileRenderer:
        """
        Create a real TileRenderer for testing.

        Returns:
            Real TileRenderer instance with default palettes
        """
        from core.tile_renderer import TileRenderer

        renderer = TileRenderer()
        return renderer

    def create_rom_extractor(
        self,
        rom_cache: Any | None = None,
        use_mock_hal: bool = True,
    ) -> ROMExtractor:
        """
        Create a real ROMExtractor for testing.

        Args:
            rom_cache: Optional ROMCache instance (creates one if not provided)
            use_mock_hal: If True, patches HAL to use MockHALProcessPool for speed

        Returns:
            Real ROMExtractor instance

        Note:
            By default uses MockHALProcessPool for fast integration tests.
            Use @pytest.mark.real_hal and use_mock_hal=False for full HAL testing.
        """
        from core.rom_extractor import ROMExtractor

        if rom_cache is None:
            rom_cache = self.create_rom_cache()

        if use_mock_hal:
            # Use mock HAL for fast tests
            from tests.infrastructure.mock_hal import MockHALProcessPool

            # Create extractor
            extractor = ROMExtractor(rom_cache=rom_cache)

            # Replace HAL with mock for speed
            mock_hal = MockHALProcessPool()
            mock_hal.initialize("mock_exhal", "mock_inhal")
            extractor.hal_compressor._process_pool = mock_hal
        else:
            # Use real HAL
            extractor = ROMExtractor(rom_cache=rom_cache)

        return extractor

    def cleanup(self) -> None:
        """Clean up all created components and temporary files.

        Note: By default raises AssertionError on resource leaks (fail_on_leaks=True).
        Set fail_on_leaks=False to emit warnings instead.
        This helps identify resource leaks during test development.
        """
        # Step 1: Clean up all WorkerManager-registered workers FIRST
        # This is the primary goal - ensure worker threads are properly stopped
        try:
            cleanup_count = WorkerManager.cleanup_all()
            if cleanup_count > 0:
                leak_msg = f"RealComponentFactory cleaned up {cleanup_count} worker thread(s)"
                self._leaked_resources.append(leak_msg)
        except Exception as e:
            leak_msg = f"WorkerManager.cleanup_all() failed: {e}"
            self._leaked_resources.append(leak_msg)

        # Step 2: Manager lifecycle is owned by test fixtures (session_managers,
        # isolated_managers). RealComponentFactory MUST NOT call cleanup_managers()
        # because:
        # - session_managers: Managers persist for entire session
        # - isolated_managers: Fixture handles cleanup after test
        # - Neither: Test infrastructure expects consistent state
        # Calling cleanup_managers() here would break fixture contracts and cause
        # "Session managers were cleaned up mid-session" errors.

        # Step 2: Clean up Qt components
        for component in self._created_components:
            try:
                if isinstance(component, QThread):
                    if component.isRunning():
                        component.quit()
                        # Increased timeout from 1s to 5s for CI environments
                        if not component.wait(5000):
                            leak_msg = f"Thread {component} did not terminate within 5 seconds"
                            self._leaked_resources.append(leak_msg)
                            continue  # Skip deleteLater on still-running thread
                elif isinstance(component, QWidget):
                    component.close()

                component.deleteLater()
            except Exception as e:
                # Track cleanup failures as leaks
                leak_msg = f"Cleanup failed for {component}: {e}"
                self._leaked_resources.append(leak_msg)

        self._created_components.clear()

        # Step 3: Process Qt events to allow deleteLater() calls to complete
        # Single call is sufficient - Qt processes all pending events in one pass
        try:
            if QApplication.instance():
                QApplication.processEvents()
        except Exception as e:
            warnings.warn(
                f"Failed to process Qt events during cleanup: {e}",
                ResourceWarning,
                stacklevel=2,
            )

        # Step 4: Skip explicit gc.collect() during cleanup
        # Reason: gc.collect() can trigger finalization of PySide6/Qt objects
        # while background threads are still running, which causes segfaults.
        # Qt object cleanup is handled via deleteLater() and processEvents() above.
        # The Python GC will clean up remaining objects naturally when safe.

        # Step 5: Removed time.sleep(0.05)
        # The explicit thread.wait(5000) calls above ensure threads have terminated.
        # Additional sleep is redundant and adds unnecessary test overhead.

        # Step 6: Clean up temp directories
        import shutil
        for temp_dir in self._temp_dirs:
            if temp_dir.exists():
                with contextlib.suppress(Exception):
                    shutil.rmtree(temp_dir)

        self._temp_dirs.clear()

        # Step 7: Manager cleanup (if we initialized them)
        # Clean up managers if we were the ones who initialized them.
        # Note: With manage_registry=False (default), cleanup will still happen
        # if WE initialized managers - this prevents pollution between tests.
        if self._initialized_registry:
            try:
                from core.managers import cleanup_managers, reset_for_tests

                if is_initialized():
                    cleanup_managers()
                    reset_for_tests()
                self._initialized_registry = False
            except Exception as e:
                warnings.warn(
                    f"Failed to clean up managers: {e}",
                    ResourceWarning,
                    stacklevel=2,
                )

        # Step 8: Final leak reporting
        if self._leaked_resources:
            if self._fail_on_leaks:
                msg = "Resource leaks detected during cleanup:\n" + "\n".join(
                    f"  - {leak}" for leak in self._leaked_resources
                )
                raise AssertionError(msg)
            else:
                for leak in self._leaked_resources:
                    warnings.warn(leak, ResourceWarning, stacklevel=2)

    def __enter__(self) -> RealComponentFactory:
        """Context manager entry."""
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Context manager exit with cleanup."""
        try:
            self.cleanup()
        except AssertionError:
            if exc_type is None:
                # Test succeeded but cleanup found leaks - re-raise
                raise
            # Test already failed - log leaks as warnings instead
            for leak in self._leaked_resources:
                warnings.warn(leak, ResourceWarning, stacklevel=2)

