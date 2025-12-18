"""
Test the defensive validation fix in controller.start_extraction().

This validates that the fix eliminates the 2+ minute blocking behavior
with invalid file paths, ensuring fail-fast behavior.

NOTE: Creates real MainWindow which may crash in Qt offscreen mode.
These tests use qt_widget_test(MainWindow). Marked xfail for offscreen mode.
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import pytest

# Determine if running in offscreen mode
_is_offscreen = os.environ.get("QT_QPA_PLATFORM") == "offscreen"

# NOTE: pythonpath configured in pyproject.toml - no sys.path manipulation needed

# Systematic pytest markers applied based on test content analysis
# xfail for offscreen mode - real MainWindow may crash
pytestmark = [
    pytest.mark.dialog,
    pytest.mark.file_io,
    pytest.mark.gui,  # Changed from headless - this creates real Qt widgets
    pytest.mark.mock_dialogs,
    pytest.mark.qt_real,  # Changed from no_qt - this creates real Qt widgets
    pytest.mark.rom_data,
    pytest.mark.integration,  # Changed from unit - this is integration testing
    pytest.mark.widget,
    pytest.mark.ci_safe,
    pytest.mark.xfail(
        _is_offscreen,
        reason="Creates real MainWindow which may crash in Qt offscreen mode",
        strict=False,  # Passes if unexpectedly works
    ),
]

from core.controller import ExtractionController
from tests.infrastructure import (
    ApplicationFactory,
    qt_widget_test,
)
from tests.infrastructure.test_data_repository import get_test_data_repository
from ui.main_window import MainWindow


class TestControllerDefensiveValidationFix:
    """Test that the defensive validation fix prevents blocking behavior."""

    @pytest.fixture(autouse=True)
    def setup_test_infrastructure(self, isolated_managers):
        """Set up testing infrastructure using isolated_managers fixture."""
        self.qt_app = ApplicationFactory.get_application()
        yield

    def test_fixed_fast_failure_with_invalid_vram_path(self):
        """Test that invalid VRAM path fails fast (< 1 second) after fix."""
        print("=== TESTING FIXED FAST FAILURE WITH INVALID VRAM PATH ===")

        # Managers initialized by isolated_managers fixture

        with qt_widget_test(MainWindow) as main_window:
            controller = ExtractionController(main_window)

            # Track extraction_failed calls
            extraction_failed_called = []
            original_extraction_failed = main_window.extraction_failed

            def track_extraction_failed(message):
                extraction_failed_called.append(message)
                print(f"extraction_failed called with: {message}")
                # Don't call original to avoid blocking modal dialog
                # Just update button state for test validation
                extract_button = getattr(main_window, "extract_button", None)
                if extract_button:
                    extract_button.setEnabled(True)
                if hasattr(main_window, "status_bar") and main_window.status_bar:
                    main_window.status_bar.showMessage("Extraction failed")

            main_window.extraction_failed = track_extraction_failed

            # Mock invalid params
            invalid_params = {
                "vram_path": "/nonexistent/path.dmp",
                "cgram_path": "/nonexistent/cgram.dmp",
                "output_base": "/invalid/output/path",
                "create_grayscale": True,
                "grayscale_mode": False,  # Force CGRAM validation
            }

            # Mock the get_extraction_params method
            original_get_params = main_window.get_extraction_params
            main_window.get_extraction_params = lambda: invalid_params

            start_time = time.time()

            try:
                # This should now fail FAST with defensive validation
                controller.start_extraction()
                elapsed = time.time() - start_time

                # Should complete very quickly due to defensive validation
                print(f"Controller.start_extraction() completed in {elapsed:.3f}s")
                assert elapsed < 1.0, f"Should fail fast, took {elapsed:.3f}s"

                # Should have called extraction_failed due to invalid VRAM path
                assert len(extraction_failed_called) > 0, "Should have called extraction_failed"
                error_message = extraction_failed_called[0]
                assert "does not exist" in error_message, f"Should be file existence error: {error_message}"
                assert "/nonexistent/path.dmp" in error_message, "Should mention the invalid VRAM path"

                print(f"✅ SUCCESS: Fast failure in {elapsed:.3f}s with message: {error_message}")

            finally:
                # Restore methods
                main_window.get_extraction_params = original_get_params
                main_window.extraction_failed = original_extraction_failed

    def test_fixed_fast_failure_with_invalid_cgram_path(self, tmp_path):
        """Test that invalid CGRAM path fails fast in Full Color mode."""
        print("=== TESTING FIXED FAST FAILURE WITH INVALID CGRAM PATH ===")

        # Managers initialized by isolated_managers fixture

        with qt_widget_test(MainWindow) as main_window:
            controller = ExtractionController(main_window)

            # Track extraction_failed calls
            extraction_failed_called = []
            original_extraction_failed = main_window.extraction_failed

            def track_extraction_failed(message):
                extraction_failed_called.append(message)
                print(f"extraction_failed called with: {message}")
                # Don't call original to avoid blocking modal dialog
                extract_button = getattr(main_window, "extract_button", None)
                if extract_button:
                    extract_button.setEnabled(True)
                if hasattr(main_window, "status_bar") and main_window.status_bar:
                    main_window.status_bar.showMessage("Extraction failed")

            main_window.extraction_failed = track_extraction_failed

            # Create a realistic VRAM file using DataRepository
            repo = get_test_data_repository()
            test_data = repo.get_vram_extraction_data("medium")  # Creates 64KB VRAM file
            vram_path = test_data["vram_path"]

            try:
                # Valid VRAM, invalid CGRAM, Full Color mode
                invalid_params = {
                    "vram_path": vram_path,  # Valid file
                    "cgram_path": "/nonexistent/cgram.dmp",  # Invalid file
                    "output_base": str(tmp_path / "test_output"),
                    "create_grayscale": True,
                    "grayscale_mode": False,  # Full Color mode - requires CGRAM
                }

                # Mock the get_extraction_params method
                original_get_params = main_window.get_extraction_params
                main_window.get_extraction_params = lambda: invalid_params

                start_time = time.time()

                # This should fail fast due to invalid CGRAM in Full Color mode
                controller.start_extraction()
                elapsed = time.time() - start_time

                print(f"Controller.start_extraction() completed in {elapsed:.3f}s")
                assert elapsed < 1.0, f"Should fail fast, took {elapsed:.3f}s"

                # Should have called extraction_failed due to invalid CGRAM path
                assert len(extraction_failed_called) > 0, "Should have called extraction_failed"
                error_message = extraction_failed_called[0]
                assert "does not exist" in error_message, f"Should be file existence error: {error_message}"
                assert "/nonexistent/cgram.dmp" in error_message, "Should mention the invalid CGRAM path"

                print(f"✅ SUCCESS: Fast CGRAM failure in {elapsed:.3f}s with message: {error_message}")

            finally:
                # Cleanup
                main_window.get_extraction_params = original_get_params
                main_window.extraction_failed = original_extraction_failed
                repo.cleanup()

    def test_fixed_grayscale_mode_bypasses_cgram_validation(self, tmp_path):
        """Test that Grayscale Only mode bypasses CGRAM validation correctly."""
        print("=== TESTING GRAYSCALE MODE CGRAM BYPASS ===")

        # Managers initialized by isolated_managers fixture

        with qt_widget_test(MainWindow) as main_window:
            controller = ExtractionController(main_window)

            # Track calls
            extraction_failed_called = []
            original_extraction_failed = main_window.extraction_failed

            def track_extraction_failed(message):
                extraction_failed_called.append(message)
                # Don't call original to avoid blocking modal dialog
                extract_button = getattr(main_window, "extract_button", None)
                if extract_button:
                    extract_button.setEnabled(True)
                if hasattr(main_window, "status_bar") and main_window.status_bar:
                    main_window.status_bar.showMessage("Extraction failed")

            main_window.extraction_failed = track_extraction_failed

            # Create a realistic VRAM file using DataRepository
            repo = get_test_data_repository()
            test_data = repo.get_vram_extraction_data("medium")  # Creates 64KB VRAM file
            vram_path = test_data["vram_path"]

            try:
                # Valid VRAM, invalid CGRAM, but Grayscale mode (should bypass CGRAM check)
                params = {
                    "vram_path": vram_path,  # Valid file
                    "cgram_path": "/nonexistent/cgram.dmp",  # Invalid but should be ignored
                    "output_base": str(tmp_path / "test_output"),
                    "create_grayscale": True,
                    "grayscale_mode": True,  # Grayscale mode - CGRAM not required
                }

                original_get_params = main_window.get_extraction_params
                main_window.get_extraction_params = lambda: params

                start_time = time.time()

                # This should NOT fail due to invalid CGRAM in Grayscale mode
                controller.start_extraction()
                elapsed = time.time() - start_time

                print(f"Controller.start_extraction() completed in {elapsed:.3f}s")

                # Should either proceed to worker creation or fail on manager validation
                # But NOT fail on CGRAM defensive validation in grayscale mode
                if len(extraction_failed_called) > 0:
                    error_message = extraction_failed_called[0]
                    print(f"Failed with: {error_message}")
                    # If it failed, should NOT be due to CGRAM path (grayscale mode bypasses)
                    assert "cgram.dmp" not in error_message.lower(), "Should not fail on CGRAM in grayscale mode"
                else:
                    print("✅ SUCCESS: Grayscale mode bypassed CGRAM validation")

            finally:
                # Cleanup
                main_window.get_extraction_params = original_get_params
                main_window.extraction_failed = original_extraction_failed
                repo.cleanup()

if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
