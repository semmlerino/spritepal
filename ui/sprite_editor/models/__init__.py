#!/usr/bin/env python3
"""
Data models for the unified sprite editor.
Provides models for images, palettes, VRAM, and project state.
"""

# Re-export IndexedImageModel as ImageModel for backward compatibility
# The core version is authoritative and supports configurable bit depth
from core.editing import IndexedImageModel as ImageModel

from .palette_model import PaletteModel

__all__ = [
    "ImageModel",
    "PaletteModel",
]
