"""
Real Component Factory for type-safe testing with actual components.

This factory creates real managers and components for integration testing,
providing proper type safety without unsafe cast() operations.

USAGE:
    from tests.infrastructure.real_component_factory import RealComponentFactory

    # REQUIRED: Pass manager_registry from isolated_managers fixture
    @pytest.fixture
    def real_factory(isolated_managers, tmp_path):
        with RealComponentFactory(manager_registry=isolated_managers) as factory:
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

import os
import tempfile
import warnings
from pathlib import Path
import contextlib
from typing import TYPE_CHECKING, Any, ClassVar

from PySide6.QtCore import QObject, QThread
from PySide6.QtWidgets import QApplication, QWidget

from core.managers.application_state_manager import ApplicationStateManager
from core.managers.core_operations_manager import CoreOperationsManager
from core.managers.registry import ManagerRegistry
from ui.common import WorkerManager
from ui.main_window import MainWindow

from core.services.rom_cache import ROMCache

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
        manager_registry: ManagerRegistry,
        data_repository: DataRepository | None = None,
        settings_dir: Path | None = None,
        fail_on_leaks: bool | None = None,
        manage_registry: bool = False,
    ):
        """
        Initialize the real component factory.

        Args:
            manager_registry: Pre-initialized ManagerRegistry for test isolation.
                            REQUIRED. Pass `isolated_managers` fixture from tests.
                            This ensures proper test isolation and prevents global
                            state pollution.
            data_repository: Optional test data repository to use
            settings_dir: Optional directory for test settings files.
                         If not provided, a temp directory will be created
                         and cleaned up when cleanup() is called.
            fail_on_leaks: If True, raise AssertionError on resource leaks.
                          If False, emit warnings instead.
                          If None, uses FAIL_ON_LEAKS class variable (default: True).
            manage_registry: If True, this factory takes ownership of the ManagerRegistry
                           lifecycle and will reset it during cleanup(). Use this when
                           the factory is used standalone without manager fixtures.
                           Default: False (registry lifecycle owned by test fixtures).
        """
        self._data_repo = data_repository or get_test_data_repository()
        self._temp_dirs: list[Path] = []
        self._created_components: list[QObject] = []
        self._fail_on_leaks = fail_on_leaks if fail_on_leaks is not None else self.FAIL_ON_LEAKS
        self._leaked_resources: list[str] = []
        self._manage_registry = manage_registry
        self._initialized_registry = False  # Track if we initialized it
        self._manager_registry = manager_registry  # Store provided registry for isolation

        # Set up isolated settings directory
        # Priority: explicit arg > SPRITEPAL_SETTINGS_DIR env var > tempfile
        if settings_dir is not None:
            self._settings_dir = settings_dir
        else:
            env_settings = os.environ.get("SPRITEPAL_SETTINGS_DIR")
            if env_settings:
                # Under xdist, use a unique subdir per factory instance
                self._settings_dir = Path(env_settings) / f"factory_{id(self)}"
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
        """Get extraction manager (CoreOperationsManager) via DI."""
        from core.di_container import inject
        from core.protocols.manager_protocols import ExtractionManagerProtocol
        return inject(ExtractionManagerProtocol)  # type: ignore[return-value]

    def _get_injection_manager_from_registry(self) -> CoreOperationsManager:
        """Get injection manager (CoreOperationsManager) via DI."""
        from core.di_container import inject
        from core.protocols.manager_protocols import InjectionManagerProtocol
        return inject(InjectionManagerProtocol)  # type: ignore[return-value]

    def _get_session_manager_from_registry(self) -> ApplicationStateManager:
        """Get session manager (ApplicationStateManager) via DI."""
        from core.di_container import inject
        from core.protocols.manager_protocols import ApplicationStateManagerProtocol
        return inject(ApplicationStateManagerProtocol)  # type: ignore[return-value]

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
            registry = ManagerRegistry()
            if not registry.is_initialized():
                registry.initialize_managers("TestApp", settings_path=self._settings_path)

                # Register UI factories with DI container (after managers are initialized)
                from ui import register_ui_factories
                register_ui_factories()

        # B.7: Create MainWindow with explicit DI dependencies (matching B.6 pattern)
        from core.di_container import inject
        from core.protocols.manager_protocols import (
            ApplicationStateManagerProtocol,
            ROMCacheProtocol,
            SettingsManagerProtocol,
        )

        window = MainWindow(
            settings_manager=inject(SettingsManagerProtocol),
            rom_cache=inject(ROMCacheProtocol),
            session_manager=inject(ApplicationStateManagerProtocol),  # type: ignore[arg-type]  # Protocol vs concrete type mismatch
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
        from core.di_container import inject
        from core.protocols.manager_protocols import ExtractionManagerProtocol
        from core.workers import ROMExtractionWorker, VRAMExtractionWorker

        if params is None:
            if worker_type == "vram":
                params = self._data_repo.get_vram_extraction_data("small")
            else:
                params = self._data_repo.get_rom_extraction_data("small")

        extraction_manager = inject(ExtractionManagerProtocol)

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
                cache_dir = Path(env_cache) / f"cache_{id(self)}"
                cache_dir.mkdir(parents=True, exist_ok=True)
            else:
                cache_dir = Path(tempfile.mkdtemp(prefix="spritepal_cache_"))
                self._temp_dirs.append(cache_dir)

        # Create mock settings manager that returns appropriate values
        from unittest.mock import MagicMock
        mock_settings = MagicMock()
        mock_settings.get_cache_enabled.return_value = True
        mock_settings.get_cache_location.return_value = str(cache_dir)

        cache = ROMCache(settings_manager=mock_settings, cache_dir=str(cache_dir))

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

        # Step 7: Registry cleanup (if we initialized it)
        # Clean up the registry if we were the ones who initialized it.
        # Note: With manage_registry=False (default), cleanup will still happen
        # if WE initialized the registry - this prevents pollution between tests.
        if self._initialized_registry:
            try:
                from core.managers.registry import ManagerRegistry
                registry = ManagerRegistry()
                if registry.is_initialized():
                    registry.cleanup_managers()
                    # Reset the singleton for full isolation
                    if hasattr(registry, 'reset_for_tests'):
                        registry.reset_for_tests()
                self._initialized_registry = False
            except Exception as e:
                warnings.warn(
                    f"Failed to clean up ManagerRegistry: {e}",
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

