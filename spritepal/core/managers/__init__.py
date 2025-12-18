"""
Manager classes for SpritePal business logic.

This package provides the consolidated manager architecture with backward-compatible
adapters. The recommended way to access managers is via dependency injection::

    from core.di_container import inject
    from core.protocols.manager_protocols import (
        ApplicationStateManagerProtocol,
        ExtractionManagerProtocol,
        InjectionManagerProtocol,
    )

    state_mgr = inject(ApplicationStateManagerProtocol)
    extraction_mgr = inject(ExtractionManagerProtocol)
    injection_mgr = inject(InjectionManagerProtocol)

Architecture:
    - ApplicationStateManager: Consolidated manager for session, settings, state
    - CoreOperationsManager: Consolidated manager for extraction, injection, palette
    - SessionManager, ExtractionManager, InjectionManager: Legacy base classes for
      adapters. These provide interface compatibility but all logic lives in the
      consolidated managers.
"""
from __future__ import annotations

from .application_state_manager import ApplicationStateManager
from .base_manager import BaseManager

# Consolidated managers (NEW - these hold the actual logic)
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

# DEPRECATED: Legacy manager classes below are base classes for adapters only.
# Do not instantiate directly. Use inject(XxxManagerProtocol) instead.
# See module docstring above for the recommended access pattern.
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

# DEPRECATED: See note above about legacy manager classes.
from .session_manager import SessionManager

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
    "ValidationError",
    # Manager lifecycle functions (use inject() for manager access)
    "cleanup_managers",
    "initialize_managers",
    "validate_manager_dependencies",
]
