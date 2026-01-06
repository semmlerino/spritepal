from unittest.mock import MagicMock, Mock, patch

import pytest
from PySide6.QtWidgets import QComboBox, QLineEdit, QPushButton, QWidget

from ui.sprite_edit_tab import SpriteEditTab
from ui.sprite_editor.controllers.main_controller import MainController


class MockTab(QWidget):
    def __init__(self, *args, **kwargs):
        super().__init__()
        self.set_mode = Mock()
        self.set_offset = Mock()
        self.detach_btn = Mock()  # For EditTab check
        self.detach_btn.hide = Mock()
        # Signals
        self.ready_for_inject = Mock()
        self.ready_for_inject.connect = Mock()

        self.extract_requested = Mock()
        self.extract_requested.connect = Mock()
        self.load_rom_requested = Mock()
        self.load_rom_requested.connect = Mock()
        self.browse_vram_requested = Mock()
        self.browse_vram_requested.connect = Mock()
        self.browse_cgram_requested = Mock()
        self.browse_cgram_requested.connect = Mock()
        self.browse_rom_requested = Mock()
        self.browse_rom_requested.connect = Mock()

        self.inject_requested = Mock()
        self.inject_requested.connect = Mock()
        self.save_rom_requested = Mock()
        self.save_rom_requested.connect = Mock()
        self.browse_png_requested = Mock()
        self.browse_png_requested.connect = Mock()

        # ROM Workflow specific
        self.source_bar = Mock()
        self.source_bar.offset_changed = Mock()
        self.source_bar.offset_changed.connect = Mock()
        self.source_bar.action_clicked = Mock()
        self.source_bar.action_clicked.connect = Mock()
        self.source_bar.browse_rom_requested = Mock()
        self.source_bar.browse_rom_requested.connect = Mock()

        self.recent_captures_widget = Mock()
        self.recent_captures_widget.offset_selected = Mock()
        self.recent_captures_widget.offset_selected.connect = Mock()
        self.recent_captures_widget.offset_activated = Mock()
        self.recent_captures_widget.offset_activated.connect = Mock()

        self.prev_btn = Mock()
        self.prev_btn.clicked = Mock()
        self.prev_btn.clicked.connect = Mock()

        self.next_btn = Mock()
        self.next_btn.clicked = Mock()
        self.next_btn.clicked.connect = Mock()

        self.offset_slider = Mock()
        self.offset_slider.valueChanged = Mock()
        self.offset_slider.valueChanged.connect = Mock()

        self.step_spin = Mock()
        self.step_spin.value = Mock(return_value=1)

        # ROM Workflow Tab Layout
        self.edit_tab_layout = Mock()
        self.edit_tab_layout.addWidget = Mock()

        self.main_splitter = Mock()
        self.main_splitter.show = Mock()

        self.left_panel = Mock()
        self.left_panel.show = Mock()

        self.edit_tab_container = Mock()
        self.edit_tab_container.show = Mock()

    def set_extraction_controller(self, ctrl):
        pass

    def set_controller(self, ctrl):
        pass  # For InjectTab


class TestRomModeWorkflow:
    @pytest.fixture
    def mock_app_context(self):
        # Patch get_app_context in all controllers that use it
        with (
            patch("ui.sprite_editor.controllers.extraction_controller.get_app_context") as mock_extract,
            patch("ui.sprite_editor.controllers.rom_workflow_controller.get_app_context") as mock_rom,
            patch("core.app_context.get_app_context") as mock_core,
        ):
            context = MagicMock()
            context.rom_cache = MagicMock()
            context.application_state_manager = MagicMock()
            context.log_watcher = MagicMock()  # Needed for ROMWorkflowController

            mock_extract.return_value = context
            mock_rom.return_value = context
            mock_core.return_value = context

            yield context

    @pytest.fixture
    def sprite_edit_tab(self, qt_app, mock_app_context):
        # Patch internal classes to use MockTab
        with (
            patch("ui.sprite_edit_tab.ExtractTab", MockTab),
            patch("ui.sprite_edit_tab.EditTab", MockTab),
            patch("ui.sprite_edit_tab.InjectTab", MockTab),
            patch("ui.sprite_edit_tab.MultiPaletteTab", MockTab),
            patch("ui.sprite_edit_tab.ROMWorkflowTab", MockTab),
        ):
            tab = SpriteEditTab(settings_manager=mock_app_context.application_state_manager)
            return tab

    def test_mode_switch(self, sprite_edit_tab):
        # Verify mode combo exists
        assert hasattr(sprite_edit_tab, "_mode_combo")
        combo = sprite_edit_tab._mode_combo
        assert isinstance(combo, QComboBox)
        assert combo.count() == 2

        # Test switching to ROM mode
        with patch.object(sprite_edit_tab._controller, "set_mode") as mock_set_mode:
            # Change index to ROM (index 1)
            combo.setCurrentIndex(1)

            # Verify controller was called
            mock_set_mode.assert_called_with("rom")

            # Change back to VRAM (index 0)
            combo.setCurrentIndex(0)
            mock_set_mode.assert_called_with("vram")

    def test_jump_to_offset_switches_mode(self, sprite_edit_tab):
        # Verify jump_to_offset sets mode and offset

        # Mock the controller methods we expect to be called
        sprite_edit_tab._controller.rom_workflow_controller = MagicMock()

        # Call jump_to_offset
        sprite_edit_tab.jump_to_offset(0x123456)

        # Should have switched to ROM mode
        assert sprite_edit_tab._mode_combo.currentData() == "rom"

        # Verify rom workflow controller offset set
        sprite_edit_tab._controller.rom_workflow_controller.set_offset.assert_called_with(0x123456)

    def test_controller_propagates_mode(self, mock_app_context):
        # Test MainController propagation logic
        with patch("ui.sprite_editor.controllers.main_controller.ROMWorkflowController", MagicMock()):
            controller = MainController()
            controller.extraction_controller = MagicMock()
            controller.injection_controller = MagicMock()

            controller.set_mode("rom")

            controller.extraction_controller.set_mode.assert_called_with("rom")
            controller.injection_controller.set_mode.assert_called_with("rom")
