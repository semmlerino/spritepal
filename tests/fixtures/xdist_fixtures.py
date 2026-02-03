"""
pytest-xdist fixtures and hooks for parallel test execution.

This module provides worker-level isolation for parallel testing:
- Each worker gets its own temp directory for settings/cache
- Environment variables set per-worker to isolate globals
- Hooks for proper worker initialization and cleanup

Usage:
    # Run all tests in parallel (default behavior)
    QT_QPA_PLATFORM=offscreen pytest -n auto

    # Run serially for debugging
    QT_QPA_PLATFORM=offscreen pytest -n 0

Architecture:
    - With pytest-xdist, each worker is a separate Python process
    - Each worker gets its own session (session-scoped fixtures run per-worker)
    - Module-level singletons are naturally isolated (separate process memory)
    - Filesystem resources need explicit isolation via tmp_path/worker_temp_root

PARALLEL BY DEFAULT Policy:
    Tests run in parallel by default. Only tests marked @pytest.mark.parallel_unsafe
    are serialized via xdist groups. See pytest_collection_modifyitems in conftest.py.
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


# ============================================================================
# Fixtures for Worker Isolation
# ============================================================================


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
