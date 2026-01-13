# pyright: recommended  # Use recommended mode for test files with enhanced basedpyright features
# pyright: reportPrivateUsage=false  # Allow testing private methods
# pyright: reportUnknownMemberType=warning  # Mock attributes are dynamic
# pyright: reportUnknownArgumentType=warning  # Test data may be dynamic
# pyright: reportUntypedFunctionDecorator=error  # Type all decorators
# pyright: reportUnnecessaryTypeIgnoreComment=error  # Clean up unused ignores
"""
Unified pytest configuration for SpritePal tests.

This module consolidates all test configuration into a single, modern approach
that works consistently across all environments (headless, GUI, CI/CD).

## Modular Fixture Architecture

Fixtures are organized into modular files for maintainability:
- `fixtures/qt_fixtures.py`: Qt application, main window, qtbot fixtures
- `fixtures/core_fixtures.py`: Manager fixtures, DI fixtures, state management
- `fixtures/app_context_fixtures.py`: AppContext-based fixtures (preferred)
- `fixtures/hal_fixtures.py`: HAL compression mock/real fixtures
- `fixtures/xdist_fixtures.py`: Parallel test execution support

## Parallel Execution (pytest-xdist)

Tests run in parallel by default with `-n auto`. The policy is:
- Tests marked `@pytest.mark.parallel_unsafe` are serialized
- All other tests run in parallel across workers

For serial debugging: `pytest -n 0`

## Fixture Scopes

- **qt_app**: Session scope (shared QApplication across all tests)
- **app_context**: Function scope (fresh managers per test, recommended default)
- **session_app_context**: Session scope (shared managers, requires @shared_state_safe)
- **main_window**: Function scope (real Qt signals via RealTestMainWindow)

## State Isolation

Tests using `session_app_context` require `@pytest.mark.shared_state_safe` marker
to acknowledge shared state.

For most tests, use `app_context` for complete isolation between tests.
"""

from __future__ import annotations

import os

# Set offscreen mode early
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import importlib
import importlib.abc
import tempfile
import warnings
from collections.abc import Generator
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Any
from unittest.mock import Mock

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

    from pytest import FixtureRequest

# Import consolidated mock utilities
import contextlib
import sys

import pytest

from .infrastructure.environment_detection import get_environment_info

# ============================================================================
# pytest_plugins - Import fixtures from modular files
# ============================================================================
# This imports all fixtures from the modular fixture files, making them
# available to all tests automatically.

pytest_plugins = [
    "tests.fixtures.qt_fixtures",
    "tests.fixtures.core_fixtures",
    "tests.fixtures.app_context_fixtures",  # Simplified AppContext-based fixtures
    "tests.fixtures.hal_fixtures",
    "tests.fixtures.xdist_fixtures",  # Parallel test execution support
    "tests.fixtures.test_data_fixtures",  # Consolidated ROM/VRAM test data
]


@lru_cache(maxsize=1)
def _get_environment_info():
    """Lazy-load environment info to avoid import-time side effects."""
    return get_environment_info()


def pytest_configure(config):
    """Configure pytest hooks.

    Note: Custom markers are defined in pyproject.toml (single source of truth).
    """
    # CRITICAL: Verify PySide6 is available
    try:
        import PySide6  # noqa: F401
    except ImportError as e:
        pytest.exit(
            f"FATAL: PySide6 is required for tests but not installed.\nRun: uv sync --extra dev\nImport error: {e}"
        )

    # Install QPixmap guard via import hook - guarantees guard is installed even for late Qt imports
    _install_qpixmap_guard_unconditional()


def pytest_sessionstart(session: Any) -> None:
    """Capture thread baseline at session start before any tests run.

    This is more reliable than module import time because:
    1. It runs after pytest infrastructure is fully initialized
    2. It runs before any test fixtures are set up
    3. Under xdist, each worker gets its own session start

    The baseline is stored on session.config and can be accessed by fixtures
    via request.config._thread_baseline and request.config._thread_identities.
    """
    import threading

    session.config._thread_baseline = threading.active_count()
    session.config._thread_identities = {t.ident: t.name for t in threading.enumerate() if t.ident is not None}


def _patch_qpixmap_init() -> None:
    """Patch QPixmap.__init__ to detect worker thread usage."""
    try:
        from PySide6.QtCore import QCoreApplication, QThread
        from PySide6.QtGui import QPixmap

        if hasattr(QPixmap, "_test_guard_installed"):
            return  # Already installed

        original_init = QPixmap.__init__

        def guarded_init(self, *args, **kwargs):
            app = QCoreApplication.instance()
            if app and QThread.currentThread() != app.thread():
                raise RuntimeError("CRITICAL: QPixmap created in worker thread! Use QImage or ThreadSafeTestImage.")
            original_init(self, *args, **kwargs)

        QPixmap.__init__ = guarded_init
        QPixmap._test_guard_installed = True  # pyright: ignore[reportAttributeAccessIssue] - dynamic attr for test guard
    except ImportError:
        pass  # Qt not available, skip guard


class _QPixmapGuardFinder(importlib.abc.MetaPathFinder):
    """Import hook to install QPixmap guard when PySide6.QtGui is imported.

    Uses modern find_spec protocol (PEP 451) instead of deprecated
    find_module/load_module APIs.
    """

    _installed: bool = False

    def find_spec(
        self,
        fullname: str,
        path: Any,
        target: Any = None,
    ) -> None:
        """Intercept PySide6.QtGui import and install QPixmap guard.

        Instead of returning a ModuleSpec, we:
        1. Remove ourselves from meta_path to avoid recursion
        2. Import the real module (which goes into sys.modules)
        3. Patch QPixmap
        4. Return None - the caller finds the patched module in sys.modules
        """
        if fullname != "PySide6.QtGui" or self._installed:
            return

        # Mark as installed to prevent re-triggering
        _QPixmapGuardFinder._installed = True

        # Remove ourselves from meta_path to avoid recursion
        if self in sys.meta_path:
            sys.meta_path.remove(self)

        # Import the real module (now in sys.modules)
        importlib.import_module(fullname)

        # Install the guard on QPixmap
        _patch_qpixmap_init()

        # Return None - caller finds patched module in sys.modules
        return


def _install_qpixmap_guard_unconditional() -> None:
    """Install QPixmap guard unconditionally via import hook.

    This ensures the guard is installed even for tests that import Qt late.
    Uses an import hook that triggers as soon as PySide6.QtGui is imported.
    """
    # If Qt is already imported, patch directly
    if "PySide6.QtGui" in sys.modules:
        _patch_qpixmap_init()
        return

    # Otherwise, install an import hook to patch when Qt is imported
    # Check if our hook is already installed
    if not any(isinstance(finder, _QPixmapGuardFinder) for finder in sys.meta_path):
        sys.meta_path.insert(0, _QPixmapGuardFinder())


def pytest_addoption(parser: Any) -> None:
    """Add custom command line options for SpritePal tests."""
    # Determine default leak mode: "fail" in CI, "warn" locally
    # Can be overridden by SPRITEPAL_LEAK_MODE environment variable
    is_ci = os.environ.get("CI") == "true"
    env_leak_mode = os.environ.get("SPRITEPAL_LEAK_MODE", "").lower()

    if env_leak_mode in {"fail", "warn"}:
        default_leak_mode = env_leak_mode
    else:
        # Default: fail in CI, warn locally
        default_leak_mode = "fail" if is_ci else "warn"

    parser.addoption(
        "--use-real-hal", action="store_true", default=False, help="Use real HAL process pool instead of mocks (slower)"
    )
    parser.addoption(
        "--require-real-hal",
        action="store_true",
        default=False,
        help="Fail (don't skip) if real HAL binaries not found for @real_hal tests",
    )
    parser.addoption(
        "--leak-mode",
        action="store",
        choices=["fail", "warn"],
        default=default_leak_mode,
        help=f"Leak policy: fail or warn for resource/thread leaks. Default: {'fail' if is_ci else 'warn'} ({'CI' if is_ci else 'local'}). Override with SPRITEPAL_LEAK_MODE env var.",
    )
    # NOTE: --run-segfault-tests option removed - segfault-prone tests have been deleted


def pytest_collection_modifyitems(config: Any, items: list[Any]) -> None:
    """Validate marker usage and enforce PARALLEL BY DEFAULT xdist policy.

    This hook performs validation and configuration in a single pass over items.
    """
    # Initialize tracking
    real_hal_nodeids = []

    # Check xdist status once
    xdist_active = config.pluginmanager.has_plugin("xdist")
    worker_count = None
    if xdist_active:
        try:
            worker_count = config.getoption("-n", default=None)
        except ValueError:
            xdist_active = False

    serial_group = pytest.mark.xdist_group("serial") if xdist_active and worker_count and worker_count != "0" else None

    for item in items:
        # 1. Track real_hal tests
        if item.get_closest_marker("real_hal"):
            real_hal_nodeids.append(item.nodeid)

        # 2. Validate skip_thread_cleanup markers
        skip_marker = item.get_closest_marker("skip_thread_cleanup")
        if skip_marker is not None and not skip_marker.kwargs.get("reason"):
            raise pytest.UsageError(f"Test {item.nodeid} uses @pytest.mark.skip_thread_cleanup without a reason.")

        # 3. Validate allows_registry_state markers
        allow_marker = item.get_closest_marker("allows_registry_state")
        if allow_marker is not None and not allow_marker.kwargs.get("reason"):
            raise pytest.UsageError(f"Test {item.nodeid} uses @pytest.mark.allows_registry_state without a reason.")

        # 4. Apply xdist serialization
        if serial_group and not item.get_closest_marker("xdist_group"):
            if item.get_closest_marker("parallel_unsafe"):
                item.add_marker(serial_group)

    # Store results on config
    config._real_hal_test_count = len(real_hal_nodeids)
    config._real_hal_test_nodeids = real_hal_nodeids


def pytest_sessionfinish(session: Any, exitstatus: int) -> None:
    """Clean up all singletons at session end to prevent state pollution.

    Uses the centralized reset_all_singletons() helper to ensure consistent
    cleanup across the test suite.
    """
    from tests.fixtures.core_fixtures import reset_all_singletons

    reset_all_singletons()


def pytest_terminal_summary(terminalreporter: Any, exitstatus: int, config: Any) -> None:
    """Report real_hal test execution summary for CI visibility.

    Warns if real_hal tests were skipped due to missing HAL binaries,
    making silent failures visible in CI output.
    """
    if not hasattr(config, "_real_hal_test_count"):
        return

    total_count = config._real_hal_test_count
    if total_count == 0:
        return

    # Count skipped real_hal tests by checking skip reasons
    skipped_real_hal = 0
    skipped_stats = terminalreporter.stats.get("skipped", [])
    real_hal_nodeids = set(getattr(config, "_real_hal_test_nodeids", []))

    for report in skipped_stats:
        # Check if this skipped test is a real_hal test
        if report.nodeid in real_hal_nodeids:
            skipped_real_hal += 1

    if skipped_real_hal > 0:
        terminalreporter.write_line("")
        terminalreporter.write_line(
            f"WARNING: {skipped_real_hal}/{total_count} @real_hal tests were SKIPPED (HAL binaries not found)",
            yellow=True,
        )
        terminalreporter.write_line(
            "  Set SPRITEPAL_EXHAL_PATH and SPRITEPAL_INHAL_PATH, or use --require-real-hal to fail instead",
            yellow=True,
        )


def pytest_runtest_setup(item: Any) -> None:
    """Record registry state before test runs.

    Always checks actual registry state to correctly attribute pollution.
    Tests that inherit dirty state from previous tests are not blamed;
    only tests that CHANGE state from clean to dirty are flagged in teardown.

    NOTE: This hook runs BEFORE fixtures, so we cannot fail here for tests
    using cleanup fixtures (like isolated_managers) - the fixture hasn't had
    a chance to clean the registry yet. All enforcement happens in teardown.
    """
    # Always check actual registry state - don't assume
    try:
        from core.managers import is_clean

        item._registry_was_clean = is_clean()
    except ImportError:
        item._registry_was_clean = True  # Assume clean if can't import


def pytest_runtest_teardown(item: Any, nextitem: Any) -> None:
    """Enforce manager cleanup after each test.

    This hook converts documentation ("use isolated_managers") into runtime
    enforcement. Tests that DIRTY the registry (change it from clean to dirty)
    without using a manager fixture will fail.

    This catches:
    - Tests that initialize managers without cleanup fixtures
    - Accidental state pollution between tests
    - Direct manager instantiation that bypasses fixture detection

    This does NOT catch:
    - Tests that inherit dirty state from previous tests (use isolated_managers to fix)
    - Tests explicitly marked to allow registry state
    """
    # Skip enforcement for tests that opt out
    if item.get_closest_marker("allows_registry_state"):
        return

    # Skip for tests that use manager fixtures (they manage lifecycle)
    fixture_names = set(getattr(item, "fixturenames", []))
    cleanup_fixtures = {
        "managers_initialized",
        "app_context",  # Function-scoped isolated context
        "session_app_context",  # Session-scoped shared context
    }
    if cleanup_fixtures.intersection(fixture_names):
        return  # Test uses a fixture that manages registry lifecycle

    # Check unconditionally: did THIS test dirty the registry?
    # Note: Previous version had a performance optimization that skipped this check
    # for tests without known manager-related fixtures. That created a gap where
    # direct manager instantiation could bypass detection. Now we always check.
    try:
        from core.managers import is_clean

        was_clean = getattr(item, "_registry_was_clean", True)
        is_clean_now = is_clean()

        # Only fail if the test changed state from clean to dirty
        if was_clean and not is_clean_now:
            pytest.fail(
                f"Test '{item.name}' initialized managers without a manager fixture.\n"
                "Fix: Use isolated_managers fixture, or add "
                "@pytest.mark.allows_registry_state if intentional."
            )
    except ImportError:
        pass  # Manager module not available, skip check


# ============================================================================
# Test Data Factories (not in modular files - specific to test data creation)
# ============================================================================
# NOTE: xdist registry cleanliness check has been consolidated into
# pytest_runtest_setup hook above for better performance (single import)


@pytest.fixture
def test_data_factory() -> Callable[..., bytearray]:
    """
    Factory for creating consistent test data structures.

    Provides a unified way to create VRAM, CGRAM, and OAM test data
    with realistic patterns used across the test suite.
    """

    def _create_test_data(data_type: str, size: int | None = None, **kwargs: Any) -> bytearray:
        """
        Create test data of specified type.

        Args:
            data_type: Type of data - 'vram', 'cgram', 'oam'
            size: Size override (uses defaults if None)
            **kwargs: Additional parameters for data generation

        Returns:
            Bytearray with realistic test data
        """
        if data_type == "vram":
            # Lazy import constants to reduce startup overhead
            from utils.constants import BYTES_PER_TILE, VRAM_SPRITE_OFFSET

            default_size = 0x10000  # 64KB
            data = bytearray(size or default_size)

            # Add realistic sprite data at VRAM offset
            start_offset = kwargs.get("sprite_offset", VRAM_SPRITE_OFFSET)
            tile_count = kwargs.get("tile_count", 10)

            for i in range(tile_count):
                offset = start_offset + i * BYTES_PER_TILE
                if offset + BYTES_PER_TILE <= len(data):
                    for j in range(BYTES_PER_TILE):
                        data[offset + j] = (i + j) % 256

            return data

        if data_type == "cgram":
            default_size = 512  # 256 colors * 2 bytes
            data = bytearray(size or default_size)

            # Add realistic palette data (BGR555 format)
            for i in range(0, len(data), 2):
                data[i] = i % 256
                data[i + 1] = (i // 2) % 32

            return data

        if data_type == "oam":
            default_size = 544  # Standard OAM size
            data = bytearray(size or default_size)

            # Add realistic OAM data (sprite attributes)
            for i in range(0, min(len(data), 512), 4):  # 4 bytes per entry
                data[i] = i % 256  # X position
                data[i + 1] = i % 224  # Y position
                data[i + 2] = i % 256  # Tile index
                data[i + 3] = 0x20  # Attributes

            return data

        raise ValueError(f"Unknown data type: {data_type}")

    return _create_test_data


@pytest.fixture
def temp_files() -> Iterator[Callable[[bytes, str], str]]:
    """
    Factory for creating temporary test files with automatic cleanup.

    Creates temporary files with test data and ensures they are
    properly cleaned up after test completion.
    """
    created_files: list[str] = []

    def _create_temp_file(data: bytes, suffix: str = ".dmp") -> str:
        """Create a temporary file with the given data."""
        temp_file = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
        temp_file.write(data)
        temp_file.close()
        created_files.append(temp_file.name)
        return temp_file.name

    yield _create_temp_file

    # Cleanup
    for file_path in created_files:
        try:
            Path(file_path).unlink(missing_ok=True)
        except OSError:
            pass  # File might already be deleted


@pytest.fixture
def standard_test_params(
    test_data_factory: Callable[..., bytearray],
    temp_files: Callable[[bytes, str], str],
    tmp_path: Path,
) -> dict[str, Any]:
    """
    Create standard test parameters used across integration tests.

    Provides the common set of test parameters that many integration
    tests use, reducing duplication in test setup.
    """
    # Create standard test data
    vram_data = test_data_factory("vram")
    cgram_data = test_data_factory("cgram")
    oam_data = test_data_factory("oam")

    # Create temporary files - convert bytearray to bytes for temp_files
    vram_file = temp_files(bytes(vram_data), ".dmp")
    cgram_file = temp_files(bytes(cgram_data), ".dmp")
    oam_file = temp_files(bytes(oam_data), ".dmp")

    return {
        "vram_path": vram_file,
        "cgram_path": cgram_file,
        "oam_path": oam_file,
        "output_base": str(tmp_path / "output"),
        "create_grayscale": True,
        "create_metadata": True,
        "vram_data": vram_data,
        "cgram_data": cgram_data,
        "oam_data": oam_data,
    }


# ============================================================================
# Function-scoped fixtures for proper test isolation
# ============================================================================


@pytest.fixture(scope="function")
def mock_manager_registry() -> Generator[Mock, None, None]:
    """Function-scoped mock registry for proper test isolation.

    Changed from module-scope to function-scope to ensure:
    - Each test gets a fresh mock instance
    - No call history leaks between tests
    - No return value pollution between tests

    The ~80ms overhead (81 tests × ~1ms per Mock) is negligible compared
    to the determinism benefit of fresh state per test.
    """
    registry = Mock()

    # Add common registry methods
    registry.get_manager = Mock()
    registry.register_manager = Mock()
    registry.is_initialized = Mock(return_value=True)
    registry.cleanup = Mock()

    # Add manager getters
    registry.get_extraction_manager = Mock()
    registry.get_injection_manager = Mock()
    registry.get_session_manager = Mock()

    yield registry
    # No cleanup needed - fixture is discarded after each test


# ============================================================================
# Qt Threading Safety Fixtures
# ============================================================================
# NOTE: QPixmap threading guard is installed via import hook in pytest_configure
# (_install_qpixmap_guard_unconditional). The import hook guarantees the guard
# is installed when PySide6.QtGui is imported, removing the need for a separate
# autouse fixture to verify/fallback.


@pytest.fixture(autouse=True)
def skip_requires_display(request: FixtureRequest):
    """Skip tests marked with @pytest.mark.requires_display when running headless.

    This fixture provides a clean skip mechanism for tests that require a real
    display (not offscreen mode). Use this instead of xfail for environment
    capabilities.

    Example:
        @pytest.mark.requires_display
        def test_real_dialog():
            '''This test needs a real display.'''
            ...  # Skips cleanly in CI/offscreen, runs with real display
    """
    marker = request.node.get_closest_marker("requires_display")
    if marker is not None:
        # Check if running in offscreen mode
        qpa_platform = os.environ.get("QT_QPA_PLATFORM", "")
        if qpa_platform == "offscreen":
            pytest.skip("Test requires real display (not offscreen mode)")


# ============================================================================
# Test Cleanup Verification
# ============================================================================


@pytest.fixture(autouse=True)
def verify_cleanup(request: FixtureRequest) -> Generator[None, None, None]:
    """Verify that test cleanup actually succeeded (autouse for Qt/manager tests).

    This fixture checks for lingering manager state (active operations) after tests
    complete. It helps identify incomplete cleanup that could cause flaky tests.

    Activation: Runs automatically for tests using Qt or manager fixtures.
    Behavior: Warns or fails based on --leak-mode (consistent with cleanup_workers).
    """
    # Only run for tests that use Qt or manager fixtures
    relevant_fixtures = {
        "qtbot",
        "qt_app",
        "qapp",
        "hal_pool",
        "cleanup_singleton",
        "app_context",
        "session_app_context",
        "managers",
        "real_factory",
        "real_extraction_manager",
        "real_injection_manager",
    }
    fixture_names = set(getattr(request, "fixturenames", []))

    if not relevant_fixtures.intersection(fixture_names):
        yield
        return

    yield

    # Verify no lingering manager state
    from core.managers import is_initialized

    if not is_initialized():
        return

    leak_mode = request.config.getoption("--leak-mode", default="fail")
    leaks_found: list[str] = []

    # Check for active operations via AppContext
    try:
        from core.app_context import get_app_context_optional

        ctx = get_app_context_optional()
        if ctx:
            ops_mgr = ctx.core_operations_manager
            if hasattr(ops_mgr, "has_active_operations") and ops_mgr.has_active_operations():
                leaks_found.append("CoreOperationsManager has active operations (not cleaned up)")
    except ImportError:
        pass  # AppContext not available

    if leaks_found:
        message = f"Test '{request.node.name}' left manager state leaks:\n  - " + "\n  - ".join(leaks_found)
        if leak_mode == "warn":
            warnings.warn(message, ResourceWarning, stacklevel=2)
        else:
            pytest.fail(message)


@pytest.fixture(autouse=True)
def enforce_shared_state_safe(request: FixtureRequest) -> Generator[None, None, None]:
    """Enforce that session_app_context usage requires @pytest.mark.shared_state_safe.

    This fixture validates at test execution time that any test using session_app_context
    has the shared_state_safe marker, ensuring developers consciously acknowledge
    they're using shared state.

    The marker requirement ensures:
    1. Developers understand session_app_context shares state across tests
    2. Tests are reviewed for statelessness before using session_app_context
    3. Order-dependent test failures are easier to diagnose
    """
    # Only check tests that use session_app_context
    fixture_names = set(getattr(request, "fixturenames", []))
    if "session_app_context" not in fixture_names:
        yield
        return

    # Require the marker
    if not request.node.get_closest_marker("shared_state_safe"):
        pytest.fail(
            f"Test '{request.node.name}' uses session_app_context but lacks "
            "@pytest.mark.shared_state_safe marker. Either:\n"
            "  1. Add @pytest.mark.shared_state_safe (if test is verified stateless), or\n"
            "  2. Use app_context instead (recommended for most tests)"
        )

    yield
    # No post-test state validation - isolation is guaranteed by fixture scoping


# ===========================================================================================
# Wait Helper Fixtures for Eliminating Flaky qtbot.wait() Calls
# ===========================================================================================
# These fixtures are consolidated in tests/fixtures/qt_waits.py and re-exported here.
# See that module for implementation details.
#
# Usage: Add fixture parameter to test method, then use instead of qtbot.wait()
# Example:
#   def test_something(self, qtbot, wait_for_signal_processed):
#       button.click()
#       wait_for_signal_processed()  # Instead of qtbot.wait(100)
# ===========================================================================================

# Re-export wait helpers from shared module
from tests.fixtures.qt_waits import (
    process_events,
    wait_for,
    wait_for_layout_update,
    wait_for_signal_processed,
    wait_for_widget_ready,
)
