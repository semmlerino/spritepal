"""
Core services package.

This package contains service classes that provide cross-cutting functionality
used by both core and UI layers. Services in this package:

- worker_lifecycle.py: WorkerManager for QThread worker lifecycle management
- preview_generator.py: PreviewGenerator for async preview image generation

These services are placed in core/ rather than utils/ because they depend on Qt.
The utils/ package is reserved for pure Python utilities with no Qt dependencies.
"""
from __future__ import annotations

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
from core.services.worker_lifecycle import WorkerManager

__all__ = [
    "LRUCache",
    "PaletteData",
    # Preview generator
    "PreviewGenerator",
    "PreviewRequest",
    "PreviewResult",
    # Worker lifecycle
    "WorkerManager",
    "cleanup_preview_generator",
    "create_rom_preview_request",
    "create_vram_preview_request",
    "get_preview_generator",
]
