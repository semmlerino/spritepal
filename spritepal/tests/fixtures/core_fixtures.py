# pyright: recommended
# pyright: reportPrivateUsage=false
"""
Core manager fixtures for SpritePal tests.

This module provides fixtures for manager initialization, state management,
and dependency injection testing.

MIGRATION NOTE: For new tests, prefer the simplified `app_context` fixture
from `tests/fixtures/app_context_fixtures.py`. It provides cleaner isolation
and direct access to managers without inject() calls.

Key fixtures:
    - session_managers: Session-scoped shared managers (fastest, state persists)
    - isolated_managers: Function-scoped isolated managers (full isolation)
    - clean_registry_state: Ensure registry starts uninitialized (for lifecycle tests)

Fixture Selection Guide:
    | Need                        | Use                | NOT              |
    |-----------------------------|--------------------| -----------------|
    | Fast tests, shared state OK | session_managers   | isolated_managers|
    | Full isolation between tests| isolated_managers  | session_managers |
    | Simple isolation (NEW)      | app_context        | isolated_managers|
    | Test initialization itself  | clean_registry_state| session_managers|

Note: Cache reset is handled automatically by the `auto_reset_session_state`
autouse fixture when using session_managers.

Escape hatches:
    - @pytest.mark.allows_registry_state: Skip pollution detection
    - @pytest.mark.no_manager_setup: Skip manager initialization
"""
from __future__ import annotations

import contextlib
import logging
import os
import tempfile
import warnings
from collections.abc import Callable, Generator, Iterator
from contextlib import AbstractContextManager as ContextManager
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any
from unittest.mock import MagicMock, Mock

import pytest

from tests.infrastructure.real_component_factory import RealComponentFactory

if TYPE_CHECKING:
    from pytest import FixtureRequest, TempPathFactory

    from core.managers.application_state_manager import ApplicationStateManager
    from core.managers.core_operations_manager import CoreOperationsManager
    from core.services.rom_cache import ROMCache
    from ui.main_window import MainWindow

# Runtime imports for AppContext access
from core.app_context import get_app_context
from core.managers.application_state_manager import ApplicationStateManager
from core.managers.core_operations_manager import CoreOperationsManager

# Import Qt fixtures for IS_HEADLESS constant
try:
    from tests.fixtures.qt_fixtures import IS_HEADLESS
except ImportError:
    # Fallback if qt_fixtures can't be imported
    IS_HEADLESS = not os.environ.get("DISPLAY") and os.name != "nt"

# Module logger for fixture diagnostics
_logger = logging.getLogger(__name__)

# ============================================================================
# Parallel Execution Constants
# ============================================================================

# Fixtures that depend on session_managers (directly or transitively).
# Tests using these fixtures are auto-serialized under xdist.
SESSION_DEPENDENT_FIXTURES: frozenset[str] = frozenset({
    'session_managers',      # Direct session-scoped fixture
    'managers_initialized',  # Integration test fixture that modifies DI container
    'extraction_manager',    # Uses session_managers for extraction operations
    'mock_factory',          # Uses session_managers for mock factory setup
})


@dataclass
class SessionState:
    """Container for session-scoped test state.

    IMPORTANT: Single-writer semantics.
    - WRITE: Only `session_managers` fixture should mutate this state
    - READ: Other fixtures may read `is_initialized` and `settings_path`

    This pattern prevents test pollution from bare global variables while
    maintaining a single source of truth for session initialization state.

    If you need to check whether session managers are active, read `is_initialized`.
    Never set `is_initialized = True` outside of `session_managers` fixture.
    """
    settings_path: Path | None = None
    temp_dir: Path | None = None
    is_initialized: bool = False


# Session state container - SINGLE WRITER: only session_managers fixture modifies this
# Other fixtures may read _session_state.is_initialized but should NEVER write to it
# NOTE: Under pytest-xdist, each worker is a separate process with its own _session_state
# so this is naturally isolated per-worker. The SessionState pattern ensures consistent access.
_session_state = SessionState()


def is_session_managers_active() -> bool:
    """Check if session_managers fixture is currently active.

    This is the public API for checking session state. Use this instead of
    directly accessing _session_state.is_initialized.

    Returns:
        True if session_managers fixture has initialized managers
    """
    return _session_state.is_initialized


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
    OffsetDialogManager cleanup is per-instance, handled by Qt parent-child hierarchy.

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


def _reset_manager_caches(_unused: Any = None) -> None:
    """Reset manager state using public reset_state() APIs.

    This function uses the public reset_state() methods on managers
    rather than introspecting private attributes, making it more
    maintainable and less fragile to internal changes.

    Note: ApplicationStateManager receives full_reset=True to clear _settings
    between tests (prevents settings leakage). Other managers use full_reset=False
    to preserve services and initialized state within the session.
    """
    from core.app_context import get_app_context_optional

    ctx = get_app_context_optional()
    if ctx is None:
        return

    # Reset ApplicationStateManager with full_reset to clear settings
    state_mgr = ctx.application_state_manager
    if hasattr(state_mgr, 'reset_state'):
        with contextlib.suppress(Exception):
            state_mgr.reset_state(full_reset=True)

    # Reset CoreOperationsManager without full_reset (preserves services)
    ops_mgr = ctx.core_operations_manager
    if hasattr(ops_mgr, 'reset_state'):
        with contextlib.suppress(Exception):
            ops_mgr.reset_state()


def _should_fail_on_leaks(config: Any) -> bool:
    """Determine whether leak checks should fail or warn based on CLI flag."""
    leak_mode = "fail"
    with contextlib.suppress(Exception):
        leak_mode = config.getoption("--leak-mode")
    return leak_mode != "warn"


@pytest.fixture(scope="session")
def session_managers(tmp_path_factory: TempPathFactory) -> Iterator[None]:
    """
    Session-scoped managers for performance optimization.

    This fixture initializes managers once per test session and keeps them
    alive for the entire session. Tests can use this for better performance
    by depending on this fixture instead of setup_managers.

    Uses isolated temp settings directory to avoid polluting repo root.
    State is stored in SessionState dataclass to avoid global mutable variables.

    Ordering semantics:
        - Tests using this fixture get xdist_group("serial") marker automatically
        - This co-locates tests on one worker but does NOT guarantee execution order
        - Settings are fully reset between tests (via auto_reset_session_state)
        - Services remain initialized for performance (not cleared between tests)
        - Tests should be stateless and not rely on any particular execution order

    WARNING: While settings are reset between tests, tests should still be
    written to be order-independent. Use isolated_managers if you need
    complete isolation or are modifying manager internals.

    Usage:
        def test_something(session_managers):
            # Managers are already initialized and shared across tests
            # Access managers via: inject(CoreOperationsManager)
            pass
    """
    # Lazy import manager functions
    import os

    from PySide6.QtWidgets import QApplication

    from core.managers import cleanup_managers, initialize_managers

    # Create session-specific settings directory for isolation
    # Priority: SPRITEPAL_SETTINGS_DIR env var (xdist) > tmp_path_factory
    env_settings = os.environ.get("SPRITEPAL_SETTINGS_DIR")
    if env_settings:
        # Under xdist, use worker-specific session settings
        settings_dir = Path(env_settings) / "session_settings"
        settings_dir.mkdir(parents=True, exist_ok=True)
    else:
        settings_dir = tmp_path_factory.mktemp("session_settings")
    settings_path = settings_dir / ".test_settings.json"

    # Store in session state container
    _session_state.temp_dir = settings_dir
    _session_state.settings_path = settings_path
    _session_state.is_initialized = True

    # Ensure Qt app exists (even in headless/offscreen mode for realistic signal behavior)
    app = QApplication.instance()
    if app is None:
        app = QApplication([])

    initialize_managers("TestApp", settings_path=settings_path)

    yield None
    cleanup_managers()

    # Reset session state on cleanup
    _session_state.is_initialized = False

    # Process events to ensure cleanup completes
    if app:
        app.processEvents()


@pytest.fixture
def isolated_managers(tmp_path: Path, request: FixtureRequest) -> Iterator[None]:
    """
    Function-scoped managers for tests that need complete isolation.

    Unlike session_managers, this fixture creates fresh managers for each test
    and cleans them up afterward. Use this for tests that:
    - Modify manager state that could affect other tests
    - Need to test manager initialization/cleanup behavior
    - Can't share state with other tests

    Note: This is slower than session_managers but provides complete isolation.

    IMPORTANT: This fixture includes an isolation guard that fails if
    managers are already initialized (indicates test pollution).

    Usage:
        def test_something_that_modifies_state(isolated_managers):
            # Fresh managers, isolated from other tests
            ops_mgr = get_app_context().core_operations_manager
            # ... test code that modifies manager state ...
    """
    from PySide6.QtWidgets import QApplication

    from core.managers import (
        cleanup_managers,
        initialize_managers,
        is_initialized,
        reset_for_tests,
    )

    test_name = request.node.name if request and hasattr(request, 'node') else "<unknown>"
    session_active = _session_state.is_initialized
    session_settings_path = _session_state.settings_path

    # Same-module mixing detection has been moved to collection time
    # (see _validate_no_same_module_mixing in conftest.py) for reliability under xdist.
    # Here we only handle cross-module cleanup and pollution detection.

    # Isolation guard: clean up if managers already initialized
    if is_initialized():
        if session_active:
            # Cross-module case: session_managers is from a different module
            # Clean up session state so this test gets fresh isolated managers
            try:
                cleanup_managers()
                reset_for_tests()
            except Exception as e:
                _logger.warning(
                    "isolated_managers: Failed to cleanup session managers for test '%s': %s. "
                    "Subsequent tests may have corrupted state.",
                    test_name, e
                )
        else:
            # Managers initialized without session - likely test pollution
            # Try to clean up
            try:
                cleanup_managers()
            except Exception as e:
                _logger.warning(
                    "isolated_managers: Failed to cleanup polluted managers for test '%s': %s",
                    test_name, e
                )
            # If still initialized, fail with clear message
            if is_initialized():
                pytest.fail(
                    f"Test '{test_name}': isolated_managers fixture requires uninitialized managers. "
                    "Another fixture or test may have leaked state. "
                    "Use session_managers for shared state, or ensure cleanup in prior tests."
                )

    # Use temp settings path for isolation
    settings_path = tmp_path / ".test_settings.json"

    # Ensure Qt app exists (even in headless/offscreen mode for realistic signal behavior)
    app = QApplication.instance()
    if app is None:
        app = QApplication([])

    # Initialize fresh managers for this test with isolated settings
    initialize_managers("TestApp_Isolated", settings_path=settings_path)

    yield None

    # Clean up managers after test
    cleanup_managers()

    # Restore session managers if they were active (cross-module case)
    # Note: Same-module mixing is now caught at collection time, so if we get here
    # with session_active=True, it must be from a different module.
    if session_active and session_settings_path:
        from core.managers import is_initialized as check_initialized

        try:
            initialize_managers("TestApp", settings_path=session_settings_path)
            # Verify restoration succeeded
            if not check_initialized():
                pytest.fail(
                    f"CRITICAL: Session managers restoration verification failed after '{test_name}'.\n"
                    "Managers are not initialized after restore attempt.",
                    pytrace=False
                )
        except Exception as e:
            # Fail hard - silent restoration failures cause mysterious downstream failures
            pytest.fail(
                f"CRITICAL: Failed to restore session managers after test '{test_name}': {e}\n"
                "This will cause subsequent session_managers tests to fail.\n"
                "Fix: Mark module with @pytest.mark.parallel_unsafe or convert to session_managers.",
                pytrace=False
            )

    # Process events to ensure cleanup completes
    if app and not IS_HEADLESS:
        app.processEvents()


@pytest.fixture(autouse=True)
def detect_session_manager_cleanup(request: FixtureRequest) -> Generator[None, None, None]:
    """
    Autouse fixture to detect when session managers are incorrectly cleaned up.

    This fixture FAILS (not auto-restores) when a test using session_managers
    calls cleanup_managers() directly, which breaks the session fixture's contract.

    Previously this fixture would silently restore managers, masking the bug.
    Now it fails immediately so the test can be fixed properly.

    Note: Under xdist, parallel_safe tests use isolated_managers and don't
    share session state, so this check is skipped for them.
    """
    from core.managers import is_initialized
    from tests.fixtures.xdist_fixtures import is_xdist_worker

    # Skip check for parallel_safe tests under xdist - they use isolated_managers
    if is_xdist_worker() and request.node.get_closest_marker("parallel_safe"):
        yield
        return

    # Check if test uses session_managers fixture (directly or via managers)
    fixture_names = getattr(request, 'fixturenames', [])
    uses_session_managers = 'session_managers' in fixture_names or 'managers' in fixture_names

    if uses_session_managers and _session_state.is_initialized:
        # Check if managers got cleaned up mid-session
        if not is_initialized() and _session_state.settings_path:
            test_name = request.node.name if hasattr(request, 'node') else "<unknown>"
            pytest.fail(
                f"Test '{test_name}': Session managers were cleaned up mid-session. "
                "A prior test using session_managers called cleanup_managers() directly. "
                "Fix: Use isolated_managers if the test needs to call cleanup_managers(), "
                "or remove the cleanup_managers() call from the offending test."
            )

    yield


@pytest.fixture
def clean_registry_state(request: FixtureRequest) -> Generator[None, None, None]:
    """
    Ensure managers start uninitialized for a test, even if session_managers
    is active in this worker. Restores session managers afterward if needed.
    """
    from PySide6.QtWidgets import QApplication

    from core.di_container import reset_container
    from core.managers import (
        cleanup_managers,
        initialize_managers,
        is_initialized,
        reset_for_tests,
    )

    session_active = _session_state.is_initialized
    session_settings_path = _session_state.settings_path

    app = QApplication.instance()

    if is_initialized():
        with contextlib.suppress(Exception):
            cleanup_managers()
        with contextlib.suppress(Exception):
            reset_for_tests()

    reset_container()
    yield

    if is_initialized():
        with contextlib.suppress(Exception):
            cleanup_managers()
    reset_container()

    if session_active and session_settings_path:
        if app is None:
            app = QApplication([])
        initialize_managers("TestApp", settings_path=session_settings_path)
        if not is_initialized():
            test_name = request.node.name if request and hasattr(request, 'node') else "<unknown>"
            pytest.fail(
                f"CRITICAL: Failed to restore session managers after test '{test_name}'.\n"
                "Managers are not initialized after restore attempt.",
                pytrace=False
            )

    if app and not IS_HEADLESS:
        app.processEvents()


@pytest.fixture(autouse=True)
def auto_reset_session_state(request: FixtureRequest) -> Generator[None, None, None]:
    """Auto-reset session manager state after tests using session_managers.

    Runs after each test using session_managers to reset manager state:
    - ApplicationStateManager: full_reset=True (clears _settings to defaults)
    - Other managers: full_reset=False (preserves services, clears caches)

    This prevents settings leakage between tests while preserving the
    performance benefit of session-scoped services. Tests should still
    be written to be order-independent since xdist_group("serial") only
    co-locates tests on one worker, it does not guarantee execution order.
    """
    from core.managers import is_initialized

    fixture_names = getattr(request, 'fixturenames', [])
    uses_session = 'session_managers' in fixture_names

    if not uses_session or not _session_state.is_initialized:
        yield
        return

    yield

    # Reset after test to clean up any state it created
    if is_initialized():
        _reset_manager_caches(None)  # Managers accessed via inject()


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
    # Cleanup handled automatically by tmp_path fixture


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
    isolated_managers: None,
) -> Generator[RealComponentFactory, None, None]:
    """Provide a RealComponentFactory for creating test components.

    Depends on isolated_managers to ensure managers are properly initialized.
    The isolated_managers fixture handles initialization and cleanup.
    """
    fail_on_leaks = _should_fail_on_leaks(request.config)
    factory = RealComponentFactory(
        fail_on_leaks=fail_on_leaks,
    )
    yield factory
    # Cleanup will be handled by factory's cleanup method if needed
    if hasattr(factory, 'cleanup'):
        factory.cleanup()


@pytest.fixture
def real_extraction_manager(
    isolated_managers: None,
) -> CoreOperationsManager:
    """Function-scoped real extraction manager with automatic cleanup.

    Depends on isolated_managers to ensure proper per-test isolation.
    The isolated_managers fixture handles initialization and cleanup.

    NOTE: This returns the CoreOperationsManager directly.
    """
    _ = isolated_managers  # Ensures fixture runs first to initialize managers
    return get_app_context().core_operations_manager


@pytest.fixture
def real_injection_manager(real_factory: RealComponentFactory) -> CoreOperationsManager:
    """Provide a fully configured real injection manager.

    NOTE: Returns the CoreOperationsManager directly.
    """
    return real_factory.create_injection_manager()


@pytest.fixture
def real_session_manager(
    isolated_managers: None,
) -> ApplicationStateManager:
    """Function-scoped real session manager with automatic cleanup.

    Depends on isolated_managers to ensure proper per-test isolation.
    The isolated_managers fixture handles initialization and cleanup.

    NOTE: This returns the real ApplicationStateManager.
    For mocks, create them locally with Mock(spec=ApplicationStateManager).
    """
    _ = isolated_managers  # Ensures fixture runs first to initialize managers
    return get_app_context().application_state_manager


@pytest.fixture
def rom_cache(
    request: FixtureRequest,
    tmp_path: Path,
    isolated_managers: None,
) -> ROMCache:
    """Function-scoped ROM cache fixture with automatic cleanup.

    Uses tmp_path for worker-isolated cache directories (parallel-safe).
    The cache is automatically cleaned up when the test finishes.

    Provides a real ROM cache with common caching functionality.
    """
    _ = isolated_managers  # Ensures fixture runs first
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

@pytest.fixture
def manager_context_factory() -> Callable[..., ContextManager[Any]]:
    """
    Factory for creating manager contexts for dependency injection tests.

    This fixture provides a clean way to create test contexts with specific
    manager instances, enabling proper isolation between tests.

    Usage:
        def test_my_dialog(manager_context_factory):
            with manager_context_factory():
                dialog = InjectionDialog()
                # dialog will use real managers from context
    """
    from tests.infrastructure.manager_test_context import (
        ManagerTestContext,
        manager_context,
    )

    def _create_context(
        managers: dict[str, Any] | list[str] | None = None,
        name: str = "test_context"
    ) -> ContextManager[ManagerTestContext]:
        """
        Create a manager context for testing.

        Args:
            managers: Dict of manager instances (ignored - uses real managers),
                     or list of manager type names ("extraction", "injection", "session")
            name: Context name for debugging (unused, kept for compatibility)

        Returns:
            Context manager for use in with statements
        """
        # Determine which managers to initialize
        if managers is None:
            # Create complete test context with all managers
            manager_types = ("extraction", "injection", "session")
        elif isinstance(managers, list):
            # Use specified manager types
            manager_types = tuple(managers)
        elif isinstance(managers, dict):
            # Dict provided - extract keys as manager types
            # Note: Actual instances are ignored; we use real managers
            manager_types = tuple(managers.keys())
        else:
            manager_types = ("extraction", "injection", "session")

        return manager_context(*manager_types)

    return _create_context
