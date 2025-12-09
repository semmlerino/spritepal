"""
Manager initialization using dependency injection container.
Eliminates circular dependencies through proper inversion of control.
"""
from __future__ import annotations

import contextlib
import logging
from pathlib import Path
from typing import Any

from PySide6.QtWidgets import QApplication

from core.di_container import (
    get_container,
    inject,
)
from core.protocols.manager_protocols import (
    ExtractionManagerProtocol,
    InjectionManagerProtocol,
    NavigationManagerProtocol,
    SessionManagerProtocol,
)

from .exceptions import ManagerError
from .extraction_manager import ExtractionManager
from .injection_manager import InjectionManager

# Import concrete manager classes
from .session_manager import SessionManager

logger = logging.getLogger(__name__)

def create_session_manager(app_name: str = "SpritePal", settings_path: Path | None = None) -> SessionManagerProtocol:
    """
    Factory function to create SessionManager.

    Args:
        app_name: Application name for settings
        settings_path: Optional custom settings path

    Returns:
        SessionManager instance
    """
    return SessionManager(app_name, settings_path)  # type: ignore[return-value]  # Protocol mismatch - concrete class has different signature

def create_extraction_manager() -> ExtractionManagerProtocol:
    """
    Factory function to create ExtractionManager.

    Returns:
        ExtractionManager instance
    """
    return ExtractionManager()  # type: ignore[return-value]  # Protocol mismatch - concrete class has different signature

def create_injection_manager() -> InjectionManagerProtocol:
    """
    Factory function to create InjectionManager.

    Returns:
        InjectionManager instance
    """
    return InjectionManager()  # type: ignore[return-value]  # Protocol mismatch - concrete class has different methods

def create_navigation_manager() -> NavigationManagerProtocol:
    """
    Factory function to create NavigationManager.

    Returns:
        NavigationManager instance
    """
    # Import NavigationManager only when needed to avoid circular imports
    try:
        from core.navigation.manager import NavigationManager
        return NavigationManager()  # type: ignore[return-value]  # Protocol mismatch - concrete class has different methods
    except ImportError as e:
        logger.warning(f"NavigationManager not available: {e}")
        raise ManagerError(f"NavigationManager not available: {e}") from e

def initialize_managers(app_name: str = "SpritePal", settings_path: Path | None = None) -> None:
    """
    Initialize all managers using dependency injection container.

    Args:
        app_name: Application name for settings
        settings_path: Optional custom settings path for testing

    Raises:
        ManagerError: If manager initialization fails
    """
    container = get_container()

    # Clear any existing registrations
    container.clear()

    logger.info("Initializing managers with DI container...")

    try:
        # Register factory functions with the DI container
        # SessionManager has no dependencies, register first
        container.register_factory(
            SessionManagerProtocol,
            lambda: create_session_manager(app_name, settings_path)
        )

        # ExtractionManager has no dependencies
        container.register_factory(
            ExtractionManagerProtocol,
            create_extraction_manager
        )

        # InjectionManager dependencies will be resolved via DI when needed
        container.register_factory(
            InjectionManagerProtocol,
            create_injection_manager
        )

        # NavigationManager (optional, may fail in some environments)
        try:
            container.register_factory(
                NavigationManagerProtocol,
                create_navigation_manager
            )
            logger.info("NavigationManager factory registered")
        except (ImportError, ManagerError) as e:
            logger.info(f"NavigationManager not available, skipping: {e}")

        # Trigger creation of all managers to ensure they initialize properly
        session_manager = container.get(SessionManagerProtocol)
        extraction_manager = container.get(ExtractionManagerProtocol)
        injection_manager = container.get(InjectionManagerProtocol)

        # Try to get NavigationManager if available
        navigation_manager = None
        try:
            navigation_manager = container.get(NavigationManagerProtocol)
        except ValueError:
            logger.info("NavigationManager not registered, continuing without it")

        # Set up Qt parent relationships if QApplication is available
        app = QApplication.instance()
        if app:
            logger.debug("Setting Qt parent relationships for managers")

            # SessionManager needs parent set after creation
            if hasattr(session_manager, 'setParent'):
                session_manager.setParent(app)  # type: ignore[attr-defined]  # Qt method not in protocol

            # Other managers should already have proper parents from their constructors
            # if they were created with parent=app, but let's ensure they have parents
            for manager in [extraction_manager, injection_manager, navigation_manager]:
                if manager and hasattr(manager, 'setParent') and manager.parent() != app:  # type: ignore[attr-defined]  # Qt method not in protocol
                    manager.setParent(app)  # type: ignore[attr-defined]  # Qt method not in protocol
        else:
            logger.warning("No QApplication instance found - managers will have no Qt parent")

        # Register cleanup with QApplication if available
        if app:
            app.aboutToQuit.connect(cleanup_managers)
            logger.debug("Registered cleanup with QApplication.aboutToQuit")

        logger.info("All managers initialized successfully via DI container")

    except Exception as e:
        logger.exception(f"Manager initialization failed: {e}")
        # Cleanup on failure
        container.clear()
        raise ManagerError(f"Failed to initialize managers: {e}") from e

def cleanup_managers() -> None:
    """
    Cleanup all managers by clearing the DI container.
    """
    logger.info("Cleaning up managers...")

    container = get_container()

    # Get all managers and clean them up if they have cleanup methods
    try:
        managers = []

        # Try to get each manager type and clean it up
        for protocol in [SessionManagerProtocol, ExtractionManagerProtocol,
                        InjectionManagerProtocol, NavigationManagerProtocol]:
            try:
                manager = container.get_optional(protocol)
                if manager:
                    managers.append(manager)
            except Exception as e:
                logger.debug(f"Could not get manager for cleanup: {e}")

        # Cleanup managers in reverse order
        for manager in reversed(managers):
            try:
                if hasattr(manager, 'cleanup'):
                    manager.cleanup()
                    logger.debug(f"Cleaned up {manager.__class__.__name__}")
            except Exception as e:
                logger.warning(f"Error cleaning up manager {manager.__class__.__name__}: {e}")

        # Clear container to release all references
        container.clear()

        logger.info("All managers cleaned up successfully")

    except Exception as e:
        logger.exception(f"Error during manager cleanup: {e}")
        # Still try to clear the container
        with contextlib.suppress(Exception):
            container.clear()

def reset_managers() -> None:
    """
    Reset managers (mainly for testing).
    """
    logger.debug("Resetting managers...")
    cleanup_managers()

def get_session_manager() -> SessionManagerProtocol:
    """
    Get the session manager instance from DI container.

    Returns:
        SessionManager instance

    Raises:
        ManagerError: If managers not initialized
    """
    try:
        return inject(SessionManagerProtocol)
    except ValueError as e:
        raise ManagerError("SessionManager not initialized. Call initialize_managers() first.") from e

def get_extraction_manager() -> ExtractionManagerProtocol:
    """
    Get the extraction manager instance from DI container.

    Returns:
        ExtractionManager instance

    Raises:
        ManagerError: If managers not initialized
    """
    try:
        return inject(ExtractionManagerProtocol)
    except ValueError as e:
        raise ManagerError("ExtractionManager not initialized. Call initialize_managers() first.") from e

def get_injection_manager() -> InjectionManagerProtocol:
    """
    Get the injection manager instance from DI container.

    Returns:
        InjectionManager instance

    Raises:
        ManagerError: If managers not initialized
    """
    try:
        return inject(InjectionManagerProtocol)
    except ValueError as e:
        raise ManagerError("InjectionManager not initialized. Call initialize_managers() first.") from e

def get_navigation_manager() -> NavigationManagerProtocol:
    """
    Get the navigation manager instance from DI container.

    Returns:
        NavigationManager instance

    Raises:
        ManagerError: If managers not initialized or NavigationManager not available
    """
    try:
        return inject(NavigationManagerProtocol)
    except ValueError as e:
        raise ManagerError("NavigationManager not initialized or not available. Call initialize_managers() first.") from e

def are_managers_initialized() -> bool:
    """
    Check if managers are initialized by checking if core managers are in container.

    Returns:
        True if managers are initialized, False otherwise
    """
    container = get_container()

    # Check that core managers are available
    required_protocols = [SessionManagerProtocol, ExtractionManagerProtocol, InjectionManagerProtocol]

    return all(container.has(protocol) for protocol in required_protocols)

def validate_manager_dependencies() -> bool:
    """
    Validate that all manager dependencies are properly resolved.

    Returns:
        True if all dependencies are satisfied, False otherwise
    """
    if not are_managers_initialized():
        logger.warning("Managers not initialized, cannot validate dependencies")
        return False

    logger.debug("Validating manager dependencies via DI container...")

    try:
        # Try to get each manager to ensure they can be created
        session_manager = get_session_manager()
        extraction_manager = get_extraction_manager()
        injection_manager = get_injection_manager()

        # Validate that managers are properly initialized
        if not all(hasattr(mgr, 'is_initialized') and mgr.is_initialized()  # type: ignore[attr-defined]  # Method not in protocol
                  for mgr in [session_manager, extraction_manager, injection_manager]):
            logger.error("Some managers are not properly initialized")
            return False

        # Try to get NavigationManager if it should be available
        try:
            navigation_manager = get_navigation_manager()
            if navigation_manager and hasattr(navigation_manager, 'is_initialized'):
                if not navigation_manager.is_initialized():  # type: ignore[attr-defined]  # Method not in protocol
                    logger.warning("NavigationManager is not properly initialized")
                    return False
        except ManagerError:
            # NavigationManager is optional
            logger.debug("NavigationManager not available, continuing validation")

        logger.debug("All manager dependencies validated successfully")
        return True

    except Exception as e:
        logger.exception(f"Manager dependency validation failed: {e}")
        return False

def get_container_stats() -> dict[str, Any]:
    """
    Get statistics about the DI container for debugging.

    Returns:
        Dictionary with container statistics
    """
    container = get_container()

    stats = {
        "initialized": are_managers_initialized(),
        "session_manager_available": container.has(SessionManagerProtocol),
        "extraction_manager_available": container.has(ExtractionManagerProtocol),
        "injection_manager_available": container.has(InjectionManagerProtocol),
        "navigation_manager_available": container.has(NavigationManagerProtocol),
    }

    return stats
