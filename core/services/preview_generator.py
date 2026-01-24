"""
Preview Generator Service for SpritePal

Consolidates all sprite preview generation logic into a reusable service with caching,
thread safety, and support for different preview types (VRAM and ROM).

Architecture Note:
    This is the core layer's general-purpose preview generator. It is separate from
    the UI layer's slider preview stack (ui/common/preview_cache.py and
    ui/common/smart_preview_coordinator.py).

    Use this PreviewGenerator for:
    - One-shot preview generation in dialogs
    - Non-slider contexts requiring preview images

    Use the UI preview stack (SmartPreviewCoordinator) for:
    - Real-time 60 FPS slider scrubbing
    - Offset browsing with drag/debounce handling

This service replaces scattered preview generation code in:
- core/controller.py (_generate_preview method)
- ui/dialogs/manual_offset_dialog_simplified.py
- ui/dialogs/manual_offset/preview_coordinator.py
- core/managers/extraction_manager.py (generate_preview)

Note: This module was moved from utils/preview_generator.py to core/services/
to fix layer boundary violations (utils should only contain stdlib-only code,
but this module requires Qt).
"""

from __future__ import annotations

import hashlib
import threading
import time
import weakref
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from typing import TYPE_CHECKING, override

import numpy as np
from PIL import Image
from PySide6.QtCore import QMutex, QMutexLocker, QObject, QTimer, Signal

from core.palette_utils import bgr555_to_rgb

if TYPE_CHECKING:
    from PySide6.QtGui import QPixmap

    from core.managers.core_operations_manager import CoreOperationsManager
    from core.rom_extractor import ROMExtractor

from core.services.image_utils import pil_to_qpixmap
from core.services.lru_cache import BaseLRUCache
from utils.logging_config import get_logger

logger = get_logger(__name__)


@dataclass
class PaletteData:
    """Palette data for sprite preview generation."""

    data: bytes
    format: str = "snes_cgram"  # Format identifier


@dataclass
class PreviewRequest:
    """Unified preview request structure for all preview types."""

    source_type: str  # 'vram' or 'rom'
    data_path: str  # Path to data file (VRAM dump or ROM file)
    offset: int  # Offset within the data
    sprite_name: str = ""  # Optional sprite name
    palette: PaletteData | None = None  # Optional palette data
    size: tuple[int, int] = (384, 384)  # Preview size (width, height)
    sprite_config: object | None = None  # Optional sprite configuration

    def cache_key(self) -> str:
        """Generate a cache key for this request."""
        # Create hash from critical parameters
        key_data = (
            self.source_type,
            self.data_path,
            self.offset,
            self.size,
            # Include palette data hash if present
            hashlib.md5(self.palette.data).hexdigest() if self.palette else None,
            # Include sprite config hash if present
            str(hash(str(self.sprite_config))) if self.sprite_config else None,
        )
        return hashlib.md5(str(key_data).encode()).hexdigest()


@dataclass
class PreviewResult:
    """Result of preview generation."""

    pixmap: QPixmap
    pil_image: Image.Image
    tile_count: int
    sprite_name: str
    generation_time: float  # Time taken to generate in seconds
    cached: bool = False  # Whether this result came from cache

    def byte_size(self) -> int:
        """Estimate memory size of this result in bytes.

        Calculation:
        - QPixmap: width * height * 4 (RGBA)
        - PIL.Image: width * height * mode_bytes (varies by mode)
        - Metadata: ~100 bytes (sprite_name, floats, ints)
        """
        pixmap_size = 0
        if not self.pixmap.isNull():
            pixmap_size = self.pixmap.width() * self.pixmap.height() * 4

        # PIL mode bytes: P=1, RGB=3, RGBA=4, L=1
        mode_bytes = {"P": 1, "L": 1, "RGB": 3, "RGBA": 4}.get(self.pil_image.mode, 4)
        pil_size = self.pil_image.width * self.pil_image.height * mode_bytes

        metadata_size = 100  # Approximate overhead for strings/floats
        return pixmap_size + pil_size + metadata_size  # Whether this result came from cache


class PreviewCache(BaseLRUCache[PreviewResult]):
    """LRU cache specialized for preview results.

    Extends BaseLRUCache to mark cached results with cached=True flag.
    """

    # Default limits based on typical usage
    DEFAULT_MAX_ITEMS = 50
    DEFAULT_MAX_BYTES = 32 * 1024 * 1024  # 32 MB

    def __init__(
        self,
        max_size: int = DEFAULT_MAX_ITEMS,
        max_bytes: int = DEFAULT_MAX_BYTES,
    ):
        """Initialize preview cache with dual eviction policy."""
        super().__init__(
            max_size=max_size,
            max_bytes=max_bytes,
            size_fn=lambda r: r.byte_size(),
            name="preview_cache",
        )

    @override
    def get(self, key: str) -> PreviewResult | None:
        """Get item from cache, marking it as cached."""
        result = super().get(key)
        if result is not None:
            result.cached = True
        return result


class PreviewGenerator(QObject):
    """Consolidated preview generation service with caching and thread safety.

    This service provides unified preview generation for both VRAM and ROM sources
    with intelligent caching, debouncing, and error recovery.

    Key features:
    - LRU cache with configurable size
    - Thread-safe operations
    - Progress callback support
    - Debounced updates for rapid changes
    - Error recovery with user-friendly messages
    - Support for different preview sizes
    - Automatic resource cleanup
    """

    # Signals for preview events
    preview_ready = Signal(object)  # PreviewResult
    preview_error = Signal(str, object)  # error_message, request
    preview_progress = Signal(int, str)  # progress_percent, status_message
    cache_stats_changed = Signal(object)  # cache statistics

    def __init__(
        self,
        cache_size: int = PreviewCache.DEFAULT_MAX_ITEMS,
        cache_max_bytes: int = PreviewCache.DEFAULT_MAX_BYTES,
        debounce_delay_ms: int = 50,
        parent: QObject | None = None,
    ):
        """Initialize preview generator.

        Args:
            cache_size: Maximum number of cached previews (default 50)
            cache_max_bytes: Maximum cache size in bytes (default 32MB)
            debounce_delay_ms: Delay for debouncing rapid requests
            parent: Parent QObject
        """
        super().__init__(parent)

        # Cache management with dual limits
        self._cache = PreviewCache(cache_size, cache_max_bytes)

        # Debouncing
        self._debounce_delay_ms = debounce_delay_ms
        self._debounce_timer: QTimer | None = None
        self._pending_request: PreviewRequest | None = None

        # Thread safety
        self._generation_mutex = QMutex()

        # Manager references (weak to avoid circular refs)
        self._extraction_manager_ref: weakref.ref[CoreOperationsManager] | None = None
        self._rom_extractor_ref: weakref.ref[ROMExtractor] | None = None

        self._setup_debounce_timer()

        logger.debug(
            f"PreviewGenerator initialized with cache_size={cache_size}, "
            f"cache_max_bytes={cache_max_bytes // (1024 * 1024)}MB, debounce={debounce_delay_ms}ms"
        )

    def _setup_debounce_timer(self) -> None:
        """Set up debouncing timer."""
        self._debounce_timer = QTimer(self)
        self._debounce_timer.setSingleShot(True)
        self._debounce_timer.timeout.connect(self._process_pending_request)

    def set_managers(
        self, extraction_manager: CoreOperationsManager | None = None, rom_extractor: ROMExtractor | None = None
    ) -> None:
        """Set manager references for preview generation.

        Args:
            extraction_manager: Extraction manager for VRAM previews
            rom_extractor: ROM extractor for ROM previews
        """
        with QMutexLocker(self._generation_mutex):
            self._extraction_manager_ref = weakref.ref(extraction_manager) if extraction_manager else None
            self._rom_extractor_ref = weakref.ref(rom_extractor) if rom_extractor else None

        logger.debug("PreviewGenerator manager references updated")

    def generate_preview(
        self, request: PreviewRequest, progress_callback: Callable[[int, str], None] | None = None
    ) -> PreviewResult | None:
        """Generate preview synchronously.

        Args:
            request: Preview generation request
            progress_callback: Optional progress callback

        Returns:
            Preview result or None if generation failed
        """
        with QMutexLocker(self._generation_mutex):
            return self._generate_preview_impl(request, progress_callback)

    def generate_preview_async(self, request: PreviewRequest, use_debounce: bool = True) -> None:
        """Generate preview asynchronously with optional debouncing.

        Args:
            request: Preview generation request
            use_debounce: Whether to use debouncing for rapid requests
        """
        if use_debounce:
            self._request_debounced_preview(request)
        else:
            # Generate immediately in next event loop
            self._pending_request = request
            if self._debounce_timer is not None:
                self._debounce_timer.start(0)

    def _request_debounced_preview(self, request: PreviewRequest) -> None:
        """Request a debounced preview generation.

        Args:
            request: Preview request to process after debounce delay
        """
        self._pending_request = request

        if self._debounce_timer is not None:
            self._debounce_timer.stop()
            self._debounce_timer.start(self._debounce_delay_ms)

    def _process_pending_request(self) -> None:
        """Process the pending debounced request."""
        if self._pending_request is None:
            return

        request = self._pending_request
        self._pending_request = None

        try:
            result = self.generate_preview(request, self._emit_progress)
            if result:
                self.preview_ready.emit(result)
            else:
                self.preview_error.emit("Preview generation failed", request)
        except Exception as e:
            logger.exception("Error in debounced preview generation")
            self.preview_error.emit(str(e), request)

    def _emit_progress(self, percent: int, message: str) -> None:
        """Emit progress signal."""
        self.preview_progress.emit(percent, message)

    def _generate_preview_impl(
        self, request: PreviewRequest, progress_callback: Callable[[int, str], None] | None = None
    ) -> PreviewResult | None:
        """Internal preview generation implementation.

        Args:
            request: Preview generation request
            progress_callback: Optional progress callback

        Returns:
            Preview result or None if generation failed
        """
        start_time = time.time()

        # Check cache first
        cache_key = request.cache_key()
        cached_result = self._cache.get(cache_key)
        if cached_result:
            if progress_callback:
                progress_callback(100, f"Loaded from cache: {request.sprite_name or 'preview'}")
            self.cache_stats_changed.emit(self._cache.get_stats())
            return cached_result

        if progress_callback:
            progress_callback(10, "Generating preview...")

        try:
            # Generate based on source type
            if request.source_type == "vram":
                result = self._generate_vram_preview(request, progress_callback)
            elif request.source_type == "rom":
                result = self._generate_rom_preview(request, progress_callback)
            else:
                raise ValueError(f"Unknown source type: {request.source_type}")

            if result:
                # Cache the result
                result.generation_time = time.time() - start_time
                self._cache.put(cache_key, result)
                self.cache_stats_changed.emit(self._cache.get_stats())

                if progress_callback:
                    progress_callback(100, f"Preview ready: {result.sprite_name}")

                logger.debug(
                    f"Generated preview in {result.generation_time:.3f}s for {request.source_type}:{request.offset:06X}"
                )
                return result

        except Exception as e:
            logger.exception(f"Preview generation failed for {request.source_type}:{request.offset:06X}")
            if progress_callback:
                progress_callback(0, f"Error: {self._get_friendly_error_message(str(e))}")
            return None

        return None

    def _generate_vram_preview(
        self, request: PreviewRequest, progress_callback: Callable[[int, str], None] | None = None
    ) -> PreviewResult | None:
        """Generate preview from VRAM data.

        Args:
            request: VRAM preview request
            progress_callback: Optional progress callback

        Returns:
            Preview result or None if generation failed
        """
        # Get extraction manager
        extraction_manager = self._extraction_manager_ref() if self._extraction_manager_ref else None
        if not extraction_manager:
            raise RuntimeError("Extraction manager not available for VRAM preview")

        if progress_callback:
            progress_callback(30, "Loading VRAM data...")

        # Use extraction manager's generate_preview method
        pil_image, tile_count = extraction_manager.generate_preview(request.data_path, request.offset)

        if progress_callback:
            progress_callback(70, "Converting to display format...")

        # Convert to QPixmap
        pixmap = pil_to_qpixmap(pil_image)
        if not pixmap:
            raise RuntimeError("Failed to convert PIL image to QPixmap")

        # Scale to requested size if different
        if pixmap.size().width() != request.size[0] or pixmap.size().height() != request.size[1]:
            pixmap = pixmap.scaled(request.size[0], request.size[1])

        sprite_name = request.sprite_name or f"vram_0x{request.offset:06X}"

        return PreviewResult(
            pixmap=pixmap,
            pil_image=pil_image,
            tile_count=tile_count,
            sprite_name=sprite_name,
            generation_time=0.0,  # Will be set by caller
        )

    def _generate_rom_preview(
        self, request: PreviewRequest, progress_callback: Callable[[int, str], None] | None = None
    ) -> PreviewResult | None:
        """Generate preview from ROM data.

        Args:
            request: ROM preview request
            progress_callback: Optional progress callback

        Returns:
            Preview result or None if generation failed
        """
        # Get ROM extractor
        rom_extractor = self._rom_extractor_ref() if self._rom_extractor_ref else None
        if not rom_extractor:
            raise RuntimeError("ROM extractor not available for ROM preview")

        if progress_callback:
            progress_callback(20, "Reading ROM data...")

        # Use ROM extractor to extract sprite data
        sprite_data = rom_extractor.extract_sprite_data(
            request.data_path,
            request.offset,
        )

        # Validate sprite data plausibility
        MIN_SPRITE_BYTES = 32  # Minimum: one 8x8 tile (32 bytes for 4bpp)
        MAX_SPRITE_BYTES = 256 * 1024  # Maximum: 256KB (reasonable upper bound)

        if len(sprite_data) < MIN_SPRITE_BYTES:
            raise ValueError(
                f"Decompressed data ({len(sprite_data)} bytes) too small for valid sprite "
                f"(minimum {MIN_SPRITE_BYTES} bytes for one 8x8 tile)"
            )

        if len(sprite_data) > MAX_SPRITE_BYTES:
            raise ValueError(
                f"Decompressed data suspiciously large ({len(sprite_data)} bytes). "
                f"This may indicate an incorrect ROM offset. "
                f"Maximum expected: {MAX_SPRITE_BYTES} bytes (256KB)."
            )

        # Warn if data is not tile-aligned (4bpp = 32 bytes per 8x8 tile)
        if len(sprite_data) % 32 != 0:
            logger.warning(
                f"Sprite data not tile-aligned: {len(sprite_data)} bytes. "
                f"This may indicate incorrect offset or corrupted data."
            )

        if progress_callback:
            progress_callback(50, "Processing sprite data...")

        # Convert sprite data to PIL Image
        pil_image = self._convert_sprite_data_to_image(sprite_data, request)

        if progress_callback:
            progress_callback(80, "Converting to display format...")

        # Convert to QPixmap
        pixmap = pil_to_qpixmap(pil_image)
        if not pixmap:
            raise RuntimeError("Failed to convert PIL image to QPixmap")

        # Scale to requested size if different
        if pixmap.size().width() != request.size[0] or pixmap.size().height() != request.size[1]:
            pixmap = pixmap.scaled(request.size[0], request.size[1])

        sprite_name = request.sprite_name or f"rom_0x{request.offset:06X}"

        # Calculate tile count (estimate based on image size)
        tile_count = (pil_image.width // 8) * (pil_image.height // 8)

        return PreviewResult(
            pixmap=pixmap,
            pil_image=pil_image,
            tile_count=tile_count,
            sprite_name=sprite_name,
            generation_time=0.0,  # Will be set by caller
        )

    def _convert_sprite_data_to_image(self, sprite_data: bytes, request: PreviewRequest) -> Image.Image:
        """Convert raw sprite data to PIL Image with thread-safe palette handling.

        Thread Safety:
            This method is thread-safe when called through generate_preview() which uses
            QMutexLocker to ensure single-threaded execution.

        Args:
            sprite_data: Raw sprite tile data (read-only)
            request: Original request with configuration (read-only)

        Returns:
            PIL Image in palette mode ('P') with applied palette.
        """
        width, height = request.size

        # Use NumPy array for efficient pixel operations (10-100x faster than putpixel)
        pixel_array = np.zeros((height, width), dtype=np.uint8)

        # Handle empty sprite data
        if len(sprite_data) == 0:
            # Create error image
            img = Image.fromarray(pixel_array, mode="P")
            error_palette = [255, 0, 0] + [0, 0, 0] * 255  # Red for index 0
            img.putpalette(error_palette)
            logger.debug(f"Empty sprite data at offset {request.offset:06X}, returning error image")
            return img

        # SNES tiles are 8x8 pixels, 4bpp (32 bytes per tile)
        TILE_SIZE = 8
        BYTES_PER_TILE = 32

        # Calculate tile dimensions
        tiles_x = (width + TILE_SIZE - 1) // TILE_SIZE
        tiles_y = (height + TILE_SIZE - 1) // TILE_SIZE

        # Create local palette (thread-safe: new list each call)
        palette: list[int] = []

        # Apply palette if available
        if request.palette:
            palette_data = request.palette.data

            # Convert SNES BGR555 palette to RGB888 using shared utility
            for i in range(0, min(len(palette_data), 32), 2):
                if i + 1 < len(palette_data):
                    color = palette_data[i] | (palette_data[i + 1] << 8)
                    r, g, b = bgr555_to_rgb(color)
                    palette.extend([r, g, b])

            thread_id = threading.current_thread().ident
            logger.debug(f"Created palette with {len(palette) // 3} colors [thread={thread_id}]")
        else:
            # Default grayscale palette for 4bpp (16 shades)
            for i in range(16):
                gray = i * 17
                palette.extend([gray, gray, gray])

        # Pad palette to 256 colors (PIL requirement for P mode)
        while len(palette) < 768:
            palette.extend([0, 0, 0])

        # Decode 4bpp planar tile data
        tile_count = min(len(sprite_data) // BYTES_PER_TILE, tiles_x * tiles_y)

        for tile_idx in range(tile_count):
            tile_offset = tile_idx * BYTES_PER_TILE
            tile_data = sprite_data[tile_offset : tile_offset + BYTES_PER_TILE]

            if len(tile_data) < BYTES_PER_TILE:
                tile_data += b"\x00" * (BYTES_PER_TILE - len(tile_data))

            # Decode 4bpp planar format into an 8x8 NumPy array
            tile_pixels = np.zeros((TILE_SIZE, TILE_SIZE), dtype=np.uint8)

            for row in range(TILE_SIZE):
                plane0 = tile_data[row * 2] if row * 2 < len(tile_data) else 0
                plane1 = tile_data[row * 2 + 1] if row * 2 + 1 < len(tile_data) else 0
                plane2 = tile_data[16 + row * 2] if 16 + row * 2 < len(tile_data) else 0
                plane3 = tile_data[16 + row * 2 + 1] if 16 + row * 2 + 1 < len(tile_data) else 0

                for bit in range(7, -1, -1):
                    col = 7 - bit
                    pixel = (
                        ((plane0 >> bit) & 1)
                        | (((plane1 >> bit) & 1) << 1)
                        | (((plane2 >> bit) & 1) << 2)
                        | (((plane3 >> bit) & 1) << 3)
                    )
                    tile_pixels[row, col] = pixel

            # Place tile in image using NumPy slicing (much faster than putpixel)
            tile_x = tile_idx % tiles_x
            tile_y = tile_idx // tiles_x

            # Calculate destination region
            dest_y_start = tile_y * TILE_SIZE
            dest_y_end = min(dest_y_start + TILE_SIZE, height)
            dest_x_start = tile_x * TILE_SIZE
            dest_x_end = min(dest_x_start + TILE_SIZE, width)

            # Calculate source region (may be smaller at edges)
            src_y_end = dest_y_end - dest_y_start
            src_x_end = dest_x_end - dest_x_start

            # Copy tile to pixel array
            pixel_array[dest_y_start:dest_y_end, dest_x_start:dest_x_end] = tile_pixels[:src_y_end, :src_x_end]

        # Create PIL Image from NumPy array and apply palette
        img = Image.fromarray(pixel_array, mode="P")
        img.putpalette(palette)

        return img

    def _get_friendly_error_message(self, error_msg: str) -> str:
        """Convert technical error messages to user-friendly ones."""
        error_lower = error_msg.lower()

        if "decompression" in error_lower or "hal" in error_lower:
            return "No sprite data found. Try different offset."
        if "memory" in error_lower or "allocation" in error_lower:
            return "Memory error. Try closing other applications."
        if "permission" in error_lower or "access" in error_lower:
            return "File access error. Check file permissions."
        if "file not found" in error_lower or "no such file" in error_lower:
            return "Source file not found."
        if "manager not available" in error_lower:
            return "Preview system not ready. Try again."
        return f"Preview failed: {error_msg}"

    def clear_cache(self) -> None:
        """Clear all cached previews."""
        self._cache.clear()
        self.cache_stats_changed.emit(self._cache.get_stats())
        logger.debug("Preview cache cleared")

    def get_cache_stats(self) -> dict[str, object]:
        """Get current cache statistics."""
        return self._cache.get_stats()

    def create_preview_request(
        self, data_path: str, offset: int, width: int, height: int, sprite_name: str = ""
    ) -> PreviewRequest:
        """Create a preview request with the given parameters."""
        return create_rom_preview_request(
            rom_path=data_path, offset=offset, sprite_name=sprite_name, size=(width, height)
        )

    def generate_preview_sync(
        self, data_path: str, offset: int, width: int = 128, height: int = 128, sprite_name: str = ""
    ) -> QPixmap | None:
        """Generate preview synchronously and return QPixmap directly."""
        request = self.create_preview_request(data_path, offset, width, height, sprite_name)
        result = self.generate_preview(request)
        return result.pixmap if result else None

    def cancel_pending_requests(self) -> None:
        """Cancel any pending preview requests."""
        if self._debounce_timer is not None:
            self._debounce_timer.stop()
        self._pending_request = None
        logger.debug("Cancelled pending preview requests")

    def cleanup(self) -> None:
        """Clean up resources."""
        self.cancel_pending_requests()
        self.clear_cache()

        with QMutexLocker(self._generation_mutex):
            self._extraction_manager_ref = None
            self._rom_extractor_ref = None

        if self._debounce_timer is not None:
            self._debounce_timer.stop()
            self._debounce_timer.deleteLater()
            self._debounce_timer = None

        logger.debug("PreviewGenerator cleaned up")

    def __del__(self) -> None:
        """Ensure cleanup on deletion."""
        with suppress(Exception):
            self.cleanup()


def create_vram_preview_request(
    vram_path: str, offset: int, sprite_name: str = "", size: tuple[int, int] = (384, 384)
) -> PreviewRequest:
    """Create a VRAM preview request."""
    return PreviewRequest(
        source_type="vram",
        data_path=vram_path,
        offset=offset,
        sprite_name=sprite_name or f"vram_0x{offset:06X}",
        size=size,
    )


def create_rom_preview_request(
    rom_path: str, offset: int, sprite_name: str = "", sprite_config: object = None, size: tuple[int, int] = (384, 384)
) -> PreviewRequest:
    """Create a ROM preview request."""
    return PreviewRequest(
        source_type="rom",
        data_path=rom_path,
        offset=offset,
        sprite_name=sprite_name or f"rom_0x{offset:06X}",
        sprite_config=sprite_config,
        size=size,
    )
