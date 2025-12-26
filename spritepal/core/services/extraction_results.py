"""Result types for extraction operations.

These dataclasses replace signal emissions in services, providing structured
return values that the manager uses to emit signals.
"""

from dataclasses import dataclass, field

from PIL.Image import Image

# Type alias for palette data: dict of palette_index -> list of [r,g,b] colors
PaletteData = dict[int, list[list[int]]]


@dataclass(frozen=True)
class PaletteExtractionResult:
    """Result from palette extraction operations."""

    files: list[str] = field(default_factory=list)
    palettes: PaletteData = field(default_factory=dict)
    active_palette_indices: list[int] = field(default_factory=list)


@dataclass(frozen=True)
class ExtractionResult:
    """Result from ROM or VRAM extraction operations."""

    files: list[str]
    preview_image: Image | None = None
    tile_count: int = 0
    palettes: PaletteData = field(default_factory=dict)
    active_palette_indices: list[int] = field(default_factory=list)
    warning: str | None = None


@dataclass(frozen=True)
class TilePreviewData:
    """Raw tile data result from preview generation (ROM only).

    Note: This is distinct from core.services.preview_generator.PreviewResult,
    which contains rendered QPixmap and PIL.Image. This class holds the raw
    tile bytes before rendering.
    """

    tile_data: bytes
    width: int
    height: int
