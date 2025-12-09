"""
Manager factory for creating manager instances with proper Qt parent management.

This factory provides a clean way to create manager instances while respecting
Qt's object lifecycle and enabling both singleton and per-worker patterns.
"""
from __future__ import annotations

import threading
from typing import TYPE_CHECKING, Protocol

from PySide6.QtCore import QObject
from PySide6.QtWidgets import QApplication

from utils.logging_config import get_logger

from .extraction_manager import ExtractionManager
from .injection_manager import InjectionManager

if TYPE_CHECKING:
    import logging

logger = get_logger(__name__)

class ManagerFactory(Protocol):
    """Protocol for manager factory implementations."""

    def create_extraction_manager(self, parent: QObject | None = None) -> ExtractionManager:
        """Create an ExtractionManager instance."""
        ...

    def create_injection_manager(self, parent: QObject | None = None) -> InjectionManager:
        """Create an InjectionManager instance."""
        ...

class StandardManagerFactory:
    """
    Standard manager factory that creates new instances with proper Qt parents.

    This factory ensures all managers have proper Qt parent relationships,
    preventing lifecycle issues while allowing flexible usage patterns.
    """

    def __init__(self, default_parent_strategy: str = "application") -> None:
        """
        Initialize the factory.

        Args:
            default_parent_strategy: Strategy for default parent selection:
                - "application": Use QApplication.instance() as parent
                - "none": No default parent (caller must provide)
                - "worker": Use the calling worker as parent (for worker-owned pattern)
        """
        self.default_parent_strategy: str = default_parent_strategy
        self._logger: logging.Logger = get_logger(f"{__name__}.StandardManagerFactory")

    def _get_default_parent(self, requested_parent: QObject | None) -> QObject | None:
        """
        Get the appropriate parent based on strategy and request.

        Args:
            requested_parent: Explicitly requested parent (takes priority)

        Returns:
            QObject to use as parent, or None
        """
        # Explicit parent always takes priority
        if requested_parent is not None:
            self._logger.debug(f"Using explicit parent: {requested_parent}")
            return requested_parent

        # Apply default strategy
        if self.default_parent_strategy == "application":
            app = QApplication.instance()
            if app:
                self._logger.debug("Using QApplication as default parent")
                return app
            self._logger.warning("No QApplication instance found, using no parent")
            return None

        if self.default_parent_strategy == "none":
            self._logger.debug("Using no parent (explicit strategy)")
            return None

        if self.default_parent_strategy == "worker":
            # This would be set by worker context, for now fall back to None
            self._logger.debug("Worker parent strategy requested but no worker context available")
            return None

        self._logger.warning(f"Unknown parent strategy: {self.default_parent_strategy}")
        return None

    def create_extraction_manager(self, parent: QObject | None = None) -> ExtractionManager:
        """
        Create an ExtractionManager instance with proper Qt parent.

        Args:
            parent: Optional Qt parent object. If None, uses factory's default strategy.

        Returns:
            New ExtractionManager instance
        """
        qt_parent = self._get_default_parent(parent)
        manager = ExtractionManager(parent=qt_parent)

        self._logger.debug(f"Created ExtractionManager with parent: {qt_parent}")
        return manager

    def create_injection_manager(self, parent: QObject | None = None) -> InjectionManager:
        """
        Create an InjectionManager instance with proper Qt parent.

        Args:
            parent: Optional Qt parent object. If None, uses factory's default strategy.

        Returns:
            New InjectionManager instance
        """
        qt_parent = self._get_default_parent(parent)
        manager = InjectionManager(parent=qt_parent)

        self._logger.debug(f"Created InjectionManager with parent: {qt_parent}")
        return manager

class SingletonManagerFactory:
    """
    Manager factory that returns singleton instances from the global registry.

    This provides backward compatibility with the existing global registry pattern
    while maintaining the factory interface.
    """

    def __init__(self) -> None:
        self._logger: logging.Logger = get_logger(f"{__name__}.SingletonManagerFactory")

    def create_extraction_manager(self, parent: QObject | None = None) -> ExtractionManager:
        """
        Get the singleton ExtractionManager from global registry.

        Args:
            parent: Ignored for singleton pattern

        Returns:
            Singleton ExtractionManager instance
        """
        # Delayed import to avoid circular dependency:
        # factory -> managers -> factory
        from . import get_extraction_manager

        if parent is not None:
            self._logger.warning(
                "Parent parameter ignored for singleton factory - "
                "use StandardManagerFactory for per-instance parents"
            )

        manager = get_extraction_manager()
        self._logger.debug("Returned singleton ExtractionManager")
        return manager

    def create_injection_manager(self, parent: QObject | None = None) -> InjectionManager:
        """
        Get the singleton InjectionManager from global registry.

        Args:
            parent: Ignored for singleton pattern

        Returns:
            Singleton InjectionManager instance
        """
        # Delayed import to avoid circular dependency:
        # factory -> managers -> factory
        from . import get_injection_manager

        if parent is not None:
            self._logger.warning(
                "Parent parameter ignored for singleton factory - "
                "use StandardManagerFactory for per-instance parents"
            )

        manager = get_injection_manager()
        self._logger.debug("Returned singleton InjectionManager")
        return manager

class _DefaultFactoryHolder:
    """Holds the default factory instance without using global keyword."""
    _instance: ManagerFactory | None = None
    _lock = threading.Lock()

    @classmethod
    def get(cls) -> ManagerFactory:
        """Get the default factory instance."""
        # Fast path - check without lock
        if cls._instance is not None:
            return cls._instance

        # Slow path - create with lock
        with cls._lock:
            # Double-check pattern
            if cls._instance is None:
                # Default to singleton pattern for backward compatibility
                cls._instance = SingletonManagerFactory()
                logger.debug("Created default SingletonManagerFactory")

            return cls._instance

    @classmethod
    def set(cls, factory: ManagerFactory) -> None:
        """Set the default factory instance."""
        with cls._lock:
            cls._instance = factory
            logger.info(f"Set default factory to: {type(factory).__name__}")

def get_default_factory() -> ManagerFactory:
    """
    Get the default manager factory instance.

    Returns:
        Default ManagerFactory instance
    """
    return _DefaultFactoryHolder.get()

def set_default_factory(factory: ManagerFactory) -> None:
    """
    Set the default manager factory instance.

    This allows switching between singleton and per-instance patterns globally.

    Args:
        factory: ManagerFactory implementation to use as default
    """
    _DefaultFactoryHolder.set(factory)

def create_per_worker_factory(worker: QObject) -> ManagerFactory:
    """
    Create a factory configured for worker-owned managers.

    Args:
        worker: Worker that will own the created managers

    Returns:
        Factory configured to create managers with worker as parent
    """
    factory = StandardManagerFactory(default_parent_strategy="none")

    # Create a custom factory that uses the worker as default parent
    class WorkerOwnedFactory:
        def create_extraction_manager(self, parent: QObject | None = None) -> ExtractionManager:
            return factory.create_extraction_manager(parent or worker)

        def create_injection_manager(self, parent: QObject | None = None) -> InjectionManager:
            return factory.create_injection_manager(parent or worker)

    return WorkerOwnedFactory()
