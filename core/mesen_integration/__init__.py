"""
Mesen 2 integration for live sprite capture and extraction.

This package provides tools to:
1. Parse sprite capture data from Mesen 2 Lua scripts
2. Reassemble multi-OAM sprites using captured layout info
3. Extract complete sprites from ROM for editing
4. Map VRAM tiles back to ROM offsets via tile hash database
"""

from core.mesen_integration.address_space_bridge import (
    BankRegisters,
    CanonicalAddress,
    CanonicalRange,
    addresses_match,
    is_bwram_staging,
    is_iram_staging,
    is_wram_staging,
    normalize_dma_source,
    sa1_to_canonical,
    scpu_to_canonical,
)
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
from core.mesen_integration.full_correlation_pipeline import (
    CorrelationPipeline,
    PipelineResults,
    ROMMatch,
    format_pipeline_report,
)
from core.mesen_integration.gfx_pointer_table import (
    GFXPointerTableParser,
    rom_to_sa1_cpu,
    sa1_cpu_to_rom,
)
from core.mesen_integration.log_watcher import (
    CapturedOffset,
    LogWatcher,
)
from core.mesen_integration.rom_tile_matcher import (
    ROMTileMatcher,
    TileLocation,
)
from core.mesen_integration.sa1_character_conversion import (
    TWO_PLANE_COMBOS,
    analyze_tile_planes,
    bitmap_to_snes_4bpp,
    convert_tileset_to_bitmap,
    convert_tileset_to_snes,
    extract_two_planes,
    get_two_plane_candidates,
    get_zero_planes,
    hash_bitmap_as_snes,
    hash_packed_as_snes,
    hash_snes_tile,
    hash_two_planes,
    is_packed_2bpp_candidate,
    packed_2bpp_to_snes_4bpp,
    snes_4bpp_to_bitmap,
    snes_4bpp_to_packed_2bpp,
)
from core.mesen_integration.tile_hash_database import (
    TileHashDatabase,
    TileMatch,
    build_and_save_database,
)
from core.mesen_integration.timing_correlator import (
    CorrelationResults,
    DMAEvent,
    SpriteCapture,
    SpriteTile,
    TileCorrelation,
    TimingCorrelator,
    format_correlation_report,
    generate_correlation_json,
)

__all__ = [
    "TWO_PLANE_COMBOS",
    "BankRegisters",
    "CanonicalAddress",
    "CanonicalRange",
    "CaptureRenderer",
    "CaptureResult",
    "CapturedOffset",
    "CorrelationPipeline",
    "CorrelationResults",
    "DMAEvent",
    "GFXPointerTableParser",
    "LogWatcher",
    "MesenCaptureParser",
    "OAMEntry",
    "OBSELConfig",
    "PipelineResults",
    "ROMMatch",
    "ROMTileMatcher",
    "SpriteCapture",
    "SpriteTile",
    "TileCorrelation",
    "TileData",
    "TileHashDatabase",
    "TileLocation",
    "TileMatch",
    "TimingCorrelator",
    "addresses_match",
    "analyze_tile_planes",
    "bitmap_to_snes_4bpp",
    "build_and_save_database",
    "convert_tileset_to_bitmap",
    "convert_tileset_to_snes",
    "extract_two_planes",
    "format_correlation_report",
    "format_pipeline_report",
    "generate_correlation_json",
    "get_two_plane_candidates",
    "get_zero_planes",
    "hash_bitmap_as_snes",
    "hash_packed_as_snes",
    "hash_snes_tile",
    "hash_two_planes",
    "is_bwram_staging",
    "is_iram_staging",
    "is_packed_2bpp_candidate",
    "is_wram_staging",
    "normalize_dma_source",
    "packed_2bpp_to_snes_4bpp",
    "render_capture_to_files",
    "rom_to_sa1_cpu",
    "sa1_cpu_to_rom",
    "sa1_to_canonical",
    "scpu_to_canonical",
    "snes_4bpp_to_bitmap",
    "snes_4bpp_to_packed_2bpp",
]
