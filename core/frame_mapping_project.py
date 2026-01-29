"""Data model for Frame Mapping projects.

A Frame Mapping project links AI-generated sprite frames to game animation
frames captured from Mesen 2. This enables one-click workflow for replacing
game sprites with AI-generated alternatives.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import cast

from core.palette_utils import SNES_PALETTE_SIZE


class MappingStatus(str, Enum):
    """Status of a frame mapping.

    Uses str mixin for JSON serialization compatibility - enum values can be
    serialized directly as strings and compared with string literals.
    """

    UNMAPPED = "unmapped"
    MAPPED = "mapped"
    EDITED = "edited"
    INJECTED = "injected"


logger = logging.getLogger(__name__)


@dataclass
class SheetPalette:
    """Palette configuration for an AI sprite sheet.

    Defines a 16-color palette and optional explicit color mappings for
    consistent quantization across all AI frames in a project.

    Attributes:
        colors: List of 16 RGB tuples (index 0 = transparent)
        color_mappings: Dict mapping AI frame RGB colors to palette indices
    """

    colors: list[tuple[int, int, int]]  # 16 RGB colors (index 0 = transparent)
    color_mappings: dict[tuple[int, int, int], int] = field(default_factory=dict)

    @property
    def version_hash(self) -> int:
        """Compute hash of current palette state for cache invalidation.

        Returns a stable hash based on colors and color_mappings. Two palettes
        with identical content will have the same version_hash.
        """
        colors_tuple = tuple(self.colors)
        mappings_tuple = tuple(sorted(self.color_mappings.items()))
        return hash((colors_tuple, mappings_tuple))

    def to_dict(self) -> dict[str, object]:
        """Serialize to dictionary for JSON storage."""
        # Convert tuple keys to strings for JSON compatibility
        mappings_serializable = {f"{r},{g},{b}": idx for (r, g, b), idx in self.color_mappings.items()}
        return {
            "colors": [list(c) for c in self.colors],
            "color_mappings": mappings_serializable,
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> SheetPalette:
        """Deserialize from dictionary.

        Performs validation and clamping:
        - RGB values are clamped to 0-255 (backward compatible)
        - Mapping indices are clamped to 0-15 (SNES_PALETTE_SIZE - 1)
        - Warnings are logged for invalid values
        - Warns if index 0 is not (0,0,0) (transparency assumption)
        """
        colors_raw = cast(list[list[int]], data.get("colors", []))
        colors: list[tuple[int, int, int]] = []

        for c in colors_raw:
            if len(c) >= 3:
                # Validate and clamp RGB values to 0-255
                r = max(0, min(255, c[0]))
                g = max(0, min(255, c[1]))
                b = max(0, min(255, c[2]))
                if r != c[0] or g != c[1] or b != c[2]:
                    logger.warning(
                        "RGB value clamped: (%d, %d, %d) -> (%d, %d, %d)",
                        c[0],
                        c[1],
                        c[2],
                        r,
                        g,
                        b,
                    )
                colors.append((r, g, b))
            else:
                colors.append((0, 0, 0))

        # Ensure we have exactly 16 colors, pad with black if needed
        while len(colors) < SNES_PALETTE_SIZE:
            colors.append((0, 0, 0))
        colors = colors[:SNES_PALETTE_SIZE]

        # Validate transparency index assumption: index 0 should be (0,0,0)
        if colors and colors[0] != (0, 0, 0):
            logger.warning(
                "SheetPalette index 0 is %s, not (0,0,0). "
                "SNES sprites assume index 0 is transparent (black). "
                "This may cause incorrect transparency in previews and injection.",
                colors[0],
            )

        # Convert string keys back to tuples
        mappings_raw = cast(dict[str, int], data.get("color_mappings", {}))
        color_mappings: dict[tuple[int, int, int], int] = {}
        for key_str, idx in mappings_raw.items():
            parts = key_str.split(",")
            if len(parts) == 3:
                try:
                    rgb = (int(parts[0]), int(parts[1]), int(parts[2]))
                    # Validate and clamp mapping index to 0-15
                    idx_clamped = max(0, min(SNES_PALETTE_SIZE - 1, idx))
                    if idx_clamped != idx:
                        logger.warning(
                            "Mapping index clamped: %d -> %d for color %s",
                            idx,
                            idx_clamped,
                            key_str,
                        )
                    color_mappings[rgb] = idx_clamped
                except ValueError:
                    logger.warning("Invalid color mapping key: %s", key_str)

        return cls(colors=colors, color_mappings=color_mappings)


# Preset tags for AI frame organization
FRAME_TAGS = frozenset({"keep", "discard", "wip", "final", "review"})


@dataclass
class AIFrame:
    """Represents an AI-generated sprite frame.

    Attributes:
        path: Path to the image file
        index: Position in the frame list
        width: Image width in pixels
        height: Image height in pixels
        display_name: Optional user-friendly name (alias), shown instead of filename
        tags: Set of preset tags for organization (keep, discard, wip, final, review)
    """

    path: Path
    index: int
    width: int = 0
    height: int = 0
    display_name: str | None = None
    tags: frozenset[str] = field(default_factory=frozenset)

    @property
    def id(self) -> str:
        """Stable identifier for this AI frame (filename).

        Returns the filename which remains stable across reloads/reordering,
        unlike the position-dependent `index` field.
        """
        return self.path.name

    @property
    def name(self) -> str:
        """Display name for this frame.

        Returns display_name if set, otherwise the filename.
        """
        return self.display_name or self.path.name

    def to_dict(self, base_path: Path | None = None) -> dict[str, object]:
        """Serialize to dictionary for JSON storage.

        Args:
            base_path: Optional base directory to make path relative to.
        """
        path_str = str(self.path)
        if base_path and self.path.is_absolute():
            try:
                path_str = str(self.path.relative_to(base_path))
            except ValueError:
                # Not under base_path, keep absolute
                pass

        result: dict[str, object] = {
            "path": path_str,
            "index": self.index,
            "width": self.width,
            "height": self.height,
        }
        # Only include optional fields if set (keeps file compact)
        if self.display_name is not None:
            result["display_name"] = self.display_name
        if self.tags:
            result["tags"] = sorted(self.tags)  # Sort for deterministic output
        return result

    @classmethod
    def from_dict(cls, data: dict[str, object], base_path: Path | None = None) -> AIFrame:
        """Deserialize from dictionary.

        Args:
            data: Dictionary data.
            base_path: Optional base directory to resolve relative paths against.

        Note:
            Handles backward compatibility - display_name and tags default to
            None/empty if not present (V3 files).
        """
        path = Path(cast(str, data["path"]))
        if base_path and not path.is_absolute():
            path = base_path / path

        # Load tags (V4+), validate against allowed set
        tags_raw = data.get("tags", [])
        tags_list = cast(list[str], tags_raw) if tags_raw else []
        tags = frozenset(t for t in tags_list if t in FRAME_TAGS)

        return cls(
            path=path,
            index=cast(int, data["index"]),
            width=cast(int, data.get("width", 0)),
            height=cast(int, data.get("height", 0)),
            display_name=cast(str | None, data.get("display_name")),
            tags=tags,
        )


@dataclass
class GameFrame:
    """Represents a game frame captured from Mesen 2."""

    id: str  # e.g., "F17987"
    rom_offsets: list[int] = field(default_factory=list)  # ROM addresses
    capture_path: Path | None = None
    palette_index: int = 0
    width: int = 0
    height: int = 0
    selected_entry_ids: list[int] = field(default_factory=list)  # OAM entry IDs selected during import
    # Stored per-ROM offset, but UI enforces a single compression type per game frame.
    compression_types: dict[int, str] = field(default_factory=dict)  # ROM offset -> "hal" | "raw"
    display_name: str | None = None  # Optional user-defined display name

    @property
    def name(self) -> str:
        """Display name for this frame.

        Returns the display_name if set, otherwise returns the id.
        """
        return self.display_name or self.id

    def to_dict(self, base_path: Path | None = None) -> dict[str, object]:
        """Serialize to dictionary for JSON storage.

        Args:
            base_path: Optional base directory to make path relative to.
        """
        capture_path_str = None
        if self.capture_path:
            capture_path_str = str(self.capture_path)
            if base_path and self.capture_path.is_absolute():
                try:
                    capture_path_str = str(self.capture_path.relative_to(base_path))
                except ValueError:
                    pass

        # Convert int keys to strings for JSON serialization
        compression_types_str = {str(k): v for k, v in self.compression_types.items()}

        result: dict[str, object] = {
            "id": self.id,
            "rom_offsets": self.rom_offsets,
            "capture_path": capture_path_str,
            "palette_index": self.palette_index,
            "width": self.width,
            "height": self.height,
            "selected_entry_ids": self.selected_entry_ids,
            "compression_types": compression_types_str,
        }
        # Only include display_name if set (keeps file compact)
        if self.display_name is not None:
            result["display_name"] = self.display_name
        return result

    @classmethod
    def from_dict(cls, data: dict[str, object], base_path: Path | None = None) -> GameFrame:
        """Deserialize from dictionary.

        Args:
            data: Dictionary data.
            base_path: Optional base directory to resolve relative paths against.
        """
        capture_path_raw = data.get("capture_path")
        capture_path = Path(cast(str, capture_path_raw)) if capture_path_raw else None

        if base_path and capture_path and not capture_path.is_absolute():
            capture_path = base_path / capture_path

        # Convert string keys back to ints for compression_types
        compression_types_raw = cast(dict[str, str], data.get("compression_types", {}))
        compression_types = {int(k): v for k, v in compression_types_raw.items()}

        return cls(
            id=cast(str, data["id"]),
            rom_offsets=cast(list[int], data.get("rom_offsets", [])),
            capture_path=capture_path,
            palette_index=cast(int, data.get("palette_index", 0)),
            width=cast(int, data.get("width", 0)),
            height=cast(int, data.get("height", 0)),
            selected_entry_ids=cast(list[int], data.get("selected_entry_ids", [])),
            compression_types=compression_types,
            display_name=cast(str | None, data.get("display_name")),
        )


@dataclass
class FrameMapping:
    """Links an AI frame to a game frame.

    Uses `ai_frame_id` (filename) as the stable identifier for AI frames.
    The `ai_frame_index` field is deprecated and only kept for v1 migration.
    """

    ai_frame_id: str  # Stable identifier (filename)
    game_frame_id: str
    status: str = "mapped"  # "unmapped", "mapped", "edited", "injected"

    # Alignment for overlay (AI frame relative to game frame)
    offset_x: int = 0
    offset_y: int = 0
    flip_h: bool = False
    flip_v: bool = False
    scale: float = 1.0  # Uniform scale factor (0.01 - 1.0)

    # Quantization quality options
    sharpen: float = 0.0  # Pre-sharpening before scale (0.0-4.0)
    resampling: str = "lanczos"  # "lanczos" or "nearest"

    def to_dict(self) -> dict[str, object]:
        """Serialize to dictionary for JSON storage."""
        return {
            "ai_frame_id": self.ai_frame_id,
            "game_frame_id": self.game_frame_id,
            "status": self.status,
            "offset_x": self.offset_x,
            "offset_y": self.offset_y,
            "flip_h": self.flip_h,
            "flip_v": self.flip_v,
            "scale": self.scale,
            "sharpen": self.sharpen,
            "resampling": self.resampling,
        }

    @classmethod
    def from_dict(cls, data: dict[str, object], ai_frames: list[AIFrame] | None = None) -> FrameMapping:
        """Deserialize from dictionary.

        Args:
            data: Dictionary data.
            ai_frames: Optional list of AI frames for v1 migration (index -> id).
        """
        # V2 format: use ai_frame_id directly
        if "ai_frame_id" in data:
            ai_frame_id = cast(str, data["ai_frame_id"])
        # V1 migration: convert ai_frame_index to ai_frame_id
        elif "ai_frame_index" in data and ai_frames:
            ai_frame_index = cast(int, data["ai_frame_index"])
            # Find AI frame by index and get its id
            ai_frame_id = ""
            for frame in ai_frames:
                if frame.index == ai_frame_index:
                    ai_frame_id = frame.id
                    break
            if not ai_frame_id:
                logger.warning(
                    "V1 migration: ai_frame_index %d not found in ai_frames, skipping",
                    ai_frame_index,
                )
                ai_frame_id = f"__orphaned_index_{ai_frame_index}"
        else:
            # Fallback for malformed data
            ai_frame_id = cast(str, data.get("ai_frame_id", ""))

        return cls(
            ai_frame_id=ai_frame_id,
            game_frame_id=cast(str, data["game_frame_id"]),
            status=cast(str, data.get("status", "mapped")),
            offset_x=cast(int, data.get("offset_x", 0)),
            offset_y=cast(int, data.get("offset_y", 0)),
            flip_h=cast(bool, data.get("flip_h", False)),
            flip_v=cast(bool, data.get("flip_v", False)),
            scale=float(cast(int | float, data.get("scale", 1.0))),
            sharpen=float(cast(int | float, data.get("sharpen", 0.0))),
            resampling=cast(str, data.get("resampling", "lanczos")),
        )


# Supported project file versions
# V1: ai_frame_index (position-dependent)
# V2: ai_frame_id (filename, stable)
# V3: sheet_palette for AI frame quantization
# V4: display_name and tags for AI frame organization
SUPPORTED_VERSIONS = {1, 2, 3, 4}
CURRENT_VERSION = 4


@dataclass
class FrameMappingProject:
    """Container for a complete frame mapping project.

    A project consists of:
    - AI-generated frames (from a directory of PNG files)
    - Game frames (captured from Mesen 2)
    - Mappings linking AI frames to game frames

    Version history:
    - V1: Used ai_frame_index (position-dependent, breaks on reload)
    - V2: Uses ai_frame_id (filename, stable across reloads)
    - V3: Adds sheet_palette for consistent AI frame quantization
    - V4: Adds display_name and tags for AI frame organization

    Note:
        Persistence is handled by FrameMappingRepository.
        Use FrameMappingRepository.save(project, path) and
        FrameMappingRepository.load(path) for file operations.
    """

    name: str
    ai_frames_dir: Path | None = None
    ai_frames: list[AIFrame] = field(default_factory=list)
    game_frames: list[GameFrame] = field(default_factory=list)
    mappings: list[FrameMapping] = field(default_factory=list)
    sheet_palette: SheetPalette | None = None

    # Internal caches (not serialized)
    _mapping_index_by_ai: dict[str, FrameMapping] = field(default_factory=dict, init=False, repr=False, compare=False)
    _mapping_index_by_game: dict[str, FrameMapping] = field(default_factory=dict, init=False, repr=False, compare=False)
    _ai_frame_index_by_id: dict[str, AIFrame] = field(default_factory=dict, init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        """Initialize caches after dataclass init."""
        self._rebuild_indices()

    def _rebuild_indices(self) -> None:
        """Rebuild internal lookup indices."""
        self._mapping_index_by_ai = {m.ai_frame_id: m for m in self.mappings}
        self._mapping_index_by_game = {m.game_frame_id: m for m in self.mappings}
        self._ai_frame_index_by_id = {f.id: f for f in self.ai_frames}

    def _invalidate_mapping_index(self) -> None:
        """Invalidate mapping indices (call after modifying mappings)."""
        self._mapping_index_by_ai = {m.ai_frame_id: m for m in self.mappings}
        self._mapping_index_by_game = {m.game_frame_id: m for m in self.mappings}

    def _invalidate_ai_frame_index(self) -> None:
        """Invalidate AI frame index (call after modifying ai_frames)."""
        self._ai_frame_index_by_id = {f.id: f for f in self.ai_frames}

    def replace_ai_frames(self, frames: list[AIFrame], ai_frames_dir: Path | None = None) -> None:
        """Replace all AI frames and update internal indices.

        This is the preferred method for setting AI frames as it ensures
        index consistency. Avoids external access to private invalidation methods.

        Args:
            frames: New list of AI frames
            ai_frames_dir: Optional directory path where frames are located
        """
        self.ai_frames = frames
        if ai_frames_dir is not None:
            self.ai_frames_dir = ai_frames_dir
        self._invalidate_ai_frame_index()

    def add_ai_frame(self, frame: AIFrame) -> AIFrame:
        """Add a single AI frame to the project.

        Args:
            frame: AIFrame to add

        Returns:
            The added frame (for method chaining)
        """
        self.ai_frames.append(frame)
        self._invalidate_ai_frame_index()
        return frame

    def add_game_frame(self, frame: GameFrame) -> GameFrame:
        """Add a game frame to the project.

        Args:
            frame: GameFrame to add

        Returns:
            The added frame (for method chaining)

        Raises:
            ValueError: If a game frame with the same ID already exists
        """
        if self.get_game_frame_by_id(frame.id) is not None:
            raise ValueError(f"Game frame with ID '{frame.id}' already exists")
        self.game_frames.append(frame)
        return frame

    def filter_mappings_by_valid_ai_ids(self, valid_ai_ids: set[str]) -> int:
        """Remove mappings that reference non-existent AI frame IDs.

        Use this after reloading AI frames to prune orphaned mappings.

        Args:
            valid_ai_ids: Set of valid AI frame IDs to keep

        Returns:
            Number of mappings removed
        """
        original_len = len(self.mappings)
        self.mappings = [m for m in self.mappings if m.ai_frame_id in valid_ai_ids]
        if len(self.mappings) < original_len:
            self._invalidate_mapping_index()
        return original_len - len(self.mappings)

    def _prune_orphaned_mappings(self) -> None:
        """Remove mappings that reference non-existent AI or game frames."""
        valid_ai_ids = {f.id for f in self.ai_frames}
        valid_game_ids = {f.id for f in self.game_frames}

        orphaned = [
            m for m in self.mappings if m.ai_frame_id not in valid_ai_ids or m.game_frame_id not in valid_game_ids
        ]

        if orphaned:
            logger.warning(
                "Pruning %d orphaned mappings (AI IDs: %s, Game IDs: %s)",
                len(orphaned),
                [m.ai_frame_id for m in orphaned if m.ai_frame_id not in valid_ai_ids],
                [m.game_frame_id for m in orphaned if m.game_frame_id not in valid_game_ids],
            )
            self.mappings = [
                m for m in self.mappings if m.ai_frame_id in valid_ai_ids and m.game_frame_id in valid_game_ids
            ]
            self._invalidate_mapping_index()

    def get_mapping_for_ai_frame(self, ai_frame_id: str) -> FrameMapping | None:
        """Get mapping for a specific AI frame by ID.

        O(1) lookup using internal index.

        Args:
            ai_frame_id: The AI frame ID (filename)

        Returns:
            FrameMapping if found, None otherwise
        """
        return self._mapping_index_by_ai.get(ai_frame_id)

    def get_mapping_for_game_frame(self, game_frame_id: str) -> FrameMapping | None:
        """Get mapping for a specific game frame.

        O(1) lookup using internal index.
        """
        return self._mapping_index_by_game.get(game_frame_id)

    def get_ai_frame_linked_to_game_frame(self, game_frame_id: str) -> str | None:
        """Get the AI frame ID linked to a specific game frame.

        Args:
            game_frame_id: ID of the game frame

        Returns:
            AI frame ID if game frame is linked, None otherwise
        """
        mapping = self.get_mapping_for_game_frame(game_frame_id)
        if mapping is not None:
            return mapping.ai_frame_id
        return None

    def get_ai_frame_by_id(self, ai_frame_id: str) -> AIFrame | None:
        """Get AI frame by ID (filename).

        O(1) lookup using internal index.
        """
        return self._ai_frame_index_by_id.get(ai_frame_id)

    def update_ai_frame_path(self, old_id: str, new_path: Path) -> str | None:
        """Update an AI frame's path and fix all references.

        When an AI frame is edited and saved with a new filename,
        this updates the frame and any associated mapping to use
        the new ID (derived from the new path).

        Args:
            old_id: Current AI frame ID (old filename)
            new_path: New path for the AI frame

        Returns:
            New AI frame ID if successful, None if frame not found
        """
        ai_frame = self._ai_frame_index_by_id.get(old_id)
        if ai_frame is None:
            return None

        # Update the AI frame's path
        ai_frame.path = new_path
        new_id = ai_frame.id  # Computed from new path.name

        # Update any mapping that references this AI frame
        mapping = self._mapping_index_by_ai.get(old_id)
        if mapping is not None:
            mapping.ai_frame_id = new_id

        # Rebuild indices to reflect the new ID
        self._rebuild_indices()

        logger.info("Updated AI frame path: %s -> %s (new ID: %s)", old_id, new_path, new_id)
        return new_id

    def get_game_frame_by_id(self, frame_id: str) -> GameFrame | None:
        """Get game frame by ID."""
        for frame in self.game_frames:
            if frame.id == frame_id:
                return frame
        return None

    def remove_game_frame(self, frame_id: str) -> bool:
        """Remove a game frame and its associated mapping.

        Args:
            frame_id: ID of the game frame to remove.

        Returns:
            True if the frame was found and removed, False otherwise.
        """
        frame = self.get_game_frame_by_id(frame_id)
        if frame is None:
            return False

        # Remove any mapping associated with this game frame
        self.mappings = [m for m in self.mappings if m.game_frame_id != frame_id]
        self._invalidate_mapping_index()

        # Remove the game frame
        self.game_frames.remove(frame)

        return True

    def remove_ai_frame(self, frame_id: str) -> bool:
        """Remove an AI frame and its associated mapping.

        Args:
            frame_id: ID of the AI frame to remove.

        Returns:
            True if the frame was found and removed, False otherwise.
        """
        frame = self.get_ai_frame_by_id(frame_id)
        if frame is None:
            return False

        # Remove any mapping associated with this AI frame
        self.mappings = [m for m in self.mappings if m.ai_frame_id != frame_id]
        self._invalidate_mapping_index()

        # Remove the AI frame
        self.ai_frames.remove(frame)
        self._invalidate_ai_frame_index()

        return True

    def reorder_ai_frame(self, ai_frame_id: str, new_index: int) -> bool:
        """Move an AI frame to a new position in the list.

        Args:
            ai_frame_id: ID of the AI frame to move.
            new_index: Target position (0-based). Clamped to valid range.

        Returns:
            True if the frame was moved, False if not found or same position.
        """
        # Find current position
        current_index = -1
        for i, frame in enumerate(self.ai_frames):
            if frame.id == ai_frame_id:
                current_index = i
                break

        if current_index == -1:
            return False

        # Clamp target index to valid range
        max_index = len(self.ai_frames) - 1
        new_index = max(0, min(new_index, max_index))

        # No-op if same position
        if current_index == new_index:
            return False

        # Pop and reinsert
        frame = self.ai_frames.pop(current_index)
        self.ai_frames.insert(new_index, frame)

        # Renumber all indices
        for i, f in enumerate(self.ai_frames):
            f.index = i

        self._invalidate_ai_frame_index()
        return True

    def create_mapping(self, ai_frame_id: str, game_frame_id: str) -> FrameMapping:
        """Create a new mapping between an AI frame and a game frame.

        If a mapping already exists for the AI frame, it is updated.
        If a mapping already exists for the game frame, it is removed (1:1 enforcement).

        Args:
            ai_frame_id: ID of the AI frame (filename)
            game_frame_id: ID of the game frame

        Returns:
            The created or updated mapping

        Raises:
            ValueError: If ai_frame_id or game_frame_id is empty
            ValueError: If ai_frame_id or game_frame_id does not exist in project
        """
        # Validate inputs - empty IDs break downstream operations
        if not ai_frame_id or not ai_frame_id.strip():
            raise ValueError("ai_frame_id cannot be empty")
        if not game_frame_id or not game_frame_id.strip():
            raise ValueError("game_frame_id cannot be empty")

        # Validate referential integrity - frames must exist
        if self.get_ai_frame_by_id(ai_frame_id) is None:
            raise ValueError(f"AI frame '{ai_frame_id}' not found in project")
        if self.get_game_frame_by_id(game_frame_id) is None:
            raise ValueError(f"Game frame '{game_frame_id}' not found in project")

        # Remove existing mapping for this AI frame if any
        self.mappings = [m for m in self.mappings if m.ai_frame_id != ai_frame_id]

        # Remove existing mapping for this game frame if any (enforce 1:1)
        self.mappings = [m for m in self.mappings if m.game_frame_id != game_frame_id]

        mapping = FrameMapping(
            ai_frame_id=ai_frame_id,
            game_frame_id=game_frame_id,
            status="mapped",
        )
        self.mappings.append(mapping)
        self._invalidate_mapping_index()
        return mapping

    def update_mapping_alignment(
        self,
        ai_frame_id: str,
        offset_x: int,
        offset_y: int,
        flip_h: bool,
        flip_v: bool,
        scale: float = 1.0,
        sharpen: float = 0.0,
        resampling: str = "lanczos",
        set_edited: bool = True,
    ) -> bool:
        """Update alignment for a mapping.

        Args:
            ai_frame_id: ID of the AI frame (filename)
            offset_x: X offset for alignment
            offset_y: Y offset for alignment
            flip_h: Horizontal flip state
            flip_v: Vertical flip state
            scale: Scale factor (0.01 - 1.0)
            sharpen: Pre-sharpening amount (0.0 - 4.0)
            resampling: Resampling method ("lanczos" or "nearest")
            set_edited: If True, set status to 'edited' (clears 'injected' status).
                        Use False for auto-centering during initial link creation.

        Returns:
            True if mapping was updated, False if no mapping exists
        """
        mapping = self.get_mapping_for_ai_frame(ai_frame_id)
        if mapping is None:
            return False

        mapping.offset_x = offset_x
        mapping.offset_y = offset_y
        mapping.flip_h = flip_h
        mapping.flip_v = flip_v
        mapping.scale = max(0.01, min(1.0, scale))
        mapping.sharpen = max(0.0, min(4.0, sharpen))
        mapping.resampling = resampling if resampling in ("lanczos", "nearest") else "lanczos"

        # Phase 5 fix: Transition to "edited" when alignment changes (removed guard)
        if set_edited:
            mapping.status = "edited"

        return True

    def remove_mapping_for_ai_frame(self, ai_frame_id: str) -> bool:
        """Remove mapping for an AI frame.

        Args:
            ai_frame_id: ID of the AI frame (filename)

        Returns:
            True if a mapping was removed, False if none existed
        """
        original_len = len(self.mappings)
        self.mappings = [m for m in self.mappings if m.ai_frame_id != ai_frame_id]
        if len(self.mappings) < original_len:
            self._invalidate_mapping_index()
            return True
        return False

    @property
    def mapped_count(self) -> int:
        """Number of AI frames that have mappings."""
        return len(self.mappings)

    @property
    def total_ai_frames(self) -> int:
        """Total number of AI frames."""
        return len(self.ai_frames)

    # ─── AI Frame Organization (V4) ───────────────────────────────────────────

    def set_frame_display_name(self, ai_frame_id: str, display_name: str | None) -> bool:
        """Set display name for an AI frame.

        Args:
            ai_frame_id: ID of the AI frame (filename)
            display_name: New display name, or None to clear

        Returns:
            True if frame was found and updated, False otherwise
        """
        frame = self.get_ai_frame_by_id(ai_frame_id)
        if frame is None:
            return False
        # Dataclasses are mutable, we can update in place
        object.__setattr__(frame, "display_name", display_name)
        return True

    def add_frame_tag(self, ai_frame_id: str, tag: str) -> bool:
        """Add a tag to an AI frame.

        Args:
            ai_frame_id: ID of the AI frame (filename)
            tag: Tag to add (must be in FRAME_TAGS)

        Returns:
            True if frame was found and tag added, False otherwise
        """
        if tag not in FRAME_TAGS:
            logger.warning("Invalid tag '%s', must be one of %s", tag, FRAME_TAGS)
            return False
        frame = self.get_ai_frame_by_id(ai_frame_id)
        if frame is None:
            return False
        object.__setattr__(frame, "tags", frame.tags | {tag})
        return True

    def remove_frame_tag(self, ai_frame_id: str, tag: str) -> bool:
        """Remove a tag from an AI frame.

        Args:
            ai_frame_id: ID of the AI frame (filename)
            tag: Tag to remove

        Returns:
            True if frame was found and tag removed, False otherwise
        """
        frame = self.get_ai_frame_by_id(ai_frame_id)
        if frame is None:
            return False
        object.__setattr__(frame, "tags", frame.tags - {tag})
        return True

    def toggle_frame_tag(self, ai_frame_id: str, tag: str) -> bool:
        """Toggle a tag on an AI frame.

        Args:
            ai_frame_id: ID of the AI frame (filename)
            tag: Tag to toggle (must be in FRAME_TAGS)

        Returns:
            True if frame was found and tag toggled, False otherwise
        """
        if tag not in FRAME_TAGS:
            logger.warning("Invalid tag '%s', must be one of %s", tag, FRAME_TAGS)
            return False
        frame = self.get_ai_frame_by_id(ai_frame_id)
        if frame is None:
            return False
        if tag in frame.tags:
            object.__setattr__(frame, "tags", frame.tags - {tag})
        else:
            object.__setattr__(frame, "tags", frame.tags | {tag})
        return True

    def get_frames_with_tag(self, tag: str) -> list[AIFrame]:
        """Get all AI frames with a specific tag.

        Args:
            tag: Tag to filter by

        Returns:
            List of AIFrame objects with the tag
        """
        return [f for f in self.ai_frames if tag in f.tags]

    def set_frame_tags(self, ai_frame_id: str, tags: frozenset[str]) -> bool:
        """Set all tags for an AI frame (replace existing).

        Args:
            ai_frame_id: ID of the AI frame (filename)
            tags: New set of tags (invalid tags are filtered out)

        Returns:
            True if frame was found and updated, False otherwise
        """
        frame = self.get_ai_frame_by_id(ai_frame_id)
        if frame is None:
            return False
        valid_tags = frozenset(t for t in tags if t in FRAME_TAGS)
        object.__setattr__(frame, "tags", valid_tags)
        return True

    # ─── Capture (GameFrame) Organization ──────────────────────────────────────

    def set_capture_display_name(self, game_frame_id: str, display_name: str | None) -> bool:
        """Set display name for a game frame (capture).

        Args:
            game_frame_id: ID of the game frame
            display_name: New display name, or None to clear

        Returns:
            True if frame was found and updated, False otherwise
        """
        frame = self.get_game_frame_by_id(game_frame_id)
        if frame is None:
            return False
        object.__setattr__(frame, "display_name", display_name)
        return True

    def detect_stale_entries(self) -> dict[str, bool]:
        """Check all game frames for stale selected_entry_ids.

        A game frame has "stale" entries when its `selected_entry_ids` no longer
        match the IDs in the current capture file (e.g., after re-recording the capture).
        When entries are stale, the system falls back to ROM offset filtering.

        Returns:
            Dictionary mapping game_frame_id -> is_stale (bool).
            Only includes frames with selected_entry_ids (not ROM-only workflow).
        """
        from core.mesen_integration.click_extractor import MesenCaptureParser

        stale_status: dict[str, bool] = {}

        for game_frame in self.game_frames:
            # Skip frames without selected_entry_ids (ROM-only workflow)
            if not game_frame.selected_entry_ids:
                continue

            # Skip frames without capture path
            if not game_frame.capture_path:
                continue

            # Check if capture file exists
            if not game_frame.capture_path.exists():
                logger.warning(
                    "Capture file not found for frame '%s': %s",
                    game_frame.id,
                    game_frame.capture_path,
                )
                stale_status[game_frame.id] = True
                continue

            # Load the capture file and check if entry IDs are still valid
            try:
                parser = MesenCaptureParser()
                capture_result = parser.parse_file(game_frame.capture_path)

                # Get the IDs of all entries in the current capture
                current_entry_ids = {entry.id for entry in capture_result.entries}

                # Check if all selected_entry_ids are present
                selected_ids_set = set(game_frame.selected_entry_ids)
                is_stale = not selected_ids_set.issubset(current_entry_ids)

                if is_stale:
                    stale_status[game_frame.id] = True
                    logger.debug(
                        "Game frame '%s' has stale entries: %s not in current capture IDs %s",
                        game_frame.id,
                        selected_ids_set - current_entry_ids,
                        current_entry_ids,
                    )

            except Exception as e:
                logger.warning(
                    "Failed to parse capture file for frame '%s': %s",
                    game_frame.id,
                    e,
                )
                stale_status[game_frame.id] = True

        return stale_status
