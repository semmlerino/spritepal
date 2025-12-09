"""
Helper for testing with real MainWindow components in a controlled environment
"""
from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

import pytest
from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QLabel, QStatusBar

from ui.palette_preview import PalettePreviewWidget
from ui.zoomable_preview import PreviewPanel

# Systematic pytest markers applied based on test content analysis
pytestmark = [
    pytest.mark.file_io,
    pytest.mark.integration,
    pytest.mark.qt_app,
    pytest.mark.qt_real,
    pytest.mark.rom_data,
    pytest.mark.widget,
    pytest.mark.gui,
    pytest.mark.requires_display,
    pytest.mark.signals_slots,
]

class MainWindowHelper(QObject):
    """Helper for managing real MainWindow components in tests"""

    # Define signals that MainWindow has
    extract_requested = Signal()
    open_in_editor_requested = Signal(str)
    arrange_rows_requested = Signal(str)
    arrange_grid_requested = Signal(str)
    inject_requested = Signal()

    def __init__(self, temp_dir: str | None = None):
        """Initialize helper with optional temporary directory"""
        super().__init__()
        self.temp_dir = temp_dir or tempfile.mkdtemp()
        self.temp_path = Path(self.temp_dir)

        # Initialize UI components as None - they'll be created when needed
        self._status_bar = None
        self._sprite_preview = None
        self._palette_preview = None
        self._preview_info = None

        # Track state
        self._extracted_files: list[str] = []
        self._output_path = ""
        self._extraction_params: dict[str, Any] = {}

        # Track signal emissions for testing
        self.signal_emissions: dict[str, list[Any]] = {
            "extract_requested": [],
            "open_in_editor_requested": [],
            "arrange_rows_requested": [],
            "arrange_grid_requested": [],
            "inject_requested": [],
            "extraction_complete": [],
            "extraction_failed": [],
            "status_messages": [],
            "preview_updates": [],
            "palette_updates": []
        }

        # Connect signals to track emissions
        self.extract_requested.connect(lambda: self.signal_emissions["extract_requested"].append(True))
        self.open_in_editor_requested.connect(lambda path: self.signal_emissions["open_in_editor_requested"].append(path))
        self.arrange_rows_requested.connect(lambda path: self.signal_emissions["arrange_rows_requested"].append(path))
        self.arrange_grid_requested.connect(lambda path: self.signal_emissions["arrange_grid_requested"].append(path))
        self.inject_requested.connect(lambda: self.signal_emissions["inject_requested"].append(True))

        # Create test files
        self._create_test_files()

    @property
    def status_bar(self):
        """Lazy-create status bar when needed"""
        if self._status_bar is None:
            self._status_bar = QStatusBar()
        return self._status_bar

    @property
    def sprite_preview(self):
        """Lazy-create sprite preview when needed"""
        if self._sprite_preview is None:
            self._sprite_preview = PreviewPanel()
        return self._sprite_preview

    @property
    def palette_preview(self):
        """Lazy-create palette preview when needed"""
        if self._palette_preview is None:
            self._palette_preview = PalettePreviewWidget()
        return self._palette_preview

    @property
    def preview_info(self):
        """Lazy-create preview info when needed"""
        if self._preview_info is None:
            self._preview_info = QLabel("No sprites loaded")
        return self._preview_info

    def _create_test_files(self):
        """Create test files for extraction parameters"""
        # Create test VRAM file
        self.vram_file = self.temp_path / "test_VRAM.dmp"
        vram_data = bytearray(0x10000)  # 64KB
        # Add some test data at sprite offset
        for i in range(0x1000):
            vram_data[0xC000 + i] = i % 256
        self.vram_file.write_bytes(vram_data)

        # Create test CGRAM file
        self.cgram_file = self.temp_path / "test_CGRAM.dmp"
        cgram_data = bytearray(512)  # 256 colors * 2 bytes
        for i in range(256):
            cgram_data[i * 2] = i % 32
            cgram_data[i * 2 + 1] = (i // 32) % 32
        self.cgram_file.write_bytes(cgram_data)

        # Create test OAM file
        self.oam_file = self.temp_path / "test_OAM.dmp"
        oam_data = bytearray(544)  # 544 bytes
        # Add some test sprite entries
        oam_data[0] = 0x50  # X position
        oam_data[1] = 0x50  # Y position
        oam_data[2] = 0x00  # Tile number
        oam_data[3] = 0x00  # Attributes
        self.oam_file.write_bytes(oam_data)

        # Create test ROM file
        self.rom_file = self.temp_path / "test_ROM.sfc"
        rom_data = bytearray(0x400000)  # 4MB
        # Add some test data
        for i in range(0x1000):
            rom_data[0x8000 + i] = i % 256
        self.rom_file.write_bytes(rom_data)

    def get_extraction_params(self) -> dict[str, Any]:
        """Get extraction parameters (mimics MainWindow.get_extraction_params)"""
        # Return default test parameters if none set
        if not self._extraction_params:
            return {
                "vram_path": str(self.vram_file),
                "cgram_path": str(self.cgram_file),
                "output_base": str(self.temp_path / "test_sprite"),
                "create_grayscale": True,
                "create_metadata": True,
                "oam_path": str(self.oam_file),
                "vram_offset": 0xC000,
                "sprite_size": (8, 8),
            }
        return self._extraction_params.copy()

    def set_extraction_params(self, params: dict[str, Any]):
        """Set extraction parameters for testing"""
        self._extraction_params = params.copy()

    def extraction_complete(self, extracted_files: list[str]):
        """Handle extraction completion (mimics MainWindow.extraction_complete)"""
        self._extracted_files = extracted_files
        self.signal_emissions["extraction_complete"].append(extracted_files)

        # Update real UI components
        sprite_file = None
        for file_path in extracted_files:
            if file_path.endswith(".png"):
                sprite_file = file_path
                break

        if sprite_file:
            self.preview_info.setText(f"Extracted {len(extracted_files)} files")
            self.status_bar.showMessage("Extraction complete!")
            self.signal_emissions["status_messages"].append("Extraction complete!")
        else:
            self.status_bar.showMessage("Extraction failed")
            self.signal_emissions["status_messages"].append("Extraction failed")

    def extraction_failed(self, error_message: str):
        """Handle extraction failure (mimics MainWindow.extraction_failed)"""
        self.signal_emissions["extraction_failed"].append(error_message)
        self.status_bar.showMessage("Extraction failed")
        self.signal_emissions["status_messages"].append("Extraction failed")

    def set_preview(self, image_data, tile_count: int = 0):
        """Set sprite preview (mimics MainWindow sprite preview functionality)"""
        self.signal_emissions["preview_updates"].append({"image_data": image_data, "tile_count": tile_count})
        if hasattr(self.sprite_preview, "set_preview"):
            self.sprite_preview.set_preview(image_data)

    def set_all_palettes(self, palettes_data):
        """Set palette preview (mimics MainWindow palette preview functionality)"""
        self.signal_emissions["palette_updates"].append(palettes_data)
        if hasattr(self.palette_preview, "set_all_palettes"):
            self.palette_preview.set_all_palettes(palettes_data)

    def highlight_active_palettes(self, active_palettes: list[int]):
        """Highlight active palettes (mimics MainWindow palette preview functionality)"""
        self.signal_emissions["palette_updates"].append({"active_palettes": active_palettes})
        if hasattr(self.palette_preview, "highlight_active_palettes"):
            self.palette_preview.highlight_active_palettes(active_palettes)

    def get_extracted_files(self) -> list[str]:
        """Get list of extracted files"""
        return self._extracted_files.copy()

    def get_status_message(self) -> str:
        """Get current status bar message"""
        return self.status_bar.currentMessage()

    def get_preview_info_text(self) -> str:
        """Get current preview info text"""
        return self.preview_info.text()

    def simulate_extract_request(self):
        """Simulate user clicking extract button"""
        self.extract_requested.emit()

    def simulate_open_in_editor_request(self, sprite_path: str):
        """Simulate user requesting to open sprite in editor"""
        self.open_in_editor_requested.emit(sprite_path)

    def simulate_arrange_rows_request(self, sprite_path: str):
        """Simulate user requesting row arrangement"""
        self.arrange_rows_requested.emit(sprite_path)

    def simulate_arrange_grid_request(self, sprite_path: str):
        """Simulate user requesting grid arrangement"""
        self.arrange_grid_requested.emit(sprite_path)

    def clear_signal_tracking(self):
        """Clear signal emission tracking"""
        for key in self.signal_emissions:
            self.signal_emissions[key].clear()

    def get_signal_emissions(self) -> dict[str, list[Any]]:
        """Get copy of signal emissions for testing"""
        return {key: value.copy() for key, value in self.signal_emissions.items()}

    def cleanup(self):
        """Cleanup helper resources"""
        # Cleanup temp files
        import shutil
        try:
            shutil.rmtree(self.temp_dir)
        except Exception:
            pass  # Best effort cleanup

    # Convenience methods for common test scenarios
    def create_vram_extraction_scenario(self) -> dict[str, Any]:
        """Create a typical VRAM extraction scenario"""
        params = {
            "vram_path": str(self.vram_file),
            "cgram_path": str(self.cgram_file),
            "output_base": str(self.temp_path / "vram_extraction"),
            "create_grayscale": True,
            "create_metadata": True,
            "oam_path": str(self.oam_file),
            "vram_offset": 0xC000,
            "sprite_size": (8, 8),
        }
        self.set_extraction_params(params)
        return params

    def create_rom_extraction_scenario(self) -> dict[str, Any]:
        """Create a typical ROM extraction scenario"""
        params = {
            "rom_path": str(self.rom_file),
            "offset": 0x8000,
            "output_base": str(self.temp_path / "rom_extraction"),
            "sprite_name": "test_sprite",
            "cgram_path": str(self.cgram_file),
        }
        self.set_extraction_params(params)
        return params

    def verify_workflow_signals(self, expected_signals: list[str]) -> bool:
        """Verify that expected workflow signals were emitted"""
        for signal_name in expected_signals:
            if signal_name not in self.signal_emissions:
                return False
            if not self.signal_emissions[signal_name]:
                return False
        return True

    def get_workflow_summary(self) -> dict[str, Any]:
        """Get summary of workflow state for testing"""
        return {
            "extracted_files_count": len(self._extracted_files),
            "status_message": self.get_status_message(),
            "preview_info": self.get_preview_info_text(),
            "signals_emitted": {k: len(v) for k, v in self.signal_emissions.items()},
            "has_preview_data": len(self.signal_emissions["preview_updates"]) > 0,
            "has_palette_data": len(self.signal_emissions["palette_updates"]) > 0,
        }
