"""
Integration tests for complete UI → Manager workflows

Uses isolated_managers fixture from core_fixtures.py for test isolation.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from core.managers.exceptions import ValidationError
from core.managers.registry import ManagerRegistry


def get_extraction_manager():
    """Get extraction manager from registry."""
    return ManagerRegistry().get_extraction_manager()


def get_injection_manager():
    """Get injection manager from registry."""
    return ManagerRegistry().get_injection_manager()


def get_session_manager():
    """Get session manager from registry."""
    return ManagerRegistry().get_session_manager()


from tests.fixtures.test_managers import (
    # Systematic pytest markers applied based on test content analysis
    create_extraction_manager_fixture,
    create_injection_manager_fixture,
)

pytestmark = [
    pytest.mark.file_io,
    pytest.mark.headless,
    pytest.mark.integration,
    pytest.mark.no_qt,
    pytest.mark.rom_data,
    pytest.mark.usefixtures("isolated_managers"),  # Use isolated managers for test independence
]


class TestManagerCommunication:
    """Test communication patterns between managers"""

    def test_managers_share_session_data(self):
        """Test that managers can share data through session manager"""
        get_extraction_manager()
        get_injection_manager()
        session_manager = get_session_manager()

        # Set some session data
        test_vram_path = "/test/path/to/vram.dmp"
        session_manager.set("session", "vram_path", test_vram_path)

        # Managers should be able to access shared session data
        session_vram = session_manager.get("session", "vram_path", "")
        assert session_vram == test_vram_path

    def test_manager_error_handling_integration(self):
        """Test error handling across manager interactions"""
        extraction_manager = get_extraction_manager()
        injection_manager = get_injection_manager()

        # Test extraction with invalid parameters
        invalid_params = {
            "vram_path": "/nonexistent/vram.dmp",
            "output_base": "/invalid/output",
        }

        with pytest.raises(ValidationError):  # Should raise validation error
            extraction_manager.validate_extraction_params(invalid_params)

        # Test injection with invalid parameters
        invalid_injection_params = {
            "mode": "invalid_mode",
            "sprite_path": "/nonexistent/sprite.png",
            "offset": -100,
        }

        with pytest.raises(ValidationError):  # Should raise validation error
            injection_manager.validate_injection_params(invalid_injection_params)

    def test_rom_injection_workflow_integration(self, tmp_path):
        """Test ROM injection workflow integration"""
        injection_manager = get_injection_manager()

        # Use injection manager fixture to create real test files
        injection_fixture = create_injection_manager_fixture(str(tmp_path))

        try:
            # Get real ROM injection parameters from fixture
            fixture_params = injection_fixture.get_rom_injection_params()

            # Convert fixture parameter names to manager expected names
            rom_injection_params = {
                "mode": "rom",
                "sprite_path": fixture_params["sprite_path"],
                "input_rom": fixture_params["input_rom_path"],
                "output_rom": str(tmp_path / "output.sfc"),
                "offset": 0x8000,
                "fast_compression": True,
            }

            # Validate ROM injection parameters with real manager
            injection_manager.validate_injection_params(rom_injection_params)

            # Verify ROM injection parameters are properly structured
            assert Path(rom_injection_params["sprite_path"]).exists()
            assert Path(rom_injection_params["input_rom"]).exists()
            assert rom_injection_params["offset"] == 0x8000
            assert rom_injection_params["mode"] == "rom"
            assert rom_injection_params["fast_compression"] is True

        finally:
            injection_fixture.cleanup()

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
