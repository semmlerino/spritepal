"""
Workflow state enum for extraction operations.

ExtractionState is used by ApplicationStateManager to track workflow progress.
"""

from __future__ import annotations

from enum import Enum, auto

__all__ = ["ExtractionState"]


class ExtractionState(Enum):
    """States for the extraction workflow.

    This enum is the canonical source for workflow states.
    """

    IDLE = auto()  # No operation in progress
    LOADING_ROM = auto()  # Loading ROM file
    SCANNING_SPRITES = auto()  # Scanning for sprite locations
    PREVIEWING_SPRITE = auto()  # Loading sprite preview
    SEARCHING_SPRITE = auto()  # Searching for next/prev sprite
    EXTRACTING = auto()  # Performing extraction
    ERROR = auto()  # Error state
