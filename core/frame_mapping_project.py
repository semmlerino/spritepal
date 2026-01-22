"""Data model for Frame Mapping projects.

A Frame Mapping project links AI-generated sprite frames to game animation
frames captured from Mesen 2. This enables one-click workflow for replacing
game sprites with AI-generated alternatives.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import cast

logger = logging.getLogger(__name__)


@dataclass
class AIFrame:
    """Represents an AI-generated sprite frame."""

    path: Path
    index: int
    width: int = 0
    height: int = 0

    @property
    def id(self) -> str:
        """Stable identifier for this AI frame (filename).

        Returns the filename which remains stable across reloads/reordering,
        unlike the position-dependent `index` field.
        """
        return self.path.name

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

        return {
            "path": path_str,
            "index": self.index,
            "width": self.width,
            "height": self.height,
        }

    @classmethod
    def from_dict(cls, data: dict[str, object], base_path: Path | None = None) -> AIFrame:
        """Deserialize from dictionary.

        Args:
            data: Dictionary data.
            base_path: Optional base directory to resolve relative paths against.
        """
        path = Path(cast(str, data["path"]))
        if base_path and not path.is_absolute():
            path = base_path / path

        return cls(
            path=path,
            index=cast(int, data["index"]),
            width=cast(int, data.get("width", 0)),
            height=cast(int, data.get("height", 0)),
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

        return {
            "id": self.id,
            "rom_offsets": self.rom_offsets,
            "capture_path": capture_path_str,
            "palette_index": self.palette_index,
            "width": self.width,
            "height": self.height,
            "selected_entry_ids": self.selected_entry_ids,
        }

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

        return cls(
            id=cast(str, data["id"]),
            rom_offsets=cast(list[int], data.get("rom_offsets", [])),
            capture_path=capture_path,
            palette_index=cast(int, data.get("palette_index", 0)),
            width=cast(int, data.get("width", 0)),
            height=cast(int, data.get("height", 0)),
            selected_entry_ids=cast(list[int], data.get("selected_entry_ids", [])),
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
    scale: float = 1.0  # Uniform scale factor (0.1 - 10.0)

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
        )


# Supported project file versions
SUPPORTED_VERSIONS = {1, 2}
CURRENT_VERSION = 2


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
    """

    name: str
    ai_frames_dir: Path | None = None
    ai_frames: list[AIFrame] = field(default_factory=list)
    game_frames: list[GameFrame] = field(default_factory=list)
    mappings: list[FrameMapping] = field(default_factory=list)

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

    def save(self, path: Path) -> None:
        """Save project to JSON file atomically.

        Uses temp file + atomic rename to prevent corruption on crash.

        Args:
            path: Destination file path (should end in .spritepal-mapping.json)
        """
        import os
        import tempfile

        base_path = path.parent

        ai_frames_dir_str = None
        if self.ai_frames_dir:
            ai_frames_dir_str = str(self.ai_frames_dir)
            if self.ai_frames_dir.is_absolute():
                try:
                    ai_frames_dir_str = str(self.ai_frames_dir.relative_to(base_path))
                except ValueError:
                    pass

        data = {
            "version": CURRENT_VERSION,
            "name": self.name,
            "ai_frames_dir": ai_frames_dir_str,
            "ai_frames": [f.to_dict(base_path) for f in self.ai_frames],
            "game_frames": [f.to_dict(base_path) for f in self.game_frames],
            "mappings": [m.to_dict() for m in self.mappings],
        }

        # Ensure parent directory exists
        path.parent.mkdir(parents=True, exist_ok=True)

        # Atomic save: write to temp file then rename
        fd, tmp_path_str = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
        tmp_path = Path(tmp_path_str)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            # Atomic rename (on same filesystem)
            tmp_path.replace(path)
            logger.info("Saved frame mapping project to %s (v%d)", path, CURRENT_VERSION)
        except Exception:
            # Clean up temp file on failure
            try:
                tmp_path.unlink()
            except OSError:
                pass
            raise

    @classmethod
    def load(cls, path: Path) -> FrameMappingProject:
        """Load project from JSON file.

        Supports v1 (legacy) and v2 (current) formats. V1 projects are
        automatically migrated to v2 format on next save.

        Args:
            path: Source file path

        Returns:
            Loaded FrameMappingProject instance

        Raises:
            FileNotFoundError: If file doesn't exist
            json.JSONDecodeError: If file is not valid JSON
            KeyError: If required fields are missing
            ValueError: If version is unsupported
        """
        base_path = path.parent
        with open(path, encoding="utf-8") as f:
            data = json.load(f)

        # Version validation
        version = data.get("version", 1)
        if version not in SUPPORTED_VERSIONS:
            raise ValueError(
                f"Unsupported project version: {version}. Supported versions: {sorted(SUPPORTED_VERSIONS)}"
            )

        ai_frames_dir_raw = data.get("ai_frames_dir")
        ai_frames_dir = Path(ai_frames_dir_raw) if ai_frames_dir_raw else None
        if ai_frames_dir and not ai_frames_dir.is_absolute():
            ai_frames_dir = base_path / ai_frames_dir

        # Load AI frames first (needed for v1 migration)
        ai_frames = [AIFrame.from_dict(f, base_path) for f in data.get("ai_frames", [])]

        # Load game frames
        game_frames = [GameFrame.from_dict(f, base_path) for f in data.get("game_frames", [])]

        # Load mappings with v1 migration support
        if version == 1:
            logger.info("Migrating v1 project to v2 format (ai_frame_index -> ai_frame_id)")
            mappings = [FrameMapping.from_dict(m, ai_frames) for m in data.get("mappings", [])]
        else:
            mappings = [FrameMapping.from_dict(m) for m in data.get("mappings", [])]

        project = cls(
            name=data["name"],
            ai_frames_dir=ai_frames_dir,
            ai_frames=ai_frames,
            game_frames=game_frames,
            mappings=mappings,
        )

        # Prune orphaned mappings (referencing non-existent frames)
        project._prune_orphaned_mappings()

        logger.info("Loaded frame mapping project from %s (v%d)", path, version)
        return project

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

    def get_mapping_for_ai_frame_index(self, ai_frame_index: int) -> FrameMapping | None:
        """Get mapping for a specific AI frame by index.

        Compatibility method for code that still uses indices.
        Converts index to ID internally.

        Args:
            ai_frame_index: The AI frame index

        Returns:
            FrameMapping if found, None otherwise
        """
        frame = self.get_ai_frame_by_index(ai_frame_index)
        if frame is None:
            return None
        return self.get_mapping_for_ai_frame(frame.id)

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

    def get_ai_frame_index_linked_to_game_frame(self, game_frame_id: str) -> int | None:
        """Get the AI frame index linked to a specific game frame.

        Compatibility method for code that still uses indices.

        Args:
            game_frame_id: ID of the game frame

        Returns:
            AI frame index if game frame is linked, None otherwise
        """
        ai_frame_id = self.get_ai_frame_linked_to_game_frame(game_frame_id)
        if ai_frame_id is None:
            return None
        ai_frame = self.get_ai_frame_by_id(ai_frame_id)
        return ai_frame.index if ai_frame else None

    def get_ai_frame_by_id(self, ai_frame_id: str) -> AIFrame | None:
        """Get AI frame by ID (filename).

        O(1) lookup using internal index.
        """
        return self._ai_frame_index_by_id.get(ai_frame_id)

    def get_ai_frame_by_index(self, index: int) -> AIFrame | None:
        """Get AI frame by index.

        O(n) lookup - prefer get_ai_frame_by_id when possible.
        """
        for frame in self.ai_frames:
            if frame.index == index:
                return frame
        return None

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

    def create_mapping(self, ai_frame_id: str, game_frame_id: str) -> FrameMapping:
        """Create a new mapping between an AI frame and a game frame.

        If a mapping already exists for the AI frame, it is updated.
        If a mapping already exists for the game frame, it is removed (1:1 enforcement).

        Args:
            ai_frame_id: ID of the AI frame (filename)
            game_frame_id: ID of the game frame

        Returns:
            The created or updated mapping
        """
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

    def create_mapping_by_index(self, ai_frame_index: int, game_frame_id: str) -> FrameMapping | None:
        """Create a new mapping using AI frame index.

        Compatibility method for code that still uses indices.

        Args:
            ai_frame_index: Index of the AI frame
            game_frame_id: ID of the game frame

        Returns:
            The created mapping, or None if AI frame not found
        """
        ai_frame = self.get_ai_frame_by_index(ai_frame_index)
        if ai_frame is None:
            return None
        return self.create_mapping(ai_frame.id, game_frame_id)

    def update_mapping_alignment(
        self,
        ai_frame_id: str,
        offset_x: int,
        offset_y: int,
        flip_h: bool,
        flip_v: bool,
        scale: float = 1.0,
        set_edited: bool = True,
    ) -> bool:
        """Update alignment for a mapping.

        Args:
            ai_frame_id: ID of the AI frame (filename)
            offset_x: X offset for alignment
            offset_y: Y offset for alignment
            flip_h: Horizontal flip state
            flip_v: Vertical flip state
            scale: Scale factor (0.1 - 10.0)
            set_edited: If True and status is not 'injected', set status to 'edited'.
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
        mapping.scale = max(0.1, min(10.0, scale))

        # Phase 5 fix: Transition to "edited" when alignment changes (removed guard)
        if set_edited:
            mapping.status = "edited"

        return True

    def update_mapping_alignment_by_index(
        self,
        ai_frame_index: int,
        offset_x: int,
        offset_y: int,
        flip_h: bool,
        flip_v: bool,
        scale: float = 1.0,
        set_edited: bool = True,
    ) -> bool:
        """Update alignment for a mapping using AI frame index.

        Compatibility method for code that still uses indices.
        """
        frame = self.get_ai_frame_by_index(ai_frame_index)
        if frame is None:
            return False
        return self.update_mapping_alignment(frame.id, offset_x, offset_y, flip_h, flip_v, scale, set_edited)

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

    def remove_mapping_for_ai_frame_index(self, ai_frame_index: int) -> bool:
        """Remove mapping for an AI frame using index.

        Compatibility method for code that still uses indices.

        Args:
            ai_frame_index: Index of the AI frame

        Returns:
            True if a mapping was removed, False if none existed
        """
        frame = self.get_ai_frame_by_index(ai_frame_index)
        if frame is None:
            return False
        return self.remove_mapping_for_ai_frame(frame.id)

    @property
    def mapped_count(self) -> int:
        """Number of AI frames that have mappings."""
        return len(self.mappings)

    @property
    def total_ai_frames(self) -> int:
        """Total number of AI frames."""
        return len(self.ai_frames)
