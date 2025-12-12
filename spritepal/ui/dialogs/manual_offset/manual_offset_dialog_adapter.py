"""
Manual Offset Dialog Adapter for Backward Compatibility

This module provides a complete backward compatibility layer that switches between
the original UnifiedManualOffsetDialog and the new composed implementation based
on a feature flag.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any

try:
    # from PySide6.QtCore import Signal
    from PySide6.QtWidgets import QDialog, QWidget
    PYSIDE6_AVAILABLE = True
except ImportError:
    # Provide stubs for when PySide6 is not available
    Signal = object
    QMutex = object
    QWidget = object
    QDialog = object
    PYSIDE6_AVAILABLE = False

if TYPE_CHECKING:
    from core.managers.extraction_manager import ExtractionManager


try:
    from utils.logging_config import get_logger
    logger = get_logger(__name__)
except ImportError:
    # Fallback logger
    import logging
    logger = logging.getLogger(__name__)

def _get_implementation_class() -> type:
    """
    Get the appropriate implementation class based on feature flag.

    Returns:
        The dialog class to instantiate (either composed or legacy implementation)
    """
    flag_value = os.environ.get('SPRITEPAL_USE_COMPOSED_DIALOGS', '0').lower()
    use_composed = flag_value in ('1', 'true', 'yes', 'on')

    try:
        if use_composed:
            logger.debug("Using composed implementation for ManualOffsetDialog")
            from .core.manual_offset_dialog_core import ManualOffsetDialogCore
            return ManualOffsetDialogCore
        logger.debug("Using legacy implementation for ManualOffsetDialog")
        from ui.dialogs.manual_offset_unified_integrated import (
            UnifiedManualOffsetDialog,
        )
        return UnifiedManualOffsetDialog
    except ImportError as e:
        logger.warning(f"Could not import dialog implementation: {e}")
        # Fallback to a basic QDialog if imports fail
        if PYSIDE6_AVAILABLE:
            return QDialog
        # Return a dummy class when PySide6 is not available
        class DummyDialog:
            def __init__(self, *args: Any, **kwargs: Any) -> None:
                pass
        return DummyDialog

class ManualOffsetDialogAdapter:
    """
    Backward compatibility adapter for UnifiedManualOffsetDialog.

    This class provides the exact same API as the original UnifiedManualOffsetDialog
    while internally using either the composed implementation or the legacy implementation
    based on the SPRITEPAL_USE_COMPOSED_DIALOGS environment variable.

    The adapter uses __new__ to return the appropriate implementation instance,
    ensuring type safety and avoiding dynamic class creation issues.
    """

    # Signal definitions are on the actual implementation classes
    # Note: Signals are defined on the actual implementation classes.
    # Type checkers can find them through the __new__ return type.

    def __new__(cls, parent: QWidget | None = None, *args: Any, **kwargs: Any) -> Any:  # type: ignore[misc]
        """
        Create and return the appropriate dialog implementation.

        This factory method returns an instance of either the composed or legacy
        implementation based on the feature flag, maintaining full API compatibility.

        Args:
            parent: Parent widget (optional)
            *args: Additional positional arguments
            **kwargs: Additional keyword arguments

        Returns:
            Instance of the selected dialog implementation
        """
        implementation_class = _get_implementation_class()

        # Create and return instance of the selected implementation
        instance = implementation_class(parent, *args, **kwargs)

        # Log which implementation was created
        logger.debug(f"Created {implementation_class.__name__} instance")

        return instance

    # Type hints for the expected interface
    if TYPE_CHECKING:
        def set_rom_data(self, rom_path: str, rom_size: int, extraction_manager: ExtractionManager) -> None: ...
        def set_offset(self, offset: int) -> bool: ...
        def get_current_offset(self) -> int: ...
        def add_found_sprite(self, offset: int, quality: float = 1.0) -> None: ...
        def cleanup(self) -> None: ...
        def show(self) -> None: ...
        def hide(self) -> None: ...
        def close(self) -> bool: ...
