# pyright: recommended
# pyright: reportPrivateUsage=false
"""
Core manager fixtures for SpritePal tests.

This module provides fixtures for manager initialization, state management,
and dependency injection testing.

Key fixtures:
    - session_managers: Session-scoped shared managers (fastest, state persists)
    - class_managers: Class-scoped managers (shared within test class)
    - isolated_managers: Function-scoped isolated managers (full isolation)
    - fast_managers: Convenience alias for session_managers
    - reset_manager_state: Reset caches without re-initialization
    - detect_manager_pollution: Autouse fixture for state leak detection
    - setup_managers: Per-test manager initialization

Fixture Selection Guide:
    | Need                        | Use                | NOT              |
    |-----------------------------|--------------------| -----------------|
    | Fast tests, shared state OK | session_managers   | isolated_managers|
    | Tests in same class share   | class_managers     | setup_managers   |
    | Full isolation between tests| isolated_managers  | session_managers |
    | Performance-focused         | fast_managers      | setup_managers   |
    | Clean caches only           | reset_manager_state| isolated_managers|

Escape hatches:
    - @pytest.mark.allows_registry_state: Skip pollution detection
    - @pytest.mark.no_manager_setup: Skip setup_managers fixture
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
from unittest.mock import Mock

import pytest

from tests.infrastructure.real_component_factory import RealComponentFactory

if TYPE_CHECKING:
    from pytest import FixtureRequest, TempPathFactory

    from core.managers.extraction_manager import ExtractionManager
    from core.managers.injection_manager import InjectionManager
    from core.managers.session_manager import SessionManager
    from tests.infrastructure.test_protocols import MockMainWindowProtocol
    from utils.rom_cache import ROMCache


# Import Qt fixtures for IS_HEADLESS constant
try:
    from tests.fixtures.qt_fixtures import IS_HEADLESS
except ImportError:
    # Fallback if qt_fixtures can't be imported
    IS_HEADLESS = not os.environ.get("DISPLAY") and os.name != "nt"


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
_session_state = SessionState()


def is_session_managers_active() -> bool:
    """Check if session_managers fixture is currently active.

    This is the public API for checking session state. Use this instead of
    directly accessing _session_state.is_initialized.

    Returns:
        True if session_managers fixture has initialized managers
    """
    return _session_state.is_initialized


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
    from PySide6.QtWidgets import QApplication

    from core.managers import cleanup_managers, initialize_managers

    # Create session-specific settings directory for isolation
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
def isolated_managers(tmp_path: Path, request: FixtureRequest) -> Iterator[None]:
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

    # Check if THIS test's module also uses session_managers (same-module mixing)
    fixture_names = set(getattr(request, 'fixturenames', []))
    same_module_mixing = session_active and 'session_managers' in fixture_names

    # Isolation guard: fail if registry already initialized (indicates pollution or mixing)
    registry = ManagerRegistry()
    if registry.is_initialized():
        if same_module_mixing:
            # FAIL FAST: Same module uses both session_managers and isolated_managers
            # This indicates a test design problem - keep modules consistent.
            pytest.fail(
                f"Test '{test_name}': Cannot use isolated_managers when session_managers is also "
                "requested in the same module. This causes order-dependent failures. Either:\n"
                "  1. Use isolated_managers for ALL tests in this module, or\n"
                "  2. Use session_managers + @pytest.mark.shared_state_safe for ALL tests\n"
                "See CLAUDE.md 'Test Fixture Selection Guide' for guidance."
            )
        elif session_active:
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

    # Restore session managers if they were active from a different module
    if session_active and not same_module_mixing and session_settings_path:
        try:
            initialize_managers("TestApp", settings_path=session_settings_path)
        except Exception:
            pass  # Best effort restore

    # Process events to ensure cleanup completes
    if app and not IS_HEADLESS:
        app.processEvents()


@pytest.fixture(autouse=True)
def detect_manager_pollution(request: FixtureRequest) -> Generator[None, None, None]:
    """
    Autouse fixture to detect unexpected ManagerRegistry state MODIFICATION.

    This fixture detects tests that MODIFY registry state without using fixtures:
    1. Tests that initialize the registry without using manager fixtures (pollution)
    2. Tests that clean up the registry without owning it (breaking session state)

    Tests that simply INHERIT initialized state (from session_managers) are OK.
    The goal is to catch accidental pollution, not punish innocent tests.

    Escape hatches:
    - @pytest.mark.allows_registry_state: Skip this check entirely
    """
    from core.managers.registry import ManagerRegistry

    # Skip check if test has escape hatch marker
    if request.node.get_closest_marker("allows_registry_state"):
        yield
        return

    # Get list of manager-related fixtures this test uses
    fixture_names = getattr(request, 'fixturenames', [])
    # Include ALL fixtures that manage ManagerRegistry lifecycle
    manager_fixtures = {
        'session_managers', 'class_managers', 'isolated_managers',
        'fast_managers', 'setup_managers', 'managers_initialized'
    }
    uses_manager_fixture = bool(manager_fixtures & set(fixture_names))

    # Check state before test
    registry = ManagerRegistry()
    initialized_before = registry.is_initialized()

    # If session_managers is active, inheriting that state is expected and OK
    session_active = _session_state.is_initialized

    yield

    # Check state after test
    initialized_after = registry.is_initialized()

    # Detect pollution: test MODIFIED registry state without using a fixture
    if not uses_manager_fixture:
        test_name = request.node.name if hasattr(request, 'node') else "<unknown>"

        # Case 1: Test initialized registry (was uninitialized, now initialized)
        if not initialized_before and initialized_after:
            pytest.fail(
                f"Test '{test_name}' initialized ManagerRegistry but didn't use manager fixtures. "
                "This pollutes subsequent tests. "
                "Fix: Use isolated_managers fixture, or add @pytest.mark.allows_registry_state."
            )

        # Case 2: Test cleaned up registry when session_managers was active
        # (was initialized via session, now uninitialized)
        if initialized_before and not initialized_after and session_active:
            pytest.fail(
                f"Test '{test_name}' cleaned up ManagerRegistry but session_managers is active. "
                "This breaks session fixture contract. "
                "Fix: Use isolated_managers if you need to call cleanup_managers()."
            )


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

    # Check if test uses session_managers fixture
    fixture_names = getattr(request, 'fixturenames', [])
    uses_session_managers = 'session_managers' in fixture_names or 'fast_managers' in fixture_names

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
def fast_managers(session_managers: None) -> Iterator[None]:
    """
    Fast manager access using session-scoped managers.

    This fixture provides manager access without per-test initialization overhead.
    Tests can use this instead of setup_managers for better performance when
    they don't need isolated manager state.

    NOTE: This fixture no longer silently re-initializes managers.
    If managers are not initialized, something is wrong with the test order.

    Usage:
        def test_something(fast_managers):
            # Uses shared session managers - much faster
            pass
    """
    from core.managers.registry import ManagerRegistry

    # Verify session managers are properly initialized
    if not ManagerRegistry().is_initialized():
        pytest.fail(
            "fast_managers: Session managers are not initialized. "
            "This indicates a test pollution issue - a prior test may have "
            "called cleanup_managers() while using session_managers. "
            "Fix: Find the offending test and use isolated_managers instead."
        )

    yield


@pytest.fixture
def managers(fast_managers: None) -> Any:
    """
    Convenience fixture that provides access to the ManagerRegistry.

    This fixture depends on fast_managers (shared session state) and returns
    the ManagerRegistry instance for easy access in tests.

    Usage:
        def test_something(managers):
            extraction = managers.get_extraction_manager()
    """
    from core.managers.registry import ManagerRegistry
    return ManagerRegistry()


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

    Opt-out: @pytest.mark.skip_session_reset
    """
    from core.managers.registry import ManagerRegistry

    markers = [m.name for m in request.node.iter_markers()]
    if 'skip_session_reset' in markers:
        yield
        return

    fixture_names = getattr(request, 'fixturenames', [])
    uses_session = 'session_managers' in fixture_names or 'fast_managers' in fixture_names

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


@pytest.fixture
def setup_managers(request: FixtureRequest, tmp_path: Path) -> Iterator[None]:
    """
    Setup managers for tests requiring per-test isolation.

    This fixture ensures proper manager initialization and cleanup
    for every test, replacing duplicated setup across test files.
    
    IMPORTANT: If session_managers is active in the session, this fixture
    yields without initializing (session_managers owns the registry).
    It only cleans up if it was the one that initialized.

    For better performance, consider using 'fast_managers' fixture instead
    if your test doesn't require isolated manager state.
    """
    # Skip manager setup if test is marked with no_manager_setup
    if request.node.get_closest_marker("no_manager_setup"):
        yield
        return

    # Skip if test uses session managers (via fast_managers fixture)
    if 'session_managers' in request.fixturenames or 'fast_managers' in request.fixturenames:
        yield
        return

    # Skip if session_managers is already active in this session
    # (another test established session state - we shouldn't touch it)
    if _session_state.is_initialized:
        yield
        return

    # Lazy import manager functions to reduce startup overhead
    # Ensure Qt app exists before initializing managers
    from PySide6.QtWidgets import QApplication

    from core.managers import cleanup_managers, initialize_managers
    from core.managers.registry import ManagerRegistry

    app = QApplication.instance()
    if app is None and not IS_HEADLESS:
        app = QApplication([])

    # Track if we initialize, so we only cleanup if we initialized
    registry = ManagerRegistry()
    was_initialized_before = registry.is_initialized()

    try:
        if not was_initialized_before:
            # Use temp settings path for isolation to prevent polluting user config
            settings_path = tmp_path / ".test_settings_setup.json"
            initialize_managers("TestApp", settings_path=settings_path)
        yield
    finally:
        # Only cleanup if WE initialized (not if someone else did)
        if not was_initialized_before:
            try:
                cleanup_managers()
            except (RuntimeError, AttributeError) as e:
                # Qt objects may already be deleted, log but don't crash
                import logging
                logging.getLogger(__name__).debug(f"Manager cleanup warning: {e}")
            except Exception as e:
                # Unexpected cleanup error, log but continue
                import logging
                logging.getLogger(__name__).warning(f"Unexpected manager cleanup error: {e}")


@pytest.fixture(scope="class")
def class_managers(tmp_path_factory: TempPathFactory) -> Iterator[None]:
    """
    Class-scoped managers for test classes with multiple related tests.

    This fixture initializes managers once per test class and cleans them up
    when the class finishes. Use this when:
    - Multiple tests in a class need manager access
    - Tests don't need full isolation between each other
    - You want faster execution than per-test setup

    If session_managers is already active, this fixture is a no-op to avoid
    conflicting cleanup.

    Note: State can persist between tests in the same class.
    For full isolation, use isolated_managers instead.

    Usage:
        @pytest.mark.usefixtures("class_managers")
        class TestMyComponent:
            def test_something(self):
                # Managers already initialized
                pass

        # Or explicitly in each test:
        class TestMyComponent:
            def test_something(self, class_managers):
                pass
    """
    from PySide6.QtWidgets import QApplication

    from core.managers import cleanup_managers, initialize_managers
    from core.managers.registry import ManagerRegistry

    registry = ManagerRegistry()
    was_already_initialized = registry.is_initialized()

    # If session_managers is active, don't initialize or cleanup - let session own lifecycle
    if was_already_initialized and is_session_managers_active():
        yield
        return

    # Create class-specific settings directory for isolation
    settings_dir = tmp_path_factory.mktemp("class_settings")
    settings_path = settings_dir / ".test_settings.json"

    # Ensure Qt app exists
    app = QApplication.instance()
    if app is None and not IS_HEADLESS:
        app = QApplication([])

    if not was_already_initialized:
        initialize_managers("TestApp_Class", settings_path=settings_path)

    yield

    # Only cleanup if WE initialized AND session_managers is NOT active
    if not was_already_initialized and not is_session_managers_active():
        cleanup_managers()

    # Process events to ensure cleanup completes
    if app and not IS_HEADLESS:
        app.processEvents()


# ============================================================================
# Real Component Fixtures
# ============================================================================

@pytest.fixture
def real_factory(request: pytest.FixtureRequest) -> Generator[RealComponentFactory, None, None]:
    """Provide a RealComponentFactory for creating test components."""
    fail_on_leaks = _should_fail_on_leaks(request.config)
    factory = RealComponentFactory(fail_on_leaks=fail_on_leaks)
    yield factory
    # Cleanup will be handled by factory's cleanup method if needed
    if hasattr(factory, 'cleanup'):
        factory.cleanup()


@pytest.fixture(scope="class")
def real_extraction_manager(
    request: FixtureRequest,
) -> Generator[ExtractionManager, None, None]:
    """Class-scoped real extraction manager with proper cleanup.

    Used 51 times across tests. Class scope reduces instantiations
    from 51 to ~12 (77% reduction).

    NOTE: This returns a REAL ExtractionManager, not a mock.
    For actual mocks, create them locally with Mock(spec=ExtractionManager).
    """
    factory = RealComponentFactory(fail_on_leaks=_should_fail_on_leaks(request.config))
    manager = factory.create_extraction_manager()

    def reset_state():
        if hasattr(manager, 'reset_state'):
            with contextlib.suppress(Exception):
                manager.reset_state()

    request.addfinalizer(reset_state)

    yield manager
    if hasattr(factory, 'cleanup'):
        factory.cleanup()


@pytest.fixture
def real_injection_manager(real_factory: RealComponentFactory) -> InjectionManager:
    """Provide a fully configured real injection manager.

    NOTE: Returns a REAL InjectionManager, not a mock.
    For actual mocks, create them locally with Mock(spec=InjectionManager).
    """
    return real_factory.create_injection_manager()


@pytest.fixture(scope="class")
def real_session_manager(
    request: FixtureRequest,
) -> Generator[SessionManager, None, None]:
    """Class-scoped real session manager with proper cleanup.

    Used 26 times across tests. Class scope reduces instantiations
    from 26 to ~8 (69% reduction).

    NOTE: This returns a REAL SessionManager, not a mock.
    For actual mocks, create them locally with Mock(spec=SessionManager).
    """
    factory = RealComponentFactory(fail_on_leaks=_should_fail_on_leaks(request.config))
    manager = factory.create_session_manager()

    def reset_state():
        if hasattr(manager, 'reset_state'):
            with contextlib.suppress(Exception):
                manager.reset_state()

    request.addfinalizer(reset_state)

    yield manager
    if hasattr(factory, 'cleanup'):
        factory.cleanup()


@pytest.fixture(scope="class")
def rom_cache(
    request: FixtureRequest,
) -> Generator[ROMCache, None, None]:
    """Class-scoped ROM cache fixture with proper cleanup.

    Used 48 times across tests. Class scope reduces instantiations
    from 48 to ~10 (79% reduction).

    Provides a real ROM cache with common caching functionality.
    Reset between tests via clear_cache() in reset_class_state fixture.
    """
    factory = RealComponentFactory(fail_on_leaks=_should_fail_on_leaks(request.config))
    cache = factory.create_rom_cache()

    def reset_cache():
        # Try multiple reset methods - different caches may use different APIs
        if hasattr(cache, 'clear'):
            with contextlib.suppress(Exception):
                cache.clear()
        elif hasattr(cache, 'clear_cache'):
            with contextlib.suppress(Exception):
                cache.clear_cache()
        elif hasattr(cache, 'reset'):
            with contextlib.suppress(Exception):
                cache.reset()

    request.addfinalizer(reset_cache)

    yield cache
    if hasattr(factory, 'cleanup'):
        factory.cleanup()


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

@pytest.fixture(scope="class")
def mock_settings_manager(
    request: FixtureRequest,
) -> Mock:
    """Class-scoped mock settings manager for performance optimization.

    Used 44 times across tests. Class scope reduces instantiations
    from 44 to ~10 (77% reduction).

    Provides a mock settings manager with common configuration methods.
    """
    manager = Mock()

    # Add common settings methods
    manager.get_setting = Mock()
    manager.set_setting = Mock()
    manager.save_settings = Mock()
    manager.load_settings = Mock()
    manager.reset_to_defaults = Mock()

    # Use platform-neutral temp directory
    temp_output = str(Path(tempfile.gettempdir()) / "test_output")

    # Add common settings with default values
    manager.get_setting.side_effect = lambda key, default=None: {
        'output_path': temp_output,
        'create_grayscale': True,
        'create_metadata': True,
        'auto_save': False,
    }.get(key, default)

    def reset_mock_state():
        with contextlib.suppress(Exception):
            manager.reset_mock(return_value=True, side_effect=True)

    request.addfinalizer(reset_mock_state)

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


@pytest.fixture(scope="class")
def mock_controller(fast_mock_main_window: MockMainWindowProtocol) -> Mock:
    """Class-scoped MOCK controller for fast unit tests.

    Uses fast_mock_main_window (MagicMock signals) for speed.
    For tests needing real signal behavior, use the real main_window
    fixture and create a real controller locally.

    Returns a Mock(spec=ExtractionController) with mocked manager dependencies.
    """
    if ExtractionController is None:
        # Return mock if controller class unavailable
        return Mock()

    # Create a mock controller to avoid manager initialization issues
    mock_ctrl = Mock(spec=ExtractionController if ExtractionController else None)
    mock_ctrl.main_window = fast_mock_main_window
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
def manager_context_factory() -> Callable[[dict[str, Any] | list[str] | None, str], ContextManager[Any]]:
    """
    Factory for creating manager contexts for dependency injection tests.

    This fixture provides a clean way to create test contexts with specific
    manager instances, enabling proper isolation between tests.

    Usage:
        def test_my_dialog(manager_context_factory):
            mock_injection = Mock()
            with manager_context_factory({"injection": mock_injection}):
                dialog = InjectionDialog()
                # dialog will use mock_injection
    """
    from core.managers.context import manager_context
    from tests.infrastructure.test_manager_factory import ManagerFactory

    def _create_context(
        managers: dict[str, Any] | list[str] | None = None,
        name: str = "test_context"
    ) -> ContextManager[Any]:
        """
        Create a manager context for testing.

        Args:
            managers: Dict of manager instances, or list of manager names
            name: Context name for debugging

        Returns:
            Context manager for use in with statements
        """
        if managers is None:
            # Create complete test context
            context_managers = {
                "extraction": ManagerFactory.create_test_extraction_manager(),
                "injection": ManagerFactory.create_test_injection_manager(),
                "session": ManagerFactory.create_test_session_manager(),
            }
        elif isinstance(managers, list):
            # Create context with specific managers
            context_managers = {}
            for manager_name in managers:
                if manager_name == "extraction":
                    context_managers[manager_name] = ManagerFactory.create_test_extraction_manager()
                elif manager_name == "injection":
                    context_managers[manager_name] = ManagerFactory.create_test_injection_manager()
                elif manager_name == "session":
                    context_managers[manager_name] = ManagerFactory.create_test_session_manager()
        else:
            # Use provided manager dict
            context_managers = managers

        return manager_context(context_managers, name=name)

    return _create_context


@pytest.fixture
def test_injection_manager() -> Mock:
    """Provide a test injection manager instance."""
    from tests.infrastructure.test_manager_factory import ManagerFactory
    return ManagerFactory.create_test_injection_manager()


@pytest.fixture
def test_extraction_manager() -> Mock:
    """Provide a test extraction manager instance."""
    from tests.infrastructure.test_manager_factory import ManagerFactory
    return ManagerFactory.create_test_extraction_manager()


@pytest.fixture
def test_session_manager() -> Mock:
    """Provide a test session manager instance."""
    from tests.infrastructure.test_manager_factory import ManagerFactory
    return ManagerFactory.create_test_session_manager()


@pytest.fixture
def complete_test_context() -> Any:
    """Provide a complete test context with all managers configured."""
    from tests.infrastructure.test_manager_factory import ManagerFactory
    return ManagerFactory.create_complete_test_context()


@pytest.fixture
def minimal_injection_context() -> Any:
    """Provide a minimal context with just injection manager for dialog tests."""
    from tests.infrastructure.test_manager_factory import ManagerFactory
    return ManagerFactory.create_minimal_test_context(["injection"], name="dialog_test")
