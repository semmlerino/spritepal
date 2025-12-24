"""
Test fixtures package for SpritePal test suite.

This package contains reusable test components including Qt mocks,
test data generators, and common test utilities.

This module uses lazy loading to avoid Qt dependency chains in headless environments.
"""
from __future__ import annotations

import os
from collections.abc import Callable
from typing import Any
from unittest.mock import Mock


# Import Qt mocks with lazy loading to avoid Qt dependencies
def _get_qt_mocks():
    """Lazy import of Qt mocks to avoid dependency chain."""
    try:
        from tests.infrastructure.qt_mocks import (
            MockQLabel,
            MockQPixmap,
            MockQThread,
            MockQWidget,
            MockSignal,
        )
        return {
            "MockQLabel": MockQLabel,
            "MockQPixmap": MockQPixmap,
            "MockQThread": MockQThread,
            "MockQWidget": MockQWidget,
            "MockSignal": MockSignal,
        }
    except ImportError:
        # Provide basic mocks if qt_mocks can't be imported
        from unittest.mock import Mock
        return {
            "MockQLabel": Mock,
            "MockQPixmap": Mock,
            "MockQThread": Mock,
            "MockQWidget": Mock,
            "MockSignal": Mock,
        }

def _is_headless_environment() -> bool:
    """Detect if Qt is truly unavailable (not just CI/no-DISPLAY).

    Offscreen Qt rendering is fully functional and should NOT be treated as
    headless. Only fall back to mocks if Qt actually fails to initialize.
    """
    # If offscreen mode is configured, Qt is available via software rendering
    if os.environ.get("QT_QPA_PLATFORM") == "offscreen":
        return False  # Offscreen Qt works - use real components

    # Try to actually initialize Qt - this is the authoritative check
    try:
        from PySide6.QtWidgets import QApplication
        QApplication.instance() or QApplication([])
        # In offscreen mode, primaryScreen() may return None but Qt still works
        # So we only return True (headless) if Qt import/init itself fails
        return False
    except Exception:
        # Qt genuinely unavailable - use mock fallback
        return True

def _get_real_factory(manager_registry):
    """Lazy import and return RealComponentFactory for Qt-enabled environments.

    Args:
        manager_registry: ManagerRegistry instance from isolated_managers fixture.
                         Required for proper test isolation.
    """
    try:
        from tests.infrastructure.real_component_factory import RealComponentFactory
        return RealComponentFactory(manager_registry=manager_registry)
    except ImportError as e:
        raise RuntimeError(f"Cannot import RealComponentFactory in headless environment: {e}") from e

# Make Qt mocks available at module level for backward compatibility
def __getattr__(name: str):
    """Provide lazy access to Qt mocks."""
    qt_mocks = _get_qt_mocks()
    if name in qt_mocks:
        return qt_mocks[name]
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")

__all__ = [
    "MockQLabel",
    "MockQPixmap",
    "MockQThread",
    "MockQWidget",
    "MockSignal",
    # Test data fixtures (from test_data_fixtures.py)
    "ROM_SIZES",
    "test_rom_data_factory",
    "test_rom_file",
    "test_vram_file",
    "simple_test_rom_file",
    "simple_test_rom_data",
]

# Re-export test data fixtures for convenience
from tests.fixtures.test_data_fixtures import (
    ROM_SIZES,
    simple_test_rom_data,
    simple_test_rom_file,
    test_rom_data_factory,
    test_rom_file,
    test_vram_file,
)
