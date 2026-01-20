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

    def to_dict(self) -> dict[str, object]:
        """Serialize to dictionary for JSON storage."""
        return {
            "path": str(self.path),
            "index": self.index,
            "width": self.width,
            "height": self.height,
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> AIFrame:
        """Deserialize from dictionary."""
        return cls(
            path=Path(cast(str, data["path"])),
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

    def to_dict(self) -> dict[str, object]:
        """Serialize to dictionary for JSON storage."""
        return {
            "id": self.id,
            "rom_offsets": self.rom_offsets,
            "capture_path": str(self.capture_path) if self.capture_path else None,
            "palette_index": self.palette_index,
            "width": self.width,
            "height": self.height,
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> GameFrame:
        """Deserialize from dictionary."""
        capture_path = data.get("capture_path")
        return cls(
            id=cast(str, data["id"]),
            rom_offsets=cast(list[int], data.get("rom_offsets", [])),
            capture_path=Path(cast(str, capture_path)) if capture_path else None,
            palette_index=cast(int, data.get("palette_index", 0)),
            width=cast(int, data.get("width", 0)),
            height=cast(int, data.get("height", 0)),
        )


@dataclass
class FrameMapping:
    """Links an AI frame to a game frame."""

    ai_frame_index: int
    game_frame_id: str
    status: str = "mapped"  # "unmapped", "mapped", "edited", "injected"

    # Alignment for overlay (AI frame relative to game frame)
    offset_x: int = 0
    offset_y: int = 0
    flip_h: bool = False
    flip_v: bool = False

    def to_dict(self) -> dict[str, object]:
        """Serialize to dictionary for JSON storage."""
        return {
            "ai_frame_index": self.ai_frame_index,
            "game_frame_id": self.game_frame_id,
            "status": self.status,
            "offset_x": self.offset_x,
            "offset_y": self.offset_y,
            "flip_h": self.flip_h,
            "flip_v": self.flip_v,
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> FrameMapping:
        """Deserialize from dictionary."""
        return cls(
            ai_frame_index=cast(int, data["ai_frame_index"]),
            game_frame_id=cast(str, data["game_frame_id"]),
            status=cast(str, data.get("status", "mapped")),
            offset_x=cast(int, data.get("offset_x", 0)),
            offset_y=cast(int, data.get("offset_y", 0)),
            flip_h=cast(bool, data.get("flip_h", False)),
            flip_v=cast(bool, data.get("flip_v", False)),
        )


@dataclass
class FrameMappingProject:
    """Container for a complete frame mapping project.

    A project consists of:
    - AI-generated frames (from a directory of PNG files)
    - Game frames (captured from Mesen 2)
    - Mappings linking AI frames to game frames
    """

    name: str
    ai_frames_dir: Path | None = None
    ai_frames: list[AIFrame] = field(default_factory=list)
    game_frames: list[GameFrame] = field(default_factory=list)
    mappings: list[FrameMapping] = field(default_factory=list)

    def save(self, path: Path) -> None:
        """Save project to JSON file.

        Args:
            path: Destination file path (should end in .spritepal-mapping.json)
        """
        data = {
            "version": 1,
            "name": self.name,
            "ai_frames_dir": str(self.ai_frames_dir) if self.ai_frames_dir else None,
            "ai_frames": [f.to_dict() for f in self.ai_frames],
            "game_frames": [f.to_dict() for f in self.game_frames],
            "mappings": [m.to_dict() for m in self.mappings],
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        logger.info("Saved frame mapping project to %s", path)

    @classmethod
    def load(cls, path: Path) -> FrameMappingProject:
        """Load project from JSON file.

        Args:
            path: Source file path

        Returns:
            Loaded FrameMappingProject instance

        Raises:
            FileNotFoundError: If file doesn't exist
            json.JSONDecodeError: If file is not valid JSON
            KeyError: If required fields are missing
        """
        with open(path, encoding="utf-8") as f:
            data = json.load(f)

        ai_frames_dir = data.get("ai_frames_dir")
        project = cls(
            name=data["name"],
            ai_frames_dir=Path(ai_frames_dir) if ai_frames_dir else None,
            ai_frames=[AIFrame.from_dict(f) for f in data.get("ai_frames", [])],
            game_frames=[GameFrame.from_dict(f) for f in data.get("game_frames", [])],
            mappings=[FrameMapping.from_dict(m) for m in data.get("mappings", [])],
        )
        logger.info("Loaded frame mapping project from %s", path)
        return project

    def get_mapping_for_ai_frame(self, ai_frame_index: int) -> FrameMapping | None:
        """Get mapping for a specific AI frame."""
        for mapping in self.mappings:
            if mapping.ai_frame_index == ai_frame_index:
                return mapping
        return None

    def get_mapping_for_game_frame(self, game_frame_id: str) -> FrameMapping | None:
        """Get mapping for a specific game frame."""
        for mapping in self.mappings:
            if mapping.game_frame_id == game_frame_id:
                return mapping
        return None

    def get_ai_frame_by_index(self, index: int) -> AIFrame | None:
        """Get AI frame by index."""
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

    def create_mapping(self, ai_frame_index: int, game_frame_id: str) -> FrameMapping:
        """Create a new mapping between an AI frame and a game frame.

        If a mapping already exists for the AI frame, it is updated.

        Args:
            ai_frame_index: Index of the AI frame
            game_frame_id: ID of the game frame

        Returns:
            The created or updated mapping
        """
        # Remove existing mapping for this AI frame if any
        self.mappings = [m for m in self.mappings if m.ai_frame_index != ai_frame_index]

        mapping = FrameMapping(
            ai_frame_index=ai_frame_index,
            game_frame_id=game_frame_id,
            status="mapped",
        )
        self.mappings.append(mapping)
        return mapping

    def remove_mapping_for_ai_frame(self, ai_frame_index: int) -> bool:
        """Remove mapping for an AI frame.

        Args:
            ai_frame_index: Index of the AI frame

        Returns:
            True if a mapping was removed, False if none existed
        """
        original_len = len(self.mappings)
        self.mappings = [m for m in self.mappings if m.ai_frame_index != ai_frame_index]
        return len(self.mappings) < original_len

    @property
    def mapped_count(self) -> int:
        """Number of AI frames that have mappings."""
        return len(self.mappings)

    @property
    def total_ai_frames(self) -> int:
        """Total number of AI frames."""
        return len(self.ai_frames)
