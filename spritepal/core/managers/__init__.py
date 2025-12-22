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
"""
from __future__ import annotations

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

from .application_state_manager import ApplicationStateManager
from .base_manager import BaseManager

# Consolidated managers (NEW - these hold the actual logic)
from .core_operations_manager import CoreOperationsManager

# NOTE: ExtractionManager and InjectionManager have been removed.
# Use CoreOperationsManager via dependency injection:
#   from core.di_container import inject
#   from core.protocols.manager_protocols import ExtractionManagerProtocol, InjectionManagerProtocol
#   manager = inject(ExtractionManagerProtocol)  # Returns CoreOperationsManager
# Import DI-based manager functions
# Note: We import from registry now which supports both consolidated and original modes
# Convenience functions removed - use inject() or ManagerRegistry() directly
from .registry import (
    cleanup_managers,
    initialize_managers,
    validate_manager_dependencies,
)
from .sprite_preset_manager import SpritePresetManager
from .workflow_manager import ExtractionState

__all__ = [
    "ApplicationStateManager",
    "BaseManager",
    "CoreOperationsManager",
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
    "cleanup_managers",
    "initialize_managers",
    "validate_manager_dependencies",
]
