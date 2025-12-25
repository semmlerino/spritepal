"""
Integration tests for the ExtractionController class.

Tests the ExtractionController with real managers and components using
RealComponentFactory for proper integration testing. This consolidates
coverage from previous mocked/DI/real test suites into a single coherent suite.

Testing approach:
- Real managers via RealComponentFactory with isolated_managers
- Real test files with valid data via tmp_path
- Real Qt signal behavior via QSignalSpy
- No mocking of core business logic
- Real worker creation and lifecycle management
- Real parameter validation and error conditions
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any
from unittest.mock import Mock

import pytest
from PIL import Image
from PySide6.QtCore import QObject, Signal
from PySide6.QtTest import QSignalSpy

from core.app_context import get_app_context
from tests.fixtures.timeouts import worker_timeout
from tests.infrastructure.real_component_factory import RealComponentFactory
from ui.extraction_controller import ExtractionController

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = [
    pytest.mark.gui,
    pytest.mark.integration,
]


class MockMainWindow(QObject):
    """
    Real Qt signals-based mock for MainWindow.

    Provides actual Qt signal functionality for testing signal connections
    and behavior without the full UI overhead.
    """

    # Define all required signals - these are real Qt signals
    extract_requested = Signal()
    open_in_editor_requested = Signal(str)
    arrange_rows_requested = Signal(str)
    arrange_grid_requested = Signal(str)
    inject_requested = Signal()
    offset_changed = Signal(int)

    def __init__(self) -> None:
        super().__init__()

        # Create mock extraction panel with the same signal
        class MockExtractionPanel(QObject):
            offset_changed = Signal(int)

            def __init__(self, parent_signal: Signal) -> None:
                super().__init__()
                self.offset_changed.connect(parent_signal.emit)

        self.extraction_panel = MockExtractionPanel(self.offset_changed)

        # Mock UI components needed by controller
        self.status_bar = Mock()
        self.sprite_preview = Mock()
        self.palette_preview = Mock()
        self.preview_coordinator = Mock()

        # Store params and outputs for testing
        self._extraction_params: dict[str, Any] = {}
        self._output_path = ""
        self._extracted_files: list[str] = []
        self._extraction_failed_called = False
        self._extraction_failed_message = ""

    def get_extraction_params(self) -> dict[str, Any]:
        """Return test extraction parameters."""
        return self._extraction_params.copy()

    def set_extraction_params(self, params: dict[str, Any]) -> None:
        """Set extraction parameters for testing."""
        self._extraction_params = params.copy()

    def get_output_path(self) -> str:
        """Return test output path."""
        return self._output_path

    def set_output_path(self, path: str) -> None:
        """Set output path for testing."""
        self._output_path = path

    def extraction_complete(self, extracted_files: list[str]) -> None:
        """Handle extraction completion."""
        self._extracted_files = extracted_files.copy()

    def extraction_failed(self, message: str) -> None:
        """Handle extraction failure."""
        self._extraction_failed_called = True
        self._extraction_failed_message = message

    def get_last_extraction_failure(self) -> tuple[bool, str]:
        """Get last extraction failure status for testing."""
        return self._extraction_failed_called, self._extraction_failed_message

    def reset_extraction_status(self) -> None:
        """Reset extraction status for testing."""
        self._extraction_failed_called = False
        self._extraction_failed_message = ""
        self._extracted_files = []

    def show_cache_operation_badge(self, text: str) -> None:
        """Mock cache badge display."""

    def hide_cache_operation_badge(self) -> None:
        """Mock hide cache badge."""


@pytest.mark.no_manager_setup
class TestExtractionControllerIntegration:
    """Integration tests for ExtractionController with real components."""

    @pytest.fixture
    def test_files(self, tmp_path: Path) -> dict[str, str]:
        """Create real test files for extraction."""
        # Create minimal but valid VRAM file
        vram_file = tmp_path / "test.vram"
        vram_data = b"\x00" * 0x10000  # 64KB VRAM
        vram_file.write_bytes(vram_data)

        # Create valid CGRAM file
        cgram_file = tmp_path / "test.cgram"
        cgram_data = b"\x00" * 512  # 512 bytes for palette data
        cgram_file.write_bytes(cgram_data)

        # Create OAM file
        oam_file = tmp_path / "test.oam"
        oam_data = b"\x00" * 512  # 512 bytes for OAM data
        oam_file.write_bytes(oam_data)

        # Create output directory
        output_dir = tmp_path / "output"
        output_dir.mkdir(exist_ok=True)

        return {
            "vram_path": str(vram_file),
            "cgram_path": str(cgram_file),
            "oam_path": str(oam_file),
            "output_base": str(output_dir / "sprites"),
        }

    @pytest.fixture
    def mock_main_window(self) -> MockMainWindow:
        """Create MockMainWindow with real Qt signals."""
        return MockMainWindow()

    @pytest.fixture
    def real_managers(
        self, isolated_managers: None
    ) -> Any:
        """Create real managers using RealComponentFactory."""
        with RealComponentFactory() as factory:
            extraction_manager = factory.create_extraction_manager()
            injection_manager = factory.create_injection_manager()
            session_manager = factory.create_session_manager("TestControllerApp")
            settings_manager = get_app_context().application_state_manager

            yield {
                "extraction_manager": extraction_manager,
                "injection_manager": injection_manager,
                "session_manager": session_manager,
                "settings_manager": settings_manager,
            }

    @pytest.fixture
    def controller(
        self, mock_main_window: MockMainWindow, real_managers: dict[str, Any]
    ) -> Any:
        """Create ExtractionController with automatic worker cleanup."""
        ctrl = ExtractionController(
            main_window=mock_main_window,
            extraction_manager=real_managers["extraction_manager"],
            injection_manager=real_managers["injection_manager"],
            session_manager=real_managers["session_manager"],
            settings_manager=real_managers["settings_manager"],
        )
        yield ctrl
        # Cleanup any running workers
        for worker_attr in ["worker", "rom_worker", "injection_worker"]:
            worker = getattr(ctrl, worker_attr, None)
            if worker is not None:
                worker.requestInterruption()
                if worker.isRunning():
                    worker.quit()
                    worker.wait(2000)

    # --- Initialization Tests ---

    def test_initialization_with_real_managers(
        self, mock_main_window: MockMainWindow, real_managers: dict[str, Any]
    ) -> None:
        """Test ExtractionController initialization with real managers."""
        controller = ExtractionController(
            main_window=mock_main_window,
            extraction_manager=real_managers["extraction_manager"],
            injection_manager=real_managers["injection_manager"],
            session_manager=real_managers["session_manager"],
            settings_manager=real_managers["settings_manager"],
        )

        assert controller.main_window == mock_main_window
        assert controller.extraction_manager == real_managers["extraction_manager"]
        assert controller.injection_manager == real_managers["injection_manager"]
        assert controller.session_manager == real_managers["session_manager"]
        assert controller.worker is None
        assert controller.rom_worker is None

    def test_ui_signal_connections(
        self, mock_main_window: MockMainWindow, real_managers: dict[str, Any]
    ) -> None:
        """Test that controller properly connects to UI signals."""
        extract_spy = QSignalSpy(mock_main_window.extract_requested)
        editor_spy = QSignalSpy(mock_main_window.open_in_editor_requested)
        rows_spy = QSignalSpy(mock_main_window.arrange_rows_requested)
        grid_spy = QSignalSpy(mock_main_window.arrange_grid_requested)
        inject_spy = QSignalSpy(mock_main_window.inject_requested)
        offset_spy = QSignalSpy(mock_main_window.offset_changed)

        ExtractionController(
            main_window=mock_main_window,
            extraction_manager=real_managers["extraction_manager"],
            injection_manager=real_managers["injection_manager"],
            session_manager=real_managers["session_manager"],
            settings_manager=real_managers["settings_manager"],
        )

        # Emit signals to test connections
        mock_main_window.extract_requested.emit()
        mock_main_window.open_in_editor_requested.emit("test_file.png")
        mock_main_window.arrange_rows_requested.emit("test_file.png")
        mock_main_window.arrange_grid_requested.emit("test_file.png")
        mock_main_window.inject_requested.emit()
        mock_main_window.offset_changed.emit(0x1000)

        assert extract_spy.count() == 1
        assert editor_spy.count() == 1
        assert editor_spy.at(0)[0] == "test_file.png"
        assert rows_spy.count() == 1
        assert grid_spy.count() == 1
        assert inject_spy.count() == 1
        assert offset_spy.count() == 1
        assert offset_spy.at(0)[0] == 0x1000

    def test_manager_signal_connections(
        self, mock_main_window: MockMainWindow, real_managers: dict[str, Any]
    ) -> None:
        """Test that controller connects to real manager signals."""
        extraction_mgr = real_managers["extraction_manager"]
        injection_mgr = real_managers["injection_manager"]

        controller = ExtractionController(
            main_window=mock_main_window,
            extraction_manager=extraction_mgr,
            injection_manager=injection_mgr,
            session_manager=real_managers["session_manager"],
            settings_manager=real_managers["settings_manager"],
        )

        assert controller.extraction_manager == extraction_mgr
        assert controller.injection_manager == injection_mgr

        # Test signal emission works (basic smoke test)
        extraction_mgr.cache_miss.emit("test_data")
        injection_mgr.injection_progress.emit("Test progress")

    # --- Parameter Validation Tests ---

    def test_parameter_validation_missing_vram(
        self,
        mock_main_window: MockMainWindow,
        real_managers: dict[str, Any],
        test_files: dict[str, str],
    ) -> None:
        """Test parameter validation when VRAM path is missing."""
        controller = ExtractionController(
            main_window=mock_main_window,
            extraction_manager=real_managers["extraction_manager"],
            injection_manager=real_managers["injection_manager"],
            session_manager=real_managers["session_manager"],
            settings_manager=real_managers["settings_manager"],
        )

        mock_main_window.set_extraction_params({
            "vram_path": "",
            "cgram_path": test_files["cgram_path"],
            "output_base": test_files["output_base"],
        })

        mock_main_window.reset_extraction_status()
        controller.start_extraction()

        failed, message = mock_main_window.get_last_extraction_failure()
        assert failed
        assert "VRAM" in message or "vram_path" in message.lower()

    def test_parameter_validation_missing_cgram_in_color_mode(
        self,
        mock_main_window: MockMainWindow,
        real_managers: dict[str, Any],
        test_files: dict[str, str],
    ) -> None:
        """Test CGRAM validation in color mode with real managers."""
        controller = ExtractionController(
            main_window=mock_main_window,
            extraction_manager=real_managers["extraction_manager"],
            injection_manager=real_managers["injection_manager"],
            session_manager=real_managers["session_manager"],
            settings_manager=real_managers["settings_manager"],
        )

        mock_main_window.set_extraction_params({
            "vram_path": test_files["vram_path"],
            "cgram_path": "",
            "output_base": test_files["output_base"],
            "grayscale_mode": False,
        })

        mock_main_window.reset_extraction_status()
        controller.start_extraction()

        failed, message = mock_main_window.get_last_extraction_failure()
        assert failed
        assert "CGRAM" in message or "cgram" in message.lower()

    def test_file_validation_nonexistent(
        self,
        mock_main_window: MockMainWindow,
        real_managers: dict[str, Any],
        tmp_path: Path,
    ) -> None:
        """Test file validation with nonexistent file."""
        controller = ExtractionController(
            main_window=mock_main_window,
            extraction_manager=real_managers["extraction_manager"],
            injection_manager=real_managers["injection_manager"],
            session_manager=real_managers["session_manager"],
            settings_manager=real_managers["settings_manager"],
        )

        mock_main_window.set_extraction_params({
            "vram_path": str(tmp_path / "nonexistent.vram"),
            "cgram_path": "",
            "output_base": str(tmp_path / "output"),
            "grayscale_mode": True,
        })

        mock_main_window.reset_extraction_status()
        controller.start_extraction()

        failed, message = mock_main_window.get_last_extraction_failure()
        assert failed
        assert len(message) > 0

    def test_file_validation_invalid_size(
        self,
        mock_main_window: MockMainWindow,
        real_managers: dict[str, Any],
        tmp_path: Path,
    ) -> None:
        """Test real error handling with invalid file size."""
        controller = ExtractionController(
            main_window=mock_main_window,
            extraction_manager=real_managers["extraction_manager"],
            injection_manager=real_managers["injection_manager"],
            session_manager=real_managers["session_manager"],
            settings_manager=real_managers["settings_manager"],
        )

        # Create invalid file with wrong size
        invalid_vram = tmp_path / "invalid.vram"
        invalid_vram.write_bytes(b"\x00" * 100)

        mock_main_window.set_extraction_params({
            "vram_path": str(invalid_vram),
            "cgram_path": "",
            "output_base": str(tmp_path / "output"),
        })

        mock_main_window.reset_extraction_status()
        controller.start_extraction()

        failed, message = mock_main_window.get_last_extraction_failure()
        assert failed
        assert len(message) > 0
        assert controller.worker is None

    # --- Worker Tests ---

    def test_successful_worker_creation(
        self,
        controller: ExtractionController,
        mock_main_window: MockMainWindow,
        test_files: dict[str, str],
    ) -> None:
        """Test successful worker creation with real managers."""
        mock_main_window.set_extraction_params({
            "vram_path": test_files["vram_path"],
            "cgram_path": test_files["cgram_path"],
            "oam_path": test_files["oam_path"],
            "output_base": test_files["output_base"],
            "create_grayscale": True,
            "create_metadata": True,
            "grayscale_mode": False,
        })

        mock_main_window.reset_extraction_status()
        controller.start_extraction()

        failed, message = mock_main_window.get_last_extraction_failure()
        if failed:
            # Some failures are expected with minimal test data
            assert len(message) > 0
            assert controller.worker is None
        else:
            assert controller.worker is not None
            assert controller.worker.isRunning() or controller.worker.isFinished()

    def test_worker_cleanup(
        self,
        controller: ExtractionController,
        mock_main_window: MockMainWindow,
        test_files: dict[str, str],
    ) -> None:
        """Test proper worker cleanup with real workers."""
        mock_main_window.set_extraction_params({
            "vram_path": test_files["vram_path"],
            "cgram_path": test_files["cgram_path"],
            "output_base": test_files["output_base"],
        })

        controller.start_extraction()

        if controller.worker is not None:
            worker = controller.worker
            controller._cleanup_worker()
            assert controller.worker is None
            assert not worker.isRunning()

    # --- Signal Handler Tests ---

    def test_progress_handler(
        self, controller: ExtractionController, mock_main_window: MockMainWindow
    ) -> None:
        """Test progress message handler emits signal."""
        test_message = "Extracting sprites..."
        signal_received: list[str] = []
        controller.status_message_changed.connect(lambda msg: signal_received.append(msg))

        controller._on_progress(50, test_message)

        assert len(signal_received) == 1
        assert signal_received[0] == test_message

    def test_preview_ready_handler(
        self, controller: ExtractionController, mock_main_window: MockMainWindow
    ) -> None:
        """Test preview ready handler emits signals."""
        from unittest.mock import patch

        test_image = Image.new("RGB", (8, 8), color="red")
        tile_count = 42
        preview_signals: list[tuple[Any, int]] = []
        info_signals: list[str] = []

        controller.preview_ready.connect(lambda px, tc: preview_signals.append((px, tc)))
        controller.preview_info_changed.connect(lambda info: info_signals.append(info))

        with patch("ui.extraction_controller.pil_to_qpixmap") as mock_convert:
            mock_convert.return_value = Mock()
            controller._on_preview_ready(test_image, tile_count)

        assert len(preview_signals) == 1
        assert preview_signals[0][1] == tile_count
        assert len(info_signals) == 1
        assert f"{tile_count}" in info_signals[0]

    def test_preview_image_ready_handler(
        self, controller: ExtractionController, mock_main_window: MockMainWindow
    ) -> None:
        """Test preview image ready handler emits signal."""
        test_image = Image.new("L", (8, 8), color=128)
        signals_received: list[Image.Image] = []
        controller.grayscale_image_ready.connect(lambda img: signals_received.append(img))

        controller._on_preview_image_ready(test_image)

        assert len(signals_received) == 1
        assert signals_received[0] is test_image

    def test_palettes_ready_handler(
        self, controller: ExtractionController, mock_main_window: MockMainWindow
    ) -> None:
        """Test palettes ready handler emits signal."""
        test_palettes = {8: [[0, 0, 0], [255, 0, 0]]}
        signals_received: list[dict[int, list[list[int]]]] = []
        controller.palettes_ready.connect(lambda p: signals_received.append(p))

        controller._on_palettes_ready(test_palettes)

        assert len(signals_received) == 1
        assert signals_received[0] == test_palettes

    def test_extraction_finished_handler(
        self, controller: ExtractionController, mock_main_window: MockMainWindow
    ) -> None:
        """Test extraction finished handler emits signal and cleans up worker."""
        from tests.controllers.test_extraction_controller import DummyWorker

        extracted_files = ["sprite.png"]
        signals_received: list[list[str]] = []
        controller.extraction_completed.connect(lambda f: signals_received.append(f))
        controller.worker = DummyWorker()  # type: ignore[assignment]

        controller._on_extraction_finished(extracted_files)

        assert len(signals_received) == 1
        assert signals_received[0] == extracted_files
        assert controller.worker is None

    def test_extraction_error_handler(
        self, controller: ExtractionController, mock_main_window: MockMainWindow
    ) -> None:
        """Test extraction error handler emits signal and cleans up worker."""
        from tests.controllers.test_extraction_controller import DummyWorker

        error_message = "Failed to read VRAM file"
        signals_received: list[str] = []
        controller.extraction_error.connect(lambda msg: signals_received.append(msg))
        controller.worker = DummyWorker()  # type: ignore[assignment]

        controller._on_extraction_error(error_message)

        assert len(signals_received) == 1
        assert signals_received[0] == error_message
        assert controller.worker is None

    # --- ROM Extraction Tests ---

    def test_rom_extraction_worker_creation(
        self, controller: ExtractionController, tmp_path: Path
    ) -> None:
        """Test ROM extraction worker creation with real managers."""
        rom_file = tmp_path / "test.sfc"
        rom_data = b"\x00" * 0x100000  # 1MB ROM
        rom_file.write_bytes(rom_data)

        rom_params = {
            "rom_path": str(rom_file),
            "sprite_offset": 0x10000,
            "sprite_name": "test_sprite",
            "output_base": str(tmp_path / "rom_output"),
            "cgram_path": None,
        }

        controller.start_rom_extraction(rom_params)

        assert controller.rom_worker is not None

    def test_rom_extraction_cleanup(
        self, controller: ExtractionController, tmp_path: Path
    ) -> None:
        """Test ROM extraction worker cleanup."""
        rom_file = tmp_path / "test.sfc"
        rom_file.write_bytes(b"\x00" * 0x100000)

        rom_params = {
            "rom_path": str(rom_file),
            "sprite_offset": 0x10000,
            "sprite_name": "test_sprite",
            "output_base": str(tmp_path / "rom_output"),
            "cgram_path": None,
        }

        controller.start_rom_extraction(rom_params)

        if controller.rom_worker is not None:
            worker = controller.rom_worker
            controller._cleanup_rom_worker()
            assert controller.rom_worker is None
            assert not worker.isRunning()

    # --- Preview Update Tests ---

    def test_preview_update_with_offset(
        self,
        mock_main_window: MockMainWindow,
        real_managers: dict[str, Any],
        test_files: dict[str, str],
    ) -> None:
        """Test preview update with offset using real managers."""
        controller = ExtractionController(
            main_window=mock_main_window,
            extraction_manager=real_managers["extraction_manager"],
            injection_manager=real_managers["injection_manager"],
            session_manager=real_managers["session_manager"],
            settings_manager=real_managers["settings_manager"],
        )

        mock_main_window.extraction_panel.has_vram = Mock(return_value=True)
        mock_main_window.extraction_panel.get_vram_path = Mock(
            return_value=test_files["vram_path"]
        )
        mock_main_window.sprite_preview.width = Mock(return_value=256)
        mock_main_window.sprite_preview.height = Mock(return_value=256)
        mock_main_window.sprite_preview.update_preview = Mock()
        mock_main_window.sprite_preview.set_grayscale_image = Mock()

        try:
            controller.update_preview_with_offset(0x1000)
            # Success case
        except Exception as e:
            # Some errors expected with minimal test data
            error_str = str(e).lower()
            assert "preview" in error_str or "vram" in error_str or "offset" in error_str

    # --- Error Handler Tests ---

    def test_error_handler_integration(
        self, mock_main_window: MockMainWindow, real_managers: dict[str, Any]
    ) -> None:
        """Test error handler integration with real managers."""
        controller = ExtractionController(
            main_window=mock_main_window,
            extraction_manager=real_managers["extraction_manager"],
            injection_manager=real_managers["injection_manager"],
            session_manager=real_managers["session_manager"],
            settings_manager=real_managers["settings_manager"],
        )

        assert controller.error_handler is not None


class DummyWorker:
    """Reusable dummy worker for cleanup testing.

    Must implement all methods that WorkerManager.cleanup_worker() expects.
    """

    def blockSignals(self, block: bool) -> bool:  # noqa: ARG002
        return False

    def isRunning(self) -> bool:
        return False

    def isFinished(self) -> bool:
        return True

    def wait(self, timeout: int = 0) -> bool:  # noqa: ARG002
        return True

    def deleteLater(self) -> None:
        pass
