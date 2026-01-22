"""
Pytest configuration for Mesen2 integration tests.

These tests require external tools (Mesen2 emulator) and are typically
run manually during development. They are skipped by default in CI.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Add project root to path for imports
project_root = Path(__file__).parent.parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))


def pytest_addoption(parser: pytest.Parser) -> None:
    """Add command line option to run Mesen2 tests."""
    parser.addoption(
        "--run-mesen2",
        action="store_true",
        default=False,
        help="Run Mesen2 integration tests (requires Mesen2 emulator)",
    )


def pytest_configure(config: pytest.Config) -> None:
    """Register custom markers."""
    config.addinivalue_line("markers", "external_tools: Tests requiring external tools (Mesen2)")


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Mark all tests in this directory as requiring external tools."""
    run_mesen2 = config.getoption("--run-mesen2")

    for item in items:
        # Always mark as external_tools
        item.add_marker(pytest.mark.external_tools)

        # Skip unless --run-mesen2 is passed
        if not run_mesen2:
            item.add_marker(pytest.mark.skip(reason="Mesen2 tests require --run-mesen2 flag"))


@pytest.fixture
def mesen_config() -> Path:
    """Return path to mesen2_integration directory."""
    return project_root / "mesen2_integration"
