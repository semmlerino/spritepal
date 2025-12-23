"""
Core services package.

This package contains service classes that provide cross-cutting functionality
used by both core and UI layers. Services in this package:

- worker_lifecycle.py: WorkerManager for QThread worker lifecycle management
- preview_generator.py: PreviewGenerator for async preview image generation
- rom_service.py: ROMService for ROM-based sprite extraction operations
- vram_service.py: VRAMService for VRAM-based sprite extraction operations
- rom_cache.py: ROMCache for ROM scan result caching
- path_suggestion_service.py: PathSuggestionService for intelligent path suggestions

Settings management is now consolidated in ApplicationStateManager (core/managers/).

These services are placed in core/ rather than utils/ because they depend on Qt
or core layer types. The utils/ package is reserved for pure Python utilities
with only stdlib dependencies.
"""
from __future__ import annotations

from core.services.path_suggestion_service import PathSuggestionService
from core.services.preview_generator import (
    LRUCache,
    PaletteData,
    PreviewGenerator,
    PreviewRequest,
    PreviewResult,
    cleanup_preview_generator,
    create_rom_preview_request,
    create_vram_preview_request,
    get_preview_generator,
)
from core.services.rom_cache import ROMCache
from core.services.rom_service import ROMService
from core.services.vram_service import VRAMService
from core.services.worker_lifecycle import WorkerManager

__all__ = [
    "LRUCache",
    "PaletteData",
    # Path suggestion
    "PathSuggestionService",
    # Preview generator
    "PreviewGenerator",
    "PreviewRequest",
    "PreviewResult",
    # ROM and VRAM services
    "ROMCache",
    "ROMService",
    "VRAMService",
    # Worker lifecycle
    "WorkerManager",
    "cleanup_preview_generator",
    "create_rom_preview_request",
    "create_vram_preview_request",
    "get_preview_generator",
]
