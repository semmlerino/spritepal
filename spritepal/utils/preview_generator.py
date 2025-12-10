"""
Preview Generator Service - DEPRECATED LOCATION

This module has been moved to core/services/preview_generator.py to fix
layer boundary violations (utils/ should only contain stdlib-only code,
but this module requires Qt).

This file re-exports all symbols from the new location for backward compatibility.
New code should import directly from core.services.preview_generator.
"""
from __future__ import annotations

# Re-export everything from the new location for backward compatibility
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

__all__ = [
    "PreviewGenerator",
    "PreviewRequest",
    "PreviewResult",
    "PaletteData",
    "LRUCache",
    "get_preview_generator",
    "cleanup_preview_generator",
    "create_vram_preview_request",
    "create_rom_preview_request",
]
