"""Persistence for tile arrangement configurations.

Stores arrangement metadata as sidecar JSON files alongside ROMs,
enabling arrangements to be reloaded across sessions.
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

logger = logging.getLogger(__name__)

FORMAT_VERSION = "1.2"  # Added grid_mapping


# Module-level cache for ROM hashes to avoid redundant I/O
_ROM_HASH_CACHE: dict[str, str] = {}


@dataclass
class ArrangementConfig:
    """Persisted arrangement configuration.

    Stores all data needed to reconstruct an ArrangementBridge from
    a GridArrangementManager's state.
    """

    rom_hash: str
    rom_offset: int
    sprite_name: str
    grid_dimensions: dict[str, int]
    arrangement_order: list[dict[str, str]]
    groups: list[dict[str, object]]
    total_tiles: int
    logical_width: int
    # Grid mapping (added in v1.2) - stores visual layout
    # Key: "row,col", Value: {"type": str, "key": str}
    grid_mapping: dict[str, dict[str, str]] = field(default_factory=dict)
    # Overlay state (added in v1.1)
    overlay_path: str | None = None
    overlay_x: float = 0.0
    overlay_y: float = 0.0
    overlay_scale: float = 1.0  # Added in v1.2 fix
    overlay_opacity: float = 0.5
    overlay_visible: bool = True
    # Timestamps
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    last_modified: datetime = field(default_factory=lambda: datetime.now(UTC))

    @staticmethod
    def get_sidecar_path(rom_path: str, offset: int) -> Path:
        """Get sidecar file path for given ROM and offset.

        Args:
            rom_path: Path to ROM file
            offset: Sprite offset in ROM

        Returns:
            Path to sidecar JSON file
        """
        rom_path_obj = Path(rom_path)
        return rom_path_obj.parent / f"{rom_path_obj.stem}_0x{offset:06X}.arrangement.json"

    @staticmethod
    def compute_rom_hash(rom_path: str) -> str:
        """Compute SHA256 hash of ROM file with caching.

        Args:
            rom_path: Path to ROM file

        Returns:
            Hex-encoded SHA256 hash
        """
        abs_path = str(Path(rom_path).absolute())
        if abs_path in _ROM_HASH_CACHE:
            return _ROM_HASH_CACHE[abs_path]

        hasher = hashlib.sha256()
        try:
            with open(rom_path, "rb") as f:
                for chunk in iter(lambda: f.read(65536), b""):
                    hasher.update(chunk)
            hash_val = hasher.hexdigest()
            _ROM_HASH_CACHE[abs_path] = hash_val
            return hash_val
        except OSError as e:
            logger.error("Failed to compute ROM hash for %s: %s", rom_path, e)
            return ""

    @staticmethod
    def exists_for(rom_path: str, offset: int) -> bool:
        """Check if arrangement exists for ROM/offset.

        Args:
            rom_path: Path to ROM file
            offset: Sprite offset in ROM

        Returns:
            True if sidecar file exists
        """
        return ArrangementConfig.get_sidecar_path(rom_path, offset).exists()

    def save(self, path: Path | None = None) -> Path:
        """Save arrangement to sidecar file.

        Args:
            path: Optional explicit path. If None, uses default sidecar path.

        Returns:
            Path where file was saved
        """
        if path is None:
            msg = "Path must be provided"
            raise ValueError(msg)

        base_path = path.parent
        overlay_path_str = self.overlay_path
        if overlay_path_str:
            overlay_p = Path(overlay_path_str)
            if overlay_p.is_absolute():
                try:
                    overlay_path_str = str(overlay_p.relative_to(base_path))
                except ValueError:
                    pass

        self.last_modified = datetime.now(UTC)
        data = {
            "format_version": FORMAT_VERSION,
            "rom_hash": self.rom_hash,
            "rom_offset": self.rom_offset,
            "rom_offset_hex": f"0x{self.rom_offset:06X}",
            "sprite_name": self.sprite_name,
            "grid_dimensions": self.grid_dimensions,
            "arrangement_order": self.arrangement_order,
            "groups": self.groups,
            "total_tiles": self.total_tiles,
            "logical_width": self.logical_width,
            # Grid mapping
            "grid_mapping": self.grid_mapping,
            # Overlay state
            "overlay_path": overlay_path_str,
            "overlay_x": self.overlay_x,
            "overlay_y": self.overlay_y,
            "overlay_scale": self.overlay_scale,
            "overlay_opacity": self.overlay_opacity,
            "overlay_visible": self.overlay_visible,
            # Timestamps
            "created_at": self.created_at.isoformat(),
            "last_modified": self.last_modified.isoformat(),
        }

        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        logger.info("Saved arrangement to %s", path)
        return path

    @classmethod
    def load(cls, path: Path) -> ArrangementConfig:
        """Load arrangement from sidecar file.

        Args:
            path: Path to sidecar JSON file

        Returns:
            ArrangementConfig instance

        Raises:
            FileNotFoundError: If sidecar file doesn't exist
            json.JSONDecodeError: If file is not valid JSON
            KeyError: If required fields are missing
        """
        data = json.loads(path.read_text(encoding="utf-8"))
        base_path = path.parent

        # Validate format version (warn but allow older versions)
        version = data.get("format_version", "0.0")
        if version != FORMAT_VERSION:
            logger.warning(
                "Arrangement format version mismatch: expected %s, got %s",
                FORMAT_VERSION,
                version,
            )

        overlay_path = data.get("overlay_path")
        if overlay_path:
            overlay_p = Path(overlay_path)
            if not overlay_p.is_absolute():
                overlay_path = str(base_path / overlay_p)

        return cls(
            rom_hash=data["rom_hash"],
            rom_offset=data["rom_offset"],
            sprite_name=data.get("sprite_name", ""),
            grid_dimensions=data["grid_dimensions"],
            arrangement_order=data["arrangement_order"],
            groups=data.get("groups", []),
            total_tiles=data["total_tiles"],
            logical_width=data["logical_width"],
            # Grid mapping (v1.2+, defaults to empty for older files)
            grid_mapping=data.get("grid_mapping", {}),
            # Overlay state (v1.1+, defaults for older files)
            overlay_path=overlay_path,
            overlay_x=data.get("overlay_x", 0),
            overlay_y=data.get("overlay_y", 0),
            overlay_scale=data.get("overlay_scale", 1.0),
            overlay_opacity=data.get("overlay_opacity", 0.5),
            overlay_visible=data.get("overlay_visible", True),
            # Timestamps
            created_at=datetime.fromisoformat(data["created_at"]),
            last_modified=datetime.fromisoformat(data["last_modified"]),
        )

    @classmethod
    def from_metadata(
        cls,
        metadata: dict[str, object],
        rom_path: str,
        rom_offset: int,
        sprite_name: str,
    ) -> ArrangementConfig:
        """Create config from GridArrangementManager metadata.

        Args:
            metadata: Metadata dict from create_arrangement_preview_data()
            rom_path: Path to ROM file
            rom_offset: Sprite offset in ROM
            sprite_name: Display name of sprite

        Returns:
            ArrangementConfig instance
        """
        return cls(
            rom_hash=cls.compute_rom_hash(rom_path),
            rom_offset=rom_offset,
            sprite_name=sprite_name,
            grid_dimensions=cast(dict[str, int], metadata["grid_dimensions"]),
            arrangement_order=cast(list[dict[str, str]], metadata["arrangement_order"]),
            groups=cast(list[dict[str, object]], metadata.get("groups", [])),
            total_tiles=cast(int, metadata["total_tiles"]),
            logical_width=cast(int, metadata.get("logical_width", 16)),
            # Grid mapping (v1.2+, defaults to empty for older files)
            grid_mapping=cast(dict[str, dict[str, str]], metadata.get("grid_mapping", {})),
            # Overlay state (injected by dialog)
            overlay_path=cast(str | None, metadata.get("overlay_path")),
            overlay_x=cast(float, metadata.get("overlay_x", 0.0)),
            overlay_y=cast(float, metadata.get("overlay_y", 0.0)),
            overlay_scale=cast(float, metadata.get("overlay_scale", 1.0)),
            overlay_opacity=cast(float, metadata.get("overlay_opacity", 0.5)),
            overlay_visible=cast(bool, metadata.get("overlay_visible", True)),
        )

    def validate_rom_hash(self, rom_path: str) -> bool:
        """Validate that ROM hash matches.

        Args:
            rom_path: Path to ROM file to check

        Returns:
            True if hash matches, False otherwise
        """
        current_hash = self.compute_rom_hash(rom_path)
        if current_hash != self.rom_hash:
            logger.warning(
                "ROM hash mismatch for arrangement at offset 0x%06X",
                self.rom_offset,
            )
            return False
        return True
