#!/usr/bin/env python3
"""Tests for PaletteModel.

Verifies index 0 (transparent) protection and other palette operations.
"""

import pytest

from ui.sprite_editor.models.palette_model import PaletteModel


def test_set_color_index_0_protected():
    """Index 0 (transparent) should not be modifiable."""
    model = PaletteModel()
    original_color = model.get_color(0)

    # Attempt to set index 0 to a different color
    model.set_color(0, (255, 0, 0))

    # Index 0 should remain unchanged
    assert model.get_color(0) == original_color


def test_set_color_valid_indices():
    """Indices 1-15 should be modifiable."""
    model = PaletteModel()

    for index in range(1, 16):
        test_color = (index * 10, index * 10, index * 10)
        model.set_color(index, test_color)
        assert model.get_color(index) == test_color


def test_set_color_out_of_range():
    """Out of range indices should be silently ignored."""
    model = PaletteModel()

    # Negative index
    model.set_color(-1, (255, 0, 0))  # Should not raise

    # Index >= 16
    model.set_color(16, (255, 0, 0))  # Should not raise
    model.set_color(100, (255, 0, 0))  # Should not raise


def test_get_color_returns_tuple():
    """get_color should return RGB tuple."""
    model = PaletteModel()

    color = model.get_color(1)

    assert isinstance(color, tuple)
    assert len(color) == 3


def test_get_color_out_of_range():
    """get_color for out of range index should return black (0, 0, 0)."""
    model = PaletteModel()

    assert model.get_color(-1) == (0, 0, 0)
    assert model.get_color(16) == (0, 0, 0)
    assert model.get_color(100) == (0, 0, 0)


def test_default_palette_has_16_colors():
    """Default palette should have 16 colors."""
    model = PaletteModel()

    assert len(model.colors) == 16


def test_from_rgb_list():
    """from_rgb_list should set colors correctly."""
    model = PaletteModel()

    colors = [(i, i, i) for i in range(16)]
    model.from_rgb_list(colors)

    for i in range(16):
        assert model.get_color(i) == (i, i, i)


def test_from_rgb_list_pads_short_list():
    """from_rgb_list should pad short lists with black."""
    model = PaletteModel()

    colors = [(255, 0, 0), (0, 255, 0), (0, 0, 255)]
    model.from_rgb_list(colors)

    assert model.get_color(0) == (255, 0, 0)
    assert model.get_color(1) == (0, 255, 0)
    assert model.get_color(2) == (0, 0, 255)
    # Rest should be black
    for i in range(3, 16):
        assert model.get_color(i) == (0, 0, 0)


def test_from_rgb_list_truncates_long_list():
    """from_rgb_list should truncate lists longer than 16."""
    model = PaletteModel()

    colors = [(i, i, i) for i in range(32)]
    model.from_rgb_list(colors)

    # Should only have 16 colors
    assert len(model.colors) == 16
