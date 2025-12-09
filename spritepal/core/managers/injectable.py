"""
Injectable Base Classes for Dependency Injection

This module provides base classes for UI components that support dependency injection
while maintaining backward compatibility with the existing global singleton pattern.

These classes offer a clean migration path from global manager access to explicit
dependency injection.
"""
from __future__ import annotations

from typing import Any, Protocol, TypeVar

from PySide6.QtWidgets import QDialog, QWidget

from utils.logging_config import get_logger

from .context import ManagerContext, get_current_context
from .extraction_manager import ExtractionManager
from .injection_manager import InjectionManager
from .registry import get_extraction_manager, get_injection_manager, get_session_manager
from .session_manager import SessionManager

logger = get_logger(__name__)

T = TypeVar('T')

class ManagerProvider(Protocol):
    """
    Protocol for objects that can provide manager instances.

    This allows flexibility in how managers are provided - through contexts,
    dependency injection, global singletons, or other mechanisms.
    """

    def get_extraction_manager(self) -> ExtractionManager:
        """Get extraction manager instance."""
        ...

    def get_injection_manager(self) -> InjectionManager:
        """Get injection manager instance."""
        ...

    def get_session_manager(self) -> SessionManager:
        """Get session manager instance."""
        ...

class ContextualManagerProvider:
    """
    Manager provider that uses context-based dependency injection with fallback
    to global singletons for backward compatibility.

    This is the default provider used by injectable base classes.
    """

    def __init__(self, context: ManagerContext | None = None) -> None:
        """
        Initialize with optional manager context.

        Args:
            context: Manager context to use, or None to use current thread context
        """
        self._context = context

    def get_extraction_manager(self) -> ExtractionManager:
        """Get extraction manager with context fallback."""
        context = self._context or get_current_context()

        if context and context.has_manager("extraction"):
            return context.get_manager("extraction", ExtractionManager)

        # Fallback to global singleton
        logger.debug("No extraction manager in context, falling back to global")
        return get_extraction_manager()

    def get_injection_manager(self) -> InjectionManager:
        """Get injection manager with context fallback."""
        context = self._context or get_current_context()

        if context and context.has_manager("injection"):
            return context.get_manager("injection", InjectionManager)

        # Fallback to global singleton
        logger.debug("No injection manager in context, falling back to global")
        return get_injection_manager()

    def get_session_manager(self) -> SessionManager:
        """Get session manager with context fallback."""
        context = self._context or get_current_context()

        if context and context.has_manager("session"):
            return context.get_manager("session", SessionManager)

        # Fallback to global singleton
        logger.debug("No session manager in context, falling back to global")
        return get_session_manager()

class InjectableWidget(QWidget):
    """
    Base widget class that supports dependency injection.

    Provides managers through context-based injection with fallback to global
    singletons. This allows gradual migration from global access to injection.

    Usage:
        # Existing code continues to work
        widget = MyWidget()

        # New code can inject dependencies
        widget = MyWidget(manager_provider=custom_provider)

        # Tests can use contexts
        with manager_context({"injection": mock_manager}):
            widget = MyWidget()  # Will use mock_manager
    """

    def __init__(
        self,
        parent: QWidget | None = None,
        manager_provider: ManagerProvider | None = None,
        manager_context: ManagerContext | None = None
    ) -> None:
        """
        Initialize injectable widget.

        Args:
            parent: Parent widget
            manager_provider: Custom manager provider (overrides context)
            manager_context: Specific context to use (overrides current context)
        """
        super().__init__(parent)

        # Set up manager provider
        if manager_provider:
            self._manager_provider = manager_provider
            logger.debug(f"{self.__class__.__name__} using custom manager provider")
        else:
            self._manager_provider = ContextualManagerProvider(manager_context)
            if manager_context:
                logger.debug(f"{self.__class__.__name__} using explicit context '{manager_context._name}'")
            else:
                logger.debug(f"{self.__class__.__name__} using current thread context with global fallback")

    def get_extraction_manager(self) -> ExtractionManager:
        """Get extraction manager through dependency injection."""
        return self._manager_provider.get_extraction_manager()

    def get_injection_manager(self) -> InjectionManager:
        """Get injection manager through dependency injection."""
        return self._manager_provider.get_injection_manager()

    def get_session_manager(self) -> SessionManager:
        """Get session manager through dependency injection."""
        return self._manager_provider.get_session_manager()

class InjectableDialog(QDialog):
    """
    Base dialog class that supports dependency injection.

    Provides the same dependency injection capabilities as InjectableWidget
    for dialog windows.

    Usage:
        # Existing code continues to work
        dialog = MyDialog()

        # New code can inject dependencies
        dialog = MyDialog(manager_provider=custom_provider)

        # Tests can use contexts
        with manager_context({"injection": mock_manager}):
            dialog = MyDialog()  # Will use mock_manager
    """

    def __init__(
        self,
        parent: QWidget | None = None,
        manager_provider: ManagerProvider | None = None,
        manager_context: ManagerContext | None = None,
        **dialog_kwargs: Any
    ) -> None:
        """
        Initialize injectable dialog.

        Args:
            parent: Parent widget
            manager_provider: Custom manager provider (overrides context)
            manager_context: Specific context to use (overrides current context)
            **dialog_kwargs: Additional arguments passed to QDialog
        """
        super().__init__(parent, **dialog_kwargs)

        # Set up manager provider
        if manager_provider:
            self._manager_provider = manager_provider
            logger.debug(f"{self.__class__.__name__} using custom manager provider")
        else:
            self._manager_provider = ContextualManagerProvider(manager_context)
            if manager_context:
                logger.debug(f"{self.__class__.__name__} using explicit context '{manager_context._name}'")
            else:
                logger.debug(f"{self.__class__.__name__} using current thread context with global fallback")

    def get_extraction_manager(self) -> ExtractionManager:
        """Get extraction manager through dependency injection."""
        return self._manager_provider.get_extraction_manager()

    def get_injection_manager(self) -> InjectionManager:
        """Get injection manager through dependency injection."""
        return self._manager_provider.get_injection_manager()

    def get_session_manager(self) -> SessionManager:
        """Get session manager through dependency injection."""
        return self._manager_provider.get_session_manager()

class DirectManagerProvider:
    """
    Manager provider that uses directly injected manager instances.

    This is useful for explicit dependency injection where managers are
    passed directly rather than through contexts.
    """

    def __init__(
        self,
        extraction_manager: ExtractionManager | None = None,
        injection_manager: InjectionManager | None = None,
        session_manager: SessionManager | None = None
    ) -> None:
        """
        Initialize with specific manager instances.

        Args:
            extraction_manager: Extraction manager instance
            injection_manager: Injection manager instance
            session_manager: Session manager instance
        """
        self._extraction_manager = extraction_manager
        self._injection_manager = injection_manager
        self._session_manager = session_manager

    def get_extraction_manager(self) -> ExtractionManager:
        """Get extraction manager."""
        if self._extraction_manager is None:
            logger.debug("No extraction manager injected, falling back to global")
            return get_extraction_manager()
        return self._extraction_manager

    def get_injection_manager(self) -> InjectionManager:
        """Get injection manager."""
        if self._injection_manager is None:
            logger.debug("No injection manager injected, falling back to global")
            return get_injection_manager()
        return self._injection_manager

    def get_session_manager(self) -> SessionManager:
        """Get session manager."""
        if self._session_manager is None:
            logger.debug("No session manager injected, falling back to global")
            return get_session_manager()
        return self._session_manager

def create_direct_provider(
    extraction_manager: ExtractionManager | None = None,
    injection_manager: InjectionManager | None = None,
    session_manager: SessionManager | None = None
) -> DirectManagerProvider:
    """
    Factory function for creating a direct manager provider.

    Args:
        extraction_manager: Extraction manager instance
        injection_manager: Injection manager instance
        session_manager: Session manager instance

    Returns:
        DirectManagerProvider instance
    """
    return DirectManagerProvider(
        extraction_manager=extraction_manager,
        injection_manager=injection_manager,
        session_manager=session_manager
    )

class InjectionMixin:
    """
    Mixin class that adds dependency injection capabilities to existing classes.

    This is useful for gradually migrating existing widgets/dialogs without
    changing their inheritance hierarchy.

    Usage:
        class MyExistingWidget(QWidget, InjectionMixin):
            def __init__(self, parent=None):
                QWidget.__init__(self, parent)
                InjectionMixin.__init__(self)

                # Now you can use self.get_injection_manager()
                self.injection_manager = self.get_injection_manager()
    """

    def __init__(
        self,
        manager_provider: ManagerProvider | None = None,
        manager_context: ManagerContext | None = None
    ) -> None:
        """
        Initialize injection mixin.

        Args:
            manager_provider: Custom manager provider
            manager_context: Specific context to use
        """
        if manager_provider:
            self._manager_provider = manager_provider
        else:
            self._manager_provider = ContextualManagerProvider(manager_context)

    def get_extraction_manager(self) -> ExtractionManager:
        """Get extraction manager through dependency injection."""
        return self._manager_provider.get_extraction_manager()

    def get_injection_manager(self) -> InjectionManager:
        """Get injection manager through dependency injection."""
        return self._manager_provider.get_injection_manager()

    def get_session_manager(self) -> SessionManager:
        """Get session manager through dependency injection."""
        return self._manager_provider.get_session_manager()

# Convenience type aliases for type hints
InjectableQWidget = InjectableWidget
InjectableQDialog = InjectableDialog
