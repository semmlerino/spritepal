"""
Dependency injection container for SpritePal.
Breaks circular dependencies and improves testability.
"""
from __future__ import annotations

import logging
from collections.abc import Callable
from threading import RLock
from typing import Any, Protocol, TypeVar

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
    Configure the DI container with application dependencies.

    This function sets up all the necessary bindings for the application.
    It should be called during application initialization.

    The container uses the consolidated manager architecture where:
    - ApplicationStateManager handles session, settings, state, and history
    - CoreOperationsManager handles extraction and injection operations
    - Adapters provide backward-compatible interfaces (SessionManager, etc.)

    Args:
        configuration_service: Optional pre-created ConfigurationService instance.
                              If not provided, one will be created automatically.
    """
    # Import protocols
    # Register ConfigurationService FIRST - it's needed by other managers
    from core.configuration_service import ConfigurationService
    from core.protocols.manager_protocols import (
        ApplicationStateManagerProtocol,
        ConfigurationServiceProtocol,
        ExtractionManagerProtocol,
        InjectionManagerProtocol,
        SessionManagerProtocol,
        SettingsManagerProtocol,
    )
    from utils.settings_manager import SettingsManager

    if configuration_service is not None:
        register_singleton(ConfigurationServiceProtocol, configuration_service)
    else:
        # Create default ConfigurationService
        register_singleton(ConfigurationServiceProtocol, ConfigurationService())

    # Register consolidated managers with adapters
    # ApplicationStateManager handles session, settings, state, and history
    # CoreOperationsManager handles extraction and injection operations
    register_factory(
        ApplicationStateManagerProtocol,
        lambda: _get_application_state_manager()
    )

    register_factory(
        SessionManagerProtocol,
        lambda: _get_consolidated_session_adapter()
    )

    register_factory(
        ExtractionManagerProtocol,
        lambda: _get_consolidated_extraction_adapter()
    )

    register_factory(
        InjectionManagerProtocol,
        lambda: _get_consolidated_injection_adapter()
    )

    # Register SettingsManager
    register_factory(
        SettingsManagerProtocol,
        lambda: SettingsManager(app_name="SpritePal", session_manager=inject(SessionManagerProtocol))
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

    # Import and register ROMService and VRAMService
    from core.protocols.manager_protocols import (
        ROMServiceProtocol,
        VRAMServiceProtocol,
    )
    from core.services import ROMService, VRAMService

    # Register ROMService (creates its own ROMExtractor if needed)
    register_factory(
        ROMServiceProtocol,
        lambda: ROMService()
    )

    # Register VRAMService
    register_factory(
        VRAMServiceProtocol,
        lambda: VRAMService()
    )

    # Register ManualOffsetDialogFactory via protocol to avoid layer violation
    # The factory creates UI objects so it lives in ui/, but we register by protocol
    from core.protocols.dialog_protocols import ManualOffsetDialogFactoryProtocol

    def _create_manual_offset_dialog_factory():
        from ui.dialogs.dialog_factories import ManualOffsetDialogFactory
        return ManualOffsetDialogFactory(
            rom_cache=inject(ROMCacheProtocol),
            settings_manager=inject(SettingsManagerProtocol),
            extraction_manager=inject(ExtractionManagerProtocol),
            rom_extractor=inject(ROMExtractorProtocol)
        )

    register_factory(ManualOffsetDialogFactoryProtocol, _create_manual_offset_dialog_factory)

    # Register DialogFactory for controller dialog creation with lazy import
    from core.protocols.dialog_protocols import DialogFactoryProtocol

    def _create_controller_dialog_factory():
        from ui.dialogs.controller_dialog_factory import ControllerDialogFactory
        return ControllerDialogFactory()

    register_factory(DialogFactoryProtocol, _create_controller_dialog_factory)

    logger.info("DI container configured with consolidated manager architecture")

# Helper functions for lazy manager creation
def _get_application_state_manager():
    """Get ApplicationStateManager from registry."""
    from core.managers.registry import ManagerRegistry
    return ManagerRegistry().get_application_state_manager()

def _get_consolidated_session_adapter():
    """Get session adapter from consolidated ApplicationStateManager."""
    from core.managers.registry import ManagerRegistry
    return ManagerRegistry().get_application_state_manager().get_session_adapter()

def _get_consolidated_extraction_adapter():
    """Get extraction adapter from consolidated CoreOperationsManager."""
    from core.managers.registry import ManagerRegistry
    return ManagerRegistry().get_core_operations_manager().get_extraction_adapter()

def _get_consolidated_injection_adapter():
    """Get injection adapter from consolidated CoreOperationsManager."""
    from core.managers.registry import ManagerRegistry
    return ManagerRegistry().get_core_operations_manager().get_injection_adapter()


# Example usage with protocols
if __name__ == "__main__":
    # Example protocol
    class DatabaseProtocol(Protocol):
        def query(self, sql: str) -> list[str]: ...

    # Example implementation
    class SQLiteDatabase:
        def query(self, sql: str) -> list[str]:
            return ["result1", "result2"]

    # Register
    register_singleton(DatabaseProtocol, SQLiteDatabase())

    # Use
    db = inject(DatabaseProtocol)
    results = db.query("SELECT * FROM users")
    print(f"Query results: {results}")
