"""
Tests for ROM injection settings persistence

NOTE: This file creates SessionManager instances directly for testing with isolated sessions.
The deprecation warning is suppressed.
"""
from __future__ import annotations

import os
import tempfile
import warnings
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

# Suppress deprecation warning for direct SessionManager instantiation
warnings.filterwarnings(
    "ignore",
    message=r"Direct SessionManager instantiation is deprecated",
    category=DeprecationWarning,
)

from core.managers import InjectionManager
from ui.injection_dialog import InjectionDialog
from utils.constants import (
    # Systematic pytest markers applied based on test content analysis
    SETTINGS_KEY_FAST_COMPRESSION,
    SETTINGS_KEY_LAST_CUSTOM_OFFSET,
    SETTINGS_KEY_LAST_INPUT_ROM,
    SETTINGS_KEY_LAST_INPUT_VRAM,
    SETTINGS_KEY_LAST_SPRITE_LOCATION,
    SETTINGS_NS_ROM_INJECTION,
)
from core.services.settings_manager import SettingsManager

pytestmark = [
    pytest.mark.dialog,
    pytest.mark.file_io,
    pytest.mark.headless,
    pytest.mark.integration,
    pytest.mark.mock_dialogs,
    pytest.mark.mock_only,
    pytest.mark.no_qt,
    pytest.mark.rom_data,
    pytest.mark.ci_safe,
]
class TestROMInjectionSettingsPersistence:
    """Test ROM injection settings persistence functionality"""

    @pytest.fixture
    def temp_settings_file(self):
        """Create a temporary settings file"""
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            temp_path = f.name
        yield temp_path
        if os.path.exists(temp_path):
            os.unlink(temp_path)

    @pytest.fixture
    def settings_manager(self, temp_settings_file):
        """Create a settings manager with temporary file"""
        # Mock the SessionManager to use temporary storage
        import json

        from core.managers.session_manager import SessionManager

        # Create a session manager with temporary file storage
        real_session_manager = SessionManager(settings_path=Path(temp_settings_file))

        # Pass session_manager directly to SettingsManager (replaces deprecated get_session_manager patch)
        manager = SettingsManager("SpritePal", session_manager=real_session_manager)

        # Add _settings property for test compatibility
        def get_settings():
            # Load settings from the temp file for test verification
            try:
                with open(temp_settings_file) as f:
                    return json.load(f)
            except Exception:
                return {}

        # Make it accessible as both a property and direct attribute
        manager._settings = property(get_settings)
        # Also store direct access for tests
        manager._get_settings = get_settings
        manager._mock_session_manager = real_session_manager  # Expose for tests

        yield manager

    @pytest.fixture
    def mock_dialog(self):
        """Create a mock injection dialog"""
        # Create a mock dialog without initializing Qt components
        dialog = Mock(spec=InjectionDialog)

        # Mock UI elements
        dialog.input_rom_edit = Mock()
        dialog.output_rom_edit = Mock()
        dialog.sprite_location_combo = Mock()
        dialog.sprite_location_combo.count.return_value = 0  # No items in combo box
        dialog.rom_offset_hex_edit = Mock()
        dialog.fast_compression_check = Mock()
        dialog.input_vram_edit = Mock()
        dialog.output_vram_edit = Mock()

        # Add input/output selectors
        dialog.input_rom_selector = Mock()
        dialog.output_rom_selector = Mock()
        dialog.rom_offset_input = Mock()

        # Add the actual method from the class
        dialog.save_rom_injection_parameters = (
            InjectionDialog.save_rom_injection_parameters.__get__(dialog)
        )
        dialog._set_rom_injection_defaults = (
            InjectionDialog._set_rom_injection_defaults.__get__(dialog)
        )
        dialog._restore_saved_sprite_location = (
            InjectionDialog._restore_saved_sprite_location.__get__(dialog)
        )
        dialog._load_rom_info = Mock()

        return dialog

    def test_save_rom_injection_parameters(self, mock_dialog, settings_manager):
        """Test saving ROM injection parameters"""
        # Set up mock values
        mock_dialog.input_rom_selector.get_path.return_value = "/path/to/test.sfc"
        mock_dialog.sprite_location_combo.currentText.return_value = (
            "Kirby Sprite (0x123456)"
        )
        mock_dialog.rom_offset_input.get_text.return_value = "0x123456"
        mock_dialog.fast_compression_check.isChecked.return_value = True

        # Create a real injection manager that uses our test session_manager
        injection_manager = InjectionManager()
        with patch.object(
            injection_manager, "_get_session_manager", return_value=settings_manager._mock_session_manager
        ):
            mock_dialog.injection_manager = injection_manager

            # Save parameters
            mock_dialog.save_rom_injection_parameters()

        # Verify saved values in the actual settings manager
        assert (
            settings_manager.get_value(
                SETTINGS_NS_ROM_INJECTION, SETTINGS_KEY_LAST_INPUT_ROM
            )
            == "/path/to/test.sfc"
        )
        assert (
            settings_manager.get_value(
                SETTINGS_NS_ROM_INJECTION, SETTINGS_KEY_LAST_SPRITE_LOCATION
            )
            == "Kirby Sprite (0x123456)"
        )
        assert (
            settings_manager.get_value(
                SETTINGS_NS_ROM_INJECTION, SETTINGS_KEY_LAST_CUSTOM_OFFSET
            )
            == "0x123456"
        )
        assert (
            settings_manager.get_value(
                SETTINGS_NS_ROM_INJECTION, SETTINGS_KEY_FAST_COMPRESSION
            )
            is True
        )

    def test_save_empty_rom_injection_parameters(self, mock_dialog, settings_manager):
        """Test saving when fields are empty"""
        # Set up empty values
        mock_dialog.input_rom_selector.get_path.return_value = ""
        mock_dialog.sprite_location_combo.currentText.return_value = (
            "Select sprite location..."
        )
        mock_dialog.rom_offset_input.get_text.return_value = ""
        mock_dialog.fast_compression_check.isChecked.return_value = False

        # Create a real injection manager that uses our test settings_manager
        injection_manager = InjectionManager()
        with patch.object(
            injection_manager, "_get_session_manager", return_value=settings_manager._mock_session_manager
        ):
            mock_dialog.injection_manager = injection_manager

            # Save parameters
            mock_dialog.save_rom_injection_parameters()

        # Verify empty custom offset is saved as empty string
        value = settings_manager.get_value(
            SETTINGS_NS_ROM_INJECTION, SETTINGS_KEY_LAST_CUSTOM_OFFSET, None
        )
        assert value == ""  # Empty string is saved

        # Verify fast compression is saved as False
        value = settings_manager.get_value(
            SETTINGS_NS_ROM_INJECTION, SETTINGS_KEY_FAST_COMPRESSION, None
        )
        assert value is False

    def test_save_vram_injection_paths(self, settings_manager):
        """Test saving VRAM injection paths using ROM injection namespace"""
        # Save VRAM paths
        settings_manager.set_value(
            SETTINGS_NS_ROM_INJECTION,
            SETTINGS_KEY_LAST_INPUT_VRAM,
            "/path/to/input.dmp",
        )
        settings_manager.save()

        # Create a new settings manager to verify persistence
        # The settings should persist through the SessionManager
        assert (
            settings_manager.get_value(
                SETTINGS_NS_ROM_INJECTION, SETTINGS_KEY_LAST_INPUT_VRAM
            )
            == "/path/to/input.dmp"
        )

    def test_load_rom_injection_defaults(self, mock_dialog, settings_manager):
        """Test loading ROM injection defaults"""
        # Pre-populate settings
        settings_manager.set_value(
            SETTINGS_NS_ROM_INJECTION, SETTINGS_KEY_LAST_INPUT_ROM, "/test/rom.sfc"
        )
        settings_manager.set_value(
            SETTINGS_NS_ROM_INJECTION,
            SETTINGS_KEY_LAST_SPRITE_LOCATION,
            "Kirby Sprite (0x123456)",
        )
        settings_manager.set_value(
            SETTINGS_NS_ROM_INJECTION, SETTINGS_KEY_LAST_CUSTOM_OFFSET, "0x789ABC"
        )
        settings_manager.set_value(
            SETTINGS_NS_ROM_INJECTION, SETTINGS_KEY_FAST_COMPRESSION, True
        )

        # Create a real injection manager that uses our test settings_manager
        injection_manager = InjectionManager()
        with (
            patch("pathlib.Path.exists", return_value=True),  # Path().exists() not os.path.exists
            patch.object(
                injection_manager, "_get_session_manager", return_value=settings_manager._mock_session_manager
            ),
        ):
            mock_dialog.injection_manager = injection_manager
            mock_dialog.sprite_path = "/test/sprite.png"
            mock_dialog.metadata = None
            mock_dialog.rom_extraction_info = None
            mock_dialog.extraction_vram_offset = None

            mock_dialog._set_rom_injection_defaults()

        # Verify UI elements were populated
        mock_dialog.input_rom_selector.set_path.assert_called_with("/test/rom.sfc")
        # Check that output ROM path was set (it may include a timestamp if file exists)
        assert mock_dialog.output_rom_selector.set_path.called
        output_path = mock_dialog.output_rom_selector.set_path.call_args[0][0]
        assert output_path.startswith("/test/rom_modified")
        assert output_path.endswith(".sfc")
        mock_dialog.rom_offset_input.set_text.assert_called_with("0x789ABC")
        mock_dialog.fast_compression_check.setChecked.assert_called_with(True)

    def test_settings_save_error_handling(self, mock_dialog, settings_manager, caplog):
        """Test error handling when saving settings fails"""
        import logging

        caplog.set_level(logging.ERROR)

        # Set up mock values
        mock_dialog.input_rom_selector.get_path.return_value = "/path/to/test.sfc"
        mock_dialog.sprite_location_combo.currentText.return_value = (
            "Select sprite location..."
        )
        mock_dialog.rom_offset_input.get_text.return_value = ""
        mock_dialog.fast_compression_check.isChecked.return_value = False

        # Mock save to raise exception
        injection_manager = InjectionManager()
        with (
            patch.object(
                injection_manager, "_get_session_manager", return_value=settings_manager._mock_session_manager
            ),
            patch.object(
                settings_manager._mock_session_manager, "save_session", side_effect=OSError("Permission denied")
            ),
        ):
            mock_dialog.injection_manager = injection_manager

            # Call the method
            mock_dialog.save_rom_injection_parameters()

            # Verify error was logged using caplog
            assert len(caplog.records) >= 1
            assert "Failed to save ROM injection parameters" in caplog.text
            assert "Permission denied" in caplog.text

    def test_sprite_location_restoration_after_rom_load(self, mock_dialog, settings_manager):
        """Test that sprite location is restored after ROM is loaded"""
        # Setup combo box with items
        mock_dialog.sprite_location_combo.count.return_value = 4
        # Define the item texts by index
        item_texts = {
            0: "Select sprite location...",
            1: "Kirby Sprite (0x123456)",
            2: "Helper Sprite (0x234567)",
            3: "Boss Sprite (0x345678)",
        }
        mock_dialog.sprite_location_combo.itemText.side_effect = lambda i: item_texts.get(i, "")

        # Define the item data by index
        item_data = {0: None, 1: 0x123456, 2: 0x234567, 3: 0x345678}
        mock_dialog.sprite_location_combo.itemData.side_effect = lambda i: item_data.get(i)

        # Mock settings with saved sprite location
        # Note: The saved value includes the full text with offset, as saved by the dialog
        settings_manager.set_value(
            SETTINGS_NS_ROM_INJECTION,
            SETTINGS_KEY_LAST_SPRITE_LOCATION,
            "Helper Sprite (0x234567)"
        )

        injection_manager = InjectionManager()
        with patch.object(
            injection_manager, "_get_session_manager", return_value=settings_manager._mock_session_manager
        ):
            mock_dialog.injection_manager = injection_manager
            mock_dialog.extraction_vram_offset = None

            mock_dialog._restore_saved_sprite_location()

        # Verify correct index was selected (index 2 for "Helper Sprite")
        mock_dialog.sprite_location_combo.setCurrentIndex.assert_called_with(2)

    def test_settings_namespace_consistency(self, settings_manager):
        """Test that all ROM injection settings use consistent namespace"""
        # Save various settings
        settings_manager.set_value(
            SETTINGS_NS_ROM_INJECTION, SETTINGS_KEY_LAST_INPUT_ROM, "/test.sfc"
        )
        settings_manager.set_value(
            SETTINGS_NS_ROM_INJECTION, SETTINGS_KEY_LAST_INPUT_VRAM, "/test.dmp"
        )
        settings_manager.save()

        # Verify namespace structure in raw settings
        raw_settings = settings_manager._get_settings()
        assert SETTINGS_NS_ROM_INJECTION in raw_settings
        rom_injection_settings = raw_settings[SETTINGS_NS_ROM_INJECTION]

        assert SETTINGS_KEY_LAST_INPUT_ROM in rom_injection_settings
        assert SETTINGS_KEY_LAST_INPUT_VRAM in rom_injection_settings

        # Verify old namespace is not used
        assert (
            "injection" not in raw_settings
            or SETTINGS_KEY_LAST_INPUT_ROM not in raw_settings.get("injection", {})
        )
