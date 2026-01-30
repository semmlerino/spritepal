"""Repository for frame mapping project persistence.

Handles atomic saves, version migration, and backward compatibility for
.spritepal-mapping.json files.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from pathlib import Path
from typing import cast

from core.frame_mapping_project import (
    CURRENT_VERSION,
    SUPPORTED_VERSIONS,
    AIFrame,
    FrameMapping,
    FrameMappingProject,
    GameFrame,
    SheetPalette,
)

logger = logging.getLogger(__name__)


class FrameMappingRepository:
    """Repository for persisting FrameMappingProject instances.

    Provides:
    - Atomic writes (temp file + rename)
    - Version detection and migration
    - Backward compatibility with v1-v4 formats
    - Forward compatibility (unknown fields preserved)
    """

    @staticmethod
    def save(project: FrameMappingProject, path: Path) -> None:
        """Save project to JSON file atomically.

        Uses temp file + atomic rename to prevent corruption on crash.

        Args:
            project: FrameMappingProject instance to save
            path: Destination file path (should end in .spritepal-mapping.json)

        Raises:
            OSError: If file operations fail
        """
        base_path = path.parent

        # Convert ai_frames_dir to relative path if possible
        ai_frames_dir_str = None
        if project.ai_frames_dir:
            ai_frames_dir_str = str(project.ai_frames_dir)
            if project.ai_frames_dir.is_absolute():
                try:
                    ai_frames_dir_str = str(project.ai_frames_dir.relative_to(base_path))
                except ValueError:
                    # Not under base_path, keep absolute
                    pass

        # Build JSON data structure
        data = {
            "version": CURRENT_VERSION,
            "name": project.name,
            "ai_frames_dir": ai_frames_dir_str,
            "ai_frames": [f.to_dict(base_path) for f in project.ai_frames],
            "game_frames": [f.to_dict(base_path) for f in project.game_frames],
            "mappings": [m.to_dict() for m in project.mappings],
            "sheet_palette": project.sheet_palette.to_dict() if project.sheet_palette else None,
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

    @staticmethod
    def load(path: Path) -> FrameMappingProject:
        """Load project from JSON file.

        Supports v1-v4 formats with automatic migration. Unknown fields
        are preserved for forward compatibility.

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

        # Detect version and validate
        version = FrameMappingRepository._detect_version(data)
        if version not in SUPPORTED_VERSIONS:
            raise ValueError(
                f"Unsupported project version: {version}. Supported versions: {sorted(SUPPORTED_VERSIONS)}"
            )

        # Migrate if needed (transparent to caller)
        if version < CURRENT_VERSION:
            data = FrameMappingRepository._migrate_to_current(data, version)

        # Resolve ai_frames_dir to absolute path
        ai_frames_dir_raw = data.get("ai_frames_dir")
        ai_frames_dir = None
        if ai_frames_dir_raw:
            # Normalize separators for cross-platform compatibility
            ai_frames_dir_str = cast(str, ai_frames_dir_raw).replace("\\", "/")
            ai_frames_dir = Path(ai_frames_dir_str)

        if ai_frames_dir and not ai_frames_dir.is_absolute():
            ai_frames_dir = base_path / ai_frames_dir

        # Load AI frames first (needed for v1 migration)
        ai_frames = [AIFrame.from_dict(f, base_path) for f in cast(list[dict[str, object]], data.get("ai_frames", []))]

        # Load game frames
        game_frames = [
            GameFrame.from_dict(f, base_path) for f in cast(list[dict[str, object]], data.get("game_frames", []))
        ]

        # Load mappings (v1 needs ai_frames for migration)
        if version == 1:
            mappings = [
                FrameMapping.from_dict(m, ai_frames) for m in cast(list[dict[str, object]], data.get("mappings", []))
            ]
        else:
            mappings = [FrameMapping.from_dict(m) for m in cast(list[dict[str, object]], data.get("mappings", []))]

        # Load sheet_palette (v3+, None for older versions)
        sheet_palette: SheetPalette | None = None
        sheet_palette_data = data.get("sheet_palette")
        if sheet_palette_data is not None:
            sheet_palette = SheetPalette.from_dict(cast(dict[str, object], sheet_palette_data))

        project = FrameMappingProject(
            name=cast(str, data["name"]),
            ai_frames_dir=ai_frames_dir,
            ai_frames=ai_frames,
            game_frames=game_frames,
            mappings=mappings,
            sheet_palette=sheet_palette,
        )

        # Prune orphaned mappings (referencing non-existent frames)
        project._prune_orphaned_mappings()

        # Check for stale entries and log warnings
        stale_frames = project.detect_stale_entries()
        if stale_frames:
            stale_ids = [fid for fid, is_stale in stale_frames.items() if is_stale]
            logger.warning(
                "Project loaded with %d stale game frames: %s. "
                "Capture files may have been re-recorded. Preview/injection will fall back to ROM offsets.",
                len(stale_ids),
                stale_ids,
            )

        logger.info("Loaded frame mapping project from %s (v%d)", path, version)
        return project

    @staticmethod
    def _detect_version(data: dict[str, object]) -> int:
        """Detect schema version from JSON data.

        Args:
            data: Parsed JSON dictionary

        Returns:
            Version number (defaults to 1 if not specified)
        """
        return cast(int, data.get("version", 1))

    @staticmethod
    def _migrate_to_current(data: dict[str, object], from_version: int) -> dict[str, object]:
        """Migrate project data to current version.

        Applies incremental migrations: v1 -> v2 -> v3 -> v4.

        Args:
            data: Project data at from_version
            from_version: Starting version number

        Returns:
            Migrated data at CURRENT_VERSION
        """
        if from_version == 1:
            logger.info("Migrating v1 project to v2 format (ai_frame_index -> ai_frame_id)")
            data = FrameMappingRepository._migrate_v1_to_v2(data)
            from_version = 2

        if from_version == 2:
            logger.info("Migrating v2 project to v3 format (adding sheet_palette)")
            data = FrameMappingRepository._migrate_v2_to_v3(data)
            from_version = 3

        if from_version == 3:
            logger.info("Migrating v3 project to v4 format (adding AI frame organization)")
            data = FrameMappingRepository._migrate_v3_to_v4(data)
            from_version = 4

        return data

    @staticmethod
    def _migrate_v1_to_v2(data: dict[str, object]) -> dict[str, object]:
        """Migrate v1 to v2: ai_frame_index -> ai_frame_id.

        V1 used position-dependent indices. V2 uses stable filenames.
        Migration is handled by FrameMapping.from_dict() when ai_frames are provided.

        Args:
            data: V1 project data

        Returns:
            V2 project data (version field updated)
        """
        # Migration logic is in FrameMapping.from_dict()
        # Just update version number here
        data["version"] = 2
        return data

    @staticmethod
    def _migrate_v2_to_v3(data: dict[str, object]) -> dict[str, object]:
        """Migrate v2 to v3: add sheet_palette field.

        Args:
            data: V2 project data

        Returns:
            V3 project data (sheet_palette=None for backward compat)
        """
        data["version"] = 3
        # sheet_palette defaults to None, no data migration needed
        if "sheet_palette" not in data:
            data["sheet_palette"] = None
        return data

    @staticmethod
    def _migrate_v3_to_v4(data: dict[str, object]) -> dict[str, object]:
        """Migrate v3 to v4: add display_name and tags to AI frames.

        Args:
            data: V3 project data

        Returns:
            V4 project data (display_name=None, tags=[] for existing frames)
        """
        data["version"] = 4
        # display_name and tags default to None/[] in AIFrame.from_dict()
        # No explicit data migration needed
        return data
