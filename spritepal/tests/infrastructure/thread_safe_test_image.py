"""
Thread-Safe Test Image Implementation

This module provides ThreadSafeTestImage, a thread-safe alternative to QPixmap
for use in worker thread tests. It prevents Qt threading violations that cause
"Fatal Python error: Aborted" crashes.

Qt Threading Safety Rules:
- QPixmap: Main GUI thread ONLY (causes crashes in worker threads)
- QImage: Any thread (thread-safe for image processing)

This implementation follows Qt's canonical threading pattern for image operations.
"""

from __future__ import annotations

import threading

from PySide6.QtCore import QSize
from PySide6.QtGui import QColor, QImage

# Constants for common image formats and sizes
DEFAULT_WIDTH = 100
DEFAULT_HEIGHT = 100
DEFAULT_COLOR = QColor(255, 255, 255)  # White


class ThreadSafeTestImage:
    """Thread-safe test double for QPixmap using QImage internally.

    QPixmap is not thread-safe and can only be used in the main GUI thread.
    QImage is thread-safe and can be used in any thread. This class provides
    a QPixmap-like interface while using QImage internally for thread safety.

    Based on Qt's canonical threading pattern for image operations:

    Worker Thread (Background):     Main Thread (GUI):
    ┌─────────────────────┐        ┌──────────────────┐
    │ 1. Process with     │─signal→│ 4. Convert to    │
    │    QImage           │        │    QPixmap       │
    │                     │        │                  │
    │ 2. Emit signal      │        │ 5. Display in UI │
    │    with QImage      │        │                  │
    │                     │        │                  │
    │ 3. Worker finishes  │        │ 6. UI updates    │
    └─────────────────────┘        └──────────────────┘

    Usage:
        # ❌ CRASHES - QPixmap in worker thread
        def worker_function():
            pixmap = QPixmap(100, 100)  # FATAL ERROR  # pixmap-ok: documentation example

        # ✅ SAFE - ThreadSafeTestImage in worker thread
        def worker_function():
            image = ThreadSafeTestImage(100, 100)  # Thread-safe
            image.fill(QColor(255, 0, 0))

    Attributes:
        _image: Internal QImage for thread-safe operations
        _width: Image width in pixels
        _height: Image height in pixels
        _thread_id: Thread ID where this instance was created
    """

    def __init__(self, width: int = DEFAULT_WIDTH, height: int = DEFAULT_HEIGHT):
        """Create a thread-safe test image.

        Args:
            width: Image width in pixels (default: 100)
            height: Image height in pixels (default: 100)

        Note:
            Uses QImage.Format_RGB32 which provides good performance and
            compatibility for test scenarios. The image is initialized
            to white by default.
        """
        if width <= 0 or height <= 0:
            raise ValueError(f"Image dimensions must be positive: {width}x{height}")

        # Use QImage which is thread-safe, unlike QPixmap
        self._image = QImage(width, height, QImage.Format.Format_RGB32)
        self._width = width
        self._height = height
        self._thread_id = threading.get_ident()

        # Fill with white by default (matches QPixmap default behavior)
        self._image.fill(DEFAULT_COLOR)

    def fill(self, color: QColor | None = None) -> None:
        """Fill the image with a color.

        Args:
            color: Color to fill with. If None, fills with white.

        Note:
            This operation is thread-safe as it uses QImage internally.
        """
        if color is None:
            color = DEFAULT_COLOR
        self._image.fill(color)

    def isNull(self) -> bool:
        """Check if the image is null.

        Returns:
            True if the image is null (invalid), False otherwise.

        Note:
            Mimics QPixmap.isNull() behavior for test compatibility.
        """
        return self._image.isNull()

    def sizeInBytes(self) -> int:
        """Return the size of the image data in bytes.

        Returns:
            Number of bytes occupied by the image data.

        Note:
            This is useful for memory usage testing and cache size calculations.
        """
        return self._image.sizeInBytes()

    def size(self) -> QSize:
        """Return the size of the image.

        Returns:
            QSize containing the width and height of the image.

        Note:
            Provides QPixmap-compatible interface for size information.
        """
        return QSize(self._width, self._height)

    def width(self) -> int:
        """Return the width of the image in pixels.

        Returns:
            Image width in pixels.
        """
        return self._width

    def height(self) -> int:
        """Return the height of the image in pixels.

        Returns:
            Image height in pixels.
        """
        return self._height

    def toImage(self) -> QImage:
        """Return the internal QImage for advanced operations.

        Returns:
            The internal QImage instance.

        Warning:
            This method exposes the internal QImage. While QImage is thread-safe,
            be careful about concurrent access to the same instance from multiple
            threads.
        """
        return self._image

    def toQPixmap(self):
        """Convert ThreadSafeTestImage to QPixmap safely.

        Returns:
            QPixmap created from the internal QImage.

        Warning:
            This method should only be called from the main GUI thread.
            QPixmap objects are not thread-safe and will cause crashes if
            created in worker threads. This method is provided for convenience
            in main thread contexts only.

        Note:
            This is equivalent to QPixmap.fromImage(self.toImage()) but
            provides a more convenient interface for test code.
        """
        from PySide6.QtGui import QPixmap

        return QPixmap.fromImage(self._image)

    def scaled(self, width: int, height: int, aspectMode=None, transformMode=None):
        """Return a scaled version of the image.

        Args:
            width: Target width in pixels
            height: Target height in pixels
            aspectMode: Aspect ratio mode (ignored for test simplicity)
            transformMode: Transform mode (ignored for test simplicity)

        Returns:
            A new ThreadSafeTestImage scaled to the specified size.

        Note:
            This mimics QPixmap.scaled() for test compatibility.
            For test purposes, we create a new image with the target size.
        """
        # Create new image at target size
        scaled_image = ThreadSafeTestImage(width, height)
        # In real implementation, we'd scale the actual image data
        # For tests, we just return a new image of the right size
        return scaled_image

    def created_in_thread(self) -> int:
        """Return the thread ID where this instance was created.

        Returns:
            Thread identifier for debugging threading issues.

        Note:
            Useful for debugging and ensuring proper thread usage in tests.
        """
        return self._thread_id

    def __str__(self) -> str:
        """String representation for debugging.

        Returns:
            Human-readable description of the image.
        """
        return f"ThreadSafeTestImage({self._width}x{self._height}, thread_id={self._thread_id}, null={self.isNull()})"

    def __repr__(self) -> str:
        """Developer representation for debugging.

        Returns:
            Detailed representation suitable for debugging.
        """
        return (
            f"ThreadSafeTestImage(width={self._width}, height={self._height}, "
            f"format={self._image.format()}, bytes={self.sizeInBytes()})"
        )
