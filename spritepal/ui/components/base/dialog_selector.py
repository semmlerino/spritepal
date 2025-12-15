"""
Dialog implementation selector.

This module provides the DialogBase class for creating dialogs.
Previously supported feature flag switching between implementations,
now always uses the standard DialogBase.

Usage:
    from ui.components.base.dialog_selector import DialogBase
"""
from __future__ import annotations

from .dialog_base import DialogBase, InitializationOrderError

# Export the implementation
__all__ = [
    "DialogBase",
    "InitializationOrderError",
]
