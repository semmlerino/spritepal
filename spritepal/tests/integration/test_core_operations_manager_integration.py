"""
Integration tests for CoreOperationsManager.

These tests verify the consolidated manager path works correctly,
particularly the extract_from_vram method that was previously broken
due to calling a non-existent extract_sprite method on SpriteExtractor.
"""
from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def vram_test_data(temp_dir: Path) -> Path:
    """Create a valid VRAM dump file for testing.

    Creates a 64KB VRAM file with recognizable 4bpp tile patterns.
    """
    vram_path = temp_dir / "test_vram.bin"

    # Create 64KB VRAM dump
    vram_size = 65536  # 64KB standard VRAM size
    vram_data = bytearray(vram_size)

    # Fill with tile patterns starting at sprite offset (0x0000 for test)
    # Each 4bpp SNES tile is 32 bytes
    bytes_per_tile = 32
    num_tiles = 64  # Create 64 test tiles

    for tile_idx in range(num_tiles):
        tile_offset = tile_idx * bytes_per_tile
        # Create simple gradient pattern for each tile
        for byte_idx in range(bytes_per_tile):
            vram_data[tile_offset + byte_idx] = (tile_idx + byte_idx) % 256

    vram_path.write_bytes(bytes(vram_data))
    return vram_path


@pytest.mark.headless
class TestCoreOperationsManagerVRAMExtraction:
    """Tests for the VRAM extraction path in CoreOperationsManager."""

    def test_extract_from_vram_returns_success(
        self,
        temp_dir: Path,
        vram_test_data: Path,
        managers_initialized,
    ) -> None:
        """Ensure extract_from_vram completes without AttributeError.

        This test verifies the fix for the broken extract_sprite method call.
        Previously, CoreOperationsManager.extract_from_vram would raise:
            AttributeError: 'SpriteExtractor' object has no attribute 'extract_sprite'
        """
        from core.managers.core_operations_manager import CoreOperationsManager

        manager = CoreOperationsManager()

        output_base = str(temp_dir / "output")

        result = manager.extract_from_vram(
            vram_path=str(vram_test_data),
            output_base=output_base,
        )

        # Verify result structure
        assert isinstance(result, dict)
        assert result.get("success") is True
        assert "image" in result
        assert "tile_count" in result
        assert "output_path" in result

    def test_extract_from_vram_creates_output_file(
        self,
        temp_dir: Path,
        vram_test_data: Path,
        managers_initialized,
    ) -> None:
        """Verify that extract_from_vram creates the output PNG file."""
        from core.managers.core_operations_manager import CoreOperationsManager

        manager = CoreOperationsManager()

        output_base = str(temp_dir / "extraction_output")

        result = manager.extract_from_vram(
            vram_path=str(vram_test_data),
            output_base=output_base,
        )

        assert result.get("success") is True

        # Check output file was created
        output_path = Path(result["output_path"])
        assert output_path.exists()
        assert output_path.suffix == ".png"

    def test_extract_from_vram_with_offset(
        self,
        temp_dir: Path,
        vram_test_data: Path,
        managers_initialized,
    ) -> None:
        """Test extraction with a custom VRAM offset."""
        from core.managers.core_operations_manager import CoreOperationsManager

        manager = CoreOperationsManager()

        output_base = str(temp_dir / "offset_output")

        result = manager.extract_from_vram(
            vram_path=str(vram_test_data),
            output_base=output_base,
            vram_offset=0x100,  # Start 256 bytes in
        )

        assert isinstance(result, dict)
        # May fail if offset is invalid, but should not raise AttributeError
        # The important thing is that extract_sprite method exists and is called

    def test_extract_from_vram_optional_params_stored(
        self,
        temp_dir: Path,
        vram_test_data: Path,
        managers_initialized,
    ) -> None:
        """Test that optional cgram/oam paths are stored in result."""
        from core.managers.core_operations_manager import CoreOperationsManager

        manager = CoreOperationsManager()

        output_base = str(temp_dir / "params_output")

        # Create dummy cgram/oam files
        cgram_path = temp_dir / "test.cgram"
        oam_path = temp_dir / "test.oam"
        cgram_path.write_bytes(b"\x00" * 512)
        oam_path.write_bytes(b"\x00" * 544)

        result = manager.extract_from_vram(
            vram_path=str(vram_test_data),
            output_base=output_base,
            cgram_path=str(cgram_path),
            oam_path=str(oam_path),
        )

        assert result.get("success") is True
        assert result.get("cgram_path") == str(cgram_path)
        assert result.get("oam_path") == str(oam_path)


@pytest.mark.headless
class TestSpriteExtractorExtractSprite:
    """Direct tests for the new extract_sprite method on SpriteExtractor."""

    def test_extract_sprite_method_exists(self) -> None:
        """Verify extract_sprite method exists on SpriteExtractor."""
        from core.extractor import SpriteExtractor

        extractor = SpriteExtractor()
        assert hasattr(extractor, "extract_sprite")
        assert callable(extractor.extract_sprite)

    def test_extract_sprite_returns_dict(
        self,
        temp_dir: Path,
        vram_test_data: Path,
    ) -> None:
        """Verify extract_sprite returns a dict with expected keys."""
        from core.extractor import SpriteExtractor

        extractor = SpriteExtractor()
        output_base = str(temp_dir / "sprite_output")

        result = extractor.extract_sprite(
            vram_path=str(vram_test_data),
            output_base=output_base,
        )

        assert isinstance(result, dict)
        assert "success" in result
        assert "image" in result
        assert "tile_count" in result
        assert "output_path" in result

    def test_extract_sprite_signature_matches_caller(
        self,
        temp_dir: Path,
        vram_test_data: Path,
    ) -> None:
        """Verify extract_sprite accepts all parameters CoreOperationsManager passes."""
        from core.extractor import SpriteExtractor

        extractor = SpriteExtractor()
        output_base = str(temp_dir / "sig_test")

        # Call with all parameters that CoreOperationsManager passes
        result = extractor.extract_sprite(
            str(vram_test_data),  # vram_path positional
            output_base,  # output_base positional
            cgram_path=None,
            oam_path=None,
            vram_offset=None,
            create_grayscale=True,
            create_metadata=True,
            create_palette_files=True,
        )

        assert result.get("success") is True
