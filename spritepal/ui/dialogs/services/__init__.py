"""
Services for Dialog State Management

This package contains dialog state management services:
- ViewStateManager: Window state and position management (working well)
- BookmarkManager: Bookmark storage and menu management
- CacheStatusController: Cache statistics tracking and UI management

Note: The over-engineered MVP services (ManualOffsetController, ROMDataSession,
OffsetExplorationService) have been removed and consolidated into the simplified
ManualOffsetDialogSimplified for better stability and maintainability.
"""

from __future__ import annotations

from .bookmark_manager import BookmarkManager
from .cache_status_controller import CacheStatusController
from .view_state_manager import ViewStateManager

__all__ = [
    "BookmarkManager",
    "CacheStatusController",
    "ViewStateManager",
]
