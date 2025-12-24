"""
Manager classes for SpritePal business logic.

This package provides the consolidated manager architecture. The recommended
way to access managers is via dependency injection::

    from core.di_container import inject
    from core.managers import ApplicationStateManager, CoreOperationsManager

    state_mgr = inject(ApplicationStateManager)
    ops_mgr = inject(CoreOperationsManager)

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
from .workflow_state_manager import WorkflowStateManager

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
    "WorkflowStateManager",
    "cleanup_managers",
    "initialize_managers",
    "validate_manager_dependencies",
]
