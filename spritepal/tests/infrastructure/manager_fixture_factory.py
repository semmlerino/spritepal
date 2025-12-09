"""
RealManagerFixtureFactory: Create real manager instances for testing.

This factory creates real manager instances using the worker-owned pattern,
replacing problematic manager mocking with actual implementations that
can catch architectural bugs.
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Any

# Add parent directory to Python path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from PySide6.QtCore import QObject

if TYPE_CHECKING:
    from core.managers import ExtractionManager, InjectionManager, SessionManager

from core.managers.factory import ManagerFactory, StandardManagerFactory

from .qt_application_factory import ApplicationFactory


class RealManagerFixtureFactory:
    """
    Factory for creating real manager instances for testing.

    This factory creates actual manager instances with proper Qt parent
    relationships, using the worker-owned pattern to ensure thread safety
    and proper lifecycle management.

    Key features:
    - Creates real managers instead of mocks
    - Ensures proper Qt parent/child relationships
    - Uses worker-owned pattern for thread isolation
    - Provides cleanup mechanisms
    - Supports both singleton and isolated patterns
    """

    def __init__(self, qt_parent: QObject | None = None, manager_factory: ManagerFactory | None = None):
        """
        Initialize the real manager fixture factory.

        Args:
            qt_parent: Qt parent object for managers (uses QApplication if None)
            manager_factory: Manager factory to use (creates default if None)
        """
        # Ensure Qt application exists
        self.qt_app = ApplicationFactory.get_application()

        # Set up Qt parent
        self.qt_parent = qt_parent or self.qt_app

        # Set up manager factory
        self.manager_factory = manager_factory or StandardManagerFactory(
            default_parent_strategy="explicit"
        )

        # Track created managers for cleanup
        self._created_managers: list[QObject] = []
        self._temp_dirs: list[str] = []

    def create_extraction_manager(self, isolated: bool = True) -> ExtractionManager:
        """
        Create a real ExtractionManager instance.

        Args:
            isolated: If True, creates an isolated manager (worker-owned pattern)
                     If False, uses singleton pattern

        Returns:
            Real ExtractionManager instance with proper Qt parent
        """
        if isolated:
            # Create isolated manager with proper Qt parent
            manager = self.manager_factory.create_extraction_manager(parent=self.qt_parent)
        else:
            # Use singleton manager
            from core.managers import get_extraction_manager, initialize_managers
            if not self._managers_initialized():
                initialize_managers()
            manager = get_extraction_manager()

        self._created_managers.append(manager)
        return manager

    def create_injection_manager(self, isolated: bool = True) -> InjectionManager:
        """
        Create a real InjectionManager instance.

        Args:
            isolated: If True, creates an isolated manager (worker-owned pattern)
                     If False, uses singleton pattern

        Returns:
            Real InjectionManager instance with proper Qt parent
        """
        if isolated:
            # Create isolated manager with proper Qt parent
            manager = self.manager_factory.create_injection_manager(parent=self.qt_parent)
        else:
            # Use singleton manager
            from core.managers import (
                get_injection_manager,
                initialize_managers,
            )
            if not self._managers_initialized():
                initialize_managers()
            manager = get_injection_manager()

        self._created_managers.append(manager)
        return manager

    def create_session_manager(self, isolated: bool = True, temp_settings: bool = True) -> SessionManager:
        """
        Create a real SessionManager instance.

        Args:
            isolated: If True, creates an isolated manager
                     If False, uses singleton pattern
            temp_settings: If True, uses temporary settings file

        Returns:
            Real SessionManager instance with proper configuration
        """
        settings_path = None
        if temp_settings:
            # Create temporary settings file
            temp_dir = tempfile.mkdtemp()
            self._temp_dirs.append(temp_dir)
            settings_path = Path(temp_dir) / "test_settings.json"

        if isolated:
            # Create isolated session manager
            from core.managers.session_manager import SessionManager
            manager = SessionManager(settings_path=settings_path)
        else:
            # Use singleton manager
            from core.managers import (
                get_session_manager,
                initialize_managers,
            )
            if not self._managers_initialized():
                initialize_managers()
            manager = get_session_manager()

        self._created_managers.append(manager)
        return manager

    def create_manager_set(self, isolated: bool = True) -> dict[str, Any]:
        """
        Create a complete set of real managers for comprehensive testing.

        Args:
            isolated: If True, creates isolated managers (recommended)
                     If False, uses singleton managers

        Returns:
            Dictionary containing all manager instances
        """
        return {
            "extraction": self.create_extraction_manager(isolated),
            "injection": self.create_injection_manager(isolated),
            "session": self.create_session_manager(isolated),
        }

    def cleanup(self) -> None:
        """Clean up all created managers and temporary resources."""
        # Clean up managers
        for manager in self._created_managers:
            try:
                if hasattr(manager, "cleanup"):
                    manager.cleanup()
                # Remove from Qt parent/child hierarchy
                manager.setParent(None)
            except Exception:
                # Ignore cleanup errors
                pass

        self._created_managers.clear()

        # Clean up temporary directories
        import shutil
        for temp_dir in self._temp_dirs:
            try:
                shutil.rmtree(temp_dir)
            except Exception:
                # Ignore cleanup errors
                pass

        self._temp_dirs.clear()

    def _managers_initialized(self) -> bool:
        """Check if singleton managers are initialized."""
        try:
            from core.managers import are_managers_initialized
            return are_managers_initialized()
        except ImportError:
            return False

    def validate_manager_state(self, manager: QObject) -> dict[str, Any]:
        """
        Validate manager state for debugging test issues.

        Args:
            manager: Manager instance to validate

        Returns:
            Dictionary with manager state information
        """
        return {
            "manager_type": type(manager).__name__,
            "parent": type(manager.parent()).__name__ if manager.parent() else None,
            "parent_is_qapp": manager.parent() is self.qt_app,
            "is_initialized": getattr(manager, "is_initialized", lambda: True)(),
            "qt_object_valid": not hasattr(manager, "isValid") or manager.isValid(),
        }

class WorkerOwnedManagerFixture:
    """
    Specialized fixture for worker-owned managers.

    This provides a pattern for tests that need managers with complete
    isolation and proper Qt parent relationships, eliminating cross-thread
    and lifecycle issues.
    """

    def __init__(self, worker_parent: QObject | None = None):
        """
        Initialize worker-owned manager fixture.

        Args:
            worker_parent: Parent object that will own the managers
        """
        self.qt_app = ApplicationFactory.get_application()
        self.worker_parent = worker_parent or self.qt_app
        self.factory = RealManagerFixtureFactory(qt_parent=self.worker_parent)

    def create_isolated_extraction_context(self) -> dict[str, Any]:
        """
        Create an isolated extraction context with real managers.

        Returns:
            Dictionary containing extraction manager and supporting components
        """
        manager = self.factory.create_extraction_manager(isolated=True)

        return {
            "manager": manager,
            "parent": self.worker_parent,
            "factory": self.factory,
            "qt_app": self.qt_app,
        }

    def create_isolated_injection_context(self) -> dict[str, Any]:
        """
        Create an isolated injection context with real managers.

        Returns:
            Dictionary containing injection manager and supporting components
        """
        manager = self.factory.create_injection_manager(isolated=True)

        return {
            "manager": manager,
            "parent": self.worker_parent,
            "factory": self.factory,
            "qt_app": self.qt_app,
        }

    def cleanup(self) -> None:
        """Clean up the worker-owned fixture."""
        self.factory.cleanup()

# Convenience functions for common testing patterns
def create_real_extraction_manager(qt_parent: QObject | None = None) -> ExtractionManager:
    """Create a real extraction manager for testing."""
    factory = RealManagerFixtureFactory(qt_parent)
    return factory.create_extraction_manager(isolated=True)

def create_real_injection_manager(qt_parent: QObject | None = None) -> InjectionManager:
    """Create a real injection manager for testing."""
    factory = RealManagerFixtureFactory(qt_parent)
    return factory.create_injection_manager(isolated=True)

def create_real_session_manager(qt_parent: QObject | None = None) -> SessionManager:
    """Create a real session manager for testing."""
    factory = RealManagerFixtureFactory(qt_parent)
    return factory.create_session_manager(isolated=True)

def create_worker_owned_fixture(worker_parent: QObject | None = None) -> WorkerOwnedManagerFixture:
    """Create a worker-owned manager fixture."""
    return WorkerOwnedManagerFixture(worker_parent)
