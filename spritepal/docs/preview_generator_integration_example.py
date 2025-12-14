"""
Example Integration: Using PreviewGenerator in Manual Offset Dialog

This example shows how to replace the existing complex preview logic in
ui/dialogs/manual_offset_dialog_simplified.py with the new PreviewGenerator service.

The example demonstrates:
1. Setting up the preview generator
2. Replacing existing preview update logic
3. Handling async preview generation
4. Cache management
5. Error handling
"""
from __future__ import annotations

# Example of how to modify ManualOffsetDialogSimplified to use PreviewGenerator
import logging

from core.services.preview_generator import (
    create_rom_preview_request,
    create_vram_preview_request,
    get_preview_generator,
)

logger = logging.getLogger(__name__)

class ManualOffsetDialogSimplifiedWithPreviewGenerator:
    """Modified ManualOffsetDialogSimplified using PreviewGenerator service."""

    def __init__(self, parent=None):
        # ... existing init code ...

        # Initialize preview generator (replaces existing preview logic)
        self.preview_generator = get_preview_generator()
        self._setup_preview_generator()

    def _setup_preview_generator(self):
        """Set up preview generator with managers and signals."""
        # Set manager references
        if hasattr(self, "extraction_manager") and hasattr(self, "rom_extractor"):
            self.preview_generator.set_managers(
                extraction_manager=self.extraction_manager,
                rom_extractor=self.rom_extractor
            )

        # Connect signals
        self.preview_generator.preview_ready.connect(self._on_preview_generator_ready)
        self.preview_generator.preview_error.connect(self._on_preview_generator_error)
        self.preview_generator.preview_progress.connect(self._on_preview_generator_progress)
        self.preview_generator.cache_stats_changed.connect(self._on_cache_stats_changed)

    def set_rom_data(self, rom_path: str, rom_size: int, extraction_manager):
        """Override to update preview generator managers."""
        # ... existing set_rom_data code ...

        # Update preview generator managers
        self.preview_generator.set_managers(
            extraction_manager=extraction_manager,
            rom_extractor=extraction_manager.get_rom_extractor()
        )

    def _update_preview(self):
        """REPLACEMENT: Simplified preview update using PreviewGenerator.

        This replaces the complex logic in the original _update_preview method:
        - No manual worker management
        - No complex thread safety concerns
        - Automatic caching and debouncing
        - Unified error handling
        """
        # Check if ROM data is available
        if not self._has_rom_data():
            return

        current_offset = self.get_current_offset()

        # Create preview request based on current mode
        if self._is_rom_mode():
            # ROM preview
            sprite_config = self._get_sprite_config_for_offset(current_offset)
            request = create_rom_preview_request(
                rom_path=self.rom_path,
                offset=current_offset,
                sprite_name=f"manual_0x{current_offset:X}",
                sprite_config=sprite_config,
                size=(256, 256)  # or get from preview widget
            )
        else:
            # VRAM preview (if supported)
            vram_path = self._get_vram_path()
            if not vram_path:
                return

            request = create_vram_preview_request(
                vram_path=vram_path,
                offset=current_offset,
                sprite_name=f"vram_0x{current_offset:X}",
                size=(256, 256)
            )

        # Generate preview asynchronously with debouncing
        self.preview_generator.generate_preview_async(request, use_debounce=True)

    def _on_preview_generator_ready(self, result):
        """Handle preview ready from PreviewGenerator.

        This replaces _on_preview_ready and handles the unified PreviewResult.
        """
        # Update preview widget directly with QPixmap
        if self.preview_widget is not None:
            try:
                # The PreviewGenerator has already converted to QPixmap
                self.preview_widget.set_pixmap(result.pixmap, result.sprite_name)
                self.preview_widget.set_tile_count(result.tile_count)

                # Also store the PIL image for other operations
                self.preview_widget.set_grayscale_image(result.pil_image)
            except (RuntimeError, AttributeError) as e:
                logger.warning(f"Preview widget update failed: {e}")

        # Update status with cache info
        cache_status = " (cached)" if result.cached else ""
        self._update_status(f"Sprite found at 0x{self.get_current_offset():06X}{cache_status}")

    def _on_preview_generator_error(self, error_msg: str, request):
        """Handle preview error from PreviewGenerator.

        This replaces _on_preview_error with enhanced error information.
        """
        # Clear preview widget
        if self.preview_widget is not None:
            try:
                self.preview_widget.clear()
                self.preview_widget.info_label.setText("No sprite found")
            except (RuntimeError, AttributeError) as e:
                logger.warning(f"Preview widget clear failed: {e}")

        # The PreviewGenerator already converts technical errors to user-friendly messages
        self._update_status(error_msg)

    def _on_preview_generator_progress(self, percent: int, message: str):
        """Handle progress updates from PreviewGenerator."""
        # Update status with progress
        self._update_status(f"{message} ({percent}%)")

        # Update progress bar if available
        if hasattr(self, "status_panel") and self.status_panel:
            if percent == 100:
                self.status_panel.hide_progress()
            else:
                self.status_panel.show_progress(percent, 100)

    def _on_cache_stats_changed(self, stats):
        """Handle cache statistics updates."""
        # Optional: Update UI with cache statistics
        if hasattr(self, "_cache_stats_label"):
            hit_rate = stats.get("hit_rate", 0.0)
            cache_size = stats.get("cache_size", 0)
            self._cache_stats_label.setText(
                f"Cache: {cache_size} items, {hit_rate:.1%} hit rate"
            )

    def _request_preview_update(self, delay_ms: int = 50):
        """REPLACEMENT: Simplified preview request.

        This replaces the complex debouncing timer logic with a simple call.
        """
        # The PreviewGenerator handles debouncing internally
        self._update_preview()

    def cleanup_workers(self):
        """REPLACEMENT: Simplified cleanup.

        This replaces complex worker cleanup with a single call.
        """
        # Cancel any pending preview operations
        self.preview_generator.cancel_pending_requests()

        # The PreviewGenerator manages its own cleanup
        # No need to manually manage workers, timers, etc.

    def clear_preview_cache(self):
        """Clear the preview cache (new functionality)."""
        self.preview_generator.clear_cache()
        self._update_status("Preview cache cleared")

    def get_preview_cache_stats(self):
        """Get preview cache statistics (new functionality)."""
        return self.preview_generator.get_cache_stats()

# Example of integrating with existing UI components

class PreviewCacheStatsWidget:
    """Example widget to display preview cache statistics."""

    def __init__(self, preview_generator, parent=None):
        # ... create UI elements ...

        self.preview_generator = preview_generator

        # Connect to cache stats updates
        self.preview_generator.cache_stats_changed.connect(self.update_stats)

        # Create clear cache button
        self.clear_button.clicked.connect(self.preview_generator.clear_cache)

    def update_stats(self, stats):
        """Update display with cache statistics."""
        self.hits_label.setText(f"Cache Hits: {stats['hits']}")
        self.misses_label.setText(f"Cache Misses: {stats['misses']}")
        self.hit_rate_label.setText(f"Hit Rate: {stats['hit_rate']:.1%}")
        self.cache_size_label.setText(f"Cached Items: {stats['cache_size']}/{stats['max_size']}")

# Example of performance monitoring

class PreviewPerformanceMonitor:
    """Example monitor for preview generation performance."""

    def __init__(self, preview_generator):
        self.preview_generator = preview_generator
        self.preview_generator.preview_ready.connect(self.track_generation_time)

        self.generation_times = []
        self.max_history = 100

    def track_generation_time(self, result):
        """Track preview generation performance."""
        self.generation_times.append(result.generation_time)

        # Keep only recent history
        if len(self.generation_times) > self.max_history:
            self.generation_times.pop(0)

        # Log performance metrics
        if len(self.generation_times) >= 10:
            avg_time = sum(self.generation_times) / len(self.generation_times)
            logger.debug(f"Preview generation avg time: {avg_time:.3f}s")

# Benefits of using PreviewGenerator:

"""
1. **Simplified Code**:
   - No manual worker thread management
   - No complex timer-based debouncing
   - No manual cache implementation

2. **Enhanced Performance**:
   - Intelligent LRU caching
   - Automatic debouncing
   - Progress reporting

3. **Better Error Handling**:
   - User-friendly error messages
   - Automatic error recovery
   - Consistent error reporting

4. **Thread Safety**:
   - All thread management handled internally
   - No Qt threading violations
   - Proper resource cleanup

5. **Unified Interface**:
   - Same API for VRAM and ROM previews
   - Consistent request/response pattern
   - Easy to extend for new preview types

6. **Monitoring**:
   - Cache statistics
   - Performance metrics
   - Progress tracking

7. **Maintainability**:
   - Single point of preview logic
   - Easy to test and debug
   - Clear separation of concerns
"""
