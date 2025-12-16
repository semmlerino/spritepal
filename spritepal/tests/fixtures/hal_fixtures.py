# pyright: recommended
"""
HAL compression fixtures for SpritePal tests.

This module provides fixtures for HAL compression testing with support for
both mock and real HAL implementations.

Usage:
    - By default, fixtures return mock implementations (fast, no dependencies)
    - Use `@pytest.mark.real_hal` marker to get real implementations
    - Use `--use-real-hal` CLI option to force real HAL for all tests

Fixtures:
    - hal_pool: HAL process pool (mock or real)
    - hal_compressor: HAL compressor (mock or real)
    - mock_hal: Explicit mock that patches HAL imports
    - reset_hal_singletons: Reset HAL state between tests
    - mock_hal_tools: Create mock exhal/inhal executables
    - hal_test_data: Standard test data patterns
"""
from __future__ import annotations

import contextlib
import os
import shutil
from collections.abc import Generator
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from tests.infrastructure.mock_hal import (
    MockHALCompressor,
    MockHALProcessPool,
    create_mock_hal_tools,
)

if TYPE_CHECKING:
    from pytest import FixtureRequest


def _find_real_hal_binaries() -> tuple[str, str] | None:
    """Try to find real exhal/inhal binaries.

    Looks for binaries in:
    1. Environment variables (SPRITEPAL_EXHAL_PATH, SPRITEPAL_INHAL_PATH)
    2. System PATH via shutil.which()
    3. Common locations relative to project root

    Returns tuple of (exhal_path, inhal_path) or None if not found.
    """
    # Try environment variables first
    exhal_path = os.environ.get("SPRITEPAL_EXHAL_PATH")
    inhal_path = os.environ.get("SPRITEPAL_INHAL_PATH")

    if exhal_path and inhal_path:
        if Path(exhal_path).exists() and Path(inhal_path).exists():
            return (exhal_path, inhal_path)

    # Try system PATH
    exhal_path = shutil.which("exhal")
    inhal_path = shutil.which("inhal")

    if exhal_path and inhal_path:
        return (exhal_path, inhal_path)

    # Try common locations relative to project
    project_root = Path(__file__).parent.parent.parent.parent  # exhal-master
    common_locations = [
        project_root / "bin",
        project_root,
        Path.home() / ".local" / "bin",
    ]

    for loc in common_locations:
        exhal_candidate = loc / "exhal"
        inhal_candidate = loc / "inhal"
        # Also check for Windows executables
        if not exhal_candidate.exists():
            exhal_candidate = loc / "exhal.exe"
        if not inhal_candidate.exists():
            inhal_candidate = loc / "inhal.exe"

        if exhal_candidate.exists() and inhal_candidate.exists():
            return (str(exhal_candidate), str(inhal_candidate))

    return None


@pytest.fixture(autouse=True)
def reset_hal_singletons(request: FixtureRequest) -> Generator[None, None, None]:
    """
    Reset HAL singletons after tests that USE HAL (autouse, opt-in by fixture usage).

    This prevents HAL state (statistics, mock configuration, failure modes)
    from leaking between tests. Only runs for tests that actually use HAL fixtures
    to avoid unnecessary overhead for non-HAL tests (~1000 tests don't need this).

    HAL fixtures that trigger this: hal_pool, hal_compressor, mock_hal
    HAL marker that triggers this: @pytest.mark.real_hal

    Opt-out markers:
        @pytest.mark.skip_hal_reset - Skip for tests that manage HAL lifecycle manually
        @pytest.mark.no_hal - Skip for non-HAL tests
    """
    markers = [m.name for m in request.node.iter_markers()]

    # Opt-OUT: Skip if explicitly marked
    if 'skip_hal_reset' in markers or 'no_hal' in markers:
        yield
        return

    # Only run for tests that use HAL fixtures or have real_hal marker
    hal_fixtures = {'hal_pool', 'hal_compressor', 'mock_hal'}
    fixture_names = set(getattr(request, 'fixturenames', []))
    uses_hal = bool(hal_fixtures & fixture_names)
    has_hal_marker = 'real_hal' in markers

    if not (uses_hal or has_hal_marker):
        # Non-HAL test: skip reset entirely for efficiency
        yield
        return

    # HAL test: let it run, then reset
    yield

    # Reset HAL singletons using centralized helper
    from tests.fixtures.core_fixtures import reset_hal_singletons_only
    reset_hal_singletons_only()


@pytest.fixture
def hal_pool(request: FixtureRequest, tmp_path: Path) -> Generator[MockHALProcessPool, None, None]:
    """
    Provide HAL process pool - mock or real based on test markers or CLI option.

    Selection logic (in order of precedence):
    1. `--use-real-hal` CLI option forces real HAL for all tests
    2. `@pytest.mark.real_hal` marker on test gets real HAL
    3. Default: mock HAL implementation (fast, no external dependencies)

    When real HAL is requested:
    - First tries to find real exhal/inhal binaries
    - If not found, skips the test with informative message
    - Set SPRITEPAL_EXHAL_PATH and SPRITEPAL_INHAL_PATH to specify binary locations
    """
    # Check CLI option first, then marker
    use_real = (
        request.config.getoption("--use-real-hal", default=False) or
        request.node.get_closest_marker("real_hal") is not None
    )

    if use_real:
        # Use real HAL process pool
        from core.hal_compression import HALProcessPool

        # Try to find real binaries first
        real_binaries = _find_real_hal_binaries()
        if real_binaries is None:
            pytest.skip(
                "Real HAL binaries not found. "
                "Set SPRITEPAL_EXHAL_PATH and SPRITEPAL_INHAL_PATH, "
                "or install exhal/inhal to PATH."
            )

        exhal_path, inhal_path = real_binaries

        # Reset singleton before test
        HALProcessPool.reset_singleton()
        pool = HALProcessPool()
        pool.initialize(exhal_path, inhal_path)

        yield pool  # type: ignore[misc]

        # Cleanup
        pool.shutdown()
        HALProcessPool.reset_singleton()
    else:
        # Use mock HAL process pool
        MockHALProcessPool.reset_singleton()
        pool = MockHALProcessPool()

        # Initialize with mock paths
        pool.initialize("mock_exhal", "mock_inhal")

        yield pool

        # Cleanup
        pool.shutdown()
        MockHALProcessPool.reset_singleton()


@pytest.fixture
def hal_compressor(request: FixtureRequest, tmp_path: Path) -> Generator[MockHALCompressor, None, None]:
    """
    Provide HAL compressor - mock or real based on test markers or CLI option.

    Selection logic (in order of precedence):
    1. `--use-real-hal` CLI option forces real HAL for all tests
    2. `@pytest.mark.real_hal` marker on test gets real HAL
    3. Default: mock HAL implementation (fast, no external dependencies)

    When real HAL is requested:
    - First tries to find real exhal/inhal binaries
    - If not found, skips the test with informative message
    - Set SPRITEPAL_EXHAL_PATH and SPRITEPAL_INHAL_PATH to specify binary locations
    """
    # Check CLI option first, then marker
    use_real = (
        request.config.getoption("--use-real-hal", default=False) or
        request.node.get_closest_marker("real_hal") is not None
    )

    if use_real:
        # Use real HAL compressor
        from core.hal_compression import HALCompressor

        # Try to find real binaries first
        real_binaries = _find_real_hal_binaries()
        if real_binaries is None:
            pytest.skip(
                "Real HAL binaries not found. "
                "Set SPRITEPAL_EXHAL_PATH and SPRITEPAL_INHAL_PATH, "
                "or install exhal/inhal to PATH."
            )

        exhal_path, inhal_path = real_binaries
        compressor = HALCompressor(exhal_path, inhal_path, use_pool=True)

        yield compressor  # type: ignore[misc]

        # Cleanup if pool was initialized
        if hasattr(compressor, '_pool') and compressor._pool:
            compressor._pool.shutdown()
    else:
        # Use mock HAL compressor
        compressor = MockHALCompressor(use_pool=True)

        yield compressor

        # Cleanup
        if compressor._pool:
            compressor._pool.shutdown()


@pytest.fixture
def mock_hal(monkeypatch: pytest.MonkeyPatch) -> Generator[None, None, None]:
    """
    Explicit HAL mock fixture - tests must request this to use mocked HAL.

    This fixture patches the HAL module to use mock implementations.
    Tests that need fast HAL mocking (e.g., unit tests) should explicitly
    request this fixture.

    Usage:
        def test_something_with_hal(mock_hal):
            # HAL is now mocked
            ...

        @pytest.mark.usefixtures("mock_hal")
        class TestHALDependentCode:
            # All tests in this class use mocked HAL
            ...

    For tests that need real HAL, simply don't request this fixture.

    IMPORTANT: This fixture patches HALCompressor at ALL import locations,
    not just the source module. Python's `from X import Y` creates a new
    binding in the importing module, so we must patch each location.
    """
    # Reset any existing real HAL singletons FIRST (before patching)
    with contextlib.suppress(Exception):
        from core.hal_compression import HALProcessPool as RealHALProcessPool
        RealHALProcessPool.reset_singleton()

    # Patch at source module
    monkeypatch.setattr("core.hal_compression.HALProcessPool", MockHALProcessPool)
    monkeypatch.setattr("core.hal_compression.HALCompressor", MockHALCompressor)

    # Patch at ALL import locations in production code
    # (Python's `from X import Y` creates local bindings that need separate patches)
    monkeypatch.setattr("core.rom_extractor.HALCompressor", MockHALCompressor)
    monkeypatch.setattr("core.rom_injector.HALCompressor", MockHALCompressor)

    yield

    # Cleanup singletons after test
    with contextlib.suppress(Exception):
        MockHALProcessPool.reset_singleton()
    # Also reset real HAL singletons in case they were created
    with contextlib.suppress(Exception):
        from core.hal_compression import HALProcessPool as RealHALProcessPool
        RealHALProcessPool.reset_singleton()


@pytest.fixture
def mock_hal_tools(tmp_path: Path) -> tuple[Path, Path]:
    """
    Create mock HAL tool executables for testing.

    Returns tuple of (exhal_path, inhal_path).
    """
    return create_mock_hal_tools(tmp_path)


@pytest.fixture
def hal_test_data() -> dict[str, bytes]:
    """
    Provide standard test data for HAL compression tests.

    Returns dict with various test data patterns.
    """
    return {
        "small": b"Small test data for compression" * 10,
        "medium": b"M" * 0x1000,  # 4KB
        "large": b"L" * 0x8000,   # 32KB
        "pattern": bytes([(i * 17) % 256 for i in range(0x2000)]),  # 8KB pattern
        "zeros": b"\x00" * 0x1000,  # 4KB zeros
        "ones": b"\xff" * 0x1000,   # 4KB ones
    }


@pytest.fixture
def hal_golden_data() -> dict[str, dict]:
    """
    Provide golden HAL test data with recorded checksums.

    Returns dict mapping test names to:
    - input_data: bytes
    - expected_sha256: str (checksum of expected output, if recorded)
    - expected_size: int (expected output size, if recorded)

    If checksums.json has no entries (not yet regenerated with real HAL),
    returns empty dict and tests should handle accordingly.
    """
    import json
    from pathlib import Path

    golden_dir = Path(__file__).parent / "golden_data" / "hal"
    checksums_file = golden_dir / "checksums.json"

    if not checksums_file.exists():
        return {}

    with open(checksums_file) as f:
        checksums = json.load(f)

    if not checksums.get("entries"):
        # No golden data yet - return test patterns without expected checksums
        return {}

    result: dict[str, dict] = {}
    for name, entry in checksums["entries"].items():
        input_file = golden_dir / entry.get("input_file", "")
        if input_file.exists():
            result[name] = {
                "input_data": input_file.read_bytes(),
                "expected_sha256": entry.get("output_sha256"),
                "expected_size": entry.get("output_size"),
                "compression_ratio": entry.get("compression_ratio"),
            }

    return result
