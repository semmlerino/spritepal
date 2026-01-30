"""Stale entry detection logic for frame mapping projects.

A game frame has "stale" entries when its `selected_entry_ids` no longer
match the IDs in the current capture file (e.g., after re-recording the capture).
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from utils.logging_config import get_logger

if TYPE_CHECKING:
    from core.frame_mapping_project import GameFrame
    from core.mesen_integration.click_extractor import CaptureResult

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class StaleCheckResult:
    """Result of checking a single game frame for stale entries.

    Attributes:
        frame_id: The game frame ID.
        is_stale: True if the frame has stale entries.
        reason: Optional reason for staleness (for debugging).
    """

    frame_id: str
    is_stale: bool
    reason: str | None = None


def check_frame_staleness(
    game_frame: GameFrame,
    get_capture: Callable[[Path], CaptureResult],
) -> StaleCheckResult | None:
    """Check if a single game frame has stale entry IDs.

    Args:
        game_frame: The game frame to check.
        get_capture: Function to retrieve a CaptureResult from a capture file path.

    Returns:
        StaleCheckResult if the frame was checked, None if skipped (no selected_entry_ids
        or no capture_path).
    """
    # Skip frames without selected_entry_ids (ROM-only workflow)
    if not game_frame.selected_entry_ids:
        return None

    # Skip frames without capture path
    if not game_frame.capture_path:
        return None

    # Check if capture file exists
    if not game_frame.capture_path.exists():
        logger.warning(
            "Capture file not found for frame '%s': %s",
            game_frame.id,
            game_frame.capture_path,
        )
        return StaleCheckResult(game_frame.id, is_stale=True, reason="file_not_found")

    # Load the capture file and check if entry IDs are still valid
    try:
        capture_result = get_capture(game_frame.capture_path)

        # Get the IDs of all entries in the current capture
        current_entry_ids = {entry.id for entry in capture_result.entries}

        # Check if all selected_entry_ids are present
        selected_ids_set = set(game_frame.selected_entry_ids)
        missing_ids = selected_ids_set - current_entry_ids
        is_stale = len(missing_ids) > 0

        if is_stale:
            logger.debug(
                "Game frame '%s' has stale entries: %s not in current capture IDs %s",
                game_frame.id,
                missing_ids,
                current_entry_ids,
            )
            return StaleCheckResult(game_frame.id, is_stale=True, reason="missing_ids")

        return StaleCheckResult(game_frame.id, is_stale=False)

    except Exception as e:
        logger.warning(
            "Failed to parse capture file for frame '%s': %s",
            game_frame.id,
            e,
        )
        return StaleCheckResult(game_frame.id, is_stale=True, reason="parse_error")


def detect_stale_frame_ids(
    game_frames: Iterable[GameFrame],
    get_capture: Callable[[Path], CaptureResult],
    *,
    stop_check: Callable[[], bool] | None = None,
) -> list[str]:
    """Detect which game frames have stale entry IDs.

    A frame is stale when its selected_entry_ids no longer match the IDs
    in the current capture file. This can happen after re-recording a capture.

    Args:
        game_frames: Game frames to check.
        get_capture: Function to retrieve a CaptureResult from a capture file path.
        stop_check: Optional callable that returns True to abort early (for cancellation).

    Returns:
        List of game frame IDs that have stale entries.
    """
    stale_ids: list[str] = []

    for game_frame in game_frames:
        if stop_check is not None and stop_check():
            break

        result = check_frame_staleness(game_frame, get_capture)
        if result is not None and result.is_stale:
            stale_ids.append(result.frame_id)

    return stale_ids
