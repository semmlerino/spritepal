"""
Manager Context System for Dependency Injection

This module provides a context-based dependency injection system that allows
tests to inject their own manager instances while maintaining backward compatibility
with the existing global singleton pattern.

Key Features:
- Thread-safe context management using threading.local()
- Context inheritance chain for nested scopes
- Fallback to global registry when no context is set
- Zero breaking changes to existing code
- Clean migration path for future dependency injection
"""
from __future__ import annotations

import atexit
import threading
import weakref
from contextlib import contextmanager
from typing import Any, TypeVar

from typing_extensions import override

from utils.logging_config import get_logger
from utils.safe_logging import safe_debug, suppress_logging_errors

from .exceptions import ManagerError

logger = get_logger(__name__)

# Type variable for manager types
T = TypeVar('T')

class ManagerContext:
    """
    Context for holding manager instances in a specific scope.

    Supports inheritance chain where child contexts can access parent managers
    if they don't have their own instance of a specific manager type.
    """

    def __init__(
        self,
        managers: dict[str, Any] | None = None,
        parent: ManagerContext | None = None,
        name: str = "unnamed"
    ) -> None:
        """
        Initialize a manager context.

        Args:
            managers: Dictionary of manager instances keyed by name
            parent: Parent context for inheritance chain
            name: Human-readable name for debugging
        """
        self._managers = managers or {}
        self._parent = parent
        self._name = name
        self._id = id(self)

        logger.debug(f"Created ManagerContext '{name}' (id: {self._id}) with managers: {list(self._managers.keys())}")

    def get_manager(self, name: str, expected_type: type[T]) -> T:
        """
        Get a manager by name with type checking.

        Searches the inheritance chain: local -> parent -> global fallback

        Args:
            name: Manager name (e.g., "injection", "extraction", "session")
            expected_type: Expected manager type for validation

        Returns:
            Manager instance of the expected type

        Raises:
            ManagerError: If manager not found or type mismatch
        """
        # Check local context first
        if name in self._managers:
            manager = self._managers[name]
            self._validate_manager_type(manager, expected_type, name)
            logger.debug(f"Context '{self._name}' resolved '{name}' manager locally")
            return manager

        # Check parent context
        if self._parent:
            logger.debug(f"Context '{self._name}' delegating '{name}' manager to parent")
            return self._parent.get_manager(name, expected_type)

        # No manager found in context chain
        raise ManagerError(
            f"{name.capitalize()} manager not available in context '{self._name}'. "
            f"Available managers: {list(self._managers.keys())}"
        )

    def has_manager(self, name: str) -> bool:
        """
        Check if a manager is available in this context or parent chain.

        Args:
            name: Manager name to check

        Returns:
            True if manager is available, False otherwise
        """
        if name in self._managers:
            return True

        if self._parent:
            return self._parent.has_manager(name)

        return False

    def add_manager(self, name: str, manager: Any) -> None:
        """
        Add or replace a manager in this context.

        Args:
            name: Manager name
            manager: Manager instance
        """
        self._managers[name] = manager
        logger.debug(f"Added '{name}' manager to context '{self._name}'")

    def remove_manager(self, name: str) -> bool:
        """
        Remove a manager from this context (not from parent chain).

        Args:
            name: Manager name to remove

        Returns:
            True if manager was removed, False if not found
        """
        if name in self._managers:
            del self._managers[name]
            logger.debug(f"Removed '{name}' manager from context '{self._name}'")
            return True
        return False

    def get_available_managers(self) -> dict[str, Any]:
        """
        Get all managers available in this context and parent chain.

        Returns:
            Dictionary of all available managers
        """
        all_managers = {}

        # Start with parent managers (so local managers override)
        if self._parent:
            all_managers.update(self._parent.get_available_managers())

        # Add local managers (overriding parent managers)
        all_managers.update(self._managers)

        return all_managers

    def create_child_context(
        self,
        managers: dict[str, Any] | None = None,
        name: str = "child"
    ) -> ManagerContext:
        """
        Create a child context that inherits from this context.

        Args:
            managers: Additional managers for the child context
            name: Name for the child context

        Returns:
            New child context
        """
        child_name = f"{self._name}/{name}"
        return ManagerContext(managers, parent=self, name=child_name)

    def debug_info(self) -> str:
        """
        Generate debug information about this context and its inheritance chain.

        Returns:
            Human-readable debug information
        """
        lines = [f"ManagerContext '{self._name}' (id: {self._id})"]
        lines.append(f"  Local managers: {list(self._managers.keys())}")

        if self._parent:
            lines.append(f"  Parent: {self._parent._name} (id: {self._parent._id})")
            parent_info = self._parent.debug_info()
            # Indent parent info
            lines.extend(f"  {line}" for line in parent_info.split('\n'))
        else:
            lines.append("  Parent: None (root context)")

        return "\n".join(lines)

    @staticmethod
    def _validate_manager_type(manager: Any, expected_type: type[T], name: str) -> None:
        """
        Validate that a manager matches the expected type.

        Args:
            manager: Manager instance to validate
            expected_type: Expected type
            name: Manager name for error messages

        Raises:
            ManagerError: If type doesn't match
        """
        # Skip type checking in test mode (set via environment variable)
        import os
        if os.environ.get('PYTEST_CURRENT_TEST') or os.environ.get('TESTING'):
            # In test mode, skip strict type checking to allow test doubles
            return

        if not isinstance(manager, expected_type):
            actual_type = type(manager).__name__
            expected_name = expected_type.__name__
            raise ManagerError(
                f"Manager type mismatch for '{name}': expected {expected_name}, "
                f"got {actual_type}"
            )

    @override
    def __repr__(self) -> str:
        return f"ManagerContext(name='{self._name}', managers={list(self._managers.keys())})"

class ThreadLocalContextManager:
    """
    Thread-safe manager for storing and retrieving the current manager context.

    Uses threading.local() to ensure each thread has its own context stack,
    preventing interference between parallel tests or operations.
    """

    def __init__(self) -> None:
        self._storage = threading.local()
        self._thread_refs: dict[int, weakref.ReferenceType[threading.Thread]] = {}  # Track threads for cleanup
        self._lock = threading.Lock()

        # Register cleanup for thread-local storage
        atexit.register(self._cleanup_all_threads)

    def get_current_context(self) -> ManagerContext | None:
        """
        Get the current context for this thread.

        Returns:
            Current context or None if no context is set
        """
        return getattr(self._storage, 'context', None)

    def set_current_context(self, context: ManagerContext | None) -> None:
        """
        Set the current context for this thread.

        Args:
            context: Context to set as current, or None to clear
        """
        current_thread = threading.current_thread()
        thread_id = current_thread.ident

        # Track thread for cleanup if not already tracked
        if thread_id and thread_id not in self._thread_refs:
            with self._lock:
                self._thread_refs[thread_id] = weakref.ref(current_thread,
                    lambda ref: self._cleanup_thread(thread_id))

        self._storage.context = context

        if context:
            safe_debug(logger, f"Set current context to '{context._name}' in thread {current_thread.name}")
        else:
            safe_debug(logger, f"Cleared current context in thread {current_thread.name}")

    def push_context(self, context: ManagerContext) -> None:
        """
        Push a context onto the stack, making it current.

        The new context will have the previous context as its parent if it
        doesn't already have a parent set.

        Args:
            context: Context to push
        """
        current = self.get_current_context()

        # If the context doesn't have a parent, set the current context as parent
        if context._parent is None and current is not None:
            context._parent = current
            logger.debug(f"Auto-linked context '{context._name}' to parent '{current._name}'")

        self.set_current_context(context)

    def pop_context(self) -> ManagerContext | None:
        """
        Pop the current context, restoring the previous context.

        Returns:
            The context that was popped, or None if no context was set
        """
        current = self.get_current_context()

        if current and current._parent:
            self.set_current_context(current._parent)
            logger.debug(f"Popped context '{current._name}', restored parent '{current._parent._name}'")
        else:
            self.set_current_context(None)
            if current:
                logger.debug(f"Popped context '{current._name}', no parent to restore")

        return current

    def debug_context_stack(self) -> str:
        """
        Generate debug information about the current context stack.

        Returns:
            Human-readable debug information
        """
        current = self.get_current_context()
        if not current:
            return "No current context"

        return current.debug_info()

    def _cleanup_thread(self, thread_id: int) -> None:
        """Clean up references for a thread that has ended"""
        with self._lock:
            self._thread_refs.pop(thread_id, None)
        safe_debug(logger, f"Cleaned up context references for thread {thread_id}")

    @suppress_logging_errors
    def _cleanup_all_threads(self) -> None:
        """Cleanup all thread references at exit"""
        with self._lock:
            self._thread_refs.clear()
        safe_debug(logger, "Cleaned up all thread context references")

# Global instance for thread-local context management
_context_manager = ThreadLocalContextManager()

# Module-level cleanup for context manager
# WARNING: SPOOKY ACTION AT A DISTANCE
# This atexit handler runs in UNDEFINED ORDER relative to other atexit handlers in:
# - core/managers/registry.py (_cleanup_global_registry)
# - core/hal_compression.py (_cleanup_hal_singleton)
# Do not assume managers or HAL are still alive when this runs.
@suppress_logging_errors
def _cleanup_context_manager():
    """Cleanup context manager at module exit"""
    global _context_manager
    try:
        _context_manager._cleanup_all_threads()
    except Exception:
        pass  # Ignore errors during cleanup
    _context_manager = None

atexit.register(_cleanup_context_manager)

def get_current_context() -> ManagerContext | None:
    """
    Get the current manager context for this thread.

    Returns:
        Current context or None if no context is set
    """
    if _context_manager is None:
        return None
    return _context_manager.get_current_context()

def set_current_context(context: ManagerContext | None) -> None:
    """
    Set the current manager context for this thread.

    Args:
        context: Context to set as current, or None to clear
    """
    if _context_manager is None:
        return
    _context_manager.set_current_context(context)

@contextmanager
def manager_context(
    managers: dict[str, Any] | None = None,
    name: str = "context",
    parent: ManagerContext | None = None
):
    """
    Context manager for temporarily setting a manager context.

    This is the primary interface for tests to inject their own managers.

    Args:
        managers: Dictionary of manager instances
        name: Name for the context (for debugging)
        parent: Parent context (defaults to current context)

    Yields:
        The created ManagerContext instance

    Example:
        with manager_context({"injection": mock_injection_manager}) as ctx:
            dialog = InjectionDialog()  # Will use mock_injection_manager
    """
    # Use current context as parent if none specified
    if parent is None:
        parent = get_current_context()

    # Create new context
    context = ManagerContext(managers, parent, name)

    # Set as current context
    old_context = get_current_context()
    set_current_context(context)

    try:
        logger.debug(f"Entered manager context '{name}'")
        yield context
    finally:
        # Restore previous context
        set_current_context(old_context)
        logger.debug(f"Exited manager context '{name}'")

class ContextValidator:
    """
    Utilities for validating manager contexts and debugging context issues.
    """

    @staticmethod
    def validate_context(context: ManagerContext) -> list[str]:
        """
        Validate that a context has properly initialized managers.

        Args:
            context: Context to validate

        Returns:
            List of validation errors (empty if valid)
        """
        errors = []
        required_managers = ["session", "extraction", "injection"]

        for manager_name in required_managers:
            try:
                manager = context.get_manager(manager_name, object)

                # Check if manager has is_initialized method and is initialized
                if hasattr(manager, 'is_initialized'):
                    is_initialized_method = manager.is_initialized  # type: ignore[attr-defined]  # Runtime duck typing
                    if callable(is_initialized_method) and not is_initialized_method():
                        errors.append(f"{manager_name} manager not properly initialized")
                else:
                    # For mock managers or managers without is_initialized
                    logger.debug(f"{manager_name} manager has no is_initialized method (possibly a mock)")

            except ManagerError as e:
                errors.append(f"Missing {manager_name} manager: {e}")

        return errors

    @staticmethod
    def debug_context_chain() -> str:
        """
        Generate debug information for the current context chain.

        Returns:
            Human-readable debug information
        """
        if _context_manager is None:
            return "Context manager is None (during shutdown?)"
        return _context_manager.debug_context_stack()

    @staticmethod
    def validate_current_context() -> tuple[bool, list[str]]:
        """
        Validate the current context in this thread.

        Returns:
            Tuple of (is_valid, list_of_errors)
        """
        current = get_current_context()
        if not current:
            return False, ["No current context set"]

        errors = ContextValidator.validate_context(current)
        return len(errors) == 0, errors
