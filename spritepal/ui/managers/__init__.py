"""
UI managers package

Contains manager classes that handle specific UI responsibilities,
following the Single Responsibility Principle.
"""
from __future__ import annotations

from .output_settings_manager import OutputSettingsManager
from .status_bar_manager import StatusBarManager
from .toolbar_manager import ToolbarManager
from .ui_coordinator import UICoordinator

__all__ = [
    "OutputSettingsManager",
    "StatusBarManager",
    "ToolbarManager",
    "UICoordinator",
]
