"""Shared filtering utilities for CaptureResult entries.

This module provides a unified filtering strategy for OAM entries that's used
by both PreviewService (UI) and InjectionOrchestrator (core). The filtering
logic handles:

1. Primary filter: selected_entry_ids (user's explicit selection)
2. Fallback filter: rom_offset matching (when entry IDs are stale)
3. Last resort: all entries (when allow_fallback=True and nothing else matches)
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from utils.logging_config import get_logger

if TYPE_CHECKING:
    from core.mesen_integration.click_extractor import CaptureResult, OAMEntry

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class FilteringResult:
    """Result of filtering capture entries.

    Attributes:
        entries: The filtered list of OAM entries.
        used_fallback: True if rom_offset fallback was used (entry IDs were stale).
        used_all_entries: True if all entries fallback was used (allow_fallback=True).
        is_stale: True if the stored entry IDs didn't match any entries in the capture.
    """

    entries: list[OAMEntry]
    used_fallback: bool
    used_all_entries: bool
    is_stale: bool

    @property
    def has_entries(self) -> bool:
        """Whether any entries were found after filtering."""
        return len(self.entries) > 0


def filter_capture_entries(
    capture_result: CaptureResult,
    selected_entry_ids: list[int],
    rom_offsets: Iterable[int],
    *,
    allow_rom_offset_fallback: bool = True,
    allow_all_entries_fallback: bool = False,
    context_label: str = "",
) -> FilteringResult:
    """Filter capture entries using a cascading fallback strategy.

    The filtering cascade is:
    1. If selected_entry_ids provided → filter by entry ID
       - If no matches and allow_rom_offset_fallback=True → fall back to rom_offset filtering
    2. If no selected_entry_ids → filter by rom_offset
    3. If nothing matches and allow_all_entries_fallback=True → use all entries

    This mirrors the behavior in both PreviewService and InjectionOrchestrator.

    Args:
        capture_result: The parsed Mesen capture containing all entries.
        selected_entry_ids: List of entry IDs to filter by (from game frame).
        rom_offsets: ROM offsets to filter by (fallback). Converted to set internally.
        allow_rom_offset_fallback: If True (default), fall back to rom_offset filtering
            when entry IDs are stale. Set to False to abort on stale entry IDs.
        allow_all_entries_fallback: If True, return all entries when nothing matches.
        context_label: Label for logging (e.g., frame ID).

    Returns:
        FilteringResult with filtered entries and status flags.
    """
    all_entries = capture_result.entries
    rom_offsets_set = set(rom_offsets)  # Convert to set for O(1) lookup

    # Case 1: Filter by selected_entry_ids if provided
    if selected_entry_ids:
        selected_ids_set = set(selected_entry_ids)
        filtered = [e for e in all_entries if e.id in selected_ids_set]

        if filtered:
            return FilteringResult(
                entries=filtered,
                used_fallback=False,
                used_all_entries=False,
                is_stale=False,
            )

        # Entry IDs are stale
        if not allow_rom_offset_fallback:
            # Abort without fallback (for injection with allow_fallback=False)
            return FilteringResult(
                entries=[],
                used_fallback=False,
                used_all_entries=False,
                is_stale=True,
            )

        # Fall back to rom_offset filtering
        logger.warning(
            "Stored entry IDs %s not found in capture%s. Using rom_offset fallback.",
            selected_entry_ids,
            f" for {context_label}" if context_label else "",
        )

        filtered = [e for e in all_entries if e.rom_offset in rom_offsets_set]
        if filtered:
            return FilteringResult(
                entries=filtered,
                used_fallback=True,
                used_all_entries=False,
                is_stale=True,
            )
    else:
        # Case 2: No selected_entry_ids - filter by rom_offset
        filtered = [e for e in all_entries if e.rom_offset in rom_offsets_set]
        if filtered:
            return FilteringResult(
                entries=filtered,
                used_fallback=False,
                used_all_entries=False,
                is_stale=False,
            )

    # Nothing matched - check if we should fall back to all entries
    if allow_all_entries_fallback and all_entries:
        logger.info(
            "No entries match filters%s. Using all entries fallback.",
            f" for {context_label}" if context_label else "",
        )
        return FilteringResult(
            entries=list(all_entries),
            used_fallback=True,
            used_all_entries=True,
            is_stale=bool(selected_entry_ids),  # Only stale if we had IDs to match
        )

    # No entries found
    return FilteringResult(
        entries=[],
        used_fallback=bool(selected_entry_ids),  # True if we tried fallback
        used_all_entries=False,
        is_stale=bool(selected_entry_ids),
    )


def create_filtered_capture(
    original: CaptureResult,
    filtered_entries: list[OAMEntry],
) -> CaptureResult:
    """Create a new CaptureResult with only the filtered entries.

    This is a convenience function to create a filtered capture while preserving
    all other capture metadata (frame, obsel, palettes, timestamp).

    Args:
        original: The original CaptureResult.
        filtered_entries: The filtered list of entries.

    Returns:
        A new CaptureResult with only the filtered entries.
    """
    from core.mesen_integration.click_extractor import CaptureResult as CaptureResultClass

    return CaptureResultClass(
        frame=original.frame,
        visible_count=len(filtered_entries),
        obsel=original.obsel,
        entries=filtered_entries,
        palettes=original.palettes,
        timestamp=original.timestamp,
    )
