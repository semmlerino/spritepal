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
from pathlib import Path
from typing import TYPE_CHECKING

from core.exceptions import (
    ExtractionError,
    FileOperationError,
    InjectionError,
    ManagerError,
    NavigationError,
    PreviewError,
    SessionError,
    ValidationError,
)
from utils.logging_config import get_logger

from .application_state_manager import ApplicationStateManager
from .base_manager import BaseManager
from .core_operations_manager import CoreOperationsManager
from .error_helpers import (
    ErrorCallback,
    handle_categorized_error,
    handle_data_format_error,
    handle_file_io_error,
    handle_operation_error,
)
from .operation_decorator import OperationManager, with_operation_handling
from .sprite_preset_manager import SpritePresetManager
from .workflow_manager import ExtractionState
from .workflow_state_manager import WorkflowStateManager

if TYPE_CHECKING:
    from core.configuration_service import ConfigurationService

_logger = get_logger("managers")

# Module-level state (tracks if initialize_managers was called)
_initialized = False
_lock = threading.RLock()


def initialize_managers(
    app_name: str = "SpritePal",
    settings_path: Path | None = None,
    configuration_service: ConfigurationService | None = None,
) -> None:
    """
    Initialize all managers in dependency order.

    This is a wrapper around create_app_context() for backward compatibility.
    New code should use create_app_context() directly.

    Args:
        app_name: Application name for settings
        settings_path: Optional custom settings path (for testing)
        configuration_service: Optional pre-created ConfigurationService instance
    """
    global _initialized

    with _lock:
        if _initialized:
            _logger.debug("Managers already initialized, skipping")
            return

        _logger.info("Initializing managers via AppContext...")

        from core.app_context import create_app_context

        try:
            create_app_context(
                app_name=app_name,
                settings_path=settings_path,
                configuration_service=configuration_service,
            )
            _initialized = True
            _logger.info("All managers initialized successfully")

        except Exception as e:
            _logger.exception(f"Manager initialization failed: {e}")
            raise ManagerError(f"Failed to initialize managers: {e}") from e


def cleanup_managers() -> None:
    """Cleanup all managers in reverse initialization order."""
    global _initialized

    with _lock:
        if not _initialized:
            return

        _logger.info("Cleaning up managers...")

        from core.app_context import get_app_context_optional, reset_app_context

        ctx = get_app_context_optional()
        if ctx:
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
        _initialized = False
        _logger.info("All managers cleaned up")


def is_initialized() -> bool:
    """Check if managers are initialized."""
    return _initialized


def validate_manager_dependencies() -> bool:
    """
    Validate that all managers and their dependencies are properly initialized.

    Returns:
        True if all dependencies are satisfied, False otherwise
    """
    if not _initialized:
        _logger.warning("Managers not initialized, cannot validate dependencies")
        return False

    from core.app_context import get_app_context_optional

    ctx = get_app_context_optional()
    if ctx is None:
        _logger.warning("AppContext not available")
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
    global _initialized

    with _lock:
        from core.app_context import reset_app_context

        reset_app_context()
        _initialized = False


def is_clean() -> bool:
    """Check if manager state is clean (not initialized).

    Used by test infrastructure to verify test isolation.
    """
    return not _initialized


__all__ = [
    "ApplicationStateManager",
    "BaseManager",
    "CoreOperationsManager",
    # Error helpers
    "ErrorCallback",
    "handle_categorized_error",
    "handle_data_format_error",
    "handle_file_io_error",
    "handle_operation_error",
    # Operation decorator
    "OperationManager",
    "with_operation_handling",
    # Exceptions
    "ExtractionError",
    "ExtractionState",
    "FileOperationError",
    "InjectionError",
    "ManagerError",
    "NavigationError",
    "PreviewError",
    "SessionError",
    "SpritePresetManager",
    "ValidationError",
    "WorkflowStateManager",
    # Module functions
    "cleanup_managers",
    "initialize_managers",
    "is_clean",
    "is_initialized",
    "reset_for_tests",
    "validate_manager_dependencies",
]
