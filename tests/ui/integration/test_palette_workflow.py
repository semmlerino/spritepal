"""
Consolidated Palette Workflow Tests.

This file consolidates all palette-related regression tests from:
- test_palette_association.py (2 tests)
- test_palette_duplication.py (1 test)
- test_palette_integration.py (2 tests)
- test_palette_source_sync.py (3 tests)
- test_palette_sync_full.py (1 test)
- test_rom_palette_workflow.py (3 tests)

Total: 12 tests

The tests are organized by functional area rather than by source file.
Each class contains source attribution in its docstring.
"""

from __future__ import annotations

from unittest.mock import ANY, MagicMock, patch

import numpy as np
import pytest
from PySide6.QtWidgets import QComboBox

from core.sprite_library import LibrarySprite
from ui.sprite_editor import get_default_snes_palette
from ui.sprite_editor.controllers.editing_controller import EditingController
from ui.sprite_editor.controllers.rom_workflow_controller import ROMWorkflowController
from ui.sprite_editor.views.tabs.edit_tab import EditTab
from ui.sprite_editor.views.workspaces.edit_workspace import EditWorkspace

# =============================================================================
# PALETTE ASSOCIATION TESTS
# Source: test_palette_association.py
# =============================================================================


class TestPaletteAssociation:
    """Tests for palette association with sprites via library.

    Source: test_palette_association.py

    Verifies that manually loaded palettes stay associated with sprites.
    """

    def test_palette_association_persistence(self, qtbot):
        """Verify that a manually loaded palette stays associated with a sprite via library."""
        mock_editing_controller = MagicMock()
        mock_rom_extractor = MagicMock()
        mock_sprite_library = MagicMock()
        mock_view = MagicMock()
        mock_workspace = MagicMock()
        mock_palette_panel = MagicMock()
        mock_view.workspace = mock_workspace
        mock_workspace.palette_panel = mock_palette_panel

        mock_sprite_library.compute_rom_hash.return_value = "fake_hash"

        controller = ROMWorkflowController(
            parent=None,
            editing_controller=mock_editing_controller,
            rom_extractor=mock_rom_extractor,
            sprite_library=mock_sprite_library,
        )
        controller.set_view(mock_view)

        controller.rom_path = "test.sfc"
        controller.current_offset = 0x123456
        controller.current_tile_offset = 0x123456  # Must match current_offset
        controller.current_tile_data = b"\x00" * 32
        controller.current_width = 8
        controller.current_height = 8
        controller.current_sprite_name = "test_sprite"

        custom_palette = [(255, 0, 0)] + [(0, 0, 0)] * 15
        custom_source = ("file", 0)
        mock_editing_controller.get_current_colors.return_value = custom_palette
        mock_editing_controller.get_current_palette_source.return_value = custom_source
        mock_editing_controller.palette_model.name = "Custom Palette"

        mock_sprite_library.get_by_offset.return_value = []

        lib_sprite = LibrarySprite(
            rom_offset=0x123456,
            rom_hash="fake_hash",
            name="test_sprite",
            palette_colors=custom_palette,
            palette_name="Custom Palette",
            palette_source=custom_source,
        )
        mock_sprite_library.add_sprite.return_value = lib_sprite

        controller._on_save_to_library(0x123456, "rom")

        mock_sprite_library.add_sprite.assert_called_with(
            rom_offset=0x123456,
            rom_path="test.sfc",
            name=ANY,
            thumbnail=ANY,
            palette_colors=custom_palette,
            palette_name="Custom Palette",
            palette_source=custom_source,
        )

        mock_editing_controller.reset_mock()
        mock_rom_extractor.reset_mock()

        mock_sprite_library.get_by_offset.return_value = [lib_sprite]

        mock_rom_extractor.rom_injector.read_rom_header.return_value = MagicMock()
        mock_rom_extractor.get_palette_config_from_sprite_config.return_value = (0x1000, [8])
        rom_palette = [(0, 255, 0)] * 16
        mock_rom_extractor.extract_palette_range.return_value = {8: rom_palette}

        controller.open_in_editor()

        mock_editing_controller.set_palette.assert_any_call(custom_palette, "Custom Palette")
        mock_editing_controller.set_palette_source.assert_called_with("file", 0)
        mock_editing_controller.register_palette_source.assert_any_call("file", 0, custom_palette, "Custom Palette")

    def test_on_palette_changed_updates_library(self, qtbot):
        """Verify that changing a palette color updates the library association if present."""
        mock_editing_controller = MagicMock()
        mock_sprite_library = MagicMock()

        controller = ROMWorkflowController(
            parent=None, editing_controller=mock_editing_controller, sprite_library=mock_sprite_library
        )

        controller.rom_path = "test.sfc"
        controller.current_offset = 0x123456

        lib_sprite = LibrarySprite(rom_offset=0x123456, rom_hash="fake_hash", name="test_sprite")
        mock_sprite_library.compute_rom_hash.return_value = "fake_hash"
        mock_sprite_library.get_by_offset.return_value = [lib_sprite]

        current_colors = [(10, 20, 30)] * 16
        mock_editing_controller.get_current_colors.return_value = current_colors
        mock_editing_controller.palette_model.name = "My Palette"
        mock_editing_controller.get_current_palette_source.return_value = ("rom", 8)

        controller._on_palette_changed()

        mock_sprite_library.update_sprite.assert_called_with(
            ANY,
            palette_colors=current_colors,
            palette_name="My Palette",
            palette_source=("rom", 8),
        )


# =============================================================================
# PALETTE DUPLICATION TESTS
# Source: test_palette_duplication.py
# =============================================================================


class TestPaletteDuplication:
    """Tests for preventing palette source duplication.

    Source: test_palette_duplication.py

    Ensures ROM palette sources are cleared before registering new ones.
    """

    def test_palette_sources_not_duplicated_on_reopen(self, qtbot):
        """Test that ROM palette sources are cleared before registering new ones,
        preventing duplication when re-opening a sprite.
        """
        editing_controller = EditingController()

        controller = ROMWorkflowController(None, editing_controller)
        controller.rom_path = "dummy.sfc"
        controller.current_tile_data = b"\x00" * 32
        controller.current_tile_offset = 0  # Must match current_offset (defaults to 0)
        controller.current_sprite_name = "test_sprite"

        mock_extractor = MagicMock()
        mock_extractor.read_rom_header.return_value = MagicMock()
        mock_extractor._find_game_configuration.return_value = {"configs": {}}
        mock_extractor.get_palette_config_from_sprite_config.return_value = (0x100, [8])
        mock_extractor.extract_palette_range.return_value = {8: [(0, 0, 0)] * 16}
        controller.rom_extractor = mock_extractor

        controller.open_in_editor()
        sources_1 = editing_controller.get_palette_sources()
        count_1 = len([k for k in sources_1 if k[0] == "rom"])
        assert count_1 > 0

        controller.open_in_editor()
        sources_2 = editing_controller.get_palette_sources()
        count_2 = len([k for k in sources_2 if k[0] == "rom"])

        assert count_1 == count_2


# =============================================================================
# PALETTE INTEGRATION TESTS
# Source: test_palette_integration.py
# =============================================================================


class TestPaletteIntegration:
    """Tests for palette panel signal wiring.

    Source: test_palette_integration.py

    Verifies palette panel signals are correctly wired to controller.
    """

    def test_palette_wiring(self, qtbot):
        """Verify palette panel signals are wired to controller."""
        workspace = EditWorkspace()
        qtbot.addWidget(workspace)

        controller = EditingController()

        controller.handle_load_palette = MagicMock()
        controller.handle_save_palette = MagicMock()
        controller.handle_edit_color = MagicMock()
        controller.handle_palette_source_changed = MagicMock()

        workspace.set_controller(controller)

        workspace.palette_panel.loadPaletteClicked.emit()
        assert controller.handle_load_palette.called

        workspace.palette_panel.savePaletteClicked.emit()
        assert controller.handle_save_palette.called

        workspace.palette_panel.editColorClicked.emit()
        assert controller.handle_edit_color.called

        workspace.palette_panel.sourceChanged.emit("mesen", 1)
        controller.handle_palette_source_changed.assert_called_with("mesen", 1)

    def test_palette_source_update(self, qtbot):
        """Verify controller can update palette sources in view."""
        workspace = EditWorkspace()
        qtbot.addWidget(workspace)
        controller = EditingController()
        workspace.set_controller(controller)

        workspace.palette_panel.add_palette_source = MagicMock()

        workspace.set_controller(controller)

        test_colors = [(255, 0, 0), (0, 255, 0), (0, 0, 255)]
        controller.paletteSourceAdded.emit("New Source", "mesen", 2, test_colors, True)

        workspace.palette_panel.add_palette_source.assert_called_with("New Source", "mesen", 2, test_colors, True)


# =============================================================================
# PALETTE SOURCE SYNC TESTS
# Source: test_palette_source_sync.py
# =============================================================================


class TestPaletteSourceSync:
    """Tests for palette source synchronization.

    Source: test_palette_source_sync.py

    Verifies palette sources registered in the controller are correctly
    populated in the view.
    """

    def test_palette_source_sync_late_connection(self, qtbot):
        """Verify that palette sources registered in the controller BEFORE
        the view is connected are correctly populated in the view.
        """
        controller = EditingController()

        controller.register_palette_source("rom", 10, [(255, 0, 0)] * 16, "Red Palette")

        workspace = EditWorkspace()
        qtbot.addWidget(workspace)
        workspace.set_controller(controller)

        palette_panel = workspace.palette_panel
        selector = palette_panel.palette_source_selector

        combo = selector.findChild(QComboBox)
        assert combo is not None, "Could not find QComboBox in PaletteSourceSelector"

        combo_items = [combo.itemText(i) for i in range(combo.count())]
        assert "Red Palette" in combo_items, f"'Red Palette' not found in combo items: {combo_items[:5]}..."

        sources = controller.get_palette_sources()
        assert ("rom", 10) in sources, f"('rom', 10) not found in controller sources: {list(sources.keys())[:5]}..."

    def test_rom_workspace_palette_source_syncs(self, qtbot):
        """Contract: Programmatic palette source selection updates the ROM workspace dropdown.

        Regression: Before fix, EditingController only updated self._view (VRAM EditTab),
        leaving the ROM workspace's dropdown stale.
        """
        controller = EditingController()

        vram_tab = EditTab()
        qtbot.addWidget(vram_tab)
        controller.set_view(vram_tab)

        rom_workspace = EditWorkspace()
        qtbot.addWidget(rom_workspace)
        rom_workspace.set_controller(controller)

        colors = [(0, 0, 0)] * 16
        controller.register_palette_source("rom", 8, colors, "ROM Palette 8")
        controller.set_palette_source("rom", 8)

        assert ("rom", 8) in controller.get_palette_sources()

        selector = rom_workspace.palette_panel.palette_source_selector
        selected_source = selector.get_selected_source()
        assert selected_source == (
            "rom",
            8,
        ), f"Expected ('rom', 8), got {selected_source}"

    def test_load_palette_updates_selector(self, qtbot, tmp_path):
        """Verify that loading a palette file registers it as a "file" source
        and updates the dropdown selector.

        Regression: Before fix, handle_load_palette() bypassed the source system,
        leaving the dropdown showing "Default" while colors showed the loaded file.
        """
        controller = EditingController()

        workspace = EditWorkspace()
        qtbot.addWidget(workspace)
        workspace.set_controller(controller)

        pal_file = tmp_path / "test.pal"
        pal_file.write_text("JASC-PAL\n0100\n16\n" + "\n".join(f"{i * 16} {i * 16} {i * 16}" for i in range(16)))

        with patch(
            "PySide6.QtWidgets.QFileDialog.getOpenFileName",
            return_value=(str(pal_file), ""),
        ):
            controller.handle_load_palette()

        selector = workspace.palette_panel.palette_source_selector
        selected_source = selector.get_selected_source()
        assert selected_source == ("file", 0), f"Expected ('file', 0), got {selected_source}"

        combo = selector.findChild(QComboBox)
        item_texts = [combo.itemText(i) for i in range(combo.count())]
        assert "Loaded Palette" in item_texts, f"Expected 'Loaded Palette' in {item_texts}"


# =============================================================================
# PALETTE SYNC FULL TESTS
# Source: test_palette_sync_full.py
# =============================================================================


class TestPaletteSyncFull:
    """Tests for palette synchronization across workspaces.

    Source: test_palette_sync_full.py

    Verifies palette changes propagate to all workspaces sharing a controller.
    """

    def test_palette_sync_across_workspaces(self, qtbot):
        """Verify palette changes propagate to both workspaces sharing a controller."""
        controller = EditingController()

        vram_workspace = EditWorkspace()
        vram_workspace.set_controller(controller)

        rom_workspace = EditWorkspace()
        rom_workspace.set_controller(controller)

        fallback_palette = get_default_snes_palette()
        data = np.zeros((16, 16), dtype=np.uint8)
        data[0, 0] = 7

        controller.load_image(data, fallback_palette)
        qtbot.wait_exposed(rom_workspace)

        assert rom_workspace.palette_panel.get_color_at(7) == (88, 144, 248)
        assert vram_workspace.palette_panel.get_color_at(7) == (88, 144, 248)

        orange_palette = [(0, 0, 0)] * 16
        orange_palette[7] = (255, 165, 0)
        orange_palette[8] = (139, 69, 19)

        controller.set_palette(orange_palette, "JSON Palette")

        assert rom_workspace.palette_panel.get_color_at(7) == (255, 165, 0)
        assert vram_workspace.palette_panel.get_color_at(7) == (255, 165, 0)


# =============================================================================
# ROM PALETTE WORKFLOW TESTS
# Source: test_rom_palette_workflow.py
# =============================================================================


class TestROMPaletteWorkflow:
    """Tests for ROM palette extraction and fallback behavior.

    Source: test_rom_palette_workflow.py

    Verifies that open_in_editor extracts ROM palettes and handles fallbacks.
    """

    def test_open_in_editor_uses_extracted_palette(self, qtbot):
        """Verify that open_in_editor extracts all ROM palettes and registers them."""
        mock_editing_controller = MagicMock()
        mock_rom_extractor = MagicMock()

        controller = ROMWorkflowController(
            parent=None, editing_controller=mock_editing_controller, rom_extractor=mock_rom_extractor
        )

        controller.current_tile_data = b"\x00" * 32
        controller.current_tile_offset = 0  # Must match current_offset (defaults to 0)
        controller.current_width = 8
        controller.current_height = 8
        controller.current_sprite_name = "test_sprite"
        controller.rom_path = "test.sfc"

        mock_header = MagicMock()
        mock_rom_extractor.rom_injector.read_rom_header.return_value = mock_header

        mock_rom_extractor.get_palette_config_from_sprite_config.return_value = (
            0x1000,
            [10, 11],
        )

        expected_palette_10 = [(0, 0, 0)] * 16
        expected_palette_10[0] = (255, 0, 0)
        all_palettes = {
            8: [(0, 0, 0)] * 16,
            9: [(0, 0, 0)] * 16,
            10: expected_palette_10,
            11: [(0, 0, 0)] * 16,
            12: [(0, 0, 0)] * 16,
            13: [(0, 0, 0)] * 16,
            14: [(0, 0, 0)] * 16,
            15: [(0, 0, 0)] * 16,
        }
        mock_rom_extractor.extract_palette_range.return_value = all_palettes

        with patch("ui.sprite_editor.get_default_snes_palette") as mock_default:
            controller.open_in_editor()

            mock_rom_extractor.extract_palette_range.assert_called_with("test.sfc", 0x1000, 8, 15)

            mock_editing_controller.register_rom_palettes.assert_called_once_with(
                all_palettes, active_indices=ANY, descriptions=ANY
            )

            mock_editing_controller.set_palette_source.assert_called_with("rom", 10)

            mock_editing_controller.load_image.assert_called()
            args = mock_editing_controller.load_image.call_args
            assert args[0][1] == expected_palette_10

            mock_default.assert_not_called()

    def test_open_in_editor_fallback_to_default(self, qtbot):
        """Verify that open_in_editor falls back to default palette on failure."""
        mock_editing_controller = MagicMock()
        mock_rom_extractor = MagicMock()

        controller = ROMWorkflowController(
            parent=None, editing_controller=mock_editing_controller, rom_extractor=mock_rom_extractor
        )

        controller.current_tile_data = b"\x00" * 32
        controller.current_tile_offset = 0  # Must match current_offset (defaults to 0)
        controller.current_width = 8
        controller.current_height = 8
        controller.current_sprite_name = "test_sprite"
        controller.rom_path = "test.sfc"

        mock_rom_extractor.rom_injector.read_rom_header.return_value = MagicMock()
        mock_rom_extractor.get_palette_config_from_sprite_config.return_value = (None, None)

        with patch("ui.sprite_editor.get_default_snes_palette") as mock_default:
            mock_default_palette = [(1, 1, 1)] * 16
            mock_default.return_value = mock_default_palette

            controller.open_in_editor()

            mock_editing_controller.load_image.assert_called()
            args = mock_editing_controller.load_image.call_args
            assert args[0][1] == mock_default_palette

            mock_default.assert_called_once()

    def test_open_in_editor_clears_previous_rom_sources(self, qtbot):
        """Verify that loading a new sprite clears previous ROM palette sources."""
        mock_editing_controller = MagicMock()
        mock_rom_extractor = MagicMock()
        mock_view = MagicMock()
        mock_workspace = MagicMock()
        mock_palette_panel = MagicMock()
        mock_view.workspace = mock_workspace
        mock_workspace.palette_panel = mock_palette_panel

        controller = ROMWorkflowController(
            parent=None, editing_controller=mock_editing_controller, rom_extractor=mock_rom_extractor
        )
        controller.set_view(mock_view)

        controller.current_tile_data = b"\x00" * 32
        controller.current_tile_offset = 0  # Must match current_offset (defaults to 0)
        controller.current_width = 8
        controller.current_height = 8
        controller.current_sprite_name = "test_sprite"
        controller.rom_path = "test.sfc"

        mock_rom_extractor.rom_injector.read_rom_header.return_value = MagicMock()
        mock_rom_extractor.get_palette_config_from_sprite_config.return_value = (None, None)

        with patch("ui.sprite_editor.get_default_snes_palette") as mock_default:
            mock_default.return_value = [(0, 0, 0)] * 16
            controller.open_in_editor()

            mock_view.clear_rom_palette_sources.assert_called_once()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
