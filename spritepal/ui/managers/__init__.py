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
from .status_bar_manager import StatusBarManager
from .toolbar_manager import ToolbarActionsProtocol, ToolbarManager
from .ui_coordinator import TabCoordinatorActionsProtocol, UICoordinator

__all__ = [
    "OutputSettingsActionsProtocol",
    "OutputSettingsManager",
    "StatusBarManager",
    "TabCoordinatorActionsProtocol",
    "ToolbarActionsProtocol",
    "ToolbarManager",
    "UICoordinator",
]
