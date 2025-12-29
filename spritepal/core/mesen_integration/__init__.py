"""
Mesen 2 integration for live sprite capture and extraction.

This package provides tools to:
1. Parse sprite capture data from Mesen 2 Lua scripts
2. Reassemble multi-OAM sprites using captured layout info
3. Extract complete sprites from ROM for editing
4. Map VRAM tiles back to ROM offsets via tile hash database
"""

from core.mesen_integration.capture_renderer import (
    CaptureRenderer,
    render_capture_to_files,
)
from core.mesen_integration.click_extractor import (
    CaptureResult,
    MesenCaptureParser,
    OAMEntry,
    OBSELConfig,
    TileData,
)
from core.mesen_integration.gfx_pointer_table import (
    GFXPointerTableParser,
    rom_to_sa1_cpu,
    sa1_cpu_to_rom,
)
from core.mesen_integration.tile_hash_database import (
    TileHashDatabase,
    TileMatch,
    build_and_save_database,
)

__all__ = [
    "CaptureRenderer",
    "CaptureResult",
    "GFXPointerTableParser",
    "MesenCaptureParser",
    "OAMEntry",
    "OBSELConfig",
    "TileData",
    "TileHashDatabase",
    "TileMatch",
    "build_and_save_database",
    "render_capture_to_files",
    "rom_to_sa1_cpu",
    "sa1_cpu_to_rom",
]
