"""
Backwards-compatibility shim for registry imports.

DEPRECATED: Import from core.managers instead:
    from core.managers import (
        ManagerRegistry,
        initialize_managers,
        cleanup_managers,
        is_initialized,
        reset_for_tests,
        validate_manager_dependencies,
    )
"""
from __future__ import annotations

# Re-export everything from __init__.py for backwards compatibility
from . import (
    ManagerRegistry,
    _ensure_registry,
    cleanup_managers,
    initialize_managers,
    is_initialized,
    reset_for_tests,
    validate_manager_dependencies,
)


# For tests that import _cleanup_global_registry
def _cleanup_global_registry() -> None:
    """Backwards-compatibility alias for cleanup_managers()."""
    cleanup_managers()

__all__ = [
    "ManagerRegistry",
    "_cleanup_global_registry",
    "_ensure_registry",
    "cleanup_managers",
    "initialize_managers",
    "is_initialized",
    "reset_for_tests",
    "validate_manager_dependencies",
]
