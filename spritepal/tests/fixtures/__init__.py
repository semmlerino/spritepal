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

class _HeadlessFallbackFactory:
    """Lightweight fallback factory for headless environments."""

    def create_drag_drop_event(self):
        """Create a mock drag drop event."""
        return Mock(spec=["mimeData", "acceptProposedAction", "ignore"])

    def create_extraction_manager(self):
        """Create a mock extraction manager."""
        mock = Mock()
        mock.extract_sprites = Mock(return_value={"sprites": [], "success": True})
        mock.validate_vram = Mock(return_value=True)
        return mock

    def create_extraction_worker(self, params=None, worker_type="vram"):
        """Create a mock extraction worker."""
        mock = Mock()
        mock.finished = Mock()
        mock.progress = Mock()
        mock.error = Mock()
        mock.start = Mock()
        mock.quit = Mock()
        mock.wait = Mock()
        return mock

    def create_file_dialogs(self):
        """Create mock file dialog functions."""
        import tempfile
        from pathlib import Path

        return {
            "getOpenFileName": Mock(return_value=(str(Path(tempfile.gettempdir()) / "test.dmp"), "Memory dump (*.dmp)")),
            "getSaveFileName": Mock(return_value=(str(Path(tempfile.gettempdir()) / "output.png"), "PNG files (*.png)")),
            "getExistingDirectory": Mock(return_value=str(Path(tempfile.gettempdir()))),
        }

    def create_main_window(self, with_managers=True):
        """Create a mock main window."""
        mock = Mock()
        mock.extraction_panel = Mock()
        mock.extraction_panel.vram_input = Mock()
        mock.extraction_panel.cgram_input = Mock()
        mock.show = Mock()
        mock.hide = Mock()
        mock.close = Mock()
        return mock

    def create_qimage(self):
        """Create a mock QImage."""
        mock = Mock()
        mock.width = Mock(return_value=16)
        mock.height = Mock(return_value=16)
        mock.format = Mock(return_value=4)  # QImage.Format_RGB32
        mock.save = Mock(return_value=True)
        return mock

def _get_factory():
    """Get the appropriate factory based on environment."""
    if _is_headless_environment():
        return _HeadlessFallbackFactory()
    return _get_real_factory()

# Create backward compatibility functions with lazy loading
def create_mock_drag_drop_event():
    """Create a mock drag drop event, using lazy loading for Qt dependencies."""
    factory = _get_factory()
    if hasattr(factory, 'create_drag_drop_event'):
        return factory.create_drag_drop_event()
    return None

def create_mock_extraction_manager():
    """Create a mock extraction manager, using lazy loading for Qt dependencies."""
    factory = _get_factory()
    return factory.create_extraction_manager()

def create_mock_extraction_worker():
    """Create a mock extraction worker, using lazy loading for Qt dependencies."""
    factory = _get_factory()
    return factory.create_extraction_worker()

def create_mock_file_dialogs():
    """Create mock file dialogs, using lazy loading for Qt dependencies."""
    factory = _get_factory()
    return factory.create_file_dialogs()

def create_mock_main_window():
    """Create a mock main window, using lazy loading for Qt dependencies."""
    factory = _get_factory()
    return factory.create_main_window()

def create_mock_qimage():
    """Create a mock QImage, using lazy loading for Qt dependencies."""
    factory = _get_factory()
    if hasattr(factory, 'create_qimage'):
        return factory.create_qimage()
    return None

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
    "create_mock_drag_drop_event",
    "create_mock_extraction_manager",
    "create_mock_extraction_worker",
    "create_mock_file_dialogs",
    "create_mock_main_window",
    "create_mock_qimage",
]
