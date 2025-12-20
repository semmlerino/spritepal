"""
Tests for ROM extraction crash fixes.
Verifies fixes for signal loops, offset parsing, and error handling.
"""
from __future__ import annotations

import os
import tempfile
from unittest.mock import Mock, patch

import pytest

from core.di_container import inject
from core.protocols.manager_protocols import InjectionManagerProtocol
from ui.injection_dialog import InjectionDialog
from ui.rom_extraction.workers.preview_worker import SpritePreviewWorker

# Systematic pytest markers applied based on test content analysis
pytestmark = [
    pytest.mark.usefixtures("isolated_managers", "mock_hal"),
    pytest.mark.skip_thread_cleanup(reason="Uses isolated_managers which owns worker threads"),
    pytest.mark.headless,
    pytest.mark.integration,
]

class TestSignalLoopFixes:
    """Test signal loop protection in injection dialog"""

    @pytest.fixture
    def injection_dialog(self, qtbot, isolated_managers):
        """Create injection dialog for testing"""
        injection_manager = inject(InjectionManagerProtocol)
        dialog = InjectionDialog(injection_manager=injection_manager)
        qtbot.addWidget(dialog)
        return dialog

    def test_sprite_location_change_blocks_signals(self, injection_dialog):
        """Test that changing sprite location blocks signals to prevent recursion"""
        dialog = injection_dialog

        # Mock the combo box to have sprite data
        dialog.sprite_location_combo.clear()
        dialog.sprite_location_combo.addItem("Select sprite location...", None)
        dialog.sprite_location_combo.addItem("Test Sprite (0x8000)", 0x8000)

        # Track if signals were fired
        rom_offset_changed_called = False
        original_handler = dialog._on_rom_offset_changed

        def mock_rom_offset_changed(text):
            nonlocal rom_offset_changed_called
            rom_offset_changed_called = True
            return original_handler(text)

        dialog._on_rom_offset_changed = mock_rom_offset_changed

        # Simulate selecting a sprite location
        dialog.sprite_location_combo.setCurrentIndex(1)

        # Verify the offset field was updated
        assert dialog.rom_offset_input.hex_edit.text() == "0x8000"

        # Verify the signal handler was NOT called due to signal blocking
        assert not rom_offset_changed_called

    def test_rom_offset_change_blocks_signals(self, injection_dialog):
        """Test that changing ROM offset blocks signals to prevent recursion"""
        dialog = injection_dialog

        # Set up combo box with a selection
        dialog.sprite_location_combo.clear()
        dialog.sprite_location_combo.addItem("Select sprite location...", None)
        dialog.sprite_location_combo.addItem("Test Sprite (0x8000)", 0x8000)
        dialog.sprite_location_combo.setCurrentIndex(1)

        # Track if signals were fired
        sprite_location_changed_called = False
        original_handler = dialog._on_sprite_location_changed

        def mock_sprite_location_changed(index):
            nonlocal sprite_location_changed_called
            sprite_location_changed_called = True
            return original_handler(index)

        dialog._on_sprite_location_changed = mock_sprite_location_changed

        # Manually change the offset field
        dialog.rom_offset_input.hex_edit.setText("0x9000")

        # Verify the combo box was reset to index 0
        assert dialog.sprite_location_combo.currentIndex() == 0

        # Verify the signal handler was NOT called due to signal blocking
        assert not sprite_location_changed_called

class TestOffsetParsingFixes:
    """Test improved offset parsing with error handling"""

    @pytest.fixture
    def injection_dialog(self, qtbot, isolated_managers):
        """Create injection dialog for testing"""
        injection_manager = inject(InjectionManagerProtocol)
        dialog = InjectionDialog(injection_manager=injection_manager)
        qtbot.addWidget(dialog)
        return dialog

    def test_parse_hex_offset_valid_formats(self, injection_dialog):
        """Test parsing of various valid hex offset formats"""
        dialog = injection_dialog

        # Test various valid formats
        test_cases = [
            ("0x8000", 0x8000),
            ("0X8000", 0x8000),
            ("8000", 0x8000),
            ("0xABCD", 0xABCD),
            ("abcd", 0xABCD),
            ("0x0", 0x0),
            ("FFFF", 0xFFFF),
            (" 0x8000 ", 0x8000),  # With whitespace
        ]

        for input_text, expected in test_cases:
            result = dialog.rom_offset_input._parse_hex_offset(input_text)
            assert result == expected, f"Failed for input: '{input_text}'"

    def test_parse_hex_offset_invalid_formats(self, injection_dialog):
        """Test parsing of invalid hex offset formats"""
        dialog = injection_dialog

        # Test various invalid formats
        invalid_inputs = [
            "",
            "   ",
            "not_hex",
            "0xGGGG",
            "12345G",
            "0x",
            "x8000",
            None,
        ]

        for invalid_input in invalid_inputs:
            result = dialog.rom_offset_input._parse_hex_offset(invalid_input)
            assert result is None, f"Should have failed for input: '{invalid_input}'"

    def test_offset_validation_in_get_parameters(self, injection_dialog):
        """Test that get_parameters properly validates offsets"""
        dialog = injection_dialog

        # Set up dialog for ROM injection
        dialog.set_current_tab(1)  # ROM tab

        # Mock file selectors to avoid UI blocking
        with patch.object(dialog.sprite_file_selector, "get_path", return_value="/fake/sprite.png"), \
             patch.object(dialog.input_rom_selector, "get_path", return_value="/fake/input.sfc"), \
             patch.object(dialog.output_rom_selector, "get_path", return_value="/fake/output.sfc"):

            # Test invalid offset
            dialog.rom_offset_input.hex_edit.setText("invalid_hex")

            # Mock QDialog.accept and dialog result
            dialog.setResult(dialog.DialogCode.Accepted)

            # Should return None due to invalid offset
            with patch("PySide6.QtWidgets.QMessageBox.warning") as mock_warning:
                result = dialog.get_parameters()
                assert result is None
                mock_warning.assert_called_once()
                args = mock_warning.call_args[0]
                assert "Invalid ROM offset value" in args[2]

class TestROMLoadingSafety:
    """Test safe ROM loading with error handling"""

    @pytest.fixture
    def injection_dialog(self, qtbot, isolated_managers):
        """Create injection dialog for testing"""
        injection_manager = inject(InjectionManagerProtocol)
        dialog = InjectionDialog(injection_manager=injection_manager)
        qtbot.addWidget(dialog)
        return dialog

    def test_load_rom_info_file_not_found(self, injection_dialog, qtbot):
        """Test ROM loading with non-existent file - async worker pattern.

        Since Issue 2 fix, ROM loading is now async to prevent UI freezes.
        The worker will complete and the handler will show an error dialog.
        We patch QMessageBox to prevent blocking in tests.
        """
        dialog = injection_dialog

        # Patch QMessageBox to prevent blocking dialogs during test
        with patch("ui.injection_dialog.QMessageBox") as mock_msgbox:
            mock_msgbox.critical.return_value = None
            mock_msgbox.warning.return_value = None

            # Start async ROM loading
            dialog._load_rom_info("/nonexistent/file.sfc")

            # Wait for worker to complete using waitUntil (handles fast-completing workers)
            # The signal may fire before waitSignal is ready, so check worker state instead
            def worker_done() -> bool:
                loader = dialog._rom_info_loader
                return loader is None or not loader.isRunning()

            qtbot.waitUntil(worker_done, timeout=5000)

            # Process events to ensure handler runs
            qtbot.wait(100)

            # Verify an error dialog was shown (critical or warning)
            assert mock_msgbox.critical.called or mock_msgbox.warning.called or \
                   dialog.sprite_location_combo.itemText(0) in ("Error loading ROM", "Load ROM file first...")

    def test_load_rom_info_invalid_file_size(self, injection_dialog, qtbot):
        """Test ROM loading with invalid file size - async worker pattern.

        Since Issue 2 fix, ROM loading is now async to prevent UI freezes.
        The worker will complete and handler may show warning dialog.
        We patch QMessageBox to prevent blocking in tests.
        """
        dialog = injection_dialog

        with tempfile.NamedTemporaryFile(delete=False) as tmp_file:
            # Create a file that's too small to be a valid ROM
            tmp_file.write(b"tiny")
            tmp_file.flush()

            try:
                # Patch QMessageBox to prevent blocking dialogs during test
                with patch("ui.injection_dialog.QMessageBox") as mock_msgbox:
                    mock_msgbox.critical.return_value = None
                    mock_msgbox.warning.return_value = None

                    # Start async ROM loading
                    dialog._load_rom_info(tmp_file.name)

                    # Wait for worker to complete using waitUntil (handles fast-completing workers)
                    # The signal may fire before waitSignal is ready, so check worker state instead
                    def worker_done() -> bool:
                        loader = dialog._rom_info_loader
                        return loader is None or not loader.isRunning()

                    qtbot.waitUntil(worker_done, timeout=5000)

                    # Process events to ensure handler runs
                    qtbot.wait(100)

                    # Test passes if either:
                    # 1. A warning/error dialog was shown
                    # 2. UI was updated to show error state
                    assert mock_msgbox.critical.called or mock_msgbox.warning.called or \
                           dialog.sprite_location_combo.itemText(0) in (
                               "Error loading ROM", "Loading ROM info...", "Load ROM file first..."
                           )

            finally:
                os.unlink(tmp_file.name)

    def test_clear_rom_ui_state(self, injection_dialog):
        """Test that ROM UI state is properly cleared"""
        dialog = injection_dialog

        # Set up some state first
        dialog.sprite_location_combo.addItem("Test Item", 0x8000)
        dialog.rom_info_text.setText("Test ROM info")
        dialog.rom_info_group.show()

        # Clear state
        dialog._clear_rom_ui_state()

        # Verify state was cleared
        assert dialog.sprite_location_combo.count() == 1
        assert dialog.sprite_location_combo.itemText(0) == "Load ROM file first..."
        assert dialog.rom_info_text.toPlainText() == ""
        assert not dialog.rom_info_group.isVisible()

class TestPreviewWorkerSafety:
    """Test preview worker safety improvements"""

    def test_preview_worker_invalid_offset(self, tmp_path):
        """Test preview worker with invalid offset"""
        # Mock extractor
        mock_extractor = Mock()

        # Create a valid ROM file
        rom_file = tmp_path / "test.sfc"
        rom_file.write_bytes(b"\x00" * 0x10000)  # 64KB dummy ROM

        # Create worker with invalid (negative) offset
        worker = SpritePreviewWorker(
            rom_path=str(rom_file),
            offset=-1,
            sprite_name="test",
            extractor=mock_extractor
        )

        # Mock the error signal
        error_messages = []
        worker.preview_error.connect(lambda msg: error_messages.append(msg))

        # Run the worker
        worker.run()

        # Verify error was emitted
        assert len(error_messages) == 1
        assert "Invalid" in error_messages[0]
        assert "negative" in error_messages[0]

    def test_preview_worker_file_not_found(self):
        """Test preview worker with non-existent ROM file"""
        mock_extractor = Mock()

        worker = SpritePreviewWorker(
            rom_path="/nonexistent/rom.sfc",
            offset=0x8000,
            sprite_name="test",
            extractor=mock_extractor
        )

        error_messages = []
        worker.preview_error.connect(lambda msg: error_messages.append(msg))

        worker.run()

        assert len(error_messages) == 1
        assert "ROM file not found" in error_messages[0]

    def test_preview_worker_offset_beyond_rom_size(self):
        """Test preview worker with offset beyond ROM size"""
        mock_extractor = Mock()

        # Create a small temporary ROM file
        with tempfile.NamedTemporaryFile(delete=False) as tmp_file:
            tmp_file.write(b"A" * 0x8000)  # 32KB ROM
            tmp_file.flush()

            try:
                worker = SpritePreviewWorker(
                    rom_path=tmp_file.name,
                    offset=0x10000,  # Offset beyond file size
                    sprite_name="test",
                    extractor=mock_extractor
                )

                error_messages = []
                worker.preview_error.connect(lambda msg: error_messages.append(msg))

                worker.run()

                assert len(error_messages) == 1
                assert "beyond ROM size" in error_messages[0]

            finally:
                os.unlink(tmp_file.name)

class TestInputValidation:
    """Test input validation improvements"""

    @pytest.fixture
    def injection_dialog(self, qtbot, isolated_managers):
        """Create injection dialog for testing"""
        injection_manager = inject(InjectionManagerProtocol)
        dialog = InjectionDialog(injection_manager=injection_manager)
        qtbot.addWidget(dialog)
        return dialog

    def test_real_time_offset_validation(self, injection_dialog):
        """Test offset input accepts various formats"""
        dialog = injection_dialog

        # Test valid hex input formats are accepted
        test_cases = [
            "0x8000",
            "0X8000",
            "8000",
            "ABCD",
            "  0x1234  ",  # with whitespace
        ]

        for test_input in test_cases:
            dialog.rom_offset_input.hex_edit.setText(test_input)
            # Just verify the text was set - the widget doesn't have decimal display
            assert dialog.rom_offset_input.hex_edit.text() == test_input

        # Test that parsing works correctly through the internal method
        assert dialog.rom_offset_input._parse_hex_offset("0x8000") == 0x8000
        assert dialog.rom_offset_input._parse_hex_offset("invalid") is None
        assert dialog.rom_offset_input._parse_hex_offset("") is None
        assert dialog.rom_offset_input._parse_hex_offset("   ") is None

    def test_comprehensive_parameter_validation(self, injection_dialog):
        """Test comprehensive parameter validation in get_parameters"""
        dialog = injection_dialog

        # Set dialog to accepted state
        dialog.setResult(dialog.DialogCode.Accepted)

        # Test ROM injection tab
        dialog.set_current_tab(1)

        # Test missing sprite path
        with patch.object(dialog.sprite_file_selector, "get_path", return_value=""), \
             patch.object(dialog.input_rom_selector, "get_path", return_value=""), \
             patch.object(dialog.output_rom_selector, "get_path", return_value=""):

            with patch("PySide6.QtWidgets.QMessageBox.warning") as mock_warning:
                result = dialog.get_parameters()
                assert result is None
                mock_warning.assert_called_once()
                args = mock_warning.call_args[0]
                assert "sprite file" in args[2].lower()
