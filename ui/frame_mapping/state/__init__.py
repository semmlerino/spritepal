"""State management for frame mapping.

This module contains managers for stateful business logic that was
previously embedded in view classes.
"""

from ui.frame_mapping.state.selection_state_manager import SelectionStateManager

__all__ = ["SelectionStateManager"]
