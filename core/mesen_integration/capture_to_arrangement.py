"""Convert Mesen 2 sprite captures to arrangement grid tiles.

This module provides functionality to:
1. Group OAM entries by palette
2. Render each group's sprites
3. Split into 8x8 tiles for grid arrangement
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from PIL import Image

from core.mesen_integration.capture_renderer import CaptureRenderer
from core.mesen_integration.click_extractor import CaptureResult, OAMEntry, OBSELConfig

logger = logging.getLogger(__name__)


@dataclass
class SpriteCluster:
    """A cluster of spatially-close OAM entries (likely one game object)."""

    id: int
    entries: list[OAMEntry]
    palette_index: int
    min_x: int
    min_y: int
    width: int
    height: int

    @property
    def entry_count(self) -> int:
        """Number of OAM entries in this cluster."""
        return len(self.entries)

    @property
    def center_x(self) -> int:
        """Approximate center X coordinate."""
        return self.min_x + self.width // 2

    @property
    def center_y(self) -> int:
        """Approximate center Y coordinate."""
        return self.min_y + self.height // 2


@dataclass
class PaletteGroup:
    """OAM entries grouped by palette."""

    palette_index: int
    entries: list[OAMEntry]
    tiles: dict[tuple[int, int], Image.Image] = field(default_factory=dict)  # (row, col) -> 8x8 tile
    width_tiles: int = 0
    height_tiles: int = 0

    @property
    def entry_count(self) -> int:
        """Number of OAM entries in this group."""
        return len(self.entries)


@dataclass
class CaptureArrangementData:
    """Capture data converted to grid tiles."""

    source_path: str
    frame: int
    groups: list[PaletteGroup]
    palettes: dict[int, list[tuple[int, int, int]]]  # RGB palettes by index
    obsel: OBSELConfig
    total_tiles: int

    @property
    def has_tiles(self) -> bool:
        """Check if any tiles were extracted."""
        return self.total_tiles > 0

    @property
    def palette_indices(self) -> list[int]:
        """Get sorted list of palette indices with groups."""
        return sorted(g.palette_index for g in self.groups)


# Default garbage tile indices for Kirby games
DEFAULT_GARBAGE_TILES: set[int] = {0x03, 0x04}


class CaptureToArrangementConverter:
    """Converts Mesen captures to arrangement grid tiles."""

    def convert(
        self,
        capture: CaptureResult,
        source_path: str = "",
        selected_palettes: set[int] | None = None,
        filter_garbage_tiles: bool = True,
        garbage_tile_indices: set[int] | None = None,
        tile_size: int = 8,
        cluster_sprites: bool = True,
        cluster_distance: int = 32,
    ) -> CaptureArrangementData:
        """
        Convert capture to grid-ready tile data.

        Args:
            capture: Mesen capture result to convert
            source_path: Path to the capture file (for reference)
            selected_palettes: Which palette indices to include (None = all)
            filter_garbage_tiles: Whether to exclude common garbage tiles
            garbage_tile_indices: Custom garbage tile indices (default: {0x03, 0x04})
            tile_size: Size of output tiles (default 8x8)
            cluster_sprites: Whether to cluster nearby sprites (prevents HUD mixing)
            cluster_distance: Max pixel distance to consider sprites as grouped

        Returns:
            CaptureArrangementData with tiles ready for grid display
        """
        if garbage_tile_indices is None:
            garbage_tile_indices = DEFAULT_GARBAGE_TILES

        # Filter entries by palette if requested
        entries = capture.entries
        if selected_palettes is not None:
            entries = [e for e in entries if e.palette in selected_palettes]

        # Filter garbage tiles if enabled
        if filter_garbage_tiles:
            entries = self._filter_garbage_entries(entries, garbage_tile_indices)

        # Filter off-screen sprites (y=224 is often HUD/off-screen)
        if cluster_sprites:
            entries = self._filter_offscreen(entries)

        # Group entries by palette
        palette_groups = self._group_by_palette(entries)

        # Convert palettes to RGB tuples
        rgb_palettes = self._convert_palettes(capture.palettes)

        # Create renderer for this capture
        renderer = CaptureRenderer(capture)

        # Process each palette group
        groups: list[PaletteGroup] = []
        total_tiles = 0

        for palette_idx, group_entries in sorted(palette_groups.items()):
            if selected_palettes is not None and palette_idx not in selected_palettes:
                continue

            if cluster_sprites and len(group_entries) > 1:
                # Cluster sprites by proximity within this palette
                clusters = self._cluster_by_proximity(group_entries, cluster_distance)
                for cluster in clusters:
                    group = self._render_and_split_group(
                        palette_idx=palette_idx,
                        entries=cluster,
                        renderer=renderer,
                        tile_size=tile_size,
                    )
                    if group.tiles:  # Only add non-empty groups
                        groups.append(group)
                        total_tiles += len(group.tiles)
            else:
                # No clustering - render all entries together
                group = self._render_and_split_group(
                    palette_idx=palette_idx,
                    entries=group_entries,
                    renderer=renderer,
                    tile_size=tile_size,
                )
                groups.append(group)
                total_tiles += len(group.tiles)

        return CaptureArrangementData(
            source_path=source_path,
            frame=capture.frame,
            groups=groups,
            palettes=rgb_palettes,
            obsel=capture.obsel,
            total_tiles=total_tiles,
        )

    def get_sprite_clusters(
        self,
        capture: CaptureResult,
        filter_garbage_tiles: bool = True,
        garbage_tile_indices: set[int] | None = None,
        cluster_distance: int = 32,
    ) -> list[SpriteCluster]:
        """
        Get sprite clusters without converting to tiles.

        Use this to display cluster options for user selection before import.

        Args:
            capture: Mesen capture result to analyze
            filter_garbage_tiles: Whether to exclude common garbage tiles
            garbage_tile_indices: Custom garbage tile indices (default: {0x03, 0x04})
            cluster_distance: Max pixel distance to consider sprites as grouped

        Returns:
            List of SpriteCluster objects for user selection
        """
        if garbage_tile_indices is None:
            garbage_tile_indices = DEFAULT_GARBAGE_TILES

        # Filter entries
        entries = capture.entries
        if filter_garbage_tiles:
            entries = self._filter_garbage_entries(entries, garbage_tile_indices)
        entries = self._filter_offscreen(entries)

        # Group by palette then cluster
        palette_groups = self._group_by_palette(entries)

        clusters: list[SpriteCluster] = []
        cluster_id = 0

        for palette_idx, group_entries in sorted(palette_groups.items()):
            if len(group_entries) > 1:
                # Cluster sprites by proximity within this palette
                entry_clusters = self._cluster_by_proximity(group_entries, cluster_distance)
                for entry_cluster in entry_clusters:
                    cluster = self._create_cluster_info(cluster_id, palette_idx, entry_cluster)
                    clusters.append(cluster)
                    cluster_id += 1
            else:
                # Single entry is its own cluster
                cluster = self._create_cluster_info(cluster_id, palette_idx, group_entries)
                clusters.append(cluster)
                cluster_id += 1

        return clusters

    def _create_cluster_info(
        self,
        cluster_id: int,
        palette_idx: int,
        entries: list[OAMEntry],
    ) -> SpriteCluster:
        """Create cluster info from entries."""
        # Normalize x positions for SNES wrap-around
        def normalize_x(x: int) -> int:
            return x if x >= 0 else x + 256

        norm_positions = [
            (normalize_x(e.x), e.y, e.width, e.height) for e in entries
        ]
        min_x = min(p[0] for p in norm_positions)
        min_y = min(p[1] for p in norm_positions)
        max_x = max(p[0] + p[2] for p in norm_positions)
        max_y = max(p[1] + p[3] for p in norm_positions)

        return SpriteCluster(
            id=cluster_id,
            entries=entries,
            palette_index=palette_idx,
            min_x=min_x,
            min_y=min_y,
            width=max_x - min_x,
            height=max_y - min_y,
        )

    def convert_clusters(
        self,
        capture: CaptureResult,
        clusters: list[SpriteCluster],
        source_path: str = "",
        tile_size: int = 8,
    ) -> CaptureArrangementData:
        """
        Convert selected clusters to arrangement data.

        Args:
            capture: Original capture result
            clusters: Selected clusters to convert
            source_path: Path to the capture file
            tile_size: Size of output tiles

        Returns:
            CaptureArrangementData with tiles ready for grid display
        """
        # Convert palettes to RGB tuples
        rgb_palettes = self._convert_palettes(capture.palettes)

        # Create renderer for this capture
        renderer = CaptureRenderer(capture)

        # Process selected clusters
        groups: list[PaletteGroup] = []
        total_tiles = 0

        for cluster in clusters:
            group = self._render_and_split_group(
                palette_idx=cluster.palette_index,
                entries=cluster.entries,
                renderer=renderer,
                tile_size=tile_size,
            )
            if group.tiles:
                groups.append(group)
                total_tiles += len(group.tiles)

        return CaptureArrangementData(
            source_path=source_path,
            frame=capture.frame,
            groups=groups,
            palettes=rgb_palettes,
            obsel=capture.obsel,
            total_tiles=total_tiles,
        )

    def _filter_garbage_entries(
        self,
        entries: list[OAMEntry],
        garbage_indices: set[int],
    ) -> list[OAMEntry]:
        """Filter out entries that use common garbage tile indices."""
        filtered = []
        for entry in entries:
            # Check if any of the entry's tiles are garbage
            has_garbage = any(tile.tile_index in garbage_indices for tile in entry.tiles)
            if not has_garbage:
                filtered.append(entry)
            else:
                logger.debug(f"Filtered garbage entry: tile={entry.tile}, tiles={[t.tile_index for t in entry.tiles]}")
        return filtered

    def _group_by_palette(self, entries: list[OAMEntry]) -> dict[int, list[OAMEntry]]:
        """Group entries by their palette index."""
        groups: dict[int, list[OAMEntry]] = {}
        for entry in entries:
            if entry.palette not in groups:
                groups[entry.palette] = []
            groups[entry.palette].append(entry)
        return groups

    def _filter_offscreen(self, entries: list[OAMEntry]) -> list[OAMEntry]:
        """Filter out off-screen sprites (commonly y=224 for HUD elements)."""
        return [e for e in entries if e.y != 224 and e.y < 200]

    def _cluster_by_proximity(
        self,
        entries: list[OAMEntry],
        distance_threshold: int = 32,
    ) -> list[list[OAMEntry]]:
        """
        Group OAM entries that are spatially close (likely same game object).

        This prevents unrelated sprites (e.g., character + HUD) from being
        merged into one huge sparse composite.

        Handles SNES screen wrap-around (x can be -256 to 255).
        """
        if not entries:
            return []

        def wrapped_distance(x1: int, x2: int, screen_width: int = 256) -> int:
            """Calculate distance accounting for screen wrap-around."""
            # Direct distance
            direct = abs(x1 - x2)
            # Wrapped distance (sprite at x=-24 is near x=232 via wrap)
            wrapped = screen_width - direct
            return min(direct, wrapped)

        clusters: list[list[OAMEntry]] = []
        used: set[int] = set()

        for entry in entries:
            entry_id = id(entry)
            if entry_id in used:
                continue

            # Start new cluster
            cluster = [entry]
            used.add(entry_id)

            # Find nearby entries (greedy expansion)
            changed = True
            while changed:
                changed = False
                for other in entries:
                    other_id = id(other)
                    if other_id in used:
                        continue

                    # Check if other is close to ANY entry in current cluster
                    for cluster_entry in cluster:
                        cx = cluster_entry.x + cluster_entry.width // 2
                        cy = cluster_entry.y + cluster_entry.height // 2
                        ox = other.x + other.width // 2
                        oy = other.y + other.height // 2

                        dx = wrapped_distance(cx, ox)
                        dy = abs(cy - oy)

                        if dx < distance_threshold and dy < distance_threshold:
                            cluster.append(other)
                            used.add(other_id)
                            changed = True
                            break

            clusters.append(cluster)

        return clusters

    def _convert_palettes(
        self,
        palettes: dict[int, list[int | list[int]]],
    ) -> dict[int, list[tuple[int, int, int]]]:
        """Convert palette format to list of (R,G,B) tuples.

        Handles both packed RGB integers and RGB triplets.
        """
        rgb_palettes: dict[int, list[tuple[int, int, int]]] = {}
        for idx, colors in palettes.items():
            rgb_colors: list[tuple[int, int, int]] = []
            for color in colors:
                if isinstance(color, int):
                    # Colors stored as packed RGB integer (0xRRGGBB)
                    r = (color >> 16) & 0xFF
                    g = (color >> 8) & 0xFF
                    b = color & 0xFF
                    rgb_colors.append((r, g, b))
                else:
                    # Already RGB triplet (list[int]) - convert to tuple
                    rgb_colors.append((int(color[0]), int(color[1]), int(color[2])))
            rgb_palettes[idx] = rgb_colors
        return rgb_palettes

    def _render_and_split_group(
        self,
        palette_idx: int,
        entries: list[OAMEntry],
        renderer: CaptureRenderer,
        tile_size: int = 8,
    ) -> PaletteGroup:
        """
        Render entries and split into tiles.

        1. Normalize x positions for SNES screen wrap-around
        2. Calculate group bounding box
        3. Render each entry relative to group origin
        4. Composite into single image
        5. Split into tile_size x tile_size tiles
        """
        if not entries:
            return PaletteGroup(palette_index=palette_idx, entries=[])

        # Normalize x positions for SNES wrap-around (x can be -256 to 255)
        # Negative x values are sprites wrapping from right edge
        def normalize_x(x: int) -> int:
            return x if x >= 0 else x + 256

        # Calculate bounding box with normalized positions
        norm_positions = [
            (normalize_x(e.x), e.y, e.width, e.height) for e in entries
        ]
        min_x = min(p[0] for p in norm_positions)
        min_y = min(p[1] for p in norm_positions)
        max_x = max(p[0] + p[2] for p in norm_positions)
        max_y = max(p[1] + p[3] for p in norm_positions)

        # Calculate dimensions
        width = max_x - min_x
        height = max_y - min_y

        # Round up to tile boundaries
        width_tiles = (width + tile_size - 1) // tile_size
        height_tiles = (height + tile_size - 1) // tile_size
        canvas_width = width_tiles * tile_size
        canvas_height = height_tiles * tile_size

        # Create composite canvas
        composite = Image.new("RGBA", (canvas_width, canvas_height), (0, 0, 0, 0))

        # Render each entry as indexed grayscale onto canvas
        # Using indexed rendering allows the colorizer to apply palettes on demand
        for entry in entries:
            entry_img = renderer.render_entry_indexed(entry)
            # Position relative to group origin (normalized)
            x = normalize_x(entry.x) - min_x
            y = entry.y - min_y
            composite.paste(entry_img, (x, y), entry_img)

        # Split into tiles
        tiles: dict[tuple[int, int], Image.Image] = {}
        for row in range(height_tiles):
            for col in range(width_tiles):
                x = col * tile_size
                y = row * tile_size
                tile_img = composite.crop((x, y, x + tile_size, y + tile_size))

                # Only include non-empty tiles (with any visible pixels)
                if tile_img.getbbox() is not None:
                    tiles[(row, col)] = tile_img

        return PaletteGroup(
            palette_index=palette_idx,
            entries=entries,
            tiles=tiles,
            width_tiles=width_tiles,
            height_tiles=height_tiles,
        )
