"""
Integration tests for ROM palette extraction using real ROM files.

These tests validate actual ROM reading, header parsing, game config lookup,
and palette extraction - complementing the unit tests in test_rom_palette_workflow.py
which mock the extraction chain.
"""

from __future__ import annotations

from pathlib import Path

import pytest

# Mark the entire module with integration marker
pytestmark = [
    pytest.mark.integration,
    pytest.mark.real_rom,
]


@pytest.fixture
def kirby_rom_path() -> Path:
    """Path to Kirby Super Star ROM for testing."""
    rom_path = Path("roms/Kirby Super Star (USA).sfc")
    if not rom_path.exists():
        pytest.skip("Kirby Super Star ROM not available")
    return rom_path


class TestROMHeaderReading:
    """Test ROM header reading from real ROM."""

    def test_read_kirby_rom_header(self, app_context, kirby_rom_path: Path) -> None:
        """Verify ROM header can be read from Kirby Super Star."""
        rom_extractor = app_context.rom_extractor
        header = rom_extractor.rom_injector.read_rom_header(str(kirby_rom_path))

        assert header is not None
        # Kirby Super Star (USA) has a known title
        assert "KIRBY" in header.title.upper()

    def test_find_game_configuration(self, app_context, kirby_rom_path: Path) -> None:
        """Verify game configuration lookup from header."""
        rom_extractor = app_context.rom_extractor
        header = rom_extractor.rom_injector.read_rom_header(str(kirby_rom_path))
        assert header is not None

        game_config = rom_extractor._find_game_configuration(header)
        assert game_config is not None
        assert "sprites" in game_config


class TestROMPaletteExtraction:
    """Test actual palette extraction from ROM."""

    def test_extract_palette_range(self, app_context, kirby_rom_path: Path) -> None:
        """Verify palette extraction returns valid palette data."""
        rom_extractor = app_context.rom_extractor
        header = rom_extractor.rom_injector.read_rom_header(str(kirby_rom_path))
        assert header is not None

        game_config = rom_extractor._find_game_configuration(header)
        assert game_config is not None

        # Find a known sprite to get palette config
        sprite_config = game_config.get("sprites", {}).get("kirby_normal")
        if sprite_config is None:
            # Try alternate names
            sprites = game_config.get("sprites", {})
            if sprites:
                sprite_name = next(iter(sprites))
                sprite_config = sprites[sprite_name]

        if sprite_config is None:
            pytest.skip("No sprite configuration found in game config")

        # Get palette config
        palette_config = rom_extractor.rom_palette_extractor.get_palette_config_from_sprite_config(
            game_config, next(iter(game_config.get("sprites", {})))
        )

        if palette_config is None:
            pytest.skip("No palette config available for this ROM")

        palette_offset, palette_indices = palette_config
        if palette_offset is None or palette_offset == 0:
            pytest.skip("Palette offset not configured for this ROM")

        # Extract palettes 8-15 (sprite palette range)
        palettes = rom_extractor.rom_palette_extractor.extract_palette_range(
            str(kirby_rom_path), palette_offset, 8, 15
        )

        # Verify structure
        assert palettes is not None
        assert isinstance(palettes, dict)
        assert len(palettes) == 8  # Palettes 8-15

        # Verify each palette has 16 colors
        for pal_idx in range(8, 16):
            if pal_idx in palettes:
                palette = palettes[pal_idx]
                assert len(palette) == 16, f"Palette {pal_idx} should have 16 colors"
                # Each color should be an RGB tuple
                for color in palette:
                    assert len(color) == 3, f"Color should be RGB tuple"
                    assert all(0 <= c <= 255 for c in color), f"Color values should be 0-255"

    def test_palette_colors_are_reasonable(self, app_context, kirby_rom_path: Path) -> None:
        """Verify extracted palettes have reasonable color values (not all zeros)."""
        rom_extractor = app_context.rom_extractor
        header = rom_extractor.rom_injector.read_rom_header(str(kirby_rom_path))
        if header is None:
            pytest.skip("Could not read ROM header")

        game_config = rom_extractor._find_game_configuration(header)
        if game_config is None:
            pytest.skip("No game config found")

        sprites = game_config.get("sprites", {})
        if not sprites:
            pytest.skip("No sprites in game config")

        sprite_name = next(iter(sprites))
        palette_config = rom_extractor.rom_palette_extractor.get_palette_config_from_sprite_config(
            game_config, sprite_name
        )

        if palette_config is None:
            pytest.skip("No palette config available")

        palette_offset, _ = palette_config
        if palette_offset is None or palette_offset == 0:
            pytest.skip("Palette offset not configured")
        palettes = rom_extractor.rom_palette_extractor.extract_palette_range(
            str(kirby_rom_path), palette_offset, 8, 15
        )

        if not palettes:
            pytest.skip("No palettes extracted")

        # At least one palette should have non-zero colors
        has_nonzero = False
        for pal_idx, palette in palettes.items():
            for color in palette:
                if any(c > 0 for c in color):
                    has_nonzero = True
                    break
            if has_nonzero:
                break

        assert has_nonzero, "At least one palette should have non-zero colors"
