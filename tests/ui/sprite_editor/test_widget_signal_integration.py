#!/usr/bin/env python3
"""
Integration tests for UI redesign signal chains (Task 5.2).

Tests verify end-to-end signal flows between widgets and controllers:
- Asset browser → controller → canvas
- Mesen2 capture ingestion
- Palette source changes
- Asset rename persistence
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING
from unittest.mock import Mock, patch

from PySide6.QtCore import QCoreApplication

if TYPE_CHECKING:
    from pytestqt.qtbot import QtBot


class TestAssetBrowserControllerIntegration:
    """Integration tests for AssetBrowserController with SpriteAssetBrowser."""

    def test_browser_selection_emits_controller_signal(self, qtbot: QtBot) -> None:
        """Verify sprite_selected signal flows: browser widget → controller."""
        from ui.sprite_editor.controllers.asset_browser_controller import AssetBrowserController
        from ui.sprite_editor.views.widgets.sprite_asset_browser import SpriteAssetBrowser

        # Create browser and controller
        browser = SpriteAssetBrowser()
        controller = AssetBrowserController()
        qtbot.addWidget(browser)

        # Connect controller to browser
        controller.set_browser(browser)

        # Add a sprite
        controller.add_rom_sprite("Test Kirby", 0x100000)
        QCoreApplication.processEvents()

        # Spy on controller signal
        signal_spy = Mock()
        controller.spriteSelected.connect(signal_spy)

        # Select sprite in browser
        browser.select_sprite_by_offset(0x100000)
        QCoreApplication.processEvents()

        # Verify signal propagated through controller
        signal_spy.assert_called_with(0x100000, "rom")

    def test_mesen_capture_ingestion(self, qtbot: QtBot) -> None:
        """Verify Mesen2 capture adds to browser via controller."""
        from core.mesen_integration.log_watcher import CapturedOffset
        from ui.sprite_editor.controllers.asset_browser_controller import AssetBrowserController
        from ui.sprite_editor.views.widgets.sprite_asset_browser import SpriteAssetBrowser

        # Create browser and controller
        browser = SpriteAssetBrowser()
        controller = AssetBrowserController()
        qtbot.addWidget(browser)

        controller.set_browser(browser)

        # Create mock capture (using actual CapturedOffset signature)
        capture = CapturedOffset(
            offset=0x284000,
            frame=1500,
            timestamp=datetime(2025, 1, 7, 12, 30, 45, tzinfo=UTC),
            raw_line="DMA: 0x284000",
        )

        # Spy on captureAdded signal
        capture_spy = Mock()
        controller.captureAdded.connect(capture_spy)

        # Add capture
        controller.add_mesen_capture(capture)
        QCoreApplication.processEvents()

        # Verify signal emitted
        capture_spy.assert_called_once()
        call_args = capture_spy.call_args[0]
        assert call_args[0] == 0x284000
        assert "0x284000" in call_args[1].upper() or "284000" in call_args[1].upper()

        # Verify browser updated
        counts = browser.get_item_count()
        assert counts[SpriteAssetBrowser.CATEGORY_MESEN] == 1

    def test_mesen_capture_deduplication(self, qtbot: QtBot) -> None:
        """Verify duplicate Mesen2 captures are not added twice."""
        from core.mesen_integration.log_watcher import CapturedOffset
        from ui.sprite_editor.controllers.asset_browser_controller import AssetBrowserController
        from ui.sprite_editor.views.widgets.sprite_asset_browser import SpriteAssetBrowser

        # Create browser and controller
        browser = SpriteAssetBrowser()
        controller = AssetBrowserController()
        qtbot.addWidget(browser)

        controller.set_browser(browser)

        # Create capture (using actual CapturedOffset signature)
        capture = CapturedOffset(
            offset=0x200000,
            frame=1000,
            timestamp=datetime.now(),
            raw_line="DMA: 0x200000",
        )

        # Add twice
        controller.add_mesen_capture(capture)
        controller.add_mesen_capture(capture)
        QCoreApplication.processEvents()

        # Should only have one
        counts = browser.get_item_count()
        assert counts[SpriteAssetBrowser.CATEGORY_MESEN] == 1


class TestAssetRenamePersistence:
    """Tests for asset rename persistence via QSettings."""

    def test_rename_updates_controller_metadata(self, qtbot: QtBot) -> None:
        """Verify renamed assets update controller metadata."""
        from ui.sprite_editor.controllers.asset_browser_controller import AssetBrowserController
        from ui.sprite_editor.views.widgets.sprite_asset_browser import SpriteAssetBrowser

        # Create browser and controller
        browser = SpriteAssetBrowser()
        controller = AssetBrowserController()
        qtbot.addWidget(browser)

        controller.set_browser(browser)
        controller.set_rom_hash("test_rom_hash_12345")

        # Add sprite
        controller.add_rom_sprite("Original Name", 0x123456)
        QCoreApplication.processEvents()

        # Rename
        controller.rename_asset(0x123456, "rom", "Renamed Kirby")
        QCoreApplication.processEvents()

        # Verify name updated in controller metadata
        assert controller.get_asset_name(0x123456, "rom") == "Renamed Kirby"

    def test_rename_calls_save_method(self, qtbot: QtBot) -> None:
        """Verify rename_asset calls save_asset_name for persistence."""
        from ui.sprite_editor.controllers.asset_browser_controller import AssetBrowserController
        from ui.sprite_editor.views.widgets.sprite_asset_browser import SpriteAssetBrowser

        # Create browser and controller
        browser = SpriteAssetBrowser()
        controller = AssetBrowserController()
        qtbot.addWidget(browser)

        controller.set_browser(browser)
        controller.set_rom_hash("test_rom_hash")

        # Add sprite
        controller.add_rom_sprite("Original", 0x100000)
        QCoreApplication.processEvents()

        # Mock save method
        with patch.object(controller, "save_asset_name") as mock_save:
            controller.rename_asset(0x100000, "rom", "New Name")

            mock_save.assert_called_once_with(0x100000, "rom", "New Name")

    def test_get_asset_name_returns_none_for_unknown(self, qtbot: QtBot) -> None:
        """Verify get_asset_name returns None for unknown assets."""
        from ui.sprite_editor.controllers.asset_browser_controller import AssetBrowserController

        controller = AssetBrowserController()

        # Should return None for non-existent asset
        assert controller.get_asset_name(0xFFFFFF, "rom") is None


class TestIconToolbarControllerIntegration:
    """Integration tests for IconToolbar with EditingController."""

    def test_toolbar_tool_change_updates_controller(self, qtbot: QtBot) -> None:
        """Verify tool changes in toolbar update controller state."""
        from ui.sprite_editor.controllers.editing_controller import EditingController
        from ui.sprite_editor.views.widgets.icon_toolbar import IconToolbar

        # Create toolbar and controller
        toolbar = IconToolbar()
        controller = EditingController()
        qtbot.addWidget(toolbar)

        # Connect toolbar signal to controller
        toolbar.toolChanged.connect(controller.set_tool)

        # Change tool via toolbar
        toolbar.tool_buttons["fill"].click()
        QCoreApplication.processEvents()

        # Verify controller updated
        assert controller.get_current_tool_name() == "fill"

    def test_controller_tool_change_updates_toolbar(self, qtbot: QtBot) -> None:
        """Verify controller tool changes update toolbar (via signal)."""
        from ui.sprite_editor.controllers.editing_controller import EditingController
        from ui.sprite_editor.views.widgets.icon_toolbar import IconToolbar

        # Create toolbar and controller
        toolbar = IconToolbar()
        controller = EditingController()
        qtbot.addWidget(toolbar)

        # Connect controller signal to toolbar
        controller.toolChanged.connect(toolbar.set_tool)

        # Change tool via controller
        controller.set_tool("picker")
        QCoreApplication.processEvents()

        # Verify toolbar updated (no signal loop due to QSignalBlocker)
        assert toolbar.get_current_tool() == "picker"


class TestPaletteSourceIntegration:
    """Integration tests for PaletteSourceSelector signal flows."""

    def test_palette_source_change_signal_chain(self, qtbot: QtBot) -> None:
        """Verify palette source changes emit signals correctly."""
        from ui.sprite_editor.views.widgets.palette_source_selector import PaletteSourceSelector

        selector = PaletteSourceSelector()
        qtbot.addWidget(selector)

        # Add mesen source
        selector.add_palette_source("Mesen Palette 2", "mesen", 2)

        # Spy on signal
        signal_spy = Mock()
        selector.sourceChanged.connect(signal_spy)

        # Change selection using public API
        selector.set_selected_source("mesen", 2)
        QCoreApplication.processEvents()

        # Verify signal chain
        signal_spy.assert_called_with("mesen", 2)


class TestContextualPreviewIntegration:
    """Integration tests for ContextualPreview with image updates."""

    def test_preview_updates_with_controller_image(self, qtbot: QtBot) -> None:
        """Verify preview updates when image is provided."""
        from PySide6.QtGui import QImage

        from ui.sprite_editor.views.widgets.contextual_preview import ContextualPreview

        preview = ContextualPreview()
        qtbot.addWidget(preview)

        # Create test image (16x16 SNES sprite size)
        image = QImage(16, 16, QImage.Format.Format_ARGB32)
        image.fill(0xFFFF0000)  # Red

        # Update preview
        preview.update_preview(image)
        QCoreApplication.processEvents()

        # Verify image stored using public API
        assert preview.has_preview()
        assert preview.get_preview_size() == (16, 16)


class TestSaveExportPanelIntegration:
    """Integration tests for SaveExportPanel signal flows."""

    def test_save_button_enables_with_modified_image(self, qtbot: QtBot) -> None:
        """Verify save button can be enabled when image is modified."""
        from ui.sprite_editor.views.widgets.save_export_panel import SaveExportPanel

        panel = SaveExportPanel()
        qtbot.addWidget(panel)

        # Initially disabled
        assert not panel.save_to_rom_btn.isEnabled()

        # Simulate image modification
        panel.set_save_enabled(True)
        panel.set_export_enabled(True)
        QCoreApplication.processEvents()

        # Verify enabled
        assert panel.save_to_rom_btn.isEnabled()
        assert panel.export_png_btn.isEnabled()

    def test_save_signal_chain(self, qtbot: QtBot) -> None:
        """Verify save button click emits signal for controller handling."""
        from ui.sprite_editor.views.widgets.save_export_panel import SaveExportPanel

        panel = SaveExportPanel()
        qtbot.addWidget(panel)

        # Enable and connect
        panel.set_save_enabled(True)

        signal_spy = Mock()
        panel.saveToRomClicked.connect(signal_spy)

        # Click save
        panel.save_to_rom_btn.click()
        QCoreApplication.processEvents()

        signal_spy.assert_called_once()


class TestEditorStatusBarIntegration:
    """Integration tests for EditorStatusBar with canvas events."""

    def test_status_bar_updates_from_canvas_hover(self, qtbot: QtBot) -> None:
        """Verify status bar updates when receiving canvas hover data."""
        from ui.sprite_editor.views.widgets.editor_status_bar import EditorStatusBar

        status_bar = EditorStatusBar()
        qtbot.addWidget(status_bar)

        # Simulate canvas hover update
        status_bar.update_cursor(8, 12)
        status_bar.update_tile(0x2A)
        status_bar.update_address(0x284000)
        status_bar.update_color((255, 128, 64))
        QCoreApplication.processEvents()

        # Verify all fields updated
        assert "8" in status_bar.cursor_label.text()
        assert "12" in status_bar.cursor_label.text()
        assert "2A" in status_bar.tile_label.text().upper()
        assert "284000" in status_bar.address_label.text().upper()
        assert status_bar.get_current_color() == (255, 128, 64)


class TestEditTabPanelAccess:
    """Tests for EditTab property access to new widgets."""

    def test_edit_tab_exposes_icon_toolbar(self, qtbot: QtBot) -> None:
        """Verify EditTab.icon_toolbar property returns IconToolbar."""
        from ui.sprite_editor.views.tabs.edit_tab import EditTab
        from ui.sprite_editor.views.widgets.icon_toolbar import IconToolbar

        tab = EditTab()
        qtbot.addWidget(tab)

        assert hasattr(tab, "icon_toolbar")
        assert isinstance(tab.icon_toolbar, IconToolbar)

    def test_edit_tab_exposes_palette_panel(self, qtbot: QtBot) -> None:
        """Verify EditTab.palette_panel property returns PalettePanel."""
        from ui.sprite_editor.views.panels.palette_panel import PalettePanel
        from ui.sprite_editor.views.tabs.edit_tab import EditTab

        tab = EditTab()
        qtbot.addWidget(tab)

        assert hasattr(tab, "palette_panel")
        assert isinstance(tab.palette_panel, PalettePanel)

    def test_edit_tab_exposes_preview_panel(self, qtbot: QtBot) -> None:
        """Verify EditTab.preview_panel property returns PreviewPanel."""
        from ui.sprite_editor.views.panels.preview_panel import PreviewPanel
        from ui.sprite_editor.views.tabs.edit_tab import EditTab

        tab = EditTab()
        qtbot.addWidget(tab)

        assert hasattr(tab, "preview_panel")
        assert isinstance(tab.preview_panel, PreviewPanel)


class TestFullSignalChain:
    """End-to-end tests for complete signal chains."""

    def test_edit_tab_controller_bidirectional_sync(self, qtbot: QtBot) -> None:
        """Verify bidirectional sync between EditTab and EditingController."""
        from ui.sprite_editor.controllers.editing_controller import EditingController
        from ui.sprite_editor.views.tabs.edit_tab import EditTab

        # Create controller and tab
        controller = EditingController()
        tab = EditTab()
        qtbot.addWidget(tab)

        # Connect controller to tab
        tab.set_controller(controller)
        QCoreApplication.processEvents()

        # Change tool via controller
        controller.set_tool("fill")
        QCoreApplication.processEvents()

        # Verify tab toolbar synced
        assert tab.icon_toolbar.get_current_tool() == "fill"

        # Change color via controller
        controller.set_selected_color(7)
        QCoreApplication.processEvents()

        # Verify palette panel synced
        assert tab.palette_panel.get_selected_color() == 7

    def test_asset_browser_to_offset_flow(self, qtbot: QtBot) -> None:
        """Verify selecting asset in browser can trigger offset change."""
        from ui.sprite_editor.controllers.asset_browser_controller import AssetBrowserController
        from ui.sprite_editor.views.widgets.sprite_asset_browser import SpriteAssetBrowser

        # Create components
        browser = SpriteAssetBrowser()
        controller = AssetBrowserController()
        qtbot.addWidget(browser)

        controller.set_browser(browser)

        # Add sprites
        controller.add_rom_sprite("Sprite 1", 0x100000)
        controller.add_rom_sprite("Sprite 2", 0x200000)
        controller.add_rom_sprite("Sprite 3", 0x300000)
        QCoreApplication.processEvents()

        # Mock offset handler
        offset_handler = Mock()
        controller.spriteSelected.connect(offset_handler)

        # Select second sprite
        browser.select_sprite_by_offset(0x200000)
        QCoreApplication.processEvents()

        # Verify offset handler called
        offset_handler.assert_called_with(0x200000, "rom")
