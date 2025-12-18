"""
Dependency injection container for SpritePal.
Breaks circular dependencies and improves testability.
"""
from __future__ import annotations

import logging
from collections.abc import Callable
from threading import RLock
from typing import Any, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar('T')

class DIContainer:
    """
    Simple dependency injection container for managing application dependencies.

    Features:
    - Singleton instances
    - Factory functions
    - Thread-safe operations
    - Lazy initialization
    - Protocol/interface based registration
    """

    def __init__(self):
        """Initialize the DI container."""
        self._singletons: dict[type, Any] = {}
        self._factories: dict[type, Callable[[], Any]] = {}
        self._lock = RLock()
        logger.debug("DIContainer initialized")

    def register_singleton(self, interface: type[T], implementation: T) -> None:
        """
        Register a singleton instance.

        Args:
            interface: The interface/protocol type
            implementation: The implementation instance
        """
        with self._lock:
            self._singletons[interface] = implementation
            logger.debug(f"Registered singleton: {interface.__name__} -> {implementation.__class__.__name__}")

    def register_factory(self, interface: type[T], factory: Callable[[], T]) -> None:
        """
        Register a factory function for lazy initialization.

        Args:
            interface: The interface/protocol type
            factory: Function that creates an instance
        """
        with self._lock:
            self._factories[interface] = factory
            logger.debug(f"Registered factory for: {interface.__name__}")

    def get(self, interface: type[T]) -> T:
        """
        Get an instance of the requested type.

        Args:
            interface: The interface/protocol type to retrieve

        Returns:
            Instance of the requested type

        Raises:
            ValueError: If no registration exists for the interface
        """
        with self._lock:
            # Check singletons first
            if interface in self._singletons:
                return self._singletons[interface]

            # Check factories
            if interface in self._factories:
                # Create instance and store as singleton
                instance = self._factories[interface]()
                self._singletons[interface] = instance
                logger.debug(f"Created singleton from factory: {interface.__name__}")
                return instance

            raise ValueError(f"No registration for {interface.__name__}")

    def get_optional(self, interface: type[T]) -> T | None:
        """
        Get an instance if registered, otherwise return None.

        Args:
            interface: The interface/protocol type to retrieve

        Returns:
            Instance or None if not registered
        """
        try:
            return self.get(interface)
        except ValueError:
            return None

    def has(self, interface: type) -> bool:
        """
        Check if an interface is registered.

        Args:
            interface: The interface/protocol type to check

        Returns:
            True if registered, False otherwise
        """
        with self._lock:
            return interface in self._singletons or interface in self._factories

    def clear(self) -> None:
        """Clear all registrations (useful for testing)."""
        with self._lock:
            self._singletons.clear()
            self._factories.clear()
            logger.debug("DIContainer cleared")

    def unregister(self, interface: type) -> None:
        """
        Remove a registration.

        Args:
            interface: The interface/protocol type to remove
        """
        with self._lock:
            self._singletons.pop(interface, None)
            self._factories.pop(interface, None)
            logger.debug(f"Unregistered: {interface.__name__}")

# Global container instance
_container = DIContainer()

def get_container() -> DIContainer:
    """
    Get the global DI container instance.

    Returns:
        The global DIContainer instance
    """
    return _container

def register_singleton(interface: type[T], implementation: T) -> None:
    """
    Convenience function to register a singleton.

    Args:
        interface: The interface/protocol type
        implementation: The implementation instance
    """
    _container.register_singleton(interface, implementation)

def register_factory(interface: type[T], factory: Callable[[], T]) -> None:
    """
    Convenience function to register a factory.

    Args:
        interface: The interface/protocol type
        factory: Function that creates an instance
    """
    _container.register_factory(interface, factory)

def inject(interface: type[T]) -> T:
    """
    Convenience function to get an injected dependency.

    Args:
        interface: The interface/protocol type

    Returns:
        Instance of the requested type
    """
    return _container.get(interface)

def reset_container() -> None:
    """Reset the container (mainly for testing)."""
    _container.clear()

def configure_container(
    configuration_service: Any = None,
) -> None:
    """
    Configure the DI container with non-manager dependencies.

    This function sets up service bindings. Manager bindings are registered
    separately by ManagerRegistry.initialize_managers() after managers are created.

    INITIALIZATION ORDER (enforced by ManagerRegistry):
    1. configure_container() - registers services and factories
    2. ManagerRegistry creates managers
    3. register_managers() - registers manager protocols with actual instances

    Args:
        configuration_service: Optional pre-created ConfigurationService instance.
                              If not provided, one will be created automatically.
    """
    # Import protocols
    # Register ConfigurationService FIRST - it's needed by other managers
    from core.configuration_service import ConfigurationService
    from core.protocols.manager_protocols import (
        ConfigurationServiceProtocol,
        SettingsManagerProtocol,
    )
    from utils.settings_manager import SettingsManager

    if configuration_service is not None:
        register_singleton(ConfigurationServiceProtocol, configuration_service)
    else:
        # Create default ConfigurationService
        register_singleton(ConfigurationServiceProtocol, ConfigurationService())

    # NOTE: Manager protocols (ApplicationStateManagerProtocol, ExtractionManagerProtocol, etc.)
    # are registered by register_managers() AFTER managers are created.
    # This avoids circular dependency between DI container and ManagerRegistry.

    # Register SettingsManager (depends on ApplicationStateManagerProtocol, so use factory)
    register_factory(
        SettingsManagerProtocol,
        lambda: SettingsManager(
            app_name="SpritePal",
            session_manager=inject(
                __import__('core.protocols.manager_protocols', fromlist=['ApplicationStateManagerProtocol']).ApplicationStateManagerProtocol
            )
        )
    )

    # Import ROMCache and its Protocol
    from core.protocols.manager_protocols import ROMCacheProtocol
    from utils.rom_cache import ROMCache

    # Register ROMCache
    register_factory(
        ROMCacheProtocol,
        lambda: ROMCache(settings_manager=inject(SettingsManagerProtocol))
    )

    # Import ROMExtractor and its Protocol
    from core.protocols.manager_protocols import ROMExtractorProtocol
    from core.rom_extractor import ROMExtractor

    # Register ROMExtractor
    register_factory(
        ROMExtractorProtocol,
        lambda: ROMExtractor(rom_cache=inject(ROMCacheProtocol))
    )

    # NOTE: UI factory registrations (ManualOffsetDialogFactoryProtocol, DialogFactoryProtocol)
    # are handled by ui.register_ui_factories() called by application entry points
    # AFTER initialize_managers() completes. This keeps UI dependencies out of core/ layer.
    # See: launch_spritepal.py, tests/fixtures/core_fixtures.py

    logger.info("DI container configured (services registered, managers pending)")


def register_managers(
    core_operations_manager: Any,
) -> None:
    """
    Register CoreOperationsManager with the DI container.

    CoreOperationsManager is the consolidated manager that handles both
    extraction and injection operations. It is registered under both
    ExtractionManagerProtocol and InjectionManagerProtocol for backward
    compatibility with code that injects these protocols.

    NOTE: SessionManagerProtocol and ApplicationStateManagerProtocol are registered
    earlier in initialize_managers() because other services depend on them during
    CoreOperationsManager initialization.

    INITIALIZATION ORDER:
    1. configure_container() - registers services and factories
    2. ApplicationStateManager created, SessionManagerProtocol registered
    3. CoreOperationsManager created (depends on SessionManager via DI chain)
    4. register_managers() - registers CoreOperationsManager (THIS FUNCTION)

    Args:
        core_operations_manager: CoreOperationsManager instance that handles
            both extraction and injection operations
    """
    from core.protocols.manager_protocols import (
        ExtractionManagerProtocol,
        InjectionManagerProtocol,
    )

    # Register same instance under both protocols for backward compatibility
    register_singleton(ExtractionManagerProtocol, core_operations_manager)
    register_singleton(InjectionManagerProtocol, core_operations_manager)

    logger.info("CoreOperationsManager registered with DI container (extraction + injection)")
