"""
Tests for PaletteSourceSelector widget.

Merged from tests/ui/integration/test_ui_logic_desync_fixes.py (Bug 2 and Bug 4).
"""

from __future__ import annotations

import pytest

from ui.sprite_editor.views.widgets.palette_source_selector import PaletteSourceSelector

# =============================================================================
# Bug 2: [Modified] palette item never removed
# =============================================================================


class TestBug2ModifiedItemRemoval:
    """Bug 2: [Modified] palette item should be removed when standard source selected."""

    def test_modified_item_removed_when_standard_source_selected(self, qtbot) -> None:
        """Selecting a standard source should remove the [Modified] entry.

        When user selects 'Default' or another standard source, the [Modified]
        entry should be automatically removed from the dropdown.
        """
        selector = PaletteSourceSelector()
        qtbot.addWidget(selector)

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

    def test_remove_custom_item_method_exists(self, qtbot) -> None:
        """PaletteSourceSelector should have remove_custom_item method."""
        selector = PaletteSourceSelector()
        qtbot.addWidget(selector)

        # Bug 2 fix requires this method to exist
        assert hasattr(selector, "remove_custom_item"), "PaletteSourceSelector should have remove_custom_item method"

    def test_clear_all_sources_method_exists(self, qtbot) -> None:
        """PaletteSourceSelector should have clear_all_sources method."""
        selector = PaletteSourceSelector()
        qtbot.addWidget(selector)

        # Bug 2 fix requires this method to exist
        assert hasattr(selector, "clear_all_sources"), "PaletteSourceSelector should have clear_all_sources method"


# =============================================================================
# Bug 4: Incomplete clearing for preset/file/custom types
# =============================================================================


class TestBug4IncompleteClearingByType:
    """Bug 4: All source types should support clearing."""

    def test_palette_source_selector_clear_sources_by_type_method_exists(self, qtbot) -> None:
        """PaletteSourceSelector should have clear_sources_by_type method."""
        selector = PaletteSourceSelector()
        qtbot.addWidget(selector)

        # Bug 4 fix requires this method to exist
        assert hasattr(selector, "clear_sources_by_type"), (
            "PaletteSourceSelector should have clear_sources_by_type method"
        )

    def test_clear_sources_by_type_preset(self, qtbot) -> None:
        """Clearing 'preset' type should remove preset sources."""
        selector = PaletteSourceSelector()
        qtbot.addWidget(selector)

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

    def test_clear_sources_by_type_file(self, qtbot) -> None:
        """Clearing 'file' type should remove file sources."""
        selector = PaletteSourceSelector()
        qtbot.addWidget(selector)

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

    def test_clear_sources_by_type_custom(self, qtbot) -> None:
        """Clearing '' (custom) type should remove the [Modified] entry."""
        selector = PaletteSourceSelector()
        qtbot.addWidget(selector)

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
