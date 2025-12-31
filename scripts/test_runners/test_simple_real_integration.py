"""
Simple real integration test to validate testing infrastructure with pytest.

This test validates the core functionality without complex dialogs that might hang.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Add parent directory for imports
current_dir = Path(__file__).parent
parent_dir = current_dir.parent
sys.path.insert(0, str(parent_dir))
sys.path.insert(0, str(current_dir))

import pytest

from core.exceptions import ValidationError
from tests.infrastructure import (
    DataRepository,
    RealManagerFixtureFactory,
    TestApplicationFactory,
)


class TestSimpleRealIntegration:
    """Simple real integration tests to validate infrastructure."""

    @pytest.fixture(autouse=True)
    def setup_test_infrastructure(self):
        """Set up real testing infrastructure for each test."""
        # Initialize Qt application
        self.qt_app = TestApplicationFactory.get_application()

        # Initialize real manager factory
        self.manager_factory = RealManagerFixtureFactory(qt_parent=self.qt_app)

        # Initialize test data repository
        self.test_data = DataRepository()

        yield

        # Cleanup
        self.manager_factory.cleanup()
        self.test_data.cleanup()

    def test_real_manager_creation_and_validation(self):
        """Test real manager creation and validation with real data."""
        # Create real extraction manager (worker-owned pattern)
        extraction_manager = self.manager_factory.create_extraction_manager(isolated=True)

        # Validate manager has proper Qt parent
        assert extraction_manager.parent() is self.qt_app

        # Test validation with invalid parameters (should raise ValidationError)
        invalid_params = {
            "vram_path": "/nonexistent/file.dmp",  # Non-existent file
            "output_base": "test_output",
        }

        # This tests our bug fix - validation should raise ValidationError, not return None
        with pytest.raises(ValidationError):
            extraction_manager.validate_extraction_params(invalid_params)

    def test_real_manager_validation_success(self):
        """Test that validation returns True for valid parameters."""
        # Get real test data
        extraction_data = self.test_data.get_vram_extraction_data("small")

        # Create real extraction manager
        extraction_manager = self.manager_factory.create_extraction_manager(isolated=True)

        # Test with valid parameters
        valid_params = {
            "vram_path": extraction_data["vram_path"],
            "cgram_path": extraction_data["cgram_path"],
            "output_base": extraction_data["output_base"],
            "grayscale_mode": True,  # Skip palette validation
        }

        # This should return True (our bug fix working)
        is_valid = extraction_manager.validate_extraction_params(valid_params)
        assert is_valid is True, "Valid parameters should return True"

        # Verify the return type is boolean (not None)
        assert isinstance(is_valid, bool), "Validation should return boolean, not None"

    def test_real_vs_mock_validation_comparison(self):
        """Demonstrate that real validation catches bugs mocks would miss."""
        # Create real manager
        extraction_manager = self.manager_factory.create_extraction_manager(isolated=True)

        # Test cases that reveal real behavior vs mock behavior
        test_cases = [
            {"name": "Empty VRAM path", "params": {"vram_path": "", "output_base": "test"}, "should_fail": True},
            {"name": "Missing output_base", "params": {"vram_path": "/tmp/test.dmp"}, "should_fail": True},
            {"name": "None values", "params": {"vram_path": None, "output_base": None}, "should_fail": True},
        ]

        for case in test_cases:
            if case["should_fail"]:
                # Real validation should catch these issues
                with pytest.raises(Exception, match="validation|required|invalid"):
                    extraction_manager.validate_extraction_params(case["params"])
            else:
                # Should pass validation
                result = extraction_manager.validate_extraction_params(case["params"])
                assert result is True

    def test_multiple_manager_isolation(self):
        """Test that isolated managers don't interfere with each other."""
        # Create multiple isolated managers
        manager1 = self.manager_factory.create_extraction_manager(isolated=True)
        manager2 = self.manager_factory.create_extraction_manager(isolated=True)

        # Verify they're different instances
        assert manager1 is not manager2

        # Verify they both have the same Qt parent
        assert manager1.parent() is self.qt_app
        assert manager2.parent() is self.qt_app

        # Verify they can operate independently
        # This would fail with singleton pattern or improper mocking
        state1 = manager1._active_operations  # Access internal state
        state2 = manager2._active_operations

        assert state1 is not state2, "Isolated managers should have separate state"


if __name__ == "__main__":
    # Run the simple tests directly
    pytest.main([__file__, "-v"])
