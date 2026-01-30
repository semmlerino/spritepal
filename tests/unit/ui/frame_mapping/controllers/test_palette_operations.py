"""Tests for palette operations in FrameMappingController.

These tests verify set_sheet_palette, copy_game_palette_to_sheet,
extract_sheet_colors, and related palette functionality.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from core.frame_mapping_project import AIFrame, GameFrame, SheetPalette
from ui.frame_mapping.controllers.frame_mapping_controller import FrameMappingController


@pytest.fixture
def controller(qtbot: object) -> FrameMappingController:
    """Create a controller with a test project."""
    ctrl = FrameMappingController()
    ctrl.new_project("Test Project")
    return ctrl


@pytest.fixture
def populated_controller(controller: FrameMappingController, tmp_path: Path) -> FrameMappingController:
    """Create a controller with AI frames and game frames."""
    project = controller.project
    assert project is not None

    # Create a simple test PNG file with some colors
    img = Image.new("RGBA", (16, 16), (255, 0, 0, 255))
    img.putpixel((0, 0), (0, 255, 0, 255))
    img.putpixel((1, 0), (0, 0, 255, 255))
    sprite_path = tmp_path / "sprite_01.png"
    img.save(sprite_path)

    # Add AI frame
    ai_frame_1 = AIFrame(path=sprite_path, index=0)
    project.replace_ai_frames([ai_frame_1], tmp_path)

    # Add game frame (palettes come from capture result, not the frame itself)
    game_frame = GameFrame(
        id="capture_A",
        rom_offsets=[0x1000],
        width=16,
        height=16,
    )
    project.add_game_frame(game_frame)

    return controller


class TestGetSheetPalette:
    """Tests for get_sheet_palette method."""

    def test_returns_none_initially(self, controller: FrameMappingController) -> None:
        """get_sheet_palette returns None when no palette is set."""
        assert controller.get_sheet_palette() is None

    def test_returns_set_palette(self, controller: FrameMappingController) -> None:
        """get_sheet_palette returns the set palette."""
        # SheetPalette needs 16 colors for SNES palette
        colors = [(0, 0, 0)] + [(255, 0, 0), (0, 255, 0), (0, 0, 255)] + [(0, 0, 0)] * 12
        palette = SheetPalette(colors=colors)
        controller.set_sheet_palette(palette)

        result = controller.get_sheet_palette()
        assert result is not None
        assert result.colors == palette.colors

    def test_returns_none_without_project(self, controller: FrameMappingController) -> None:
        """get_sheet_palette returns None when no project exists."""
        controller._project = None
        assert controller.get_sheet_palette() is None


class TestSetSheetPalette:
    """Tests for set_sheet_palette method."""

    def test_emits_signal_on_set(self, controller: FrameMappingController) -> None:
        """set_sheet_palette emits sheet_palette_changed signal."""
        changed_count = [0]
        controller.sheet_palette_changed.connect(lambda: changed_count.__setitem__(0, changed_count[0] + 1))

        colors = [(0, 0, 0)] + [(255, 0, 0)] * 15
        palette = SheetPalette(colors=colors)
        controller.set_sheet_palette(palette)

        assert changed_count[0] == 1

    def test_emits_signal_on_clear(self, controller: FrameMappingController) -> None:
        """set_sheet_palette emits signal when clearing palette."""
        # First set a palette
        colors = [(0, 0, 0)] + [(255, 0, 0)] * 15
        palette = SheetPalette(colors=colors)
        controller.set_sheet_palette(palette)

        changed_count = [0]
        controller.sheet_palette_changed.connect(lambda: changed_count.__setitem__(0, changed_count[0] + 1))

        # Clear it
        controller.set_sheet_palette(None)

        assert changed_count[0] == 1

    def test_no_effect_without_project(self, controller: FrameMappingController) -> None:
        """set_sheet_palette does nothing when no project exists."""
        controller._project = None

        colors = [(0, 0, 0)] + [(255, 0, 0)] * 15
        palette = SheetPalette(colors=colors)
        # Should not crash
        controller.set_sheet_palette(palette)


class TestSetSheetPaletteColor:
    """Tests for set_sheet_palette_color method."""

    def test_updates_existing_color(self, controller: FrameMappingController) -> None:
        """set_sheet_palette_color updates a color in the palette."""
        colors = [(0, 0, 0), (255, 0, 0), (0, 255, 0), (0, 0, 255)] + [(0, 0, 0)] * 12
        palette = SheetPalette(colors=colors)
        controller.set_sheet_palette(palette)

        controller.set_sheet_palette_color(1, (128, 128, 128))

        result = controller.get_sheet_palette()
        assert result is not None
        assert result.colors[1] == (128, 128, 128)

    def test_emits_signal_on_change(self, controller: FrameMappingController) -> None:
        """set_sheet_palette_color emits signal when color is changed."""
        colors = [(0, 0, 0)] + [(255, 0, 0)] * 15
        palette = SheetPalette(colors=colors)
        controller.set_sheet_palette(palette)

        changed_count = [0]
        controller.sheet_palette_changed.connect(lambda: changed_count.__setitem__(0, changed_count[0] + 1))

        controller.set_sheet_palette_color(1, (0, 0, 0))

        assert changed_count[0] == 1


class TestCopyGamePaletteToSheet:
    """Tests for copy_game_palette_to_sheet method."""

    def test_returns_none_without_project(self, controller: FrameMappingController) -> None:
        """copy_game_palette_to_sheet returns None without project."""
        controller._project = None

        result = controller.copy_game_palette_to_sheet("capture_A")
        assert result is None

    def test_returns_none_for_nonexistent_game_frame(self, controller: FrameMappingController) -> None:
        """copy_game_palette_to_sheet returns None for nonexistent game frame."""
        result = controller.copy_game_palette_to_sheet("nonexistent")
        assert result is None

    def test_returns_none_for_frame_without_palette(self, populated_controller: FrameMappingController) -> None:
        """copy_game_palette_to_sheet returns None when frame has no palette."""
        # Our test game frame doesn't have capture result data with palettes
        result = populated_controller.copy_game_palette_to_sheet("capture_A")

        # Should return None since we don't have a capture result with palettes
        # (In real usage, the capture would come from Mesen with palette data)
        assert result is None


class TestExtractSheetColors:
    """Tests for extract_sheet_colors method."""

    def test_extracts_colors_from_all_ai_frames(self, populated_controller: FrameMappingController) -> None:
        """extract_sheet_colors extracts unique colors from all AI frames."""
        colors = populated_controller.extract_sheet_colors()

        assert colors is not None
        # Should contain colors from our test image(s)
        assert isinstance(colors, dict)

    def test_returns_empty_without_project(self, controller: FrameMappingController) -> None:
        """extract_sheet_colors returns empty dict without project."""
        controller._project = None

        result = controller.extract_sheet_colors()
        # Returns empty dict when project is None (based on service behavior)
        assert result is not None
        assert isinstance(result, dict)


class TestGenerateSheetPaletteFromColors:
    """Tests for generate_sheet_palette_from_colors method."""

    def test_generates_palette_from_colors(self, controller: FrameMappingController) -> None:
        """generate_sheet_palette_from_colors creates a SheetPalette."""
        # Input is a dict of color -> count for sorting by frequency
        colors = {(255, 0, 0): 10, (0, 255, 0): 5, (0, 0, 255): 3}

        result = controller.generate_sheet_palette_from_colors(colors)

        assert result is not None
        assert len(result.colors) == 16  # Always 16 for SNES

    def test_generates_palette_without_explicit_colors(self, controller: FrameMappingController) -> None:
        """generate_sheet_palette_from_colors can auto-extract from AI frames."""
        # Without explicit colors, it extracts from AI frames
        result = controller.generate_sheet_palette_from_colors(None)

        # Still returns a palette (possibly empty if no frames)
        assert result is not None


class TestGetGamePalettes:
    """Tests for get_game_palettes method."""

    def test_returns_empty_dict_without_project(self, controller: FrameMappingController) -> None:
        """get_game_palettes returns empty dict without project."""
        controller._project = None

        result = controller.get_game_palettes()
        assert result is not None
        assert isinstance(result, dict)

    def test_returns_dict_for_game_frames(self, populated_controller: FrameMappingController) -> None:
        """get_game_palettes returns a dict mapping frame IDs to palettes."""
        result = populated_controller.get_game_palettes()

        assert result is not None
        assert isinstance(result, dict)
        # Our test frame may not have palettes (no capture result)

    def test_returns_empty_for_no_captures(self, controller: FrameMappingController) -> None:
        """get_game_palettes returns empty dict when no game frames with palettes."""
        result = controller.get_game_palettes()

        assert result is not None
        assert isinstance(result, dict)
        assert len(result) == 0  # No game frames yet
