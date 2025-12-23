"""
Integration tests for complete UI → Manager workflows

Uses isolated_managers fixture from core_fixtures.py for test isolation.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from core.di_container import inject
from core.exceptions import ValidationError
from core.managers.application_state_manager import ApplicationStateManager
from core.protocols.manager_protocols import (
    ExtractionManagerProtocol,
    InjectionManagerProtocol,
)


def get_extraction_manager():
    """Get extraction manager via DI."""
    return inject(ExtractionManagerProtocol)


def get_injection_manager():
    """Get injection manager via DI."""
    return inject(InjectionManagerProtocol)


def get_session_manager():
    """Get session manager via DI."""
    return inject(ApplicationStateManager)


from tests.fixtures.test_data_factory import TestDataFactory

pytestmark = [
    pytest.mark.headless,
    pytest.mark.integration,
    pytest.mark.usefixtures("isolated_managers"),
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

        # Create test files using TestDataFactory
        paths = TestDataFactory.create_injection_test_files(tmp_path)

        # Build ROM injection parameters
        rom_injection_params = {
            "mode": "rom",
            "sprite_path": str(paths.sprite_path),
            "input_rom": str(paths.rom_path),
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

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
