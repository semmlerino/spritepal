# pyright: recommended
"""
Simplified AppContext fixtures for SpritePal tests.

These fixtures use the new AppContext pattern for simpler test isolation.
They replace the legacy session_managers/isolated_managers fixtures in core_fixtures.py.

Key fixtures:
    - app_context: Function-scoped isolated AppContext (recommended default)
    - session_app_context: Session-scoped shared AppContext (for performance-sensitive tests)
    - state_manager: Shortcut to get ApplicationStateManager from context
    - core_operations: Shortcut to get CoreOperationsManager from context

Fixture Selection:
    | Use Case                          | Fixture              |
    |-----------------------------------|----------------------|
    | Most tests (default)              | app_context          |
    | Performance-sensitive integration | session_app_context  |
    | Need state_manager only           | state_manager        |
    | Need core_operations only         | core_operations      |

Migration Guide:
    Replace: isolated_managers -> app_context
    Replace: session_managers -> session_app_context
    Replace: get_app_context().application_state_manager -> state_manager fixture
    Replace: get_app_context().core_operations_manager -> core_operations fixture
"""

from __future__ import annotations

import contextlib
import tempfile
from collections.abc import Generator, Iterator
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pytest import TempPathFactory

    from core.app_context import AppContext
    from core.managers.application_state_manager import ApplicationStateManager
    from core.managers.core_operations_manager import CoreOperationsManager


@pytest.fixture
def app_context(tmp_path: Path) -> Generator[AppContext, None, None]:
    """
    Function-scoped isolated AppContext for clean test isolation.

    Creates a fresh AppContext with isolated settings for each test.
    Automatically cleans up after the test completes.

    This is the recommended fixture for most tests. It provides:
    - Complete isolation between tests
    - No global state pollution
    - Explicit dependency access via context attributes

    Usage:
        def test_something(app_context):
            manager = app_context.core_operations_manager
            # ... test code ...

        def test_with_state(app_context):
            state = app_context.application_state_manager
            state.update_settings(some_key="value")
            # ... test code ...
    """
    from PySide6.QtWidgets import QApplication

    from core.app_context import create_app_context, reset_app_context
    from tests.fixtures.core_fixtures import _session_state

    # Ensure Qt app exists
    app = QApplication.instance()
    if app is None:
        app = QApplication([])

    # Remember if session context was active
    session_active = _session_state.is_initialized
    session_settings_path = _session_state.settings_path

    # Create isolated settings
    settings_path = tmp_path / ".test_settings.json"

    # Create the context - let create_app_context handle ConfigurationService creation
    context = create_app_context(
        app_name="TestApp",
        settings_path=settings_path,
    )

    yield context

    # Cleanup
    reset_app_context()

    # Restore session context if one was active
    if session_active and session_settings_path:
        create_app_context(
            app_name="TestApp-Session",
            settings_path=session_settings_path,
        )

    # Process events to ensure cleanup completes
    if app:
        app.processEvents()


@pytest.fixture(scope="session")
def session_app_context(
    tmp_path_factory: TempPathFactory,
) -> Generator[AppContext, None, None]:
    """
    Session-scoped shared AppContext for performance-sensitive tests.

    Creates an AppContext that persists across all tests in the session.
    Use this for integration tests where manager initialization cost matters.

    IMPORTANT: Tests using this fixture should:
    - Be marked with @pytest.mark.shared_state_safe
    - Avoid mutating shared state
    - Be read-only or clean up after themselves

    Usage:
        @pytest.mark.shared_state_safe
        def test_integration(session_app_context):
            manager = session_app_context.core_operations_manager
            result = manager.read_only_operation()
            # ... test code ...
    """
    from PySide6.QtWidgets import QApplication

    from core.app_context import create_app_context, reset_app_context
    from tests.fixtures.core_fixtures import _session_state

    # Ensure Qt app exists
    app = QApplication.instance()
    if app is None:
        app = QApplication([])

    # Create isolated settings directory for the session
    settings_dir = tmp_path_factory.mktemp("session_settings")
    settings_path = settings_dir / ".test_settings.json"

    # Create the context - let create_app_context handle ConfigurationService creation
    context = create_app_context(
        app_name="TestApp-Session",
        settings_path=settings_path,
    )

    # Store in session state so isolated_managers can detect and restore us
    _session_state.settings_path = settings_path
    _session_state.is_initialized = True

    yield context

    # Reset session state
    _session_state.is_initialized = False

    # Cleanup at end of session
    reset_app_context()

    # Process events to ensure cleanup completes
    if app:
        app.processEvents()


@pytest.fixture
def state_manager(app_context: AppContext) -> ApplicationStateManager:
    """
    Get the ApplicationStateManager from the test context.

    This is a convenience fixture for direct manager access.

    Usage:
        def test_settings(state_manager):
            state_manager.update_settings(key="value")
            assert state_manager.settings.key == "value"
    """
    return app_context.application_state_manager


@pytest.fixture
def core_operations(app_context: AppContext) -> CoreOperationsManager:
    """
    Get the CoreOperationsManager from the test context.

    This is a convenience fixture for direct manager access.

    Usage:
        def test_extraction(core_operations, tmp_path):
            result = core_operations.extract_from_vram(...)
            assert result is not None
    """
    return app_context.core_operations_manager


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Compatibility shims for legacy patterns
# These wrap the new app_context pattern to support existing test code.
# New tests should use app_context directly.
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class _ManagerContextWrapper:
    """
    Wrapper that provides manager_context-style API using AppContext.

    This is a compatibility shim to allow existing tests using manager_context
    to work with the new app_context infrastructure.
    """

    def __init__(self, context: AppContext) -> None:
        self._context = context

    def get_extraction_manager(self) -> CoreOperationsManager:
        """Get the extraction manager (CoreOperationsManager)."""
        return self._context.core_operations_manager

    def get_injection_manager(self) -> CoreOperationsManager:
        """Get the injection manager (CoreOperationsManager)."""
        return self._context.core_operations_manager

    def get_session_manager(self) -> ApplicationStateManager:
        """Get the session manager (ApplicationStateManager)."""
        return self._context.application_state_manager

    def get_manager(self, manager_type: str) -> CoreOperationsManager | ApplicationStateManager:
        """Get a manager by type name (legacy API compatibility).

        Args:
            manager_type: One of "extraction", "injection", or "session"

        Returns:
            The requested manager instance
        """
        if manager_type in ("extraction", "injection"):
            return self._context.core_operations_manager
        elif manager_type == "session":
            return self._context.application_state_manager
        else:
            raise ValueError(f"Unknown manager type: {manager_type}")


@pytest.fixture
def manager_context_wrapper(app_context: AppContext) -> _ManagerContextWrapper:
    """
    Compatibility fixture providing manager_context-style API.

    This wraps app_context with the legacy manager_context interface.
    Use this when migrating tests that used manager_context.

    Usage:
        def test_something(manager_context_wrapper):
            mgr = manager_context_wrapper.get_extraction_manager()
            # ... test code ...
    """
    return _ManagerContextWrapper(app_context)


@contextlib.contextmanager
def manager_context(*_manager_types: str) -> Iterator[_ManagerContextWrapper]:
    """
    Compatibility context manager for legacy manager_context usage.

    This is a drop-in replacement for the deprecated manager_context from
    tests.infrastructure.manager_test_context. It uses the new app_context
    infrastructure internally.

    Args:
        *_manager_types: Ignored. Legacy parameter for manager types.
                        All managers are now always available via AppContext.

    Legacy usage (for backward compatibility):
        with manager_context("extraction") as ctx:
            manager = ctx.get_extraction_manager()
            # ... test code ...

    Preferred (use app_context fixture instead):
        def test_something(app_context):
            manager = app_context.core_operations_manager
            # ... test code ...

    Note:
        If a context already exists (e.g., from session_managers fixture),
        this function will reuse it and NOT reset it on exit. This prevents
        conflicts when tests use both session_managers and manager_context_factory.
    """
    from PySide6.QtWidgets import QApplication

    from core.app_context import (
        create_app_context,
        get_app_context_optional,
        reset_app_context,
    )

    # Check if a context already exists (e.g., from session_managers)
    existing_context = get_app_context_optional()
    if existing_context is not None:
        # Reuse existing context - do NOT reset on exit
        yield _ManagerContextWrapper(existing_context)
        return

    # Ensure Qt app exists
    app = QApplication.instance()
    if app is None:
        app = QApplication([])

    # Create isolated settings
    with tempfile.TemporaryDirectory(prefix="manager_context_") as tmp_dir:
        settings_path = Path(tmp_dir) / ".test_settings.json"

        # Create the context - let create_app_context handle ConfigurationService creation
        context = create_app_context(
            app_name="TestApp",
            settings_path=settings_path,
        )

        try:
            yield _ManagerContextWrapper(context)
        finally:
            reset_app_context()
            if app:
                app.processEvents()
