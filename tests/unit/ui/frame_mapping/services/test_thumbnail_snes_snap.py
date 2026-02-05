"""Tests for SNES color snap in thumbnail quantization (BUG-5).

Verifies that quantize_pil_image() snaps palette colors to SNES-valid values
before quantization, matching the injection/compositor pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest
from PIL import Image

from core.palette_utils import snap_to_snes_color
from ui.frame_mapping.services.thumbnail_service import quantize_pil_image


@dataclass
class FakeSheetPalette:
    """Minimal SheetPalette for testing."""

    colors: list[tuple[int, int, int]]
    color_mappings: list[object] = field(default_factory=list)
    alpha_threshold: int = 128
    dither_mode: str = "none"
    dither_strength: float = 0.0


def _pad_palette(colors: list[tuple[int, int, int]]) -> list[tuple[int, int, int]]:
    """Pad palette to minimum 16 colors for quantization."""
    padded = list(colors)
    while len(padded) < 16:
        padded.append((0, 0, 0))
    return padded


class TestQuantizePilImageSnesSnap:
    """Verify quantize_pil_image snaps palette colors to SNES values."""

    def test_quantize_snaps_palette_to_snes_colors(self) -> None:
        """Non-SNES palette colors should be snapped before quantization."""
        # 127 is NOT a valid SNES color — it snaps to 132
        non_snes_color = (127, 127, 127)
        expected_snapped = snap_to_snes_color(non_snes_color)
        assert expected_snapped != non_snes_color  # Sanity check

        palette = FakeSheetPalette(colors=_pad_palette([(0, 0, 0), non_snes_color]))

        # Create a small image with the non-SNES color
        img = Image.new("RGBA", (4, 4), (*non_snes_color, 255))
        result = quantize_pil_image(img, palette)

        # All opaque pixels should be the SNES-snapped color, not the original
        pixels = list(result.getdata())
        opaque_pixels = [p for p in pixels if p[3] > 0]
        for pixel in opaque_pixels:
            assert pixel[:3] == expected_snapped, f"Expected SNES-snapped {expected_snapped}, got {pixel[:3]}"

    def test_quantize_already_snes_colors_unchanged(self) -> None:
        """Colors that are already SNES-valid should not change."""
        snes_color = (132, 132, 132)  # Already SNES-valid
        assert snap_to_snes_color(snes_color) == snes_color

        palette = FakeSheetPalette(colors=_pad_palette([(0, 0, 0), snes_color]))
        img = Image.new("RGBA", (4, 4), (*snes_color, 255))
        result = quantize_pil_image(img, palette)

        pixels = list(result.getdata())
        opaque_pixels = [p for p in pixels if p[3] > 0]
        for pixel in opaque_pixels:
            assert pixel[:3] == snes_color

    def test_multiple_non_snes_colors_all_snapped(self) -> None:
        """Multiple non-SNES colors should all be snapped before quantization."""
        # Create palette with several non-SNES colors
        non_snes_colors = [
            (127, 127, 127),  # Snaps to (132, 132, 132)
            (200, 100, 50),  # Non-SNES, will snap
        ]
        snapped_expected = [snap_to_snes_color(c) for c in non_snes_colors]

        palette = FakeSheetPalette(colors=_pad_palette([(0, 0, 0)] + non_snes_colors))

        # Create image with first non-SNES color
        img = Image.new("RGBA", (4, 4), (*non_snes_colors[0], 255))
        result = quantize_pil_image(img, palette)

        # Check that pixels map to the snapped version
        pixels = list(result.getdata())
        opaque_pixels = [p for p in pixels if p[3] > 0]
        for pixel in opaque_pixels:
            # The pixel should match the SNES-snapped version
            assert pixel[:3] == snapped_expected[0], f"Expected snapped {snapped_expected[0]}, got {pixel[:3]}"
