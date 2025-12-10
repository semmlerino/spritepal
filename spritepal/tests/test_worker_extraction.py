"""
Unit tests for extraction worker implementations.

Tests the VRAMExtractionWorker and ROMExtractionWorker classes to ensure
proper manager delegation, signal handling, and error management.
"""
from __future__ import annotations

from unittest.mock import Mock, patch

import pytest
from PIL import Image
from PySide6.QtTest import QSignalSpy

from core.managers.base_manager import BaseManager
from core.workers.extraction import ROMExtractionWorker, VRAMExtractionWorker

# Serial execution required: QApplication management
pytestmark = [

    pytest.mark.serial,
    pytest.mark.qt_application,
    pytest.mark.headless,
    pytest.mark.requires_display,
    pytest.mark.rom_data,
    pytest.mark.signals_slots,
]

@pytest.mark.no_manager_setup
class TestVRAMExtractionWorker:
    """Test the VRAMExtractionWorker class."""

    def test_vram_worker_initialization(self, qtbot):
        """Test VRAM extraction worker initialization."""
        params = {
            "vram_path": "/test/vram.dmp",
            "output_base": "/test/output",
            "create_grayscale": True,
        }

        with patch("core.workers.extraction.get_extraction_manager") as mock_get_manager:
            mock_manager = Mock(spec=BaseManager)
            mock_get_manager.return_value = mock_manager

            worker = VRAMExtractionWorker(params)
            qtbot.addWidget(worker)

            assert worker.params == params
            assert worker.manager is mock_manager
            assert worker._operation_name == "VRAMExtractionWorker"
            assert worker._connections == []

    def test_vram_manager_signal_connections(self, qtbot):
        """Test VRAM worker manager signal connections."""
        params = {
            "vram_path": "/test/vram.dmp",
            "output_base": "/test/output",
        }

        with patch("core.workers.extraction.get_extraction_manager") as mock_get_manager:
            mock_manager = Mock()
            mock_manager.extraction_progress = Mock()
            mock_manager.palettes_extracted = Mock()
            mock_manager.active_palettes_found = Mock()
            mock_manager.preview_generated = Mock()

            # Mock connection objects
            mock_connection = Mock()
            mock_manager.extraction_progress.connect.return_value = mock_connection
            mock_manager.palettes_extracted.connect.return_value = mock_connection
            mock_manager.active_palettes_found.connect.return_value = mock_connection
            mock_manager.preview_generated.connect.return_value = mock_connection

            mock_get_manager.return_value = mock_manager

            worker = VRAMExtractionWorker(params)
            qtbot.addWidget(worker)

            # Test signal connections
            worker.connect_manager_signals()

            # Verify connections were made
            assert mock_manager.extraction_progress.connect.called
            assert mock_manager.palettes_extracted.connect.called
            assert mock_manager.active_palettes_found.connect.called
            assert mock_manager.preview_generated.connect.called

            # Verify connections were stored
            assert len(worker._connections) == 4

    def test_vram_preview_signal_conversion(self, qtbot):
        """Test that preview signals emit PIL images directly (no QPixmap conversion in worker thread)."""
        params = {
            "vram_path": "/test/vram.dmp",
            "output_base": "/test/output",
        }

        with patch("core.workers.extraction.get_extraction_manager") as mock_get_manager:
            mock_manager = Mock()
            mock_manager.extraction_progress = Mock()
            mock_manager.palettes_extracted = Mock()
            mock_manager.active_palettes_found = Mock()
            mock_manager.preview_generated = Mock()

            # Mock connection returns
            mock_connection = Mock()
            mock_manager.extraction_progress.connect.return_value = mock_connection
            mock_manager.palettes_extracted.connect.return_value = mock_connection
            mock_manager.active_palettes_found.connect.return_value = mock_connection
            mock_manager.preview_generated.connect.return_value = mock_connection

            mock_get_manager.return_value = mock_manager

            worker = VRAMExtractionWorker(params)
            qtbot.addWidget(worker)

            # Set up signal spies
            preview_spy = QSignalSpy(worker.preview_ready)
            preview_image_spy = QSignalSpy(worker.preview_image_ready)

            # Connect signals and get the preview callback
            worker.connect_manager_signals()

            # Get the callback function from the connect call
            preview_callback = mock_manager.preview_generated.connect.call_args[0][0]

            # Create a mock PIL image
            mock_image = Mock(spec=Image.Image)
            tile_count = 10

            # Call the preview callback
            preview_callback(mock_image, tile_count)

            # Verify signals were emitted with PIL image objects directly
            # (No QPixmap conversion should happen in worker thread)
            assert preview_spy.count() == 1
            assert preview_spy.at(0) == [mock_image, tile_count]

            assert preview_image_spy.count() == 1
            assert preview_image_spy.at(0) == [mock_image]

    def test_vram_successful_operation(self, qtbot):
        """Test successful VRAM extraction operation."""
        params = {
            "vram_path": "/test/vram.dmp",
            "output_base": "/test/output",
            "create_grayscale": True,
        }

        with patch("core.workers.extraction.get_extraction_manager") as mock_get_manager:
            mock_manager = Mock()
            mock_manager.extract_from_vram.return_value = ["file1.png", "file2.pal.json"]
            mock_get_manager.return_value = mock_manager

            worker = VRAMExtractionWorker(params)
            qtbot.addWidget(worker)

            # Set up signal spies
            extraction_spy = QSignalSpy(worker.extraction_finished)
            operation_spy = QSignalSpy(worker.operation_finished)

            # Perform operation
            worker.perform_operation()

            # Verify manager was called with correct parameters
            mock_manager.extract_from_vram.assert_called_once_with(
                vram_path="/test/vram.dmp",
                output_base="/test/output",
                cgram_path=None,
                oam_path=None,
                vram_offset=None,
                create_grayscale=True,
                create_metadata=True,
                grayscale_mode=False,
            )

            # Verify completion signals
            assert extraction_spy.count() == 1
            assert extraction_spy.at(0) == [["file1.png", "file2.pal.json"]]

            assert operation_spy.count() == 1
            assert operation_spy.at(0) == [True, "Successfully extracted 2 files"]

    def test_vram_operation_error_handling(self, qtbot):
        """Test VRAM extraction error handling."""
        params = {
            "vram_path": "/test/vram.dmp",
            "output_base": "/test/output",
        }

        with patch("core.workers.extraction.get_extraction_manager") as mock_get_manager:
            mock_manager = Mock()
            mock_manager.extract_from_vram.side_effect = Exception("Test extraction error")
            mock_get_manager.return_value = mock_manager

            worker = VRAMExtractionWorker(params)
            qtbot.addWidget(worker)

            # Set up signal spies
            error_spy = QSignalSpy(worker.error)
            operation_spy = QSignalSpy(worker.operation_finished)

            # Perform operation (should handle error)
            worker.perform_operation()

            # Verify error handling
            assert error_spy.count() == 1
            assert "VRAM extraction failed: Test extraction error" in error_spy.at(0)[0]
            assert isinstance(error_spy.at(0)[1], Exception)

            assert operation_spy.count() == 1
            assert operation_spy.at(0)[0] is False  # Success = False
            assert "VRAM extraction failed: Test extraction error" in operation_spy.at(0)[1]

    def test_vram_worker_with_manager_signals(self, qtbot):
        """Test VRAM worker with manager signals using proper mocking."""
        params = {
            "vram_path": "/test/vram.dmp",
            "output_base": "/test/output",
        }

        with patch("core.workers.extraction.get_extraction_manager") as mock_get_manager:
            # Create a properly mocked manager
            mock_manager = Mock()
            mock_manager.extraction_progress = Mock()
            mock_manager.palettes_extracted = Mock()
            mock_manager.active_palettes_found = Mock()
            mock_manager.preview_generated = Mock()
            # The actual method called is extract_from_vram, not extract_vram_sprites
            mock_manager.extract_from_vram = Mock(return_value=["output1.png", "output2.png"])

            # Set up mock returns for signal connections
            mock_connection = Mock()
            mock_connection.disconnect = Mock()
            mock_manager.extraction_progress.connect.return_value = mock_connection
            mock_manager.palettes_extracted.connect.return_value = mock_connection
            mock_manager.active_palettes_found.connect.return_value = mock_connection
            mock_manager.preview_generated.connect.return_value = mock_connection

            mock_get_manager.return_value = mock_manager

            worker = VRAMExtractionWorker(params)
            qtbot.addWidget(worker)

            # Set up signal spies
            operation_spy = QSignalSpy(worker.operation_finished)
            extraction_spy = QSignalSpy(worker.extraction_finished)

            # Connect manager signals
            worker.connect_manager_signals()

            # Perform operation
            worker.perform_operation()

            # Verify manager method was called with the expected keyword arguments
            mock_manager.extract_from_vram.assert_called_once()
            call_kwargs = mock_manager.extract_from_vram.call_args.kwargs
            assert call_kwargs["vram_path"] == "/test/vram.dmp"
            assert call_kwargs["output_base"] == "/test/output"

            # Verify signals emitted
            assert operation_spy.count() == 1
            assert operation_spy.at(0)[0] is True
            assert "Successfully extracted 2 files" in operation_spy.at(0)[1]

            assert extraction_spy.count() == 1
            assert extraction_spy.at(0) == [["output1.png", "output2.png"]]

            # Test disconnection
            worker.disconnect_manager_signals()
            # Note: The actual disconnect is called via QObject.disconnect(connection),
            # not connection.disconnect(), so we just verify the connections are cleared
            assert worker._connections == []

@pytest.mark.no_manager_setup
class TestROMExtractionWorker:
    """Test the ROMExtractionWorker class."""

    def test_rom_worker_initialization(self, qtbot):
        """Test ROM extraction worker initialization."""
        params = {
            "rom_path": "/test/rom.smc",
            "sprite_offset": 0x1000,
            "output_base": "/test/output",
            "sprite_name": "test_sprite",
        }

        with patch("core.workers.extraction.get_extraction_manager") as mock_get_manager:
            mock_manager = Mock(spec=BaseManager)
            mock_get_manager.return_value = mock_manager

            worker = ROMExtractionWorker(params)
            qtbot.addWidget(worker)

            assert worker.params == params
            assert worker.manager is mock_manager
            assert worker._operation_name == "ROMExtractionWorker"
            assert worker._connections == []

    def test_rom_manager_signal_connections(self, qtbot):
        """Test ROM worker manager signal connections."""
        params = {
            "rom_path": "/test/rom.smc",
            "sprite_offset": 0x1000,
            "output_base": "/test/output",
            "sprite_name": "test_sprite",
        }

        with patch("core.workers.extraction.get_extraction_manager") as mock_get_manager:
            mock_manager = Mock()
            mock_manager.extraction_progress = Mock()

            # Mock connection object
            mock_connection = Mock()
            mock_manager.extraction_progress.connect.return_value = mock_connection

            mock_get_manager.return_value = mock_manager

            worker = ROMExtractionWorker(params)
            qtbot.addWidget(worker)

            # Test signal connections
            worker.connect_manager_signals()

            # Verify connection was made
            assert mock_manager.extraction_progress.connect.called

            # Verify connection was stored
            assert len(worker._connections) == 1

    def test_rom_successful_operation(self, qtbot):
        """Test successful ROM extraction operation."""
        params = {
            "rom_path": "/test/rom.smc",
            "sprite_offset": 0x1000,
            "output_base": "/test/output",
            "sprite_name": "test_sprite",
            "cgram_path": "/test/cgram.dmp",
        }

        with patch("core.workers.extraction.get_extraction_manager") as mock_get_manager:
            mock_manager = Mock()
            mock_manager.extract_from_rom.return_value = ["sprite.png", "sprite.pal.json"]
            mock_get_manager.return_value = mock_manager

            worker = ROMExtractionWorker(params)
            qtbot.addWidget(worker)

            # Set up signal spies
            extraction_spy = QSignalSpy(worker.extraction_finished)
            operation_spy = QSignalSpy(worker.operation_finished)

            # Perform operation
            worker.perform_operation()

            # Verify manager was called with correct parameters
            mock_manager.extract_from_rom.assert_called_once_with(
                rom_path="/test/rom.smc",
                offset=0x1000,
                output_base="/test/output",
                sprite_name="test_sprite",
                cgram_path="/test/cgram.dmp",
            )

            # Verify completion signals
            assert extraction_spy.count() == 1
            assert extraction_spy.at(0) == [["sprite.png", "sprite.pal.json"]]

            assert operation_spy.count() == 1
            assert operation_spy.at(0) == [True, "Successfully extracted 2 files"]

    def test_rom_operation_error_handling(self, qtbot):
        """Test ROM extraction error handling."""
        params = {
            "rom_path": "/test/rom.smc",
            "sprite_offset": 0x1000,
            "output_base": "/test/output",
            "sprite_name": "test_sprite",
        }

        with patch("core.workers.extraction.get_extraction_manager") as mock_get_manager:
            mock_manager = Mock()
            mock_manager.extract_from_rom.side_effect = Exception("ROM file not found")
            mock_get_manager.return_value = mock_manager

            worker = ROMExtractionWorker(params)
            qtbot.addWidget(worker)

            # Set up signal spies
            error_spy = QSignalSpy(worker.error)
            operation_spy = QSignalSpy(worker.operation_finished)

            # Perform operation (should handle error)
            worker.perform_operation()

            # Verify error handling
            assert error_spy.count() == 1
            assert "ROM extraction failed: ROM file not found" in error_spy.at(0)[0]
            assert isinstance(error_spy.at(0)[1], Exception)

            assert operation_spy.count() == 1
            assert operation_spy.at(0)[0] is False  # Success = False
            assert "ROM extraction failed: ROM file not found" in operation_spy.at(0)[1]

    def test_rom_operation_cancellation(self, qtbot):
        """Test ROM extraction cancellation handling."""
        params = {
            "rom_path": "/test/rom.smc",
            "sprite_offset": 0x1000,
            "output_base": "/test/output",
            "sprite_name": "test_sprite",
        }

        with patch("core.workers.extraction.get_extraction_manager") as mock_get_manager:
            mock_manager = Mock()
            mock_get_manager.return_value = mock_manager

            worker = ROMExtractionWorker(params)
            qtbot.addWidget(worker)

            # Cancel the worker
            worker.cancel()

            # Performing operation should raise InterruptedError
            with pytest.raises(InterruptedError, match="Operation was cancelled"):
                worker.perform_operation()

@pytest.fixture
def qtbot():
    """Provide qtbot for Qt testing."""
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance()
    if app is None:
        app = QApplication([])

    class QtBot:
        def addWidget(self, widget):
            pass

    return QtBot()
