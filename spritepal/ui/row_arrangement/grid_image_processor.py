"""
Grid-based image processing for flexible sprite extraction
"""
from __future__ import annotations

import os

from PIL import Image

from utils.exceptions import TileError

from .grid_arrangement_manager import TileGroup, TilePosition
from .image_processor import RowImageProcessor


class GridImageProcessor(RowImageProcessor):
    """Extended image processor with grid-based tile extraction capabilities"""

    def __init__(self) -> None:
        super().__init__()
        self.tiles: dict[TilePosition, Image.Image] = {}
        self.grid_rows = 0
        self.grid_cols = 0
        self.original_image: Image.Image | None = None

    def extract_tiles_as_grid(
        self, image: Image.Image, tiles_per_row: int
    ) -> dict[TilePosition, Image.Image]:
        """Extract individual tiles from sprite sheet into a grid structure

        Args:
            image: The sprite sheet image
            tiles_per_row: Number of tiles in each row

        Returns:
            Dictionary mapping tile positions to tile images

        Raises:
            ValueError: If tiles_per_row is invalid or grid dimensions are invalid
        """
        # Validate input parameters
        if tiles_per_row <= 0:
            raise ValueError(f"tiles_per_row must be positive, got {tiles_per_row}")

        if not image or image.width <= 0 or image.height <= 0:
            raise ValueError("Invalid image dimensions")

        # Calculate dimensions if not already done
        if self.tile_width == 0 or self.tile_height == 0:
            self.calculate_tile_dimensions(image, tiles_per_row)

        # Validate tile dimensions
        if self.tile_width <= 0 or self.tile_height <= 0:
            raise ValueError(
                f"Invalid tile dimensions: {self.tile_width}x{self.tile_height}"
            )

        if self.tiles:
            self.tiles.clear()

        # Calculate grid dimensions
        self.grid_cols = image.width // self.tile_width
        self.grid_rows = image.height // self.tile_height

        # Validate grid dimensions
        if self.grid_cols <= 0 or self.grid_rows <= 0:
            raise ValueError(
                f"Invalid grid dimensions: {self.grid_cols}x{self.grid_rows}"
            )

        # Extract each tile
        for row in range(self.grid_rows):
            for col in range(self.grid_cols):
                x_start = col * self.tile_width
                y_start = row * self.tile_height
                x_end = x_start + self.tile_width
                y_end = y_start + self.tile_height

                # Crop tile
                tile_image = image.crop((x_start, y_start, x_end, y_end))
                position = TilePosition(row, col)
                self.tiles[position] = tile_image

        return self.tiles

    def get_tile(self, position: TilePosition) -> Image.Image | None:
        """Get a specific tile by position

        Args:
            position: The tile position

        Returns:
            The tile image or None if not found
        """
        return self.tiles.get(position)

    def get_column(self, col_index: int) -> list[tuple[TilePosition, Image.Image]]:
        """Extract all tiles in a column

        Args:
            col_index: The column index

        Returns:
            List of (position, image) tuples for the column
        """
        column_tiles = []
        for row in range(self.grid_rows):
            position = TilePosition(row, col_index)
            if position in self.tiles:
                column_tiles.append((position, self.tiles[position]))
        return column_tiles

    def get_row_tiles(self, row_index: int) -> list[tuple[TilePosition, Image.Image]]:
        """Extract all tiles in a row

        Args:
            row_index: The row index

        Returns:
            List of (position, image) tuples for the row
        """
        row_tiles = []
        for col in range(self.grid_cols):
            position = TilePosition(row_index, col)
            if position in self.tiles:
                row_tiles.append((position, self.tiles[position]))
        return row_tiles

    def get_tile_group(
        self, group: TileGroup
    ) -> list[tuple[TilePosition, Image.Image]]:
        """Get all tiles in a group

        Args:
            group: The tile group

        Returns:
            List of (position, image) tuples for the group
        """
        group_tiles = []
        for position in group.tiles:
            if position in self.tiles:
                group_tiles.append((position, self.tiles[position]))
        return group_tiles

    def create_image_from_tiles(
        self,
        tiles: list[tuple[TilePosition, Image.Image]],
        arrangement_width: int | None = None,
    ) -> Image.Image:
        """Create a single image from a list of tiles

        Args:
            tiles: List of (position, image) tuples
            arrangement_width: Width of the arrangement in tiles (None for auto)

        Returns:
            Combined image
        """
        if not tiles:
            return Image.new("L", (1, 1))

        # If no arrangement width specified, calculate based on tile positions
        if arrangement_width is None:
            max_col = max(pos.col for pos, _ in tiles)
            min_col = min(pos.col for pos, _ in tiles)
            arrangement_width = max_col - min_col + 1

        # Calculate image dimensions
        num_tiles = len(tiles)
        arrangement_height = (num_tiles + arrangement_width - 1) // arrangement_width

        img_width = arrangement_width * self.tile_width
        img_height = arrangement_height * self.tile_height

        # Create output image
        output = Image.new("L", (img_width, img_height))

        # Place tiles
        for i, (_position, tile_img) in enumerate(tiles):
            x = (i % arrangement_width) * self.tile_width
            y = (i // arrangement_width) * self.tile_height
            output.paste(tile_img, (x, y))

        return output

    def create_column_strip(self, col_index: int) -> Image.Image | None:
        """Create a vertical strip image from a column

        Args:
            col_index: The column index

        Returns:
            Column strip image or None if column is empty
        """
        column_tiles = self.get_column(col_index)
        if not column_tiles:
            return None

        # Create vertical strip
        strip_width = self.tile_width
        strip_height = len(column_tiles) * self.tile_height

        strip = Image.new("L", (strip_width, strip_height))

        for i, (_position, tile_img) in enumerate(column_tiles):
            y = i * self.tile_height
            strip.paste(tile_img, (0, y))

        return strip

    def create_row_strip(self, row_index: int) -> Image.Image | None:
        """Create a horizontal strip image from a row

        Args:
            row_index: The row index

        Returns:
            Row strip image or None if row is empty
        """
        row_tiles = self.get_row_tiles(row_index)
        if not row_tiles:
            return None

        # Create horizontal strip
        strip_width = len(row_tiles) * self.tile_width
        strip_height = self.tile_height

        strip = Image.new("L", (strip_width, strip_height))

        for i, (_position, tile_img) in enumerate(row_tiles):
            x = i * self.tile_width
            strip.paste(tile_img, (x, 0))

        return strip

    def create_group_image(
        self, group: TileGroup, preserve_layout: bool = True
    ) -> Image.Image | None:
        """Create an image from a tile group

        Args:
            group: The tile group
            preserve_layout: If True, preserve relative positions; if False, pack tightly

        Returns:
            Group image or None if group is empty
        """
        group_tiles = self.get_tile_group(group)
        if not group_tiles:
            return None

        if preserve_layout:
            # Find bounding box
            positions = [pos for pos, _ in group_tiles]
            min_row = min(p.row for p in positions)
            max_row = max(p.row for p in positions)
            min_col = min(p.col for p in positions)
            max_col = max(p.col for p in positions)

            # Create image with proper dimensions
            img_width = (max_col - min_col + 1) * self.tile_width
            img_height = (max_row - min_row + 1) * self.tile_height

            output = Image.new("L", (img_width, img_height), 0)

            # Place tiles at relative positions
            for position, tile_img in group_tiles:
                x = (position.col - min_col) * self.tile_width
                y = (position.row - min_row) * self.tile_height
                output.paste(tile_img, (x, y))
        else:
            # Pack tiles tightly
            output = self.create_image_from_tiles(group_tiles, group.width)

        return output

    def process_sprite_sheet_as_grid(
        self, sprite_path: str, tiles_per_row: int
    ) -> tuple[Image.Image, dict[TilePosition, Image.Image]]:
        """Complete sprite processing pipeline for grid-based extraction

        Args:
            sprite_path: Path to the sprite image file
            tiles_per_row: Number of tiles in each row

        Returns:
            Tuple of (original_image, tiles_dict)

        Raises:
            FileNotFoundError: If sprite file doesn't exist
            ValueError: If sprite file is invalid or grid parameters are invalid
            Exception: For other processing errors
        """
        # Validate file exists
        if not os.path.exists(sprite_path):
            raise FileNotFoundError(f"Sprite file not found: {sprite_path}")

        try:
            # Load and convert image
            image = self.load_sprite(sprite_path)

            # Store original image for preview generation
            self.original_image = image

            # Extract tiles
            tiles = self.extract_tiles_as_grid(image, tiles_per_row)

        except Exception as e:
            # Clean up on error
            self.original_image = None
            if self.tiles:
                self.tiles.clear()
            raise TileError(f"Error processing sprite sheet: {e}") from e
        else:
            return image, tiles
