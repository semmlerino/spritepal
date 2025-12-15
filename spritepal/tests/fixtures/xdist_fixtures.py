"""
pytest-xdist fixtures and hooks for parallel test execution.

This module provides worker-level isolation for parallel testing:
- Each worker gets its own temp directory for settings/cache
- Environment variables set per-worker to isolate globals
- Hooks for proper worker initialization and cleanup

Usage:
    # Run only parallel_safe tests in parallel
    QT_QPA_PLATFORM=offscreen pytest -m parallel_safe -n auto

    # Run all tests, but only parallel_safe ones distributed
    QT_QPA_PLATFORM=offscreen pytest -n auto

Architecture:
    - With pytest-xdist, each worker is a separate Python process
    - Each worker gets its own session (session-scoped fixtures run per-worker)
    - Module-level singletons are naturally isolated (separate process memory)
    - Filesystem resources need explicit isolation via tmp_path/worker_temp_root

Conservative Approach:
    Only tests marked @pytest.mark.parallel_safe are distributed across workers.
    All other tests run on the controller or a single worker for safety.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from collections.abc import Iterator


# ============================================================================
# Worker Detection Utilities
# ============================================================================


def get_xdist_worker_id() -> str | None:
    """Get the xdist worker ID, or None if not running in xdist.

    Worker IDs are like "gw0", "gw1", etc.
    Returns None when running pytest without -n flag.
    """
    return os.environ.get("PYTEST_XDIST_WORKER")


def is_xdist_worker() -> bool:
    """Check if running as an xdist worker process.

    Returns True for worker processes (gw0, gw1, etc.)
    Returns False for the controller process or single-process pytest.
    """
    return get_xdist_worker_id() is not None


def is_xdist_controller() -> bool:
    """Check if running as the xdist controller or single-process pytest.

    The controller orchestrates test distribution but doesn't run tests itself.
    In single-process mode (no -n flag), this also returns True.
    """
    return os.environ.get("PYTEST_XDIST_WORKER") is None


def get_worker_count() -> int:
    """Get the total number of xdist workers.

    Returns 0 if not running under xdist.
    """
    worker_count = os.environ.get("PYTEST_XDIST_WORKER_COUNT")
    if worker_count:
        return int(worker_count)
    return 0


# ============================================================================
# Fixtures for Worker Isolation
# ============================================================================


@pytest.fixture(scope="session")
def xdist_worker_id() -> str | None:
    """Provide the xdist worker ID as a fixture.

    Useful for tests that need to know which worker they're running on,
    e.g., for debugging parallel test issues.
    """
    return get_xdist_worker_id()


@pytest.fixture(scope="session")
def worker_temp_root(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Session-scoped worker temp directory for isolated resources.

    Under xdist, each worker gets its own session, so this fixture
    naturally provides a unique temp directory per worker.

    Use this for resources that need to persist across multiple tests
    within a single worker's session (e.g., settings files, caches).

    For per-test isolation, use the standard `tmp_path` fixture instead.
    """
    worker_id = get_xdist_worker_id() or "main"
    return tmp_path_factory.mktemp(f"worker_{worker_id}")


@pytest.fixture(scope="session", autouse=True)
def configure_worker_environment(worker_temp_root: Path) -> Iterator[None]:
    """Configure environment variables for worker isolation.

    This runs automatically at session start for each worker,
    setting up isolated paths for settings and cache directories.

    Only modifies environment under xdist (when PYTEST_XDIST_WORKER is set).
    In single-process mode, the standard tmp_path mechanisms are sufficient.

    Environment variables set:
    - SPRITEPAL_SETTINGS_DIR: Worker-specific settings directory
    - SPRITEPAL_CACHE_DIR: Worker-specific cache directory
    - SPRITEPAL_LOG_DIR: Worker-specific log directory
    - SPRITEPAL_WORKER_ID: Current worker ID (for debugging)
    """
    worker_id = get_xdist_worker_id()

    if worker_id:
        # Set worker-specific environment for isolation
        settings_dir = worker_temp_root / "settings"
        cache_dir = worker_temp_root / "cache"
        log_dir = worker_temp_root / "logs"

        settings_dir.mkdir(exist_ok=True)
        cache_dir.mkdir(exist_ok=True)
        log_dir.mkdir(exist_ok=True)

        os.environ["SPRITEPAL_SETTINGS_DIR"] = str(settings_dir)
        os.environ["SPRITEPAL_CACHE_DIR"] = str(cache_dir)
        os.environ["SPRITEPAL_LOG_DIR"] = str(log_dir)
        os.environ["SPRITEPAL_WORKER_ID"] = worker_id

    yield

    # Cleanup environment on session end
    if worker_id:
        os.environ.pop("SPRITEPAL_SETTINGS_DIR", None)
        os.environ.pop("SPRITEPAL_CACHE_DIR", None)
        os.environ.pop("SPRITEPAL_LOG_DIR", None)
        os.environ.pop("SPRITEPAL_WORKER_ID", None)


# ============================================================================
# Validation Fixtures
# ============================================================================


@pytest.fixture
def require_parallel_safe(request: pytest.FixtureRequest) -> None:
    """Fixture that validates the test is marked parallel_safe.

    Use this in fixtures that should only be used with parallel-safe tests.
    Raises pytest.fail if the test lacks the @pytest.mark.parallel_safe marker.

    Example:
        @pytest.fixture
        def my_isolated_resource(require_parallel_safe):
            # This will fail if test isn't marked parallel_safe
            yield create_resource()
    """
    marker = request.node.get_closest_marker("parallel_safe")
    if marker is None:
        pytest.fail(
            f"Test {request.node.nodeid} uses a parallel-only fixture "
            "but is not marked @pytest.mark.parallel_safe"
        )


@pytest.fixture
def validate_parallel_isolation(request: pytest.FixtureRequest) -> None:
    """Validate that a parallel_safe test doesn't use unsafe fixtures.

    Checks that the test:
    1. Does not use session_managers (should use isolated_managers)
    2. Does not use class_managers
    3. Uses tmp_path for any file operations

    This fixture is automatically applied to parallel_safe tests via conftest.py.
    """
    marker = request.node.get_closest_marker("parallel_safe")
    if marker is None:
        return  # Skip validation for non-parallel tests

    # Get all fixture names used by this test
    fixture_names = set(request.fixturenames)

    # Check for unsafe fixtures
    unsafe_fixtures = {"session_managers", "class_managers"}
    used_unsafe = fixture_names & unsafe_fixtures

    if used_unsafe:
        pytest.fail(
            f"Test {request.node.nodeid} is marked @pytest.mark.parallel_safe "
            f"but uses unsafe fixtures: {used_unsafe}. "
            "Use isolated_managers instead for parallel-safe tests."
        )

    # Recommend tmp_path if any file operations are likely
    if "isolated_managers" in fixture_names and "tmp_path" not in fixture_names:
        # This is a soft warning, not a failure
        import warnings

        warnings.warn(
            f"Test {request.node.nodeid} uses isolated_managers but not tmp_path. "
            "Consider using tmp_path for any file operations to ensure isolation.",
            stacklevel=2,
        )
