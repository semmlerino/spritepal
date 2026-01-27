from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from core.mesen_integration.click_extractor import CaptureResult, OAMEntry, OBSELConfig, TileData
from core.services.rom_verification_service import ROMVerificationService


class DummyMatcher:
    def __init__(self, _rom_path: str) -> None:
        pass

    def build_database(self) -> None:
        return None

    def lookup_vram_tile(self, _tile_data: bytes) -> list:
        return []


def test_verify_offsets_fills_missing_offsets_when_enabled(tmp_path: Path) -> None:
    tile_bytes = b"\xab" * 32
    target_offset = 0x200
    rom_path = tmp_path / "game.sfc"
    rom_path.write_bytes(b"\x00" * target_offset + tile_bytes + b"\x00" * 64)

    tile = TileData(
        tile_index=0,
        vram_addr=0x1000,
        pos_x=0,
        pos_y=0,
        data_hex=tile_bytes.hex(),
        rom_offset=None,
    )
    entry = OAMEntry(
        id=1,
        x=0,
        y=0,
        tile=0,
        width=8,
        height=8,
        flip_h=False,
        flip_v=False,
        palette=0,
        tiles=[tile],
    )
    capture = CaptureResult(
        frame=0,
        visible_count=1,
        obsel=OBSELConfig(
            raw=0,
            name_base=0,
            name_select=0,
            size_select=0,
            tile_base_addr=0,
            oam_base_addr=0,
            oam_addr_offset=0,
        ),
        entries=[entry],
        palettes={0: [0] * 16},
        timestamp=0,
    )

    verifier = ROMVerificationService(rom_path)
    with patch("core.mesen_integration.rom_tile_matcher.ROMTileMatcher", DummyMatcher):
        result = verifier.verify_offsets(capture, include_missing=True)

    assert tile.rom_offset == target_offset
    assert result.missing_total == 1
    assert result.missing_filled == 1
    assert result.missing_not_found == 0
