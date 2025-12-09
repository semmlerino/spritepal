"""
Complete implementation example of the Smart Preview system for real-time updates.

This example demonstrates how to integrate all components for smooth 60 FPS
preview updates during slider scrubbing.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QApplication,
    QLabel,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from ui.common.smart_preview_coordinator import SmartPreviewCoordinator
from ui.widgets.sprite_preview_widget import SpritePreviewWidget


class SmartPreviewExample(QWidget):
    """Example implementation of smart preview system."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Smart Preview Example - Real-time Updates")
        self.setMinimumSize(800, 600)

        # Setup UI
        self._setup_ui()

        # Setup smart preview coordinator
        self._setup_smart_preview()

    def _setup_ui(self):
        """Setup example UI."""
        layout = QVBoxLayout(self)

        # Status label
        self.status_label = QLabel("Drag slider for real-time preview updates")
        layout.addWidget(self.status_label)

        # Position info
        self.position_label = QLabel("Position: 0x200000")
        layout.addWidget(self.position_label)

        # Smart slider with real-time preview
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setMinimum(0x100000)
        self.slider.setMaximum(0x400000)
        self.slider.setValue(0x200000)
        self.slider.setMinimumHeight(40)

        # Style slider for visual feedback
        self.slider.setStyleSheet("""
            QSlider::groove:horizontal {
                border: 2px solid #4488dd;
                height: 12px;
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #2b2b2b, stop:1 #3b3b3b);
                border-radius: 6px;
            }
            QSlider::handle:horizontal {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 #4488dd, stop:1 #5599ee);
                border: 2px solid #66aaff;
                width: 24px;
                margin: -8px 0;
                border-radius: 12px;
            }
            QSlider::handle:horizontal:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 #5599ee, stop:1 #66aaff);
                border: 2px solid #77bbff;
            }
            QSlider::handle:horizontal:pressed {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 #66aaff, stop:1 #77bbff);
                border: 2px solid #88ccff;
            }
        """)

        layout.addWidget(self.slider)

        # Performance indicator
        self.perf_label = QLabel("Preview Performance: Ready")
        layout.addWidget(self.perf_label)

        # Preview widget
        self.preview_widget = SpritePreviewWidget()
        layout.addWidget(self.preview_widget)

        # Control buttons
        button_layout = QVBoxLayout()

        self.cache_stats_btn = QPushButton("Show Cache Stats")
        self.cache_stats_btn.clicked.connect(self._show_cache_stats)
        button_layout.addWidget(self.cache_stats_btn)

        self.clear_cache_btn = QPushButton("Clear Cache")
        self.clear_cache_btn.clicked.connect(self._clear_cache)
        button_layout.addWidget(self.clear_cache_btn)

        layout.addLayout(button_layout)

    def _setup_smart_preview(self):
        """Setup smart preview coordinator."""
        self.coordinator = SmartPreviewCoordinator(self)

        # Connect slider for drag detection
        self.coordinator.connect_slider(self.slider)

        # Setup callbacks
        self.coordinator.set_ui_update_callback(self._on_ui_update)
        self.coordinator.set_rom_data_provider(self._get_rom_data)

        # Connect preview signals
        self.coordinator.preview_ready.connect(self._on_preview_ready)
        self.coordinator.preview_cached.connect(self._on_preview_cached)
        self.coordinator.preview_error.connect(self._on_preview_error)

        # Connect slider value changes to coordinator
        self.slider.valueChanged.connect(
            lambda value: self.coordinator.request_preview(value)
        )

    def _get_rom_data(self):
        """Provide ROM data for preview generation with cache support."""
        # In real implementation, return actual ROM path, extractor, and cache
        from utils.rom_cache import get_rom_cache
        rom_cache = get_rom_cache()
        return ("/path/to/rom.smc", None, rom_cache)  # Mock data with cache

    def _on_ui_update(self, offset: int):
        """Handle immediate UI updates during dragging."""
        # Update position display immediately for smooth feedback
        self.position_label.setText(f"Position: 0x{offset:06X}")

        # Show visual feedback that we're updating
        mb_pos = offset / (1024 * 1024)
        percentage = (offset - 0x100000) / (0x400000 - 0x100000) * 100
        self.status_label.setText(
            f"Scanning {mb_pos:.1f}MB ({percentage:.0f}%) - "
            f"{'Dragging...' if self.slider.isSliderDown() else 'Updated'}"
        )

    def _on_preview_ready(self, tile_data: bytes, width: int, height: int, sprite_name: str):
        """Handle high-quality preview ready."""
        self.preview_widget.load_sprite_from_4bpp(tile_data, width, height, sprite_name)
        self.perf_label.setText("Preview Performance: High-Quality ✓")
        self.perf_label.setStyleSheet("color: #4CAF50;")  # Green

        # Auto-clear performance indicator
        QTimer.singleShot(2000, lambda: self.perf_label.setText("Preview Performance: Ready"))
        QTimer.singleShot(2000, lambda: self.perf_label.setStyleSheet(""))

    def _on_preview_cached(self, tile_data: bytes, width: int, height: int, sprite_name: str):
        """Handle cached preview displayed."""
        self.preview_widget.load_sprite_from_4bpp(tile_data, width, height, sprite_name)
        self.perf_label.setText("Preview Performance: Cached ⚡")
        self.perf_label.setStyleSheet("color: #FF9800;")  # Orange

        # Auto-clear performance indicator
        QTimer.singleShot(1000, lambda: self.perf_label.setText("Preview Performance: Ready"))
        QTimer.singleShot(1000, lambda: self.perf_label.setStyleSheet(""))

    def _on_preview_error(self, error_msg: str):
        """Handle preview error."""
        self.preview_widget.clear()
        if self.preview_widget.info_label:
            self.preview_widget.info_label.setText("No sprite found")
        self.perf_label.setText(f"Preview Error: {error_msg}")
        self.perf_label.setStyleSheet("color: #F44336;")  # Red

        # Auto-clear error after delay
        QTimer.singleShot(3000, lambda: self.perf_label.setText("Preview Performance: Ready"))
        QTimer.singleShot(3000, lambda: self.perf_label.setStyleSheet(""))

    def _show_cache_stats(self):
        """Show cache statistics."""
        if hasattr(self.coordinator, "_cache"):
            stats = self.coordinator._cache.get_stats()
            stats_text = (
                f"Cache Stats:\n"
                f"Entries: {stats['entry_count']}/{stats['max_size']}\n"
                f"Memory: {stats['memory_usage_mb']:.1f}MB/{stats['max_memory_mb']:.1f}MB\n"
                f"Utilization: {stats['memory_utilization']:.0%}"
            )
            self.status_label.setText(stats_text)

    def _clear_cache(self):
        """Clear preview cache."""
        if hasattr(self.coordinator, "_cache"):
            self.coordinator._cache.clear()
            self.status_label.setText("Cache cleared")

    def closeEvent(self, event):
        """Clean up on close."""
        if hasattr(self, "coordinator"):
            self.coordinator.cleanup()
        super().closeEvent(event)

# Timing Strategy Configuration Example
TIMING_STRATEGIES = {
    # Real-time UI updates (60 FPS)
    "ui_update_interval": 16,  # 16ms for smooth 60fps feedback

    # Preview generation during dragging
    "drag_preview_debounce": 50,  # 50ms for responsive drag updates

    # High-quality preview after release
    "release_preview_debounce": 200,  # 200ms for quality after positioning

    # Cache configuration
    "cache_max_entries": 20,  # 20 preview entries
    "cache_max_memory_mb": 2.0,  # 2MB memory limit

    # Worker pool configuration
    "max_preview_workers": 2,  # 2 concurrent workers
    "worker_idle_timeout": 30000,  # 30s idle timeout
}

# Signal Connection Pattern Example
def connect_smart_preview_to_slider(coordinator, slider):
    """
    Example of proper signal connections for smart preview.

    This demonstrates the complete signal flow:
    1. Drag detection via sliderPressed/sliderReleased
    2. Value changes via valueChanged
    3. Immediate UI updates via coordinator callbacks
    4. Preview generation via worker pool
    """

    # Connect coordinator to slider for drag detection
    coordinator.connect_slider(slider)

    # Connect value changes to preview requests
    slider.valueChanged.connect(
        lambda value: coordinator.request_preview(value, priority=5)
    )

    # Optional: Connect to slider signals for custom behavior
    slider.sliderPressed.connect(
        lambda: print("Drag started - showing cached previews")
    )

    slider.sliderReleased.connect(
        lambda: print("Drag ended - generating high-quality preview")
    )

if __name__ == "__main__":
    app = QApplication([])

    # Create and show example
    example = SmartPreviewExample()
    example.show()

    # Add some test data to demonstrate functionality
    example.status_label.setText(
        "Smart Preview Demo: Drag slider for real-time updates!\n"
        "• Immediate visual feedback (60 FPS)\n"
        "• Cached previews during dragging\n"
        "• High-quality previews after release"
    )

    app.exec()
