"""
Preview generation for arranged sprite rows
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from PIL import Image

from utils.image_utils import create_output_image, paste_with_mode_handling

from .palette_colorizer import PaletteColorizer


class ArrangementPreviewGenerator:
    """Generates preview images for sprite row arrangements"""

    def __init__(self, colorizer: PaletteColorizer | None = None):
        """Initialize preview generator

        Args:
            colorizer: palette colorizer for colorized previews
        """
        self.colorizer = colorizer

    def create_arranged_image(
        self,
        original_image: Image.Image,
        tile_rows: list[dict[str, Any]],  # pyright: ignore[reportExplicitAny] - Row metadata
        arranged_indices: list[int],
        tile_height: int,
        row_spacing_ratio: float = 0.75,
    ) -> Image.Image | None:
        """Create image with arranged rows

        Args:
            original_image: The original sprite sheet image
            tile_rows: List of row data dictionaries
            arranged_indices: List of row indices in arrangement order
            tile_height: Height of each tile
            row_spacing_ratio: Ratio of tile height for spacing (default 0.75)

        Returns:
            Arranged image or None if no rows
        """
        if not arranged_indices:
            return None

        # Calculate row spacing (reduced from full tile height for tighter packing)
        row_spacing = int(tile_height * row_spacing_ratio)

        # Calculate total height using reduced spacing
        if len(arranged_indices) == 1:
            new_height = tile_height
        else:
            new_height = (len(arranged_indices) - 1) * row_spacing + tile_height
        new_width = original_image.width

        # Create output image with appropriate mode
        use_rgba = self.colorizer is not None and self.colorizer.is_palette_mode()
        arranged = create_output_image(new_width, new_height, use_rgba, original_image)

        # Copy rows in new arrangement
        y_offset = 0
        for row_idx in arranged_indices:
            if row_idx < len(tile_rows):
                # Get row data
                row_data = tile_rows[row_idx]
                grayscale_image = row_data["image"]

                # Get the appropriate display image (grayscale or colorized)
                if self.colorizer:
                    row_image = self.colorizer.get_display_image(row_idx, grayscale_image)
                else:
                    row_image = grayscale_image

                if row_image:
                    paste_with_mode_handling(arranged, row_image, (0, y_offset))

                y_offset += row_spacing

        return arranged

    def apply_palette_to_full_image(self, image: Image.Image) -> Image.Image | None:
        """Apply current palette to a full image (for original preview)

        Args:
            image: The image to colorize

        Returns:
            Colorized image or None if no colorizer/palettes
        """
        if not self.colorizer or not self.colorizer.is_palette_mode():
            return None

        # Use a special index (-1) to indicate full image colorization
        return self.colorizer.get_display_image(-1, image)

    def export_arranged_image(self, sprite_path: str, arranged_image: Image.Image, num_rows: int) -> str:
        """Export the arranged sprite sheet to a file

        Args:
            sprite_path: Original sprite file path for naming
            arranged_image: The arranged image to save
            num_rows: Number of rows in arrangement (for logging)

        Returns:
            Path to the exported file
        """
        # Generate output path
        base_name = Path(sprite_path).stem
        output_path = f"{base_name}_arranged.png"

        # Save arranged image
        arranged_image.save(output_path)

        return output_path

    def generate_output_filename(self, sprite_path: str, suffix: str = "_arranged") -> str:
        """Generate output filename based on input path

        Args:
            sprite_path: Original sprite file path
            suffix: Suffix to add before extension

        Returns:
            Generated output filename
        """
        base_name = Path(sprite_path).stem
        return f"{base_name}{suffix}.png"
