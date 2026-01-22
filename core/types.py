"""
Type aliases for SpritePal to improve type safety and readability.

This module defines common type aliases used throughout the codebase
to make type annotations more readable and consistent.

Moved from utils/type_aliases.py to fix layer boundary violations
(utils should be stdlib-only per docs/architecture.md).
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from enum import Enum
from typing import Literal, NotRequired, Protocol, TypeAlias, TypedDict, cast, runtime_checkable

from PIL import Image
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QWidget


class CompressionType(Enum):
    """Type of compression used for sprite data.

    Used to track whether extracted sprite data was HAL-compressed or raw,
    which affects how injection should be performed.
    """

    HAL = "hal"  # HAL compression (standard for Kirby games)
    RAW = "raw"  # Uncompressed raw tile data
    UNKNOWN = "unknown"  # Compression type not yet determined


@runtime_checkable
class CancellationToken(Protocol):
    """Protocol for cancellation tokens that provide an is_set() method.

    This matches the interface of threading.Event and can be used to
    check if an operation should be cancelled.
    """

    def is_set(self) -> bool:
        """Return True if cancellation has been requested."""
        ...


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


class InjectTabParams(TypedDict):
    """Parameters from the Inject Tab UI."""

    png_file: str
    vram_file: str
    rom_file: str
    offset: int
    output_file: str


class ExtractTabParams(TypedDict):
    """Parameters from the Extract Tab UI."""

    vram_file: str
    rom_file: str
    offset: int
    size: int
    tiles_per_row: int
    use_palette: bool
    cgram_file: str | None
    palette_num: int | None


class SpriteInfo(TypedDict):
    """Information about a sprite found during ROM scanning.

    Consolidates duplicate definitions from rom_extractor.py, sprite_finder.py,
    and scan_controller.py (SpriteInfoDict).

    Required fields (always present after scan):
        offset: Raw byte offset in ROM
        offset_hex: Hexadecimal string representation (e.g., "0x8000")
        compressed_size: Size of compressed sprite data in bytes
        decompressed_size: Size after HAL decompression
        tile_count: Number of 8x8 tiles in sprite
        alignment: Memory alignment info (e.g., "word", "page")
        quality: Decompression quality score (0.0-1.0)

    Optional fields (context-dependent):
        size_limit_used: Present when scan used size limit heuristic
        size: Alternative size field (deprecated, use compressed_size)
        name: Present when sprite has a known name from config
    """

    offset: int
    offset_hex: str
    compressed_size: int
    decompressed_size: int
    tile_count: int
    alignment: str
    quality: float
    # Optional fields - see docstring for when each is present
    size_limit_used: NotRequired[int]
    size: NotRequired[int]
    name: NotRequired[str]


class ROMHeaderInfo(TypedDict):
    """ROM header information from read_rom_header()."""

    title: str
    rom_type: str
    checksum: str


class ScanParams(TypedDict):
    """Parameters for ROM scanning operations."""

    start_offset: int
    end_offset: int
    step: int


class WindowGeometry(TypedDict):
    """Window position and size settings."""

    window_width: int
    window_height: int
    window_x: int
    window_y: int
    restore_position: bool
    theme: NotRequired[str]


class CacheMetadata(TypedDict):
    """Cache entry metadata."""

    created_at: float
    expires_at: float
    size_bytes: int
    source: str


class SpriteSearchResult(TypedDict):
    """Result from sprite search operations."""

    offset: int
    quality: float
    size: int
    metadata: NotRequired[dict[str, object]]


class ParsedMetadataInfo(TypedDict):
    """Result from load_metadata()."""

    metadata: dict[str, object]
    source_type: str
    extraction: dict[str, object] | None


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


class SpriteLocationData(TypedDict):
    """Typed sprite location data matching SpritePointer structure.

    This TypedDict mirrors the SpritePointer dataclass from core/rom_injector.py
    for use in serialization and type-safe dict access.

    Required fields:
        offset: Raw byte offset in ROM where sprite data begins
        bank: SNES memory bank number (0x00-0xFF)
        address: Address within bank (0x0000-0xFFFF)

    Optional fields:
        compressed_size: Size of compressed data if known
        offset_variants: Alternative offsets for sprite variations
    """

    offset: int
    bank: int
    address: int
    compressed_size: NotRequired[int | None]
    offset_variants: NotRequired[list[int] | None]


# Literal types for mode values and status
PresetSource = Literal["builtin", "user", "imported"]
InjectionMode = Literal["rom", "vram"]
SourceType = Literal["rom", "vram"]
OperationStatus = Literal["success", "failed", "pending", "cancelled"]


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
            offset=cast(int, data.get("offset", 0)),
            game_title=str(data.get("game_title", "")),
            game_checksums=list(cast(Iterable[int], data.get("game_checksums", []))),
            description=str(data.get("description", "")),
            compressed=bool(data.get("compressed", True)),
            estimated_size=cast(int, data.get("estimated_size", 8192)),
            tags=list(cast(Iterable[str], data.get("tags", []))),
            source=cast(PresetSource, data.get("source", "user")),
            verified=bool(data.get("verified", False)),
        )


class PaletteEntry(TypedDict):
    """A single palette entry in default_palettes.json."""

    index: int
    name: str
    colors: list[RGBColor]


class PaletteCategory(TypedDict):
    """A category of palettes (e.g., 'kirby_normal') in default_palettes.json."""

    description: str
    palettes: list[PaletteEntry]


class DefaultPalettesJson(TypedDict):
    """Structure of the default_palettes.json file."""

    format_version: str
    description: str
    palettes: dict[str, PaletteCategory]


class ExtractionMetadata(TypedDict):
    """Metadata about a sprite extraction, saved in .metadata.json."""

    source_type: SourceType
    rom_source: NotRequired[str]
    vram_source: NotRequired[str]
    rom_offset: NotRequired[str]
    vram_offset: NotRequired[str]
    sprite_name: NotRequired[str]
    compressed_size: NotRequired[int]
    tile_count: int
    extraction_size: int
    rom_title: NotRequired[str]
    rom_checksum: NotRequired[str]
    rom_palettes_used: NotRequired[bool]
    default_palettes_used: NotRequired[bool]
    palette_count: int


# Re-export for backward compatibility
__all__ = [
    "CacheData",
    "CacheKey",
    "CacheMetadata",
    "CachePath",
    "CacheStats",
    "ConfigDict",
    "DefaultPalettesJson",
    "DialogResult",
    "ErrorCallback",
    "ExtractionMetadata",
    "FilePath",
    "InjectionMode",
    "NavigationHint",
    "OperationName",
    "OperationProgress",
    "OperationResult",
    "OperationStatus",
    "OutputPath",
    "PILImage",
    "PaletteCategory",
    "PaletteData",
    "PaletteEntry",
    "ParsedMetadataInfo",
    "PresetSource",
    "PreviewPixmap",
    "PreviewSize",
    "ProgressCallback",
    "RGBColor",
    "ROMData",
    "ROMExtractionParams",
    "ROMHeaderInfo",
    "ScanParams",
    "SearchResults",
    "SettingsValue",
    "SimilarityResult",
    "SimilarityScore",
    "SourceType",
    "SpriteInfo",
    "SpriteLocationData",
    "SpriteOffset",
    "SpritePreset",
    "SpriteSearchResult",
    "TileCount",
    "TileData",
    "VRAMExtractionParams",
    "ValidationResult",
    "WidgetParent",
    "WindowGeometry",
    "WorkerCallback",
]
