"""
Manager factory for creating manager instances with proper Qt parent management.

This factory provides a clean way to create manager instances while respecting
Qt's object lifecycle and enabling both singleton and per-worker patterns.

.. deprecated::
    The factory pattern for creating ExtractionManager and InjectionManager
    is deprecated. Use dependency injection instead::

        from core.di_container import inject
        from core.protocols.manager_protocols import (
            ExtractionManagerProtocol,
            InjectionManagerProtocol,
        )

        extraction_mgr = inject(ExtractionManagerProtocol)
        injection_mgr = inject(InjectionManagerProtocol)
"""
from __future__ import annotations

import warnings
from typing import TYPE_CHECKING, Protocol

from PySide6.QtCore import QObject
from PySide6.QtWidgets import QApplication

from utils.logging_config import get_logger

from .core_operations_manager import CoreOperationsManager

if TYPE_CHECKING:
    import logging

logger = get_logger(__name__)

class ManagerFactory(Protocol):
    """Protocol for manager factory implementations."""

    def create_extraction_manager(self, parent: QObject | None = None) -> CoreOperationsManager:
        """Create an ExtractionManager instance (returns CoreOperationsManager)."""
        ...

    def create_injection_manager(self, parent: QObject | None = None) -> CoreOperationsManager:
        """Create an InjectionManager instance (returns CoreOperationsManager)."""
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

    def create_extraction_manager(self, parent: QObject | None = None) -> CoreOperationsManager:
        """
        Create a CoreOperationsManager instance with proper Qt parent.

        .. deprecated::
            Use ``inject(ExtractionManagerProtocol)`` from ``core.di_container`` instead.

        Args:
            parent: Optional Qt parent object. If None, uses factory's default strategy.

        Returns:
            New CoreOperationsManager instance
        """
        warnings.warn(
            "StandardManagerFactory.create_extraction_manager() is deprecated. "
            "Use inject(ExtractionManagerProtocol) from core.di_container instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        qt_parent = self._get_default_parent(parent)
        manager = CoreOperationsManager(parent=qt_parent)

        self._logger.debug(f"Created CoreOperationsManager with parent: {qt_parent}")
        return manager

    def create_injection_manager(self, parent: QObject | None = None) -> CoreOperationsManager:
        """
        Create a CoreOperationsManager instance with proper Qt parent.

        .. deprecated::
            Use ``inject(InjectionManagerProtocol)`` from ``core.di_container`` instead.

        Args:
            parent: Optional Qt parent object. If None, uses factory's default strategy.

        Returns:
            New CoreOperationsManager instance
        """
        warnings.warn(
            "StandardManagerFactory.create_injection_manager() is deprecated. "
            "Use inject(InjectionManagerProtocol) from core.di_container instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        qt_parent = self._get_default_parent(parent)
        manager = CoreOperationsManager(parent=qt_parent)

        self._logger.debug(f"Created CoreOperationsManager with parent: {qt_parent}")
        return manager

    def create_operations_manager(self, parent: QObject | None = None) -> CoreOperationsManager:
        """
        Create a CoreOperationsManager instance for worker-owned patterns.

        This method is intended for workers that need their own manager instance
        (not the shared singleton from DI). Unlike the deprecated create_*_manager()
        methods, this does not emit a deprecation warning since worker-owned patterns
        are a legitimate use case.

        Args:
            parent: Optional Qt parent object. If None, uses factory's default strategy.

        Returns:
            New CoreOperationsManager instance
        """
        qt_parent = self._get_default_parent(parent)
        manager = CoreOperationsManager(parent=qt_parent)

        self._logger.debug(f"Created CoreOperationsManager for worker with parent: {qt_parent}")
        return manager


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
        def create_extraction_manager(self, parent: QObject | None = None) -> CoreOperationsManager:
            return factory.create_operations_manager(parent or worker)

        def create_injection_manager(self, parent: QObject | None = None) -> CoreOperationsManager:
            return factory.create_operations_manager(parent or worker)

    return WorkerOwnedFactory()
