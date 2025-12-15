"""
Dialog implementation selector.

This module provides the DialogBase class for creating dialogs.
Previously supported feature flag switching between implementations,
now always uses the standard DialogBase.

Usage:
    from ui.components.base.dialog_selector import DialogBase
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from utils.logging_config import get_logger

logger = get_logger(__name__)

# Import the standard implementation
DialogBase: type[Any]
InitializationOrderError: type[Any]

try:
    from .dialog_base import (
        DialogBase as LegacyDialogBase,
        InitializationOrderError as LegacyInitializationOrderError,
    )
    DialogBase = LegacyDialogBase  # type: ignore[assignment]
    InitializationOrderError = LegacyInitializationOrderError  # type: ignore[assignment]
    logger.debug("DialogBase loaded from dialog_base")
except ImportError as e:
    logger.warning(f"Qt dependencies not available: {e}")
    logger.info("Dialog implementations will not be available (testing mode)")

    # Create placeholder classes for testing
    class DialogBase:  # type: ignore[no-redef]
        """Placeholder DialogBase for testing environments without Qt."""
        pass

    class InitializationOrderError(Exception):  # type: ignore[no-redef]
        """Placeholder InitializationOrderError for testing."""
        pass

# Export the implementation
__all__ = [
    "DialogBase",
    "InitializationOrderError",
]
