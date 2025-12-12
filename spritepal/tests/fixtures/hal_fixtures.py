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
from collections.abc import Generator
from typing import TYPE_CHECKING

import pytest

from tests.infrastructure.mock_hal import (
    MockHALCompressor,
    MockHALProcessPool,
    create_mock_hal_tools,
)

if TYPE_CHECKING:
    from pathlib import Path

    from pytest import FixtureRequest


@pytest.fixture(autouse=True)
def reset_hal_singletons(request: FixtureRequest) -> Generator[None, None, None]:
    """
    Reset HAL singletons after EVERY test (autouse).

    This prevents HAL state (statistics, mock configuration, failure modes)
    from leaking between tests. Previously this was opt-in; now it runs
    automatically to catch HAL state pollution.

    Opt-out markers:
        @pytest.mark.skip_hal_reset - Skip for tests that manage HAL lifecycle manually
        @pytest.mark.no_hal - Skip for non-HAL tests
    """
    markers = [m.name for m in request.node.iter_markers()]

    # Opt-OUT: Skip if explicitly marked
    if 'skip_hal_reset' in markers or 'no_hal' in markers:
        yield
        return

    # Let the test run
    yield

    # Reset both real and mock HAL singletons after each test
    with contextlib.suppress(Exception):
        MockHALProcessPool.reset_singleton()
    with contextlib.suppress(Exception):
        from core.hal_compression import HALProcessPool
        HALProcessPool.reset_singleton()


@pytest.fixture
def hal_pool(request: FixtureRequest, tmp_path: Path) -> Generator[MockHALProcessPool, None, None]:
    """
    Provide HAL process pool - mock or real based on test markers or CLI option.

    Selection logic (in order of precedence):
    1. `--use-real-hal` CLI option forces real HAL for all tests
    2. `@pytest.mark.real_hal` marker on test gets real HAL
    3. Default: mock HAL implementation (fast, no external dependencies)

    Tests marked with @pytest.mark.real_hal will get the real pool.
    All other tests get the fast mock implementation.
    """
    # Check CLI option first, then marker
    use_real = (
        request.config.getoption("--use-real-hal", default=False) or
        request.node.get_closest_marker("real_hal") is not None
    )

    if use_real:
        # Use real HAL process pool
        from core.hal_compression import HALProcessPool

        # Reset singleton before test
        HALProcessPool.reset_singleton()
        pool = HALProcessPool()

        # Create real or mock tools
        exhal_path, inhal_path = create_mock_hal_tools(tmp_path)
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

    Tests marked with @pytest.mark.real_hal will get the real compressor.
    All other tests get the fast mock implementation.
    """
    # Check CLI option first, then marker
    use_real = (
        request.config.getoption("--use-real-hal", default=False) or
        request.node.get_closest_marker("real_hal") is not None
    )

    if use_real:
        # Use real HAL compressor
        from core.hal_compression import HALCompressor

        # Create mock tools for testing
        exhal_path, inhal_path = create_mock_hal_tools(tmp_path)
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
