"""
Manager classes for SpritePal business logic.

This package provides the consolidated manager architecture. The recommended
way to access managers is via AppContext::

    from core.app_context import get_app_context

    ctx = get_app_context()
    state_mgr = ctx.application_state_manager
    ops_mgr = ctx.core_operations_manager

Architecture:
    - ApplicationStateManager: Consolidated manager for session, settings, state
    - CoreOperationsManager: Consolidated manager for extraction, injection, palette
"""

from __future__ import annotations

import threading

from core.exceptions import (
    ExtractionError,
    InjectionError,
    ManagerError,
    SessionError,
    ValidationError,
)
from utils.logging_config import get_logger

from .application_state_manager import ApplicationStateManager
from .base_manager import BaseManager
from .core_operations_manager import CoreOperationsManager
from .sprite_preset_manager import SpritePresetManager
from .workflow_state_manager import ExtractionState, WorkflowStateManager

_logger = get_logger("managers")

_lock = threading.RLock()


def cleanup_managers() -> None:
    """Cleanup all managers in reverse initialization order."""
    with _lock:
        from core.app_context import get_app_context_optional, reset_app_context

        ctx = get_app_context_optional()
        if ctx is None:
            return

        _logger.info("Cleaning up managers...")

        # Cleanup in reverse order
        for mgr in [
            ctx.core_operations_manager,
            ctx.sprite_preset_manager,
            ctx.application_state_manager,
        ]:
            try:
                mgr.cleanup()
                _logger.debug("Cleaned up %s", type(mgr).__name__)
            except Exception:
                _logger.warning("Error cleaning up %s", type(mgr).__name__, exc_info=True)

        reset_app_context()
        _logger.info("All managers cleaned up")


def is_initialized() -> bool:
    """Check if managers are initialized by checking app context availability."""
    from core.app_context import get_app_context_optional

    return get_app_context_optional() is not None


def validate_manager_dependencies() -> bool:
    """
    Validate that all managers and their dependencies are properly initialized.

    Returns:
        True if all dependencies are satisfied, False otherwise
    """
    from core.app_context import get_app_context_optional

    ctx = get_app_context_optional()
    if ctx is None:
        _logger.warning("Managers not initialized, cannot validate dependencies")
        return False

    try:
        for mgr in [
            ctx.application_state_manager,
            ctx.sprite_preset_manager,
            ctx.core_operations_manager,
        ]:
            if not mgr.is_initialized():
                raise ManagerError(f"{type(mgr).__name__} not properly initialized")

        _logger.debug("All manager dependencies validated successfully")
        return True

    except Exception as e:
        _logger.exception(f"Manager dependency validation failed: {e}")
        return False


def reset_for_tests() -> None:
    """Reset manager state for test isolation.

    WARNING: This method is for test infrastructure only.
    Do not use in production code.
    """
    with _lock:
        from core.app_context import reset_app_context

        reset_app_context()


def is_clean() -> bool:
    """Check if manager state is clean (not initialized).

    Used by test infrastructure to verify test isolation.
    """
    return not is_initialized()


__all__ = [
    "ApplicationStateManager",
    "BaseManager",
    "CoreOperationsManager",
    "ExtractionError",
    "ExtractionState",
    "InjectionError",
    "ManagerError",
    "SessionError",
    "SpritePresetManager",
    "ValidationError",
    "WorkflowStateManager",
    "cleanup_managers",
    "is_clean",
    "is_initialized",
    "reset_for_tests",
    "validate_manager_dependencies",
]
