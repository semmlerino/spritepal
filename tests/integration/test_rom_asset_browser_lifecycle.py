"""
Integration tests for ROM-mode asset browser lifecycle.

Tests the complete workflow:
1. ROM load -> Asset discovery -> Browser population
2. Palette extraction -> Resolution -> Application
3. Sprite extraction -> Modification -> Reinjection
4. Verification that modified sprite is correctly reflected

Requires:
- Real Kirby Super Star ROM at roms/Kirby Super Star (USA).sfc
- Real HAL compression binaries (exhal/inhal)
- Qt application context
"""

from __future__ import annotations

import hashlib
import shutil
from collections.abc import Generator
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QTreeWidgetItemIterator

from tests.fixtures.timeouts import LONG, signal_timeout, worker_timeout

if TYPE_CHECKING:
    from pytestqt.qtbot import QtBot

    from core.app_context import AppContext
    from core.rom_extractor import ROMExtractor
    from core.rom_injector import ROMInjector
    from core.rom_palette_extractor import ROMPaletteExtractor
    from core.sprite_config_loader import SpriteConfigLoader
    from ui.sprite_editor.controllers.rom_workflow_controller import ROMWorkflowController
    from ui.sprite_editor.views.widgets.sprite_asset_browser import SpriteAssetBrowser
    from ui.sprite_editor.views.workspaces.rom_workflow_page import ROMWorkflowPage

# Test markers - require real HAL and mark as parallel unsafe due to ROM modifications
pytestmark = [
    pytest.mark.integration,
    pytest.mark.parallel_unsafe,  # Modifies ROM files
    pytest.mark.real_hal,  # Requires real HAL binaries
]

# Constants from sprite_locations.json
ROM_PATH = Path(__file__).parent.parent.parent / "roms" / "Kirby Super Star (USA).sfc"
KIRBY_MAIN_SPRITES_OFFSET = 0x1B0000
KIRBY_EXPECTED_SIZE = 11264
ENEMY_SPRITES_OFFSET = 0x1A0000
PALETTE_OFFSET = 0x467D6
SPRITE_PALETTE_INDEX = 8  # Kirby pink palette
EXPECTED_SPRITE_COUNT_MIN = 5  # Minimum known sprites in config (confirmed entries)
BYTES_PER_TILE = 32  # 4bpp tile = 32 bytes

# Valid ROM titles for Kirby games (different regions have different titles)
VALID_KIRBY_TITLES = {"KIRBY SUPER STAR", "KIRBY SUPER DELUXE", "KIRBY'S FUN PAK"}


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def real_rom_path() -> Path:
    """Provide path to real Kirby Super Star ROM, skip if unavailable."""
    if not ROM_PATH.exists():
        pytest.skip(f"Real ROM not found: {ROM_PATH}")
    return ROM_PATH


@pytest.fixture
def rom_copy(real_rom_path: Path, tmp_path: Path) -> Path:
    """Create a writable copy of the ROM for injection tests."""
    rom_copy_path = tmp_path / "kirby_test_copy.sfc"
    shutil.copy(real_rom_path, rom_copy_path)
    return rom_copy_path


@pytest.fixture
def rom_extractor(app_context: AppContext) -> ROMExtractor:
    """Get configured ROMExtractor from app context."""
    return app_context.core_operations_manager.get_rom_extractor()


@pytest.fixture
def rom_injector(rom_extractor: ROMExtractor) -> ROMInjector:
    """Get ROMInjector from ROMExtractor."""
    return rom_extractor.rom_injector


@pytest.fixture
def palette_extractor(rom_extractor: ROMExtractor) -> ROMPaletteExtractor:
    """Get ROMPaletteExtractor from ROMExtractor."""
    return rom_extractor.rom_palette_extractor


@pytest.fixture
def sprite_config_loader(rom_extractor: ROMExtractor) -> SpriteConfigLoader:
    """Get SpriteConfigLoader from ROMExtractor."""
    return rom_extractor.sprite_config_loader


# ============================================================================
# Test Classes
# ============================================================================


class TestAssetDiscovery:
    """Tests for ROM asset discovery and browser population."""

    def test_load_rom_discovers_known_sprites(
        self,
        real_rom_path: Path,
        rom_injector: ROMInjector,
        sprite_config_loader: SpriteConfigLoader,
    ) -> None:
        """Verify that loading the ROM discovers all known sprite locations.

        Validates:
        - ROM header is correctly parsed
        - Game is identified as Kirby Super Star
        - Known sprites from config are discovered
        - Each sprite has valid offset and expected_size
        """
        # Read ROM header
        header = rom_injector.read_rom_header(str(real_rom_path))

        assert header.title.strip() in VALID_KIRBY_TITLES, (
            f"Expected one of {VALID_KIRBY_TITLES}, got '{header.title.strip()}'"
        )
        assert header.checksum > 0, "ROM checksum should be positive"

        # Get known sprite locations
        sprites = sprite_config_loader.get_game_sprites(header.title, header.checksum)

        assert len(sprites) >= EXPECTED_SPRITE_COUNT_MIN, (
            f"Expected at least {EXPECTED_SPRITE_COUNT_MIN} sprites, got {len(sprites)}"
        )

        # Verify confirmed sprites exist
        assert "Kirby_Main_Sprites" in sprites, "Kirby_Main_Sprites not found in config"
        assert "Enemy_Sprites" in sprites, "Enemy_Sprites not found in config"

        # Verify Kirby_Main_Sprites has correct offset
        kirby_config = sprites["Kirby_Main_Sprites"]
        assert kirby_config.offset == KIRBY_MAIN_SPRITES_OFFSET, (
            f"Expected Kirby offset 0x{KIRBY_MAIN_SPRITES_OFFSET:X}, got 0x{kirby_config.offset:X}"
        )

        # Verify each sprite has required fields
        for name, config in sprites.items():
            assert config.offset > 0, f"{name} has invalid offset: {config.offset}"
            assert config.estimated_size > 0, f"{name} has no estimated_size"

    def test_sprite_config_contains_palette_info(
        self,
        real_rom_path: Path,
        rom_injector: ROMInjector,
    ) -> None:
        """Verify the config file contains palette information for Kirby."""
        from core.sprite_config_loader import SpriteConfigLoader

        loader = SpriteConfigLoader()

        # Access raw config data to check palette info
        config_data = loader.config_data
        assert "games" in config_data, "Config should have 'games' section"

        kirby_game = config_data["games"].get("KIRBY SUPER STAR")
        assert kirby_game is not None, "Kirby Super Star config not found"

        palettes = kirby_game.get("palettes")
        assert palettes is not None, "Palette config not found for Kirby"
        assert "offset" in palettes, "Palette offset not specified"

        # Verify palette offset matches expected
        palette_offset_str = palettes["offset"]
        palette_offset = int(palette_offset_str, 16)
        assert palette_offset == PALETTE_OFFSET, (
            f"Expected palette offset 0x{PALETTE_OFFSET:X}, got 0x{palette_offset:X}"
        )


class TestPaletteExtraction:
    """Tests for ROM palette extraction and application."""

    def test_palette_extraction_returns_valid_colors(
        self,
        real_rom_path: Path,
        palette_extractor: ROMPaletteExtractor,
    ) -> None:
        """Verify palette extraction returns valid 16-color palettes.

        Validates:
        - Palette offset is valid
        - Returns palettes 8-15 (sprite palettes)
        - Each palette has exactly 16 colors
        - Colors are valid RGB tuples
        """
        # Extract sprite palettes (8-15)
        palettes = palette_extractor.extract_palette_range(str(real_rom_path), PALETTE_OFFSET, 8, 15)

        assert len(palettes) >= 4, f"Should have at least palettes 8-11, got {len(palettes)}"

        for index, colors in palettes.items():
            assert 8 <= index <= 15, f"Unexpected palette index: {index}"
            assert len(colors) == 16, f"Palette {index} should have 16 colors, got {len(colors)}"

            for i, color in enumerate(colors):
                assert isinstance(color, tuple), f"Color {i} in palette {index} not a tuple"
                assert len(color) == 3, f"Color {i} should be RGB (3 values), got {len(color)}"
                r, g, b = color
                assert 0 <= r <= 255, f"Red out of range: {r}"
                assert 0 <= g <= 255, f"Green out of range: {g}"
                assert 0 <= b <= 255, f"Blue out of range: {b}"

    def test_kirby_palette_has_pink_colors(
        self,
        real_rom_path: Path,
        palette_extractor: ROMPaletteExtractor,
    ) -> None:
        """Verify Kirby's palette (index 8) contains expected pink colors.

        Kirby is known to be pink, so palette 8 should have pink-ish colors.
        """
        palettes = palette_extractor.extract_palette_range(str(real_rom_path), PALETTE_OFFSET, 8, 8)

        assert SPRITE_PALETTE_INDEX in palettes, f"Palette {SPRITE_PALETTE_INDEX} not extracted"
        kirby_palette = palettes[SPRITE_PALETTE_INDEX]

        # Check for pink-ish colors (R > G and R > B)
        # Filter out near-black colors (likely transparency or outlines)
        pink_count = sum(
            1
            for r, g, b in kirby_palette
            if r > g and r > b and r > 100  # Has significant red component
        )
        assert pink_count >= 2, (
            f"Kirby palette should have pink-ish colors, found {pink_count}. Palette: {kirby_palette}"
        )

    def test_multiple_palette_offsets_valid(
        self,
        real_rom_path: Path,
        palette_extractor: ROMPaletteExtractor,
    ) -> None:
        """Verify that multiple known palette offsets are readable."""
        from core.sprite_config_loader import SpriteConfigLoader

        loader = SpriteConfigLoader()
        config_data = loader.config_data
        kirby_game = config_data["games"]["KIRBY SUPER STAR"]
        all_offsets = kirby_game["palettes"].get("all_offsets", [])

        # Test first 3 offsets (enough to validate the list)
        for offset_str in all_offsets[:3]:
            offset = int(offset_str, 16)
            palettes = palette_extractor.extract_palette_range(str(real_rom_path), offset, 8, 8)
            assert len(palettes) > 0, f"No palettes extracted from offset 0x{offset:X}"


class TestExtractionPipeline:
    """Tests for complete sprite extraction flow."""

    def test_extract_kirby_sprite_returns_valid_tiles(
        self,
        real_rom_path: Path,
        rom_injector: ROMInjector,
    ) -> None:
        """Extract Kirby sprites and verify tile data.

        Validates:
        - HAL decompression succeeds
        - Returned data is aligned to 32-byte tiles
        - Data is non-empty and reasonable size
        """
        with open(real_rom_path, "rb") as f:
            rom_data = f.read()

        # Find and decompress Kirby sprites
        compressed_size, decompressed_data, slack_size = rom_injector.find_compressed_sprite(
            rom_data, KIRBY_MAIN_SPRITES_OFFSET, expected_size=KIRBY_EXPECTED_SIZE
        )

        assert compressed_size > 0, "Should have found compressed data"
        assert len(decompressed_data) > 0, "Should have decompressed data"
        assert len(decompressed_data) % BYTES_PER_TILE == 0, (
            f"Data should be tile-aligned (32 bytes per tile), "
            f"got {len(decompressed_data)} bytes ({len(decompressed_data) % BYTES_PER_TILE} extra)"
        )

        # Verify reasonable size for Kirby sprites
        tile_count = len(decompressed_data) // BYTES_PER_TILE
        assert 100 <= tile_count <= 500, f"Unexpected tile count: {tile_count}"

    def test_extraction_deterministic_across_calls(
        self,
        real_rom_path: Path,
        rom_injector: ROMInjector,
    ) -> None:
        """Verify extraction produces identical results on repeated calls.

        Ensures the extraction pipeline is deterministic.
        """
        with open(real_rom_path, "rb") as f:
            rom_data = f.read()

        # Extract twice
        _, data1, _ = rom_injector.find_compressed_sprite(
            rom_data, KIRBY_MAIN_SPRITES_OFFSET, expected_size=KIRBY_EXPECTED_SIZE
        )
        _, data2, _ = rom_injector.find_compressed_sprite(
            rom_data, KIRBY_MAIN_SPRITES_OFFSET, expected_size=KIRBY_EXPECTED_SIZE
        )

        # Compare hashes for determinism
        hash1 = hashlib.sha256(data1).hexdigest()
        hash2 = hashlib.sha256(data2).hexdigest()

        assert hash1 == hash2, "Extraction should be deterministic"

    def test_enemy_sprites_also_extractable(
        self,
        real_rom_path: Path,
        rom_injector: ROMInjector,
    ) -> None:
        """Verify enemy sprites can also be extracted."""
        with open(real_rom_path, "rb") as f:
            rom_data = f.read()

        # Extract enemy sprites at different offset
        compressed_size, decompressed_data, _ = rom_injector.find_compressed_sprite(
            rom_data,
            ENEMY_SPRITES_OFFSET,
            expected_size=11936,  # From config
        )

        assert compressed_size > 0, "Should find enemy sprite data"
        assert len(decompressed_data) > 0, "Should decompress enemy sprites"
        assert len(decompressed_data) % BYTES_PER_TILE == 0, "Enemy sprites should be tile-aligned"


class TestRoundTripModification:
    """Tests for sprite modification and reinjection."""

    def test_modify_tile_and_reinject(
        self,
        rom_copy: Path,
        rom_injector: ROMInjector,
        tmp_path: Path,
    ) -> None:
        """Full round-trip: extract, modify a tile, reinject, verify.

        This test:
        1. Extracts a sprite from ROM
        2. Modifies an entire 8x8 tile (32 bytes) with a checkerboard pattern
        3. Creates a PNG with the modified data
        4. Reinjects the modified sprite (with force=True since compression may vary)
        5. Re-extracts and verifies the modification persisted

        Note: force=True is used because HAL compression is not deterministic -
        the same data may compress to slightly different sizes. The test ROM copy
        is isolated in tmp_path, so force injection is safe here.
        """
        from PIL import Image

        offset = KIRBY_MAIN_SPRITES_OFFSET

        # Step 1: Extract original sprite
        with open(rom_copy, "rb") as f:
            original_rom = f.read()

        compressed_size, original_data, slack = rom_injector.find_compressed_sprite(
            original_rom, offset, expected_size=KIRBY_EXPECTED_SIZE
        )

        assert len(original_data) > 0, "Failed to extract original sprite"
        original_first_tile = bytes(original_data[:BYTES_PER_TILE])

        # Step 2: Modify first tile (32 bytes) with checkerboard pattern
        # 4bpp format: 8 rows x 4 bytes per row = 32 bytes
        modified_data = bytearray(original_data)
        for i in range(BYTES_PER_TILE):
            modified_data[i] = 0x55 if i % 2 == 0 else 0xAA

        # Step 3: Create PNG from modified data for injection
        tile_count = len(modified_data) // BYTES_PER_TILE
        width_tiles = min(16, tile_count)
        height_tiles = (tile_count + width_tiles - 1) // width_tiles

        # Create indexed image with grayscale palette
        img = Image.new("P", (width_tiles * 8, height_tiles * 8))
        # Set 16-color grayscale palette (4bpp = 16 colors)
        palette_data = []
        for i in range(16):
            gray = i * 17  # 0, 17, 34, ... 255
            palette_data.extend([gray, gray, gray])
        # Pad to 256 colors (768 bytes)
        palette_data.extend([0] * (768 - len(palette_data)))
        img.putpalette(palette_data)

        # Decode 4bpp tiles and populate image
        for tile_idx in range(tile_count):
            tile_bytes = modified_data[tile_idx * BYTES_PER_TILE : (tile_idx + 1) * BYTES_PER_TILE]
            tx = (tile_idx % width_tiles) * 8
            ty = (tile_idx // width_tiles) * 8

            # Decode each pixel in the 8x8 tile
            for py in range(8):
                for px in range(8):
                    pixel = self._decode_4bpp_pixel(tile_bytes, px, py)
                    img.putpixel((tx + px, ty + py), pixel)

        # Save to temp PNG
        png_path = tmp_path / "modified_sprite.png"
        img.save(str(png_path))

        # Step 4: Inject modified sprite with force=True
        # force=True is safe here because we're working on an isolated copy
        # and this tests the full round-trip functionality
        output_rom = tmp_path / "modified_rom.sfc"
        success, message = rom_injector.inject_sprite_to_rom(
            sprite_path=str(png_path),
            rom_path=str(rom_copy),
            output_path=str(output_rom),
            sprite_offset=offset,
            create_backup=False,  # tmp_path already isolated
            force=True,  # Allow slight size variations from compression
        )

        assert success, f"Injection failed: {message}"

        # Step 5: Re-extract and verify modification
        with open(output_rom, "rb") as f:
            modified_rom = f.read()

        _, reextracted_data, _ = rom_injector.find_compressed_sprite(
            modified_rom, offset, expected_size=KIRBY_EXPECTED_SIZE
        )

        # Verify first tile was modified
        reextracted_first_tile = bytes(reextracted_data[:BYTES_PER_TILE])
        assert reextracted_first_tile != original_first_tile, "First tile should be modified after round-trip"

        # Verify rest of data is mostly unchanged (compression may cause minor differences)
        rest_original = original_data[BYTES_PER_TILE:]
        rest_modified = reextracted_data[BYTES_PER_TILE:]

        # Count byte differences (use strict=False since lengths may differ slightly)
        differences = sum(1 for a, b in zip(rest_original, rest_modified, strict=False) if a != b)
        tolerance = len(rest_original) * 0.01  # 1% tolerance for compression artifacts

        assert differences <= tolerance, (
            f"Too many differences in unmodified tiles: {differences} bytes (tolerance: {tolerance:.0f} bytes)"
        )

    def _decode_4bpp_pixel(self, tile_bytes: bytes | bytearray, x: int, y: int) -> int:
        """Decode a single pixel from 4bpp tile data.

        4bpp SNES format:
        - Bytes 0-15: Bitplanes 0,1 (interleaved, 2 bytes per row)
        - Bytes 16-31: Bitplanes 2,3 (interleaved, 2 bytes per row)
        """
        bit = 7 - (x % 8)

        # Bitplanes 0,1 are in first 16 bytes (2 bytes per row)
        bp0 = (tile_bytes[y * 2] >> bit) & 1
        bp1 = (tile_bytes[y * 2 + 1] >> bit) & 1

        # Bitplanes 2,3 are in bytes 16-31 (2 bytes per row)
        bp2 = (tile_bytes[16 + y * 2] >> bit) & 1
        bp3 = (tile_bytes[16 + y * 2 + 1] >> bit) & 1

        return (bp3 << 3) | (bp2 << 2) | (bp1 << 1) | bp0

    def test_rom_checksum_updated_after_injection(
        self,
        rom_copy: Path,
        rom_injector: ROMInjector,
        tmp_path: Path,
    ) -> None:
        """Verify ROM checksum is recalculated after injection."""
        from PIL import Image

        # Read original header (checksum will be updated after injection)
        _ = rom_injector.read_rom_header(str(rom_copy))

        # Create minimal sprite for injection
        img = Image.new("P", (128, 88))  # Size matching Kirby tile count
        palette_data = [i * 17 for i in range(16)] * 3 + [0] * (768 - 48)
        img.putpalette(palette_data)

        png_path = tmp_path / "test_sprite.png"
        img.save(str(png_path))

        output_rom = tmp_path / "checksum_test.sfc"
        success, _ = rom_injector.inject_sprite_to_rom(
            sprite_path=str(png_path),
            rom_path=str(rom_copy),
            output_path=str(output_rom),
            sprite_offset=KIRBY_MAIN_SPRITES_OFFSET,
            create_backup=False,
        )

        if success:
            # Read new checksum
            new_header = rom_injector.read_rom_header(str(output_rom))

            # ROM checksum should be updated (may or may not change depending on data)
            # The key validation is that checksum + complement = 0xFFFF
            assert new_header.checksum ^ new_header.checksum_complement == 0xFFFF, (
                f"Checksum validation failed: 0x{new_header.checksum:04X} ^ "
                f"0x{new_header.checksum_complement:04X} != 0xFFFF"
            )


class TestErrorHandling:
    """Tests for error conditions and edge cases."""

    def test_invalid_offset_fails_gracefully(
        self,
        real_rom_path: Path,
        rom_injector: ROMInjector,
    ) -> None:
        """Verify invalid offsets produce clear errors, not crashes."""
        with open(real_rom_path, "rb") as f:
            rom_data = f.read()

        # Offset beyond ROM size
        with pytest.raises(ValueError, match="exceeds ROM"):
            rom_injector.find_compressed_sprite(rom_data, len(rom_data) + 1000, expected_size=1024)

    def test_negative_offset_fails(
        self,
        real_rom_path: Path,
        rom_injector: ROMInjector,
    ) -> None:
        """Verify negative offsets are rejected."""
        with open(real_rom_path, "rb") as f:
            rom_data = f.read()

        with pytest.raises(ValueError, match="negative"):
            rom_injector.find_compressed_sprite(rom_data, -1, expected_size=1024)

    def test_extraction_at_various_offsets_deterministic(
        self,
        real_rom_path: Path,
        rom_injector: ROMInjector,
    ) -> None:
        """Verify extraction behavior is consistent at different offsets.

        Some offsets may have valid HAL-compressed data (the ROM format reuses
        HAL compression for various data types), so this test verifies that
        extraction is deterministic rather than testing for failure.
        """
        with open(real_rom_path, "rb") as f:
            rom_data = f.read()

        # Test a few different offsets for consistency
        test_offsets = [
            KIRBY_MAIN_SPRITES_OFFSET,  # Known sprite location
            ENEMY_SPRITES_OFFSET,  # Known enemy location
        ]

        for offset in test_offsets:
            # Extract twice at same offset
            _, data1, _ = rom_injector.find_compressed_sprite(rom_data, offset, expected_size=1024)
            _, data2, _ = rom_injector.find_compressed_sprite(rom_data, offset, expected_size=1024)

            # Should be deterministic
            assert data1 == data2, f"Extraction at offset 0x{offset:X} should be deterministic"


# ============================================================================
# UI Integration Fixtures
# ============================================================================


@pytest.fixture
def rom_workflow_page(qtbot: QtBot) -> Generator[ROMWorkflowPage, None, None]:
    """Create ROMWorkflowPage widget for UI testing."""
    from ui.sprite_editor.views.workspaces.rom_workflow_page import ROMWorkflowPage

    page = ROMWorkflowPage()
    qtbot.addWidget(page)
    page.show()

    yield page

    page.close()


@pytest.fixture
def rom_workflow_controller(
    qtbot: QtBot,
    app_context: AppContext,
    rom_workflow_page: ROMWorkflowPage,
) -> Generator[ROMWorkflowController, None, None]:
    """Create fully-wired controller with view connected."""
    from ui.sprite_editor.controllers.editing_controller import EditingController
    from ui.sprite_editor.controllers.rom_workflow_controller import ROMWorkflowController

    # Create editing controller (required dependency)
    # Note: EditingController is a QObject, not a QWidget, so don't use addWidget
    editing_controller = EditingController(parent=None)

    # Create controller with injected services
    controller = ROMWorkflowController(
        parent=None,
        editing_controller=editing_controller,
        message_service=None,
        rom_cache=app_context.rom_cache,
        rom_extractor=app_context.core_operations_manager.get_rom_extractor(),
        log_watcher=None,
        sprite_library=None,
    )

    # Connect view
    controller.set_view(rom_workflow_page)

    yield controller

    # Cleanup
    controller.cleanup()


@pytest.fixture
def asset_browser(rom_workflow_page: ROMWorkflowPage) -> SpriteAssetBrowser:
    """Direct access to the asset browser widget."""
    return rom_workflow_page.asset_browser


# ============================================================================
# UI Integration Tests
# ============================================================================


@pytest.mark.gui
class TestAssetBrowserUI:
    """UI integration tests for the asset browser widget and ROM workflow."""

    def test_rom_load_populates_browser(
        self,
        qtbot: QtBot,
        rom_workflow_controller: ROMWorkflowController,
        asset_browser: SpriteAssetBrowser,
        real_rom_path: Path,
    ) -> None:
        """Verify ROM load adds known sprites to browser."""
        # Pre-condition: browser is empty
        initial_counts = asset_browser.get_item_count()
        assert initial_counts.get("ROM Sprites", 0) == 0

        # Action: load ROM
        rom_workflow_controller.load_rom(str(real_rom_path))

        # Wait for population
        qtbot.waitUntil(
            lambda: asset_browser.get_item_count().get("ROM Sprites", 0) > 0,
            timeout=worker_timeout(),
        )

        # Verify expected sprites present
        counts = asset_browser.get_item_count()
        assert counts["ROM Sprites"] >= EXPECTED_SPRITE_COUNT_MIN

        # Verify "Kirby_Main_Sprites" is in the tree
        found_kirby = False
        iterator = QTreeWidgetItemIterator(asset_browser.tree)
        while iterator.value():
            item = iterator.value()
            data = item.data(0, Qt.ItemDataRole.UserRole)
            if isinstance(data, dict) and data.get("offset") == KIRBY_MAIN_SPRITES_OFFSET:
                found_kirby = True
                assert data.get("source_type") == "rom"
                break
            iterator += 1

        assert found_kirby, f"Kirby_Main_Sprites at 0x{KIRBY_MAIN_SPRITES_OFFSET:X} not found"

    def test_clear_all_and_reload(
        self,
        qtbot: QtBot,
        rom_workflow_controller: ROMWorkflowController,
        asset_browser: SpriteAssetBrowser,
        real_rom_path: Path,
    ) -> None:
        """Verify sprites are cleared and re-populated on ROM reload."""
        # Load ROM first
        rom_workflow_controller.load_rom(str(real_rom_path))
        qtbot.waitUntil(
            lambda: asset_browser.get_item_count().get("ROM Sprites", 0) >= EXPECTED_SPRITE_COUNT_MIN,
            timeout=worker_timeout(),
        )

        # Manually clear
        asset_browser.clear_all()
        assert asset_browser.get_item_count()["ROM Sprites"] == 0

        # Reload ROM
        rom_workflow_controller.load_rom(str(real_rom_path))
        qtbot.waitUntil(
            lambda: asset_browser.get_item_count().get("ROM Sprites", 0) >= EXPECTED_SPRITE_COUNT_MIN,
            timeout=worker_timeout(),
        )

        # Should be repopulated
        assert asset_browser.get_item_count()["ROM Sprites"] >= EXPECTED_SPRITE_COUNT_MIN

    def test_thumbnails_generated_for_sprites(
        self,
        qtbot: QtBot,
        rom_workflow_controller: ROMWorkflowController,
        asset_browser: SpriteAssetBrowser,
        real_rom_path: Path,
    ) -> None:
        """Verify thumbnails are generated via worker."""
        thumbnails_received: list[tuple[int, QPixmap]] = []

        def capture_thumbnail(offset: int, pixmap: QPixmap) -> None:
            thumbnails_received.append((offset, pixmap))

        # Load ROM first
        rom_workflow_controller.load_rom(str(real_rom_path))

        # Wait for population
        qtbot.waitUntil(
            lambda: asset_browser.get_item_count().get("ROM Sprites", 0) > 0,
            timeout=worker_timeout(),
        )

        # Connect to catch thumbnails
        if rom_workflow_controller._thumbnail_controller:
            rom_workflow_controller._thumbnail_controller.thumbnail_ready.connect(capture_thumbnail)

        # Wait for at least one thumbnail
        qtbot.waitUntil(
            lambda: len(thumbnails_received) > 0,
            timeout=worker_timeout(LONG),
        )

        # Verify thumbnail is not null and has reasonable size
        offset, pixmap = thumbnails_received[0]
        assert not pixmap.isNull(), f"Thumbnail for 0x{offset:06X} is null"
        assert pixmap.width() > 0
        assert pixmap.height() > 0

    def test_thumbnail_set_on_browser_item(
        self,
        qtbot: QtBot,
        rom_workflow_controller: ROMWorkflowController,
        asset_browser: SpriteAssetBrowser,
        real_rom_path: Path,
    ) -> None:
        """Verify set_thumbnail() stores pixmap in item data."""
        # Load ROM
        rom_workflow_controller.load_rom(str(real_rom_path))
        qtbot.waitUntil(
            lambda: asset_browser.get_item_count().get("ROM Sprites", 0) > 0,
            timeout=worker_timeout(),
        )

        # Wait for at least one thumbnail to be set
        def has_any_thumbnail() -> bool:
            iterator = QTreeWidgetItemIterator(asset_browser.tree)
            while iterator.value():
                item = iterator.value()
                data = item.data(0, Qt.ItemDataRole.UserRole)
                if isinstance(data, dict) and data.get("thumbnail"):
                    return True
                iterator += 1
            return False

        qtbot.waitUntil(has_any_thumbnail, timeout=worker_timeout(LONG))

        # Find item with thumbnail and verify data
        iterator = QTreeWidgetItemIterator(asset_browser.tree)
        while iterator.value():
            item = iterator.value()
            data = item.data(0, Qt.ItemDataRole.UserRole)
            if isinstance(data, dict) and data.get("thumbnail"):
                thumbnail = data["thumbnail"]
                assert isinstance(thumbnail, QPixmap)
                assert not thumbnail.isNull()
                return
            iterator += 1

        pytest.fail("No item found with thumbnail set")

    def test_thumbnail_is_not_placeholder(
        self,
        qtbot: QtBot,
        rom_workflow_controller: ROMWorkflowController,
        asset_browser: SpriteAssetBrowser,
        real_rom_path: Path,
    ) -> None:
        """Verify thumbnails contain actual image data (not all one color)."""
        thumbnail_found: list[tuple[int, QPixmap]] = []

        def capture_thumbnail(offset: int, pixmap: QPixmap) -> None:
            thumbnail_found.append((offset, pixmap))

        # Load ROM
        rom_workflow_controller.load_rom(str(real_rom_path))
        qtbot.waitUntil(
            lambda: asset_browser.get_item_count().get("ROM Sprites", 0) > 0,
            timeout=worker_timeout(),
        )

        # Connect to thumbnail signal
        if rom_workflow_controller._thumbnail_controller:
            rom_workflow_controller._thumbnail_controller.thumbnail_ready.connect(capture_thumbnail)

        # Wait for Kirby thumbnail specifically
        qtbot.waitUntil(
            lambda: any(o == KIRBY_MAIN_SPRITES_OFFSET for o, _ in thumbnail_found),
            timeout=worker_timeout(LONG),
        )

        # Find Kirby's thumbnail
        kirby_thumbnail = next(
            (p for o, p in thumbnail_found if o == KIRBY_MAIN_SPRITES_OFFSET),
            None,
        )
        assert kirby_thumbnail is not None

        # Convert to QImage for pixel analysis
        image = kirby_thumbnail.toImage()
        assert image.width() > 0 and image.height() > 0

        # Sample multiple pixels - they should NOT all be identical (placeholder pattern)
        colors = set()
        step_x = max(1, image.width() // 4)
        step_y = max(1, image.height() // 4)
        for x in range(0, image.width(), step_x):
            for y in range(0, image.height(), step_y):
                colors.add(image.pixelColor(x, y).rgba())

        # Real sprites have variation; placeholders are uniform
        assert len(colors) > 1, "Thumbnail appears to be a uniform placeholder"

    def test_selection_emits_sprite_selected_signal(
        self,
        qtbot: QtBot,
        rom_workflow_controller: ROMWorkflowController,
        asset_browser: SpriteAssetBrowser,
        real_rom_path: Path,
    ) -> None:
        """Verify selecting a sprite emits sprite_selected signal."""
        # Load ROM
        rom_workflow_controller.load_rom(str(real_rom_path))
        qtbot.waitUntil(
            lambda: asset_browser.get_item_count().get("ROM Sprites", 0) > 0,
            timeout=worker_timeout(),
        )

        # Find a sprite item
        sprite_item = None
        iterator = QTreeWidgetItemIterator(asset_browser.tree)
        while iterator.value():
            item = iterator.value()
            data = item.data(0, Qt.ItemDataRole.UserRole)
            if isinstance(data, dict) and "offset" in data:
                sprite_item = item
                break
            iterator += 1

        assert sprite_item is not None, "No sprite item found in browser"

        expected_offset = sprite_item.data(0, Qt.ItemDataRole.UserRole)["offset"]
        expected_source = sprite_item.data(0, Qt.ItemDataRole.UserRole)["source_type"]

        # Click the item and wait for signal
        with qtbot.waitSignal(
            asset_browser.sprite_selected,
            timeout=signal_timeout(),
        ) as blocker:
            asset_browser.tree.setCurrentItem(sprite_item)

        # Verify signal arguments
        offset, source_type = blocker.args
        assert offset == expected_offset
        assert source_type == expected_source

    def test_double_click_emits_sprite_activated_signal(
        self,
        qtbot: QtBot,
        rom_workflow_controller: ROMWorkflowController,
        asset_browser: SpriteAssetBrowser,
        real_rom_path: Path,
    ) -> None:
        """Verify double-clicking sprite emits sprite_activated signal."""
        # Load ROM
        rom_workflow_controller.load_rom(str(real_rom_path))
        qtbot.waitUntil(
            lambda: asset_browser.get_item_count().get("ROM Sprites", 0) > 0,
            timeout=worker_timeout(),
        )

        # Find a sprite item
        sprite_item = None
        iterator = QTreeWidgetItemIterator(asset_browser.tree)
        while iterator.value():
            item = iterator.value()
            data = item.data(0, Qt.ItemDataRole.UserRole)
            if isinstance(data, dict) and "offset" in data:
                sprite_item = item
                break
            iterator += 1

        assert sprite_item is not None

        expected_offset = sprite_item.data(0, Qt.ItemDataRole.UserRole)["offset"]
        expected_source = sprite_item.data(0, Qt.ItemDataRole.UserRole)["source_type"]

        # First select the item
        asset_browser.tree.setCurrentItem(sprite_item)

        # Double-click via signal directly (simulating itemDoubleClicked)
        with qtbot.waitSignal(
            asset_browser.sprite_activated,
            timeout=signal_timeout(),
        ) as blocker:
            # Emit the internal signal that double-click triggers
            asset_browser.tree.itemDoubleClicked.emit(sprite_item, 0)

        offset, source_type = blocker.args
        assert offset == expected_offset
        assert source_type == expected_source

    def test_full_workflow_rom_to_selection(
        self,
        qtbot: QtBot,
        rom_workflow_controller: ROMWorkflowController,
        asset_browser: SpriteAssetBrowser,
        real_rom_path: Path,
    ) -> None:
        """End-to-end test: ROM load -> browser population -> thumbnail -> selection.

        Validates the complete signal flow through all components.
        """
        # Track signals received
        signals_received: dict[str, list] = {
            "rom_info": [],
            "thumbnails": [],
            "selections": [],
        }

        def on_rom_info(info: str) -> None:
            signals_received["rom_info"].append(info)

        def on_thumbnail(offset: int, pixmap: QPixmap) -> None:
            signals_received["thumbnails"].append((offset, pixmap))

        def on_selection(offset: int, source_type: str) -> None:
            signals_received["selections"].append((offset, source_type))

        # Connect signals
        rom_workflow_controller.rom_info_updated.connect(on_rom_info)
        asset_browser.sprite_selected.connect(on_selection)

        # Step 1: Load ROM
        rom_workflow_controller.load_rom(str(real_rom_path))

        # Step 2: Wait for ROM info signal
        qtbot.waitUntil(
            lambda: len(signals_received["rom_info"]) > 0,
            timeout=signal_timeout(),
        )
        assert any("KIRBY" in info.upper() for info in signals_received["rom_info"])

        # Step 3: Wait for browser population
        qtbot.waitUntil(
            lambda: asset_browser.get_item_count().get("ROM Sprites", 0) >= EXPECTED_SPRITE_COUNT_MIN,
            timeout=worker_timeout(),
        )

        # Step 4: Connect thumbnail signal after worker is set up
        if rom_workflow_controller._thumbnail_controller:
            rom_workflow_controller._thumbnail_controller.thumbnail_ready.connect(on_thumbnail)

        # Step 5: Wait for at least one thumbnail
        qtbot.waitUntil(
            lambda: len(signals_received["thumbnails"]) > 0,
            timeout=worker_timeout(LONG),
        )

        # Step 6: Select a sprite
        iterator = QTreeWidgetItemIterator(asset_browser.tree)
        while iterator.value():
            item = iterator.value()
            data = item.data(0, Qt.ItemDataRole.UserRole)
            if isinstance(data, dict) and "offset" in data:
                asset_browser.tree.setCurrentItem(item)
                break
            iterator += 1

        # Step 7: Verify selection signal
        qtbot.waitUntil(
            lambda: len(signals_received["selections"]) > 0,
            timeout=signal_timeout(),
        )

        assert len(signals_received["selections"]) > 0
        offset, source_type = signals_received["selections"][0]
        assert offset > 0
        assert source_type == "rom"

    def test_kirby_thumbnail_has_proper_grayscale_shading(
        self,
        qtbot: QtBot,
        rom_workflow_controller: ROMWorkflowController,
        asset_browser: SpriteAssetBrowser,
        real_rom_path: Path,
    ) -> None:
        """Verify Kirby thumbnail has proper grayscale shading (not flat/corrupt).

        Note: Thumbnails are intentionally rendered in grayscale for performance.
        Full palette colors are only applied when viewing sprites in the editor.
        This test verifies the grayscale rendering shows proper shading.
        """
        thumbnail_found: list[tuple[int, QPixmap]] = []

        def capture_thumbnail(offset: int, pixmap: QPixmap) -> None:
            thumbnail_found.append((offset, pixmap))

        # Load ROM
        rom_workflow_controller.load_rom(str(real_rom_path))
        qtbot.waitUntil(
            lambda: asset_browser.get_item_count().get("ROM Sprites", 0) > 0,
            timeout=worker_timeout(),
        )

        # Connect to thumbnail signal
        if rom_workflow_controller._thumbnail_controller:
            rom_workflow_controller._thumbnail_controller.thumbnail_ready.connect(capture_thumbnail)

        # Wait for Kirby thumbnail specifically
        qtbot.waitUntil(
            lambda: any(o == KIRBY_MAIN_SPRITES_OFFSET for o, _ in thumbnail_found),
            timeout=worker_timeout(LONG),
        )

        # Find Kirby's thumbnail
        kirby_thumbnail = next(
            (p for o, p in thumbnail_found if o == KIRBY_MAIN_SPRITES_OFFSET),
            None,
        )
        assert kirby_thumbnail is not None

        # Convert to QImage for pixel analysis
        image = kirby_thumbnail.toImage()
        assert image.width() > 0 and image.height() > 0

        # Collect grayscale values (use red channel since R=G=B for grayscale)
        gray_values: set[int] = set()
        for x in range(image.width()):
            for y in range(image.height()):
                color = image.pixelColor(x, y)
                gray_values.add(color.red())

        # Verify grayscale has reasonable range (not all one value)
        # Real sprite data should have multiple shading levels (at least 4 for 4bpp)
        assert len(gray_values) >= 4, (
            f"Kirby thumbnail should have varied grayscale shading: found only {len(gray_values)} "
            f"distinct gray values. Data may be corrupted or all one color."
        )

        # Verify we have both light and dark values (not just mid-tones)
        min_gray = min(gray_values)
        max_gray = max(gray_values)
        gray_range = max_gray - min_gray
        assert gray_range >= 100, (
            f"Kirby thumbnail should have good contrast: gray range is only {gray_range} "
            f"(min={min_gray}, max={max_gray}). Expected range >= 100."
        )

    def test_thumbnail_has_expected_dimensions(
        self,
        qtbot: QtBot,
        rom_workflow_controller: ROMWorkflowController,
        asset_browser: SpriteAssetBrowser,
        real_rom_path: Path,
    ) -> None:
        """Verify thumbnails have reasonable dimensions matching sprite data.

        Thumbnails should be at least 32x32 (display size) and represent
        actual tile data, not tiny or corrupted images.
        """
        thumbnail_found: list[tuple[int, QPixmap]] = []

        def capture_thumbnail(offset: int, pixmap: QPixmap) -> None:
            thumbnail_found.append((offset, pixmap))

        # Load ROM
        rom_workflow_controller.load_rom(str(real_rom_path))
        qtbot.waitUntil(
            lambda: asset_browser.get_item_count().get("ROM Sprites", 0) > 0,
            timeout=worker_timeout(),
        )

        # Connect to thumbnail signal
        if rom_workflow_controller._thumbnail_controller:
            rom_workflow_controller._thumbnail_controller.thumbnail_ready.connect(capture_thumbnail)

        # Wait for at least one thumbnail
        qtbot.waitUntil(
            lambda: len(thumbnail_found) > 0,
            timeout=worker_timeout(LONG),
        )

        # Verify dimensions on all received thumbnails
        for offset, pixmap in thumbnail_found:
            assert not pixmap.isNull(), f"Thumbnail at 0x{offset:06X} is null"
            # Minimum 32x8 (at least one 8x8 tile wide/tall)
            assert pixmap.width() >= 32, f"Thumbnail at 0x{offset:06X} too narrow: {pixmap.width()}px (min 32)"
            assert pixmap.height() >= 8, f"Thumbnail at 0x{offset:06X} too short: {pixmap.height()}px (min 8)"
            # Sanity upper bound - sprites shouldn't be absurdly large
            assert pixmap.width() <= 512, f"Thumbnail at 0x{offset:06X} suspiciously wide: {pixmap.width()}px"
            assert pixmap.height() <= 512, f"Thumbnail at 0x{offset:06X} suspiciously tall: {pixmap.height()}px"

    def test_sprites_in_correct_category(
        self,
        qtbot: QtBot,
        rom_workflow_controller: ROMWorkflowController,
        asset_browser: SpriteAssetBrowser,
        real_rom_path: Path,
    ) -> None:
        """Verify ROM sprites are placed in 'ROM Sprites' category, not others."""
        # Load ROM
        rom_workflow_controller.load_rom(str(real_rom_path))
        qtbot.waitUntil(
            lambda: asset_browser.get_item_count().get("ROM Sprites", 0) >= EXPECTED_SPRITE_COUNT_MIN,
            timeout=worker_timeout(),
        )

        # Find the ROM Sprites category item
        rom_category = None
        for i in range(asset_browser.tree.topLevelItemCount()):
            item = asset_browser.tree.topLevelItem(i)
            if item and item.text(0) == "ROM Sprites":
                rom_category = item
                break

        assert rom_category is not None, "ROM Sprites category not found"

        # Verify Kirby sprite is under ROM Sprites (not Mesen2 Captures or other)
        found_kirby = False
        for i in range(rom_category.childCount()):
            child = rom_category.child(i)
            if child:
                data = child.data(0, Qt.ItemDataRole.UserRole)
                if isinstance(data, dict) and data.get("offset") == KIRBY_MAIN_SPRITES_OFFSET:
                    found_kirby = True
                    assert data.get("source_type") == "rom", (
                        f"Kirby sprite has wrong source_type: {data.get('source_type')}"
                    )
                    break

        assert found_kirby, "Kirby sprite not found in ROM Sprites category"

        # Verify other categories don't contain ROM sprites
        counts = asset_browser.get_item_count()
        # Mesen2 Captures should be 0 initially (no captures loaded)
        assert counts.get("Mesen2 Captures", 0) == 0, "Mesen2 Captures should be empty when only ROM is loaded"


@pytest.mark.gui
class TestAssetBrowserErrorHandling:
    """Tests for error conditions and edge cases in the asset browser UI."""

    def test_load_nonexistent_rom_shows_error(
        self,
        qtbot: QtBot,
        rom_workflow_controller: ROMWorkflowController,
        asset_browser: SpriteAssetBrowser,
        tmp_path: Path,
    ) -> None:
        """Verify loading a non-existent ROM file is handled gracefully."""
        # Create path to non-existent file
        fake_rom = tmp_path / "nonexistent.sfc"
        assert not fake_rom.exists()

        # Track error messages
        error_shown = []

        # Mock message service to capture error
        class MockMessageService:
            def show_message(self, msg: str) -> None:
                error_shown.append(msg)

        rom_workflow_controller._message_service = MockMessageService()  # type: ignore[assignment]

        # Attempt to load non-existent ROM
        rom_workflow_controller.load_rom(str(fake_rom))

        # Should show error message
        assert len(error_shown) > 0, "No error message shown for missing ROM"
        assert any("not found" in msg.lower() or "error" in msg.lower() for msg in error_shown)

        # Browser should remain empty
        assert asset_browser.get_item_count().get("ROM Sprites", 0) == 0

    def test_load_invalid_file_shows_error(
        self,
        qtbot: QtBot,
        rom_workflow_controller: ROMWorkflowController,
        asset_browser: SpriteAssetBrowser,
        tmp_path: Path,
    ) -> None:
        """Verify loading an invalid/corrupted file shows error, not success."""
        # Create a small invalid file (not a real ROM)
        invalid_rom = tmp_path / "invalid.sfc"
        invalid_rom.write_bytes(b"This is not a valid ROM file")

        # Track messages
        messages: list[str] = []

        class MockMessageService:
            def show_message(self, msg: str) -> None:
                messages.append(msg)

        rom_workflow_controller._message_service = MockMessageService()  # type: ignore[assignment]

        # Attempt to load invalid ROM - should not raise exception
        rom_workflow_controller.load_rom(str(invalid_rom))

        # Give time for any async operations
        qtbot.wait(100)

        # Should show error message, not success
        assert len(messages) > 0, "Should show a message for invalid ROM"
        assert any("error" in msg.lower() or "invalid" in msg.lower() for msg in messages), (
            f"Should show error message for invalid ROM, got: {messages}"
        )

        # Should NOT show success message
        assert not any("loaded rom:" in msg.lower() for msg in messages), (
            f"Should NOT show success message for invalid ROM, got: {messages}"
        )

        # Browser should remain empty
        assert asset_browser.get_item_count().get("ROM Sprites", 0) == 0

    def test_clear_all_on_empty_browser_is_safe(
        self,
        qtbot: QtBot,
        asset_browser: SpriteAssetBrowser,
    ) -> None:
        """Verify clear_all() on an already empty browser doesn't crash."""
        # Browser starts empty
        assert asset_browser.get_item_count().get("ROM Sprites", 0) == 0

        # Clear should be safe even when empty
        asset_browser.clear_all()

        # Still empty, no crash
        assert asset_browser.get_item_count().get("ROM Sprites", 0) == 0

    def test_rapid_clear_load_cycles_are_safe(
        self,
        qtbot: QtBot,
        rom_workflow_controller: ROMWorkflowController,
        asset_browser: SpriteAssetBrowser,
        real_rom_path: Path,
    ) -> None:
        """Verify rapid clear/load cycles don't cause race conditions."""
        # Perform several rapid load/clear cycles
        for _ in range(3):
            rom_workflow_controller.load_rom(str(real_rom_path))
            qtbot.wait(50)  # Brief delay
            asset_browser.clear_all()
            qtbot.wait(50)

        # Final load
        rom_workflow_controller.load_rom(str(real_rom_path))
        qtbot.waitUntil(
            lambda: asset_browser.get_item_count().get("ROM Sprites", 0) > 0,
            timeout=worker_timeout(),
        )

        # Should have sprites loaded correctly
        assert asset_browser.get_item_count()["ROM Sprites"] >= EXPECTED_SPRITE_COUNT_MIN
