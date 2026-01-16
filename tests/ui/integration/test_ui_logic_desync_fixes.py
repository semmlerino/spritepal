"""
Tests for UI-logic desynchronization fixes.

These tests verify that signal state stays synchronized with UI state across
various operations. Each test corresponds to a bug identified in the
UI_LOGIC_DESYNC_AUDIT_JAN_2026.md audit.

Bug 1: Undo signal not emitted after clear in load_image/revert_to_original
Bug 2: [Modified] palette item never removed when standard source selected
Bug 3: Palette sources persist across ROM loads
Bug 4: Incomplete clearing for preset/file/custom source types
"""

from __future__ import annotations

import numpy as np
import pytest
from PySide6.QtTest import QSignalSpy

from ui.sprite_editor.controllers.editing_controller import EditingController
from ui.sprite_editor.views.widgets.palette_source_selector import PaletteSourceSelector

# ==============================================================================
# Bug 1: Undo signal not emitted after clear
# ==============================================================================


class TestBug1UndoSignalAfterClear:
    """Bug 1: Undo signal must be emitted after clearing undo history."""

    def test_load_image_emits_undo_signal(self, qtbot: object) -> None:
        """load_image() should emit undoStateChanged after clearing history.

        After loading an image, the undo state should be (can_undo=False, can_redo=False)
        and this state must be communicated via the undoStateChanged signal.
        """
        controller = EditingController()

        # First, create some undo history
        initial_data = np.zeros((8, 8), dtype=np.uint8)
        controller.load_image(initial_data)
        controller.set_selected_color(1)
        controller.handle_pixel_press(0, 0)
        controller.handle_pixel_release(0, 0)

        # Verify we have undo state
        assert controller.undo_manager.can_undo()

        # Create new spy AFTER we have undo history
        spy_undo = QSignalSpy(controller.undoStateChanged)
        assert spy_undo.count() == 0

        # Load a new image - this should clear undo history AND emit signal
        new_data = np.ones((8, 8), dtype=np.uint8)
        controller.load_image(new_data)

        # Bug 1: undoStateChanged should be emitted after load_image clears history
        assert spy_undo.count() >= 1, "undoStateChanged must be emitted after load_image"
        last_args = spy_undo.at(spy_undo.count() - 1)
        assert last_args[0] is False, "can_undo should be False after load_image"
        assert last_args[1] is False, "can_redo should be False after load_image"


# ==============================================================================
# Bug 2: [Modified] palette item never removed
# ==============================================================================


class TestBug2ModifiedItemRemoval:
    """Bug 2: [Modified] palette item should be removed when standard source selected."""

    def test_modified_item_removed_when_standard_source_selected(self, qtbot: object) -> None:
        """Selecting a standard source should remove the [Modified] entry.

        When user selects 'Default' or another standard source, the [Modified]
        entry should be automatically removed from the dropdown.
        """
        selector = PaletteSourceSelector()
        qtbot.addWidget(selector)  # type: ignore[attr-defined]

        # Trigger [Modified] item to appear by setting empty source type
        selector.set_selected_source("", -1)

        # Verify [Modified] item exists
        combo = selector._combo_box
        custom_exists = any(combo.itemData(i, selector._SOURCE_TYPE_ROLE) == "" for i in range(combo.count()))
        assert custom_exists, "[Modified] item should exist after set_selected_source('', -1)"

        # Now select a standard source
        selector.set_selected_source("default", 0)

        # Bug 2: [Modified] should be removed when standard source selected
        custom_exists_after = any(combo.itemData(i, selector._SOURCE_TYPE_ROLE) == "" for i in range(combo.count()))
        assert not custom_exists_after, "[Modified] item should be removed after selecting standard source"

    def test_remove_custom_item_method_exists(self, qtbot: object) -> None:
        """PaletteSourceSelector should have remove_custom_item method."""
        selector = PaletteSourceSelector()
        qtbot.addWidget(selector)  # type: ignore[attr-defined]

        # Bug 2 fix requires this method to exist
        assert hasattr(selector, "remove_custom_item"), "PaletteSourceSelector should have remove_custom_item method"

    def test_clear_all_sources_method_exists(self, qtbot: object) -> None:
        """PaletteSourceSelector should have clear_all_sources method."""
        selector = PaletteSourceSelector()
        qtbot.addWidget(selector)  # type: ignore[attr-defined]

        # Bug 2 fix requires this method to exist
        assert hasattr(selector, "clear_all_sources"), "PaletteSourceSelector should have clear_all_sources method"


# ==============================================================================
# Bug 3: Palette sources persist across ROM loads
# ==============================================================================


class TestBug3PaletteSourcesPersistence:
    """Bug 3: Palette sources must be cleared when loading a new ROM."""

    def test_editing_controller_clears_rom_sources(self, qtbot: object) -> None:
        """EditingController should emit paletteSourcesCleared for 'rom' type."""
        controller = EditingController()
        spy_cleared = QSignalSpy(controller.paletteSourcesCleared)

        # Register a ROM palette source
        controller.register_palette_source("rom", 0, [(0, 0, 0)] * 16, "ROM Palette")
        assert ("rom", 0) in controller._palette_sources

        # Clear ROM sources
        controller.clear_palette_sources("rom")

        # Bug 3: Signal should be emitted
        assert spy_cleared.count() >= 1, "paletteSourcesCleared should be emitted"
        assert spy_cleared.at(spy_cleared.count() - 1)[0] == "rom"
        assert ("rom", 0) not in controller._palette_sources

    def test_editing_controller_clears_mesen_sources(self, qtbot: object) -> None:
        """EditingController should emit paletteSourcesCleared for 'mesen' type."""
        controller = EditingController()
        spy_cleared = QSignalSpy(controller.paletteSourcesCleared)

        # Register a Mesen palette source
        controller.register_palette_source("mesen", 0, [(0, 0, 0)] * 16, "Mesen Capture")
        assert ("mesen", 0) in controller._palette_sources

        # Clear Mesen sources
        controller.clear_palette_sources("mesen")

        # Bug 3: Signal should be emitted
        assert spy_cleared.count() >= 1, "paletteSourcesCleared should be emitted"
        assert spy_cleared.at(spy_cleared.count() - 1)[0] == "mesen"
        assert ("mesen", 0) not in controller._palette_sources


# ==============================================================================
# Bug 4: Incomplete clearing for preset/file/custom types
# ==============================================================================


class TestBug4IncompleteClearingByType:
    """Bug 4: All source types should support clearing."""

    def test_palette_source_selector_clear_sources_by_type_method_exists(self, qtbot: object) -> None:
        """PaletteSourceSelector should have clear_sources_by_type method."""
        selector = PaletteSourceSelector()
        qtbot.addWidget(selector)  # type: ignore[attr-defined]

        # Bug 4 fix requires this method to exist
        assert hasattr(selector, "clear_sources_by_type"), (
            "PaletteSourceSelector should have clear_sources_by_type method"
        )

    def test_clear_sources_by_type_preset(self, qtbot: object) -> None:
        """Clearing 'preset' type should remove preset sources."""
        selector = PaletteSourceSelector()
        qtbot.addWidget(selector)  # type: ignore[attr-defined]

        # Add a preset source (display_name, source_type, palette_index)
        selector.add_palette_source("Test Preset", "preset", 0)
        combo = selector._combo_box

        # Verify preset exists
        preset_exists = any(combo.itemData(i, selector._SOURCE_TYPE_ROLE) == "preset" for i in range(combo.count()))
        assert preset_exists, "Preset source should exist after adding"

        # Clear preset sources
        selector.clear_sources_by_type("preset")

        # Bug 4: Preset should be removed
        preset_exists_after = any(
            combo.itemData(i, selector._SOURCE_TYPE_ROLE) == "preset" for i in range(combo.count())
        )
        assert not preset_exists_after, "Preset sources should be cleared"

    def test_clear_sources_by_type_file(self, qtbot: object) -> None:
        """Clearing 'file' type should remove file sources."""
        selector = PaletteSourceSelector()
        qtbot.addWidget(selector)  # type: ignore[attr-defined]

        # Add a file source (display_name, source_type, palette_index)
        selector.add_palette_source("loaded_file.pal", "file", 0)
        combo = selector._combo_box

        # Verify file exists
        file_exists = any(combo.itemData(i, selector._SOURCE_TYPE_ROLE) == "file" for i in range(combo.count()))
        assert file_exists, "File source should exist after adding"

        # Clear file sources
        selector.clear_sources_by_type("file")

        # Bug 4: File should be removed
        file_exists_after = any(combo.itemData(i, selector._SOURCE_TYPE_ROLE) == "file" for i in range(combo.count()))
        assert not file_exists_after, "File sources should be cleared"

    def test_clear_sources_by_type_custom(self, qtbot: object) -> None:
        """Clearing '' (custom) type should remove the [Modified] entry."""
        selector = PaletteSourceSelector()
        qtbot.addWidget(selector)  # type: ignore[attr-defined]

        # Trigger [Modified] item
        selector.set_selected_source("", -1)
        combo = selector._combo_box

        # Verify custom exists
        custom_exists = any(combo.itemData(i, selector._SOURCE_TYPE_ROLE) == "" for i in range(combo.count()))
        assert custom_exists, "[Modified] should exist after set_selected_source('', -1)"

        # Clear custom sources
        selector.clear_sources_by_type("")

        # Bug 4: Custom should be removed
        custom_exists_after = any(combo.itemData(i, selector._SOURCE_TYPE_ROLE) == "" for i in range(combo.count()))
        assert not custom_exists_after, "[Modified] entry should be cleared"
