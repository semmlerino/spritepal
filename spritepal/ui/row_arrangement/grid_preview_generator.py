"""
Grid-based preview generation for flexible sprite arrangements
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw
from PIL.ImageDraw import ImageDraw as ImageDrawType

from .grid_arrangement_manager import (
    ArrangementType,
    GridArrangementManager,
    TilePosition,
)
from .grid_image_processor import GridImageProcessor
from .palette_colorizer import PaletteColorizer
from .preview_generator import PreviewGenerator


class GridPreviewGenerator(PreviewGenerator):
    """Extended preview generator with grid-based arrangement support"""

    def __init__(self, colorizer: PaletteColorizer | None = None):
        super().__init__(colorizer)
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

    def create_grid_arranged_image(
        self,
        processor: GridImageProcessor,
        manager: GridArrangementManager,
        spacing: int = 0,
    ) -> Image.Image | None:
        """Create image from grid arrangement

        Args:
            processor: Grid image processor with extracted tiles
            manager: Grid arrangement manager with arrangement data
            spacing: Spacing between tiles in pixels

        Returns:
            Arranged image or None if no arrangement
        """
        arrangement_order = manager.get_arrangement_order()
        if not arrangement_order:
            return None

        # Collect all tiles in arrangement order
        arranged_tiles = []

        for arr_type, key in arrangement_order:
            if arr_type == ArrangementType.TILE:
                # Single tile
                row, col = map(int, key.split(","))
                position = TilePosition(row, col)
                tile_img = processor.get_tile(position)
                if tile_img:
                    arranged_tiles.append((position, tile_img))

            elif arr_type == ArrangementType.ROW:
                # Entire row
                row_index = int(key)
                row_tiles = processor.get_row_tiles(row_index)
                arranged_tiles.extend(row_tiles)

            elif arr_type == ArrangementType.COLUMN:
                # Entire column
                col_index = int(key)
                col_tiles = processor.get_column(col_index)
                arranged_tiles.extend(col_tiles)

            elif arr_type == ArrangementType.GROUP:
                # Custom group
                group = manager.get_groups().get(key)
                if group:
                    group_tiles = processor.get_tile_group(group)
                    arranged_tiles.extend(group_tiles)

        if not arranged_tiles:
            return None

        # Calculate output dimensions
        # For now, use a default width that creates a reasonable layout
        default_width = min(16, processor.grid_cols)  # Max 16 tiles wide
        return self._create_arranged_image_with_spacing(
            arranged_tiles,
            processor.tile_width,
            processor.tile_height,
            default_width,
            spacing,
        )

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
                if output.mode == "RGBA" and display_img.mode == "RGBA":
                    output.paste(display_img, (x, y), display_img)
                elif output.mode == "RGBA" and display_img.mode != "RGBA":
                    rgba_img = display_img.convert("RGBA")
                    output.paste(rgba_img, (x, y), rgba_img)
                else:
                    output.paste(display_img, (x, y))

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
                {"type": arr_type.value, "key": key}
                for arr_type, key in manager.get_arrangement_order()
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
        }
