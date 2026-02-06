"""Immutable snapshots of project data for thread-safe async injection.

These frozen dataclasses capture the necessary project state at queue time
to avoid reading mutable project data in the worker thread. This prevents
race conditions when the user modifies alignment/settings while injection
is in progress.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from core.types import CompressionType

if TYPE_CHECKING:
    from core.frame_mapping_project import FrameMappingProject


@dataclass(frozen=True)
class MappingSnapshot:
    """Immutable snapshot of mapping alignment settings."""

    offset_x: int
    offset_y: int
    flip_h: bool
    flip_v: bool
    scale: float
    sharpen: float
    resampling: str
    ingame_edited_path: str | None = None


@dataclass(frozen=True)
class AIFrameSnapshot:
    """Immutable snapshot of AI frame data."""

    id: str
    path: Path
    index: int


@dataclass(frozen=True)
class GameFrameSnapshot:
    """Immutable snapshot of game frame data."""

    id: str
    rom_offsets: tuple[int, ...]
    capture_path: Path | None
    palette_index: int
    selected_entry_ids: tuple[int, ...]
    compression_types: dict[int, CompressionType]
    width: int
    height: int


@dataclass(frozen=True)
class PaletteSnapshot:
    """Immutable snapshot of sheet palette colors and mappings."""

    colors: tuple[tuple[int, int, int], ...]
    color_mappings: tuple[tuple[tuple[int, int, int], int], ...]  # Frozen dict as tuple of pairs
    background_color: tuple[int, int, int] | None
    background_tolerance: int
    alpha_threshold: int
    dither_mode: str
    dither_strength: float


@dataclass(frozen=True)
class InjectionSnapshot:
    """Complete immutable snapshot for injection.

    Captures all project data needed for injection at queue time,
    ensuring the worker thread doesn't read mutable state.
    """

    mapping: MappingSnapshot
    ai_frame: AIFrameSnapshot
    game_frame: GameFrameSnapshot
    palette: PaletteSnapshot | None

    @classmethod
    def from_project(
        cls,
        project: FrameMappingProject,
        ai_frame_id: str,
    ) -> InjectionSnapshot | None:
        """Create a snapshot from current project state.

        Args:
            project: The project to snapshot
            ai_frame_id: ID of AI frame being injected

        Returns:
            InjectionSnapshot or None if required data is missing
        """
        # Get mapping
        mapping = project.get_mapping_for_ai_frame(ai_frame_id)
        if mapping is None:
            return None

        # Get AI frame
        ai_frame = project.get_ai_frame_by_id(ai_frame_id)
        if ai_frame is None:
            return None

        # Get game frame
        game_frame = project.get_game_frame_by_id(mapping.game_frame_id)
        if game_frame is None:
            return None

        # Snapshot mapping
        mapping_snapshot = MappingSnapshot(
            offset_x=mapping.offset_x,
            offset_y=mapping.offset_y,
            flip_h=mapping.flip_h,
            flip_v=mapping.flip_v,
            scale=mapping.scale,
            sharpen=mapping.sharpen,
            resampling=mapping.resampling,
            ingame_edited_path=mapping.ingame_edited_path,
        )

        # Snapshot AI frame
        ai_frame_snapshot = AIFrameSnapshot(
            id=ai_frame.id,
            path=ai_frame.path,
            index=ai_frame.index,
        )

        # Snapshot game frame
        game_frame_snapshot = GameFrameSnapshot(
            id=game_frame.id,
            rom_offsets=tuple(game_frame.rom_offsets),
            capture_path=game_frame.capture_path,
            palette_index=game_frame.palette_index,
            selected_entry_ids=tuple(game_frame.selected_entry_ids),
            compression_types=dict(game_frame.compression_types),
            width=game_frame.width,
            height=game_frame.height,
        )

        # Snapshot palette (optional)
        palette_snapshot = None
        if project.sheet_palette is not None:
            # Cast each color tuple to fixed 3-tuple for type safety
            palette_snapshot = PaletteSnapshot(
                colors=tuple((c[0], c[1], c[2]) for c in project.sheet_palette.colors),
                color_mappings=tuple(project.sheet_palette.color_mappings.items()),
                background_color=project.sheet_palette.background_color,
                background_tolerance=project.sheet_palette.background_tolerance,
                alpha_threshold=project.sheet_palette.alpha_threshold,
                dither_mode=project.sheet_palette.dither_mode,
                dither_strength=project.sheet_palette.dither_strength,
            )

        return cls(
            mapping=mapping_snapshot,
            ai_frame=ai_frame_snapshot,
            game_frame=game_frame_snapshot,
            palette=palette_snapshot,
        )
