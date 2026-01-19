"""Tests for _build_rom_map_from_capture in GridArrangementDialog.

Tests the conversion of capture arrangement data + VRAM attribution
into ROMMapData for tile reinjection.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest
from PIL import Image
from pytestqt.qtbot import QtBot

from core.mesen_integration.capture_to_arrangement import (
    CaptureArrangementData,
    PaletteGroup,
)
from core.mesen_integration.click_extractor import OBSELConfig


@pytest.fixture
def test_sprite_path(tmp_path: Path) -> str:
    """Create a test sprite image and return its path."""
    test_image_path = tmp_path / "test_sprite.png"
    # Create a 16x16 image (2x2 8x8 tiles)
    test_image = Image.new("RGB", (16, 16), color="white")
    test_image.save(test_image_path)
    return str(test_image_path)


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
def sample_tile_image() -> Image.Image:
    """Create a sample 8x8 tile image."""
    return Image.new("RGBA", (8, 8), (255, 0, 0, 255))


@pytest.fixture
def sample_palette_group(sample_tile_image: Image.Image) -> PaletteGroup:
    """Create a sample PaletteGroup with tiles and VRAM addresses."""
    tiles = {
        (0, 0): sample_tile_image,
        (0, 1): sample_tile_image,
        (1, 0): sample_tile_image,
        (1, 1): sample_tile_image,
    }
    vram_addresses = {
        (0, 0): 0x6000,
        (0, 1): 0x6020,
        (1, 0): 0x6200,
        (1, 1): 0x6220,
    }
    return PaletteGroup(
        palette_index=7,
        entries=[],
        tiles=tiles,
        width_tiles=2,
        height_tiles=2,
        vram_addresses=vram_addresses,
    )


@pytest.fixture
def sample_capture_data(
    obsel_config: OBSELConfig,
    sample_palette_group: PaletteGroup,
) -> CaptureArrangementData:
    """Create sample CaptureArrangementData."""
    return CaptureArrangementData(
        source_path="/path/to/sprite_capture_frame100.json",
        frame=100,
        groups=[sample_palette_group],
        palettes={7: [(0, 0, 0)] + [(255, 0, 0)] * 15},
        obsel=obsel_config,
        total_tiles=4,
    )


@dataclass
class MockAttributionMap:
    """Mock VRAM attribution map for testing."""

    offsets: dict[int, int]  # vram_addr -> rom_offset

    def get_rom_offset(self, vram_addr: int) -> int | None:
        """Get ROM offset for VRAM address."""
        return self.offsets.get(vram_addr)


@pytest.fixture
def attribution_map() -> MockAttributionMap:
    """Create mock attribution map with VRAM -> ROM mappings."""
    return MockAttributionMap(
        offsets={
            0x6000: 0x017000,
            0x6020: 0x017020,
            0x6200: 0x017200,
            0x6220: 0x017220,
        }
    )


class TestBuildRomMapFromCapture:
    """Tests for _build_rom_map_from_capture method."""

    def test_creates_rom_map_data(
        self,
        qtbot: QtBot,
        test_sprite_path: str,
        sample_capture_data: CaptureArrangementData,
        attribution_map: MockAttributionMap,
        app_context: object,
    ) -> None:
        """Method creates valid ROMMapData from capture + attribution."""
        from ui.grid_arrangement_dialog import GridArrangementDialog

        dialog = GridArrangementDialog(test_sprite_path, tiles_per_row=16)
        qtbot.addWidget(dialog)

        result = dialog._build_rom_map_from_capture(
            sample_capture_data,
            attribution_map,
            "/path/to/capture.json",
        )

        assert result is not None
        assert len(result.tiles) == 4
        assert result.frame_name == "capture"
        assert result.palette_index == 7

    def test_maps_vram_to_rom_offsets(
        self,
        qtbot: QtBot,
        test_sprite_path: str,
        sample_capture_data: CaptureArrangementData,
        attribution_map: MockAttributionMap,
        app_context: object,
    ) -> None:
        """VRAM addresses are correctly mapped to ROM offsets."""
        from ui.grid_arrangement_dialog import GridArrangementDialog

        dialog = GridArrangementDialog(test_sprite_path, tiles_per_row=16)
        qtbot.addWidget(dialog)

        result = dialog._build_rom_map_from_capture(
            sample_capture_data,
            attribution_map,
            "/path/to/capture.json",
        )

        assert result is not None

        # Check that ROM offsets match expected values
        rom_offsets = {t.rom_offset for t in result.tiles}
        assert 0x017000 in rom_offsets
        assert 0x017020 in rom_offsets
        assert 0x017200 in rom_offsets
        assert 0x017220 in rom_offsets

    def test_preserves_grid_positions(
        self,
        qtbot: QtBot,
        test_sprite_path: str,
        sample_capture_data: CaptureArrangementData,
        attribution_map: MockAttributionMap,
        app_context: object,
    ) -> None:
        """Grid positions are correctly preserved in ROMTile objects."""
        from ui.grid_arrangement_dialog import GridArrangementDialog

        dialog = GridArrangementDialog(test_sprite_path, tiles_per_row=16)
        qtbot.addWidget(dialog)

        result = dialog._build_rom_map_from_capture(
            sample_capture_data,
            attribution_map,
            "/path/to/capture.json",
        )

        assert result is not None

        # Find tile at position (0, 0)
        tile_00 = next((t for t in result.tiles if t.row == 0 and t.col == 0), None)
        assert tile_00 is not None
        assert tile_00.rom_offset == 0x017000

        # Find tile at position (1, 1)
        tile_11 = next((t for t in result.tiles if t.row == 1 and t.col == 1), None)
        assert tile_11 is not None
        assert tile_11.rom_offset == 0x017220

    def test_returns_none_for_no_mappings(
        self,
        qtbot: QtBot,
        test_sprite_path: str,
        sample_capture_data: CaptureArrangementData,
        app_context: object,
    ) -> None:
        """Returns None when no tiles have ROM mappings."""
        from ui.grid_arrangement_dialog import GridArrangementDialog

        dialog = GridArrangementDialog(test_sprite_path, tiles_per_row=16)
        qtbot.addWidget(dialog)

        # Attribution map with no matching entries
        empty_attribution = MockAttributionMap(offsets={})

        result = dialog._build_rom_map_from_capture(
            sample_capture_data,
            empty_attribution,
            "/path/to/capture.json",
        )

        assert result is None

    def test_handles_partial_attribution(
        self,
        qtbot: QtBot,
        test_sprite_path: str,
        sample_capture_data: CaptureArrangementData,
        app_context: object,
    ) -> None:
        """Handles case where only some tiles have ROM mappings."""
        from ui.grid_arrangement_dialog import GridArrangementDialog

        dialog = GridArrangementDialog(test_sprite_path, tiles_per_row=16)
        qtbot.addWidget(dialog)

        # Attribution map with only 2 of 4 tiles mapped
        partial_attribution = MockAttributionMap(
            offsets={
                0x6000: 0x017000,
                0x6220: 0x017220,
            }
        )

        result = dialog._build_rom_map_from_capture(
            sample_capture_data,
            partial_attribution,
            "/path/to/capture.json",
        )

        assert result is not None
        assert len(result.tiles) == 2

    def test_multiple_groups_with_row_offset(
        self,
        qtbot: QtBot,
        test_sprite_path: str,
        obsel_config: OBSELConfig,
        sample_tile_image: Image.Image,
        attribution_map: MockAttributionMap,
        app_context: object,
    ) -> None:
        """Multiple groups are offset correctly (same as _populate_from_capture_data)."""
        from ui.grid_arrangement_dialog import GridArrangementDialog

        # Create two groups
        group1 = PaletteGroup(
            palette_index=7,
            entries=[],
            tiles={(0, 0): sample_tile_image},
            width_tiles=1,
            height_tiles=1,
            vram_addresses={(0, 0): 0x6000},
        )
        group2 = PaletteGroup(
            palette_index=0,
            entries=[],
            tiles={(0, 0): sample_tile_image},
            width_tiles=1,
            height_tiles=1,
            vram_addresses={(0, 0): 0x6020},
        )

        capture_data = CaptureArrangementData(
            source_path="test.json",
            frame=100,
            groups=[group1, group2],
            palettes={7: [(0, 0, 0)] * 16, 0: [(0, 0, 0)] * 16},
            obsel=obsel_config,
            total_tiles=2,
        )

        # Attribution for both tiles
        attribution = MockAttributionMap(
            offsets={
                0x6000: 0x017000,
                0x6020: 0x017020,
            }
        )

        dialog = GridArrangementDialog(test_sprite_path, tiles_per_row=16)
        qtbot.addWidget(dialog)

        result = dialog._build_rom_map_from_capture(
            capture_data,
            attribution,
            "test.json",
        )

        assert result is not None
        assert len(result.tiles) == 2

        # First group at row 0
        tile1 = next((t for t in result.tiles if t.rom_offset == 0x017000), None)
        assert tile1 is not None
        assert tile1.row == 0

        # Second group at row 2 (height_tiles=1 + 1 spacing = 2)
        tile2 = next((t for t in result.tiles if t.rom_offset == 0x017020), None)
        assert tile2 is not None
        assert tile2.row == 2  # 0 + 1 (height) + 1 (spacing) = 2

    def test_vram_word_conversion(
        self,
        qtbot: QtBot,
        test_sprite_path: str,
        sample_capture_data: CaptureArrangementData,
        attribution_map: MockAttributionMap,
        app_context: object,
    ) -> None:
        """VRAM byte addresses are correctly converted to word addresses."""
        from ui.grid_arrangement_dialog import GridArrangementDialog

        dialog = GridArrangementDialog(test_sprite_path, tiles_per_row=16)
        qtbot.addWidget(dialog)

        result = dialog._build_rom_map_from_capture(
            sample_capture_data,
            attribution_map,
            "/path/to/capture.json",
        )

        assert result is not None

        # VRAM byte 0x6000 -> word 0x3000
        tile = next((t for t in result.tiles if t.rom_offset == 0x017000), None)
        assert tile is not None
        assert tile.vram_word == 0x3000  # 0x6000 // 2
