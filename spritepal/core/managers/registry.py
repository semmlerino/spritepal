"""
Registry for accessing manager instances
"""
from __future__ import annotations

import threading
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
from .ui_coordinator_manager import UICoordinatorManager

# NavigationManager import deferred to avoid circular imports

class ManagerRegistry:
    """Singleton registry for manager instances with memory leak prevention"""

    _instance: ManagerRegistry | None = None
    _lock: threading.RLock = threading.RLock()  # RLock for reentrant locking
    _cleanup_registered: bool = False

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

    def initialize_managers(
        self,
        app_name: str = "SpritePal",
        settings_path: Any = None,
        use_consolidated: bool = True,
        configuration_service: Any = None,
    ) -> None:
        """
        Initialize all managers with proper error handling and cleanup

        Args:
            app_name: Application name for settings
            settings_path: Optional custom settings path (for testing)
            use_consolidated: Whether to use consolidated managers (default: True)
            configuration_service: Optional pre-created ConfigurationService instance

        Raises:
            ManagerError: If manager initialization fails
        """
        with self._lock:  # Ensure thread-safe initialization
            # Skip if already initialized
            if self.is_initialized():
                self._logger.debug("Managers already initialized, skipping")
                return

            self._logger.info(f"Initializing managers (consolidated={use_consolidated})...")

            # Configure the DI container first to register all protocols
            # Pass configuration_service so it gets registered in the container
            from core.di_container import configure_container
            configure_container(
                use_consolidated=use_consolidated,
                configuration_service=configuration_service,
            )

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
                if use_consolidated:
                    # Use new consolidated managers
                    self._logger.debug("Creating ApplicationStateManager...")
                    state_manager = ApplicationStateManager(app_name, settings_path, parent=qt_parent)
                    self._managers["state"] = state_manager
                    created_managers.append("state")

                    # Register adapters for backward compatibility
                    self._managers["session"] = state_manager.get_session_adapter()
                    self._logger.debug("ApplicationStateManager created successfully")

                    # Create CoreOperationsManager
                    self._logger.debug("Creating CoreOperationsManager...")
                    core_manager = CoreOperationsManager(parent=qt_parent)
                    self._managers["core_operations"] = core_manager
                    created_managers.append("core_operations")

                    # Register adapters
                    self._managers["extraction"] = core_manager.get_extraction_adapter()
                    self._managers["injection"] = core_manager.get_injection_adapter()
                    self._logger.debug("CoreOperationsManager created successfully")

                    # Create UICoordinatorManager
                    self._logger.debug("Creating UICoordinatorManager...")
                    ui_manager = UICoordinatorManager(parent=qt_parent)
                    self._managers["ui_coordinator"] = ui_manager
                    created_managers.append("ui_coordinator")
                    self._logger.debug("UICoordinatorManager created successfully")

                else:
                    # Use original managers for backward compatibility
                    # Initialize session manager first as others may depend on it
                    # SessionManager inherits from BaseManager (QObject), so it can take a parent
                    self._logger.debug("Creating SessionManager...")
                    session_manager = SessionManager(app_name, settings_path)
                    session_manager.setParent(qt_parent)  # Set parent after creation
                    self._managers["session"] = session_manager
                    created_managers.append("session")
                    self._logger.debug("SessionManager created successfully")

                    # Initialize Qt-based managers with proper parent to prevent lifecycle issues
                    self._logger.debug("Creating ExtractionManager...")
                    extraction_manager = ExtractionManager(parent=qt_parent)
                    self._managers["extraction"] = extraction_manager
                    created_managers.append("extraction")
                    self._logger.debug("ExtractionManager created successfully")

                    self._logger.debug("Creating InjectionManager...")
                    injection_manager = InjectionManager(parent=qt_parent)
                    self._managers["injection"] = injection_manager
                    created_managers.append("injection")
                    self._logger.debug("InjectionManager created successfully")

                # NavigationManager is DISABLED due to threading issues in tests.
                # Implementation exists at: core/navigation/manager.py (600+ lines)
                # To re-enable: uncomment below and add "navigation" to expected_managers
                # in is_initialized() method.
                # from core.navigation.manager import NavigationManager
                # self._managers["navigation"] = NavigationManager(parent=qt_parent)
                # created_managers.append("navigation")

                # Initialize MonitoringManager
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

                # Future managers will be added here

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

            # Clear context references to break circular dependencies
            try:
                from .context import _context_manager
                if _context_manager is not None:
                    _context_manager.set_current_context(None)
                    safe_debug(self._logger, "Cleared context manager references")
                else:
                    safe_debug(self._logger, "Context manager already cleaned up")
            except Exception as e:
                safe_debug(self._logger, f"Error clearing context references: {e}")

            safe_info(self._logger, "All managers cleaned up")

    def get_session_manager(self) -> SessionManager:
        """
        Get the session manager instance.

        Delegates to DI container for consistent dependency resolution.

        Returns:
            SessionManager instance

        Raises:
            ManagerError: If manager not initialized
        """
        from core.di_container import inject
        from core.protocols.manager_protocols import SessionManagerProtocol
        try:
            return inject(SessionManagerProtocol)  # type: ignore[return-value]
        except ValueError as e:
            raise ManagerError("SessionManager not initialized. Call initialize_managers() first.") from e

    def get_extraction_manager(self) -> ExtractionManager:
        """
        Get the extraction manager instance.

        Delegates to DI container for consistent dependency resolution.

        Returns:
            ExtractionManager instance

        Raises:
            ManagerError: If manager not initialized
        """
        from core.di_container import inject
        from core.protocols.manager_protocols import ExtractionManagerProtocol
        try:
            return inject(ExtractionManagerProtocol)  # type: ignore[return-value]
        except ValueError as e:
            raise ManagerError("ExtractionManager not initialized. Call initialize_managers() first.") from e

    def get_injection_manager(self) -> InjectionManager:
        """
        Get the injection manager instance.

        Delegates to DI container for consistent dependency resolution.

        Returns:
            InjectionManager instance

        Raises:
            ManagerError: If manager not initialized
        """
        from core.di_container import inject
        from core.protocols.manager_protocols import InjectionManagerProtocol
        try:
            return inject(InjectionManagerProtocol)  # type: ignore[return-value]
        except ValueError as e:
            raise ManagerError("InjectionManager not initialized. Call initialize_managers() first.") from e

    def get_navigation_manager(self):
        """
        Get the navigation manager instance

        Returns:
            NavigationManager instance

        Raises:
            ManagerError: If manager not initialized
        """
        # Use DI container to resolve NavigationManager - eliminates circular dependencies
        from core.di_container import inject
        from core.protocols.manager_protocols import NavigationManagerProtocol
        try:
            return inject(NavigationManagerProtocol)
        except ValueError as e:
            raise ManagerError("NavigationManager not initialized. Call initialize_managers() first.") from e

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

    def get_ui_coordinator_manager(self):
        """
        Get the consolidated UI coordinator manager instance

        Returns:
            UICoordinatorManager instance

        Raises:
            ManagerError: If manager not initialized
        """
        return self._get_manager("ui_coordinator", UICoordinatorManager)

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
            # CRITICAL: Also reset the module-level _registry to match
            # This ensures both ManagerRegistry() and _ensure_registry() return the same instance
            # Without this, DI factories using ManagerRegistry() get a different instance
            # than initialize_managers() which uses _registry via _ensure_registry()
            _registry = ManagerRegistry()

# Global instance accessor functions with context support
_registry = ManagerRegistry()

# Register cleanup at module level to prevent memory leaks
@suppress_logging_errors
def _cleanup_global_registry():
    """Cleanup function for module-level registry"""
    global _registry
    try:
        _registry.cleanup_managers()
    except Exception:
        pass  # Ignore errors during cleanup
    _registry = None  # Always clear registry reference

import atexit

atexit.register(_cleanup_global_registry)

def _ensure_registry() -> ManagerRegistry:
    """Ensure the global registry is available and return it."""
    if _registry is None:
        raise ManagerError("Manager registry has been cleaned up or not initialized")
    return _registry

def initialize_managers(
    app_name: str = "SpritePal",
    settings_path: Any = None,
    use_consolidated: bool = True,
    configuration_service: Any = None,
) -> None:
    """
    Initialize all managers

    Args:
        app_name: Application name for settings
        settings_path: Optional custom settings path (for testing)
        use_consolidated: Whether to use consolidated managers (default: True)
        configuration_service: Optional pre-created ConfigurationService instance
    """
    _ensure_registry().initialize_managers(
        app_name, settings_path, use_consolidated, configuration_service
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
