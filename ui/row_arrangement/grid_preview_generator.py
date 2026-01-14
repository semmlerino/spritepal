"""
Grid-based preview generation for flexible sprite arrangements
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw
from PIL.ImageDraw import ImageDraw as ImageDrawType

from utils.image_utils import paste_with_mode_handling

from .grid_arrangement_manager import (
    ArrangementType,
    GridArrangementManager,
    TilePosition,
)
from .grid_image_processor import GridImageProcessor
from .palette_colorizer import PaletteColorizer


class GridPreviewGenerator:
    """Extended preview generator with grid-based arrangement support"""

    def __init__(self, colorizer: PaletteColorizer | None = None):
        """Initialize preview generator

        Args:
            colorizer: palette colorizer for colorized previews
        """
        self.colorizer = colorizer
        self.grid_color = (128, 128, 128, 128)  # Semi-transparent gray for grid lines
        self.selection_color = (
            255,
            255,
            0,
            64,
        )  # Semi-transparent yellow for selection
        self.group_colors = [  # Different colors for different groups
            (255, 0, 0, 64),  # Red
            (0, 255, 0, 64),  # Green
            (0, 0, 255, 64),  # Blue
            (255, 128, 0, 64),  # Orange
            (128, 0, 255, 64),  # Purple
            (0, 255, 255, 64),  # Cyan
        ]

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

    def create_grid_arranged_image(
        self,
        processor: GridImageProcessor,
        manager: GridArrangementManager,
        spacing: int = 0,
        width: int | None = None,
    ) -> Image.Image | None:
        """Create image from grid arrangement.

        If grid_mapping is available, creates a spatial layout preserving gaps.
        Otherwise falls back to linear layout based on arrangement_order.

        Args:
            processor: Grid image processor with extracted tiles
            manager: Grid arrangement manager with arrangement data
            spacing: Spacing between tiles in pixels
            width: Width of the arrangement in tiles (None for default)

        Returns:
            Arranged image or None if no arrangement
        """
        grid_mapping = manager.get_grid_mapping()
        if grid_mapping:
            return self._create_spatial_arranged_image(processor, manager, grid_mapping, spacing, width)

        arrangement_order = manager.get_arrangement_order()
        if not arrangement_order:
            return None

        # Collect all tiles in arrangement order
        arranged_tiles = []
        for arr_type, key in arrangement_order:
            if arr_type == ArrangementType.TILE:
                try:
                    row, col = map(int, key.split(","))
                    position = TilePosition(row, col)
                    tile_img = processor.get_tile(position)
                    if tile_img:
                        arranged_tiles.append((position, tile_img))
                except (ValueError, IndexError):
                    continue
            elif arr_type == ArrangementType.ROW:
                try:
                    row_index = int(key)
                    row_tiles = processor.get_row_tiles(row_index)
                    arranged_tiles.extend(row_tiles)
                except (ValueError, IndexError):
                    continue
            elif arr_type == ArrangementType.COLUMN:
                try:
                    col_index = int(key)
                    col_tiles = processor.get_column(col_index)
                    arranged_tiles.extend(col_tiles)
                except (ValueError, IndexError):
                    continue
            elif arr_type == ArrangementType.GROUP:
                group = manager.get_groups().get(key)
                if group:
                    group_tiles = processor.get_tile_group(group)
                    arranged_tiles.extend(group_tiles)

        if not arranged_tiles:
            return None

        if width is None:
            width = min(16, processor.grid_cols)

        return self._create_arranged_image_with_spacing(
            arranged_tiles,
            processor.tile_width,
            processor.tile_height,
            width,
            spacing,
        )

    def _create_spatial_arranged_image(
        self,
        processor: GridImageProcessor,
        manager: GridArrangementManager,
        grid_mapping: dict[tuple[int, int], tuple[ArrangementType, str]],
        spacing: int = 0,
        width: int | None = None,
    ) -> Image.Image | None:
        """Create image that preserves spatial layout including gaps."""
        # Find bounds
        rows = [p[0] for p in grid_mapping]
        cols = [p[1] for p in grid_mapping]
        max_r = max(rows) if rows else 0
        max_c = max(cols) if cols else 0

        # Set output dimensions in tiles
        if width is not None and width > 0:
            out_tiles_w = max(width, max_c + 1)
        else:
            out_tiles_w = max_c + 1
        out_tiles_h = max_r + 1

        # Calculate pixel dimensions
        img_w = out_tiles_w * processor.tile_width + (out_tiles_w - 1) * spacing
        img_h = out_tiles_h * processor.tile_height + (out_tiles_h - 1) * spacing

        # Determine output mode
        if self.colorizer and self.colorizer.is_palette_mode():
            output = Image.new("RGBA", (img_w, img_h), (0, 0, 0, 0))
        else:
            output = Image.new("L", (img_w, img_h), 0)

        # Place items from grid mapping
        for (r, c), (arr_type, key) in grid_mapping.items():
            items_to_draw = []
            if arr_type == ArrangementType.TILE:
                try:
                    row_p, col_p = map(int, key.split(","))
                    pos = TilePosition(row_p, col_p)
                    img = processor.get_tile(pos)
                    if img:
                        items_to_draw.append((r, c, pos, img))
                except (ValueError, IndexError):
                    continue
            elif arr_type == ArrangementType.ROW:
                try:
                    row_idx = int(key)
                    row_tiles = processor.get_row_tiles(row_idx)
                    for i, (pos, img) in enumerate(row_tiles):
                        items_to_draw.append((r, c + i, pos, img))
                except (ValueError, IndexError):
                    continue
            elif arr_type == ArrangementType.COLUMN:
                try:
                    col_idx = int(key)
                    col_tiles = processor.get_column(col_idx)
                    for i, (pos, img) in enumerate(col_tiles):
                        items_to_draw.append((r + i, c, pos, img))
                except (ValueError, IndexError):
                    continue
            elif arr_type == ArrangementType.GROUP:
                group = manager.get_groups().get(key)
                if group and group.tiles:
                    min_row = min(p.row for p in group.tiles)
                    min_col = min(p.col for p in group.tiles)
                    for p in group.tiles:
                        img = processor.get_tile(p)
                        if img:
                            dr = p.row - min_row
                            dc = p.col - min_col
                            items_to_draw.append((r + dr, c + dc, p, img))

            # Draw the collected tiles for this item
            for tr, tc, t_pos, t_img in items_to_draw:
                x = tc * (processor.tile_width + spacing)
                y = tr * (processor.tile_height + spacing)
                
                # Apply colorization if enabled
                if self.colorizer:
                    display_img = self.colorizer.get_display_image(t_pos.row, t_img)
                else:
                    display_img = t_img

                if display_img:
                    paste_with_mode_handling(output, display_img, (x, y))

        return output

    def create_grid_preview_with_overlay(
        self,
        processor: GridImageProcessor,
        manager: GridArrangementManager,
        show_grid: bool = True,
        show_selection: bool = True,
        selected_tiles: list[TilePosition] | None = None,
    ) -> Image.Image:
        """Create a preview of the original sprite sheet with grid overlay and selections

        Args:
            processor: Grid image processor with original image
            manager: Grid arrangement manager with arrangement data
            show_grid: Whether to show grid lines
            show_selection: Whether to show selected/arranged tiles
            selected_tiles: Additional tiles to highlight

        Returns:
            Preview image with overlays
        """
        # Start with original image (convert to RGBA for overlay)
        base_image = processor.original_image
        if not base_image:
            return Image.new("RGBA", (1, 1))

        # Apply colorization if enabled
        if self.colorizer and self.colorizer.is_palette_mode():
            colorized = self.apply_palette_to_full_image(base_image)
            if colorized:
                base_image = colorized

        # Convert to RGBA for overlay support
        if base_image.mode != "RGBA":
            preview = base_image.convert("RGBA")
        else:
            preview = base_image.copy()

        # Create overlay
        overlay = Image.new("RGBA", preview.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)

        # Draw grid lines if enabled
        if show_grid:
            self._draw_grid(
                draw,
                processor.tile_width,
                processor.tile_height,
                processor.grid_cols,
                processor.grid_rows,
            )

        # Highlight arranged tiles
        if show_selection:
            arranged_tiles = manager.get_arranged_tiles()
            groups = manager.get_groups()

            # Draw group highlights first (under individual tiles)
            for color_index, group in enumerate(groups.values()):
                color = self.group_colors[color_index % len(self.group_colors)]
                for tile_pos in group.tiles:
                    self._highlight_tile(
                        draw,
                        tile_pos,
                        processor.tile_width,
                        processor.tile_height,
                        color,
                    )

            # Draw individual tile highlights
            for tile_pos in arranged_tiles:
                if not manager.get_tile_group(tile_pos):  # Not part of a group
                    self._highlight_tile(
                        draw,
                        tile_pos,
                        processor.tile_width,
                        processor.tile_height,
                        self.selection_color,
                    )

        # Highlight additional selected tiles
        if selected_tiles:
            for tile_pos in selected_tiles:
                self._highlight_tile(
                    draw,
                    tile_pos,
                    processor.tile_width,
                    processor.tile_height,
                    (0, 255, 255, 64),
                )

        # Composite overlay onto preview
        return Image.alpha_composite(preview, overlay)

    def _create_arranged_image_with_spacing(
        self,
        tiles: list[tuple[TilePosition, Image.Image]],
        tile_width: int,
        tile_height: int,
        tiles_per_row: int,
        spacing: int,
    ) -> Image.Image:
        """Create arranged image with optional spacing between tiles"""
        if not tiles:
            return Image.new("L", (1, 1))

        # Guard against invalid tiles_per_row
        if tiles_per_row <= 0:
            return Image.new("L", (1, 1))

        num_tiles = len(tiles)
        num_rows = (num_tiles + tiles_per_row - 1) // tiles_per_row

        # Calculate dimensions with spacing
        img_width = tiles_per_row * tile_width + (tiles_per_row - 1) * spacing
        img_height = num_rows * tile_height + (num_rows - 1) * spacing

        # Determine output mode based on colorization
        if self.colorizer and self.colorizer.is_palette_mode():
            output = Image.new("RGBA", (img_width, img_height), (0, 0, 0, 0))
        else:
            output = Image.new("L", (img_width, img_height), 0)

        # Place tiles
        for i, (position, tile_img) in enumerate(tiles):
            row = i // tiles_per_row
            col = i % tiles_per_row

            x = col * (tile_width + spacing)
            y = row * (tile_height + spacing)

            # Apply colorization if enabled
            if self.colorizer:
                display_img = self.colorizer.get_display_image(position.row, tile_img)
            else:
                display_img = tile_img

            if display_img:
                paste_with_mode_handling(output, display_img, (x, y))

        return output

    def _draw_grid(
        self,
        draw: ImageDrawType,
        tile_width: int,
        tile_height: int,
        cols: int,
        rows: int,
    ) -> None:
        """Draw grid lines on the image"""
        width = cols * tile_width
        height = rows * tile_height

        # Draw vertical lines
        for col in range(cols + 1):
            x = col * tile_width
            draw.line([(x, 0), (x, height)], fill=self.grid_color, width=1)

        # Draw horizontal lines
        for row in range(rows + 1):
            y = row * tile_height
            draw.line([(0, y), (width, y)], fill=self.grid_color, width=1)

    def _highlight_tile(
        self,
        draw: ImageDrawType,
        position: TilePosition,
        tile_width: int,
        tile_height: int,
        color: tuple[int, int, int, int],
    ) -> None:
        """Highlight a single tile"""
        x = position.col * tile_width
        y = position.row * tile_height
        draw.rectangle([x, y, x + tile_width, y + tile_height], fill=color)

    def export_grid_arrangement(
        self,
        sprite_path: str,
        arranged_image: Image.Image,
        arrangement_type: str = "grid",
    ) -> str:
        """Export grid-arranged sprite sheet

        Args:
            sprite_path: Original sprite file path
            arranged_image: The arranged image
            arrangement_type: Type of arrangement for filename

        Returns:
            Path to exported file
        """
        base_name = Path(sprite_path).stem
        output_path = f"{base_name}_{arrangement_type}_arranged.png"

        arranged_image.save(output_path)
        return output_path

    def create_arrangement_preview_data(
        self, manager: GridArrangementManager, processor: GridImageProcessor
    ) -> dict[str, Any]:  # pyright: ignore[reportExplicitAny] - Arrangement configuration
        """Create data structure describing the arrangement for saving/loading

        Args:
            manager: Grid arrangement manager
            processor: Grid image processor

        Returns:
            Dictionary with arrangement data
        """
        return {
            "grid_dimensions": {
                "rows": processor.grid_rows,
                "cols": processor.grid_cols,
                "tile_width": processor.tile_width,
                "tile_height": processor.tile_height,
            },
            "arrangement_order": [
                {"type": arr_type.value, "key": key} for arr_type, key in manager.get_arrangement_order()
            ],
            "groups": [
                {
                    "id": group.id,
                    "name": group.name,
                    "width": group.width,
                    "height": group.height,
                    "tiles": [{"row": t.row, "col": t.col} for t in group.tiles],
                }
                for group in manager.get_groups().values()
            ],
            "total_tiles": manager.get_arranged_count(),
            "grid_mapping": {
                f"{r},{c}": {"type": arr_type.value, "key": key}
                for (r, c), (arr_type, key) in manager.get_grid_mapping().items()
            },
        }
