"""
Core services package.

This package contains service classes that provide cross-cutting functionality
used by both core and UI layers. Services in this package:

- worker_lifecycle.py: WorkerManager for QThread worker lifecycle management
- preview_generator.py: PreviewGenerator for async preview image generation
- rom_cache.py: ROMCache for ROM scan result caching
- path_suggestion_service.py: Path suggestion functions (validate_path, find_vram_path, etc.)
- extraction_results.py: Result dataclasses for extraction operations

Settings management is now consolidated in ApplicationStateManager (core/managers/).

These services are placed in core/ rather than utils/ because they depend on Qt
or core layer types. The utils/ package is reserved for pure Python utilities
with only stdlib dependencies.
"""

from __future__ import annotations

from core.services.path_suggestion_service import (
    find_suggested_input_vram,
    find_vram_path,
    get_smart_vram_suggestion,
    suggest_output_path,
    suggest_output_rom_path,
    suggest_output_vram_path,
    validate_path,
)
from core.services.preview_generator import (
    PaletteData,
    PreviewCache,
    PreviewGenerator,
    PreviewRequest,
    PreviewResult,
    create_rom_preview_request,
    create_vram_preview_request,
)
from core.services.rom_cache import ROMCache
from core.services.tile_sampling_service import (
    TileCoord,
    TileSampleResult,
    TileSamplingService,
    calculate_auto_alignment,
)
from core.services.worker_lifecycle import WorkerManager

__all__ = [
    "PaletteData",
    "PreviewCache",
    "PreviewGenerator",
    "PreviewRequest",
    "PreviewResult",
    "ROMCache",
    "TileCoord",
    "TileSampleResult",
    "TileSamplingService",
    "WorkerManager",
    "calculate_auto_alignment",
    "create_rom_preview_request",
    "create_vram_preview_request",
    "find_suggested_input_vram",
    "find_vram_path",
    "get_smart_vram_suggestion",
    "suggest_output_path",
    "suggest_output_rom_path",
    "suggest_output_vram_path",
    "validate_path",
]
