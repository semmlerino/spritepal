"""
Integration tests for CoreOperationsManager.

These tests verify the consolidated manager path works correctly,
particularly the extract_from_vram method that was previously broken
due to calling a non-existent extract_sprite method on SpriteExtractor.
"""
from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = [
    pytest.mark.usefixtures("session_managers"),
    pytest.mark.shared_state_safe,
    pytest.mark.skip_thread_cleanup(reason="Manager tests may spawn worker threads")
]


@pytest.fixture
def vram_test_data(tmp_path: Path) -> Path:
    """Create a valid VRAM dump file for testing.

    Creates a 64KB VRAM file with recognizable 4bpp tile patterns.
    """
    vram_path = tmp_path / "test_vram.bin"

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
        tmp_path: Path,
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

        output_base = str(tmp_path / "output")

        result = manager.extract_from_vram(
            vram_path=str(vram_test_data),
            output_base=output_base,
        )

        # CoreOperationsManager.extract_from_vram returns list[str] of created file paths
        assert isinstance(result, list)
        assert len(result) > 0
        # At least one PNG file should be created
        assert any(path.endswith(".png") for path in result)

    def test_extract_from_vram_creates_output_file(
        self,
        tmp_path: Path,
        vram_test_data: Path,
        managers_initialized,
    ) -> None:
        """Verify that extract_from_vram creates the output PNG file."""
        from core.managers.core_operations_manager import CoreOperationsManager

        manager = CoreOperationsManager()

        output_base = str(tmp_path / "extraction_output")

        result = manager.extract_from_vram(
            vram_path=str(vram_test_data),
            output_base=output_base,
        )

        # Result is a list of created file paths
        assert isinstance(result, list)
        assert len(result) > 0

        # Check that at least one PNG output file was created
        png_files = [p for p in result if p.endswith(".png")]
        assert len(png_files) > 0
        output_path = Path(png_files[0])
        assert output_path.exists()
        assert output_path.suffix == ".png"

    def test_extract_from_vram_with_offset(
        self,
        tmp_path: Path,
        vram_test_data: Path,
        managers_initialized,
    ) -> None:
        """Test extraction with a custom VRAM offset."""
        from core.managers.core_operations_manager import CoreOperationsManager

        manager = CoreOperationsManager()

        output_base = str(tmp_path / "offset_output")

        result = manager.extract_from_vram(
            vram_path=str(vram_test_data),
            output_base=output_base,
            vram_offset=0x100,  # Start 256 bytes in
        )

        # Result is a list of created file paths
        assert isinstance(result, list)
        # May have fewer files if offset makes extraction partial, but should not raise AttributeError
        # The important thing is that the method completes successfully

    def test_extract_from_vram_with_cgram_oam(
        self,
        tmp_path: Path,
        vram_test_data: Path,
        managers_initialized,
    ) -> None:
        """Test that extraction works with optional cgram/oam paths."""
        from core.managers.core_operations_manager import CoreOperationsManager

        manager = CoreOperationsManager()

        output_base = str(tmp_path / "params_output")

        # Create dummy cgram/oam files
        cgram_path = tmp_path / "test.cgram"
        oam_path = tmp_path / "test.oam"
        cgram_path.write_bytes(b"\x00" * 512)
        oam_path.write_bytes(b"\x00" * 544)

        result = manager.extract_from_vram(
            vram_path=str(vram_test_data),
            output_base=output_base,
            cgram_path=str(cgram_path),
            oam_path=str(oam_path),
        )

        # Result is a list of created file paths
        assert isinstance(result, list)
        # Extraction should complete successfully with the extra paths provided
        assert len(result) > 0


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
        tmp_path: Path,
        vram_test_data: Path,
    ) -> None:
        """Verify extract_sprite returns a dict with expected keys."""
        from core.extractor import SpriteExtractor

        extractor = SpriteExtractor()
        output_base = str(tmp_path / "sprite_output")

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
        tmp_path: Path,
        vram_test_data: Path,
    ) -> None:
        """Verify extract_sprite accepts all parameters CoreOperationsManager passes."""
        from core.extractor import SpriteExtractor

        extractor = SpriteExtractor()
        output_base = str(tmp_path / "sig_test")

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
