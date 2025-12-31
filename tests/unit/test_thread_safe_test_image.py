"""
Unit tests for ThreadSafeTestImage class.

These tests verify that ThreadSafeTestImage provides a thread-safe alternative
to QPixmap and prevents Qt threading violations that cause crashes.

Test Categories:
1. Basic functionality tests
2. Thread safety verification tests
3. Error handling tests
4. Qt compatibility tests
5. Performance tests
"""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

import pytest
from PySide6.QtCore import QSize
from PySide6.QtGui import QColor, QImage

from tests.infrastructure.thread_safe_test_image import ThreadSafeTestImage

pytestmark = [
    pytest.mark.skip_thread_cleanup(reason="Thread tests may intentionally leave threads running"),
    pytest.mark.headless,
]


class TestThreadSafeTestImageBasic:
    """Test basic functionality of ThreadSafeTestImage."""

    def test_create_default_image(self):
        """Test creating image with default dimensions."""
        image = ThreadSafeTestImage()

        assert image.width() == 100
        assert image.height() == 100
        assert image.size() == QSize(100, 100)
        assert not image.isNull()
        assert image.sizeInBytes() > 0

    def test_create_custom_size_image(self):
        """Test creating image with custom dimensions."""
        image = ThreadSafeTestImage(200, 150)

        assert image.width() == 200
        assert image.height() == 150
        assert image.size() == QSize(200, 150)

    def test_invalid_dimensions_raises_error(self):
        """Test that invalid dimensions raise ValueError."""
        with pytest.raises(ValueError, match="Image dimensions must be positive"):
            ThreadSafeTestImage(0, 100)

        with pytest.raises(ValueError, match="Image dimensions must be positive"):
            ThreadSafeTestImage(100, -1)

    def test_fill_with_color(self):
        """Test filling image with different colors."""
        image = ThreadSafeTestImage(50, 50)

        # Fill with red
        red_color = QColor(255, 0, 0)
        image.fill(red_color)

        # Image should not be null after filling
        assert not image.isNull()

    def test_fill_with_none_uses_white(self):
        """Test that fill(None) uses white color."""
        image = ThreadSafeTestImage(50, 50)

        # Fill with None should use white (default)
        image.fill(None)

        assert not image.isNull()

    def test_to_image_returns_qimage(self):
        """Test that toImage() returns the internal QImage."""
        image = ThreadSafeTestImage(75, 75)

        qimage = image.toImage()

        assert isinstance(qimage, QImage)
        assert qimage.width() == 75
        assert qimage.height() == 75

    def test_string_representations(self):
        """Test string and repr methods."""
        image = ThreadSafeTestImage(80, 60)

        str_repr = str(image)
        assert "ThreadSafeTestImage(80x60" in str_repr
        assert "null=False" in str_repr

        repr_str = repr(image)
        assert "ThreadSafeTestImage(width=80, height=60" in repr_str
        assert "bytes=" in repr_str


class TestThreadSafeTestImageThreadSafety:
    """Test thread safety of ThreadSafeTestImage."""

    def test_create_in_multiple_threads(self):
        """Test creating images concurrently in multiple threads."""
        results = []
        errors = []

        def create_image(thread_id: int):
            """Create image in worker thread."""
            try:
                # This should NOT crash (unlike QPixmap)
                image = ThreadSafeTestImage(100, 100)
                image.fill(QColor(thread_id % 255, 0, 0))

                results.append(
                    {
                        "thread_id": thread_id,
                        "image_width": image.width(),
                        "image_height": image.height(),
                        "is_null": image.isNull(),
                        "size_bytes": image.sizeInBytes(),
                        "created_thread_id": image.created_in_thread(),
                    }
                )

            except Exception as e:
                errors.append((thread_id, str(e)))

        # Start multiple worker threads
        threads = []
        for i in range(5):
            t = threading.Thread(target=create_image, args=(i,))
            threads.append(t)
            t.start()

        # Wait for completion
        for t in threads:
            t.join(timeout=5.0)

        # Verify no threading violations occurred
        assert len(errors) == 0, f"Threading errors: {errors}"
        assert len(results) == 5

        # Verify all images were created successfully
        for result in results:
            assert result["image_width"] == 100
            assert result["image_height"] == 100
            assert not result["is_null"]
            assert result["size_bytes"] > 0
            assert result["created_thread_id"] > 0

    def test_concurrent_image_operations(self):
        """Test concurrent image operations without crashes."""
        results = []
        errors = []

        def process_image(thread_id: int):
            """Process image in worker thread."""
            try:
                # Create and manipulate image
                image = ThreadSafeTestImage(50, 50)

                # Perform multiple operations
                image.fill(QColor(255, 255, 255))  # White
                image.fill(QColor(255, 0, 0))  # Red
                image.fill(QColor(0, 255, 0))  # Green
                image.fill(QColor(0, 0, 255))  # Blue

                # Verify final state
                assert not image.isNull()
                assert image.width() == 50
                assert image.height() == 50

                results.append((thread_id, True))

            except Exception as e:
                errors.append((thread_id, str(e)))

        # Use ThreadPoolExecutor for better thread management
        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = []
            for i in range(10):
                future = executor.submit(process_image, i)
                futures.append(future)

            # Wait for all tasks to complete
            for future in as_completed(futures, timeout=10):
                future.result()  # This will raise any exceptions

        # Verify no errors occurred
        assert len(errors) == 0, f"Threading errors: {errors}"
        assert len(results) == 10

    def test_thread_id_tracking(self):
        """Test that thread ID is correctly tracked."""
        main_thread_id = threading.get_ident()

        # Image created in main thread
        main_image = ThreadSafeTestImage()
        assert main_image.created_in_thread() == main_thread_id

        # Image created in worker thread
        worker_thread_id = None
        worker_image = None

        def create_in_worker():
            nonlocal worker_thread_id, worker_image
            worker_thread_id = threading.get_ident()
            worker_image = ThreadSafeTestImage()

        thread = threading.Thread(target=create_in_worker)
        thread.start()
        thread.join()

        # Verify different thread IDs
        assert worker_image.created_in_thread() == worker_thread_id
        assert main_image.created_in_thread() != worker_image.created_in_thread()


class TestQtCompatibility:
    """Test Qt compatibility and interface matching."""

    def test_qpixmap_interface_compatibility(self):
        """Test that ThreadSafeTestImage mimics QPixmap interface."""
        image = ThreadSafeTestImage(120, 80)

        # Test QPixmap-like methods exist and work
        assert hasattr(image, "fill")
        assert hasattr(image, "isNull")
        assert hasattr(image, "size")
        assert hasattr(image, "width")
        assert hasattr(image, "height")

        # Test method return types match expectations
        assert isinstance(image.size(), QSize)
        assert isinstance(image.width(), int)
        assert isinstance(image.height(), int)
        assert isinstance(image.isNull(), bool)
        assert isinstance(image.sizeInBytes(), int)

    def test_qimage_format_consistency(self):
        """Test that internal QImage uses consistent format."""
        image = ThreadSafeTestImage(100, 100)
        qimage = image.toImage()

        # Should use RGB32 format for consistency
        assert qimage.format() == QImage.Format.Format_RGB32

    def test_qimage_creation_parameters(self):
        """Test that QImage is created with correct parameters."""
        # Instead of mocking, test the actual QImage properties
        image = ThreadSafeTestImage(150, 100)
        qimage = image.toImage()

        # Verify QImage has correct properties
        assert qimage.width() == 150
        assert qimage.height() == 100
        assert qimage.format() == QImage.Format.Format_RGB32

        # Verify image is properly initialized (not null)
        assert not qimage.isNull()


class TestErrorHandling:
    """Test error handling and edge cases."""

    def test_zero_dimensions_error(self):
        """Test error handling for zero dimensions."""
        with pytest.raises(ValueError, match="Image dimensions must be positive"):
            ThreadSafeTestImage(0, 0)

    def test_negative_dimensions_error(self):
        """Test error handling for negative dimensions."""
        with pytest.raises(ValueError, match="Image dimensions must be positive"):
            ThreadSafeTestImage(-10, 50)

        with pytest.raises(ValueError, match="Image dimensions must be positive"):
            ThreadSafeTestImage(50, -20)

    def test_large_dimensions_handling(self):
        """Test handling of very large dimensions."""
        # Should not crash, but might be slow
        try:
            image = ThreadSafeTestImage(1000, 1000)
            assert image.width() == 1000
            assert image.height() == 1000
            assert not image.isNull()
        except MemoryError:
            # Acceptable on low-memory systems
            pytest.skip("Insufficient memory for large image test")

    def test_concurrent_exception_safety(self):
        """Test that exceptions in one thread don't affect others."""
        successful_threads = []
        failed_threads = []

        def worker_with_error(thread_id: int, should_error: bool):
            try:
                if should_error:
                    # Force an error
                    raise ValueError(f"Intentional error in thread {thread_id}")
                else:
                    # Normal operation
                    image = ThreadSafeTestImage(50, 50)
                    image.fill(QColor(0, 255, 0))
                    successful_threads.append(thread_id)
            except ValueError:
                failed_threads.append(thread_id)

        # Start threads, some with errors
        threads = []
        for i in range(6):
            should_error = i % 2 == 0  # Error in even-numbered threads
            t = threading.Thread(target=worker_with_error, args=(i, should_error))
            threads.append(t)
            t.start()

        # Wait for completion
        for t in threads:
            t.join()

        # Verify that successful threads completed despite errors in others
        assert len(successful_threads) == 3  # Odd-numbered threads (1, 3, 5)
        assert len(failed_threads) == 3  # Even-numbered threads (0, 2, 4)


class TestPerformance:
    """Performance and optimization tests."""

    def test_memory_usage_reasonable(self):
        """Test that memory usage is reasonable."""
        # Create several images and verify they don't use excessive memory
        images = []
        for i in range(10):
            image = ThreadSafeTestImage(100, 100)
            images.append(image)

        # Each 100x100 RGB32 image should be approximately 40KB
        # 10 images should be around 400KB
        total_bytes = sum(img.sizeInBytes() for img in images)
        expected_bytes = 10 * 100 * 100 * 4  # 10 images * 100x100 * 4 bytes/pixel

        # Allow for some variation due to Qt internals
        assert abs(total_bytes - expected_bytes) < expected_bytes * 0.1


if __name__ == "__main__":
    # Run specific test categories
    pytest.main(
        [
            __file__,
            "-v",
            "--tb=short",
            "-m",
            "not slow",  # Skip slow tests by default
        ]
    )
