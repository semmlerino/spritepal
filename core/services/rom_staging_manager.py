"""ROM staging manager for atomic file operations.

Handles safe ROM file operations with staging for atomic writes:
- Creating numbered copies for injection
- Staging files for atomic commit/rollback
- RAW slot size detection

This extracts low-level file operations from the controller.
"""

from __future__ import annotations

import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from utils.logging_config import get_logger

logger = get_logger(__name__)


@dataclass
class StagingSession:
    """Tracks a staging operation for atomic commit/rollback.

    Attributes:
        staging_path: Path to the temporary staging file.
        target_path: Path where the staging file will be committed.
        committed: Whether the staging file has been committed.
        source_path: Original source ROM path (for tracking).
    """

    staging_path: Path
    target_path: Path
    committed: bool = field(default=False)
    source_path: Path | None = field(default=None)

    def __post_init__(self) -> None:
        """Validate paths."""
        if not self.staging_path.suffix.endswith(".staging"):
            raise ValueError(f"Staging path must end with .staging: {self.staging_path}")


class ROMStagingManager:
    """Atomic ROM file operations with staging for safety.

    Provides safe file operations for ROM injection:
    1. Create numbered copies (_injected_N suffix) to preserve originals
    2. Use staging files (.staging) for atomic writes
    3. Commit (atomic rename) or rollback (delete) staging files
    4. Detect RAW slot boundaries to prevent overwriting adjacent data

    Usage:
        manager = ROMStagingManager()

        # Create a copy for injection
        injection_path = manager.create_injection_copy(rom_path)

        # Create staging for atomic writes
        session = manager.create_staging(injection_path)

        try:
            # ... perform injection operations on session.staging_path ...
            manager.commit(session)
        except Exception:
            manager.rollback(session)
    """

    def create_injection_copy(
        self,
        rom_path: Path,
        output_path: Path | None = None,
    ) -> Path | None:
        """Create a numbered copy of the ROM for injection.

        Creates a copy with a numbered suffix (_injected_N) to avoid
        overwriting the original or conflicting with existing files.

        Args:
            rom_path: Path to the source ROM.
            output_path: Optional explicit output path. If provided,
                        uses its directory and name as base.

        Returns:
            Path to the created copy, or None if creation failed.
        """
        # Determine output directory and base name
        if output_path is not None:
            output_dir = output_path.parent
            base_name = output_path.stem
            extension = output_path.suffix
        else:
            output_dir = rom_path.parent
            base_name = rom_path.stem
            extension = rom_path.suffix

        # Remove existing suffixes to get clean base name
        base_name = base_name.removesuffix("_modified")
        base_name = re.sub(r"_injected_\d+$", "", base_name)

        # Find next available number
        counter = 1
        while True:
            new_name = f"{base_name}_injected_{counter}{extension}"
            new_path = output_dir / new_name
            if not new_path.exists():
                break
            counter += 1

        # Copy the ROM
        try:
            shutil.copy2(rom_path, new_path)
            logger.info("Created injection ROM copy: %s", new_path)
            return new_path
        except OSError as e:
            logger.exception("Failed to create ROM copy: %s", e)
            return None

    def create_staging(self, target_path: Path) -> StagingSession | None:
        """Create a staging copy for atomic writes.

        Creates a temporary .staging file that will be written to during
        injection. On success, commit() atomically renames it to the target.
        On failure, rollback() deletes it.

        Args:
            target_path: Path to the target file that will be replaced on commit.

        Returns:
            StagingSession tracking the operation, or None if creation failed.
        """
        staging_path = target_path.with_suffix(target_path.suffix + ".staging")

        try:
            shutil.copy2(target_path, staging_path)
            logger.info("Created staging ROM copy: %s", staging_path)
            return StagingSession(
                staging_path=staging_path,
                target_path=target_path,
                source_path=target_path,
            )
        except OSError as e:
            logger.exception("Failed to create staging ROM copy: %s", e)
            return None

    def commit(self, session: StagingSession) -> bool:
        """Commit staging file by atomically replacing target.

        Performs an atomic rename from staging to target. On same filesystem,
        this is a single operation that can't leave the file in an
        inconsistent state.

        Args:
            session: The staging session to commit.

        Returns:
            True if commit succeeded, False otherwise.
        """
        if session.committed:
            logger.warning("Staging session already committed: %s", session.staging_path)
            return True

        try:
            session.staging_path.replace(session.target_path)
            session.committed = True
            logger.info("Committed staging file to: %s", session.target_path)
            return True
        except OSError as e:
            logger.exception("Failed to commit staging file: %s", e)
            return False

    def rollback(self, session: StagingSession | None) -> None:
        """Delete staging file on injection failure.

        Safe to call multiple times or with None.

        Args:
            session: The staging session to rollback, or None.
        """
        if session is None:
            return

        if session.committed:
            logger.debug("Staging session already committed, nothing to rollback")
            return

        if session.staging_path.exists():
            try:
                session.staging_path.unlink()
                logger.info("Rolled back staging file: %s", session.staging_path)
            except OSError as e:
                logger.warning(
                    "Failed to delete staging file %s: %s",
                    session.staging_path,
                    e,
                )

    def detect_raw_slot_size(
        self,
        rom_data: bytes,
        file_offset: int,
        max_tiles: int = 256,
    ) -> int | None:
        """Detect the size of a RAW (uncompressed) sprite slot in ROM.

        Scans from the offset, counting 32-byte tiles (8x8 4bpp) until hitting
        a padding boundary (block of all 0x00 or 0xFF bytes).

        This prevents overwriting adjacent ROM data when the captured sprite
        has more tiles than the original slot can hold.

        Args:
            rom_data: Full ROM data bytes.
            file_offset: Starting file offset (accounting for SMC header).
            max_tiles: Maximum tiles to scan before giving up.

        Returns:
            Number of tiles in the slot, or None if no boundary detected.
        """
        # Account for SMC header (512 bytes if present)
        smc_header = 512 if len(rom_data) % 0x8000 == 512 else 0
        actual_offset = file_offset + smc_header

        # Validate offset is within ROM
        if actual_offset < 0 or actual_offset >= len(rom_data):
            logger.warning(
                "detect_raw_slot_size: offset 0x%X out of bounds (ROM size: 0x%X)",
                file_offset,
                len(rom_data),
            )
            return None

        tile_size = 32  # 8x8 4bpp tile = 32 bytes

        for tile_index in range(max_tiles):
            tile_start = actual_offset + (tile_index * tile_size)
            tile_end = tile_start + tile_size

            # Stop if we would read past end of ROM
            if tile_end > len(rom_data):
                break

            tile_data = rom_data[tile_start:tile_end]

            # Check for padding boundary (all 0x00 or all 0xFF)
            if all(b == 0x00 for b in tile_data) or all(b == 0xFF for b in tile_data):
                # Found boundary - return count of tiles before it
                return tile_index if tile_index > 0 else None

        # No boundary found within max_tiles
        return None

    def cleanup_on_failure(
        self,
        session: StagingSession | None,
        injection_path: Path | None,
        was_existing_output: bool,
    ) -> None:
        """Clean up files after a failure.

        Rolls back staging and optionally removes the injection copy
        if it was freshly created (not reusing existing output).

        Args:
            session: Staging session to rollback.
            injection_path: Path to injection ROM copy.
            was_existing_output: True if injection_path existed before
                               we started (don't delete in that case).
        """
        self.rollback(session)

        # Only delete injection copy if we created it (not reusing existing)
        if injection_path is not None and not was_existing_output:
            if injection_path.exists():
                try:
                    injection_path.unlink()
                    logger.info("Cleaned up injection copy: %s", injection_path)
                except OSError as e:
                    logger.warning(
                        "Failed to clean up injection copy %s: %s",
                        injection_path,
                        e,
                    )
