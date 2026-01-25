"""Signal payload dataclasses for typed Qt signals.

These dataclasses provide typed payloads for Qt signals, replacing raw
tuples with structured, self-documenting data. Signals using these should
be declared as Signal(object) and emit the dataclass instance.

Example:
    # Signal definition
    paletteSourceAdded = Signal(object)  # PaletteSourcePayload

    # Emission
    self.paletteSourceAdded.emit(PaletteSourcePayload(
        name="ROM Palette 8",
        source_type="rom",
        index=8,
        colors=[(255, 0, 0), ...],
        is_active=True,
    ))

    # Connection with type hint
    signal.connect(lambda payload: handle_palette_source(payload))
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class PaletteSourcePayload:
    """Payload for palette source added signals.

    Attributes:
        name: Display name for the source (e.g., "Mesen2 #1", "ROM Palette 8")
        source_type: Type of source ("default", "mesen", "rom", "preset", "file")
        index: Palette index (0-15 for ROM, 0+ for others)
        colors: List of RGB tuples for the palette colors
        is_active: Whether this palette is OAM-active (detected in use)
    """

    name: str
    source_type: str
    index: int
    colors: list[tuple[int, int, int]] = field(default_factory=list)
    is_active: bool = False


@dataclass(frozen=True)
class PreviewData:
    """Payload for sprite preview ready signals.

    Contains all data needed to display a ROM sprite preview, including
    the raw tile data, dimensions, compression information, and metadata.

    Attributes:
        tile_data: Raw decompressed tile data bytes
        width: Preview image width in pixels
        height: Preview image height in pixels
        sprite_name: Display name for the sprite (e.g., "manual_0x3C6EF1")
        compressed_size: Size of compressed data in ROM (bytes)
        slack_size: Unused bytes at end of compressed block
        actual_offset: ROM offset where data was found (may differ from request)
        hal_succeeded: True if HAL decompression was used successfully
        header_bytes: Raw HAL header bytes (for debugging/display)
    """

    tile_data: bytes
    width: int
    height: int
    sprite_name: str = ""
    compressed_size: int = 0
    slack_size: int = 0
    actual_offset: int = -1
    hal_succeeded: bool = True
    header_bytes: bytes = b""
