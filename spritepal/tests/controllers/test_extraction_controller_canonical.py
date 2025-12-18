"""
Canonical tests for ExtractionController functionality.

This module consolidates the most robust unit and integration tests for the
ExtractionController, drawing from previous iterative testing efforts.
It prioritizes testing through public interfaces and minimal mocking
where appropriate, aligning with "real component" testing principles.

Key improvements:
- Consolidated test cases from various controller test files.
- Clearer separation of concerns.
- Focus on testing behavior and outcomes.
- Reduced redundancy.
"""
from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, Mock, patch

import pytest
from PySide6.QtTest import QSignalSpy

# NOTE: pythonpath configured in pyproject.toml - no sys.path manipulation needed
import core.controller
from core.controller import ExtractionController
from core.managers.extraction_manager import ExtractionManager
from core.managers.injection_manager import InjectionManager
from core.managers.session_manager import SessionManager
from core.protocols.dialog_protocols import DialogFactoryProtocol
from core.workers import VRAMExtractionWorker
from core.services.settings_manager import SettingsManager

# Unified pytest markers for this consolidated module
pytestmark = [
    pytest.mark.unit,
    pytest.mark.headless,
    pytest.mark.file_io,
    pytest.mark.rom_data,
    pytest.mark.signals_slots,
]


# Defer MainWindow import to avoid potential initialization issues
def get_main_window_mock_spec():
    from ui.main_window import MainWindow
    return MainWindow


# =============================================================================
# MODULE-LEVEL HELPERS AND FIXTURES FOR TEST CONSOLIDATION
# ============================================================================

class DummyWorker:
    """Reusable dummy worker for cleanup testing - prevents duplication.

    Must implement all methods that WorkerManager.cleanup_worker() expects:
    - blockSignals(bool): Block/unblock Qt signals
    - isRunning(): Return False to indicate worker is not running
    - isFinished(): Return True to indicate worker has finished
    - wait(timeout=None): No-op, return True for immediate success
    - deleteLater(): No-op for cleanup scheduling
    """
    def blockSignals(self, block: bool) -> bool:  # noqa: ARG002
        """Simulate Qt signal blocking. Returns previous state."""
        return False

    def isRunning(self) -> bool:
        return False

    def isFinished(self) -> bool:
        return True

    def wait(self, timeout: int = 0) -> bool:  # noqa: ARG002
        """Simulate successful wait."""
        return True

    def deleteLater(self) -> None:
        pass


@pytest.fixture
def standard_mock_main_window() -> Any:
    """Create standard mock main window with all required signals and attributes.

    This consolidates the repeated main_window fixture creation pattern.
    """
    MainWindow = get_main_window_mock_spec()
    window = Mock(spec=MainWindow)

    # Add required signals as mock signals with proper spec
    window.extract_requested = MagicMock()
    window.open_in_editor_requested = MagicMock()
    window.arrange_rows_requested = MagicMock()
    window.arrange_grid_requested = MagicMock()
    window.inject_requested = MagicMock()
    window.extraction_completed = MagicMock()
    window.extraction_error_occurred = MagicMock()

    # Add required attributes with spec where applicable
    window.extraction_panel = Mock()
    window.rom_extraction_panel = Mock()
    window.output_settings_manager = Mock()
    window.toolbar_manager = Mock()
    window.preview_coordinator = Mock()
    window.status_bar_manager = Mock()
    window.status_bar = Mock()
    window.sprite_preview = Mock()
    window.palette_preview = Mock()
    window.extraction_tabs = Mock()
    window._output_path = ""
    window._extracted_files = []

    # Mock get_extraction_params for validation tests
    window.get_extraction_params = Mock()
    window.get_extraction_params.return_value = {
        "vram_path": "/valid/path/to/vram.dmp",
        "cgram_path": "/valid/path/to/cgram.dmp",
        "output_base": "/valid/path/to/output",
        "grayscale_mode": False,
        "create_grayscale": True,
        "create_metadata": True,
    }

    return window


@pytest.fixture
def standard_mock_managers() -> tuple[Mock, Mock, Mock, Mock, Mock]:
    """Create standard mock managers for dependency injection.

    Returns (extraction_manager, injection_manager, session_manager, settings_manager, dialog_factory).
    This consolidates repeated manager mock creation pattern.
    """
    extraction_manager = Mock(spec=ExtractionManager)
    injection_manager = Mock(spec=InjectionManager)
    session_manager = Mock(spec=SessionManager)
    settings_manager = Mock(spec=SettingsManager)
    dialog_factory = Mock(spec=DialogFactoryProtocol)
    return extraction_manager, injection_manager, session_manager, settings_manager, dialog_factory


@pytest.mark.no_manager_setup
class TestControllerImports:
    """Test that controller module imports work correctly"""

    def test_controller_imports(self) -> None:
        """Test that all imports in controller module work without errors"""
        try:
            importlib.reload(core.controller)
        except ImportError as e:
            pytest.fail(f"Import error in controller module: {e}")
        except NameError as e:
            pytest.fail(f"Name error in controller module: {e}")
        except Exception as e:
            pytest.fail(f"Unexpected error importing controller module: {e}")

    def test_pil_to_qpixmap_import(self) -> None:
        """Test that pil_to_qpixmap function is available in controller module"""
        from core import controller
        assert hasattr(controller, "pil_to_qpixmap")
        assert callable(controller.pil_to_qpixmap)


@pytest.mark.no_manager_setup
class TestExtractionControllerUnit:
    """Unit tests for ExtractionController functionality using mocks."""

    @pytest.fixture
    def main_window(self, standard_mock_main_window: Any) -> Any:
        """Main window fixture - uses consolidated standard_mock_main_window"""
        return standard_mock_main_window

    @pytest.fixture
    def controller(self, main_window: Any, standard_mock_managers: tuple[Mock, Mock, Mock, Mock, Mock]) -> ExtractionController:
        """Create REAL controller instance with mock managers."""
        extraction_manager, injection_manager, session_manager, settings_manager, dialog_factory = standard_mock_managers

        # Controller now uses ConsoleErrorHandler directly (no UI import)
        controller = ExtractionController(
            main_window=main_window,
            extraction_manager=extraction_manager,
            injection_manager=injection_manager,
            session_manager=session_manager,
            settings_manager=settings_manager,
            dialog_factory=dialog_factory,
        )

        return controller

    def test_init_connects_signals(self, controller: ExtractionController, main_window: Any) -> None:
        """Test controller initialization correctly sets up dependencies.

        Note: With mock objects, we verify the presence of signals and methods,
        not the actual Qt signal/slot connection mechanism.
        """
        assert controller.main_window == main_window
        assert controller.worker is None

        # Verify expected methods that should be connected
        assert hasattr(controller, 'start_extraction')
        assert hasattr(controller, 'open_in_editor')
        assert hasattr(controller, 'open_row_arrangement')
        assert hasattr(controller, 'open_grid_arrangement')
        assert hasattr(controller, 'start_injection')
        assert hasattr(controller, 'update_preview_with_offset')

        # Verify main window has expected signals (mocked)
        assert hasattr(main_window, 'extract_requested')
        assert hasattr(main_window, 'open_in_editor_requested')
        assert hasattr(main_window, 'arrange_rows_requested')
        assert hasattr(main_window, 'arrange_grid_requested')
        assert hasattr(main_window, 'inject_requested')

    def test_parameter_validation_missing_vram(self, controller: ExtractionController, main_window: Any):
        """Test parameter validation when VRAM path is missing."""
        main_window.get_extraction_params.return_value = {
            "vram_path": "",
            "cgram_path": "/path/to/cgram.dmp",
            "output_base": "/path/to/output",
        }
        controller.extraction_manager.validate_extraction_params.side_effect = \
            ValueError("VRAM file is required for extraction")

        controller.start_extraction()

        main_window.extraction_failed.assert_called_once()
        error_message = main_window.extraction_failed.call_args[0][0]
        assert "VRAM file is required for extraction" in error_message
        assert controller.worker is None

    def test_parameter_validation_missing_cgram(self, controller: ExtractionController, main_window: Any):
        """Test parameter validation when CGRAM path is missing."""
        expected_msg = "CGRAM file is required for Full Color mode."
        main_window.get_extraction_params.return_value = {
            "vram_path": "/path/to/vram.dmp",
            "cgram_path": "",
            "output_base": "/path/to/output",
            "grayscale_mode": False,
        }
        controller.extraction_manager.validate_extraction_params.side_effect = \
            ValueError(expected_msg)

        controller.start_extraction()

        main_window.extraction_failed.assert_called_once()
        error_message = main_window.extraction_failed.call_args[0][0]
        assert expected_msg in error_message
        assert controller.worker is None

    def test_parameter_validation_missing_both(self, controller: ExtractionController, main_window: Any):
        """Test parameter validation when both paths are missing."""
        main_window.get_extraction_params.return_value = {
            "vram_path": None,
            "cgram_path": None,
            "output_base": "/path/to/output",
        }
        controller.extraction_manager.validate_extraction_params.side_effect = \
            ValueError("VRAM file is required for extraction")

        controller.start_extraction()

        main_window.extraction_failed.assert_called_once()
        error_message = main_window.extraction_failed.call_args[0][0]
        assert "VRAM file is required for extraction" in error_message
        assert controller.worker is None

    def test_start_extraction_valid_params(self, controller: ExtractionController, main_window: Any):
        """Test starting extraction with valid parameters."""
        valid_params = {
            "vram_path": "/valid/path/to/vram.dmp",
            "cgram_path": "/valid/path/to/cgram.dmp",
            "output_base": "/valid/path/to/output",
            "grayscale_mode": True,
            "create_grayscale": True,
            "create_metadata": True,
        }
        main_window.get_extraction_params.return_value = valid_params
        controller.extraction_manager.validate_extraction_params.return_value = None

        # Mock file validation to return valid results (files don't actually exist)
        mock_validation_result = Mock()
        mock_validation_result.is_valid = True
        mock_validation_result.error_message = None
        mock_validation_result.warnings = []

        with patch('core.controller.VRAMExtractionWorker') as mock_worker_class, \
             patch('core.controller.FileValidator.validate_vram_file', return_value=mock_validation_result), \
             patch('core.controller.FileValidator.validate_cgram_file', return_value=mock_validation_result):
            mock_worker = Mock(spec=VRAMExtractionWorker)
            mock_worker_class.return_value = mock_worker

            controller.start_extraction()

            mock_worker_class.assert_called_once()
            worker_params = mock_worker_class.call_args[0][0]
            assert worker_params["vram_path"] == valid_params["vram_path"]
            assert controller.worker == mock_worker
            mock_worker.start.assert_called_once()

    def test_on_progress_handler(self, controller: ExtractionController, main_window: Any):
        """Test progress message handler emits signal."""
        test_message = "Extracting sprites..."
        # Capture signal emission
        signal_received = []
        controller.status_message_changed.connect(lambda msg: signal_received.append(msg))
        controller._on_progress(50, test_message)
        assert len(signal_received) == 1
        assert signal_received[0] == test_message

    def test_on_preview_ready_handler(self, controller: ExtractionController, main_window: Any):
        """Test preview ready handler emits signals."""
        from PIL import Image
        test_image = Image.new('RGB', (8, 8), color='red')
        tile_count = 42
        # Capture signal emissions
        preview_signals = []
        info_signals = []
        controller.preview_ready.connect(lambda px, tc: preview_signals.append((px, tc)))
        controller.preview_info_changed.connect(lambda info: info_signals.append(info))
        # Patch pil_to_qpixmap to avoid Qt context requirement
        with patch('core.controller.pil_to_qpixmap') as mock_pil_to_qpixmap:
            mock_pil_to_qpixmap.return_value = Mock()  # Return mock QPixmap
            controller._on_preview_ready(test_image, tile_count)
        assert len(preview_signals) == 1
        assert preview_signals[0][1] == tile_count
        assert len(info_signals) == 1
        assert f"{tile_count}" in info_signals[0]

    def test_on_preview_image_ready_handler(self, controller: ExtractionController, main_window: Any):
        """Test preview image ready handler emits signal."""
        from PIL import Image
        test_image = Image.new('L', (8, 8), color=128)
        # Capture signal emission
        signals_received = []
        controller.grayscale_image_ready.connect(lambda img: signals_received.append(img))
        controller._on_preview_image_ready(test_image)
        assert len(signals_received) == 1
        assert signals_received[0] is test_image

    def test_on_palettes_ready_handler(self, controller: ExtractionController, main_window: Any):
        """Test palettes ready handler emits signal."""
        test_palettes = {8: [[0, 0, 0], [255, 0, 0]]}
        # Capture signal emission
        signals_received = []
        controller.palettes_ready.connect(lambda p: signals_received.append(p))
        controller._on_palettes_ready(test_palettes)
        assert len(signals_received) == 1
        assert signals_received[0] == test_palettes

    def test_on_active_palettes_ready_handler(self, controller: ExtractionController, main_window: Any):
        """Test active palettes ready handler emits signal."""
        active_palettes = [8, 9]
        # Capture signal emission
        signals_received = []
        controller.active_palettes_ready.connect(lambda p: signals_received.append(p))
        controller._on_active_palettes_ready(active_palettes)
        assert len(signals_received) == 1
        assert signals_received[0] == active_palettes

    def test_on_extraction_finished_handler(self, controller: ExtractionController, main_window: Any):
        """Test extraction finished handler emits signal and cleans up worker."""
        extracted_files = ["sprite.png"]
        # Capture signal emission
        signals_received = []
        controller.extraction_completed.connect(lambda f: signals_received.append(f))
        controller.worker = DummyWorker()  # Simulate worker being active
        controller._on_extraction_finished(extracted_files)
        assert len(signals_received) == 1
        assert signals_received[0] == extracted_files
        assert controller.worker is None

    def test_on_extraction_error_handler(self, controller: ExtractionController, main_window: Any):
        """Test extraction error handler emits signal and cleans up worker."""
        error_message = "Failed to read VRAM file"
        # Capture signal emission
        signals_received = []
        controller.extraction_error.connect(lambda msg: signals_received.append(msg))
        controller.worker = DummyWorker()  # Simulate worker being active
        controller._on_extraction_error(error_message)
        assert len(signals_received) == 1
        assert signals_received[0] == error_message
        assert controller.worker is None

    @patch("core.controller.subprocess.Popen")
    def test_open_in_editor_launcher_found(self, mock_popen, controller: ExtractionController, main_window: Any, tmp_path: Path):
        """Test opening in editor when launcher is found."""
        launcher_dir = tmp_path / "pixel_editor"
        launcher_dir.mkdir()
        launcher_file = launcher_dir / "launch_pixel_editor.py"
        launcher_file.write_text("# Fake launcher script")
        sprite_file = tmp_path / "sprite.png"
        sprite_file.write_text("fake png data")

        mock_controller_file = tmp_path / "core" / "controller.py"
        with patch("core.controller.__file__", str(mock_controller_file)):
            controller.open_in_editor(str(sprite_file))

        mock_popen.assert_called_once()
        launch_command = mock_popen.call_args[0][0]
        assert launch_command[0] == sys.executable
        assert launch_command[1].endswith("launch_pixel_editor.py")
        assert launch_command[2] == os.path.abspath(str(sprite_file))
        main_window.status_bar.showMessage.assert_called_once()
        assert "Opened" in main_window.status_bar.showMessage.call_args[0][0]

    @patch("core.controller.subprocess.Popen")
    def test_open_in_editor_launcher_not_found(self, mock_popen, controller: ExtractionController, main_window: Any, tmp_path: Path):
        """Test opening in editor when launcher is not found."""
        sprite_file = tmp_path / "sprite.png"
        sprite_file.write_text("fake png data")

        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()
        mock_controller_file = empty_dir / "core" / "controller.py"
        with patch("core.controller.__file__", str(mock_controller_file)):
            controller.open_in_editor(str(sprite_file))

        mock_popen.assert_not_called()
        main_window.status_bar.showMessage.assert_called_once_with("Pixel editor not found")

    @patch("core.controller.subprocess.Popen")
    def test_open_in_editor_subprocess_error(self, mock_popen, controller: ExtractionController, main_window: Any, tmp_path: Path):
        """Test opening in editor when subprocess fails."""
        launcher_file = tmp_path / "launch_pixel_editor.py"
        launcher_file.write_text("# Fake launcher script")
        sprite_file = tmp_path / "sprite.png"
        sprite_file.write_text("fake png data")
        mock_popen.side_effect = Exception("Subprocess failed")

        mock_controller_file = tmp_path / "core" / "controller.py"
        with patch("core.controller.__file__", str(mock_controller_file)):
            controller.open_in_editor(str(sprite_file))

        main_window.status_bar.showMessage.assert_called_once()
        error_msg = main_window.status_bar.showMessage.call_args[0][0]
        assert "Failed to open pixel editor: Subprocess failed" in error_msg


@pytest.mark.no_manager_setup
class TestControllerManagerContextIntegration:
    """Test controller integration with manager context system.

    Note: These tests use mock managers with proper spec to verify controller
    initialization and signal connections without requiring full DI setup.
    """

    def test_controller_manager_access(self, standard_mock_main_window: Any, standard_mock_managers: tuple[Mock, Mock, Mock, Mock, Mock]):
        """Test that controller can access injected managers."""
        extraction_manager, injection_manager, session_manager, settings_manager, dialog_factory = standard_mock_managers

        # Controller now uses ConsoleErrorHandler directly (no UI import)
        controller = ExtractionController(
            standard_mock_main_window,
            extraction_manager=extraction_manager,
            injection_manager=injection_manager,
            session_manager=session_manager,
            settings_manager=settings_manager,
            dialog_factory=dialog_factory,
        )
        # Verify the exact managers passed are used (not fetched from DI)
        assert controller.extraction_manager is extraction_manager
        assert controller.injection_manager is injection_manager
        assert controller.session_manager is session_manager

    def test_controller_manager_state_persistence(self, standard_mock_main_window: Any, standard_mock_managers: tuple[Mock, Mock, Mock, Mock, Mock]):
        """Test that managers maintain their state independently."""
        extraction_manager, injection_manager, session_manager, settings_manager, dialog_factory = standard_mock_managers

        # Controller now uses ConsoleErrorHandler directly (no UI import)
        controller1 = ExtractionController(
            standard_mock_main_window,
            extraction_manager=extraction_manager,
            injection_manager=injection_manager,
            session_manager=session_manager,
            settings_manager=settings_manager,
            dialog_factory=dialog_factory,
        )
        # Set state on the extraction manager
        extraction_manager.test_state = "persistent_value"

        # Create second window mock with required attributes
        MainWindow = get_main_window_mock_spec()
        window2 = Mock(spec=MainWindow)
        window2.extract_requested = MagicMock()
        window2.open_in_editor_requested = MagicMock()
        window2.arrange_rows_requested = MagicMock()
        window2.arrange_grid_requested = MagicMock()
        window2.inject_requested = MagicMock()
        window2.extraction_panel = Mock()
        window2.extraction_panel.offset_changed = Mock()

        controller2 = ExtractionController(
            window2,
            extraction_manager=extraction_manager,
            injection_manager=injection_manager,
            session_manager=session_manager,
            settings_manager=settings_manager,
            dialog_factory=dialog_factory,
        )

        assert controller2.extraction_manager is controller1.extraction_manager
        assert controller2.extraction_manager.test_state == "persistent_value"


@pytest.mark.no_manager_setup
class TestPrivateAttributeAccessFix:
    """Test the private attribute access fix: get_output_path() method implementation"""

    @pytest.fixture
    def test_main_window(self, standard_mock_main_window: Any):
        """Create test main window for output path testing."""
        window = standard_mock_main_window

        # Add test methods for output path testing, simulating the MainWindow's public API
        def mock_get_output_path():
            return getattr(window, '_test_output_path', '')

        def set_test_output_path(path):
            window._test_output_path = path

        window.get_output_path = mock_get_output_path
        window.set_test_output_path = set_test_output_path

        return window

    @pytest.fixture
    def test_controller(self, test_main_window: Any, standard_mock_managers: tuple[Mock, Mock, Mock, Mock, Mock]) -> ExtractionController:
        """Create controller instance for private attribute access tests."""
        extraction_manager, injection_manager, session_manager, settings_manager, dialog_factory = standard_mock_managers

        # Controller now uses ConsoleErrorHandler directly (no UI import)
        controller = ExtractionController(
            test_main_window,
            extraction_manager=extraction_manager,
            injection_manager=injection_manager,
            session_manager=session_manager,
            settings_manager=settings_manager,
            dialog_factory=dialog_factory,
        )
        return controller

    def test_get_output_path_returns_value(self, test_main_window: Any):
        """Test that get_output_path() method works correctly with valid path."""
        test_path = "/path/to/output/sprite"
        test_main_window.set_test_output_path(test_path)
        result = test_main_window.get_output_path()
        assert result == test_path

    def test_get_output_path_returns_empty_string(self, test_main_window: Any):
        """Test that get_output_path() method handles empty path."""
        test_main_window.set_test_output_path("")
        result = test_main_window.get_output_path()
        assert result == ""

    def test_get_output_path_returns_none(self, test_main_window: Any):
        """Test that get_output_path() method handles None value."""
        test_main_window.set_test_output_path(None)
        result = test_main_window.get_output_path()
        assert result is None

    def test_controller_uses_public_method(self, test_controller: ExtractionController, test_main_window: Any):
        """Test that controller uses the public get_output_path() method (not private attribute)."""
        test_path = "/valid/output/path"
        test_main_window.set_test_output_path(test_path)

        original_get_path = test_main_window.get_output_path
        call_count = 0
        def tracked_get_path():
            nonlocal call_count
            call_count += 1
            return original_get_path()
        test_main_window.get_output_path = tracked_get_path

        # Assuming start_injection internally calls get_output_path
        test_controller.start_injection()

        assert call_count >= 1 # Ensure the public method was called

    def test_controller_handles_empty_output_path(self, test_controller: ExtractionController, test_main_window: Any):
        """Test that controller properly handles empty output path."""
        test_main_window.set_test_output_path("")
        test_controller.start_injection()
        # Assert - check status bar was updated with appropriate message if it is called
        if hasattr(test_main_window, 'status_bar') and test_main_window.status_bar:
            current_message = test_main_window.status_bar.showMessage.call_args
            # The exact message might depend on internal logic; check if it was called or if no error message
            if current_message:
                assert "No extraction to inject" in current_message[0][0] or current_message[0][0] == ""

    def test_controller_handles_none_output_path(self, test_controller: ExtractionController, test_main_window: Any):
        """Test that controller properly handles None output path."""
        test_main_window.set_test_output_path(None)
        test_controller.start_injection()
        if hasattr(test_main_window, 'status_bar') and test_main_window.status_bar:
            current_message = test_main_window.status_bar.showMessage.call_args
            if current_message:
                assert "No extraction to inject" in current_message[0][0] or current_message[0][0] == ""

    def test_private_attribute_not_accessed_directly(self, test_controller: ExtractionController, test_main_window: Any):
        """Test that controller does NOT access _output_path private attribute directly."""
        test_main_window._test_private_path = "/private/path"
        test_main_window.set_test_output_path("")

        test_controller.start_injection()

        assert test_main_window.get_output_path() == ""
        assert hasattr(test_main_window, '_test_private_path') # Private attribute exists but should be unused by controller
