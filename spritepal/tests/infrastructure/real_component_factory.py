"""
Real Component Factory for type-safe testing with actual components.

This module replaces MockFactory with a factory that creates real managers
and components, providing better integration testing and eliminating unsafe
type casting throughout the test suite.

MIGRATION GUIDE FROM MOCKFACTORY:
---------------------------------

OLD (MockFactory - deprecated):
    from tests.infrastructure.mock_factory import MockFactory
from typing import cast

    def test_extraction():
        # Creates mock with 15+ unsafe cast() operations
        manager = cast(ExtractionManager, MockFactory.create_extraction_manager())
        # Type checker can't verify this is safe
        result = manager.extract_sprites(params)

NEW (RealComponentFactory - recommended):
    from tests.infrastructure.real_component_factory import RealComponentFactory

    def test_extraction(real_factory):  # Use fixture from conftest.py
        # Creates real manager, properly typed
        manager = real_factory.create_extraction_manager()
        # Type checker knows this is ExtractionManager
        result = manager.extract_sprites(params)

BENEFITS:
- No unsafe cast() operations needed
- Real components with actual behavior
- Type checker can verify all operations
- Better integration testing
- Consistent test data from DataRepository

AUTOMATED MIGRATION:
Run: python -m tests.infrastructure.migration_helpers report
to see migration progress and get assistance.
"""

from __future__ import annotations

import tempfile
import warnings
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar, Generic, TypeVar

from PySide6.QtCore import QObject, QThread
from PySide6.QtWidgets import QApplication, QWidget

from core.managers.base_manager import BaseManager
from core.managers.extraction_manager import ExtractionManager
from core.managers.injection_manager import InjectionManager
from core.managers.registry import ManagerRegistry
from core.managers.session_manager import SessionManager
from ui.common import WorkerManager
from ui.common.error_handler import ErrorHandler
from ui.main_window import MainWindow
from ui.rom_extraction_panel import ROMExtractionPanel

# Import widget classes for factory methods
try:
    from ui.row_arrangement_dialog import RowArrangementDialog
    from ui.zoomable_preview import PreviewPanel, ZoomablePreviewWidget
except ImportError:
    # Fallback for testing environments
    ZoomablePreviewWidget = QWidget
    PreviewPanel = QWidget
    RowArrangementDialog = QWidget
import contextlib

from utils.rom_cache import ROMCache

from .test_data_repository import DataRepository, get_test_data_repository

if TYPE_CHECKING:
    from core.rom_extractor import ROMExtractor
    from core.tile_renderer import TileRenderer
    from core.workers import (
        ROMExtractionWorker,
        ROMInjectionWorker,
        VRAMExtractionWorker,
        VRAMInjectionWorker,
    )

# Type variables for generic manager handling
M = TypeVar("M", bound=BaseManager)
W = TypeVar("W", bound=QThread)

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
        data_repository: DataRepository | None = None,
        settings_dir: Path | None = None,
        *,
        fail_on_leaks: bool | None = None,
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
        """
        self._data_repo = data_repository or get_test_data_repository()
        self._temp_dirs: list[Path] = []
        self._created_components: list[QObject] = []
        self._fail_on_leaks = fail_on_leaks if fail_on_leaks is not None else self.FAIL_ON_LEAKS
        self._leaked_resources: list[str] = []

        # Set up isolated settings directory
        if settings_dir is not None:
            self._settings_dir = settings_dir
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

        # Initialize managers to ensure DI container and protocols are registered
        # This is necessary because managers like ExtractionManager create ROMExtractor
        # which uses inject(ROMCacheProtocol) internally, and the DI factories depend
        # on consolidated managers being initialized
        from core.managers.registry import ManagerRegistry
        registry = ManagerRegistry()
        if not registry.is_initialized():
            from core.managers import initialize_managers
            initialize_managers("TestApp", settings_path=self._settings_path)

    def create_extraction_manager(self, with_test_data: bool = True) -> ExtractionManager:
        """
        Create a real ExtractionManager for testing.

        Args:
            with_test_data: Whether to inject test data paths

        Returns:
            Real ExtractionManager instance
        """
        manager = ExtractionManager()
        self._created_components.append(manager)

        if with_test_data:
            # Set up test data paths
            test_data = self._data_repo.get_vram_extraction_data("medium")

            # Inject test paths into manager's internal state if needed
            # The manager validates paths, so we use real test files
            manager._last_vram_path = test_data["vram_path"]
            manager._last_cgram_path = test_data["cgram_path"]

        return manager

    def create_injection_manager(self, with_test_data: bool = True) -> InjectionManager:
        """
        Create a real InjectionManager for testing.

        Args:
            with_test_data: Whether to inject test data paths

        Returns:
            Real InjectionManager instance
        """
        manager = InjectionManager()
        self._created_components.append(manager)

        if with_test_data:
            # Set up test data paths
            test_data = self._data_repo.get_injection_data("medium")

            # Inject test paths if manager supports it
            if hasattr(manager, "_last_sprite_path"):
                manager._last_sprite_path = test_data["sprite_path"]

        return manager

    def create_session_manager(self, app_name: str = "TestApp") -> SessionManager:
        """
        Create a real SessionManager for testing.

        Args:
            app_name: Application name for session management

        Returns:
            Real SessionManager instance
        """
        # Use temp directory for test sessions
        temp_dir = Path(tempfile.mkdtemp(prefix="spritepal_test_session_"))
        self._temp_dirs.append(temp_dir)

        manager = SessionManager(app_name)
        self._created_components.append(manager)

        # Override session directory to temp location
        if hasattr(manager, "_session_dir"):
            manager._session_dir = temp_dir

        return manager

    def create_manager_registry(self, populate: bool = True) -> ManagerRegistry:
        """
        Create a ManagerRegistry with real managers.

        Args:
            populate: Whether to populate with default managers

        Returns:
            ManagerRegistry instance with real managers

        Note:
            Uses isolated temp settings path to avoid polluting repo
            with .testapp_settings.json in the project root.
        """
        registry = ManagerRegistry()

        if populate:
            # Initialize real managers via registry with isolated settings
            registry.initialize_managers("TestApp", settings_path=self._settings_path)

        return registry

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

        # B.7: Create MainWindow with explicit DI dependencies (matching B.6 pattern)
        from core.di_container import inject
        from core.protocols.manager_protocols import (
            ROMCacheProtocol,
            SessionManagerProtocol,
            SettingsManagerProtocol,
        )

        window = MainWindow(
            settings_manager=inject(SettingsManagerProtocol),
            rom_cache=inject(ROMCacheProtocol),
            session_manager=inject(SessionManagerProtocol),  # type: ignore[arg-type]  # Protocol vs concrete type mismatch
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

    def create_rom_extraction_panel(self, parent: QWidget | None = None) -> ROMExtractionPanel:
        """
        Create a real ROMExtractionPanel for testing.

        Args:
            parent: Optional parent widget

        Returns:
            Real ROMExtractionPanel instance
        """
        from core.di_container import inject
        from core.protocols.manager_protocols import ExtractionManagerProtocol

        panel = ROMExtractionPanel(
            parent,
            extraction_manager=inject(ExtractionManagerProtocol),
        )
        self._created_components.append(panel)

        # Set up with test ROM data
        test_data = self._data_repo.get_rom_extraction_data("medium")

        if hasattr(panel, "rom_path_edit") and panel.rom_path_edit:
            panel.rom_path_edit.setText(test_data["rom_path"])

        return panel

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

    def create_injection_worker(self, params: dict[str, Any] | None = None, worker_type: str = "vram") -> VRAMInjectionWorker | ROMInjectionWorker:
        """
        Create a real injection worker for testing.

        Args:
            params: Optional injection parameters
            worker_type: Type of worker - "vram" or "rom"

        Returns:
            Real VRAMInjectionWorker or ROMInjectionWorker instance
        """
        from core.di_container import inject
        from core.protocols.manager_protocols import InjectionManagerProtocol
        from core.workers import ROMInjectionWorker, VRAMInjectionWorker

        if params is None:
            params = self._data_repo.get_injection_data("small")

        injection_manager = inject(InjectionManagerProtocol)

        if worker_type == "vram":
            worker = VRAMInjectionWorker(params, injection_manager=injection_manager)
        else:
            worker = ROMInjectionWorker(params, injection_manager=injection_manager)

        self._created_components.append(worker)

        return worker

    def create_typed_manager(self, manager_class: type[M], **kwargs: Any) -> M:
        """
        Create a typed manager instance with type safety.

        Args:
            manager_class: The manager class to instantiate
            **kwargs: Arguments to pass to manager constructor

        Returns:
            Typed manager instance
        """
        manager = manager_class(**kwargs)
        self._created_components.append(manager)
        return manager

    def create_typed_worker(self, worker_class: type[W], params: dict[str, Any] | None = None) -> W:
        """
        Create a typed worker instance with type safety.

        Args:
            worker_class: The worker class to instantiate
            params: Optional parameters for the worker

        Returns:
            Typed worker instance
        """
        if params is None:
            # Use appropriate test data based on worker type
            if "Extraction" in worker_class.__name__:
                params = self._data_repo.get_vram_extraction_data("small")
            elif "Injection" in worker_class.__name__:
                params = self._data_repo.get_injection_data("small")
            else:
                params = {}

        worker = worker_class(params)
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

    def create_error_handler(self, parent: QWidget | None = None) -> ErrorHandler:
        """
        Create a real error handler for testing.

        Args:
            parent: Optional parent widget

        Returns:
            Real ErrorHandler instance
        """
        handler = ErrorHandler(parent)
        self._created_components.append(handler)

        # Configure for testing (no modal dialogs)
        if hasattr(handler, "_show_dialogs"):
            handler._show_dialogs = False

        return handler

    def create_worker_manager(self) -> WorkerManager:
        """
        Create a real WorkerManager for testing.

        Returns:
            Real WorkerManager instance
        """
        return WorkerManager()

    def create_zoomable_preview_widget(self) -> ZoomablePreviewWidget:
        """
        Create a real ZoomablePreviewWidget for testing.

        Returns:
            Real ZoomablePreviewWidget instance
        """
        from ui.zoomable_preview import ZoomablePreviewWidget

        widget = ZoomablePreviewWidget()
        self._created_components.append(widget)
        return widget

    def create_preview_panel(self) -> PreviewPanel:
        """
        Create a real PreviewPanel for testing.

        Returns:
            Real PreviewPanel instance
        """
        from ui.zoomable_preview import PreviewPanel

        panel = PreviewPanel()
        self._created_components.append(panel)
        return panel

    def create_row_arrangement_dialog(self, sprite_path: str, tiles_per_row: int = 16) -> RowArrangementDialog:
        """
        Create a real RowArrangementDialog for testing.

        Args:
            sprite_path: Path to the sprite file
            tiles_per_row: Number of tiles per row

        Returns:
            Real RowArrangementDialog instance
        """
        from ui.row_arrangement_dialog import RowArrangementDialog

        dialog = RowArrangementDialog(sprite_path, tiles_per_row)
        self._created_components.append(dialog)
        return dialog

    def create_test_widget(self, qtbot: Any, widget_class: type[QWidget] | None = None) -> QWidget:
        """
        Create a test widget for generic Qt component testing.

        Args:
            qtbot: pytest-qt's qtbot fixture for widget management
            widget_class: Optional specific widget class to create

        Returns:
            Real Qt widget instance managed by qtbot
        """
        if widget_class is None:
            widget_class = QWidget

        widget = widget_class()
        qtbot.addWidget(widget)
        self._created_components.append(widget)
        return widget

    def inject_test_data(self, component: Any, data_size: str = "medium") -> None:
        """
        Inject test data into a component.

        Args:
            component: Component to inject data into
            data_size: Size of test data to use
        """
        component_type = type(component).__name__

        if "Extraction" in component_type:
            test_data = self._data_repo.get_vram_extraction_data(data_size)
            self._inject_data(component, test_data)
        elif "Injection" in component_type:
            test_data = self._data_repo.get_injection_data(data_size)
            self._inject_data(component, test_data)
        elif "Rom" in component_type or "ROM" in component_type:
            test_data = self._data_repo.get_rom_extraction_data(data_size)
            self._inject_data(component, test_data)

    def _inject_data(self, component: Any, data: dict[str, Any]) -> None:
        """
        Helper to inject data into component attributes.

        Args:
            component: Component to inject into
            data: Data dictionary to inject
        """
        for key, value in data.items():
            # Try to set as attribute
            if hasattr(component, key):
                setattr(component, key, value)
            # Try to set with underscore prefix
            elif hasattr(component, f"_{key}"):
                setattr(component, f"_{key}", value)
            # Try to find a setter method
            elif hasattr(component, f"set_{key}"):
                getattr(component, f"set_{key}")(value)

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
        # This ensures all QThread cleanup and signal disconnections are processed
        try:
            if QApplication.instance():
                for _ in range(10):
                    QApplication.processEvents()
        except Exception as e:
            warnings.warn(
                f"Failed to process Qt events during cleanup: {e}",
                ResourceWarning,
                stacklevel=2,
            )

        # Step 4: Force garbage collection to clean up deleted workers
        try:
            import gc
            gc.collect()
            gc.collect()  # Second pass to handle circular references
        except Exception as e:
            warnings.warn(
                f"Failed to force garbage collection: {e}",
                ResourceWarning,
                stacklevel=2,
            )

        # Step 5: Allow time for OS thread cleanup
        # Python's threading.active_count() may still see threads being destroyed
        try:
            import time
            time.sleep(0.15)  # sleep-ok: OS thread teardown after gc.collect()
        except Exception as e:
            warnings.warn(
                f"Failed to wait for thread cleanup: {e}",
                ResourceWarning,
                stacklevel=2,
            )

        # Step 6: Clean up temp directories
        import shutil
        for temp_dir in self._temp_dirs:
            if temp_dir.exists():
                with contextlib.suppress(Exception):
                    shutil.rmtree(temp_dir)

        self._temp_dirs.clear()

        # Step 7: Final leak reporting
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

class TypedManagerFactory(Generic[M]):
    """
    Generic factory for creating typed managers with compile-time type safety.

    This eliminates the need for unsafe cast() operations in tests.
    """

    def __init__(self, manager_class: type[M], factory: RealComponentFactory | None = None):
        """
        Initialize typed manager factory.

        Args:
            manager_class: The manager class to create instances of
            factory: Optional RealComponentFactory to use
        """
        self._manager_class = manager_class
        self._factory = factory or RealComponentFactory()

    def create(self, **kwargs: Any) -> M:
        """
        Create a typed manager instance.

        Args:
            **kwargs: Arguments for manager creation

        Returns:
            Typed manager instance
        """
        return self._factory.create_typed_manager(self._manager_class, **kwargs)

    def create_with_test_data(self, data_size: str = "medium") -> M:
        """
        Create a manager with test data injected.

        Args:
            data_size: Size of test data to inject

        Returns:
            Typed manager with test data
        """
        manager = self.create()
        self._factory.inject_test_data(manager, data_size)
        return manager

class TypedWorkerFactory(Generic[W]):
    """
    Generic factory for creating typed workers with compile-time type safety.
    """

    def __init__(self, worker_class: type[W], factory: RealComponentFactory | None = None):
        """
        Initialize typed worker factory.

        Args:
            worker_class: The worker class to create instances of
            factory: Optional RealComponentFactory to use
        """
        self._worker_class = worker_class
        self._factory = factory or RealComponentFactory()

    def create(self, params: dict[str, Any] | None = None) -> W:
        """
        Create a typed worker instance.

        Args:
            params: Optional parameters for the worker

        Returns:
            Typed worker instance
        """
        return self._factory.create_typed_worker(self._worker_class, params)

    def create_with_test_data(self, data_size: str = "small") -> W:
        """
        Create a worker with test data parameters.

        Args:
            data_size: Size of test data to use

        Returns:
            Typed worker with test parameters
        """
        # Determine appropriate test data based on worker type
        if "Extraction" in self._worker_class.__name__:
            params = self._factory._data_repo.get_vram_extraction_data(data_size)
        elif "Injection" in self._worker_class.__name__:
            params = self._factory._data_repo.get_injection_data(data_size)
        else:
            params = {}

        return self.create(params)

# Convenience functions for common manager types
def create_extraction_manager_factory() -> TypedManagerFactory[ExtractionManager]:
    """Create a typed factory for ExtractionManager."""
    return TypedManagerFactory(ExtractionManager)

def create_injection_manager_factory() -> TypedManagerFactory[InjectionManager]:
    """Create a typed factory for InjectionManager."""
    return TypedManagerFactory(InjectionManager)

def create_session_manager_factory() -> TypedManagerFactory[SessionManager]:
    """Create a typed factory for SessionManager."""
    return TypedManagerFactory(SessionManager)
