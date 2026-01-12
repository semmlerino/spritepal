#!/usr/bin/env python3
"""
Unit tests for UI redesign widgets (Task 5.1).

Tests verify signal emission, state management, and basic functionality
of widgets created during the UI redesign.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import Mock

from PySide6.QtCore import QCoreApplication, Qt
from PySide6.QtGui import QImage

if TYPE_CHECKING:
    from pytestqt.qtbot import QtBot


class TestSpriteAssetBrowser:
    """Tests for SpriteAssetBrowser widget."""

    def test_categories_created_on_init(self, qtbot: QtBot) -> None:
        """Verify three categories are created on initialization."""
        from ui.sprite_editor.views.widgets.sprite_asset_browser import SpriteAssetBrowser

        browser = SpriteAssetBrowser()
        qtbot.addWidget(browser)

        counts = browser.get_item_count()
        assert SpriteAssetBrowser.CATEGORY_ROM in counts
        assert SpriteAssetBrowser.CATEGORY_MESEN in counts
        assert SpriteAssetBrowser.CATEGORY_LOCAL in counts

    def test_add_rom_sprite(self, qtbot: QtBot) -> None:
        """Verify ROM sprites can be added to browser."""
        from ui.sprite_editor.views.widgets.sprite_asset_browser import SpriteAssetBrowser

        browser = SpriteAssetBrowser()
        qtbot.addWidget(browser)

        browser.add_rom_sprite("Test Sprite", 0x123456)
        QCoreApplication.processEvents()

        counts = browser.get_item_count()
        assert counts[SpriteAssetBrowser.CATEGORY_ROM] == 1

    def test_add_mesen_capture(self, qtbot: QtBot) -> None:
        """Verify Mesen2 captures can be added to browser."""
        from ui.sprite_editor.views.widgets.sprite_asset_browser import SpriteAssetBrowser

        browser = SpriteAssetBrowser()
        qtbot.addWidget(browser)

        browser.add_mesen_capture("Captured Sprite", 0x789ABC)
        QCoreApplication.processEvents()

        counts = browser.get_item_count()
        assert counts[SpriteAssetBrowser.CATEGORY_MESEN] == 1

    def test_add_local_file(self, qtbot: QtBot) -> None:
        """Verify local files can be added to browser."""
        from ui.sprite_editor.views.widgets.sprite_asset_browser import SpriteAssetBrowser

        browser = SpriteAssetBrowser()
        qtbot.addWidget(browser)

        browser.add_local_file("local_sprite.png", "/path/to/local_sprite.png")
        QCoreApplication.processEvents()

        counts = browser.get_item_count()
        assert counts[SpriteAssetBrowser.CATEGORY_LOCAL] == 1

    def test_sprite_selected_signal(self, qtbot: QtBot) -> None:
        """Verify sprite_selected signal emits offset and source_type."""
        from ui.sprite_editor.views.widgets.sprite_asset_browser import SpriteAssetBrowser

        browser = SpriteAssetBrowser()
        qtbot.addWidget(browser)

        # Add a sprite
        browser.add_rom_sprite("Test Sprite", 0x123456)
        QCoreApplication.processEvents()

        # Connect signal spy
        signal_spy = Mock()
        browser.sprite_selected.connect(signal_spy)

        # Select the sprite
        rom_category = browser._rom_category
        sprite_item = rom_category.child(0)
        browser.tree.setCurrentItem(sprite_item)
        QCoreApplication.processEvents()

        # Verify signal emitted with correct args
        signal_spy.assert_called_once_with(0x123456, "rom")

    def test_search_filters_items(self, qtbot: QtBot) -> None:
        """Verify search bar filters visible items."""
        from ui.sprite_editor.views.widgets.sprite_asset_browser import SpriteAssetBrowser

        browser = SpriteAssetBrowser()
        qtbot.addWidget(browser)

        # Add multiple sprites
        browser.add_rom_sprite("Kirby", 0x100000)
        browser.add_rom_sprite("Waddle Dee", 0x200000)
        browser.add_rom_sprite("King Dedede", 0x300000)
        QCoreApplication.processEvents()

        # Search for "Kirby"
        browser.filter_items("Kirby")
        QCoreApplication.processEvents()

        # Count visible items
        visible_count = 0
        rom_category = browser._rom_category
        for i in range(rom_category.childCount()):
            if not rom_category.child(i).isHidden():
                visible_count += 1

        assert visible_count == 1, "Only 'Kirby' should be visible"

    def test_clear_all(self, qtbot: QtBot) -> None:
        """Verify clear_all removes all items from all categories."""
        from ui.sprite_editor.views.widgets.sprite_asset_browser import SpriteAssetBrowser

        browser = SpriteAssetBrowser()
        qtbot.addWidget(browser)

        # Add items to each category
        browser.add_rom_sprite("ROM Sprite", 0x100000)
        browser.add_mesen_capture("Mesen Capture", 0x200000)
        browser.add_local_file("Local File", "/path/to/file.png")
        QCoreApplication.processEvents()

        # Clear all
        browser.clear_all()
        QCoreApplication.processEvents()

        # Verify all categories empty
        counts = browser.get_item_count()
        assert counts[SpriteAssetBrowser.CATEGORY_ROM] == 0
        assert counts[SpriteAssetBrowser.CATEGORY_MESEN] == 0
        assert counts[SpriteAssetBrowser.CATEGORY_LOCAL] == 0

    def test_select_sprite_by_offset(self, qtbot: QtBot) -> None:
        """Verify sprite can be selected by offset."""
        from ui.sprite_editor.views.widgets.sprite_asset_browser import SpriteAssetBrowser

        browser = SpriteAssetBrowser()
        qtbot.addWidget(browser)

        # Add sprites
        browser.add_rom_sprite("First", 0x100000)
        browser.add_rom_sprite("Second", 0x200000)
        browser.add_rom_sprite("Third", 0x300000)
        QCoreApplication.processEvents()

        # Select by offset
        found = browser.select_sprite_by_offset(0x200000)

        assert found, "Sprite should be found"
        current = browser.tree.currentItem()
        assert current is not None
        assert current.text(0) == "Second"

    def test_update_mesen_capture_offset(self, qtbot: QtBot) -> None:
        """Asset browser updates Mesen capture offset after alignment adjustment."""
        from ui.sprite_editor.views.widgets.sprite_asset_browser import SpriteAssetBrowser

        browser = SpriteAssetBrowser()
        qtbot.addWidget(browser)

        # Add capture at original offset
        browser.add_mesen_capture("Test Capture", 0x100)
        QCoreApplication.processEvents()
        assert browser.has_mesen_capture(0x100)
        assert not browser.has_mesen_capture(0x102)

        # Update offset (simulating alignment adjustment)
        result = browser.update_mesen_capture_offset(0x100, 0x102)

        assert result is True
        assert not browser.has_mesen_capture(0x100)  # Old offset gone
        assert browser.has_mesen_capture(0x102)  # New offset present

    def test_update_mesen_capture_offset_not_found(self, qtbot: QtBot) -> None:
        """Asset browser returns False when updating non-existent capture."""
        from ui.sprite_editor.views.widgets.sprite_asset_browser import SpriteAssetBrowser

        browser = SpriteAssetBrowser()
        qtbot.addWidget(browser)

        # Try to update non-existent capture
        result = browser.update_mesen_capture_offset(0x100, 0x102)

        assert result is False


class TestIconToolbar:
    """Tests for IconToolbar widget."""

    def test_pencil_selected_by_default(self, qtbot: QtBot) -> None:
        """Verify pencil tool is selected by default."""
        from ui.sprite_editor.views.widgets.icon_toolbar import IconToolbar

        toolbar = IconToolbar()
        qtbot.addWidget(toolbar)

        assert toolbar.get_current_tool() == "pencil"

    def test_tool_selection_mutually_exclusive(self, qtbot: QtBot) -> None:
        """Verify only one tool can be selected at a time."""
        from ui.sprite_editor.views.widgets.icon_toolbar import IconToolbar

        toolbar = IconToolbar()
        qtbot.addWidget(toolbar)

        # Select fill tool
        toolbar.tool_buttons["fill"].click()
        QCoreApplication.processEvents()

        assert toolbar.get_current_tool() == "fill"
        assert not toolbar.tool_buttons["pencil"].isChecked()
        assert toolbar.tool_buttons["fill"].isChecked()
        assert not toolbar.tool_buttons["picker"].isChecked()
        assert not toolbar.tool_buttons["eraser"].isChecked()

    def test_tool_changed_signal(self, qtbot: QtBot) -> None:
        """Verify toolChanged signal emits tool name."""
        from ui.sprite_editor.views.widgets.icon_toolbar import IconToolbar

        toolbar = IconToolbar()
        qtbot.addWidget(toolbar)

        signal_spy = Mock()
        toolbar.toolChanged.connect(signal_spy)

        # Click picker tool
        toolbar.tool_buttons["picker"].click()
        QCoreApplication.processEvents()

        signal_spy.assert_called_with("picker")

    def test_set_tool_blocks_signal(self, qtbot: QtBot) -> None:
        """Verify set_tool() does not emit signal (QSignalBlocker)."""
        from ui.sprite_editor.views.widgets.icon_toolbar import IconToolbar

        toolbar = IconToolbar()
        qtbot.addWidget(toolbar)

        signal_spy = Mock()
        toolbar.toolChanged.connect(signal_spy)

        # Programmatic update should not emit
        toolbar.set_tool("eraser")
        QCoreApplication.processEvents()

        assert toolbar.get_current_tool() == "eraser"
        signal_spy.assert_not_called()

    def test_zoom_signals(self, qtbot: QtBot) -> None:
        """Verify zoom buttons emit signals."""
        from ui.sprite_editor.views.widgets.icon_toolbar import IconToolbar

        toolbar = IconToolbar()
        qtbot.addWidget(toolbar)

        zoom_in_spy = Mock()
        zoom_out_spy = Mock()
        toolbar.zoomInClicked.connect(zoom_in_spy)
        toolbar.zoomOutClicked.connect(zoom_out_spy)

        # Click zoom buttons
        toolbar.zoom_in_btn.click()
        toolbar.zoom_out_btn.click()
        QCoreApplication.processEvents()

        zoom_in_spy.assert_called_once()
        zoom_out_spy.assert_called_once()

    def test_grid_toggle_signals(self, qtbot: QtBot) -> None:
        """Verify grid toggle buttons emit signals with checked state."""
        from ui.sprite_editor.views.widgets.icon_toolbar import IconToolbar

        toolbar = IconToolbar()
        qtbot.addWidget(toolbar)

        grid_spy = Mock()
        tile_grid_spy = Mock()
        toolbar.gridToggled.connect(grid_spy)
        toolbar.tileGridToggled.connect(tile_grid_spy)

        # Toggle grids
        toolbar.grid_btn.click()
        toolbar.tile_grid_btn.click()
        QCoreApplication.processEvents()

        grid_spy.assert_called_with(True)
        tile_grid_spy.assert_called_with(True)

    def test_all_tool_buttons_exist(self, qtbot: QtBot) -> None:
        """Verify all expected tool buttons are created."""
        from ui.sprite_editor.views.widgets.icon_toolbar import IconToolbar

        toolbar = IconToolbar()
        qtbot.addWidget(toolbar)

        expected_tools = ["pencil", "fill", "picker", "eraser"]
        for tool in expected_tools:
            assert tool in toolbar.tool_buttons, f"Tool '{tool}' should exist"


class TestPaletteSourceSelector:
    """Tests for PaletteSourceSelector widget."""

    def test_default_source_exists(self, qtbot: QtBot) -> None:
        """Verify 'Default' source exists on initialization."""
        from ui.sprite_editor.views.widgets.palette_source_selector import PaletteSourceSelector

        selector = PaletteSourceSelector()
        qtbot.addWidget(selector)

        source_type, palette_index = selector.get_selected_source()
        assert source_type == "default"
        assert palette_index == 0

    def test_add_palette_source(self, qtbot: QtBot) -> None:
        """Verify palette sources can be added."""
        from ui.sprite_editor.views.widgets.palette_source_selector import PaletteSourceSelector

        selector = PaletteSourceSelector()
        qtbot.addWidget(selector)

        selector.add_palette_source("Mesen Palette 0", "mesen", 0)
        selector.add_palette_source("Mesen Palette 1", "mesen", 1)

        # Should have 5 items: Default + 2 Mesen + Separator + Manual entry
        assert selector._combo_box.count() == 5

    def test_source_changed_signal(self, qtbot: QtBot) -> None:
        """Verify sourceChanged signal emits source_type and palette_index."""
        from ui.sprite_editor.views.widgets.palette_source_selector import PaletteSourceSelector

        selector = PaletteSourceSelector()
        qtbot.addWidget(selector)

        selector.add_palette_source("Mesen Palette 0", "mesen", 0)

        signal_spy = Mock()
        selector.sourceChanged.connect(signal_spy)

        # Select the mesen source
        selector._combo_box.setCurrentIndex(1)
        QCoreApplication.processEvents()

        signal_spy.assert_called_with("mesen", 0)

    def test_button_signals(self, qtbot: QtBot) -> None:
        """Verify button signals emit correctly."""
        from ui.sprite_editor.views.widgets.palette_source_selector import PaletteSourceSelector

        selector = PaletteSourceSelector()
        qtbot.addWidget(selector)

        load_spy = Mock()
        save_spy = Mock()
        edit_spy = Mock()
        selector.loadPaletteClicked.connect(load_spy)
        selector.savePaletteClicked.connect(save_spy)
        selector.editColorClicked.connect(edit_spy)

        # Click buttons
        selector._load_palette_btn.click()
        selector._save_palette_btn.click()
        selector._edit_color_btn.click()
        QCoreApplication.processEvents()

        load_spy.assert_called_once()
        save_spy.assert_called_once()
        edit_spy.assert_called_once()

    def test_clear_mesen_sources(self, qtbot: QtBot) -> None:
        """Verify clear_mesen_sources keeps only Default and the manual palette entry."""
        from ui.sprite_editor.views.widgets.palette_source_selector import PaletteSourceSelector

        selector = PaletteSourceSelector()
        qtbot.addWidget(selector)

        # Add mesen sources
        selector.add_palette_source("Mesen Palette 0", "mesen", 0)
        selector.add_palette_source("Mesen Palette 1", "mesen", 1)
        # Should have 5 items: Default + 2 Mesen + Separator + Manual entry
        assert selector._combo_box.count() == 5

        # Clear mesen sources
        selector.clear_mesen_sources()

        # Should have 3 items: Default + Separator + Manual entry
        assert selector._combo_box.count() == 3
        source_type, _ = selector.get_selected_source()
        assert source_type == "default"


class TestContextualPreview:
    """Tests for ContextualPreview widget."""

    def test_default_background_checkerboard(self, qtbot: QtBot) -> None:
        """Verify default background is checkerboard."""
        from ui.sprite_editor.views.widgets.contextual_preview import ContextualPreview

        preview = ContextualPreview()
        qtbot.addWidget(preview)

        assert preview.get_background_type() == "checkerboard"

    def test_set_background_black(self, qtbot: QtBot) -> None:
        """Verify background can be set to black."""
        from ui.sprite_editor.views.widgets.contextual_preview import ContextualPreview

        preview = ContextualPreview()
        qtbot.addWidget(preview)

        preview.set_background("black")

        assert preview.get_background_type() == "black"

    def test_set_background_white(self, qtbot: QtBot) -> None:
        """Verify background can be set to white."""
        from ui.sprite_editor.views.widgets.contextual_preview import ContextualPreview

        preview = ContextualPreview()
        qtbot.addWidget(preview)

        preview.set_background("white")

        assert preview.get_background_type() == "white"

    def test_background_changed_signal(self, qtbot: QtBot) -> None:
        """Verify backgroundChanged signal emits background type."""
        from ui.sprite_editor.views.widgets.contextual_preview import ContextualPreview

        preview = ContextualPreview()
        qtbot.addWidget(preview)

        signal_spy = Mock()
        preview.backgroundChanged.connect(signal_spy)

        # Change background via combo box
        preview._background_combo.setCurrentIndex(1)  # Black
        QCoreApplication.processEvents()

        signal_spy.assert_called_with("black")

    def test_update_preview_with_image(self, qtbot: QtBot) -> None:
        """Verify preview updates with image."""
        from ui.sprite_editor.views.widgets.contextual_preview import ContextualPreview

        preview = ContextualPreview()
        qtbot.addWidget(preview)

        # Create test image
        image = QImage(32, 32, QImage.Format.Format_ARGB32)
        image.fill(Qt.GlobalColor.red)

        preview.update_preview(image)

        # Verify image is stored
        assert preview._current_image is not None
        assert not preview._current_image.isNull()

    def test_clear_preview(self, qtbot: QtBot) -> None:
        """Verify clear_preview removes image and shows placeholder."""
        from ui.sprite_editor.views.widgets.contextual_preview import ContextualPreview

        preview = ContextualPreview()
        qtbot.addWidget(preview)

        # Set image first
        image = QImage(32, 32, QImage.Format.Format_ARGB32)
        image.fill(Qt.GlobalColor.blue)
        preview.update_preview(image)

        # Clear
        preview.clear_preview()

        assert preview._current_image is None
        assert preview._preview_label.text() == "No Preview"


class TestSaveExportPanel:
    """Tests for SaveExportPanel widget."""

    def test_buttons_disabled_by_default(self, qtbot: QtBot) -> None:
        """Verify buttons are disabled by default."""
        from ui.sprite_editor.views.widgets.save_export_panel import SaveExportPanel

        panel = SaveExportPanel()
        qtbot.addWidget(panel)

        assert not panel.save_to_rom_btn.isEnabled()
        assert not panel.export_png_btn.isEnabled()

    def test_set_save_enabled(self, qtbot: QtBot) -> None:
        """Verify save button can be enabled."""
        from ui.sprite_editor.views.widgets.save_export_panel import SaveExportPanel

        panel = SaveExportPanel()
        qtbot.addWidget(panel)

        panel.set_save_enabled(True)

        assert panel.save_to_rom_btn.isEnabled()

    def test_set_export_enabled(self, qtbot: QtBot) -> None:
        """Verify export button can be enabled."""
        from ui.sprite_editor.views.widgets.save_export_panel import SaveExportPanel

        panel = SaveExportPanel()
        qtbot.addWidget(panel)

        panel.set_export_enabled(True)

        assert panel.export_png_btn.isEnabled()

    def test_save_signal(self, qtbot: QtBot) -> None:
        """Verify saveToRomClicked signal emits on button click."""
        from ui.sprite_editor.views.widgets.save_export_panel import SaveExportPanel

        panel = SaveExportPanel()
        qtbot.addWidget(panel)

        signal_spy = Mock()
        panel.saveToRomClicked.connect(signal_spy)

        panel.set_save_enabled(True)
        panel.save_to_rom_btn.click()
        QCoreApplication.processEvents()

        signal_spy.assert_called_once()

    def test_export_signal(self, qtbot: QtBot) -> None:
        """Verify exportPngClicked signal emits on button click."""
        from ui.sprite_editor.views.widgets.save_export_panel import SaveExportPanel

        panel = SaveExportPanel()
        qtbot.addWidget(panel)

        signal_spy = Mock()
        panel.exportPngClicked.connect(signal_spy)

        panel.set_export_enabled(True)
        panel.export_png_btn.click()
        QCoreApplication.processEvents()

        signal_spy.assert_called_once()

    def test_size_info_initially_hidden(self, qtbot: QtBot) -> None:
        """Verify size info is hidden by default."""
        from ui.sprite_editor.views.widgets.save_export_panel import SaveExportPanel

        panel = SaveExportPanel()
        qtbot.addWidget(panel)

        assert not panel.size_info_widget.isVisible()

    def test_set_size_info_shows_widget(self, qtbot: QtBot) -> None:
        """Verify set_size_info shows and updates size info widget."""
        from ui.sprite_editor.views.widgets.save_export_panel import SaveExportPanel

        panel = SaveExportPanel()
        qtbot.addWidget(panel)

        panel.set_size_info(1024, 1056)

        # Check widget is not hidden (isVisibleTo checks layout visibility)
        assert not panel.size_info_widget.isHidden()
        assert "1024" in panel.original_size_label.text()
        assert "1056" in panel.modified_size_label.text()


class TestEditorStatusBar:
    """Tests for EditorStatusBar widget."""

    def test_update_cursor(self, qtbot: QtBot) -> None:
        """Verify cursor position updates correctly."""
        from ui.sprite_editor.views.widgets.editor_status_bar import EditorStatusBar

        status_bar = EditorStatusBar()
        qtbot.addWidget(status_bar)

        status_bar.update_cursor(12, 15)

        assert "12" in status_bar.cursor_label.text()
        assert "15" in status_bar.cursor_label.text()

    def test_update_tile(self, qtbot: QtBot) -> None:
        """Verify tile ID updates correctly with hex format."""
        from ui.sprite_editor.views.widgets.editor_status_bar import EditorStatusBar

        status_bar = EditorStatusBar()
        qtbot.addWidget(status_bar)

        status_bar.update_tile(0x45)

        # Check for hex value (case-insensitive)
        assert "45" in status_bar.tile_label.text().upper()
        assert "0X" in status_bar.tile_label.text().upper()

    def test_update_address(self, qtbot: QtBot) -> None:
        """Verify ROM address updates correctly with hex format."""
        from ui.sprite_editor.views.widgets.editor_status_bar import EditorStatusBar

        status_bar = EditorStatusBar()
        qtbot.addWidget(status_bar)

        status_bar.update_address(0x2847C8)

        assert "2847C8" in status_bar.address_label.text().upper()

    def test_update_color(self, qtbot: QtBot) -> None:
        """Verify color preview updates with RGB values."""
        from ui.sprite_editor.views.widgets.editor_status_bar import EditorStatusBar

        status_bar = EditorStatusBar()
        qtbot.addWidget(status_bar)

        status_bar.update_color((255, 128, 64))

        # Check internal state
        assert status_bar._current_color == (255, 128, 64)
        # Check tooltip
        assert "255" in status_bar.color_preview.toolTip()
        assert "128" in status_bar.color_preview.toolTip()
        assert "64" in status_bar.color_preview.toolTip()

    def test_clear_cursor(self, qtbot: QtBot) -> None:
        """Verify clear_cursor shows placeholder text."""
        from ui.sprite_editor.views.widgets.editor_status_bar import EditorStatusBar

        status_bar = EditorStatusBar()
        qtbot.addWidget(status_bar)

        # Set cursor first
        status_bar.update_cursor(10, 20)
        # Clear
        status_bar.clear_cursor()

        assert "--" in status_bar.cursor_label.text()

    def test_tile_id_clamped(self, qtbot: QtBot) -> None:
        """Verify tile ID is clamped to valid range."""
        from ui.sprite_editor.views.widgets.editor_status_bar import EditorStatusBar

        status_bar = EditorStatusBar()
        qtbot.addWidget(status_bar)

        # Try to set out-of-range value
        status_bar.update_tile(300)

        # Should be clamped to 255 (0xFF)
        assert "FF" in status_bar.tile_label.text().upper()

    def test_address_clamped(self, qtbot: QtBot) -> None:
        """Verify address is clamped to 24-bit range."""
        from ui.sprite_editor.views.widgets.editor_status_bar import EditorStatusBar

        status_bar = EditorStatusBar()
        qtbot.addWidget(status_bar)

        # Try to set out-of-range value
        status_bar.update_address(0x1FFFFFF)

        # Should be clamped to 0xFFFFFF
        assert "FFFFFF" in status_bar.address_label.text().upper()
