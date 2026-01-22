# pyright: recommended
"""
AppContext fixtures for SpritePal tests.

These fixtures provide clean test isolation via the AppContext pattern.

Key fixtures:
    - app_context: Function-scoped isolated AppContext (recommended default)
    - session_app_context: Session-scoped shared AppContext (for performance-sensitive tests)
    - _session_services: Session-scoped cached services (HALCompressor, etc.)
    - state_manager: Shortcut to get ApplicationStateManager from context
    - core_operations: Shortcut to get CoreOperationsManager from context

Fixture Selection:
    | Use Case                          | Fixture              |
    |-----------------------------------|----------------------|
    | Most tests (default)              | app_context          |
    | Performance-sensitive integration | session_app_context  |
    | Need state_manager only           | state_manager        |
    | Need core_operations only         | core_operations      |

Performance Optimization:
    The _session_services fixture caches expensive-to-create services
    (HALCompressor, SpriteConfigLoader, DefaultPaletteLoader) at session scope.
    The HALCompressor._tool_path_cache also caches binary paths across instances.
"""

from __future__ import annotations

from collections.abc import Generator
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pytest import TempPathFactory

    from core.app_context import AppContext
    from core.default_palette_loader import DefaultPaletteLoader
    from core.hal_compression import HALCompressor
    from core.managers.application_state_manager import ApplicationStateManager
    from core.managers.core_operations_manager import CoreOperationsManager
    from core.sprite_config_loader import SpriteConfigLoader


@dataclass
class SessionServices:
    """Container for session-scoped cached services."""

    hal_compressor: HALCompressor
    sprite_config_loader: SpriteConfigLoader
    default_palette_loader: DefaultPaletteLoader


@pytest.fixture(scope="session")
def _session_services() -> Generator[SessionServices, None, None]:
    """
    Session-scoped cached services for performance optimization.

    These stateless services are expensive to create (especially HALCompressor
    which searches for binaries on disk) but safe to share across tests.

    Yields:
        SessionServices containing cached service instances
    """
    from core.default_palette_loader import DefaultPaletteLoader
    from core.hal_compression import HALCompressor
    from core.sprite_config_loader import SpriteConfigLoader

    # Create services once per session
    services = SessionServices(
        hal_compressor=HALCompressor(),
        sprite_config_loader=SpriteConfigLoader(),
        default_palette_loader=DefaultPaletteLoader(),
    )
    yield services

    # No cleanup needed - these are stateless services


@pytest.fixture
def app_context(tmp_path: Path, _session_services: SessionServices) -> Generator[AppContext, None, None]:
    """
    Function-scoped isolated AppContext for clean test isolation.

    Creates a fresh AppContext with isolated settings for each test.
    Automatically cleans up after the test completes.

    Uses session-scoped cached services (_session_services) for performance.
    The HALCompressor, SpriteConfigLoader, and DefaultPaletteLoader are
    created once per test session and reused across all tests.

    If a session-scoped context already exists (e.g., session_app_context),
    this fixture temporarily suspends it and restores it after the test.
    This prevents function-scoped tests from destroying session-scoped contexts.

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
    from contextlib import ExitStack

    from PySide6.QtWidgets import QApplication

    from core.app_context import (
        create_app_context,
        is_context_initialized,
        reset_app_context,
        suspend_app_context,
    )

    # Ensure Qt app exists
    app = QApplication.instance()
    if app is None:
        app = QApplication([])

    # Check if a session context already exists
    session_context_exists = is_context_initialized()

    # Use ExitStack to manage the optional suspension context manager
    with ExitStack() as stack:
        if session_context_exists:
            # Suspend the session context - it will be restored when we exit
            stack.enter_context(suspend_app_context())

        # Create isolated settings
        settings_path = tmp_path / ".test_settings.json"

        # Create the context with cached services for performance
        context = create_app_context(
            app_name="TestApp",
            settings_path=settings_path,
            hal_compressor=_session_services.hal_compressor,
            sprite_config_loader=_session_services.sprite_config_loader,
            default_palette_loader=_session_services.default_palette_loader,
        )

        yield context

        # Cleanup the test context
        reset_app_context()

        # Process events to ensure cleanup completes
        if app:
            app.processEvents()

    # ExitStack automatically restores the session context if it was suspended


@pytest.fixture(scope="session")
def session_app_context(
    tmp_path_factory: TempPathFactory,
    _session_services: SessionServices,
) -> Generator[AppContext, None, None]:
    """
    Session-scoped shared AppContext for performance-sensitive tests.

    Creates an AppContext that persists across all tests in the session.
    Use this for integration tests where manager initialization cost matters
    (typically 100+ test suite with read-only operations).

    Uses session-scoped cached services (_session_services) for performance.
    The HALCompressor, SpriteConfigLoader, and DefaultPaletteLoader are
    shared with the function-scoped app_context fixture.

    IMPORTANT: Tests using this fixture should:
    - Be marked with @pytest.mark.shared_state_safe
    - Avoid mutating shared state (settings, cache, ROM data)
    - Be read-only or clean up after themselves explicitly

    PARALLEL SAFETY: xdist workers are isolated - each worker has its own
    session_app_context. State sharing only happens within a worker, not
    across workers. Workers run in separate processes.

    WHEN TO MIGRATE TO app_context:
    - Test fails intermittently in parallel runs (state mutation bug)
    - Test verifies initialization behavior
    - Test needs predictable starting state
    - State mutation is unavoidable

    MIGRATION PATTERN (if state bugs emerge):
        # Before (session scope - shared state):
        @pytest.mark.shared_state_safe
        def test_extraction(session_app_context):
            manager = session_app_context.core_operations_manager
            # ... test modifies manager state ...

        # After (function scope - isolated):
        def test_extraction(app_context):
            manager = app_context.core_operations_manager
            # ... test now has clean manager state ...

    Usage:
        @pytest.mark.shared_state_safe
        def test_integration(session_app_context):
            manager = session_app_context.core_operations_manager
            result = manager.validate_params(...)  # Read-only
            assert result is True
    """
    from PySide6.QtWidgets import QApplication

    from core.app_context import create_app_context, reset_app_context

    # Ensure Qt app exists
    app = QApplication.instance()
    if app is None:
        app = QApplication([])

    # Create isolated settings directory for the session
    settings_dir = tmp_path_factory.mktemp("session_settings")
    settings_path = settings_dir / ".test_settings.json"

    # Create the context with cached services for performance
    context = create_app_context(
        app_name="TestApp-Session",
        settings_path=settings_path,
        hal_compressor=_session_services.hal_compressor,
        sprite_config_loader=_session_services.sprite_config_loader,
        default_palette_loader=_session_services.default_palette_loader,
    )

    yield context

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
