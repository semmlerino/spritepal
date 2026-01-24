#!/usr/bin/env python3
"""Tests for ToolManager brush pixel calculation.

Verifies that brush is properly centered at the given position.
"""

import pytest

from ui.sprite_editor.managers.tool_manager import ToolManager


def test_brush_size_1_returns_single_center_pixel():
    """Brush size 1 should return only the center pixel."""
    manager = ToolManager()
    manager.set_brush_size(1)

    pixels = manager.get_brush_pixels(5, 5)

    assert pixels == [(5, 5)]


def test_brush_size_3_is_centered():
    """Brush size 3 should return 3x3 grid centered on position."""
    manager = ToolManager()
    manager.set_brush_size(3)

    pixels = manager.get_brush_pixels(5, 5)

    # Should be 9 pixels in a 3x3 grid
    assert len(pixels) == 9

    # Check that center pixel is included
    assert (5, 5) in pixels

    # Check all expected pixels for a centered 3x3 brush
    expected = [
        (4, 4),
        (5, 4),
        (6, 4),  # top row
        (4, 5),
        (5, 5),
        (6, 5),  # middle row
        (4, 6),
        (5, 6),
        (6, 6),  # bottom row
    ]
    assert set(pixels) == set(expected)


def test_brush_size_5_is_centered():
    """Brush size 5 should return 5x5 grid centered on position."""
    manager = ToolManager()
    manager.set_brush_size(5)

    pixels = manager.get_brush_pixels(10, 10)

    # Should be 25 pixels in a 5x5 grid
    assert len(pixels) == 25

    # Check that center pixel is included
    assert (10, 10) in pixels

    # Check corners of the 5x5 grid
    assert (8, 8) in pixels  # top-left
    assert (12, 8) in pixels  # top-right
    assert (8, 12) in pixels  # bottom-left
    assert (12, 12) in pixels  # bottom-right


def test_brush_size_2_standard_offset():
    """Brush size 2 should return 2x2 grid with slight offset toward top-left."""
    manager = ToolManager()
    manager.set_brush_size(2)

    pixels = manager.get_brush_pixels(5, 5)

    # Should be 4 pixels in a 2x2 grid
    assert len(pixels) == 4

    # For even sizes, offset toward top-left is standard convention
    # half = 2 // 2 = 1
    # end = half = 1 (since 2 % 2 == 0)
    # range(-1, 1) = [-1, 0]
    expected = [
        (4, 4),
        (5, 4),  # top row
        (4, 5),
        (5, 5),  # bottom row
    ]
    assert set(pixels) == set(expected)


def test_brush_size_4_standard_offset():
    """Brush size 4 should return 4x4 grid with slight offset toward top-left."""
    manager = ToolManager()
    manager.set_brush_size(4)

    pixels = manager.get_brush_pixels(5, 5)

    # Should be 16 pixels in a 4x4 grid
    assert len(pixels) == 16

    # half = 4 // 2 = 2
    # end = half = 2 (since 4 % 2 == 0)
    # range(-2, 2) = [-2, -1, 0, 1]
    # So x: 3, 4, 5, 6 and y: 3, 4, 5, 6
    expected_xs = [3, 4, 5, 6]
    expected_ys = [3, 4, 5, 6]

    for x in expected_xs:
        for y in expected_ys:
            assert (x, y) in pixels


def test_brush_at_origin():
    """Test brush calculation at origin (0, 0)."""
    manager = ToolManager()
    manager.set_brush_size(3)

    pixels = manager.get_brush_pixels(0, 0)

    # Should include negative coordinates for centering
    assert (-1, -1) in pixels
    assert (0, 0) in pixels
    assert (1, 1) in pixels
