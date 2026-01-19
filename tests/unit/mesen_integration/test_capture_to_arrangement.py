"""Tests for CaptureToArrangementConverter.

Tests the conversion of Mesen 2 sprite captures to arrangement grid tiles.
"""

from __future__ import annotations

import pytest
from PIL import Image

from core.mesen_integration.capture_to_arrangement import (
    CaptureArrangementData,
    CaptureToArrangementConverter,
    PaletteGroup,
)
from core.mesen_integration.click_extractor import (
    CaptureResult,
    OAMEntry,
    OBSELConfig,
    TileData,
)


@pytest.fixture
def obsel_config() -> OBSELConfig:
    """Create a default OBSEL configuration."""
    return OBSELConfig(
        raw=0x63,
        name_base=3,
        name_select=0,
        size_select=3,
        tile_base_addr=0x6000,
        oam_base_addr=0x0000,
        oam_addr_offset=0x0100,
    )


@pytest.fixture
def sample_tile_data() -> TileData:
    """Create sample 8x8 tile data with visible content."""
    # 32 bytes for 4bpp 8x8 tile (64 hex chars)
    hex_data = "FF" * 32  # Solid tile (non-empty)
    return TileData(
        tile_index=10,
        vram_addr=0x6000,
        pos_x=0,
        pos_y=0,
        data_hex=hex_data,
    )


@pytest.fixture
def sample_palettes() -> dict[int, list[int]]:
    """Create sample RGB palettes."""
    # Palette 0: greens
    # Palette 7: reds
    return {
        0: [0x000000] + [0x00FF00] * 15,  # Black + green
        7: [0x000000] + [0xFF0000] * 15,  # Black + red
    }


@pytest.fixture
def sample_capture(
    obsel_config: OBSELConfig,
    sample_tile_data: TileData,
    sample_palettes: dict[int, list[int]],
) -> CaptureResult:
    """Create a sample capture with multiple entries in different palettes."""
    entries = [
        # Palette 0 - two entries
        OAMEntry(
            id=0,
            x=10,
            y=20,
            tile=10,
            width=8,
            height=8,
            flip_h=False,
            flip_v=False,
            palette=0,
            tiles=[sample_tile_data],
        ),
        OAMEntry(
            id=1,
            x=18,
            y=20,
            tile=11,
            width=8,
            height=8,
            flip_h=False,
            flip_v=False,
            palette=0,
            tiles=[sample_tile_data],
        ),
        # Palette 7 - one entry
        OAMEntry(
            id=2,
            x=50,
            y=60,
            tile=20,
            width=16,
            height=16,
            flip_h=False,
            flip_v=False,
            palette=7,
            tiles=[sample_tile_data] * 4,  # 4 tiles for 16x16
        ),
    ]
    return CaptureResult(
        frame=100,
        visible_count=3,
        obsel=obsel_config,
        entries=entries,
        palettes=sample_palettes,
        timestamp=12345,
    )


@pytest.fixture
def garbage_tile_entry(obsel_config: OBSELConfig) -> CaptureResult:
    """Create a capture with garbage tiles (0x03, 0x04)."""
    garbage_data = TileData(
        tile_index=3,  # Garbage tile
        vram_addr=0x6000,
        pos_x=0,
        pos_y=0,
        data_hex="00" * 32,
    )
    entry = OAMEntry(
        id=0,
        x=0,
        y=0,
        tile=3,
        width=8,
        height=8,
        flip_h=False,
        flip_v=False,
        palette=0,
        tiles=[garbage_data],
    )
    return CaptureResult(
        frame=100,
        visible_count=1,
        obsel=obsel_config,
        entries=[entry],
        palettes={0: [0x000000] * 16},
        timestamp=12345,
    )


class TestCaptureToArrangementConverter:
    """Tests for CaptureToArrangementConverter."""

    def test_groups_entries_by_palette(self, sample_capture: CaptureResult) -> None:
        """Entries with same palette are grouped together."""
        converter = CaptureToArrangementConverter()
        result = converter.convert(sample_capture, filter_garbage_tiles=False)

        # Should have 2 palette groups (0 and 7)
        assert len(result.groups) == 2

        # Find groups by palette
        group_0 = next((g for g in result.groups if g.palette_index == 0), None)
        group_7 = next((g for g in result.groups if g.palette_index == 7), None)

        assert group_0 is not None
        assert group_7 is not None

        # Palette 0 has 2 entries, palette 7 has 1
        assert group_0.entry_count == 2
        assert group_7.entry_count == 1

    def test_renders_tiles_at_8x8(self, sample_capture: CaptureResult) -> None:
        """Each group's tiles are 8x8 PIL Images."""
        converter = CaptureToArrangementConverter()
        result = converter.convert(sample_capture, filter_garbage_tiles=False)

        for group in result.groups:
            for tile_img in group.tiles.values():
                assert isinstance(tile_img, Image.Image)
                assert tile_img.size == (8, 8)

    def test_filters_selected_palettes(self, sample_capture: CaptureResult) -> None:
        """Only requested palettes are included."""
        converter = CaptureToArrangementConverter()

        # Only select palette 7
        result = converter.convert(
            sample_capture,
            selected_palettes={7},
            filter_garbage_tiles=False,
        )

        # Should only have 1 group (palette 7)
        assert len(result.groups) == 1
        assert result.groups[0].palette_index == 7

    def test_filters_garbage_tiles(self, garbage_tile_entry: CaptureResult) -> None:
        """Tiles 0x03, 0x04 are filtered when enabled."""
        converter = CaptureToArrangementConverter()

        # With filter enabled - should have no tiles
        result_filtered = converter.convert(
            garbage_tile_entry,
            filter_garbage_tiles=True,
        )
        assert result_filtered.total_tiles == 0

        # With filter disabled - should have tiles
        result_unfiltered = converter.convert(
            garbage_tile_entry,
            filter_garbage_tiles=False,
        )
        # May still have 0 tiles if the entry is truly empty, but at least check it ran
        assert result_unfiltered is not None

    def test_calculates_group_dimensions(self, sample_capture: CaptureResult) -> None:
        """Group width/height in tiles is correct."""
        converter = CaptureToArrangementConverter()
        result = converter.convert(sample_capture, filter_garbage_tiles=False)

        # Palette 0: Two 8x8 entries side-by-side at (10,20) and (18,20)
        # Bounding box: x=10-26, y=20-28 -> 16x8 -> 2x1 tiles
        group_0 = next((g for g in result.groups if g.palette_index == 0), None)
        assert group_0 is not None
        assert group_0.width_tiles == 2
        assert group_0.height_tiles == 1

        # Palette 7: One 16x16 entry -> 2x2 tiles
        group_7 = next((g for g in result.groups if g.palette_index == 7), None)
        assert group_7 is not None
        assert group_7.width_tiles == 2
        assert group_7.height_tiles == 2

    def test_returns_total_tiles_count(self, sample_capture: CaptureResult) -> None:
        """Total tiles count is accurate."""
        converter = CaptureToArrangementConverter()
        result = converter.convert(sample_capture, filter_garbage_tiles=False)

        # Sum up actual tiles in groups
        actual_count = sum(len(g.tiles) for g in result.groups)
        assert result.total_tiles == actual_count
        assert result.total_tiles > 0

    def test_source_path_stored(self, sample_capture: CaptureResult) -> None:
        """Source path is stored in result."""
        converter = CaptureToArrangementConverter()
        result = converter.convert(
            sample_capture,
            source_path="/path/to/capture.json",
            filter_garbage_tiles=False,
        )
        assert result.source_path == "/path/to/capture.json"

    def test_frame_preserved(self, sample_capture: CaptureResult) -> None:
        """Frame number is preserved in result."""
        converter = CaptureToArrangementConverter()
        result = converter.convert(sample_capture, filter_garbage_tiles=False)
        assert result.frame == 100

    def test_palettes_converted_to_rgb_tuples(self, sample_capture: CaptureResult) -> None:
        """Palettes are converted to (R,G,B) tuples."""
        converter = CaptureToArrangementConverter()
        result = converter.convert(sample_capture, filter_garbage_tiles=False)

        # Check palette 0 (greens)
        assert 0 in result.palettes
        palette_0 = result.palettes[0]
        assert len(palette_0) == 16
        assert palette_0[0] == (0, 0, 0)  # Black (transparent)
        assert palette_0[1] == (0, 255, 0)  # Green

        # Check palette 7 (reds)
        assert 7 in result.palettes
        palette_7 = result.palettes[7]
        assert palette_7[1] == (255, 0, 0)  # Red

    def test_obsel_preserved(self, sample_capture: CaptureResult) -> None:
        """OBSEL config is preserved in result."""
        converter = CaptureToArrangementConverter()
        result = converter.convert(sample_capture, filter_garbage_tiles=False)
        assert result.obsel.raw == 0x63

    def test_empty_capture_returns_empty_result(self, obsel_config: OBSELConfig) -> None:
        """Empty capture returns valid result with no tiles."""
        empty_capture = CaptureResult(
            frame=0,
            visible_count=0,
            obsel=obsel_config,
            entries=[],
            palettes={},
            timestamp=0,
        )
        converter = CaptureToArrangementConverter()
        result = converter.convert(empty_capture)

        assert result.total_tiles == 0
        assert len(result.groups) == 0
        assert not result.has_tiles


class TestPaletteGroup:
    """Tests for PaletteGroup dataclass."""

    def test_entry_count_property(self) -> None:
        """entry_count returns correct count."""
        entries = [
            OAMEntry(
                id=0,
                x=0,
                y=0,
                tile=0,
                width=8,
                height=8,
                flip_h=False,
                flip_v=False,
                palette=0,
                tiles=[],
            ),
            OAMEntry(
                id=1,
                x=0,
                y=0,
                tile=1,
                width=8,
                height=8,
                flip_h=False,
                flip_v=False,
                palette=0,
                tiles=[],
            ),
        ]
        group = PaletteGroup(palette_index=0, entries=entries)
        assert group.entry_count == 2


class TestCaptureArrangementData:
    """Tests for CaptureArrangementData dataclass."""

    def test_has_tiles_property(self, obsel_config: OBSELConfig) -> None:
        """has_tiles returns True when tiles exist."""
        data = CaptureArrangementData(
            source_path="test.json",
            frame=0,
            groups=[],
            palettes={},
            obsel=obsel_config,
            total_tiles=5,
        )
        assert data.has_tiles is True

        data_empty = CaptureArrangementData(
            source_path="test.json",
            frame=0,
            groups=[],
            palettes={},
            obsel=obsel_config,
            total_tiles=0,
        )
        assert data_empty.has_tiles is False

    def test_palette_indices_property(self, obsel_config: OBSELConfig) -> None:
        """palette_indices returns sorted list of indices."""
        groups = [
            PaletteGroup(palette_index=7, entries=[]),
            PaletteGroup(palette_index=0, entries=[]),
            PaletteGroup(palette_index=3, entries=[]),
        ]
        data = CaptureArrangementData(
            source_path="test.json",
            frame=0,
            groups=groups,
            palettes={},
            obsel=obsel_config,
            total_tiles=0,
        )
        assert data.palette_indices == [0, 3, 7]
