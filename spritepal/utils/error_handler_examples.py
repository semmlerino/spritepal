"""
Examples of how to integrate UnifiedErrorHandler with existing patterns.

This module demonstrates the various ways to use the UnifiedErrorHandler
with existing code patterns in SpritePal, showing migration paths and
integration strategies.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QApplication, QWidget

from core.managers.exceptions import ExtractionError, ValidationError
from utils.error_integration import (
    ErrorHandlerMixin,
    enhanced_handle_worker_errors,
    file_operation_handler,
    qt_error_handler,
    validation_handler,
)
from utils.unified_error_handler import get_unified_error_handler


# Example 1: Enhanced Worker Pattern
class ExampleWorker(QObject):
    """
    Example worker using enhanced error handling.

    This shows how to migrate from @handle_worker_errors to
    @enhanced_handle_worker_errors for better error processing.
    """

    # Standard worker signals
    progress = Signal(int)
    error = Signal(str, Exception)
    finished = Signal(object)
    operation_finished = Signal(bool, str)

    def __init__(self):
        super().__init__()
        self._operation_name = "ExampleWorker"
        self._current_file: str | None = None

    @enhanced_handle_worker_errors("sprite extraction")
    def extract_sprites(self, rom_path: str) -> list[bytes]:
        """Example extraction method with enhanced error handling"""
        self._current_file = rom_path

        # Simulate extraction work
        self.progress.emit(25)

        # This would be real extraction logic
        with Path(rom_path).open("rb") as f:
            data = f.read()

        self.progress.emit(75)

        # Simulate validation
        if len(data) < 1024:
            raise ValidationError("ROM file too small")

        self.progress.emit(100)
        sprites = [data[i:i+64] for i in range(0, min(len(data), 1024), 64)]

        self.finished.emit(sprites)
        return sprites

# Example 2: Qt Widget with Error Handling Mixin
class ExampleWidget(QWidget, ErrorHandlerMixin):
    """
    Example widget using ErrorHandlerMixin for convenient error handling.
    """

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setup_error_handling(parent)
        self.file_path = None

    @qt_error_handler("updating sprite display", "ExampleWidget")
    def update_sprite_display(self, sprite_data: bytes) -> None:
        """Update the sprite display with error handling"""
        if not sprite_data:
            raise ValueError("No sprite data provided")

        # Simulate UI update that might fail
        self.setWindowTitle(f"Sprite ({len(sprite_data)} bytes)")

    @file_operation_handler("loading sprite file", "file_path")
    def load_sprite_file(self, file_path: str) -> bytes:
        """Load sprite file with enhanced error handling"""
        self.file_path = file_path

        with Path(file_path).open("rb") as f:
            return f.read()

    @validation_handler("validating sprite parameters")
    def validate_sprite_params(self, width: int, height: int) -> bool:
        """Validate sprite parameters with error handling"""
        if width <= 0 or height <= 0:
            raise ValidationError("Sprite dimensions must be positive")

        if width > 64 or height > 64:
            raise ValidationError("Sprite too large (max 64x64)")

        return True

    def process_sprite_with_context(self, sprite_data: bytes) -> None:
        """Example using error context manager"""
        with self.error_context("processing sprite", file_path=self.file_path):
            # Operations that might fail
            if len(sprite_data) < 8:
                raise ValueError("Invalid sprite data")

            # More processing...
            self.update_sprite_display(sprite_data)

# Example 3: Manager Integration
class ExampleManager:
    """
    Example manager showing error handling integration.
    """

    def __init__(self):
        self._error_handler = get_unified_error_handler()

    def extract_with_error_handling(self, rom_path: str) -> list[bytes] | None:
        """Extract sprites with comprehensive error handling"""
        try:
            with self._error_handler.error_context(
                "extracting sprites from ROM",
                file_path=rom_path,
                component="ExampleManager"
            ):
                # Validate input
                if not rom_path:
                    raise ValidationError("ROM path is required")

                # Perform extraction
                with Path(rom_path).open("rb") as f:
                    data = f.read()

                if len(data) < 1024:
                    raise ExtractionError("ROM file too small for sprite extraction")

                # Extract sprites
                sprites = []
                for i in range(0, min(len(data), 2048), 64):
                    sprite = data[i:i+64]
                    if len(sprite) == 64:  # Valid sprite size
                        sprites.append(sprite)

                return sprites

        except Exception:
            # Error is automatically handled by context manager
            # We can add additional handling here if needed
            return None

    def batch_extract_with_recovery(self, rom_paths: list[str]) -> dict[str, Any]:
        """Extract from multiple ROMs with error recovery"""
        results = {}

        for rom_path in rom_paths:
            try:
                sprites = self.extract_with_error_handling(rom_path)
                results[rom_path] = {
                    "success": sprites is not None,
                    "sprites": sprites or [],
                    "error": None
                }
            except Exception as e:
                # Handle individual failures without stopping batch
                if isinstance(e, OSError):
                    error_result = self._error_handler.handle_file_error(
                        e, rom_path, f"batch extraction of {rom_path}"
                    )
                else:
                    error_result = self._error_handler.handle_error(  # type: ignore[attr-defined]
                        e, f"batch extraction of {rom_path}"
                    )

                results[rom_path] = {
                    "success": False,
                    "sprites": [],
                    "error": error_result.message
                }

                # Continue with next file unless critical
                if error_result.should_abort:
                    break

        return results

# Example 4: Legacy Integration
class LegacyIntegrationExample:
    """
    Example showing how to integrate with existing error patterns.
    """

    def __init__(self):
        self._error_handler = get_unified_error_handler()

    def migrate_existing_error_handling(self):
        """Example of migrating existing error handling patterns"""

        # OLD PATTERN:
        # try:
        #     result = risky_operation()
        # except Exception as e:
        #     QMessageBox.critical(self, "Error", str(e))
        #     logger.error(f"Operation failed: {e}")
        #     return None

        # NEW PATTERN:
        try:
            return self._risky_operation()
        except Exception as e:
            error_result = self._error_handler.handle_exception(
                e,
                context=None  # Will use current context from stack
            )

            # Error is automatically displayed and logged
            # Return appropriate value based on error result
            return None if not error_result.should_retry else "retry"

    def _risky_operation(self) -> str:
        """Simulate a risky operation"""
        raise ValueError("Something went wrong")

    def demonstrate_error_categories(self):
        """Demonstrate different error categories"""

        # File operation error
        try:
            with Path("nonexistent.file").open() as f:
                f.read()
        except Exception as e:
            if isinstance(e, OSError):
                self._error_handler.handle_file_error(
                    e, "nonexistent.file", "reading configuration"
                )
            else:
                self._error_handler.handle_error(  # type: ignore[attr-defined]
                    e, "reading configuration"
                )

        # Validation error
        try:
            if True:  # Some invalid condition
                raise ValidationError("Invalid input parameters")
        except Exception as e:
            self._error_handler.handle_validation_error(
                e, "validating user input", user_input="invalid data"
            )

        # Worker error
        try:
            raise ExtractionError("Failed to extract sprites")
        except Exception as e:
            self._error_handler.handle_worker_error(
                e, "SpriteExtractor", "extracting sprites from ROM"
            )

# Example 5: Testing Integration
def demonstrate_error_statistics():
    """Demonstrate error statistics gathering"""
    error_handler = get_unified_error_handler()

    # Generate some test errors
    test_errors = [
        (FileNotFoundError("test.file"), "reading file"),
        (ValidationError("invalid input"), "validating data"),
        (ExtractionError("extraction failed"), "extracting sprites"),
    ]

    for error, _operation in test_errors:
        try:
            raise error
        except Exception as e:
            error_handler.handle_exception(e)

    # Get statistics
    stats = error_handler.get_error_statistics()
    print("Error Statistics:")
    print(f"Total errors: {stats['total_errors']}")
    print(f"By category: {stats['categories']}")
    print(f"By severity: {stats['severities']}")

    return stats

# Example usage functions
def example_worker_usage():
    """Demonstrate worker error handling usage"""
    worker = ExampleWorker()

    # Connect error signals
    worker.error.connect(lambda msg, exc: print(f"Worker error: {msg}"))
    worker.finished.connect(lambda result: print(f"Worker finished: {len(result)} sprites"))

    # This will trigger error handling if file doesn't exist
    worker.extract_sprites("test_rom.smc")

def example_widget_usage():
    """Demonstrate widget error handling usage"""

    QApplication(sys.argv)
    widget = ExampleWidget()

    # These operations will trigger different error handling patterns
    widget.validate_sprite_params(-1, 10)  # Validation error
    widget.load_sprite_file("nonexistent.file")  # File error
    widget.update_sprite_display(b"")  # Qt error

    # Show error statistics
    stats = widget.get_error_statistics()
    print(f"Widget error stats: {stats}")

if __name__ == "__main__":
    # Run demonstrations
    print("=== Error Statistics Demo ===")
    demonstrate_error_statistics()

    print("\n=== Worker Error Handling Demo ===")
    example_worker_usage()

    print("\n=== Widget Error Handling Demo ===")
    example_widget_usage()
