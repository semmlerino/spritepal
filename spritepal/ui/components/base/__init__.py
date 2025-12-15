"""Base UI components for SpritePal"""
from __future__ import annotations

from .dialog_selector import (
    DialogBase,
    InitializationOrderError,
)
from .help_icon_button import HelpIconButton, HelpLabel, InfoBanner

# Maintain backward compatibility alias
BaseDialog = DialogBase

__all__ = [
    "BaseDialog",  # Backward compatibility alias
    "DialogBase",
    "HelpIconButton",
    "HelpLabel",
    "InfoBanner",
    "InitializationOrderError",
]
