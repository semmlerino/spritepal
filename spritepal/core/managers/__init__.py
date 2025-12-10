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
# Backward compatibility: keep registry import but it will use DI container internally
from .registry import (
    are_managers_initialized,
    cleanup_managers,
    get_application_state_manager,
    get_container_stats,
    get_core_operations_manager,
    get_extraction_manager,
    get_injection_manager,
    get_navigation_manager,
    get_registry,
    get_session_manager,
    get_ui_coordinator_manager,
    initialize_managers,
    reset_managers,
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
    # Manager access functions (DI-based)
    "are_managers_initialized",
    "cleanup_managers",
    "get_application_state_manager",
    "get_container_stats",
    # New consolidated manager accessors
    "get_core_operations_manager",
    "get_extraction_manager",
    "get_injection_manager",
    "get_navigation_manager",
    # Backward compatibility
    "get_registry",
    "get_session_manager",
    "get_ui_coordinator_manager",
    "initialize_managers",
    "reset_managers",
    "validate_manager_dependencies",
]
