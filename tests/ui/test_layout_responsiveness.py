from unittest.mock import MagicMock, Mock, patch

import pytest
from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import QLabel, QScrollArea, QSplitter, QTabWidget, QVBoxLayout, QWidget

from ui.managers.ui_coordinator import UICoordinator
from ui.sprite_editor.views.tabs.edit_tab import EditTab
from ui.sprite_editor.views.tabs.extract_tab import ExtractTab
from ui.sprite_editor.views.tabs.inject_tab import InjectTab
from ui.sprite_editor.views.widgets.pixel_canvas import PixelCanvas


class MockPanel(QWidget):
    # Signals needed for connections
    toolChanged = Signal(str)
    brushSizeChanged = Signal(int)
    colorSelected = Signal(object)
    gridToggled = Signal(bool)
    paletteToggled = Signal(bool)
    zoomChanged = Signal(int)
    zoomToFit = Signal()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.set_tool = Mock()
        self.set_brush_size = Mock()
        self.set_selected_color = Mock()
        self.set_palette = Mock()
        self.set_zoom = Mock()
        self.update_preview = Mock()
        self.update_color_preview = Mock()
        self._controller = None

    @property
    def controller(self):
        return self._controller

    @controller.setter
    def controller(self, value):
        self._controller = value


class TestLayoutResponsiveness:
    @pytest.fixture
    def mock_dependencies(self, qt_app):
        # ... existing fixture ...
        main_window = Mock()
        # Use a real QSplitter to allow testing sizes
        main_window.main_splitter = QSplitter()
        main_window.main_splitter.addWidget(QWidget())
        main_window.main_splitter.addWidget(QWidget())
        main_window.main_splitter.setSizes([500, 500])

        sprite_preview = Mock()
        palette_preview = Mock()
        extraction_panel = Mock()
        output_settings_manager = Mock()
        session_manager = Mock()
        extraction_tabs = QTabWidget()
        extraction_tabs.addTab(QWidget(), "ROM")
        extraction_tabs.addTab(QWidget(), "VRAM")
        extraction_tabs.addTab(QWidget(), "Editor")

        rom_extraction_panel = Mock()
        toolbar_manager = Mock()
        actions_handler = Mock()

        # Stub specific methods needed for _configure_* methods
        actions_handler.get_rom_extraction_params.return_value = None
        actions_handler.is_vram_extraction_ready.return_value = False
        actions_handler.is_grayscale_mode.return_value = False

        return {
            "main_window": main_window,
            "sprite_preview": sprite_preview,
            "palette_preview": palette_preview,
            "extraction_panel": extraction_panel,
            "output_settings_manager": output_settings_manager,
            "session_manager": session_manager,
            "extraction_tabs": extraction_tabs,
            "rom_extraction_panel": rom_extraction_panel,
            "toolbar_manager": toolbar_manager,
            "actions_handler": actions_handler,
        }

    def test_layout_collapse_restore(self, mock_dependencies):
        # ... existing test ...
        deps = mock_dependencies
        coordinator = UICoordinator(
            deps["sprite_preview"],
            deps["palette_preview"],
            deps["main_window"],
            deps["extraction_panel"],
            deps["output_settings_manager"],
            deps["session_manager"],
            deps["extraction_tabs"],
            deps["rom_extraction_panel"],
            deps["toolbar_manager"],
            deps["actions_handler"],
        )

        splitter = deps["main_window"].main_splitter
        initial_sizes = splitter.sizes()
        assert initial_sizes[0] > 0
        assert initial_sizes[1] > 0

        coordinator._on_extraction_tab_changed(2)

        current_sizes = splitter.sizes()
        assert current_sizes[1] == 0, "Right panel should be collapsed"
        assert len(coordinator._saved_splitter_sizes) > 0, "Should have saved sizes"

        coordinator._on_extraction_tab_changed(0)

        restored_sizes = splitter.sizes()
        assert restored_sizes[1] > 0, "Layout should be restored"
        assert coordinator._saved_splitter_sizes == [], "Saved sizes should be cleared"

    def test_canvas_responsiveness(self, qt_app):
        # ... existing test ...
        with (
            patch("ui.sprite_editor.views.tabs.edit_tab.ToolPanel", MockPanel),
            patch("ui.sprite_editor.views.tabs.edit_tab.PalettePanel", MockPanel),
            patch("ui.sprite_editor.views.tabs.edit_tab.OptionsPanel", MockPanel),
            patch("ui.sprite_editor.views.tabs.edit_tab.PreviewPanel", MockPanel),
        ):
            edit_tab = EditTab()

            assert edit_tab.scroll_area.widgetResizable() is True, "Scroll area should be resizable"

            container = edit_tab.scroll_area.widget()
            assert isinstance(container, QWidget)
            layout = container.layout()
            assert isinstance(layout, QVBoxLayout)
            # No alignment set allows scroll area's widgetResizable to handle expansion
            assert layout.alignment() == Qt.AlignmentFlag(0)

            assert layout.count() == 1

            mock_controller = MagicMock()
            mock_controller.get_image_size.return_value = (100, 100)
            mock_controller.has_image.return_value = True
            mock_controller.tool_manager.get_brush_size.return_value = 1

            edit_tab.set_controller(mock_controller)

            canvas = edit_tab.get_canvas()
            assert isinstance(canvas, PixelCanvas)
            assert layout.indexOf(canvas) != -1

            canvas.zoom = 4
            hint = canvas.sizeHint()
            assert hint.width() == 400
            assert hint.height() == 400

    def test_text_readability_layout(self, qt_app):
        """Verify layout changes for text readability."""
        # Test ExtractTab hint labels
        extract_tab = ExtractTab()

        # Find hint labels (looking for text content)
        offset_hint = None
        size_hint = None
        for child in extract_tab.findChildren(QLabel):
            if "VRAM $6000" in child.text():
                offset_hint = child
            elif "16KB" in child.text():
                size_hint = child

        assert offset_hint is not None, "Offset hint not found"
        assert offset_hint.wordWrap() is True, "Offset hint should wrap"

        assert size_hint is not None, "Size hint not found"
        assert size_hint.wordWrap() is True, "Size hint should wrap"

        # Test InjectTab output hint
        inject_tab = InjectTab()
        output_hint = inject_tab.output_hint

        assert output_hint.wordWrap() is True, "Output hint should wrap"
        # Verify it's in the layout (hard to check row/col spanning via findChildren alone without layout inspection)
        # But checking wordWrap confirms the property set.
