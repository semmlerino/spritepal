# pyright: recommended
# pyright: reportPrivateUsage=false
"""
Core manager fixtures for SpritePal tests.

This module provides fixtures for manager initialization, state management,
and dependency injection testing.

Key fixtures:
    - app_context: Function-scoped isolated managers (preferred)
    - session_app_context: Session-scoped shared managers (requires marker)
    - clean_registry_state: Ensure registry starts uninitialized (for lifecycle tests)

Fixture Selection Guide:
    | Need                        | Use                    | Notes                     |
    |-----------------------------|------------------------|---------------------------|
    | Full isolation (default)    | app_context            | Function-scoped, auto-cleanup |
    | Shared state for perf       | session_app_context    | Requires @pytest.mark.shared_state_safe |
    | Test initialization itself  | clean_registry_state   | For lifecycle tests       |

Escape hatches:
    - @pytest.mark.allows_registry_state: Skip pollution detection
    - @pytest.mark.no_manager_setup: Skip manager initialization
"""

from __future__ import annotations

import contextlib
import logging
import os
from collections.abc import Callable, Generator
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

if TYPE_CHECKING:
    from pytest import FixtureRequest, TempPathFactory

    from core.app_context import AppContext
    from core.managers.application_state_manager import ApplicationStateManager
    from core.managers.core_operations_manager import CoreOperationsManager
    from core.services.rom_cache import ROMCache
    from ui.main_window import MainWindow
    from tests.infrastructure.real_component_factory import RealComponentFactory

# Import Qt fixtures for is_headless helper
from tests.fixtures.qt_fixtures import is_headless

# Module logger for fixture diagnostics
_logger = logging.getLogger(__name__)


def reset_all_singletons() -> None:
    """Reset all singleton classes for test isolation.

    This is the single source of truth for resetting test state.
    Call this instead of resetting individual singletons scattered across tests.

    Resets:
        - Manager state (DI container, initialization flags)
        - HALProcessPool (real HAL compression)
        - MockHALProcessPool (mock HAL compression)
        - DataRepository (test data cleanup)
        - WorkerManager (thread registry)

    Note: PreviewGenerator and ConfigurationService are now handled by AppContext
    cleanup (via reset_app_context in app_context_fixtures.py).
    Dialog cleanup is per-instance, handled by Qt parent-child hierarchy.

    Failures are logged but don't stop the reset process.
    Some resets are expected to fail in certain contexts (e.g., MockHALProcessPool
    not imported in non-mock tests).
    """
    import logging

    logger = logging.getLogger(__name__)

    def _try_reset(name: str, action: Callable[[], None]) -> None:
        """Attempt a reset action with failure logging."""
        try:
            action()
        except Exception as e:
            logger.debug("Failed to reset %s: %s", name, e)

    # Reset manager state
    def reset_manager_state() -> None:
        from core.managers import reset_for_tests

        reset_for_tests()

    _try_reset("managers", reset_manager_state)

    # Reset real HAL process pool
    def reset_hal_pool() -> None:
        from core.hal_compression import HALProcessPool

        HALProcessPool.reset_for_tests()

    _try_reset("HALProcessPool", reset_hal_pool)

    # Reset mock HAL process pool
    def reset_mock_hal() -> None:
        from tests.infrastructure.mock_hal import MockHALProcessPool

        MockHALProcessPool.reset_singleton()

    _try_reset("MockHALProcessPool", reset_mock_hal)

    # Clean up DataRepository
    def cleanup_data_repo() -> None:
        from tests.infrastructure.data_repository import cleanup_test_data_repository

        cleanup_test_data_repository()

    _try_reset("DataRepository", cleanup_data_repo)

    # NOTE: PreviewGenerator is now handled by AppContext cleanup (reset via reset_app_context)

    # Cleanup all workers and clear registry (waits for thread termination)
    def cleanup_worker_registry() -> None:
        from core.services.worker_lifecycle import WorkerManager

        WorkerManager.cleanup_all(timeout=500)  # Wait up to 500ms for each worker

    _try_reset("WorkerManager", cleanup_worker_registry)


def reset_hal_singletons_only() -> None:
    """Reset only HAL-related singletons.

    Use this for HAL-specific test isolation. For full reset, use reset_all_singletons().
    """
    with contextlib.suppress(Exception):
        from core.hal_compression import HALProcessPool

        HALProcessPool.reset_singleton()

    with contextlib.suppress(Exception):
        from tests.infrastructure.mock_hal import MockHALProcessPool

        MockHALProcessPool.reset_singleton()


def _should_fail_on_leaks(config: Any) -> bool:
    """Determine whether leak checks should fail or warn based on CLI flag."""
    leak_mode = "fail"
    with contextlib.suppress(Exception):
        leak_mode = config.getoption("--leak-mode")
    return leak_mode != "warn"


@pytest.fixture
def clean_registry_state() -> Generator[None, None, None]:
    """Ensure managers start uninitialized for a test.

    Useful for testing manager initialization lifecycle.
    Uses suspend_app_context to temporarily hide any existing context
    without destroying it, so that session-scoped contexts survive.

    IMPORTANT: This fixture should only be used by tests that specifically
    test the manager initialization lifecycle. It must not destroy managers
    that belong to a session-scoped context.
    """
    from PySide6.QtWidgets import QApplication

    from core.app_context import is_context_initialized, suspend_app_context
    from core.managers import (
        cleanup_managers,
        is_initialized,
        reset_for_tests,
    )

    app = QApplication.instance()

    # Check if there's an existing session context BEFORE suspending
    # If there is, we must NOT cleanup the managers (they belong to the session)
    had_session_context = is_context_initialized()

    # Use suspend_app_context to hide the current context without cleanup
    # This preserves session-scoped contexts for parallel test safety
    with suspend_app_context():
        # Only reset managers if we didn't have a session context
        # Otherwise we'd destroy managers that belong to the session
        if not had_session_context and is_initialized():
            with contextlib.suppress(Exception):
                cleanup_managers()
            with contextlib.suppress(Exception):
                reset_for_tests()

        yield

        # Clean up any managers that were initialized during the test
        # (only if they weren't already there from a session)
        if not had_session_context and is_initialized():
            with contextlib.suppress(Exception):
                cleanup_managers()

    # Context is automatically restored when suspend_app_context exits

    # Always process events if QApplication exists - required for deleteLater() cleanup.
    # Note: IS_HEADLESS means "no Qt at all", not "offscreen mode". Offscreen mode
    # has a fully functional event loop that needs processing.
    if app:
        app.processEvents()


# ============================================================================
# Real Component Fixtures
# ============================================================================


@pytest.fixture
def isolated_data_repository(tmp_path: Path) -> Generator[Any, None, None]:
    """Per-test DataRepository with tmp_path storage.

    Provides a fully isolated DataRepository instance for parallel-safe tests.
    All generated test data files are stored in tmp_path and auto-cleaned.

    Use this instead of get_test_data_repository() for parallel tests.

    Example:
        def test_extraction(isolated_data_repository, tmp_path):
            data = isolated_data_repository.get_vram_extraction_data("small")
            # Process data...
    """
    from tests.infrastructure.data_repository import get_isolated_data_repository

    repo = get_isolated_data_repository(tmp_path)
    yield repo
    # Explicit cleanup of temp files/dirs created by DataRepository
    repo.cleanup()


@pytest.fixture(scope="session")
def session_data_repository(
    tmp_path_factory: pytest.TempPathFactory,
) -> Generator[Any, None, None]:
    """Session-scoped DataRepository for read-only test data access.

    Use for tests that only READ from DataRepository and don't modify state.
    Generated files are shared across all tests in the session.

    For tests requiring isolation, use `isolated_data_repository` instead.

    Example:
        def test_readonly_access(session_data_repository):
            data = session_data_repository.get_vram_extraction_data("medium")
            # Use data for read-only operations...
    """
    from tests.infrastructure.data_repository import DataRepository

    session_tmp = tmp_path_factory.mktemp("session_data")
    repo = DataRepository(base_test_data_dir=str(session_tmp))
    yield repo
    repo.cleanup()


@pytest.fixture
def real_factory(
    request: pytest.FixtureRequest,
    app_context: AppContext,
) -> Generator[RealComponentFactory, None, None]:
    """Provide a RealComponentFactory for creating test components.

    Depends on app_context to ensure managers are properly initialized.
    The app_context fixture handles initialization and cleanup.
    """
    from tests.infrastructure.real_component_factory import RealComponentFactory

    _ = app_context  # Ensures fixture runs first to initialize managers
    fail_on_leaks = _should_fail_on_leaks(request.config)
    factory = RealComponentFactory(
        fail_on_leaks=fail_on_leaks,
    )
    yield factory
    # Cleanup will be handled by factory's cleanup method if needed
    if hasattr(factory, "cleanup"):
        factory.cleanup()


@pytest.fixture
def real_extraction_manager(
    app_context: AppContext,
) -> CoreOperationsManager:
    """Function-scoped real extraction manager with automatic cleanup.

    Depends on app_context to ensure proper per-test isolation.
    The app_context fixture handles initialization and cleanup.

    NOTE: This returns the CoreOperationsManager directly.
    """
    return app_context.core_operations_manager


@pytest.fixture
def real_injection_manager(
    app_context: AppContext,
) -> CoreOperationsManager:
    """Provide a fully configured real injection manager.

    Depends on app_context to ensure proper per-test isolation.
    NOTE: Returns the CoreOperationsManager directly.
    """
    return app_context.core_operations_manager


@pytest.fixture
def real_session_manager(
    app_context: AppContext,
) -> ApplicationStateManager:
    """Function-scoped real session manager with automatic cleanup.

    Depends on app_context to ensure proper per-test isolation.
    The app_context fixture handles initialization and cleanup.

    NOTE: This returns the real ApplicationStateManager.
    For mocks, create them locally with Mock(spec=ApplicationStateManager).
    """
    return app_context.application_state_manager


@pytest.fixture
def rom_cache(
    request: FixtureRequest,
    tmp_path: Path,
    app_context: AppContext,
) -> ROMCache:
    """Function-scoped ROM cache fixture with automatic cleanup.

    Uses tmp_path for worker-isolated cache directories (parallel-safe).
    The cache is automatically cleaned up when the test finishes.

    Provides a real ROM cache with common caching functionality.
    """
    from tests.infrastructure.real_component_factory import RealComponentFactory

    _ = app_context  # Ensures fixture runs first
    factory = RealComponentFactory(
        fail_on_leaks=_should_fail_on_leaks(request.config),
    )
    cache_dir = tmp_path / "rom_cache"
    cache_dir.mkdir(exist_ok=True)
    cache = factory.create_rom_cache(cache_dir=cache_dir)
    return cache


# ============================================================================
# Mock Fixtures
# ============================================================================


@pytest.fixture
def mock_main_window(real_factory: RealComponentFactory) -> MainWindow:
    """Provide a fully configured mock main window using real components."""
    return real_factory.create_main_window()


# ============================================================================
# Dependency Injection Fixtures
# ============================================================================


# ============================================================================
# Legacy Fixture Compatibility
# ============================================================================


@pytest.fixture
def isolated_managers(app_context: AppContext) -> Generator[None, None, None]:
    """Legacy alias for app_context fixture.

    DEPRECATED: Use `app_context` fixture directly instead.

    This fixture exists for backward compatibility with tests that
    haven't been migrated to use app_context. It provides the same
    isolation guarantees.

    The app_context fixture handles:
    - Manager initialization
    - Per-test isolation
    - Automatic cleanup
    """
    _ = app_context  # Triggers app_context initialization
    yield
