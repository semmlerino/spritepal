import pytest
from unittest.mock import Mock, MagicMock, patch
from PySide6.QtWidgets import QWidget, QComboBox, QPushButton, QLineEdit

from ui.sprite_edit_tab import SpriteEditTab
from ui.sprite_editor.controllers.main_controller import MainController

class MockTab(QWidget):
    def __init__(self, *args, **kwargs):
        super().__init__()
        self.set_mode = Mock()
        self.set_offset = Mock()
        self.detach_btn = Mock() # For EditTab check
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

    def set_extraction_controller(self, ctrl): pass
    def set_controller(self, ctrl): pass # For InjectTab

class TestRomModeWorkflow:
    
    @pytest.fixture
    def mock_app_context(self):
        with patch('ui.sprite_editor.controllers.extraction_controller.get_app_context') as mock_ctx:
            context = MagicMock()
            context.rom_cache = MagicMock()
            context.application_state_manager = MagicMock()
            mock_ctx.return_value = context
            yield context

    @pytest.fixture
    def sprite_edit_tab(self, qt_app, mock_app_context):
        # Patch internal classes to use MockTab
        with patch('ui.sprite_edit_tab.ExtractTab', MockTab) as MockExtract, \
             patch('ui.sprite_edit_tab.EditTab', MockTab) as MockEdit, \
             patch('ui.sprite_edit_tab.InjectTab', MockTab) as MockInject, \
             patch('ui.sprite_edit_tab.MultiPaletteTab', MockTab) as MockMulti:
            
            tab = SpriteEditTab(settings_manager=mock_app_context.application_state_manager)
            return tab

    def test_mode_switch(self, sprite_edit_tab):
        # Verify mode combo exists
        assert hasattr(sprite_edit_tab, "_mode_combo")
        combo = sprite_edit_tab._mode_combo
        assert isinstance(combo, QComboBox)
        assert combo.count() == 2
        
        # Test switching to ROM mode
        with patch.object(sprite_edit_tab._controller, 'set_mode') as mock_set_mode:
            # Change index to ROM (index 1)
            combo.setCurrentIndex(1)
            
            # Verify controller was called
            mock_set_mode.assert_called_with("rom")
            
            # Change back to VRAM (index 0)
            combo.setCurrentIndex(0)
            mock_set_mode.assert_called_with("vram")

    def test_jump_to_offset_switches_mode(self, sprite_edit_tab):
        with patch.object(sprite_edit_tab._controller, 'set_mode') as mock_set_mode:
            # Call jump_to_offset
            sprite_edit_tab.jump_to_offset(0x123456)
            
            # Should have switched to ROM mode (via combo update which triggers signal)
            # Or direct set_mode call. 
            # In code: self.set_mode("rom") -> updates combo -> triggers signal -> controller.set_mode
            
            assert sprite_edit_tab._mode_combo.currentData() == "rom"
            # Verify extract tab offset set
            sprite_edit_tab._extract_tab.set_offset.assert_called_with(0x123456)

    def test_controller_propagates_mode(self, mock_app_context):
        # Test MainController propagation logic
        controller = MainController()
        controller.extraction_controller = MagicMock()
        controller.injection_controller = MagicMock()
        
        controller.set_mode("rom")
        
        controller.extraction_controller.set_mode.assert_called_with("rom")
        controller.injection_controller.set_mode.assert_called_with("rom")
