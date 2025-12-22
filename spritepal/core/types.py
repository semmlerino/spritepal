"""
Type aliases for SpritePal to improve type safety and readability.

This module defines common type aliases used throughout the codebase
to make type annotations more readable and consistent.

Moved from utils/type_aliases.py to fix layer boundary violations
(utils should be stdlib-only per docs/architecture.md).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Literal, NotRequired, TypeAlias, TypedDict

from PIL import Image
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QWidget

# External library types for better type checking
# Use concrete PIL Image type to avoid forward reference issues
PILImage: TypeAlias = Image.Image
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
WorkerCallback: TypeAlias = Callable[[object], None]
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


class SpriteInfo(TypedDict):
    """Information about a sprite found during ROM scanning.

    Consolidates duplicate definitions from rom_extractor.py, sprite_finder.py,
    and scan_controller.py (SpriteInfoDict).
    """

    offset: int
    offset_hex: str
    compressed_size: int
    decompressed_size: int
    tile_count: int
    alignment: str
    quality: float
    # Optional fields (from SpriteInfoDict)
    size_limit_used: NotRequired[int]
    size: NotRequired[int]
    name: NotRequired[str]


# Configuration and settings types
ConfigDict: TypeAlias = dict[str, object]
SettingsValue: TypeAlias = object
ValidationResult: TypeAlias = tuple[bool, str | None]

# Manager operation types
OperationName: TypeAlias = str
OperationResult: TypeAlias = bool
OperationProgress: TypeAlias = tuple[int, int]  # (current, total)

# Cache types
CacheKey: TypeAlias = str
CacheData: TypeAlias = object
CacheStats: TypeAlias = dict[str, int | float]

# Navigation types (for smart sprite discovery)
NavigationHint: TypeAlias = dict[str, object]
SpriteLocation: TypeAlias = dict[str, object]
RegionMap: TypeAlias = dict[str, object]


# Preset source type
PresetSource = Literal["builtin", "user", "imported"]


@dataclass
class SpritePreset:
    """A user-managed sprite preset for quick access to known sprite locations.

    This dataclass represents a sprite offset that has been saved for reuse,
    with metadata to help match it to the correct ROM and provide context.
    """

    name: str
    offset: int
    game_title: str
    game_checksums: list[int] = field(default_factory=list)
    description: str = ""
    compressed: bool = True
    estimated_size: int = 8192
    tags: list[str] = field(default_factory=list)
    source: PresetSource = "user"
    verified: bool = False

    def to_dict(self) -> dict[str, object]:
        """Convert to dictionary for JSON serialization."""
        return {
            "name": self.name,
            "offset": self.offset,
            "game_title": self.game_title,
            "game_checksums": self.game_checksums,
            "description": self.description,
            "compressed": self.compressed,
            "estimated_size": self.estimated_size,
            "tags": self.tags,
            "source": self.source,
            "verified": self.verified,
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> SpritePreset:
        """Create a SpritePreset from a dictionary."""
        return cls(
            name=str(data.get("name", "")),
            offset=int(data.get("offset", 0)),  # type: ignore[arg-type]
            game_title=str(data.get("game_title", "")),
            game_checksums=list(data.get("game_checksums", [])),  # type: ignore[arg-type]
            description=str(data.get("description", "")),
            compressed=bool(data.get("compressed", True)),
            estimated_size=int(data.get("estimated_size", 8192)),  # type: ignore[arg-type]
            tags=list(data.get("tags", [])),  # type: ignore[arg-type]
            source=data.get("source", "user"),  # type: ignore[arg-type]
            verified=bool(data.get("verified", False)),
        )


# Re-export for backward compatibility
__all__ = [
    "CacheData",
    "CacheKey",
    "CachePath",
    "CacheStats",
    "ConfigDict",
    "DialogResult",
    "ErrorCallback",
    "FilePath",
    "NavigationHint",
    "OperationName",
    "OperationProgress",
    "OperationResult",
    "OutputPath",
    "PILImage",
    "PaletteData",
    "PresetSource",
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
    "SpriteInfo",
    "SpriteLocation",
    "SpriteOffset",
    "SpritePreset",
    "TileCount",
    "TileData",
    "VRAMExtractionParams",
    "ValidationResult",
    "WidgetParent",
    "WorkerCallback",
]
