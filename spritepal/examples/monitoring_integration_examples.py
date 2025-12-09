"""
Examples of integrating monitoring into SpritePal components

This file demonstrates various ways to integrate the monitoring system
into existing SpritePal code with minimal changes.
"""
from __future__ import annotations

import time
from pathlib import Path

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import QPushButton, QVBoxLayout, QWidget

from core.monitoring import (
    MonitoringMixin,
    WorkflowTracker,
    get_performance_summary,
    monitor_operation,
    monitor_performance,
    monitor_rom_operation,
    monitor_ui_interaction,
    track_feature_usage,
)


# Example 1: Using decorators on existing functions
class ROMExtractor:
    """Example ROM extraction class with monitoring."""

    @monitor_rom_operation
    def load_rom(self, rom_path: str) -> bool:
        """Load a ROM file with automatic monitoring."""
        # Simulate ROM loading work
        time.sleep(0.1)  # Simulate I/O time

        if not Path(rom_path).exists():
            raise FileNotFoundError(f"ROM file not found: {rom_path}")

        # ROM loading logic here
        return True

    @monitor_operation("sprite_extraction", track_usage=True)
    def extract_sprites(self, rom_data: bytes, offset: int) -> list:
        """Extract sprites with performance monitoring."""
        # Simulate extraction work
        time.sleep(0.05)

        if offset < 0 or offset >= len(rom_data):
            raise ValueError("Invalid offset")

        # Extraction logic here
        return ["sprite1", "sprite2", "sprite3"]

    @track_feature_usage("extraction", "batch_extract")
    def batch_extract_sprites(self, rom_data: bytes, offsets: list) -> dict:
        """Batch extraction with usage tracking."""
        results = {}

        for i, offset in enumerate(offsets):
            # Use context manager for individual operations
            with monitor_performance(f"extract_sprite_{i}", {"offset": offset}):
                sprites = self.extract_sprites(rom_data, offset)
                results[offset] = sprites

        return results


# Example 2: UI Widget with monitoring mixin
class SpriteGalleryWidget(QWidget, MonitoringMixin):
    """Example sprite gallery widget with monitoring capabilities."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.init_monitoring("sprite_gallery")
        self.setup_ui()

    def setup_ui(self):
        """Set up the UI."""
        layout = QVBoxLayout(self)

        self.load_button = QPushButton("Load Sprites")
        self.load_button.clicked.connect(self.load_sprites)
        layout.addWidget(self.load_button)

    @monitor_ui_interaction("sprite_gallery")
    def load_sprites(self):
        """Load sprites with UI interaction monitoring."""
        with self.monitor("load_sprites", {"source": "user_click"}):
            # Simulate loading work
            time.sleep(0.2)

            # Track successful completion
            self.track_usage("load_completed", success=True, duration_ms=200)

    def on_thumbnail_clicked(self, sprite_index: int):
        """Handle thumbnail click."""
        with self.monitor("thumbnail_click", {"index": sprite_index}):
            # Handle click
            self.show_sprite_details(sprite_index)

    def show_sprite_details(self, sprite_index: int):
        """Show sprite details."""
        # Track this as a feature usage
        self.track_usage("show_details", context={"sprite_index": sprite_index})

        # Implementation here
        pass


# Example 3: Worker thread with monitoring
class ThumbnailGeneratorWorker(QThread):
    """Worker thread for thumbnail generation with monitoring."""

    thumbnail_generated = Signal(int, str)  # index, thumbnail_path

    def __init__(self, sprite_data: list, parent=None):
        super().__init__(parent)
        self.sprite_data = sprite_data

    @monitor_operation("thumbnail_generation", track_usage=True)
    def run(self):
        """Generate thumbnails with monitoring."""
        workflow = WorkflowTracker("thumbnail_generation")

        try:
            workflow.step("prepare_data")
            self.prepare_data()

            workflow.step("generate_thumbnails")
            for i, sprite in enumerate(self.sprite_data):
                with monitor_performance("single_thumbnail", {"sprite_index": i}):
                    thumbnail_path = self.generate_single_thumbnail(sprite)
                    self.thumbnail_generated.emit(i, thumbnail_path)

            workflow.complete(success=True)

        except Exception as e:
            workflow.fail(str(e))
            raise

    def prepare_data(self):
        """Prepare data for thumbnail generation."""
        # Preparation logic
        time.sleep(0.01)

    def generate_single_thumbnail(self, sprite_data) -> str:
        """Generate a single thumbnail."""
        # Simulate thumbnail generation
        time.sleep(0.05)
        return f"thumbnail_{hash(str(sprite_data)) % 1000}.png"


# Example 4: Context manager usage for complex operations
class ROMInjector:
    """Example ROM injector with context manager monitoring."""

    def inject_sprites(self, rom_path: str, sprites: list, backup: bool = True):
        """Inject sprites into ROM with comprehensive monitoring."""
        workflow = WorkflowTracker("sprite_injection")

        try:
            # Step 1: Backup original ROM if requested
            if backup:
                workflow.step("create_backup")
                with monitor_performance("rom_backup", {"rom_size": Path(rom_path).stat().st_size}):
                    self.create_backup(rom_path)

            # Step 2: Validate sprites
            workflow.step("validate_sprites")
            with monitor_performance("sprite_validation", {"sprite_count": len(sprites)}):
                if not self.validate_sprites(sprites):
                    raise ValueError("Sprite validation failed")

            # Step 3: Perform injection
            workflow.step("inject_data")
            with monitor_performance("rom_injection", {"sprite_count": len(sprites)}):
                self.perform_injection(rom_path, sprites)

            # Step 4: Verify injection
            workflow.step("verify_injection")
            with monitor_performance("injection_verification"):
                if not self.verify_injection(rom_path, sprites):
                    raise RuntimeError("Injection verification failed")

            workflow.complete(success=True)
            return True

        except Exception as e:
            workflow.fail(str(e))
            raise

    def create_backup(self, rom_path: str):
        """Create ROM backup."""
        # Backup logic
        time.sleep(0.1)

    def validate_sprites(self, sprites: list) -> bool:
        """Validate sprites before injection."""
        # Validation logic
        time.sleep(0.02)
        return True

    def perform_injection(self, rom_path: str, sprites: list):
        """Perform the actual injection."""
        # Injection logic
        time.sleep(0.15)

    def verify_injection(self, rom_path: str, sprites: list) -> bool:
        """Verify injection was successful."""
        # Verification logic
        time.sleep(0.05)
        return True


# Example 5: Cache operations with monitoring
class ThumbnailCache:
    """Example cache implementation with monitoring."""

    def __init__(self):
        self.cache = {}

    @monitor_operation("cache_get", track_usage=True)
    def get_thumbnail(self, key: str) -> str | None:
        """Get thumbnail from cache with monitoring."""
        result = self.cache.get(key)

        # Track cache hit/miss
        from core.monitoring import get_monitoring_manager
        monitoring_manager = get_monitoring_manager()
        if monitoring_manager:
            monitoring_manager.track_feature_usage(
                feature="cache",
                action="thumbnail_hit" if result else "thumbnail_miss",
                context={"key": key, "cache_size": len(self.cache)}
            )

        return result

    @monitor_operation("cache_set", track_usage=True)
    def set_thumbnail(self, key: str, thumbnail_path: str):
        """Set thumbnail in cache with monitoring."""
        self.cache[key] = thumbnail_path

        # Track cache operations
        from core.monitoring import get_monitoring_manager
        monitoring_manager = get_monitoring_manager()
        if monitoring_manager:
            monitoring_manager.track_feature_usage(
                feature="cache",
                action="thumbnail_set",
                context={"key": key, "cache_size": len(self.cache)}
            )


# Example 6: Error handling with monitoring
class SpriteValidator:
    """Example validator with error monitoring."""

    @monitor_operation("sprite_validation", track_usage=True)
    def validate_sprite_data(self, sprite_data: bytes) -> bool:
        """Validate sprite data with error tracking."""
        try:
            if len(sprite_data) == 0:
                raise ValueError("Empty sprite data")

            if len(sprite_data) < 64:  # Minimum sprite size
                raise ValueError(f"Sprite data too small: {len(sprite_data)} bytes")

            # Validate sprite format
            if not self.is_valid_format(sprite_data):
                raise ValueError("Invalid sprite format")

            return True

        except Exception as e:
            # Error is automatically tracked by the @monitor_operation decorator
            # Additional context can be added here
            from core.monitoring import get_monitoring_manager
            monitoring_manager = get_monitoring_manager()
            if monitoring_manager:
                monitoring_manager.track_error(
                    error_type=type(e).__name__,
                    error_message=str(e),
                    operation="sprite_validation",
                    context={
                        "data_size": len(sprite_data) if sprite_data else 0,
                        "validation_step": "format_check"
                    }
                )
            raise

    def is_valid_format(self, data: bytes) -> bool:
        """Check if sprite data has valid format."""
        # Format validation logic
        return len(data) >= 64 and data[0:4] != b'\x00\x00\x00\x00'


# Example 7: Performance analysis utilities
def analyze_extraction_performance():
    """Analyze extraction performance using monitoring data."""
    # Get performance statistics
    rom_loading_stats = get_performance_summary("rom_loading", hours=24)
    extraction_stats = get_performance_summary("sprite_extraction", hours=24)

    print("=== Performance Analysis ===")

    if rom_loading_stats:
        mean_duration = rom_loading_stats['duration_stats']['mean_ms']
        success_rate = rom_loading_stats['success_rate']
        print(f"ROM Loading: {mean_duration:.1f}ms avg, {success_rate:.1%} success rate")

    if extraction_stats:
        mean_duration = extraction_stats['duration_stats']['mean_ms']
        p95_duration = extraction_stats['duration_stats']['p95_ms']
        print(f"Sprite Extraction: {mean_duration:.1f}ms avg, {p95_duration:.1f}ms P95")


# Example 8: Monitoring dashboard integration
def show_monitoring_dashboard():
    """Show the monitoring dashboard."""
    from PySide6.QtWidgets import QApplication

    from ui.dialogs.monitoring_dashboard import MonitoringDashboard

    app = QApplication.instance()
    if app is None:
        return None

    dashboard = MonitoringDashboard()
    dashboard.show()
    return dashboard


# Example usage
if __name__ == "__main__":
    # Example of how to use the monitoring system

    # 1. Initialize managers (normally done in main application)
    from core.managers.registry import initialize_managers
    initialize_managers()

    # 2. Use monitored classes
    extractor = ROMExtractor()

    try:
        # These operations will be automatically monitored
        extractor.load_rom("test_rom.sfc")
        rom_data = b"fake_rom_data" * 1000
        sprites = extractor.extract_sprites(rom_data, 0x8000)
        print(f"Extracted {len(sprites)} sprites")

        # Batch operation with workflow tracking
        offsets = [0x8000, 0x9000, 0xA000]
        results = extractor.batch_extract_sprites(rom_data, offsets)
        print(f"Batch extracted from {len(results)} offsets")

    except Exception as e:
        print(f"Error during extraction: {e}")

    # 3. Analyze performance
    analyze_extraction_performance()

    # 4. Show monitoring dashboard (in a real Qt application)
    # dashboard = show_monitoring_dashboard()
