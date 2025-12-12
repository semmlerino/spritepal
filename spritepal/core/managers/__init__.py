"""
Manager classes for SpritePal business logic
"""
from __future__ import annotations

from .application_state_manager import ApplicationStateManager
from .base_manager import BaseManager

# Import new consolidated managers
from .core_operations_manager import CoreOperationsManager
from .exceptions import (
    ExtractionError,
    FileOperationError,
    InjectionError,
    ManagerError,
    NavigationError,
    PreviewError,
    SessionError,
    ValidationError,
)
from .extraction_manager import ExtractionManager
from .injection_manager import InjectionManager

# Import DI-based manager functions
# Note: We import from registry now which supports both consolidated and original modes
# Convenience functions removed - use inject() or ManagerRegistry() directly
from .registry import (
    cleanup_managers,
    initialize_managers,
    validate_manager_dependencies,
)
from .session_manager import SessionManager
from .ui_coordinator_manager import UICoordinatorManager

__all__ = [
    "ApplicationStateManager",
    # Base classes
    "BaseManager",
    # Consolidated Managers
    "CoreOperationsManager",
    # Exceptions
    "ExtractionError",
    # Original Managers
    "ExtractionManager",
    "FileOperationError",
    "InjectionError",
    "InjectionManager",
    "ManagerError",
    "NavigationError",
    "PreviewError",
    "SessionError",
    "SessionManager",
    "UICoordinatorManager",
    "ValidationError",
    # Manager lifecycle functions (use inject() for manager access)
    "cleanup_managers",
    "initialize_managers",
    "validate_manager_dependencies",
]
