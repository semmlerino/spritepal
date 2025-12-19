"""
Helper for testing dialog integration with real dialog components
"""
from __future__ import annotations

import contextlib
import json
import tempfile
from pathlib import Path
from typing import Any

import pytest
from PySide6.QtCore import QObject
from PySide6.QtWidgets import QApplication

from tests.fixtures.qt_fixtures import ensure_headless_qt
from ui.grid_arrangement_dialog import GridArrangementDialog
from ui.injection_dialog import InjectionDialog
from ui.row_arrangement_dialog import RowArrangementDialog

# Serial execution required: QApplication management
pytestmark = [
    pytest.mark.headless,
    pytest.mark.integration,
]

class DialogHelper(QObject):
    """Helper for dialog integration testing with real dialogs"""

    def __init__(self, temp_dir: str | None = None):
        """Initialize helper with temporary directory"""
        from tests.fixtures.test_data_factory import TestDataFactory

        super().__init__()
        self.temp_dir = temp_dir or tempfile.mkdtemp()
        self.temp_path = Path(self.temp_dir)

        # Track dialog instances for cleanup
        self.active_dialogs: list[Any] = []

        # Use TestDataFactory for file creation (DRY consolidation)
        paths = TestDataFactory.create_test_files(self.temp_path)
        self.sprite_file = paths.sprite_path
        self.palette_file = paths.palette_path
        self.metadata_file = paths.metadata_path
        self.vram_file = paths.vram_path
        self.rom_file = paths.rom_path

    def create_injection_dialog(self, sprite_path: str | None = None,
                              metadata_path: str | None = None,
                              input_vram: str | None = None) -> InjectionDialog:
        """Create real InjectionDialog for testing"""
        # Ensure headless Qt environment
        ensure_headless_qt()

        # Ensure QApplication exists
        if not QApplication.instance():
            QApplication([])

        dialog = InjectionDialog(
            parent=None,  # Use None instead of Mock for parent
            sprite_path=sprite_path or str(self.sprite_file),
            metadata_path=metadata_path or str(self.metadata_file),
            input_vram=input_vram or str(self.vram_file)
        )

        self.active_dialogs.append(dialog)
        return dialog

    def create_row_arrangement_dialog(self, sprite_path: str | None = None,
                                    tiles_per_row: int = 16) -> RowArrangementDialog:
        """Create real RowArrangementDialog for testing"""
        # Ensure headless Qt environment
        ensure_headless_qt()

        # Ensure QApplication exists
        if not QApplication.instance():
            QApplication([])

        dialog = RowArrangementDialog(
            sprite_file=sprite_path or str(self.sprite_file),
            tiles_per_row=tiles_per_row,
            parent=None  # Use None instead of Mock for parent
        )

        # Set palettes if available
        if self.palette_file.exists():
            try:
                dialog.set_palettes(json.loads(self.palette_file.read_text()))
            except Exception:
                pass  # Continue without palettes

        self.active_dialogs.append(dialog)
        return dialog

    def create_grid_arrangement_dialog(self, sprite_path: str | None = None,
                                     tiles_per_row: int = 16) -> GridArrangementDialog:
        """Create real GridArrangementDialog for testing"""
        # Ensure headless Qt environment
        ensure_headless_qt()

        # Ensure QApplication exists
        if not QApplication.instance():
            QApplication([])

        dialog = GridArrangementDialog(
            sprite_file=sprite_path or str(self.sprite_file),
            tiles_per_row=tiles_per_row,
            parent=None  # Use None instead of Mock for parent
        )

        # Set palettes if available
        if self.palette_file.exists():
            try:
                dialog.set_palettes(json.loads(self.palette_file.read_text()))
            except Exception:
                pass  # Continue without palettes

        self.active_dialogs.append(dialog)
        return dialog

    def get_injection_parameters(self, dialog: InjectionDialog) -> dict[str, Any]:
        """Get injection parameters from real dialog"""
        return dialog.get_parameters()

    def get_arrangement_path(self, dialog) -> str | None:
        """Get arranged sprite path from arrangement dialog"""
        if hasattr(dialog, "get_arranged_path"):
            return dialog.get_arranged_path()
        return None

    def simulate_dialog_accept(self, dialog):
        """Simulate accepting a dialog"""
        dialog.accept()

    def simulate_dialog_reject(self, dialog):
        """Simulate rejecting a dialog"""
        dialog.reject()

    def cleanup(self):
        """Cleanup dialog resources"""
        # Close all dialogs
        for dialog in self.active_dialogs:
            if hasattr(dialog, "close"):
                with contextlib.suppress(Exception):
                    dialog.close()

        self.active_dialogs.clear()

        # Cleanup temp files
        import shutil
        try:
            shutil.rmtree(self.temp_dir)
        except Exception:
            pass  # Best effort cleanup
