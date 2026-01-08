"""
UI managers package

Contains manager classes that handle specific UI responsibilities,
following the Single Responsibility Principle.
"""

from __future__ import annotations

from .keyboard_shortcut_manager import KeyboardShortcutManager
from .output_settings_manager import OutputSettingsManager
from .status_bar_manager import StatusBarManager
from .toolbar_manager import ToolbarManager

__all__ = [
    "KeyboardShortcutManager",
    "OutputSettingsManager",
    "StatusBarManager",
    "ToolbarManager",
]
