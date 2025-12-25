"""Minimal DI container - thread-safe singletons and lazy factories.

DEPRECATED: Use get_app_context() from core.app_context instead.

The DI container is being phased out in favor of explicit AppContext wiring.
New code should use:
    from core.app_context import get_app_context
    context = get_app_context()
    state_manager = context.application_state_manager

This module remains for backward compatibility during the transition.
"""
from __future__ import annotations

import logging
import warnings
from collections.abc import Callable
from threading import RLock
from typing import TypeVar, cast

logger = logging.getLogger(__name__)

_deprecation_warned = False
T = TypeVar("T")


class DIContainer:
    """Thread-safe container for singletons and lazy factories."""

    def __init__(self) -> None:
        self._instances: dict[type, object] = {}
        self._factories: dict[type, Callable[[], object]] = {}
        self._lock = RLock()

    def register_singleton(self, key: type[T], instance: T) -> None:
        """Register a singleton instance."""
        with self._lock:
            self._instances[key] = instance
            logger.debug("Registered singleton: %s", key.__name__)

    def register_factory(self, key: type[T], factory: Callable[[], T]) -> None:
        """Register a factory for lazy initialization."""
        with self._lock:
            self._factories[key] = factory
            logger.debug("Registered factory: %s", key.__name__)

    def get(self, key: type[T]) -> T:
        """Get an instance, creating from factory if needed."""
        with self._lock:
            if key in self._instances:
                return cast(T, self._instances[key])
            if key in self._factories:
                instance = self._factories[key]()
                self._instances[key] = instance
                logger.debug("Created from factory: %s", key.__name__)
                return cast(T, instance)
            raise ValueError(f"No registration for {key.__name__}")

    def get_optional(self, key: type[T]) -> T | None:
        """Get an instance if registered, otherwise None."""
        try:
            return self.get(key)
        except ValueError:
            return None

    def has(self, key: type) -> bool:
        """Check if a type is registered."""
        with self._lock:
            return key in self._instances or key in self._factories

    def clear(self) -> None:
        """Clear all registrations."""
        with self._lock:
            self._instances.clear()
            self._factories.clear()
            logger.debug("Container cleared")

    def unregister(self, key: type) -> None:
        """Remove a registration."""
        with self._lock:
            self._instances.pop(key, None)
            self._factories.pop(key, None)
            logger.debug("Unregistered: %s", key.__name__)


# Global container instance
_container = DIContainer()


def get_container() -> DIContainer:
    """Get the global DI container."""
    return _container


def inject(interface: type[T]) -> T:
    """Get an injected dependency.

    DEPRECATED: Use get_app_context() instead.

    Example migration:
        # Old pattern
        from core.di_container import inject
        manager = inject(ApplicationStateManager)

        # New pattern
        from core.app_context import get_app_context
        manager = get_app_context().application_state_manager

    During the transition, this function checks AppContext first
    and falls back to the container if AppContext is not initialized.
    """
    global _deprecation_warned
    if not _deprecation_warned:
        warnings.warn(
            "inject() is deprecated. Use get_app_context() from core.app_context instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        _deprecation_warned = True  # Only warn once per session

    # Try AppContext first (new pattern)
    from core.app_context import get_app_context_optional

    ctx = get_app_context_optional()
    if ctx is not None:
        # Import types locally to avoid circular imports
        from core.configuration_service import ConfigurationService
        from core.managers.application_state_manager import ApplicationStateManager
        from core.managers.core_operations_manager import CoreOperationsManager
        from core.managers.sprite_preset_manager import SpritePresetManager
        from core.rom_extractor import ROMExtractor
        from core.services.rom_cache import ROMCache

        # Map types to context attributes
        if interface is ApplicationStateManager:
            return cast(T, ctx.application_state_manager)
        if interface is CoreOperationsManager:
            return cast(T, ctx.core_operations_manager)
        if interface is SpritePresetManager:
            return cast(T, ctx.sprite_preset_manager)
        if interface is ConfigurationService:
            return cast(T, ctx.configuration_service)
        if interface is ROMCache:
            return cast(T, ctx.rom_cache)
        if interface is ROMExtractor:
            return cast(T, ctx.rom_extractor)

    # Fall back to container (legacy pattern)
    return _container.get(interface)


def get_optional(interface: type[T]) -> T | None:
    """Get an injected dependency if registered, otherwise None."""
    return _container.get_optional(interface)


def register_singleton(interface: type[T], implementation: T) -> None:
    """Register a singleton instance."""
    _container.register_singleton(interface, implementation)


def register_factory(interface: type[T], factory: Callable[[], T]) -> None:
    """Register a factory for lazy initialization."""
    _container.register_factory(interface, factory)


def reset_container() -> None:
    """Reset the container (for testing)."""
    _container.clear()
