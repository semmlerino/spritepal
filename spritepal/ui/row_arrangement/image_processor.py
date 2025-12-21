"""
Image processing for sprite row extraction
"""
from __future__ import annotations

from typing import Any

from PIL import Image

from core.exceptions import FileFormatError


class RowImageProcessor:
    """Handles sprite image loading and row extraction"""

    def __init__(self) -> None:
        self.tile_width: int = 0
        self.tile_height: int = 0

    def load_sprite(self, sprite_path: str) -> Image.Image:
        """Load sprite image and convert to appropriate mode

        Args:
            sprite_path: Path to the sprite image file

        Returns:
            Loaded image in grayscale mode

        Raises:
            Exception: If image cannot be loaded
        """
        try:
            # Load the sprite sheet
            image = Image.open(sprite_path)

            # Convert palette mode images to grayscale for proper display
            if image.mode == "P":
                # Convert palette indices to actual grayscale values
                image = image.convert("L")
            elif image.mode not in ["L", "1"]:
                # Convert any other mode (RGB, RGBA, etc.) to grayscale
                image = image.convert("L")

        except Exception as e:
            raise FileFormatError(f"Error loading sprite: {e}") from e
        else:
            return image

    def calculate_tile_dimensions(
        self, image: Image.Image, tiles_per_row: int
    ) -> tuple[int, int]:
        """Calculate tile dimensions based on image width and tiles per row

        Args:
            image: The sprite sheet image
            tiles_per_row: Number of tiles in each row

        Returns:
            Tuple of (tile_width, tile_height)

        Raises:
            ValueError: If tiles_per_row is not positive
        """
        if tiles_per_row <= 0:
            raise ValueError(f"tiles_per_row must be positive, got {tiles_per_row}")

        # Calculate tile width based on tiles_per_row
        tile_width = image.width // tiles_per_row
        # Assume square tiles (most common case)
        tile_height = tile_width

        # Store for later use
        self.tile_width = tile_width
        self.tile_height = tile_height

        return tile_width, tile_height

    def extract_rows(self, image: Image.Image, tiles_per_row: int) -> list[dict[str, Any]]:
        """Extract individual rows from sprite sheet

        Args:
            image: The sprite sheet image
            tiles_per_row: Number of tiles in each row

        Returns:
            List of row data dictionaries with 'index', 'image', and 'tiles' keys
        """
        # Calculate dimensions if not already done
        if self.tile_width == 0 or self.tile_height == 0:
            self.calculate_tile_dimensions(image, tiles_per_row)

        tile_rows = []
        image_width = image.width
        image_height = image.height

        # Extract each row as a separate image
        num_rows = image_height // self.tile_height

        for row_idx in range(num_rows):
            y_start = row_idx * self.tile_height
            y_end = y_start + self.tile_height

            # Crop row
            row_image = image.crop((0, y_start, image_width, y_end))

            tile_rows.append(
                {
                    "index": row_idx,
                    "image": row_image,
                    "tiles": image_width // self.tile_width,
                }
            )

        return tile_rows

    def process_sprite_sheet(
        self, sprite_path: str, tiles_per_row: int
    ) -> tuple[Image.Image, list[dict[str, Any]]]:
        """Complete sprite processing pipeline

        Args:
            sprite_path: Path to the sprite image file
            tiles_per_row: Number of tiles in each row

        Returns:
            Tuple of (original_image, tile_rows_list)
        """
        # Load and convert image
        image = self.load_sprite(sprite_path)

        # Extract rows
        tile_rows = self.extract_rows(image, tiles_per_row)

        return image, tile_rows
