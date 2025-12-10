"""
Test suite for HAL compression tool detection robustness.

Tests the fix for intermittent exhal/inhal detection issues that occurred
when the application was launched from different working directories.
"""
from __future__ import annotations

import os
import platform
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from core.hal_compression import HALCompressionError, HALCompressor

# Mark as no_manager_setup - pure unit tests for HAL compression
# Uses mock_hal to prevent crashes from real HAL tool detection
pytestmark = [
    pytest.mark.no_manager_setup,
    pytest.mark.unit,
    pytest.mark.ci_safe,
    pytest.mark.file_io,
    pytest.mark.headless,
    pytest.mark.usefixtures("mock_hal"),  # HAL mocking
]

class TestHALToolDetection(unittest.TestCase):
    """Test HAL tool detection from various working directories"""

    def setUp(self):
        """Set up test environment"""
        self.original_cwd = os.getcwd()
        self.spritepal_dir = Path(__file__).parent.parent
        self.tools_dir = self.spritepal_dir / "tools"

        # Platform-specific executable suffix
        self.exe_suffix = ".exe" if platform.system() == "Windows" else ""
        self.exhal_name = f"exhal{self.exe_suffix}"
        self.inhal_name = f"inhal{self.exe_suffix}"

    def tearDown(self):
        """Restore original working directory"""
        os.chdir(self.original_cwd)

    def test_detection_from_spritepal_directory(self):
        """Test that detection works from spritepal directory (original working case)"""
        os.chdir(self.spritepal_dir)

        compressor = HALCompressor()

        self.assertTrue(Path(compressor.exhal_path).exists())
        self.assertTrue(Path(compressor.inhal_path).exists())
        self.assertIn("spritepal/tools", compressor.exhal_path)
        self.assertIn("spritepal/tools", compressor.inhal_path)

    def test_detection_from_parent_directory(self):
        """Test that detection works from exhal-master directory (previously failing case)"""
        parent_dir = self.spritepal_dir.parent
        os.chdir(parent_dir)

        compressor = HALCompressor()

        self.assertTrue(Path(compressor.exhal_path).exists())
        self.assertTrue(Path(compressor.inhal_path).exists())
        self.assertIn("spritepal/tools", compressor.exhal_path)
        self.assertIn("spritepal/tools", compressor.inhal_path)

    def test_detection_from_temp_directory(self):
        """Test that detection works from a temporary directory"""
        with tempfile.TemporaryDirectory() as temp_dir:
            os.chdir(temp_dir)

            compressor = HALCompressor()

            self.assertTrue(Path(compressor.exhal_path).exists())
            self.assertTrue(Path(compressor.inhal_path).exists())
            self.assertIn("spritepal/tools", compressor.exhal_path)
            self.assertIn("spritepal/tools", compressor.inhal_path)

    def test_detection_from_home_directory(self):
        """Test that detection works from user home directory"""
        try:
            home_dir = Path.home()
            os.chdir(home_dir)

            compressor = HALCompressor()

            self.assertTrue(Path(compressor.exhal_path).exists())
            self.assertTrue(Path(compressor.inhal_path).exists())
            self.assertIn("spritepal/tools", compressor.exhal_path)
            self.assertIn("spritepal/tools", compressor.inhal_path)
        except (OSError, PermissionError) as e:
            self.skipTest(f"Cannot access home directory: {e}")

    def test_absolute_path_resolution(self):
        """Test that the fix uses absolute paths and doesn't depend on working directory"""
        # Test from spritepal directory
        os.chdir(self.spritepal_dir)
        compressor1 = HALCompressor()

        # Test from parent directory
        os.chdir(self.spritepal_dir.parent)
        compressor2 = HALCompressor()

        # Both should find the same absolute paths
        self.assertEqual(compressor1.exhal_path, compressor2.exhal_path)
        self.assertEqual(compressor1.inhal_path, compressor2.inhal_path)

        # Paths should be absolute
        self.assertTrue(Path(compressor1.exhal_path).is_absolute())
        self.assertTrue(Path(compressor1.inhal_path).is_absolute())

    def test_tools_are_executable(self):
        """Test that detected tools are actually executable"""
        compressor = HALCompressor()

        # Test that tools have execute permissions
        self.assertTrue(os.access(compressor.exhal_path, os.X_OK))
        self.assertTrue(os.access(compressor.inhal_path, os.X_OK))

    def test_tools_functionality(self):
        """Test that detected tools actually work"""
        compressor = HALCompressor()

        success, message = compressor.test_tools()
        self.assertTrue(success)
        self.assertIn("working correctly", message)

    def test_provided_path_override(self):
        """Test that provided paths override automatic detection"""
        # Create a dummy executable file
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix=self.exe_suffix) as tmp:
            dummy_exhal = tmp.name

        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix=self.exe_suffix) as tmp:
            dummy_inhal = tmp.name

        try:
            # Make files executable
            os.chmod(dummy_exhal, 0o755)
            os.chmod(dummy_inhal, 0o755)

            compressor = HALCompressor(exhal_path=dummy_exhal, inhal_path=dummy_inhal)

            self.assertEqual(compressor.exhal_path, dummy_exhal)
            self.assertEqual(compressor.inhal_path, dummy_inhal)

        finally:
            # Clean up
            Path(dummy_exhal).unlink(missing_ok=True)
            Path(dummy_inhal).unlink(missing_ok=True)

    def test_multiple_initialization_consistency(self):
        """Test that multiple HALCompressor instances find the same tools"""
        paths = []

        # Create multiple instances from different working directories
        for test_dir in [self.spritepal_dir, self.spritepal_dir.parent]:
            os.chdir(test_dir)
            compressor = HALCompressor()
            paths.append((compressor.exhal_path, compressor.inhal_path))

        # All instances should find the same tools
        for i in range(1, len(paths)):
            self.assertEqual(paths[0], paths[i],
                           f"Instance {i} found different tools than instance 0")

    def test_spritepal_directory_calculation(self):
        """Test that the spritepal directory is calculated correctly from different contexts"""
        # The fix calculates spritepal_dir as Path(__file__).parent.parent
        # This should always point to the spritepal directory regardless of working directory

        test_dirs = [
            self.spritepal_dir,
            self.spritepal_dir.parent,
            Path.cwd(),
        ]

        for test_dir in test_dirs:
            if not test_dir.exists():
                continue

            os.chdir(test_dir)

            # Import the module to get the calculated spritepal_dir
            # This simulates what happens in _find_tool
            hal_compression_file = self.spritepal_dir / "core" / "hal_compression.py"
            calculated_spritepal = hal_compression_file.parent.parent

            self.assertEqual(calculated_spritepal.name, "spritepal")
            self.assertTrue((calculated_spritepal / "tools").exists())


class TestHALToolDetectionRegression(unittest.TestCase):
    """Regression tests to prevent the working directory bug from reoccurring"""

    def setUp(self):
        self.original_cwd = os.getcwd()
        self.spritepal_dir = Path(__file__).parent.parent

    def tearDown(self):
        os.chdir(self.original_cwd)

    def test_no_relative_path_dependency(self):
        """Ensure the fix doesn't rely on relative paths that depend on working directory"""
        # Change to a directory where relative paths would fail
        os.chdir(Path("/tmp"))

        # This should still work because the fix uses absolute paths
        compressor = HALCompressor()

        # Verify paths are absolute and exist
        self.assertTrue(Path(compressor.exhal_path).is_absolute())
        self.assertTrue(Path(compressor.inhal_path).is_absolute())
        self.assertTrue(Path(compressor.exhal_path).exists())
        self.assertTrue(Path(compressor.inhal_path).exists())

    def test_intermittent_failure_scenario(self):
        """Test the exact scenario that was causing intermittent failures"""
        # Simulate application startup from exhal-master directory
        # This was the scenario causing the original bug
        exhal_master_dir = self.spritepal_dir.parent

        if not exhal_master_dir.exists():
            self.skipTest("exhal-master directory not found")

        os.chdir(exhal_master_dir)

        # This should now work consistently (was failing intermittently before)
        for i in range(5):  # Test multiple times to catch intermittent issues
            compressor = HALCompressor()
            self.assertTrue(Path(compressor.exhal_path).exists())
            self.assertTrue(Path(compressor.inhal_path).exists())

    def test_manager_initialization_robustness(self):
        """Test that manager initialization works regardless of working directory"""
        from core.managers import cleanup_managers, get_injection_manager, initialize_managers

        # Test from different directories
        test_dirs = [
            self.spritepal_dir,
            self.spritepal_dir.parent,
        ]

        for test_dir in test_dirs:
            if not test_dir.exists():
                continue

            os.chdir(test_dir)

            # Actually test manager initialization from this directory
            # (This was failing before the fix when working directory was wrong)
            try:
                # Initialize managers - this is what we're testing
                initialize_managers(app_name="SpritePal_Test")

                # Verify initialization succeeded by getting a manager
                manager = get_injection_manager()
                self.assertIsNotNone(manager)

            except Exception as e:
                self.fail(f"Manager initialization failed from {test_dir}: {e}")
            finally:
                # Clean up managers to prevent interference with other tests
                # This test class has no_manager_setup marker, so other tests expect no managers
                try:
                    cleanup_managers()
                except Exception:
                    pass  # Ignore cleanup errors

if __name__ == '__main__':
    unittest.main()
