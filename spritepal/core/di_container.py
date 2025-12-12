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
    use_consolidated: bool = True,
    configuration_service: Any = None,
) -> None:
    """
    Configure the DI container with application dependencies.

    This function sets up all the necessary bindings for the application.
    It should be called during application initialization.

    Args:
        use_consolidated: Whether to use consolidated managers (default: True)
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
        NavigationManagerProtocol,
        SessionManagerProtocol,
        SettingsManagerProtocol,
    )
    from utils.settings_manager import SettingsManager

    if configuration_service is not None:
        register_singleton(ConfigurationServiceProtocol, configuration_service)
    else:
        # Create default ConfigurationService
        register_singleton(ConfigurationServiceProtocol, ConfigurationService())

    # Register SessionManager, ExtractionManager, InjectionManager

    if use_consolidated:
        # Register consolidated managers with adapters
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
    else:
        # Register original managers
        register_factory(
            SessionManagerProtocol,
            lambda: _get_or_create_session_manager()
        )

        register_factory(
            ExtractionManagerProtocol,
            lambda: _get_or_create_extraction_manager()
        )

        register_factory(
            InjectionManagerProtocol,
            lambda: _get_or_create_injection_manager()
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

    # Import ManualOffsetDialogFactory
    from ui.dialogs.dialog_factories import ManualOffsetDialogFactory

    # Register ManualOffsetDialogFactory
    register_factory(
        ManualOffsetDialogFactory,
        lambda: ManualOffsetDialogFactory(
            rom_cache=inject(ROMCacheProtocol),
            settings_manager=inject(SettingsManagerProtocol),
            extraction_manager=inject(ExtractionManagerProtocol),
            rom_extractor=inject(ROMExtractorProtocol)
        )
    )

    # Navigation manager is always from core operations (if available)
    register_factory(
        NavigationManagerProtocol,
        lambda: _get_or_create_navigation_manager()
    )

    # Register DialogFactory for controller dialog creation
    from core.protocols.dialog_protocols import DialogFactoryProtocol
    from ui.dialogs.controller_dialog_factory import ControllerDialogFactory

    register_factory(
        DialogFactoryProtocol,
        lambda: ControllerDialogFactory()
    )

    logger.info(f"DI container configured (consolidated={use_consolidated})")

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

def _get_or_create_session_manager():
    """Get or create session manager."""
    from core.managers.registry import ManagerRegistry
    return ManagerRegistry().get_session_manager()

def _get_or_create_extraction_manager():
    """Get or create extraction manager."""
    from core.managers.registry import ManagerRegistry
    return ManagerRegistry().get_extraction_manager()

def _get_or_create_injection_manager():
    """Get or create injection manager."""
    from core.managers.registry import ManagerRegistry
    return ManagerRegistry().get_injection_manager()

def _get_or_create_navigation_manager():
    """Get or create navigation manager."""
    from core.managers.registry import ManagerRegistry
    try:
        core_mgr = ManagerRegistry().get_core_operations_manager()
        return core_mgr._get_navigation_manager()
    except Exception:
        # Fallback to registry method if available
        return ManagerRegistry().get_navigation_manager()

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
