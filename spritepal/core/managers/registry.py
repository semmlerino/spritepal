"""
Registry for accessing manager instances
"""
from __future__ import annotations

import threading
import warnings
from typing import TYPE_CHECKING, Any

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

if TYPE_CHECKING:
    from .base_manager import BaseManager

# NavigationManager import deferred to avoid circular imports


def _topological_sort(
    manager_classes: list[type[BaseManager]],
) -> list[type[BaseManager]]:
    """
    Sort manager classes by their declared dependencies using Kahn's algorithm.

    Each manager class should have a DEPENDS_ON class variable listing its dependencies.
    Returns classes in initialization order (dependencies first).

    Raises:
        ManagerError: If circular dependencies are detected
    """
    # Build adjacency list and in-degree count
    in_degree: dict[type, int] = dict.fromkeys(manager_classes, 0)
    dependents: dict[type, list[type]] = {cls: [] for cls in manager_classes}
    class_set = set(manager_classes)

    for cls in manager_classes:
        for dep in getattr(cls, "DEPENDS_ON", []):
            if dep in class_set:
                in_degree[cls] += 1
                dependents[dep].append(cls)

    # Start with classes that have no dependencies
    queue = [cls for cls in manager_classes if in_degree[cls] == 0]
    result: list[type[BaseManager]] = []

    while queue:
        # Sort for deterministic order when multiple options exist
        queue.sort(key=lambda c: c.__name__)
        cls = queue.pop(0)
        result.append(cls)

        for dependent in dependents[cls]:
            in_degree[dependent] -= 1
            if in_degree[dependent] == 0:
                queue.append(dependent)

    if len(result) != len(manager_classes):
        # Circular dependency detected
        remaining = [c.__name__ for c in manager_classes if c not in result]
        raise ManagerError(f"Circular dependency detected among: {remaining}")

    return result

class ManagerRegistry:
    """Singleton registry for manager instances with memory leak prevention"""

    _instance: ManagerRegistry | None = None
    _lock: threading.RLock = threading.RLock()  # RLock for reentrant locking
    _cleanup_registered: bool = False

    # List of manager classes in initialization order (topological sort validates this)
    # When no DEPENDS_ON is declared, alphabetical order by class name is used.
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
            if hasattr(self, "_initialized"):
                return

            self._logger = get_logger("ManagerRegistry")
            self._managers: dict[str, Any] = {}
            self._initialized = True

            # Register cleanup with QApplication if available
            self._register_cleanup_hooks()

            self._logger.info("ManagerRegistry initialized")

    def _register_cleanup_hooks(self) -> None:
        """Register cleanup hooks with Qt application - delayed until Qt is available"""
        # Don't try to register hooks immediately - wait until Qt is actually available
        pass

    def _try_register_cleanup_hooks(self) -> None:
        """Actually register cleanup hooks when Qt is available"""
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

    @classmethod
    def validate_initialization_order(cls) -> bool:
        """
        Validate that MANAGED_CLASSES order matches topological sort of dependencies.

        Call this in tests or during development to ensure the hardcoded order
        is consistent with declared DEPENDS_ON attributes.

        Returns:
            True if order is valid

        Raises:
            ManagerError: If order doesn't match or circular dependency detected
        """
        expected_order = _topological_sort(cls.MANAGED_CLASSES)
        if expected_order != cls.MANAGED_CLASSES:
            expected_names = [c.__name__ for c in expected_order]
            actual_names = [c.__name__ for c in cls.MANAGED_CLASSES]
            raise ManagerError(
                f"MANAGED_CLASSES order doesn't match dependencies.\n"
                f"  Expected: {expected_names}\n"
                f"  Actual: {actual_names}"
            )
        return True

    # Manager initialization order is determined by declared dependencies.
    # Each manager class should have a DEPENDS_ON class variable listing its dependencies.
    # The _topological_sort() function computes a safe initialization order.
    #
    # To add a new manager:
    # 1. Declare DEPENDS_ON in your manager class (list of manager types it requires)
    # 2. Add the manager class to MANAGED_CLASSES below
    # 3. Add initialization code in initialize_managers() following the pattern
    #
    # Current order: ApplicationStateManager → CoreOperationsManager → MonitoringManager
    #
    # Use _validate_initialization_order() to verify the hardcoded order matches
    # what topological sort would produce.
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

            # Register UI factories (kept in ui/ layer to avoid layer violations)
            from ui import register_ui_factories
            register_ui_factories()

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
                self._managers["state"] = state_manager
                created_managers.append("state")

                # ApplicationStateManager IS the session manager (consolidated)
                self._managers["session"] = state_manager
                self._logger.debug("ApplicationStateManager created successfully")

                # Register SessionManager immediately - other managers depend on it via DI
                # (e.g., ROMCache → SettingsManager → SessionManager)
                from core.di_container import register_singleton
                from core.protocols.manager_protocols import (
                    ApplicationStateManagerProtocol,
                    SessionManagerProtocol,
                )
                register_singleton(ApplicationStateManagerProtocol, state_manager)
                register_singleton(SessionManagerProtocol, self._managers["session"])
                self._logger.debug("Session protocols registered for downstream dependencies")

                # CoreOperationsManager handles extraction and injection operations
                self._logger.debug("Creating CoreOperationsManager...")
                core_manager = CoreOperationsManager(parent=qt_parent)
                self._managers["core_operations"] = core_manager
                created_managers.append("core_operations")

                # CoreOperationsManager IS both extraction and injection manager (consolidated)
                self._managers["extraction"] = core_manager
                self._managers["injection"] = core_manager
                self._logger.debug("CoreOperationsManager created successfully")

                # MonitoringManager for performance and health monitoring
                self._logger.debug("Creating MonitoringManager...")
                monitoring_manager = MonitoringManager(parent=qt_parent)
                self._managers["monitoring"] = monitoring_manager
                created_managers.append("monitoring")
                self._logger.debug("MonitoringManager created successfully")

                # Register existing managers for automatic monitoring
                if "extraction" in self._managers:
                    monitoring_manager.register_manager_monitoring(self._managers["extraction"])
                if "injection" in self._managers:
                    monitoring_manager.register_manager_monitoring(self._managers["injection"])
                if "session" in self._managers:
                    monitoring_manager.register_manager_monitoring(self._managers["session"])

                # Register CoreOperationsManager with DI container
                # (SessionManager and ApplicationStateManager already registered above)
                from core.di_container import register_managers
                register_managers(core_operations_manager=core_manager)
                self._logger.debug("All manager protocols registered with DI container")

                self._logger.info("All managers initialized successfully")

            except Exception as e:
                self._logger.exception(f"Manager initialization failed: {e}")

                # Cleanup any managers that were created before the failure
                for manager_name in created_managers:
                    try:
                        if manager_name in self._managers:
                            manager = self._managers[manager_name]
                            manager.cleanup()
                            del self._managers[manager_name]
                            self._logger.debug(f"Cleaned up {manager_name} manager after initialization failure")
                    except Exception as cleanup_error:
                        self._logger.exception(f"Error cleaning up {manager_name} manager: {cleanup_error}")

                # Re-raise as ManagerError
                raise ManagerError(f"Failed to initialize managers: {e}") from e

    @suppress_logging_errors
    def cleanup_managers(self) -> None:
        """Cleanup all managers with enhanced memory leak prevention"""
        with self._lock:
            safe_info(self._logger, "Cleaning up managers...")

            # Cleanup in reverse order
            for name in reversed(list(self._managers.keys())):
                try:
                    manager = self._managers[name]
                    manager.cleanup()
                    safe_debug(self._logger, f"Cleaned up {name} manager")
                except Exception:
                    safe_warning(self._logger, f"Error cleaning up {name} manager", exc_info=True)

            self._managers.clear()

            # Clear DI container registrations so managers can't be retrieved after cleanup
            try:
                from core.di_container import reset_container
                reset_container()
                safe_debug(self._logger, "Cleared DI container registrations")
            except Exception as e:
                safe_debug(self._logger, f"Error clearing DI container: {e}")

            safe_info(self._logger, "All managers cleaned up")

    def get_session_manager(self) -> SessionManager:
        """
        Get the session manager instance.

        .. deprecated::
            Use ``inject(SessionManagerProtocol)`` from ``core.di_container`` instead.

        Returns:
            SessionManager instance

        Raises:
            ManagerError: If manager not initialized
        """
        warnings.warn(
            "ManagerRegistry.get_session_manager() is deprecated. "
            "Use inject(SessionManagerProtocol) from core.di_container instead.",
            DeprecationWarning,
            stacklevel=2
        )
        from core.di_container import inject
        from core.protocols.manager_protocols import SessionManagerProtocol
        try:
            return inject(SessionManagerProtocol)  # type: ignore[return-value]
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
        return self._get_manager("core_operations", CoreOperationsManager)

    def get_application_state_manager(self):
        """
        Get the consolidated application state manager instance

        Returns:
            ApplicationStateManager instance

        Raises:
            ManagerError: If manager not initialized
        """
        return self._get_manager("state", ApplicationStateManager)

    def get_monitoring_manager(self):
        """
        Get the monitoring manager instance

        Returns:
            MonitoringManager instance

        Raises:
            ManagerError: If manager not initialized
        """
        return self._get_manager("monitoring", MonitoringManager)

    def _get_manager(self, name: str, expected_type: type) -> Any:
        """
        Get a manager by name with type checking and dependency validation

        Args:
            name: Manager name
            expected_type: Expected manager type

        Returns:
            Manager instance

        Raises:
            ManagerError: If manager not found, wrong type, or not properly initialized
        """
        with self._lock:
            if name not in self._managers:
                raise ManagerError(
                    f"{name.capitalize()} manager not initialized. "
                    "Call initialize_managers() first."
                )

            manager = self._managers[name]
            if not isinstance(manager, expected_type):
                raise ManagerError(
                    f"Manager type mismatch: expected {expected_type.__name__}, "
                    f"got {type(manager).__name__}"
                )

            # Validate that the manager is properly initialized
            if not manager.is_initialized():
                raise ManagerError(
                    f"{name.capitalize()} manager found but not properly initialized. "
                    "This may indicate a partial initialization failure."
                )

            return manager

    def is_initialized(self) -> bool:
        """Check if managers are initialized"""
        # Check that all expected managers are present AND initialized
        # Note: NavigationManager excluded - see initialize_managers() for re-enable instructions
        expected_managers = {"session", "extraction", "injection"}
        if not expected_managers.issubset(self._managers.keys()):
            return False
        return all(
            self._managers[name].is_initialized()
            for name in expected_managers
        )

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
        return self._managers.copy()

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
            # Validate that all managers are individually initialized
            for name, manager in self._managers.items():
                if not manager.is_initialized():
                    raise ManagerError(f"{name} manager not properly initialized")

            # Validate specific dependency relationships
            # InjectionManager depends on SessionManager
            injection_manager = self._managers.get("injection")
            session_manager = self._managers.get("session")

            if injection_manager and not session_manager:
                raise ManagerError("InjectionManager requires SessionManager but it's not available")

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
