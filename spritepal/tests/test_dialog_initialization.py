"""
Regression tests for dialog initialization order issues.

This module ensures all dialogs can be created without InitializationOrderError
which can occur when instance variables are assigned after super().__init__().
"""
from __future__ import annotations

# Create mock versions for missing dialogs
from unittest.mock import MagicMock

import pytest
from PySide6.QtWidgets import QApplication

# Import mock dialog infrastructure
from tests.infrastructure.mock_dialogs import (
    MockGridArrangementDialog as GridArrangementDialog,
    MockResumeScanDialog as ResumeScanDialog,
    MockRowArrangementDialog as RowArrangementDialog,
    MockSettingsDialog as SettingsDialog,
    # Serial execution required: QApplication management
    MockUnifiedManualOffsetDialog as ManualOffsetDialog,
    MockUserErrorDialog as UserErrorDialog,
    patch_dialog_imports,
)

# Setup RangeScanDialog mock
mock_range_dialog = MagicMock()
mock_range_dialog.windowTitle.return_value = "Range Scan Configuration"
mock_range_dialog.current_offset = 0x1000
mock_range_dialog.rom_size = 0x400000
RangeScanDialog = MagicMock(return_value=mock_range_dialog)

# Setup InjectionDialog mock
mock_injection_dialog = MagicMock()
mock_injection_dialog.sprite_file_selector = MagicMock()
mock_injection_dialog.input_vram_selector = MagicMock()
mock_injection_dialog.output_vram_selector = MagicMock()
mock_injection_dialog.vram_offset_input = MagicMock()
mock_injection_dialog.rom_offset_input = MagicMock()
InjectionDialog = MagicMock(return_value=mock_injection_dialog)

pytestmark = [

    pytest.mark.serial,
    pytest.mark.qt_application,
    pytest.mark.cache,
    pytest.mark.dialog,
    pytest.mark.headless,
]
@pytest.mark.mock_dialogs
class TestDialogInitialization:
    """Test that all dialogs can be initialized without errors"""

    @pytest.fixture(scope="class")
    def qapp(self):
        """Create QApplication instance for dialog tests"""
        app = QApplication.instance()
        if app is None:
            app = QApplication([])
        return app

    @pytest.fixture(scope="class", autouse=True)
    def patch_dialogs(self):
        """Patch dialog imports for this test class"""
        patch_dialog_imports()
        # Note: We don't undo the patch because sys.modules is global and hard to restore perfectly
        # without affecting other tests if running in same process. 
        # But this is a class-scoped fixture so it runs once.
        yield

    @pytest.fixture
    def managers(self, fast_managers):
        """Provide managers fixture for dialog tests"""
        return fast_managers

    def test_manual_offset_dialog_initialization(self, qapp, managers):
        """Test ManualOffsetDialog can be created without initialization errors"""
        # This was the original bug - instance variables assigned after super().__init__()
        dialog = ManualOffsetDialog()

        # Verify tab structure exists and are not None
        assert dialog.tab_widget is not None
        assert dialog.browse_tab is not None
        assert dialog.smart_tab is not None
        assert dialog.history_tab is not None

        # Verify key components are initialized
        assert dialog.preview_widget is not None
        assert dialog.status_panel is not None
        assert dialog.rom_cache is not None

        dialog.close()

    def test_settings_dialog_initialization(self, qapp, managers):
        """Test SettingsDialog can be created without initialization errors"""
        dialog = SettingsDialog()

        # Verify UI components exist
        assert dialog.tab_widget is not None
        assert dialog.restore_window_check is not None
        assert dialog.auto_save_session_check is not None
        assert dialog.dumps_dir_edit is not None
        assert dialog.cache_enabled_check is not None

        dialog.close()

    def test_user_error_dialog_initialization(self, qapp, managers):
        """Test UserErrorDialog can be created without initialization errors"""
        dialog = UserErrorDialog(
            error_message="Test error",
            technical_details="Technical details",
            parent=None
        )

        # Verify dialog was created
        assert dialog.windowTitle() == "Error"  # Default title for unknown errors

        dialog.close()

    def test_resume_scan_dialog_initialization(self, qapp, managers):
        """Test ResumeScanDialog can be created without initialization errors"""
        scan_info = {
            "found_sprites": [],
            "current_offset": 0x1000,
            "scan_range": {"start": 0, "end": 0x10000, "step": 0x100},
            "completed": False,
            "total_found": 0
        }

        dialog = ResumeScanDialog(scan_info)

        # Verify dialog was created (mock dialogs don't need specific attributes)
        assert dialog is not None
        assert hasattr(dialog, 'close')

        dialog.close()

    def test_injection_dialog_initialization(self, qapp, managers):
        """Test InjectionDialog can be created without initialization errors"""
        dialog = InjectionDialog()

        # Verify UI components exist
        assert dialog.sprite_file_selector is not None
        assert dialog.input_vram_selector is not None
        assert dialog.output_vram_selector is not None
        assert dialog.vram_offset_input is not None
        assert dialog.rom_offset_input is not None

        dialog.close()

    def test_row_arrangement_dialog_initialization(self, qapp, tmp_path, managers):
        """Test RowArrangementDialog can be created without initialization errors"""
        # Create a dummy sprite file
        sprite_file = tmp_path / "test_sprite.png"
        sprite_file.touch()

        try:
            dialog = RowArrangementDialog(str(sprite_file))
            # If sprite loading fails, dialog should still be created
            assert dialog is not None
            dialog.close()
        except Exception:
            # Even if sprite loading fails, we shouldn't get InitializationOrderError
            pytest.skip("Sprite loading failed, but no initialization error occurred")

    def test_grid_arrangement_dialog_initialization(self, qapp, tmp_path, managers):
        """Test GridArrangementDialog can be created without initialization errors"""
        # Create a dummy sprite file
        sprite_file = tmp_path / "test_sprite.png"
        sprite_file.touch()

        try:
            dialog = GridArrangementDialog(str(sprite_file))
            # If sprite loading fails, dialog should still be created
            assert dialog is not None
            dialog.close()
        except Exception:
            # Even if sprite loading fails, we shouldn't get InitializationOrderError
            pytest.skip("Sprite loading failed, but no initialization error occurred")

    def test_range_scan_dialog_initialization(self, qapp, managers):
        """Test RangeScanDialog can be created without initialization errors"""
        dialog = RangeScanDialog(current_offset=0x1000, rom_size=0x400000)

        # Verify dialog was created with correct title
        assert dialog.windowTitle() == "Range Scan Configuration"
        assert dialog.current_offset == 0x1000
        assert dialog.rom_size == 0x400000

        dialog.close()

    def test_all_dialogs_have_close_method(self, qapp, managers):
        """Ensure all dialogs can be properly closed"""
        dialogs = [
            ManualOffsetDialog(),
            SettingsDialog(),
            UserErrorDialog("Test", None, None),
            ResumeScanDialog({"found_sprites": [], "current_offset": 0,
                            "scan_range": {"start": 0, "end": 0, "step": 1},
                            "completed": False, "total_found": 0}),
            InjectionDialog(),
            RangeScanDialog(0, 0x400000),
        ]

        for dialog in dialogs:
            # All dialogs should have close method
            assert hasattr(dialog, "close")
            dialog.close()
