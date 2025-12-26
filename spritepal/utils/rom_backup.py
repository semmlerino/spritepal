"""
ROM backup utilities for SpritePal
"""

from __future__ import annotations

import os
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from utils.logging_config import get_logger
from utils.rom_exceptions import ROMBackupError

logger = get_logger(__name__)


class ROMBackupManager:
    """Manages ROM backups before modifications"""

    # Maximum number of backups to keep per ROM
    MAX_BACKUPS_PER_ROM = 10

    @classmethod
    def create_backup(cls, rom_path: str, backup_dir: str | None = None) -> str:
        """
        Create a timestamped backup of ROM file.

        Args:
            rom_path: Path to ROM file to backup
            backup_dir: Directory for backups (default: same as ROM)

        Returns:
            Path to backup file

        Raises:
            ROMBackupError: If backup creation fails
        """
        if not Path(rom_path).exists():
            raise ROMBackupError(f"ROM file not found: {rom_path}")

        # Determine backup directory
        if backup_dir is None:
            backup_dir = str(Path(rom_path).parent)

        # Create backup subdirectory
        backup_subdir = Path(backup_dir) / "spritepal_backups"
        backup_subdir.mkdir(exist_ok=True)

        # Generate backup filename
        rom_path_obj = Path(rom_path)
        rom_base = rom_path_obj.stem
        rom_ext = rom_path_obj.suffix
        timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        backup_name = f"{rom_base}_backup_{timestamp}{rom_ext}"
        backup_path = backup_subdir / backup_name

        try:
            # Copy ROM to backup
            _ = shutil.copy2(rom_path, str(backup_path))
            logger.info(f"Created backup: {backup_name}")

            # Clean up old backups
            cls._cleanup_old_backups(backup_subdir, rom_base, rom_ext)

        except Exception as e:
            raise ROMBackupError(f"Failed to create backup: {e}") from e
        else:
            return str(backup_path)

    @classmethod
    def _cleanup_old_backups(cls, backup_dir: Path, rom_base: str, rom_ext: str) -> None:
        """Remove old backups keeping only the most recent ones"""
        try:
            # Find all backups for this ROM
            backups = []

            for file_path in backup_dir.iterdir():
                if file_path.name.startswith(f"{rom_base}_backup_") and file_path.name.endswith(rom_ext):
                    mtime = file_path.stat().st_mtime
                    backups.append((mtime, file_path))

            # Sort by modification time (newest first)
            backups.sort(reverse=True)

            # Remove old backups
            for _, backup_path in backups[cls.MAX_BACKUPS_PER_ROM :]:
                backup_path.unlink()
                logger.info(f"Removed old backup: {backup_path.name}")

        except (OSError, PermissionError) as e:
            logger.warning(f"Failed to cleanup old backups: {e}")

    @classmethod
    def get_latest_backup(cls, rom_path: str, backup_dir: str | None = None) -> str | None:
        """
        Get the most recent backup for a ROM.

        Returns:
            Path to latest backup or None if no backups exist
        """
        if backup_dir is None:
            backup_dir = str(Path(rom_path).parent)

        backup_subdir = Path(backup_dir) / "spritepal_backups"
        if not backup_subdir.exists():
            return None

        rom_path_obj = Path(rom_path)
        rom_base = rom_path_obj.stem
        rom_ext = rom_path_obj.suffix

        latest_backup = None
        latest_mtime = 0

        try:
            for file_path in backup_subdir.iterdir():
                if file_path.name.startswith(f"{rom_base}_backup_") and file_path.name.endswith(rom_ext):
                    mtime = file_path.stat().st_mtime
                    if mtime > latest_mtime:
                        latest_mtime = mtime
                        latest_backup = str(file_path)
        except (OSError, PermissionError) as e:
            logger.debug(f"Error scanning backup directory: {e}")

        return latest_backup

    @classmethod
    def restore_backup(cls, backup_path: str, target_path: str) -> None:
        """
        Restore a backup to target location atomically.

        Uses temp-file-then-rename pattern to prevent corruption
        if restore is interrupted (disk full, power loss, etc).

        Args:
            backup_path: Path to backup file
            target_path: Path to restore to

        Raises:
            ROMBackupError: If restore fails
        """
        if not Path(backup_path).exists():
            raise ROMBackupError(f"Backup file not found: {backup_path}")

        target = Path(target_path)

        # Create temp file in same directory (required for atomic rename)
        temp_path = target.with_suffix(f".restore_tmp_{os.getpid()}")

        try:
            # Copy backup to temp file first
            _ = shutil.copy2(backup_path, str(temp_path))

            # Atomic rename (POSIX) / best-effort (Windows)
            temp_path.replace(target)
            logger.info(f"Restored backup to: {target_path}")

        except Exception as e:
            # Clean up temp file on any failure
            temp_path.unlink(missing_ok=True)
            raise ROMBackupError(f"Failed to restore backup: {e}") from e

    @classmethod
    def list_backups(cls, rom_path: str, backup_dir: str | None = None) -> list[dict[str, Any]]:  # pyright: ignore[reportExplicitAny] - Backup metadata
        """
        List all backups for a ROM.

        Returns:
            List of backup info dicts with keys: path, size, timestamp
        """
        rom_path_obj = Path(rom_path)

        if backup_dir is None:
            backup_dir = str(rom_path_obj.parent)

        backup_subdir = Path(backup_dir) / "spritepal_backups"
        if not backup_subdir.exists():
            return []

        rom_base = rom_path_obj.stem
        rom_ext = rom_path_obj.suffix

        backups = []

        try:
            for file_path in backup_subdir.iterdir():
                if file_path.name.startswith(f"{rom_base}_backup_") and file_path.name.endswith(rom_ext):
                    stat = file_path.stat()

                    # Extract timestamp from filename
                    timestamp_str = file_path.name[len(f"{rom_base}_backup_") : -len(rom_ext)]

                    backups.append(
                        {
                            "path": str(file_path),  # Convert to string for compatibility
                            "filename": file_path.name,
                            "size": stat.st_size,
                            "mtime": stat.st_mtime,
                            "timestamp_str": timestamp_str,
                            "date": datetime.fromtimestamp(stat.st_mtime, UTC).strftime("%Y-%m-%d %H:%M:%S"),
                        }
                    )
        except (OSError, PermissionError) as e:
            logger.warning(f"Failed to list backups: {e}")

        # Sort by modification time (newest first)
        backups.sort(key=lambda x: x["mtime"], reverse=True)

        return backups
