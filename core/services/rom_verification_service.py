"""ROM verification service for tile offset validation.

This service verifies that tile ROM offsets are still valid (not stale)
and corrects them when needed. It handles the case where VRAM was
overwritten after the Lua script recorded the ROM offset.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from utils.logging_config import get_logger

if TYPE_CHECKING:
    from core.mesen_integration.click_extractor import CaptureResult, OAMEntry

logger = get_logger(__name__)


@dataclass
class ROMVerificationResult:
    """Result of ROM offset verification.

    Attributes:
        corrections: Mapping of original offset -> corrected offset (or None if not found).
        matched_hal: Number of tiles matched via HAL index.
        matched_raw: Number of tiles matched via raw search.
        not_found: Number of tiles not found in ROM.
        total: Total number of unique offsets processed.
    """

    corrections: dict[int, int | None]
    matched_hal: int = 0
    matched_raw: int = 0
    not_found: int = 0
    total: int = 0

    @property
    def all_found(self) -> bool:
        """Return True if all tiles were found in ROM."""
        return self.not_found == 0

    @property
    def has_corrections(self) -> bool:
        """Return True if any offsets were corrected."""
        return any(old != new for old, new in self.corrections.items() if new is not None)


class ROMVerificationService:
    """Service for verifying and correcting tile ROM offsets.

    Handles stale ROM offset attribution by searching the ROM for
    tile data when the recorded offset is incorrect.
    """

    def __init__(self, rom_path: Path) -> None:
        """Initialize the verification service.

        Args:
            rom_path: Path to the ROM file to verify against.
        """
        self._rom_path = rom_path
        self._rom_data: bytes | None = None
        self._matcher_initialized = False

    def verify_offsets(
        self,
        capture_result: CaptureResult,
        selected_entry_ids: list[int] | None = None,
    ) -> ROMVerificationResult:
        """Verify tile ROM offsets against the actual ROM.

        Uses ROMTileMatcher (HAL index) first, then raw search as fallback.

        Args:
            capture_result: Parsed capture with tile data.
            selected_entry_ids: If provided, only process these entries.

        Returns:
            ROMVerificationResult with corrections and statistics.
        """
        from core.mesen_integration.rom_tile_matcher import ROMTileMatcher

        corrections: dict[int, int | None] = {}
        matched_hal = 0
        matched_raw = 0
        not_found = 0

        # Initialize matcher
        matcher = ROMTileMatcher(str(self._rom_path))
        matcher.build_database()

        # Lazy-load ROM data for raw search
        if self._rom_data is None:
            self._rom_data = self._rom_path.read_bytes()

        # Process each tile
        for entry in capture_result.entries:
            if selected_entry_ids and entry.id not in selected_entry_ids:
                continue

            for tile in entry.tiles:
                if tile.rom_offset is None:
                    continue

                # Skip if already processed
                if tile.rom_offset in corrections:
                    continue

                # Search via HAL index first
                matches = matcher.lookup_vram_tile(tile.data_bytes)

                if matches:
                    best_match = matches[0]
                    corrections[tile.rom_offset] = best_match.rom_offset
                    matched_hal += 1

                    if best_match.rom_offset != tile.rom_offset:
                        logger.debug(
                            "Tile at 0x%X corrected to 0x%X (HAL index)",
                            tile.rom_offset,
                            best_match.rom_offset,
                        )
                else:
                    # Fallback: raw search
                    raw_offset = self._search_raw_tile(tile.data_bytes)
                    corrections[tile.rom_offset] = raw_offset

                    if raw_offset is not None:
                        matched_raw += 1
                        if raw_offset != tile.rom_offset:
                            logger.debug(
                                "Tile at 0x%X corrected to 0x%X (raw search)",
                                tile.rom_offset,
                                raw_offset,
                            )
                    else:
                        not_found += 1
                        logger.debug(
                            "Tile at 0x%X not found in ROM (data: %s...)",
                            tile.rom_offset,
                            tile.data_hex[:16],
                        )

        total = len(corrections)
        logger.info(
            "ROM offset verification: %d tiles, %d HAL, %d raw, %d not found",
            total,
            matched_hal,
            matched_raw,
            not_found,
        )

        return ROMVerificationResult(
            corrections=corrections,
            matched_hal=matched_hal,
            matched_raw=matched_raw,
            not_found=not_found,
            total=total,
        )

    def apply_corrections(
        self,
        entries: list[OAMEntry],
        corrections: dict[int, int | None],
    ) -> int:
        """Apply offset corrections to entry tiles in-place.

        Args:
            entries: List of OAM entries with tiles to correct.
            corrections: Mapping of old offset -> new offset.

        Returns:
            Number of tiles corrected.
        """
        corrected_count = 0

        for entry in entries:
            for tile in entry.tiles:
                if tile.rom_offset is None:
                    continue

                if tile.rom_offset in corrections:
                    new_offset = corrections[tile.rom_offset]
                    if new_offset is not None and new_offset != tile.rom_offset:
                        tile.rom_offset = new_offset
                        corrected_count += 1

        logger.debug("Applied %d offset corrections", corrected_count)
        return corrected_count

    def _search_raw_tile(self, tile_data: bytes) -> int | None:
        """Search ROM for exact 32-byte tile match.

        Fallback for tiles not in HAL-compressed blocks.
        Raw (uncompressed) tiles can be found by direct byte matching.

        Args:
            tile_data: 32 bytes of SNES 4bpp tile data.

        Returns:
            ROM offset where tile was found, or None if not found.
        """
        if len(tile_data) != 32:
            return None

        if self._rom_data is None:
            return None

        offset = self._rom_data.find(tile_data)
        return offset if offset >= 0 else None
