"""
UI managers package

Contains manager classes that handle specific UI responsibilities,
following the Single Responsibility Principle.
"""
from __future__ import annotations

from .output_settings_manager import (
    OutputSettingsActionsProtocol,
    OutputSettingsManager,
)
from .preview_coordinator import PreviewCoordinator
from .session_coordinator import SessionCoordinator
from .status_bar_manager import StatusBarManager
from .tab_coordinator import TabCoordinator, TabCoordinatorActionsProtocol
from .toolbar_manager import ToolbarActionsProtocol, ToolbarManager

__all__ = [
    "OutputSettingsActionsProtocol",
    "OutputSettingsManager",
    "PreviewCoordinator",
    "SessionCoordinator",
    "StatusBarManager",
    "TabCoordinator",
    "TabCoordinatorActionsProtocol",
    "ToolbarActionsProtocol",
    "ToolbarManager",
]
