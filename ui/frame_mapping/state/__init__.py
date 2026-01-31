"""State management for frame mapping.

This module contains managers for stateful business logic that was
previously embedded in view classes.
"""

from ui.frame_mapping.state.batch_selection_manager import BatchSelectionManager

__all__ = ["BatchSelectionManager"]
