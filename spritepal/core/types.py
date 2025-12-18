"""
Type aliases for SpritePal to improve type safety and readability.

This module defines common type aliases used throughout the codebase
to make type annotations more readable and consistent.

Moved from utils/type_aliases.py to fix layer boundary violations
(utils should be stdlib-only per docs/architecture.md).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, NotRequired, TypeAlias, TypedDict

from PIL import Image
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QWidget

# External library types for better type checking
# Use concrete PIL Image type to avoid forward reference issues
PILImage: TypeAlias = Image.Image
ImageMode: TypeAlias = str  # "RGB", "RGBA", "L", "P"
ImageSize: TypeAlias = tuple[int, int]

# Complex data structures for sprite manipulation
TileMatrix: TypeAlias = list[list[list[int]]]
SpriteData: TypeAlias = tuple[TileMatrix, int]
SimilarityScore: TypeAlias = float
# Core sprite and ROM data types (defined early to avoid forward references)
SpriteOffset: TypeAlias = int

# Complex search result types (now that SpriteOffset is defined)
SimilarityResult: TypeAlias = tuple[SpriteOffset, SimilarityScore]
SearchResults: TypeAlias = list[SimilarityResult]
PaletteData: TypeAlias = list[int]
RGBColor: TypeAlias = tuple[int, int, int]
ROMData: TypeAlias = bytes
TileData: TypeAlias = bytes

# Preview and image types
PreviewPixmap: TypeAlias = QPixmap | None
PreviewSize: TypeAlias = tuple[int, int]
TileCount: TypeAlias = int

# Worker and callback types
WorkerCallback: TypeAlias = Callable[[Any], None]
ProgressCallback: TypeAlias = Callable[[int, str], None]
ErrorCallback: TypeAlias = Callable[[str, Exception], None]

# UI and widget types
WidgetParent: TypeAlias = QWidget | None
DialogResult: TypeAlias = bool

# File path types
FilePath: TypeAlias = str
OutputPath: TypeAlias = str
CachePath: TypeAlias = str


# Extraction parameter TypedDicts (centralized to prevent drift)
class VRAMExtractionParams(TypedDict):
    """Parameters for VRAM-based sprite extraction."""

    vram_path: str
    output_base: str
    create_grayscale: bool
    create_metadata: bool
    grayscale_mode: bool
    cgram_path: NotRequired[str | None]
    oam_path: NotRequired[str | None]
    vram_offset: NotRequired[int | None]


class ROMExtractionParams(TypedDict):
    """Parameters for ROM-based sprite extraction."""

    rom_path: str
    sprite_offset: int
    sprite_name: str
    output_base: str
    cgram_path: NotRequired[str | None]


# Configuration and settings types
ConfigDict: TypeAlias = dict[str, Any]
SettingsValue: TypeAlias = Any
ValidationResult: TypeAlias = tuple[bool, str | None]

# Signal types for Qt
StringSignal: TypeAlias = str
IntSignal: TypeAlias = int
BoolSignal: TypeAlias = bool
ListSignal: TypeAlias = list[Any]
DictSignal: TypeAlias = dict[str, Any]

# Manager operation types
OperationName: TypeAlias = str
OperationResult: TypeAlias = bool
OperationProgress: TypeAlias = tuple[int, int]  # (current, total)

# Cache types
CacheKey: TypeAlias = str
CacheData: TypeAlias = Any
CacheStats: TypeAlias = dict[str, int | float]

# Navigation types (for smart sprite discovery)
NavigationHint: TypeAlias = dict[str, Any]
SpriteLocation: TypeAlias = dict[str, Any]
RegionMap: TypeAlias = dict[str, Any]

# Re-export for backward compatibility
__all__ = [
    "BoolSignal",
    "CacheData",
    "CacheKey",
    "CachePath",
    "CacheStats",
    "ConfigDict",
    "DialogResult",
    "DictSignal",
    "ErrorCallback",
    "FilePath",
    "ImageMode",
    "ImageSize",
    "IntSignal",
    "ListSignal",
    "NavigationHint",
    "OperationName",
    "OperationProgress",
    "OperationResult",
    "OutputPath",
    "PILImage",
    "PaletteData",
    "PreviewPixmap",
    "PreviewSize",
    "ProgressCallback",
    "RGBColor",
    "ROMData",
    "ROMExtractionParams",
    "RegionMap",
    "SearchResults",
    "SettingsValue",
    "SimilarityResult",
    "SimilarityScore",
    "SpriteData",
    "SpriteLocation",
    "SpriteOffset",
    "StringSignal",
    "TileCount",
    "TileData",
    "TileMatrix",
    "VRAMExtractionParams",
    "ValidationResult",
    "WidgetParent",
    "WorkerCallback",
]
