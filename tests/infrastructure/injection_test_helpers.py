"""Helpers for testing injection workflows.

Provides mock injectors that capture injected images for test assertions,
enabling output-based testing rather than mocking PIL internals.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

from PIL import Image

from core.tile_utils import encode_4bpp_tile


def make_solid_tile_hex(palette_index: int) -> str:
    """Create 4bpp tile data where all pixels use the given palette index.

    Args:
        palette_index: Palette index (0-15) for all 64 pixels.

    Returns:
        Hex string of 32 bytes of 4bpp tile data.
    """
    pixels = [palette_index] * 64
    return encode_4bpp_tile(pixels).hex().upper()


class InjectingMockROMInjector:
    """Mock ROMInjector that captures images for test assertions.

    Usage:
        mock_injector = InjectingMockROMInjector()

        with patch("core.services.injection_orchestrator.ROMInjector",
                   return_value=mock_injector):
            controller.inject_mapping(...)

        # Assert on captured images
        assert len(mock_injector.injected_images) == 1
        img = mock_injector.injected_images[0]
        assert img.getpixel((0, 0)) == (255, 0, 0, 255)
    """

    def __init__(
        self,
        *,
        tile_count: int = 4,
        success: bool = True,
        error_message: str = "Success",
    ) -> None:
        """Initialize mock injector.

        Args:
            tile_count: Number of tiles to report in find_compressed_sprite.
                       Used to control HAL decompression size (tile_count * 32 bytes).
            success: Whether inject_sprite_to_rom should succeed.
            error_message: Message to return from inject_sprite_to_rom.
        """
        self.injected_images: list[Image.Image] = []
        self.inject_calls: list[dict[str, Any]] = []
        self._tile_count = tile_count
        self._success = success
        self._error_message = error_message

        # Create a backing mock for any unexpected attribute access
        self._mock = MagicMock()

    def __getattr__(self, name: str) -> Any:
        """Delegate unknown attributes to backing mock."""
        return getattr(self._mock, name)

    def find_compressed_sprite(
        self,
        rom_data: bytes,
        offset: int,
        **kwargs: object,
    ) -> tuple[bytes, bytes, int]:
        """Return fake compressed sprite data.

        Returns:
            (compressed_data, decompressed_data, compressed_length)
        """
        decompressed_size = self._tile_count * 32  # 32 bytes per 4bpp tile
        return (
            b"\x00" * 100,  # compressed data (dummy)
            b"\x00" * decompressed_size,  # decompressed data
            100,  # compressed length
        )

    def inject_sprite_to_rom(
        self,
        sprite_path: str,
        rom_path: str,
        output_path: str,
        sprite_offset: int,
        **kwargs: object,
    ) -> tuple[bool, str]:
        """Capture the injected image and return success/failure.

        Reads the image file before the caller might delete it, storing
        a copy for later assertions.
        """
        img = Image.open(sprite_path)
        self.injected_images.append(img.copy())
        self.inject_calls.append(
            {
                "sprite_path": Path(sprite_path),
                "rom_path": Path(rom_path),
                "output_path": Path(output_path),
                "sprite_offset": sprite_offset,
                **kwargs,
            }
        )
        return (self._success, self._error_message)

    @property
    def last_injected_image(self) -> Image.Image | None:
        """Get the most recently injected image, or None if no injections."""
        return self.injected_images[-1] if self.injected_images else None

    @property
    def last_inject_call(self) -> dict[str, Any] | None:
        """Get the most recent inject call metadata, or None if no calls."""
        return self.inject_calls[-1] if self.inject_calls else None
