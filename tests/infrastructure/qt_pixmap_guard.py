# pyright: reportUnknownMemberType=warning  # Mock attributes are dynamic
# pyright: reportUnknownArgumentType=warning  # Test data may be dynamic
"""
QPixmap Thread Safety Guard for Tests.

This module provides a mechanism to detect QPixmap usage in worker threads,
which causes crashes in Qt (QPixmap is not thread-safe).

The guard uses a PEP 451-compliant import hook to intercept PySide6.QtGui
imports and patch QPixmap.__init__ to raise an error if called from a
non-main thread.

Usage:
    In conftest.py's pytest_configure():
        from tests.infrastructure.qt_pixmap_guard import install_qpixmap_guard
        install_qpixmap_guard()
"""

from __future__ import annotations

import importlib
import importlib.abc
import sys
from typing import Any


def _patch_qpixmap_init() -> None:
    """Patch QPixmap.__init__ to detect worker thread usage."""
    try:
        from PySide6.QtCore import QCoreApplication, QThread
        from PySide6.QtGui import QPixmap

        if hasattr(QPixmap, "_test_guard_installed"):
            return  # Already installed

        original_init = QPixmap.__init__

        def guarded_init(self: Any, *args: Any, **kwargs: Any) -> None:
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
        # Implicit return None - caller finds patched module in sys.modules


def install_qpixmap_guard() -> None:
    """Install QPixmap guard unconditionally via import hook.

    This ensures the guard is installed even for tests that import Qt late.
    Uses an import hook that triggers as soon as PySide6.QtGui is imported.

    Safe to call multiple times - will only install once.
    """
    # If Qt is already imported, patch directly
    if "PySide6.QtGui" in sys.modules:
        _patch_qpixmap_init()
        return

    # Otherwise, install an import hook to patch when Qt is imported
    # Check if our hook is already installed
    if not any(isinstance(finder, _QPixmapGuardFinder) for finder in sys.meta_path):
        sys.meta_path.insert(0, _QPixmapGuardFinder())
