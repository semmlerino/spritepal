"""Centralized status colors for frame mapping UI components.

This module provides a single source of truth for mapping status colors,
ensuring consistency across the AI Frames pane, Mapping Panel, and other
UI components that display mapping status.
"""

from __future__ import annotations

from PySide6.QtGui import QColor

from core.frame_mapping_project import MappingStatus

# Status colors for frame mapping status indicators
# Used by AIFramesPane, MappingPanel, and other UI components
MAPPING_STATUS_COLORS: dict[MappingStatus, QColor] = {
    MappingStatus.UNMAPPED: QColor(180, 180, 180),  # Light gray
    MappingStatus.MAPPED: QColor(76, 175, 80),  # Green
    MappingStatus.EDITED: QColor(33, 150, 243),  # Blue
    MappingStatus.INJECTED: QColor(156, 39, 176),  # Purple
}


def get_status_color(status: str | MappingStatus) -> QColor:
    """Get the color for a mapping status.

    Args:
        status: Status string or MappingStatus enum value.

    Returns:
        QColor for the status. Falls back to UNMAPPED color for unknown values.
    """
    # Convert string to enum if not already a MappingStatus
    if not isinstance(status, MappingStatus):
        try:
            status = MappingStatus(status)
        except ValueError:
            return MAPPING_STATUS_COLORS[MappingStatus.UNMAPPED]
    return MAPPING_STATUS_COLORS.get(status, MAPPING_STATUS_COLORS[MappingStatus.UNMAPPED])
