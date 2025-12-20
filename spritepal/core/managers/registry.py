"""
Registry for accessing manager instances
"""
from __future__ import annotations

import threading
import warnings
from typing import Any

from PySide6.QtWidgets import QApplication

from utils.logging_config import get_logger
from utils.safe_logging import (
    safe_debug,
    safe_info,
    safe_warning,
    suppress_logging_errors,
)

from .application_state_manager import ApplicationStateManager

# Import new consolidated managers
from .core_operations_manager import CoreOperationsManager
from .exceptions import ManagerError
from .extraction_manager import ExtractionManager
from .injection_manager import InjectionManager
from .monitoring_manager import MonitoringManager
from .session_manager import SessionManager

# NavigationManager import deferred to avoid circular imports

# Import protocols for dependency declaration (deferred to avoid circular imports at module load)
# These are used by MANAGER_DEPENDENCIES and validation functions below.


class InitializationError(ManagerError):
    """Raised when manager initialization order dependencies are not satisfied."""

    pass


# Explicit manager dependencies - protocols that must be registered BEFORE manager creation.
# This documents the dependency chain and enables validation at startup.
# Key: Manager class, Value: List of protocol types that must be registered first
MANAGER_DEPENDENCIES: dict[type, list[type]] = {}  # Populated lazily to avoid import issues

# Maps manager classes to the protocols they register (for validation)
MANAGER_TO_PROTOCOLS: dict[type, list[type]] = {}  # Populated lazily to avoid import issues

_DEPENDENCY_MAPS_INITIALIZED = False


def _ensure_dependency_maps() -> None:
    """Lazily initialize dependency maps to avoid circular import issues."""
    global _DEPENDENCY_MAPS_INITIALIZED
    if _DEPENDENCY_MAPS_INITIALIZED:
        return

    # Import protocols here to avoid circular imports at module load time
    from core.protocols.manager_protocols import (
        ApplicationStateManagerProtocol,
        ExtractionManagerProtocol,
        InjectionManagerProtocol,
    )

    from .application_state_manager import ApplicationStateManager
    from .core_operations_manager import CoreOperationsManager
    from .monitoring_manager import MonitoringManager

    MANAGER_DEPENDENCIES.update({
        ApplicationStateManager: [],  # No dependencies - always first
        CoreOperationsManager: [ApplicationStateManagerProtocol],  # Needs state manager via DI chain
        MonitoringManager: [],  # No DI dependencies (uses direct references passed in)
    })

    MANAGER_TO_PROTOCOLS.update({
        ApplicationStateManager: [ApplicationStateManagerProtocol],
        CoreOperationsManager: [ExtractionManagerProtocol, InjectionManagerProtocol],
        MonitoringManager: [],  # Not registered with a protocol
    })

    _DEPENDENCY_MAPS_INITIALIZED = True


def _get_protocols_for_manager(manager_class: type) -> list[type]:
    """Return protocols registered by a manager class.

    Args:
        manager_class: The manager class to look up.

    Returns:
        List of protocol types that this manager registers.
    """
    _ensure_dependency_maps()
    return MANAGER_TO_PROTOCOLS.get(manager_class, [])


def validate_manager_order(managed_classes: list[type] | None = None) -> None:
    """Validate that manager class order satisfies declared dependencies.

    Checks that for each manager in the list, all of its required dependencies
    (protocols) would be registered by managers appearing earlier in the list.

    Args:
        managed_classes: List of manager classes to validate. If None, uses
            ManagerRegistry.MANAGED_CLASSES.

    Raises:
        InitializationError: If a manager appears before its dependencies.
    """
    _ensure_dependency_maps()

    if managed_classes is None:
        managed_classes = ManagerRegistry.MANAGED_CLASSES

    # Track which protocols would be registered at each point
    registered_protocols: set[type] = set()

    for manager_class in managed_classes:
        # Check if this manager has a dependency declaration
        if manager_class not in MANAGER_DEPENDENCIES:
            raise InitializationError(
                f"{manager_class.__name__} is in MANAGED_CLASSES but not in "
                f"MANAGER_DEPENDENCIES. Add it to document its dependencies."
            )

        # Check that all dependencies are satisfied
        deps = MANAGER_DEPENDENCIES[manager_class]
        for dep in deps:
            if dep not in registered_protocols:
                raise InitializationError(
                    f"{manager_class.__name__} requires {dep.__name__} but no earlier "
                    f"manager in MANAGED_CLASSES registers it. "
                    f"Reorder MANAGED_CLASSES or update MANAGER_DEPENDENCIES."
                )

        # Track which protocols this manager provides
        registered_protocols.update(_get_protocols_for_manager(manager_class))


class ManagerRegistry:
    """Singleton registry for manager instances with memory leak prevention"""

    _instance: ManagerRegistry | None = None
    _lock: threading.RLock = threading.RLock()  # RLock for reentrant locking
    _cleanup_registered: bool = False

    # List of manager classes in initialization order.
    # Order: ApplicationStateManager → CoreOperationsManager → MonitoringManager
    MANAGED_CLASSES: list[type] = [
        ApplicationStateManager,
        CoreOperationsManager,
        MonitoringManager,
    ]

    def __new__(cls) -> ManagerRegistry:
        """Ensure only one instance exists"""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        """Initialize the registry"""
        # Thread-safe initialization check to prevent race between __new__ and __init__
        with self._lock:
            # Only initialize once
            if hasattr(self, "_init_done"):
                return

            self._logger = get_logger("ManagerRegistry")
            # Track protocols in initialization order for proper cleanup sequencing
            # DI container is the single source of truth for manager instances
            self._lifecycle_order: list[type] = []
            self._init_done = True
            self._managers_initialized = False

            self._logger.info("ManagerRegistry initialized")

    def _try_register_cleanup_hooks(self) -> None:
        """Register cleanup hooks with QApplication if available.

        Called during initialize_managers() when a QApplication exists.
        Falls back to atexit handler (module-level) if Qt is unavailable.
        """
        # Thread-safe check-then-act to prevent duplicate cleanup registration
        with ManagerRegistry._lock:
            if ManagerRegistry._cleanup_registered:
                return
            try:
                app = QApplication.instance()
                if app is not None:
                    app.aboutToQuit.connect(lambda: self.cleanup_managers())
                    ManagerRegistry._cleanup_registered = True
                    self._logger.debug("Registered cleanup with QApplication.aboutToQuit")
            except Exception as e:
                self._logger.debug(f"Could not register Qt cleanup: {e}")

    # To add a new manager:
    # 1. Add the manager class to MANAGED_CLASSES (maintain initialization order)
    # 2. Add initialization code in initialize_managers() following the pattern
    # Current order: ApplicationStateManager → CoreOperationsManager → MonitoringManager
    def initialize_managers(
        self,
        app_name: str = "SpritePal",
        settings_path: Any = None,
        configuration_service: Any = None,
    ) -> None:
        """
        Initialize all managers with proper error handling and cleanup.

        Uses the consolidated manager architecture where:
        - ApplicationStateManager handles session, settings, state, and history
        - CoreOperationsManager handles extraction and injection operations
        - Adapters provide backward-compatible interfaces (SessionManager, etc.)

        Args:
            app_name: Application name for settings
            settings_path: Optional custom settings path (for testing)
            configuration_service: Optional pre-created ConfigurationService instance

        Raises:
            ManagerError: If manager initialization fails
        """
        with self._lock:  # Ensure thread-safe initialization
            # Skip if already initialized
            if self.is_initialized():
                self._logger.debug("Managers already initialized, skipping")
                return

            self._logger.info("Initializing managers with consolidated architecture...")

            # Configure the DI container first to register all protocols
            # Pass configuration_service so it gets registered in the container
            from core.di_container import configure_container
            configure_container(configuration_service=configuration_service)

            # NOTE: UI factory registration (register_ui_factories) must be called
            # by the application entry point AFTER initialize_managers() completes.
            # This keeps the core layer free of UI dependencies.
            # See: launch_spritepal.py, tests/fixtures/core_fixtures.py

            # Get Qt application instance for proper parent management
            app = QApplication.instance()
            if not app:
                self._logger.warning("No QApplication instance found - managers will have no Qt parent")
                qt_parent = None
            else:
                qt_parent = app
                self._logger.debug("Using QApplication as Qt parent for managers")
                # Now that we have a QApplication, try to register cleanup hooks
                self._try_register_cleanup_hooks()

            # Track which managers were created for cleanup on failure
            created_managers = []

            try:
                # Create consolidated managers
                # ApplicationStateManager handles session, settings, state, and history
                self._logger.debug("Creating ApplicationStateManager...")
                state_manager = ApplicationStateManager(app_name, settings_path, parent=qt_parent)
                created_managers.append("state")
                self._logger.debug("ApplicationStateManager created successfully")

                # Register ApplicationStateManagerProtocol immediately - other managers depend on it via DI
                # (e.g., ROMCache → SettingsManager → ApplicationStateManager)
                from core.di_container import register_singleton
                from core.protocols.manager_protocols import (
                    ApplicationStateManagerProtocol,
                    ExtractionManagerProtocol,
                    InjectionManagerProtocol,
                )
                register_singleton(ApplicationStateManagerProtocol, state_manager)
                self._lifecycle_order.append(ApplicationStateManagerProtocol)
                self._logger.debug("ApplicationStateManagerProtocol registered for downstream dependencies")

                # CoreOperationsManager handles extraction and injection operations
                self._logger.debug("Creating CoreOperationsManager...")
                core_manager = CoreOperationsManager(parent=qt_parent)
                created_managers.append("core_operations")
                self._logger.debug("CoreOperationsManager created successfully")

                # MonitoringManager for performance and health monitoring
                self._logger.debug("Creating MonitoringManager...")
                monitoring_manager = MonitoringManager(parent=qt_parent)
                created_managers.append("monitoring")
                self._logger.debug("MonitoringManager created successfully")

                # Register managers for automatic monitoring
                monitoring_manager.register_manager_monitoring(core_manager)
                monitoring_manager.register_manager_monitoring(state_manager)

                # Register CoreOperationsManager with DI container
                # Registered under both ExtractionManagerProtocol and InjectionManagerProtocol
                from core.di_container import register_managers
                register_managers(core_operations_manager=core_manager)
                self._lifecycle_order.append(ExtractionManagerProtocol)
                self._lifecycle_order.append(InjectionManagerProtocol)
                self._logger.debug("All manager protocols registered with DI container")

                # Mark as initialized
                self._managers_initialized = True
                self._logger.info("All managers initialized successfully")

            except Exception as e:
                self._logger.exception(f"Manager initialization failed: {e}")

                # Cleanup any protocols that were registered before the failure
                from core.di_container import get_container
                container = get_container()
                for protocol in self._lifecycle_order:
                    try:
                        manager = container.get_optional(protocol)
                        if manager is not None:
                            manager.cleanup()
                            container.unregister(protocol)
                            self._logger.debug(f"Cleaned up {protocol.__name__} after initialization failure")
                    except Exception as cleanup_error:
                        self._logger.exception(f"Error cleaning up {protocol.__name__}: {cleanup_error}")

                self._lifecycle_order.clear()
                self._managers_initialized = False

                # Re-raise as ManagerError
                raise ManagerError(f"Failed to initialize managers: {e}") from e

    @suppress_logging_errors
    def cleanup_managers(self) -> None:
        """Cleanup all managers with enhanced memory leak prevention"""
        with self._lock:
            safe_info(self._logger, "Cleaning up managers...")

            # Cleanup in reverse order via lifecycle tracking
            from core.di_container import get_container, reset_container
            container = get_container()

            for protocol in reversed(self._lifecycle_order):
                try:
                    manager = container.get_optional(protocol)
                    if manager is not None:
                        manager.cleanup()
                        safe_debug(self._logger, f"Cleaned up {protocol.__name__}")
                except Exception:
                    safe_warning(self._logger, f"Error cleaning up {protocol.__name__}", exc_info=True)

            self._lifecycle_order.clear()
            self._managers_initialized = False

            # Clear DI container registrations so managers can't be retrieved after cleanup
            try:
                reset_container()
                safe_debug(self._logger, "Cleared DI container registrations")
            except Exception as e:
                safe_debug(self._logger, f"Error clearing DI container: {e}")

            safe_info(self._logger, "All managers cleaned up")

    def get_session_manager(self) -> SessionManager:
        """
        Get the session manager instance.

        .. deprecated::
            Use ``inject(ApplicationStateManagerProtocol)`` from ``core.di_container`` instead.

        Returns:
            SessionManager instance

        Raises:
            ManagerError: If manager not initialized
        """
        warnings.warn(
            "ManagerRegistry.get_session_manager() is deprecated. "
            "Use inject(ApplicationStateManagerProtocol) from core.di_container instead.",
            DeprecationWarning,
            stacklevel=2
        )
        from core.di_container import inject
        from core.protocols.manager_protocols import ApplicationStateManagerProtocol
        try:
            return inject(ApplicationStateManagerProtocol)  # type: ignore[return-value]
        except ValueError as e:
            raise ManagerError("SessionManager not initialized. Call initialize_managers() first.") from e

    def get_extraction_manager(self) -> ExtractionManager:
        """
        Get the extraction manager instance.

        .. deprecated::
            Use ``inject(ExtractionManagerProtocol)`` from ``core.di_container`` instead.

        Returns:
            ExtractionManager instance

        Raises:
            ManagerError: If manager not initialized
        """
        warnings.warn(
            "ManagerRegistry.get_extraction_manager() is deprecated. "
            "Use inject(ExtractionManagerProtocol) from core.di_container instead.",
            DeprecationWarning,
            stacklevel=2
        )
        from core.di_container import inject
        from core.protocols.manager_protocols import ExtractionManagerProtocol
        try:
            return inject(ExtractionManagerProtocol)  # type: ignore[return-value]
        except ValueError as e:
            raise ManagerError("ExtractionManager not initialized. Call initialize_managers() first.") from e

    def get_injection_manager(self) -> InjectionManager:
        """
        Get the injection manager instance.

        .. deprecated::
            Use ``inject(InjectionManagerProtocol)`` from ``core.di_container`` instead.

        Returns:
            InjectionManager instance

        Raises:
            ManagerError: If manager not initialized
        """
        warnings.warn(
            "ManagerRegistry.get_injection_manager() is deprecated. "
            "Use inject(InjectionManagerProtocol) from core.di_container instead.",
            DeprecationWarning,
            stacklevel=2
        )
        from core.di_container import inject
        from core.protocols.manager_protocols import InjectionManagerProtocol
        try:
            return inject(InjectionManagerProtocol)  # type: ignore[return-value]
        except ValueError as e:
            raise ManagerError("InjectionManager not initialized. Call initialize_managers() first.") from e

    def get_core_operations_manager(self):
        """
        Get the consolidated core operations manager instance

        Returns:
            CoreOperationsManager instance

        Raises:
            ManagerError: If manager not initialized
        """
        from core.protocols.manager_protocols import ExtractionManagerProtocol
        return self._get_manager_by_protocol(ExtractionManagerProtocol, CoreOperationsManager)

    def get_application_state_manager(self):
        """
        Get the consolidated application state manager instance

        Returns:
            ApplicationStateManager instance

        Raises:
            ManagerError: If manager not initialized
        """
        from core.protocols.manager_protocols import ApplicationStateManagerProtocol
        return self._get_manager_by_protocol(ApplicationStateManagerProtocol, ApplicationStateManager)

    def get_monitoring_manager(self):
        """
        Get the monitoring manager instance.

        Note: MonitoringManager is not registered with a protocol in DI container,
        so this method is not supported. Use inject() for protocol-based access.

        Raises:
            ManagerError: Always - MonitoringManager has no protocol registration
        """
        raise ManagerError(
            "MonitoringManager is not accessible via protocol. "
            "It is only used internally for manager monitoring."
        )

    def _get_manager_by_protocol(self, protocol: type, expected_type: type) -> Any:
        """
        Get a manager by protocol with type checking and dependency validation

        Args:
            protocol: Protocol type to retrieve from DI container
            expected_type: Expected manager type

        Returns:
            Manager instance

        Raises:
            ManagerError: If manager not found, wrong type, or not properly initialized
        """
        with self._lock:
            from core.di_container import get_container
            container = get_container()

            manager = container.get_optional(protocol)
            if manager is None:
                raise ManagerError(
                    f"{protocol.__name__} not initialized. "
                    "Call initialize_managers() first."
                )

            if not isinstance(manager, expected_type):
                raise ManagerError(
                    f"Manager type mismatch: expected {expected_type.__name__}, "
                    f"got {type(manager).__name__}"
                )

            # Validate that the manager is properly initialized
            if not manager.is_initialized():
                raise ManagerError(
                    f"{protocol.__name__} found but not properly initialized. "
                    "This may indicate a partial initialization failure."
                )

            return manager

    def is_initialized(self) -> bool:
        """Check if managers are initialized"""
        return self._managers_initialized

    @classmethod
    def is_clean(cls) -> bool:
        """Check if the registry is in a clean (uninitialized) state.

        Used by test infrastructure to detect state pollution between tests.
        A clean registry has no singleton instance.

        Returns:
            True if no singleton instance exists, False if initialized.
        """
        return cls._instance is None

    def get_all_managers(self) -> dict[str, Any]:
        """Get all registered managers (for testing/debugging)"""
        from core.di_container import get_container
        container = get_container()
        result: dict[str, Any] = {}
        for protocol in self._lifecycle_order:
            manager = container.get_optional(protocol)
            if manager is not None:
                result[protocol.__name__] = manager
        return result

    def validate_manager_dependencies(self) -> bool:
        """
        Validate that all managers and their dependencies are properly initialized

        Returns:
            True if all dependencies are satisfied, False otherwise

        Raises:
            ManagerError: If critical dependency issues are found
        """
        if not self.is_initialized():
            self._logger.warning("Managers not initialized, cannot validate dependencies")
            return False

        self._logger.debug("Validating manager dependencies...")

        try:
            from core.di_container import get_container
            container = get_container()

            # Validate that all managers are individually initialized
            for protocol in self._lifecycle_order:
                manager = container.get_optional(protocol)
                if manager is None:
                    raise ManagerError(f"{protocol.__name__} not registered")
                if not manager.is_initialized():
                    raise ManagerError(f"{protocol.__name__} not properly initialized")

            self._logger.debug("All manager dependencies validated successfully")
            return True

        except Exception as e:
            self._logger.exception(f"Manager dependency validation failed: {e}")
            return False

    @classmethod
    def reset_for_tests(cls) -> None:
        """Reset singleton state for test isolation.

        This is the ONLY approved way to reset the registry in tests.
        Call cleanup_managers() first to properly shut down managers.

        WARNING: This method is for test infrastructure only.
        Do not use in production code.
        """
        global _registry
        with cls._lock:
            # Reset the singleton instance
            cls._instance = None
            # Reset cleanup registration flag
            cls._cleanup_registered = False
            # Reset module-level _registry to None - lazy init via _ensure_registry()
            # will create a new instance when next accessed. This ensures is_clean()
            # returns True immediately after reset.
            _registry = None

# Global instance accessor functions with context support
_registry = ManagerRegistry()

# Register cleanup at module level to prevent memory leaks
@suppress_logging_errors
def _cleanup_global_registry():
    """Cleanup function for module-level registry"""
    global _registry
    try:
        if _registry is not None:
            _registry.cleanup_managers()
    except Exception:
        pass  # Ignore errors during cleanup
    _registry = None  # Always clear registry reference

import atexit

atexit.register(_cleanup_global_registry)

def _ensure_registry() -> ManagerRegistry:
    """Ensure the global registry is available and return it.

    Lazily creates the registry if it was reset for tests or not yet initialized.
    This ensures both ManagerRegistry() and _ensure_registry() return the same instance.
    """
    global _registry
    if _registry is None:
        _registry = ManagerRegistry()
    return _registry

def initialize_managers(
    app_name: str = "SpritePal",
    settings_path: Any = None,
    configuration_service: Any = None,
) -> None:
    """
    Initialize all managers with consolidated architecture.

    Uses ApplicationStateManager + CoreOperationsManager with backward-compatible
    adapters for SessionManager, ExtractionManager, and InjectionManager.

    Args:
        app_name: Application name for settings
        settings_path: Optional custom settings path (for testing)
        configuration_service: Optional pre-created ConfigurationService instance
    """
    _ensure_registry().initialize_managers(
        app_name, settings_path, configuration_service
    )

def cleanup_managers() -> None:
    """Cleanup all managers"""
    _ensure_registry().cleanup_managers()

def validate_manager_dependencies() -> bool:
    """
    Validate that all manager dependencies are satisfied

    Returns:
        True if all dependencies are valid, False otherwise
    """
    return _ensure_registry().validate_manager_dependencies()
