from unittest.mock import MagicMock, patch

import pytest

from core.managers.core_operations_manager import CoreOperationsManager


def test_validate_extraction_params_accepts_sprite_offset(tmp_path):
    """Regression test: validate_extraction_params should accept 'sprite_offset'.

    This tests that the validator accepts both 'offset' and 'sprite_offset' parameter
    names for ROM extraction, ensuring backward compatibility.
    """
    # Create a real ROM file (minimum size to pass validation)
    rom_file = tmp_path / "test.sfc"
    rom_file.write_bytes(b"\x00" * 0x10000)  # 64KB ROM

    # Mock dependencies
    mock_session = MagicMock()
    mock_rom_cache = MagicMock()
    mock_rom_extractor = MagicMock()

    # Initialize manager with mocked internal dependencies to avoid side effects
    with (
        patch("core.managers.core_operations_manager.SpriteExtractor"),
        patch("core.managers.core_operations_manager.PaletteManager"),
    ):
        manager = CoreOperationsManager(
            session_manager=mock_session, rom_cache=mock_rom_cache, rom_extractor=mock_rom_extractor
        )

    # Verify initialization was successful
    assert manager.is_initialized()

    params = {
        "rom_path": str(rom_file),
        "sprite_offset": 0x1000,  # Valid offset within ROM bounds
        "output_base": "output",
    }

    # Should not raise - validates that sprite_offset is accepted
    assert manager.validate_extraction_params(params) is True


def test_validate_extraction_params_accepts_offset(tmp_path):
    """Test that the original 'offset' parameter name still works."""
    # Create a real ROM file
    rom_file = tmp_path / "test.sfc"
    rom_file.write_bytes(b"\x00" * 0x10000)  # 64KB ROM

    # Mock dependencies
    mock_session = MagicMock()
    mock_rom_cache = MagicMock()
    mock_rom_extractor = MagicMock()

    # Initialize manager with mocked internal dependencies
    with (
        patch("core.managers.core_operations_manager.SpriteExtractor"),
        patch("core.managers.core_operations_manager.PaletteManager"),
    ):
        manager = CoreOperationsManager(
            session_manager=mock_session, rom_cache=mock_rom_cache, rom_extractor=mock_rom_extractor
        )

    params = {
        "rom_path": str(rom_file),
        "offset": 0x1000,  # Using original 'offset' name
        "output_base": "output",
    }

    # Should not raise
    assert manager.validate_extraction_params(params) is True
