"""Canonical mock classes for Mesen capture result testing.

This module provides centralized mock implementations for testing code that
interacts with Mesen2 capture results. These mocks replace 25+ inline
definitions scattered across test files.

Usage:
    from tests.infrastructure.mesen_mocks import MockBoundingBox, MockCaptureResult

    # Simple usage (class-attribute style for simple tests):
    class MockBoundingBox:
        x = 0
        y = 0
        width = 64
        height = 64

    # Or use the flexible dataclass-based mocks:
    bbox = MockBoundingBox(width=32, height=32)
    capture = MockCaptureResult(bounding_box=bbox)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence


@dataclass
class MockBoundingBox:
    """Mock for CaptureBoundingBox.

    Supports both attribute access and initialization with parameters.
    Default values match common test scenarios (64x64 at origin).
    """

    x: int = 0
    y: int = 0
    width: int = 64
    height: int = 64


@dataclass
class MockTileData:
    """Mock for tile data within OAM entries."""

    tile_index: int = 0
    vram_addr: int = 0
    pos_x: int = 0
    pos_y: int = 0
    data_hex: str = "00" * 32  # 32 bytes of zeros (4bpp 8x8 tile)
    rom_offset: int | None = None

    @property
    def data_bytes(self) -> bytes:
        """Return tile data as bytes."""
        return bytes.fromhex(self.data_hex)


@dataclass
class MockOAMEntry:
    """Mock for OAM (Object Attribute Memory) entries.

    Represents a single sprite object with position, dimensions, and tile data.
    """

    id: int = 0
    x: int = 0
    y: int = 0
    width: int = 16
    height: int = 16
    palette: int = 0
    flip_h: bool = False
    flip_v: bool = False
    priority: int = 0
    tile: int = 0
    name_table: int = 0
    size_large: bool = False
    rom_offset: int = 0x10000
    tiles: list[MockTileData] = field(default_factory=list)
    idx: int = 0  # For capture_to_rom_mapper compatibility

    @property
    def tiles_wide(self) -> int:
        """Number of tiles horizontally."""
        return self.width // 8

    @property
    def tiles_high(self) -> int:
        """Number of tiles vertically."""
        return self.height // 8


@dataclass
class MockCaptureResult:
    """Mock for CaptureResult from Mesen2 sprite captures.

    Flexible mock that supports:
    - Simple class-attribute style (entries=[], palettes={})
    - Parameterized construction with custom bounding box
    - Auto-computed bounding box from entries

    Examples:
        # Simple usage:
        capture = MockCaptureResult()

        # With custom bounding box:
        capture = MockCaptureResult(
            bounding_box=MockBoundingBox(width=32, height=32)
        )

        # With entries (bounding box computed automatically):
        entry = MockOAMEntry(x=0, y=0, width=16, height=16)
        capture = MockCaptureResult(entries=[entry])
    """

    entries: list[MockOAMEntry] = field(default_factory=list)
    palettes: dict[int, Sequence[int] | Sequence[tuple[int, int, int]]] = field(default_factory=dict)
    frame: int = 0
    visible_count: int = 0
    obsel: int = 0
    timestamp: str = ""
    _bounding_box: MockBoundingBox | None = field(default=None, repr=False)
    has_entries: bool = True  # For compatibility with code that checks this

    def __post_init__(self) -> None:
        """Initialize computed fields."""
        if self.visible_count == 0:
            self.visible_count = len(self.entries)

    @property
    def bounding_box(self) -> MockBoundingBox:
        """Return bounding box, computing from entries if not explicitly set."""
        if self._bounding_box is not None:
            return self._bounding_box

        if not self.entries:
            return MockBoundingBox(0, 0, 0, 0)

        min_x = min(e.x for e in self.entries)
        min_y = min(e.y for e in self.entries)
        max_x = max(e.x + e.width for e in self.entries)
        max_y = max(e.y + e.height for e in self.entries)
        return MockBoundingBox(min_x, min_y, max_x - min_x, max_y - min_y)

    @bounding_box.setter
    def bounding_box(self, value: MockBoundingBox) -> None:
        """Set explicit bounding box."""
        self._bounding_box = value


def create_simple_capture(
    width: int = 64,
    height: int = 64,
    x: int = 0,
    y: int = 0,
) -> MockCaptureResult:
    """Create a simple capture result with a single bounding box.

    Convenience function for tests that just need a basic capture result
    without complex entry structures.

    Args:
        width: Bounding box width
        height: Bounding box height
        x: Bounding box x position
        y: Bounding box y position

    Returns:
        MockCaptureResult with the specified bounding box
    """
    bbox = MockBoundingBox(x=x, y=y, width=width, height=height)
    return MockCaptureResult(_bounding_box=bbox)


__all__ = [
    "MockBoundingBox",
    "MockCaptureResult",
    "MockOAMEntry",
    "MockTileData",
    "create_simple_capture",
]
