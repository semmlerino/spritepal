"""Base UI components for SpritePal"""
from __future__ import annotations

# Import DialogBase through the feature flag selector
# This allows switching between legacy and composed implementations
# via the SPRITEPAL_USE_COMPOSED_DIALOGS environment variable
from .dialog_selector import (
    DialogBase,
    InitializationOrderError,
    get_dialog_implementation,
    is_composed_dialogs_enabled,
    set_dialog_implementation,
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
    "get_dialog_implementation",
    "is_composed_dialogs_enabled",
    "set_dialog_implementation",
]
