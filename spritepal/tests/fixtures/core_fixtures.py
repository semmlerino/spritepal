# pyright: recommended
# pyright: reportPrivateUsage=false
"""
Core manager fixtures for SpritePal tests.

This module provides fixtures for manager initialization, state management,
and dependency injection testing.

Key fixtures:
    - session_managers: Session-scoped shared managers (fastest, state persists)
    - isolated_managers: Function-scoped isolated managers (full isolation)
    - managers: Convenience fixture returning ManagerRegistry (depends on session_managers)
    - reset_manager_state: Reset caches without re-initialization

Fixture Selection Guide:
    | Need                        | Use                | NOT              |
    |-----------------------------|--------------------| -----------------|
    | Fast tests, shared state OK | session_managers   | isolated_managers|
    | Full isolation between tests| isolated_managers  | session_managers |
    | Access to ManagerRegistry   | managers           | direct import    |
    | Clean caches only           | reset_manager_state| isolated_managers|

Escape hatches:
    - @pytest.mark.allows_registry_state: Skip pollution detection
    - @pytest.mark.no_manager_setup: Skip manager initialization
"""
from __future__ import annotations

import contextlib
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

    from core.managers.extraction_manager import ExtractionManager
    from core.managers.injection_manager import InjectionManager
    from core.managers.registry import ManagerRegistry
    from core.managers.session_manager import SessionManager
    from tests.infrastructure.test_protocols import MockMainWindowProtocol
    from utils.rom_cache import ROMCache

# Runtime imports for inject() - needed to avoid deprecated ManagerRegistry methods
from core.di_container import inject
from core.protocols.manager_protocols import (
    ExtractionManagerProtocol,
    SessionManagerProtocol,
)

# Import Qt fixtures for IS_HEADLESS constant
try:
    from tests.fixtures.qt_fixtures import IS_HEADLESS
except ImportError:
    # Fallback if qt_fixtures can't be imported
    IS_HEADLESS = not os.environ.get("DISPLAY") and os.name != "nt"


# ============================================================================
# Parallel Execution Constants
# ============================================================================

# Fixtures that depend on session_managers (directly or transitively).
# Tests using these fixtures are auto-serialized under xdist.
SESSION_DEPENDENT_FIXTURES: frozenset[str] = frozenset({
    'session_managers',      # Direct session-scoped fixture
    'managers',              # Convenience wrapper for session_managers
    'reset_manager_state',   # Requires active session to reset
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
        - ManagerRegistry (core managers)
        - HALProcessPool (real HAL compression)
        - MockHALProcessPool (mock HAL compression)
        - DataRepository (test data cleanup)
        - PreviewGenerator (preview caching)
        - SignalRegistry (signal tracking)
        - WorkerManager (thread registry)
    """
    # Reset ManagerRegistry
    with contextlib.suppress(Exception):
        from core.managers.registry import ManagerRegistry
        ManagerRegistry.reset_for_tests()

    # Reset real HAL process pool
    with contextlib.suppress(Exception):
        from core.hal_compression import HALProcessPool
        HALProcessPool.reset_for_tests()

    # Reset mock HAL process pool
    with contextlib.suppress(Exception):
        from tests.infrastructure.mock_hal import MockHALProcessPool
        MockHALProcessPool.reset_singleton()

    # Clean up DataRepository
    with contextlib.suppress(Exception):
        from tests.infrastructure.test_data_repository import cleanup_test_data_repository
        cleanup_test_data_repository()

    # Reset PreviewGenerator singleton
    with contextlib.suppress(Exception):
        from core.services.preview_generator import cleanup_preview_generator
        cleanup_preview_generator()

    # Reset SignalRegistry singleton
    with contextlib.suppress(Exception):
        from utils.signal_registry import SignalRegistry
        SignalRegistry.reset_instance()

    # Clear WorkerManager thread registry
    with contextlib.suppress(Exception):
        from core.services.worker_lifecycle import WorkerManager
        WorkerManager._worker_registry.clear()


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


def _reset_manager_caches(registry: Any) -> None:
    """Reset manager state using public reset_state() APIs.

    This function uses the public reset_state() methods on managers
    rather than introspecting private attributes, making it more
    maintainable and less fragile to internal changes.
    """
    # List of (attribute_name, manager_instance) tuples
    manager_attrs = [
        'extraction_manager',
        'session_manager',
        'injection_manager',
        'application_state_manager',
        'monitoring_manager',
        'core_operations_manager',
    ]

    for attr in manager_attrs:
        manager = getattr(registry, attr, None)
        if manager is not None and hasattr(manager, 'reset_state'):
            with contextlib.suppress(Exception):
                manager.reset_state()

    # Also reset monitoring manager stats if available
    if hasattr(registry, 'monitoring_manager') and registry.monitoring_manager:
        mm = registry.monitoring_manager
        if hasattr(mm, 'reset_stats'):
            with contextlib.suppress(Exception):
                mm.reset_stats()


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

    WARNING: Manager state persists across ALL tests. Use isolated_managers
    or reset_manager_state if you need clean state.

    Usage:
        def test_something(session_managers):
            # Managers are already initialized and shared across tests
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

    # Ensure Qt app exists
    app = QApplication.instance()
    if app is None and not IS_HEADLESS:
        app = QApplication([])

    initialize_managers("TestApp", settings_path=settings_path)
    yield
    cleanup_managers()

    # Reset session state on cleanup
    _session_state.is_initialized = False

    # Process events to ensure cleanup completes
    if app and not IS_HEADLESS:
        app.processEvents()


@pytest.fixture
def isolated_managers(tmp_path: Path, request: FixtureRequest) -> Iterator[ManagerRegistry]:
    """
    Function-scoped managers for tests that need complete isolation.

    Unlike session_managers, this fixture creates fresh managers for each test
    and cleans them up afterward. Use this for tests that:
    - Modify manager state that could affect other tests
    - Need to test manager initialization/cleanup behavior
    - Can't share state with other tests

    Note: This is slower than session_managers but provides complete isolation.

    IMPORTANT: This fixture includes an isolation guard that fails if the
    ManagerRegistry is already initialized (indicates test pollution).

    Usage:
        def test_something_that_modifies_state(isolated_managers):
            # Fresh managers, isolated from other tests
            from core.managers.registry import ManagerRegistry
            registry = ManagerRegistry()
            # ... test code that modifies manager state ...
    """
    from PySide6.QtWidgets import QApplication

    from core.managers import cleanup_managers, initialize_managers
    from core.managers.registry import ManagerRegistry

    test_name = request.node.name if request and hasattr(request, 'node') else "<unknown>"
    session_active = _session_state.is_initialized
    session_settings_path = _session_state.settings_path

    # Same-module mixing detection has been moved to collection time
    # (see _validate_no_same_module_mixing in conftest.py) for reliability under xdist.
    # Here we only handle cross-module cleanup and pollution detection.

    # Isolation guard: clean up if registry already initialized
    registry = ManagerRegistry()
    if registry.is_initialized():
        if session_active:
            # Cross-module case: session_managers is from a different module
            # Clean up session state so this test gets fresh isolated managers
            try:
                cleanup_managers()
                ManagerRegistry.reset_for_tests()
            except Exception:
                pass
        else:
            # Registry initialized without session - likely test pollution
            # Try to clean up
            try:
                cleanup_managers()
            except Exception:
                pass
            # If still initialized, fail with clear message
            if registry.is_initialized():
                pytest.fail(
                    f"Test '{test_name}': isolated_managers fixture requires uninitialized ManagerRegistry. "
                    "Another fixture or test may have leaked state. "
                    "Use session_managers for shared state, or ensure cleanup in prior tests."
                )

    # Use temp settings path for isolation
    settings_path = tmp_path / ".test_settings.json"

    # Ensure Qt app exists
    app = QApplication.instance()
    if app is None and not IS_HEADLESS:
        app = QApplication([])

    # Initialize fresh managers for this test with isolated settings
    initialize_managers("TestApp_Isolated", settings_path=settings_path)

    # Yield the registry for convenience
    yield ManagerRegistry()  # type: ignore[misc]

    # Clean up managers after test
    cleanup_managers()

    # Restore session managers if they were active (cross-module case)
    # Note: Same-module mixing is now caught at collection time, so if we get here
    # with session_active=True, it must be from a different module.
    if session_active and session_settings_path:
        try:
            initialize_managers("TestApp", settings_path=session_settings_path)
        except Exception:
            pass  # Best effort restore

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
    from core.managers.registry import ManagerRegistry
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
        registry = ManagerRegistry()
        if not registry.is_initialized() and _session_state.settings_path:
            test_name = request.node.name if hasattr(request, 'node') else "<unknown>"
            pytest.fail(
                f"Test '{test_name}': Session managers were cleaned up mid-session. "
                "A prior test using session_managers called cleanup_managers() directly. "
                "Fix: Use isolated_managers if the test needs to call cleanup_managers(), "
                "or remove the cleanup_managers() call from the offending test."
            )

    yield


@pytest.fixture
def managers(session_managers: None) -> ManagerRegistry:
    """
    Convenience fixture that provides access to the ManagerRegistry.

    This fixture depends on session_managers (shared session state) and returns
    the ManagerRegistry instance for easy access in tests.

    Usage:
        def test_something(managers):
            extraction = managers.get_extraction_manager()
    """
    from core.managers.registry import ManagerRegistry

    # Verify session managers are properly initialized
    registry = ManagerRegistry()
    if not registry.is_initialized():
        pytest.fail(
            "managers: Session managers are not initialized. "
            "This indicates a test pollution issue - a prior test may have "
            "called cleanup_managers() while using session_managers. "
            "Fix: Find the offending test and use isolated_managers instead."
        )
    return registry


@pytest.fixture
def reset_manager_state(session_managers: None) -> Iterator[None]:
    """
    Lightweight state reset for session managers.

    This fixture uses session_managers (fast) but resets caches and counters
    before and after the test. Use this when you need:
    - Clean cache state without full manager re-initialization
    - Predictable counter values (e.g., extraction counts)
    - Isolation from prior tests without the overhead of isolated_managers

    Performance: ~5ms (vs ~50ms for isolated_managers)

    Usage:
        def test_extraction_counting(reset_manager_state):
            # Caches cleared, counters reset, but uses session managers
            manager = ManagerRegistry().extraction_manager
            # manager.extraction_count == 0
    """
    from core.managers.registry import ManagerRegistry

    registry = ManagerRegistry()
    if not registry.is_initialized():
        yield
        return

    # Reset state before test
    _reset_manager_caches(registry)

    yield

    # Reset state after test
    _reset_manager_caches(registry)


@pytest.fixture(autouse=True)
def auto_reset_session_state(request: FixtureRequest) -> Generator[None, None, None]:
    """Auto-reset session manager caches before tests using session_managers.

    This ensures each test starts with clean caches (extraction counts,
    cached data, etc.) without full re-initialization overhead.
    """
    from core.managers.registry import ManagerRegistry

    fixture_names = getattr(request, 'fixturenames', [])
    uses_session = 'session_managers' in fixture_names or 'managers' in fixture_names

    if not uses_session or not _session_state.is_initialized:
        yield
        return

    registry = ManagerRegistry()
    if registry.is_initialized():
        _reset_manager_caches(registry)

    yield

    # Also reset after test to clean up any state it created
    if registry.is_initialized():
        _reset_manager_caches(registry)


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
    from tests.infrastructure.test_data_repository import get_isolated_data_repository

    repo = get_isolated_data_repository(tmp_path)
    yield repo
    # Cleanup handled automatically by tmp_path fixture


@pytest.fixture
def real_factory(
    request: pytest.FixtureRequest,
    isolated_managers: ManagerRegistry,
) -> Generator[RealComponentFactory, None, None]:
    """Provide a RealComponentFactory for creating test components.

    Depends on isolated_managers to ensure registry is properly managed.
    The isolated_managers fixture handles initialization and cleanup,
    so RealComponentFactory won't need to manage the registry lifecycle.

    Passes the isolated_managers registry to the factory for proper test isolation.
    This ensures the factory uses managers from the test fixture instead of
    accessing global singletons.
    """
    fail_on_leaks = _should_fail_on_leaks(request.config)
    factory = RealComponentFactory(
        fail_on_leaks=fail_on_leaks,
        manager_registry=isolated_managers,
    )
    yield factory
    # Cleanup will be handled by factory's cleanup method if needed
    if hasattr(factory, 'cleanup'):
        factory.cleanup()


@pytest.fixture
def real_extraction_manager(
    isolated_managers: ManagerRegistry,
) -> ExtractionManager:
    """Function-scoped real extraction manager with automatic cleanup.

    Depends on isolated_managers to ensure proper per-test isolation.
    The isolated_managers fixture handles initialization and cleanup.

    NOTE: This returns a REAL ExtractionManager, not a mock.
    For actual mocks, create them locally with Mock(spec=ExtractionManager).
    """
    # Use inject() to avoid deprecated ManagerRegistry.get_extraction_manager()
    _ = isolated_managers  # Ensures fixture runs first to initialize managers
    return inject(ExtractionManagerProtocol)  # type: ignore[return-value]


@pytest.fixture
def real_injection_manager(real_factory: RealComponentFactory) -> InjectionManager:
    """Provide a fully configured real injection manager.

    NOTE: Returns a REAL InjectionManager, not a mock.
    For actual mocks, create them locally with Mock(spec=InjectionManager).
    """
    return real_factory.create_injection_manager()


@pytest.fixture
def real_session_manager(
    isolated_managers: ManagerRegistry,
) -> SessionManager:
    """Function-scoped real session manager with automatic cleanup.

    Depends on isolated_managers to ensure proper per-test isolation.
    The isolated_managers fixture handles initialization and cleanup.

    NOTE: This returns a REAL SessionManager, not a mock.
    For actual mocks, create them locally with Mock(spec=SessionManager).
    """
    # Use inject() to avoid deprecated ManagerRegistry.get_session_manager()
    _ = isolated_managers  # Ensures fixture runs first to initialize managers
    return inject(SessionManagerProtocol)  # type: ignore[return-value]


@pytest.fixture
def rom_cache(
    request: FixtureRequest,
    tmp_path: Path,
) -> ROMCache:
    """Function-scoped ROM cache fixture with automatic cleanup.

    Uses tmp_path for worker-isolated cache directories (parallel-safe).
    The cache is automatically cleaned up when the test finishes.

    Provides a real ROM cache with common caching functionality.
    """
    factory = RealComponentFactory(fail_on_leaks=_should_fail_on_leaks(request.config))
    cache_dir = tmp_path / "rom_cache"
    cache_dir.mkdir(exist_ok=True)
    cache = factory.create_rom_cache(cache_dir=cache_dir)
    return cache


@pytest.fixture
def mock_rom_cache(rom_cache: ROMCache) -> ROMCache:
    """Alias for rom_cache fixture for backward compatibility.

    NOTE: This now returns the class-scoped rom_cache directly
    instead of creating a new instance each time.
    """
    return rom_cache


# ============================================================================
# Mock Fixtures
# ============================================================================

@pytest.fixture
def mock_settings_manager(
    tmp_path: Path,
) -> Mock:
    """Function-scoped mock settings manager for test isolation.

    Uses tmp_path for worker-isolated temp directories (parallel-safe).

    Provides a mock settings manager with common configuration methods.
    """
    manager = Mock()

    # Add common settings methods
    manager.get_setting = Mock()
    manager.set_setting = Mock()
    manager.save_settings = Mock()
    manager.load_settings = Mock()
    manager.reset_to_defaults = Mock()

    # Use tmp_path for worker-isolated temp directory (xdist-safe)
    temp_output = str(tmp_path / "test_output")

    # Add common settings with default values
    manager.get_setting.side_effect = lambda key, default=None: {
        'output_path': temp_output,
        'create_grayscale': True,
        'create_metadata': True,
        'auto_save': False,
    }.get(key, default)

    return manager


@pytest.fixture
def mock_main_window(real_factory: RealComponentFactory) -> MockMainWindowProtocol:
    """Provide a fully configured mock main window using real components."""
    return real_factory.create_main_window()


@pytest.fixture
def mock_extraction_worker(real_factory: RealComponentFactory) -> Mock:
    """Provide a fully configured mock extraction worker using real components."""
    return real_factory.create_extraction_worker()


@pytest.fixture
def mock_file_dialogs(real_factory: RealComponentFactory) -> dict[str, Mock]:
    """Provide mock file dialog functions."""
    return real_factory.create_file_dialogs()


# ============================================================================
# Controller Fixture
# ============================================================================

# Import for controller fixture
try:
    from core.controller import ExtractionController
except ImportError:
    ExtractionController = None  # type: ignore[misc, assignment]


@pytest.fixture
def mock_controller() -> Mock:
    """Function-scoped MOCK controller for fast unit tests.

    Creates a fresh mock controller with mock manager dependencies.
    For tests needing real signal behavior, use the real main_window
    fixture and create a real controller locally.

    Returns a Mock(spec=ExtractionController) with mocked manager dependencies.
    """
    if ExtractionController is None:
        # Return mock if controller class unavailable
        return Mock()

    # Create a mock main window inline (no class-scoped dependency)
    mock_main_window = Mock()
    mock_main_window.extract_requested = MagicMock()
    mock_main_window.open_in_editor_requested = MagicMock()
    mock_main_window.arrange_rows_requested = MagicMock()
    mock_main_window.arrange_grid_requested = MagicMock()
    mock_main_window.inject_requested = MagicMock()
    mock_main_window.extraction_completed = MagicMock()
    mock_main_window.extraction_error_occurred = MagicMock()
    mock_main_window.extraction_panel = Mock()
    mock_main_window.rom_extraction_panel = Mock()
    mock_main_window.output_settings_manager = Mock()
    mock_main_window.toolbar_manager = Mock()

    # Create a mock controller to avoid manager initialization issues
    mock_ctrl = Mock(spec=ExtractionController if ExtractionController else None)
    mock_ctrl.main_window = mock_main_window
    mock_ctrl.session_manager = Mock()
    mock_ctrl.extraction_manager = Mock()
    mock_ctrl.injection_manager = Mock()
    mock_ctrl.palette_manager = Mock()
    mock_ctrl.worker_manager = Mock()
    mock_ctrl.error_handler = Mock()

    return mock_ctrl


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


@pytest.fixture
def test_injection_manager():
    """Provide a test injection manager instance."""
    from tests.infrastructure.manager_test_context import manager_context

    with manager_context("injection") as ctx:
        yield ctx.get_injection_manager()


@pytest.fixture
def test_extraction_manager():
    """Provide a test extraction manager instance."""
    from tests.infrastructure.manager_test_context import manager_context

    with manager_context("extraction") as ctx:
        yield ctx.get_extraction_manager()


@pytest.fixture
def test_session_manager():
    """Provide a test session manager instance."""
    from tests.infrastructure.manager_test_context import manager_context

    with manager_context("session") as ctx:
        yield ctx.get_session_manager()


@pytest.fixture
def complete_test_context():
    """Provide a complete test context with all managers configured."""
    from tests.infrastructure.manager_test_context import manager_context

    with manager_context("extraction", "injection", "session") as ctx:
        yield ctx


@pytest.fixture
def minimal_injection_context():
    """Provide a minimal context with just injection manager for dialog tests."""
    from tests.infrastructure.manager_test_context import manager_context

    with manager_context("injection") as ctx:
        yield ctx
