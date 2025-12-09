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

from ui.grid_arrangement_dialog import GridArrangementDialog
from ui.injection_dialog import InjectionDialog
from ui.row_arrangement_dialog import RowArrangementDialog

# Serial execution required: QApplication management
pytestmark = [
    pytest.mark.serial,
    pytest.mark.qt_application,
    pytest.mark.ci_safe,
    pytest.mark.dialog,
    pytest.mark.headless,
    pytest.mark.integration,
    pytest.mark.rom_data,
]

def ensure_headless_qt():
    """Ensure Qt is running in headless mode for testing"""
    import os
    # Set environment variables for headless testing
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    os.environ["QT_QUICK_BACKEND"] = "software"

class DialogHelper(QObject):
    """Helper for dialog integration testing with real dialogs"""

    def __init__(self, temp_dir: str | None = None):
        """Initialize helper with temporary directory"""
        super().__init__()
        self.temp_dir = temp_dir or tempfile.mkdtemp()
        self.temp_path = Path(self.temp_dir)

        # Track dialog instances for cleanup
        self.active_dialogs: list[Any] = []

        # Create test files
        self._create_test_files()

    def _create_test_files(self):
        """Create test files for dialog testing"""
        # Create test sprite file
        self.sprite_file = self.temp_path / "test_sprite.png"
        # Create minimal PNG data
        png_data = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x10\x00\x00\x00\x10\x08\x02\x00\x00\x00\x90\x91h6\x00\x00\x00\x19tEXtSoftware\x00Adobe ImageReadyq\xc9e<\x00\x00\x00\x0eIDATx\xdab\x00\x02\x00\x00\x05\x00\x01\r\n-\xdb\x00\x00\x00\x00IEND\xaeB`\x82"
        self.sprite_file.write_bytes(png_data)

        # Create test palette file
        self.palette_file = self.temp_path / "test_sprite.pal.json"
        palette_data = {
            "8": [[255, 0, 255], [0, 0, 0], [255, 255, 255], [128, 128, 128]],
            "9": [[255, 255, 0], [0, 255, 0], [0, 0, 255], [255, 128, 0]],
        }
        import json
        self.palette_file.write_text(json.dumps(palette_data, indent=2))

        # Create test metadata file
        self.metadata_file = self.temp_path / "test_sprite.metadata.json"
        metadata = {
            "palette_files": [str(self.palette_file)],
            "active_palettes": [8, 9],
            "default_palette": 8
        }
        self.metadata_file.write_text(json.dumps(metadata, indent=2))

        # Create test VRAM file
        self.vram_file = self.temp_path / "test_VRAM.dmp"
        vram_data = bytearray(0x10000)  # 64KB
        for i in range(0x1000):
            vram_data[0xC000 + i] = i % 256
        self.vram_file.write_bytes(vram_data)

        # Create test ROM file
        self.rom_file = self.temp_path / "test_ROM.sfc"
        rom_data = bytearray(0x400000)  # 4MB
        for i in range(0x1000):
            rom_data[0x8000 + i] = i % 256
        self.rom_file.write_bytes(rom_data)

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
