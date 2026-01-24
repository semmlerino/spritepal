"""Tests for RGB→indexed color mapping report.

Verifies that after loading an image, the controller emits a signal
with color mapping analysis results (exact vs fallback matches).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image
from PySide6.QtTest import QSignalSpy

from core.frame_mapping_project import SheetPalette
from ui.frame_mapping.controllers.palette_editor_controller import PaletteEditorController


@pytest.fixture
def test_palette() -> SheetPalette:
    """Create a test palette with specific colors."""
    colors = [
        (0, 0, 0),  # 0: black (transparent)
        (255, 0, 0),  # 1: pure red
        (0, 255, 0),  # 2: pure green
        (0, 0, 255),  # 3: pure blue
        (255, 255, 0),  # 4: yellow
        (255, 255, 255),  # 5: white
        (128, 128, 128),  # 6: gray
        (64, 64, 64),  # 7: dark gray
    ] + [(0, 0, 0)] * 8  # Fill remaining with black
    return SheetPalette(colors=colors)


@pytest.fixture
def image_with_exact_matches(tmp_path: Path) -> Path:
    """Create an image with colors that exactly match the palette."""
    img = Image.new("RGBA", (4, 4))
    pixels = img.load()
    # Use only colors that exactly match palette
    pixels[0, 0] = (255, 0, 0, 255)  # red (index 1)
    pixels[1, 0] = (0, 255, 0, 255)  # green (index 2)
    pixels[2, 0] = (0, 0, 255, 255)  # blue (index 3)
    pixels[3, 0] = (255, 255, 255, 255)  # white (index 5)
    # Fill rest with black
    for y in range(1, 4):
        for x in range(4):
            pixels[x, y] = (0, 0, 0, 255)
    path = tmp_path / "exact_match.png"
    img.save(path)
    return path


@pytest.fixture
def image_with_fallback_colors(tmp_path: Path) -> Path:
    """Create an image with colors that require nearest-neighbor matching."""
    img = Image.new("RGBA", (4, 4))
    pixels = img.load()
    # Use colors NOT in palette - will need fallback
    pixels[0, 0] = (250, 10, 10, 255)  # near-red (will map to index 1)
    pixels[1, 0] = (10, 250, 10, 255)  # near-green (will map to index 2)
    pixels[2, 0] = (100, 100, 100, 255)  # not exactly in palette (nearest: 6 or 7)
    pixels[3, 0] = (200, 200, 200, 255)  # not exactly in palette (nearest: 5)
    # Fill rest with exact match
    for y in range(1, 4):
        for x in range(4):
            pixels[x, y] = (255, 0, 0, 255)  # exact red
    path = tmp_path / "fallback_colors.png"
    img.save(path)
    return path


class TestColorMappingReport:
    """Tests for color mapping analysis signal."""

    def test_controller_has_color_mapping_report_signal(
        self,
        qtbot,
    ) -> None:
        """Controller should have a color_mapping_report signal."""
        controller = PaletteEditorController()

        assert hasattr(controller, "color_mapping_report")

    def test_signal_emitted_on_image_load(
        self,
        qtbot,
        image_with_exact_matches: Path,
        test_palette: SheetPalette,
    ) -> None:
        """Signal should be emitted when an image is loaded."""
        controller = PaletteEditorController()
        spy = QSignalSpy(controller.color_mapping_report)

        controller.load_image(image_with_exact_matches, test_palette)

        assert spy.count() == 1

    def test_report_shows_fallback_count(
        self,
        qtbot,
        image_with_fallback_colors: Path,
        test_palette: SheetPalette,
    ) -> None:
        """Report should include count of colors requiring fallback."""
        controller = PaletteEditorController()
        spy = QSignalSpy(controller.color_mapping_report)

        controller.load_image(image_with_fallback_colors, test_palette)

        assert spy.count() == 1
        report = spy.at(0)[0]
        # Should have some fallback matches (non-exact colors in the image)
        assert report["unmapped_count"] > 0

    def test_report_shows_exact_count(
        self,
        qtbot,
        image_with_exact_matches: Path,
        test_palette: SheetPalette,
    ) -> None:
        """Report should include count of exact matches."""
        controller = PaletteEditorController()

        # Add explicit mappings for the colors in our test image
        test_palette.color_mappings[(255, 0, 0)] = 1
        test_palette.color_mappings[(0, 255, 0)] = 2
        test_palette.color_mappings[(0, 0, 255)] = 3
        test_palette.color_mappings[(255, 255, 255)] = 5
        test_palette.color_mappings[(0, 0, 0)] = 0

        spy = QSignalSpy(controller.color_mapping_report)

        controller.load_image(image_with_exact_matches, test_palette)

        assert spy.count() == 1
        report = spy.at(0)[0]
        # All colors should be exact matches
        assert report["exact_count"] > 0
