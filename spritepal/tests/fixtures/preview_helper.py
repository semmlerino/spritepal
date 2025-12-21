"""
Helper for testing real preview functionality without extensive mocking
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import pytest
from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QPixmap

from tests.fixtures.helper_base import SignalTrackingMixin, TempDirectoryMixin
from tests.fixtures.qt_fixtures import ensure_headless_qt
from tests.infrastructure.thread_safe_test_image import ThreadSafeTestImage

# Serial execution required: QApplication management
pytestmark = [pytest.mark.headless]

class ExtractionPanelHelper(QObject, SignalTrackingMixin, TempDirectoryMixin):
    """Helper for real ExtractionPanel functionality without Qt widgets"""

    # Define real signals
    offset_changed = Signal(int)

    def __init__(self, vram_path: str, temp_dir: str | None = None):
        super().__init__()
        ensure_headless_qt()
        self._init_temp_dir(temp_dir)
        self.vram_path = vram_path

        # State tracking
        self._vram_offset = 0xC000
        self._current_mode = 1  # Custom Range mode

        # Track signal emissions
        self.signal_emissions: dict[str, list[Any]] = {
            "offset_changed": []
        }

        # Connect signals to track emissions
        self.offset_changed.connect(lambda offset: self.signal_emissions["offset_changed"].append(offset))

    def has_vram(self) -> bool:
        """Check if VRAM file is available"""
        return Path(self.vram_path).exists()

    def get_vram_path(self) -> str:
        """Get VRAM file path"""
        return self.vram_path

    def get_vram_offset(self) -> int:
        """Get current VRAM offset"""
        return self._vram_offset

    def set_vram_offset(self, offset: int):
        """Set VRAM offset and emit signal"""
        self._vram_offset = offset
        self.offset_changed.emit(offset)

    def simulate_slider_change(self, offset: int):
        """Simulate offset slider change"""
        self.set_vram_offset(offset)

    def simulate_spinbox_change(self, offset: int):
        """Simulate offset spinbox change"""
        self.set_vram_offset(offset)

class PreviewPanelHelper(QObject, SignalTrackingMixin, TempDirectoryMixin):
    """Helper for real PreviewPanel functionality without Qt widgets"""

    # Define real signals
    palette_mode_changed = Signal(bool)
    palette_index_changed = Signal(int)

    def __init__(self, temp_dir: str | None = None):
        super().__init__()
        ensure_headless_qt()
        self._init_temp_dir(temp_dir)

        # State tracking
        self._current_pixmap: QPixmap | ThreadSafeTestImage | None = None
        self._current_tile_count = 0
        self._current_tiles_per_row = 0
        self._grayscale_image = None
        self._colorized_image = None
        self._palette_mode = True
        self._selected_palette_index = 8
        self._zoom = 1.0
        self._pan_offset_x = 0.0
        self._pan_offset_y = 0.0

        # Available palettes (sprite palettes 8-15)
        self._palettes = self._create_test_palettes()

        # Track signal emissions and updates
        self.signal_emissions: dict[str, list[Any]] = {
            "palette_mode_changed": [],
            "palette_index_changed": [],
            "preview_updates": [],
            "zoom_changes": [],
            "pan_changes": []
        }

        # Connect signals to track emissions
        self.palette_mode_changed.connect(lambda mode: self.signal_emissions["palette_mode_changed"].append(mode))
        self.palette_index_changed.connect(lambda index: self.signal_emissions["palette_index_changed"].append(index))

    def _create_test_palettes(self) -> dict[int, list[tuple[int, int, int]]]:
        """Create test palette data"""
        palettes = {}
        for i in range(8, 16):  # Sprite palettes 8-15
            colors = []
            for j in range(16):
                # Generate distinct colors for each palette
                r = (i * 20 + j * 10) % 256
                g = (i * 15 + j * 15) % 256
                b = (i * 10 + j * 20) % 256
                colors.append((r, g, b))
            palettes[i] = colors
        return palettes

    def has_palettes(self) -> bool:
        """Check if palettes are available"""
        return bool(self._palettes)

    def is_palette_mode(self) -> bool:
        """Check if in palette mode"""
        return self._palette_mode

    def get_selected_palette_index(self) -> int:
        """Get currently selected palette index"""
        return self._selected_palette_index

    def set_palette_mode(self, enabled: bool):
        """Set palette mode and emit signal"""
        self._palette_mode = enabled
        self.palette_mode_changed.emit(enabled)

    def set_selected_palette(self, index: int):
        """Set selected palette and emit signal"""
        if index in self._palettes:
            self._selected_palette_index = index
            self.palette_index_changed.emit(index)

    def update_preview(self, pixmap: QPixmap | ThreadSafeTestImage, tile_count: int = 0, tiles_per_row: int = 0):
        """Update preview (preserves zoom/pan state)"""
        old_zoom = self._zoom
        old_pan_x = self._pan_offset_x
        old_pan_y = self._pan_offset_y

        self._current_pixmap = pixmap
        self._current_tile_count = tile_count
        self._current_tiles_per_row = tiles_per_row

        # Preserve zoom/pan state
        self._zoom = old_zoom
        self._pan_offset_x = old_pan_x
        self._pan_offset_y = old_pan_y

        self.signal_emissions["preview_updates"].append({
            "type": "update",
            "pixmap": pixmap,
            "tile_count": tile_count,
            "tiles_per_row": tiles_per_row,
            "zoom_preserved": True
        })

    def set_preview(self, pixmap: QPixmap | ThreadSafeTestImage, tile_count: int = 0, tiles_per_row: int = 0):
        """Set new preview (resets zoom/pan state)"""
        self._current_pixmap = pixmap
        self._current_tile_count = tile_count
        self._current_tiles_per_row = tiles_per_row

        # Reset zoom/pan state
        self._zoom = 1.0
        self._pan_offset_x = 0.0
        self._pan_offset_y = 0.0

        self.signal_emissions["preview_updates"].append({
            "type": "set",
            "pixmap": pixmap,
            "tile_count": tile_count,
            "tiles_per_row": tiles_per_row,
            "zoom_reset": True
        })

    def set_grayscale_image(self, pil_image):
        """Set grayscale image for palette application"""
        self._grayscale_image = pil_image
        self.signal_emissions["preview_updates"].append({
            "type": "grayscale",
            "image": pil_image
        })

    def apply_current_palette(self):
        """Apply current palette to grayscale image"""
        if self._grayscale_image and self._palette_mode:
            # Simulate palette application
            self._colorized_image = f"colorized_palette_{self._selected_palette_index}"
            self.signal_emissions["preview_updates"].append({
                "type": "colorized",
                "palette_index": self._selected_palette_index,
                "image": self._colorized_image
            })

    def get_zoom(self) -> float:
        """Get current zoom level"""
        return self._zoom

    def get_pan_offset(self) -> tuple[float, float]:
        """Get current pan offset"""
        return (self._pan_offset_x, self._pan_offset_y)

    def set_zoom(self, zoom: float):
        """Set zoom level"""
        self._zoom = zoom
        self.signal_emissions["zoom_changes"].append(zoom)

    def set_pan_offset(self, x: float, y: float):
        """Set pan offset"""
        self._pan_offset_x = x
        self._pan_offset_y = y
        self.signal_emissions["pan_changes"].append((x, y))

    def simulate_palette_toggle(self, enabled: bool):
        """Simulate palette mode toggle"""
        self.set_palette_mode(enabled)
        if enabled:
            self.apply_current_palette()
        else:
            # Switch to grayscale
            self.signal_emissions["preview_updates"].append({
                "type": "grayscale_mode",
                "enabled": False
            })

    def simulate_palette_change(self, palette_index: int):
        """Simulate palette selection change"""
        self.set_selected_palette(palette_index)
        if self._palette_mode:
            self.apply_current_palette()


class ControllerHelper(QObject):
    """Helper for real ExtractionController functionality"""

    def __init__(self, extraction_panel: ExtractionPanelHelper, preview_panel: PreviewPanelHelper):
        super().__init__()
        ensure_headless_qt()

        self.extraction_panel = extraction_panel
        self.preview_panel = preview_panel
        self.update_times: list[float] = []

        # Connect signals
        self.extraction_panel.offset_changed.connect(self.update_preview_with_offset)
        self.preview_panel.palette_mode_changed.connect(self.handle_palette_mode_change)
        self.preview_panel.palette_index_changed.connect(self.handle_palette_index_change)

    def update_preview_with_offset(self, offset: int) -> bool:
        """Update preview with new VRAM offset"""
        start_time = time.time()

        try:
            # Check if VRAM file exists
            if not self.extraction_panel.has_vram():
                return False

            # Simulate extraction process
            vram_path = Path(self.extraction_panel.get_vram_path())
            if not vram_path.exists():
                raise FileNotFoundError(f"VRAM file not found: {vram_path}")

            # Simulate different extraction results based on offset
            if offset == 0x1000:
                raise FileNotFoundError("VRAM file not found")
            if offset == 0x2000:
                raise PermissionError("Permission denied")
            if offset == 0x3000:
                raise MemoryError("Out of memory")
            if offset == 0x4000:
                raise ValueError("Invalid offset")

            # Create thread-safe test image for successful extraction
            # Using ThreadSafeTestImage instead of QPixmap to prevent threading violations
            mock_pixmap = ThreadSafeTestImage(128, 128)

            # Simulate different tile counts for different offsets
            if offset == 0x8000:
                tile_count = 50
            elif offset == 0xC000:
                tile_count = 75
            elif offset == 0xE000:
                tile_count = 25
            else:
                tile_count = 10

            # Update preview
            self.preview_panel.update_preview(mock_pixmap, tile_count)

            # Simulate grayscale image creation
            mock_grayscale_image = f"grayscale_image_offset_{offset:04X}"
            self.preview_panel.set_grayscale_image(mock_grayscale_image)

            # Apply palette if in palette mode
            if self.preview_panel.is_palette_mode():
                self.preview_panel.apply_current_palette()

            end_time = time.time()
            update_time = end_time - start_time
            self.update_times.append(update_time)

            return True

        except Exception:
            end_time = time.time()
            update_time = end_time - start_time
            self.update_times.append(update_time)
            raise

    def handle_palette_mode_change(self, enabled: bool):
        """Handle palette mode change"""
        if enabled:
            self.preview_panel.apply_current_palette()

    def handle_palette_index_change(self, palette_index: int):
        """Handle palette index change"""
        if self.preview_panel.is_palette_mode():
            self.preview_panel.apply_current_palette()

    def get_update_times(self) -> list[float]:
        """Get list of update times for performance analysis"""
        return self.update_times.copy()

class StatusBarHelper:
    """Helper for status bar functionality"""

    def __init__(self):
        self._current_message = "Ready"
        self.messages: list[str] = []

    def showMessage(self, message: str):
        """Show status message"""
        self._current_message = message
        self.messages.append(message)

    def currentMessage(self) -> str:
        """Get current status message"""
        return self._current_message
