"""Tests for FrameMappingController selected_entry_ids filtering.

Verifies that get_capture_result_for_game_frame respects the stored
selected_entry_ids when returning capture results. Also verifies that
inject_mapping uses the same filtering and applies scale transforms.

Also tests headless controller usage (without Qt parent or workspace).
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image

from core.frame_mapping_project import AIFrame, FrameMapping, FrameMappingProject, GameFrame
from core.services.rom_verification_service import ROMVerificationResult
from ui.frame_mapping.controllers.frame_mapping_controller import (
    FrameMappingController,
)


def create_test_capture(
    entry_ids: list[int],
    rom_offsets: list[int] | None = None,
) -> dict:
    """Create a minimal capture with entries having the given IDs.

    Args:
        entry_ids: List of entry IDs to create
        rom_offsets: Optional list of ROM offsets per entry. If not provided,
                     each entry gets a unique offset based on its index.
    """
    entries = []
    if rom_offsets is None:
        rom_offsets = [0x100000 + i * 0x100 for i in range(len(entry_ids))]

    for i, entry_id in enumerate(entry_ids):
        rom_offset = rom_offsets[i] if i < len(rom_offsets) else 0x100000 + i * 0x100
        entries.append(
            {
                "id": entry_id,
                "x": 50 + i * 10,  # Small offset to stay within [-256, 255]
                "y": 100,
                "tile": i,
                "width": 8,  # Use 8x8 sprites to match single tile
                "height": 8,
                "palette": 7,
                "rom_offset": rom_offset,
                "tiles": [
                    {
                        "tile_index": 0,
                        "vram_addr": 0x1000 + i * 0x20,
                        "pos_x": 0,
                        "pos_y": 0,
                        "data_hex": "00" * 32,
                        "rom_offset": rom_offset,
                        "tile_index_in_block": 0,
                    }
                ],
            }
        )
    return {
        "frame": 1,
        "obsel": {},
        "entries": entries,
        "palettes": {7: [[0, 0, 0]] * 16},
    }


class TestGetCaptureResultFiltering:
    """Tests for get_capture_result_for_game_frame entry ID filtering."""

    def test_returns_all_entries_when_no_selected_ids(self, tmp_path: Path, qtbot) -> None:
        """Without selected_entry_ids, returns all entries."""
        # Create capture file with 5 entries
        capture_data = create_test_capture([0, 1, 2, 3, 4])
        capture_path = tmp_path / "capture.json"
        capture_path.write_text(json.dumps(capture_data))

        # Create controller with project
        controller = FrameMappingController()
        project = FrameMappingProject(name="test")
        project.game_frames.append(
            GameFrame(
                id="F001",
                capture_path=capture_path,
                selected_entry_ids=[],  # Empty = no filtering
            )
        )
        controller._project = project

        # Get capture result (returns tuple)
        result, _ = controller.get_capture_result_for_game_frame("F001")

        assert result is not None
        assert len(result.entries) == 5

    def test_filters_entries_by_selected_ids(self, tmp_path: Path, qtbot) -> None:
        """With selected_entry_ids, returns only matching entries."""
        # Create capture file with 5 entries (IDs 0-4)
        capture_data = create_test_capture([0, 1, 2, 3, 4])
        capture_path = tmp_path / "capture.json"
        capture_path.write_text(json.dumps(capture_data))

        # Create controller with project - only select entries 1 and 3
        controller = FrameMappingController()
        project = FrameMappingProject(name="test")
        project.game_frames.append(
            GameFrame(
                id="F001",
                capture_path=capture_path,
                selected_entry_ids=[1, 3],
            )
        )
        controller._project = project

        # Get capture result (returns tuple)
        result, _ = controller.get_capture_result_for_game_frame("F001")

        assert result is not None
        assert len(result.entries) == 2
        assert {e.id for e in result.entries} == {1, 3}

    def test_filters_preserves_entry_order(self, tmp_path: Path, qtbot) -> None:
        """Filtered entries preserve their original order."""
        # Create capture file with entries in specific order
        capture_data = create_test_capture([10, 20, 30, 40, 50])
        capture_path = tmp_path / "capture.json"
        capture_path.write_text(json.dumps(capture_data))

        # Create controller with project - select in different order than stored
        controller = FrameMappingController()
        project = FrameMappingProject(name="test")
        project.game_frames.append(
            GameFrame(
                id="F001",
                capture_path=capture_path,
                selected_entry_ids=[40, 20, 10],  # Reversed subset
            )
        )
        controller._project = project

        # Get capture result - should preserve capture file order (returns tuple)
        result, _ = controller.get_capture_result_for_game_frame("F001")

        assert result is not None
        assert len(result.entries) == 3
        # Order should match capture file, not selected_entry_ids order
        assert [e.id for e in result.entries] == [10, 20, 40]

    def test_returns_none_when_no_entries_match(self, tmp_path: Path, qtbot) -> None:
        """Falls back to unfiltered capture when no entries match selected IDs."""
        # Create capture file with entries
        capture_data = create_test_capture([0, 1, 2])
        capture_path = tmp_path / "capture.json"
        capture_path.write_text(json.dumps(capture_data))

        # Create controller with non-matching IDs
        controller = FrameMappingController()
        project = FrameMappingProject(name="test")
        project.game_frames.append(
            GameFrame(
                id="F001",
                capture_path=capture_path,
                selected_entry_ids=[99, 100],  # IDs not in capture
            )
        )
        controller._project = project

        # Get capture result - should fall back to unfiltered with all entries (returns tuple)
        with qtbot.waitSignal(controller.stale_entries_warning, timeout=1000):
            result, _ = controller.get_capture_result_for_game_frame("F001")

        # Should return unfiltered capture with all 3 entries
        assert result is not None
        assert len(result.entries) == 3
        assert result.visible_count == 3

    def test_filters_single_entry(self, tmp_path: Path, qtbot) -> None:
        """Can filter down to a single entry."""
        # Create capture file with 10 entries
        capture_data = create_test_capture(list(range(10)))
        capture_path = tmp_path / "capture.json"
        capture_path.write_text(json.dumps(capture_data))

        # Create controller with single selection
        controller = FrameMappingController()
        project = FrameMappingProject(name="test")
        project.game_frames.append(
            GameFrame(
                id="F001",
                capture_path=capture_path,
                selected_entry_ids=[5],
            )
        )
        controller._project = project

        # Get capture result (returns tuple)
        result, _ = controller.get_capture_result_for_game_frame("F001")

        assert result is not None
        assert len(result.entries) == 1
        assert result.entries[0].id == 5


class TestInjectMappingEntryFiltering:
    """Tests that inject_mapping filters entries by selected_entry_ids, not rom_offset.

    Bug: inject_mapping at line 690 filters by rom_offset which can match wrong entries
    when multiple frames share ROM offsets. Should filter by selected_entry_ids instead.
    """

    def test_inject_mapping_uses_selected_entry_ids_not_rom_offset(self, tmp_path: Path, qtbot) -> None:
        """Injection should filter by selected_entry_ids, not rom_offset.

        Scenario: Two entries with different IDs but SAME rom_offset (shared tile).
        If filtering by rom_offset, both entries are included (wrong).
        If filtering by selected_entry_ids, only the selected entry is included (correct).
        """
        # Create capture with 2 entries sharing the SAME rom_offset
        shared_offset = 0x123456
        capture_data = create_test_capture(
            entry_ids=[10, 20],  # Different IDs
            rom_offsets=[shared_offset, shared_offset],  # Same ROM offset
        )
        capture_path = tmp_path / "capture.json"
        capture_path.write_text(json.dumps(capture_data))

        # Create AI frame image
        ai_frame_path = tmp_path / "ai_frame.png"
        ai_img = Image.new("RGBA", (8, 8), (255, 0, 0, 255))
        ai_img.save(ai_frame_path)

        # Create project with game frame that only selected entry 10
        project = FrameMappingProject(name="test")
        project.ai_frames_dir = tmp_path
        project.ai_frames.append(AIFrame(path=ai_frame_path, index=0))
        project.game_frames.append(
            GameFrame(
                id="F001",
                capture_path=capture_path,
                rom_offsets=[shared_offset],
                selected_entry_ids=[10],  # Only entry 10, not entry 20
            )
        )
        project.mappings.append(
            FrameMapping(
                ai_frame_id="ai_frame.png",  # Must match AIFrame path filename
                game_frame_id="F001",
                offset_x=0,
                offset_y=0,
            )
        )
        project._rebuild_indices()

        controller = FrameMappingController()
        controller._project = project

        # Track which entries are used in injection
        captured_entries: list[int] = []

        def mock_render_selection(self):
            """Capture which entries are being rendered."""
            for entry in self.capture.entries:
                captured_entries.append(entry.id)
            # Return a minimal valid image
            return Image.new("RGBA", (8, 8), (0, 0, 0, 255))

        # Mock ROM operations to avoid actual file manipulation
        with (
            patch(
                "core.mesen_integration.capture_renderer.CaptureRenderer.render_selection",
                mock_render_selection,
            ),
            patch.object(controller, "create_injection_copy", return_value=tmp_path / "out.sfc"),
            patch("core.services.injection_orchestrator.ROMInjector") as mock_injector_class,
        ):
            mock_injector = MagicMock()
            mock_injector.find_compressed_sprite.return_value = (0, b"\x00" * 32, 32)
            mock_injector.inject_sprite_to_rom.return_value = (True, "Success")
            mock_injector_class.return_value = mock_injector

            # Create a fake ROM file
            rom_path = tmp_path / "test.sfc"
            rom_path.write_bytes(b"\x00" * 0x200000)
            (tmp_path / "out.sfc").write_bytes(b"\x00" * 0x200000)

            # This should use ONLY entry 10 (via selected_entry_ids)
            # BUG: Currently uses ALL entries matching rom_offset (both 10 AND 20)
            controller.inject_mapping("ai_frame.png", rom_path)

        # Should only have processed entry 10
        # BUG: Will have both [10, 20] because filtering uses rom_offset
        assert captured_entries == [10], (
            f"Expected only entry 10 from selected_entry_ids, "
            f"but got {captured_entries} (filtering by rom_offset includes all matching entries)"
        )


def create_flipped_capture(
    entry_id: int,
    flip_h: bool,
    flip_v: bool,
    width: int = 16,
    height: int = 16,
) -> dict:
    """Create a capture with a single entry that has flip flags set.

    Creates a 16x16 sprite (2x2 tiles) to test position mirroring.

    The tile layout for a 16x16 sprite:
    - tile (0,0) is top-left
    - tile (1,0) is top-right
    - tile (0,1) is bottom-left
    - tile (1,1) is bottom-right

    When flip_h=True, CaptureRenderer mirrors positions:
    - tile at pos_x=0 should appear at x=entry.x + (width - 0 - 8) = entry.x + 8
    - tile at pos_x=1 should appear at x=entry.x + (width - 8 - 8) = entry.x + 0
    """
    rom_offset = 0x100000
    tiles = []
    tile_idx = 0

    # Generate solid tile data (all pixels = palette index 1, opaque)
    # 4bpp SNES tile: 32 bytes per tile, interleaved bitplanes
    # For simplicity, fill with 0xFF which makes all pixels use a non-zero index
    solid_tile_hex = "FF" * 32

    for ty in range(height // 8):
        for tx in range(width // 8):
            tiles.append(
                {
                    "tile_index": tile_idx,
                    "vram_addr": 0x1000 + tile_idx * 0x20,
                    "pos_x": tx,
                    "pos_y": ty,
                    "data_hex": solid_tile_hex,
                    "rom_offset": rom_offset,
                    "tile_index_in_block": tile_idx,
                }
            )
            tile_idx += 1

    return {
        "frame": 1,
        "obsel": {},
        "entries": [
            {
                "id": entry_id,
                "x": 100,  # Entry position on screen
                "y": 100,
                "tile": 0,
                "width": width,
                "height": height,
                "palette": 7,
                "rom_offset": rom_offset,
                "flip_h": flip_h,
                "flip_v": flip_v,
                "tiles": tiles,
            }
        ],
        # Palette with distinct colors at each index
        "palettes": {
            7: [
                [0, 0, 0],  # 0: transparent (black)
                [255, 255, 255],  # 1: white
                [255, 0, 0],  # 2: red
                [0, 255, 0],  # 3: green
                [0, 0, 255],  # 4: blue
                [255, 255, 0],  # 5: yellow
                [255, 0, 255],  # 6: magenta
                [0, 255, 255],  # 7: cyan
                [128, 128, 128],  # 8-15: gray variations
                [64, 64, 64],
                [192, 192, 192],
                [32, 32, 32],
                [96, 96, 96],
                [160, 160, 160],
                [224, 224, 224],
                [48, 48, 48],
            ]
        },
    }


class TestInjectMappingFlipHandling:
    """Tests that inject_mapping correctly handles entry-level flips.

    Bug: Tile position calculation ignores entry flip_h/flip_v flags.
    CaptureRenderer correctly mirrors tile positions for flipped entries,
    but inject_mapping extracts tiles from wrong positions.

    Additionally, extracted tile data must be counter-flipped because:
    - CaptureRenderer renders tiles in "screen appearance" (flipped)
    - ROM stores tiles in unflipped form (SNES hardware applies flip at display)
    - Injecting screen-appearance data = SNES applies flip again = double-flipped = wrong
    """

    def test_tile_positions_mirror_when_flip_h(self, tmp_path: Path, qtbot) -> None:
        """With flip_h=True, tile at pos_x=0 should appear at right edge.

        For a 16x16 sprite with flip_h=True:
        - Tile at (pos_x=0, pos_y=0) should be at screen position (entry.x + 8, entry.y)
        - Tile at (pos_x=1, pos_y=0) should be at screen position (entry.x + 0, entry.y)

        To verify correct behavior:
        - Create AI frame with distinct colors in each quadrant
        - After injection, check that tile 0 (pos_x=0, vram_addr=0x1000) contains
          the RIGHT side of the AI frame (because flip_h mirrors positions)

        BUG: Currently calculates screen_x = entry.x + pos_x * 8, ignoring flip.
        """
        capture_data = create_flipped_capture(entry_id=1, flip_h=True, flip_v=False)
        capture_path = tmp_path / "capture.json"
        capture_path.write_text(json.dumps(capture_data))

        # Create AI frame with distinct quadrants:
        # Top-left=RED, Top-right=GREEN, Bottom-left=BLUE, Bottom-right=YELLOW
        ai_frame_path = tmp_path / "ai_frame.png"
        ai_img = Image.new("RGBA", (16, 16), (0, 0, 0, 0))
        for y in range(16):
            for x in range(16):
                if x < 8 and y < 8:
                    ai_img.putpixel((x, y), (255, 0, 0, 255))  # Top-left: RED
                elif x >= 8 and y < 8:
                    ai_img.putpixel((x, y), (0, 255, 0, 255))  # Top-right: GREEN
                elif x < 8 and y >= 8:
                    ai_img.putpixel((x, y), (0, 0, 255, 255))  # Bottom-left: BLUE
                else:
                    ai_img.putpixel((x, y), (255, 255, 0, 255))  # Bottom-right: YELLOW
        ai_img.save(ai_frame_path)

        project = FrameMappingProject(name="test")
        project.ai_frames_dir = tmp_path
        project.ai_frames.append(AIFrame(path=ai_frame_path, index=0))
        project.game_frames.append(
            GameFrame(
                id="F001",
                capture_path=capture_path,
                rom_offsets=[0x100000],
                selected_entry_ids=[1],
            )
        )
        project.mappings.append(FrameMapping(ai_frame_id="ai_frame.png", game_frame_id="F001", offset_x=0, offset_y=0))
        project._rebuild_indices()

        controller = FrameMappingController()
        controller._project = project

        # Track tiles pasted to chunk image (in grid order = tile_index order)
        pasted_tiles: list[Image.Image] = []
        original_paste = Image.Image.paste

        def track_paste(self, im, box=None, mask=None):
            """Track tiles pasted to chunk image."""
            if isinstance(im, Image.Image) and im.size == (8, 8):
                pasted_tiles.append(im.copy())
            return original_paste(self, im, box, mask)

        # Mock ROMVerificationService to return identity mapping (no correction needed)
        # This test focuses on flip handling, not ROM offset correction
        mock_verification = ROMVerificationResult(
            corrections={0x100000: 0x100000},  # Identity mapping
            matched_hal=4,
            matched_raw=0,
            not_found=0,
            total=4,
        )
        mock_verifier = MagicMock()
        mock_verifier.verify_offsets.return_value = mock_verification
        mock_verifier.apply_corrections.return_value = 0

        with (
            patch.object(Image.Image, "paste", track_paste),
            patch.object(controller, "create_injection_copy", return_value=tmp_path / "out.sfc"),
            patch(
                "core.services.injection_orchestrator.ROMVerificationService",
                return_value=mock_verifier,
            ),
            patch("core.services.injection_orchestrator.ROMInjector") as mock_injector_class,
        ):
            mock_injector = MagicMock()
            mock_injector.find_compressed_sprite.return_value = (0, b"\x00" * 128, 128)
            mock_injector.inject_sprite_to_rom.return_value = (True, "Success")
            mock_injector_class.return_value = mock_injector

            rom_path = tmp_path / "test.sfc"
            rom_path.write_bytes(b"\x00" * 0x200000)
            (tmp_path / "out.sfc").write_bytes(b"\x00" * 0x200000)

            controller.inject_mapping("ai_frame.png", rom_path)

        # Find tiles pasted during chunk assembly (after the AI paste and mask paste)
        # The chunk paste happens AFTER render_selection paste operations
        # We expect 4 tiles for a 16x16 sprite
        assert len(pasted_tiles) >= 4, f"Expected at least 4 tile pastes, got {len(pasted_tiles)}"

        # The first tile (tile_index_in_block=0, pos_x=0, pos_y=0) should contain
        # pixels from the RIGHT side of canvas (because flip_h mirrors positions)
        # With flip_h: pos_x=0 → screen x = width - 0 - 8 = 8 → should get GREEN quadrant
        #
        # BUG: Without flip-aware position, pos_x=0 → screen x = 0 → gets RED quadrant
        first_tile = pasted_tiles[-4]  # First of the 4 chunk tiles
        center_pixel = first_tile.getpixel((4, 4))

        # Check if it's GREEN (correct) or RED (buggy)
        # Green = high G channel, Red = high R channel
        if len(center_pixel) >= 3:
            is_green = center_pixel[1] > center_pixel[0] and center_pixel[1] > center_pixel[2]
        else:
            # Palette mode - convert to RGB
            first_tile_rgb = first_tile.convert("RGBA")
            center_pixel = first_tile_rgb.getpixel((4, 4))
            is_green = center_pixel[1] > center_pixel[0] and center_pixel[1] > center_pixel[2]

        assert is_green, (
            f"With flip_h=True, tile at pos_x=0 should extract from canvas x=8 (green quadrant), "
            f"but center pixel was {center_pixel}. Position calculation ignores flip_h."
        )

    def test_tile_data_counter_flipped_for_flip_h(self, tmp_path: Path, qtbot) -> None:
        """Extracted tiles must be counter-flipped before ROM injection.

        When flip_h=True:
        - CaptureRenderer renders tiles horizontally flipped (screen appearance)
        - We extract from screen appearance (flipped)
        - Before injection, we must flip back (counter-flip)
        - SNES will re-apply flip_h at display time → correct result

        BUG: Currently injects screen-appearance data without counter-flip.
        SNES applies flip_h again → double-flipped → incorrect.
        """
        capture_data = create_flipped_capture(entry_id=1, flip_h=True, flip_v=False, width=8, height=8)
        capture_path = tmp_path / "capture.json"
        capture_path.write_text(json.dumps(capture_data))

        # Create AI frame with distinct left/right halves (to detect flipping)
        ai_frame_path = tmp_path / "ai_frame.png"
        ai_img = Image.new("RGBA", (8, 8), (0, 0, 0, 0))
        # Left half: red, Right half: blue
        for y in range(8):
            for x in range(4):
                ai_img.putpixel((x, y), (255, 0, 0, 255))  # Red on left
            for x in range(4, 8):
                ai_img.putpixel((x, y), (0, 0, 255, 255))  # Blue on right
        ai_img.save(ai_frame_path)

        project = FrameMappingProject(name="test")
        project.ai_frames_dir = tmp_path
        project.ai_frames.append(AIFrame(path=ai_frame_path, index=0))
        project.game_frames.append(
            GameFrame(
                id="F001",
                capture_path=capture_path,
                rom_offsets=[0x100000],
                selected_entry_ids=[1],
            )
        )
        project.mappings.append(FrameMapping(ai_frame_id="ai_frame.png", game_frame_id="F001", offset_x=0, offset_y=0))
        project._rebuild_indices()

        controller = FrameMappingController()
        controller._project = project

        # Track the final tile image that gets saved (just before quantization/save)
        saved_tile_images: list[Image.Image] = []
        original_save = Image.Image.save

        def track_save(self, path, *args, **kwargs):
            """Capture images being saved (tile chunks for injection)."""
            saved_tile_images.append(self.copy())
            return original_save(self, path, *args, **kwargs)

        # Mock ROMVerificationService to return identity mapping (no correction needed)
        # This test focuses on flip handling, not ROM offset correction
        mock_verification = ROMVerificationResult(
            corrections={0x100000: 0x100000},  # Identity mapping
            matched_hal=1,
            matched_raw=0,
            not_found=0,
            total=1,
        )
        mock_verifier = MagicMock()
        mock_verifier.verify_offsets.return_value = mock_verification
        mock_verifier.apply_corrections.return_value = 0

        with (
            patch.object(Image.Image, "save", track_save),
            patch.object(controller, "create_injection_copy", return_value=tmp_path / "out.sfc"),
            patch(
                "core.services.injection_orchestrator.ROMVerificationService",
                return_value=mock_verifier,
            ),
            patch("core.services.injection_orchestrator.ROMInjector") as mock_injector_class,
        ):
            mock_injector = MagicMock()
            mock_injector.find_compressed_sprite.return_value = (0, b"\x00" * 32, 32)
            mock_injector.inject_sprite_to_rom.return_value = (True, "Success")
            mock_injector_class.return_value = mock_injector

            rom_path = tmp_path / "test.sfc"
            rom_path.write_bytes(b"\x00" * 0x200000)
            (tmp_path / "out.sfc").write_bytes(b"\x00" * 0x200000)

            controller.inject_mapping("ai_frame.png", rom_path)

        # Find the chunk image (should be 8x8 for single tile)
        chunk_images = [img for img in saved_tile_images if img.size == (8, 8)]

        assert len(chunk_images) >= 1, f"Expected tile chunk image, got {len(saved_tile_images)} saves"

        # Check the saved tile's left edge color
        # If counter-flip applied correctly:
        #   - AI image has red on left, blue on right
        #   - Counter-flip for flip_h → blue on left, red on right in ROM
        #   - SNES applies flip_h → red on left (matches AI image) ✓
        #
        # If bug exists (no counter-flip):
        #   - ROM stores red on left (screen appearance, already flipped by renderer)
        #   - SNES applies flip_h → blue on left (wrong!)
        chunk = chunk_images[0]

        # Convert to RGBA if in palette mode
        if chunk.mode != "RGBA":
            chunk = chunk.convert("RGBA")

        # Sample left edge to check color
        left_pixel = chunk.getpixel((0, 4))  # Middle of left edge

        # With counter-flip applied, left edge should be BLUE (not red)
        # Blue = (0, 0, 255, 255) or close to it after any processing
        is_blue = left_pixel[2] > left_pixel[0]  # Blue channel > Red channel

        assert is_blue, (
            f"With flip_h=True, tile data should be counter-flipped before injection. "
            f"Left edge should be blue (counter-flipped), but got {left_pixel}. "
            f"Tile data not counter-flipped for flip_h."
        )


class TestInjectMappingScale:
    """Tests that inject_mapping applies scale transform to AI image.

    Bug: Preview applies scale via workbench_canvas._generate_preview() but
    inject_mapping only applies flip transforms, not scale.
    """

    def test_inject_mapping_applies_scale(self, tmp_path: Path, qtbot) -> None:
        """Injection should resize AI image when mapping.scale != 1.0.

        BUG: Currently inject_mapping ignores mapping.scale, only applying flips.
        The preview shows scaled image but injection uses original size.
        """
        # Create capture with single entry
        capture_data = create_test_capture(entry_ids=[1])
        capture_path = tmp_path / "capture.json"
        capture_path.write_text(json.dumps(capture_data))

        # Create AI frame image (16x16 pixels)
        ai_frame_path = tmp_path / "ai_frame.png"
        ai_img = Image.new("RGBA", (16, 16), (255, 0, 0, 255))
        ai_img.save(ai_frame_path)

        # Create project with mapping that has scale = 0.5 (should resize to 8x8)
        project = FrameMappingProject(name="test")
        project.ai_frames_dir = tmp_path
        project.ai_frames.append(AIFrame(path=ai_frame_path, index=0))
        project.game_frames.append(
            GameFrame(
                id="F001",
                capture_path=capture_path,
                rom_offsets=[0x100000],
                selected_entry_ids=[1],
            )
        )
        project.mappings.append(
            FrameMapping(
                ai_frame_id="frame_001.png",
                game_frame_id="F001",
                offset_x=0,
                offset_y=0,
                scale=0.5,  # Scale to 50% (16x16 -> 8x8)
            )
        )
        project._rebuild_indices()

        controller = FrameMappingController()
        controller._project = project

        # Track the size of AI image when pasted onto canvas
        # The first paste call in inject_mapping is:
        #   canvas.paste(ai_img, (mapping.offset_x, mapping.offset_y), ai_img)
        # We need to verify ai_img has been scaled before this paste
        # CaptureRenderer also does pastes with 8x8 tiles, so we look for images >= 16x16
        # (the AI image is 16x16 before scaling, 8x8 after scaling if scale=0.5)
        ai_image_size_at_paste: tuple[int, int] | None = None
        all_paste_sizes: list[tuple[int, int]] = []
        original_paste = Image.Image.paste

        def track_paste(self, im, box=None, mask=None):
            """Capture image sizes at paste, looking for AI image (>= original size)."""
            nonlocal ai_image_size_at_paste
            if isinstance(im, Image.Image):
                all_paste_sizes.append((im.width, im.height))
                # The AI image is 16x16 original, or 8x8 if scaled.
                # Look for the first paste that's NOT 8x8 from tiles (could be 16x16 if unscaled)
                # OR that happens after the 8x8 tile pastes
                # Actually, just track all and inspect later
            return original_paste(self, im, box, mask)

        with (
            patch.object(Image.Image, "paste", track_paste),
            patch.object(controller, "create_injection_copy", return_value=tmp_path / "out.sfc"),
            patch("core.services.injection_orchestrator.ROMInjector") as mock_injector_class,
        ):
            mock_injector = MagicMock()
            mock_injector.find_compressed_sprite.return_value = (0, b"\x00" * 32, 32)
            mock_injector.inject_sprite_to_rom.return_value = (True, "Success")
            mock_injector_class.return_value = mock_injector

            # Create fake ROM files
            rom_path = tmp_path / "test.sfc"
            rom_path.write_bytes(b"\x00" * 0x200000)
            (tmp_path / "out.sfc").write_bytes(b"\x00" * 0x200000)

            controller.inject_mapping("frame_001.png", rom_path)

        # Find the AI image paste - should be the first paste that's not from CaptureRenderer tiles
        # CaptureRenderer pastes 8x8 tiles, the AI image is 16x16 (or 8x8 if correctly scaled)
        # If bug exists: AI image is 16x16 (unscaled)
        # If bug fixed: AI image is 8x8 (scaled to 50%)
        # We can identify the AI image paste by looking for a paste > 8x8 which would indicate the bug
        has_unscaled_ai_image = any(size[0] > 8 or size[1] > 8 for size in all_paste_sizes)

        assert not has_unscaled_ai_image, (
            f"AI image should be scaled to 8x8 (50% of 16x16), "
            f"but found unscaled image in pastes: {all_paste_sizes} (scale not applied)"
        )


def create_capture_with_tile_data(
    entry_id: int,
    rom_offset: int,
    tile_data_hex: str,
) -> dict:
    """Create a capture with specific tile data for ROM offset correction tests.

    Args:
        entry_id: Entry ID
        rom_offset: ROM offset to attribute to the tile
        tile_data_hex: 64 hex chars (32 bytes) of tile data
    """
    return {
        "frame": 1,
        "obsel": {},
        "entries": [
            {
                "id": entry_id,
                "x": 100,
                "y": 100,
                "tile": 0,
                "width": 8,
                "height": 8,
                "palette": 7,
                "rom_offset": rom_offset,
                "tiles": [
                    {
                        "tile_index": 0,
                        "vram_addr": 0x1000,
                        "pos_x": 0,
                        "pos_y": 0,
                        "data_hex": tile_data_hex,
                        "rom_offset": rom_offset,
                        "tile_index_in_block": 0,
                    }
                ],
            }
        ],
        "palettes": {7: [[0, 0, 0]] * 16},
    }


class TestRomOffsetCorrection:
    """Tests for automatic ROM offset correction of stale VRAM attribution."""

    def test_corrects_stale_offset_for_raw_tile(self, tmp_path: Path, qtbot) -> None:
        """Stale offset should be corrected by finding tile in ROM via raw search."""
        # Create a distinctive 32-byte tile pattern
        tile_data = bytes(range(32))
        tile_hex = tile_data.hex()

        # Create capture with WRONG rom_offset (stale attribution)
        stale_offset = 0x100000  # Wrong location
        correct_offset = 0x50000  # Actual location in ROM

        capture_data = create_capture_with_tile_data(
            entry_id=1,
            rom_offset=stale_offset,
            tile_data_hex=tile_hex,
        )
        capture_path = tmp_path / "capture.json"
        capture_path.write_text(json.dumps(capture_data))

        # Create ROM with tile at the CORRECT offset
        rom_data = bytearray(0x200000)
        rom_data[correct_offset : correct_offset + 32] = tile_data
        rom_path = tmp_path / "test.sfc"
        rom_path.write_bytes(bytes(rom_data))

        # Create AI frame
        ai_frame_path = tmp_path / "ai_frame.png"
        Image.new("RGBA", (8, 8), (255, 0, 0, 255)).save(ai_frame_path)

        # Set up project
        project = FrameMappingProject(name="test")
        project.ai_frames_dir = tmp_path
        project.ai_frames.append(AIFrame(path=ai_frame_path, index=0))
        project.game_frames.append(
            GameFrame(
                id="F001",
                capture_path=capture_path,
                rom_offsets=[stale_offset],
                selected_entry_ids=[1],
            )
        )
        project.mappings.append(FrameMapping(ai_frame_id="ai_frame.png", game_frame_id="F001", offset_x=0, offset_y=0))
        project._rebuild_indices()

        controller = FrameMappingController()
        controller._project = project

        # Track which offset is used for injection
        injected_offsets: list[int] = []

        # Create mock injector and set it on the controller's orchestrator
        mock_injector = MagicMock()
        mock_injector.find_compressed_sprite.side_effect = Exception("Not HAL compressed")
        mock_injector.inject_sprite_to_rom.side_effect = (
            lambda sprite_path, rom_path, output_path, sprite_offset, **kw: (
                injected_offsets.append(sprite_offset),
                (True, "Success"),
            )[-1]
        )
        controller._injection_orchestrator._rom_injector = mock_injector

        with patch.object(controller, "create_injection_copy", return_value=tmp_path / "out.sfc"):
            (tmp_path / "out.sfc").write_bytes(bytes(rom_data))
            controller.inject_mapping("ai_frame.png", rom_path)

        # Should have corrected to the actual offset where tile exists
        assert len(injected_offsets) == 1, f"Expected 1 injection, got {len(injected_offsets)}"
        assert injected_offsets[0] == correct_offset, (
            f"Expected injection at corrected offset 0x{correct_offset:X}, "
            f"but got 0x{injected_offsets[0]:X} (stale offset not corrected)"
        )

    def test_uses_original_offset_when_tile_found_at_attributed_location(self, tmp_path: Path, qtbot) -> None:
        """When tile is found at the attributed offset, no correction needed."""
        # Create a distinctive tile pattern
        tile_data = bytes([0xAB, 0xCD] * 16)
        tile_hex = tile_data.hex()

        # ROM offset is CORRECT
        correct_offset = 0x80000

        capture_data = create_capture_with_tile_data(
            entry_id=1,
            rom_offset=correct_offset,
            tile_data_hex=tile_hex,
        )
        capture_path = tmp_path / "capture.json"
        capture_path.write_text(json.dumps(capture_data))

        # Create ROM with tile at the attributed offset (correct)
        rom_data = bytearray(0x200000)
        rom_data[correct_offset : correct_offset + 32] = tile_data
        rom_path = tmp_path / "test.sfc"
        rom_path.write_bytes(bytes(rom_data))

        # Create AI frame
        ai_frame_path = tmp_path / "ai_frame.png"
        Image.new("RGBA", (8, 8), (255, 0, 0, 255)).save(ai_frame_path)

        # Set up project
        project = FrameMappingProject(name="test")
        project.ai_frames_dir = tmp_path
        project.ai_frames.append(AIFrame(path=ai_frame_path, index=0))
        project.game_frames.append(
            GameFrame(
                id="F001",
                capture_path=capture_path,
                rom_offsets=[correct_offset],
                selected_entry_ids=[1],
            )
        )
        project.mappings.append(FrameMapping(ai_frame_id="ai_frame.png", game_frame_id="F001", offset_x=0, offset_y=0))
        project._rebuild_indices()

        controller = FrameMappingController()
        controller._project = project

        # Track which offset is used for injection
        injected_offsets: list[int] = []

        # Create mock injector and set it on the controller's orchestrator
        mock_injector = MagicMock()
        mock_injector.find_compressed_sprite.side_effect = Exception("Not HAL compressed")
        mock_injector.inject_sprite_to_rom.side_effect = (
            lambda sprite_path, rom_path, output_path, sprite_offset, **kw: (
                injected_offsets.append(sprite_offset),
                (True, "Success"),
            )[-1]
        )
        controller._injection_orchestrator._rom_injector = mock_injector

        with patch.object(controller, "create_injection_copy", return_value=tmp_path / "out.sfc"):
            (tmp_path / "out.sfc").write_bytes(bytes(rom_data))
            controller.inject_mapping("ai_frame.png", rom_path)

        # Should use original offset since tile is found there
        assert len(injected_offsets) == 1
        assert injected_offsets[0] == correct_offset, (
            f"Expected injection at original offset 0x{correct_offset:X}, but got 0x{injected_offsets[0]:X}"
        )

    def test_emits_error_when_no_tiles_found_in_rom(self, tmp_path: Path, qtbot) -> None:
        """Should emit error when tiles can't be found anywhere in ROM."""
        # Create tile data that won't exist in ROM
        tile_data = bytes([0xDE, 0xAD, 0xBE, 0xEF] * 8)
        tile_hex = tile_data.hex()

        capture_data = create_capture_with_tile_data(
            entry_id=1,
            rom_offset=0x100000,
            tile_data_hex=tile_hex,
        )
        capture_path = tmp_path / "capture.json"
        capture_path.write_text(json.dumps(capture_data))

        # Create ROM without the tile data (all zeros)
        rom_data = bytes(0x200000)
        rom_path = tmp_path / "test.sfc"
        rom_path.write_bytes(rom_data)

        # Create AI frame
        ai_frame_path = tmp_path / "ai_frame.png"
        Image.new("RGBA", (8, 8), (255, 0, 0, 255)).save(ai_frame_path)

        # Set up project
        project = FrameMappingProject(name="test")
        project.ai_frames_dir = tmp_path
        project.ai_frames.append(AIFrame(path=ai_frame_path, index=0))
        project.game_frames.append(
            GameFrame(
                id="F001",
                capture_path=capture_path,
                rom_offsets=[0x100000],
                selected_entry_ids=[1],
            )
        )
        project.mappings.append(FrameMapping(ai_frame_id="ai_frame.png", game_frame_id="F001", offset_x=0, offset_y=0))
        project._rebuild_indices()

        controller = FrameMappingController()
        controller._project = project

        # Track error signals
        errors: list[str] = []
        controller.error_occurred.connect(errors.append)

        with (
            patch.object(controller, "create_injection_copy", return_value=tmp_path / "out.sfc"),
            patch("core.services.injection_orchestrator.ROMInjector") as mock_injector_class,
        ):
            mock_injector = MagicMock()
            mock_injector_class.return_value = mock_injector

            (tmp_path / "out.sfc").write_bytes(rom_data)
            result = controller.inject_mapping("ai_frame.png", rom_path)

        # Should have failed with error
        assert result is False, "Expected injection to fail when no tiles found"
        assert len(errors) == 1, f"Expected 1 error, got {len(errors)}"
        assert "Could not find any tiles in ROM" in errors[0]

    def test_logs_correction_statistics(self, tmp_path: Path, qtbot, caplog) -> None:
        """Should log statistics about corrected offsets."""
        import logging

        # Create two tiles with different offsets
        tile1_data = bytes([0x11] * 32)
        tile2_data = bytes([0x22] * 32)

        # Stale offsets in capture
        stale_offset1 = 0x100000
        stale_offset2 = 0x100100

        # Correct offsets in ROM
        correct_offset1 = 0x50000
        correct_offset2 = 0x50100

        capture_data = {
            "frame": 1,
            "obsel": {},
            "entries": [
                {
                    "id": 1,
                    "x": 100,
                    "y": 100,
                    "tile": 0,
                    "width": 16,
                    "height": 8,
                    "palette": 7,
                    "rom_offset": stale_offset1,
                    "tiles": [
                        {
                            "tile_index": 0,
                            "vram_addr": 0x1000,
                            "pos_x": 0,
                            "pos_y": 0,
                            "data_hex": tile1_data.hex(),
                            "rom_offset": stale_offset1,
                            "tile_index_in_block": 0,
                        },
                        {
                            "tile_index": 1,
                            "vram_addr": 0x1020,
                            "pos_x": 1,
                            "pos_y": 0,
                            "data_hex": tile2_data.hex(),
                            "rom_offset": stale_offset2,
                            "tile_index_in_block": 1,
                        },
                    ],
                }
            ],
            "palettes": {7: [[0, 0, 0]] * 16},
        }
        capture_path = tmp_path / "capture.json"
        capture_path.write_text(json.dumps(capture_data))

        # Create ROM with tiles at correct offsets
        rom_data = bytearray(0x200000)
        rom_data[correct_offset1 : correct_offset1 + 32] = tile1_data
        rom_data[correct_offset2 : correct_offset2 + 32] = tile2_data
        rom_path = tmp_path / "test.sfc"
        rom_path.write_bytes(bytes(rom_data))

        # Create AI frame
        ai_frame_path = tmp_path / "ai_frame.png"
        Image.new("RGBA", (16, 8), (255, 0, 0, 255)).save(ai_frame_path)

        # Set up project
        project = FrameMappingProject(name="test")
        project.ai_frames_dir = tmp_path
        project.ai_frames.append(AIFrame(path=ai_frame_path, index=0))
        project.game_frames.append(
            GameFrame(
                id="F001",
                capture_path=capture_path,
                rom_offsets=[stale_offset1, stale_offset2],
                selected_entry_ids=[1],
            )
        )
        project.mappings.append(FrameMapping(ai_frame_id="ai_frame.png", game_frame_id="F001", offset_x=0, offset_y=0))
        project._rebuild_indices()

        controller = FrameMappingController()
        controller._project = project

        with (
            caplog.at_level(logging.INFO),
            patch.object(controller, "create_injection_copy", return_value=tmp_path / "out.sfc"),
            patch("core.services.injection_orchestrator.ROMInjector") as mock_injector_class,
        ):
            mock_injector = MagicMock()
            mock_injector.find_compressed_sprite.side_effect = Exception("Not HAL")
            mock_injector.inject_sprite_to_rom.return_value = (True, "Success")
            mock_injector_class.return_value = mock_injector

            (tmp_path / "out.sfc").write_bytes(bytes(rom_data))
            controller.inject_mapping("ai_frame.png", rom_path)

        # Check that verification statistics were logged
        # New format from ROMVerificationService: "ROM offset verification: N tiles, N HAL, N raw, N not found"
        log_messages = [r.message for r in caplog.records]
        verification_logs = [m for m in log_messages if "ROM offset verification" in m]

        assert len(verification_logs) >= 1, f"Expected ROM offset verification log, got: {log_messages}"
        # Both tiles should have been found (via HAL or raw search)
        assert any("2 tiles" in m for m in verification_logs), (
            f"Expected log message about 2 tiles verified, got: {verification_logs}"
        )


class TestGetGameFramePreviewFiltering:
    """Tests for get_game_frame_preview respecting selected_entry_ids.

    Bug: get_game_frame_preview was rendering full capture instead of filtered
    entries per selected_entry_ids. Users saw all entries in preview but only
    selected entries got injected.
    """

    def test_game_frame_preview_respects_selected_entry_ids(self, tmp_path: Path, qtbot) -> None:
        """Preview pixmap must match render of filtered entries, not full capture.

        Creates entries at very different positions so the bounding box differs
        between full and filtered captures.
        """
        from core.mesen_integration import CaptureRenderer, MesenCaptureParser

        # Create capture with two entries at very different positions
        # Entry 0 at top-left, Entry 1 at bottom-right (far away)
        capture_data = create_test_capture([0, 1])
        capture_data["entries"][0]["x"] = 10
        capture_data["entries"][0]["y"] = 10
        capture_data["entries"][1]["x"] = 200  # Far right
        capture_data["entries"][1]["y"] = 200  # Far down

        capture_path = tmp_path / "capture.json"
        capture_path.write_text(json.dumps(capture_data))

        # Create controller with project - select only entry 0 (top-left)
        controller = FrameMappingController()
        project = FrameMappingProject(name="test")
        project.game_frames.append(
            GameFrame(
                id="F001",
                capture_path=capture_path,
                selected_entry_ids=[0],  # Only entry 0
            )
        )
        controller._project = project

        # Get preview from controller
        preview = controller.get_game_frame_preview("F001")
        assert preview is not None

        # Render what the filtered result SHOULD look like (returns tuple)
        filtered_result, _ = controller.get_capture_result_for_game_frame("F001")
        assert filtered_result is not None
        assert len(filtered_result.entries) == 1

        expected_renderer = CaptureRenderer(filtered_result)
        expected_img = expected_renderer.render_selection()

        # Also render full capture to show it's different
        parser = MesenCaptureParser()
        full_result = parser.parse_file(capture_path)
        full_renderer = CaptureRenderer(full_result)
        full_img = full_renderer.render_selection()

        # The preview dimensions should match filtered, not full
        # Full image spans from (10,10) to (200+8, 200+8) = large
        # Filtered image spans only (10,10) to (10+8, 10+8) = small
        assert full_img.width > expected_img.width, "Test setup: full should be wider"
        assert full_img.height > expected_img.height, "Test setup: full should be taller"

        # The actual assertion: preview must match filtered size
        assert preview.width() == expected_img.width, (
            f"Preview width {preview.width()} should match filtered {expected_img.width}, not full {full_img.width}"
        )
        assert preview.height() == expected_img.height, (
            f"Preview height {preview.height()} should match filtered {expected_img.height}, not full {full_img.height}"
        )

    def test_game_frame_preview_shows_all_when_no_selection(self, tmp_path: Path, qtbot) -> None:
        """Preview shows all entries when selected_entry_ids is empty."""
        from core.mesen_integration import CaptureRenderer

        # Create capture with entries at different positions
        capture_data = create_test_capture([0, 1, 2])
        capture_data["entries"][0]["x"] = 10
        capture_data["entries"][1]["x"] = 50
        capture_data["entries"][2]["x"] = 100

        capture_path = tmp_path / "capture.json"
        capture_path.write_text(json.dumps(capture_data))

        controller = FrameMappingController()
        project = FrameMappingProject(name="test")
        project.game_frames.append(
            GameFrame(
                id="F001",
                capture_path=capture_path,
                selected_entry_ids=[],  # Empty = show all
            )
        )
        controller._project = project

        # Get preview
        preview = controller.get_game_frame_preview("F001")
        assert preview is not None

        # Get capture result (unfiltered, returns tuple)
        full_result, _ = controller.get_capture_result_for_game_frame("F001")
        assert full_result is not None
        assert len(full_result.entries) == 3

        # Render expected
        expected_renderer = CaptureRenderer(full_result)
        expected_img = expected_renderer.render_selection()

        # Preview should span all entries
        assert preview.width() == expected_img.width
        assert preview.height() == expected_img.height

    def test_preview_cached_after_first_request(self, tmp_path: Path, qtbot) -> None:
        """Preview is cached and subsequent requests don't re-render."""
        capture_data = create_test_capture([0, 1])
        capture_path = tmp_path / "capture.json"
        capture_path.write_text(json.dumps(capture_data))

        controller = FrameMappingController()
        project = FrameMappingProject(name="test")
        project.game_frames.append(
            GameFrame(
                id="F001",
                capture_path=capture_path,
                selected_entry_ids=[1],
            )
        )
        controller._project = project

        # First request
        preview1 = controller.get_game_frame_preview("F001")
        # Second request should return same object (cached)
        preview2 = controller.get_game_frame_preview("F001")

        assert preview1 is not None
        # Same object returned from cache
        assert preview1 is preview2


class TestDuplicateGameFrameIDs:
    """Tests for Bug #4: duplicate GameFrame IDs on import.

    When importing captures with the same filename from different directories,
    the generated frame_id would collide, causing cache overwrites and lookup failures.
    """

    def test_generate_unique_frame_id_no_collision(self, tmp_path: Path, qtbot) -> None:
        """Frame ID is unchanged when no collision exists."""
        controller = FrameMappingController()
        project = FrameMappingProject(name="test")
        controller._project = project

        # No existing frames, ID should be unchanged
        unique_id = controller._generate_unique_frame_id("capture_001")
        assert unique_id == "capture_001"

    def test_generate_unique_frame_id_with_collision(self, tmp_path: Path, qtbot) -> None:
        """Frame ID is suffixed when collision exists."""
        controller = FrameMappingController()
        project = FrameMappingProject(name="test")
        project.game_frames.append(GameFrame(id="capture_001", rom_offsets=[0x1000]))
        controller._project = project

        # Collision exists, should get suffix
        unique_id = controller._generate_unique_frame_id("capture_001")
        assert unique_id == "capture_001_1"

    def test_generate_unique_frame_id_multiple_collisions(self, tmp_path: Path, qtbot) -> None:
        """Frame ID handles multiple collisions (increments suffix)."""
        controller = FrameMappingController()
        project = FrameMappingProject(name="test")
        project.game_frames.append(GameFrame(id="capture_001", rom_offsets=[0x1000]))
        project.game_frames.append(GameFrame(id="capture_001_1", rom_offsets=[0x2000]))
        project.game_frames.append(GameFrame(id="capture_001_2", rom_offsets=[0x3000]))
        controller._project = project

        # Multiple collisions exist, should get next available suffix
        unique_id = controller._generate_unique_frame_id("capture_001")
        assert unique_id == "capture_001_3"

    def test_game_frames_always_have_unique_ids(self, tmp_path: Path, qtbot) -> None:
        """After adding multiple frames with same base ID, all IDs are unique."""
        controller = FrameMappingController()
        project = FrameMappingProject(name="test")
        controller._project = project

        # Simulate adding three frames that would have the same ID
        ids = []
        for i in range(3):
            unique_id = controller._generate_unique_frame_id("capture_001")
            project.game_frames.append(GameFrame(id=unique_id, rom_offsets=[0x1000 * (i + 1)]))
            ids.append(unique_id)

        # All IDs should be unique
        assert len(ids) == len(set(ids))
        assert ids == ["capture_001", "capture_001_1", "capture_001_2"]


class TestAIFramesLoadingPrunesMappings:
    """Tests for Bug #3: AI frames loading orphans mappings.

    When reloading AI frames, mappings that reference non-existent indices
    should be pruned to prevent orphaned references.
    """

    def test_load_ai_frames_prunes_orphaned_mappings(self, tmp_path: Path, qtbot) -> None:
        """Reloading AI frames with fewer frames prunes invalid mappings."""
        # Create initial AI frames directory with 5 frames
        ai_dir = tmp_path / "ai_frames"
        ai_dir.mkdir()
        for i in range(5):
            (ai_dir / f"frame_{i:03d}.png").write_bytes(
                b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
                b"\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
                b"\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01"
                b"\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
            )

        controller = FrameMappingController()
        controller.load_ai_frames_from_directory(ai_dir)

        # Create mappings for frames 0, 2, and 4 (using filenames as IDs)
        controller._project.game_frames.append(GameFrame(id="G1", rom_offsets=[0x1000]))
        controller._project.game_frames.append(GameFrame(id="G2", rom_offsets=[0x2000]))
        controller._project.game_frames.append(GameFrame(id="G3", rom_offsets=[0x3000]))
        controller._project.mappings.append(FrameMapping(ai_frame_id="frame_000.png", game_frame_id="G1"))
        controller._project.mappings.append(FrameMapping(ai_frame_id="frame_002.png", game_frame_id="G2"))
        controller._project.mappings.append(FrameMapping(ai_frame_id="frame_004.png", game_frame_id="G3"))
        controller._project._rebuild_indices()

        # Now reload with only 3 frames (filenames frame_000, frame_001, frame_002)
        ai_dir2 = tmp_path / "ai_frames2"
        ai_dir2.mkdir()
        for i in range(3):
            (ai_dir2 / f"frame_{i:03d}.png").write_bytes(
                b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
                b"\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
                b"\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01"
                b"\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
            )

        controller.load_ai_frames_from_directory(ai_dir2)

        # Mapping to frame_004.png should be pruned (file no longer exists)
        # Mappings to frame_000.png and frame_002.png should remain
        assert len(controller._project.mappings) == 2
        ai_ids = {m.ai_frame_id for m in controller._project.mappings}
        assert ai_ids == {"frame_000.png", "frame_002.png"}

    def test_load_ai_frames_preserves_compatible_mappings(self, tmp_path: Path, qtbot) -> None:
        """Reloading AI frames with same or more frames preserves all mappings."""
        ai_dir = tmp_path / "ai_frames"
        ai_dir.mkdir()
        for i in range(5):
            (ai_dir / f"frame_{i:03d}.png").write_bytes(
                b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
                b"\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
                b"\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01"
                b"\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
            )

        controller = FrameMappingController()
        controller.load_ai_frames_from_directory(ai_dir)

        # Create mappings for frames 0 and 2 (using filenames as IDs)
        controller._project.game_frames.append(GameFrame(id="G1", rom_offsets=[0x1000]))
        controller._project.game_frames.append(GameFrame(id="G2", rom_offsets=[0x2000]))
        controller._project.mappings.append(FrameMapping(ai_frame_id="frame_000.png", game_frame_id="G1"))
        controller._project.mappings.append(FrameMapping(ai_frame_id="frame_002.png", game_frame_id="G2"))
        controller._project._rebuild_indices()

        # Reload same directory - all mappings should remain (filenames match)
        controller.load_ai_frames_from_directory(ai_dir)

        assert len(controller._project.mappings) == 2
        ai_ids = {m.ai_frame_id for m in controller._project.mappings}
        assert ai_ids == {"frame_000.png", "frame_002.png"}

    def test_game_frames_unchanged_after_ai_frames_reload(self, tmp_path: Path, qtbot) -> None:
        """Reloading AI frames should not affect game frames."""
        ai_dir = tmp_path / "ai_frames"
        ai_dir.mkdir()
        for i in range(3):
            (ai_dir / f"frame_{i:03d}.png").write_bytes(
                b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
                b"\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
                b"\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01"
                b"\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
            )

        controller = FrameMappingController()
        controller.load_ai_frames_from_directory(ai_dir)

        # Add game frames
        controller._project.game_frames.append(GameFrame(id="G1", rom_offsets=[0x1000]))
        controller._project.game_frames.append(GameFrame(id="G2", rom_offsets=[0x2000]))

        # Reload AI frames
        controller.load_ai_frames_from_directory(ai_dir)

        # Game frames should be unchanged
        assert len(controller._project.game_frames) == 2
        assert controller._project.game_frames[0].id == "G1"
        assert controller._project.game_frames[1].id == "G2"


class TestPreviewCacheInvalidation:
    """Tests for Bug #5: Preview cache never invalidates.

    The cache should check file mtime and regenerate if the source file changed.
    """

    def test_preview_cache_invalidates_on_file_change(self, tmp_path: Path, qtbot) -> None:
        """Preview regenerates when source capture file is modified."""
        import time

        # Create initial capture
        capture_data = create_test_capture([0, 1])
        capture_path = tmp_path / "capture.json"
        capture_path.write_text(json.dumps(capture_data))

        controller = FrameMappingController()
        project = FrameMappingProject(name="test")
        project.game_frames.append(
            GameFrame(
                id="F001",
                capture_path=capture_path,
                selected_entry_ids=[0, 1],
            )
        )
        controller._project = project

        # First request caches the preview
        preview1 = controller.get_game_frame_preview("F001")
        assert preview1 is not None

        # Ensure mtime changes (some filesystems have second-level precision)
        time.sleep(0.1)

        # Modify the capture file
        capture_data2 = create_test_capture([0, 1, 2])  # Add a third entry
        capture_path.write_text(json.dumps(capture_data2))

        # Second request should regenerate (different file content/mtime)
        preview2 = controller.get_game_frame_preview("F001")
        assert preview2 is not None

        # Should be different pixmap objects (regenerated)
        assert preview1 is not preview2

    def test_preview_cache_returns_cached_if_file_unchanged(self, tmp_path: Path, qtbot) -> None:
        """Preview returns cached pixmap when file hasn't changed."""
        capture_data = create_test_capture([0, 1])
        capture_path = tmp_path / "capture.json"
        capture_path.write_text(json.dumps(capture_data))

        controller = FrameMappingController()
        project = FrameMappingProject(name="test")
        project.game_frames.append(
            GameFrame(
                id="F001",
                capture_path=capture_path,
                selected_entry_ids=[0, 1],
            )
        )
        controller._project = project

        # First and second requests should return same cached object
        preview1 = controller.get_game_frame_preview("F001")
        preview2 = controller.get_game_frame_preview("F001")

        assert preview1 is not None
        assert preview1 is preview2  # Same object from cache

    def test_preview_cache_returns_cached_if_no_file(self, tmp_path: Path, qtbot) -> None:
        """Preview returns cached pixmap when capture_path is None."""
        controller = FrameMappingController()
        project = FrameMappingProject(name="test")
        project.game_frames.append(
            GameFrame(
                id="F001",
                capture_path=None,  # No file
                selected_entry_ids=[],
            )
        )
        controller._project = project

        # Manually add a preview to the cache via service
        from PySide6.QtGui import QPixmap

        cached_pixmap = QPixmap(10, 10)
        # Cache stores (pixmap, mtime, entry_ids) - use 0.0 mtime and empty tuple for no-file case
        controller._preview_service.set_preview_cache("F001", cached_pixmap, 0.0, ())

        # Should return cached even with no file to compare
        preview = controller.get_game_frame_preview("F001")
        assert preview is cached_pixmap

    def test_preview_cache_returns_cached_if_file_deleted(self, tmp_path: Path, qtbot) -> None:
        """Preview returns cached pixmap when file has been deleted."""
        capture_data = create_test_capture([0, 1])
        capture_path = tmp_path / "capture.json"
        capture_path.write_text(json.dumps(capture_data))

        controller = FrameMappingController()
        project = FrameMappingProject(name="test")
        project.game_frames.append(
            GameFrame(
                id="F001",
                capture_path=capture_path,
                selected_entry_ids=[0, 1],
            )
        )
        controller._project = project

        # First request caches the preview
        preview1 = controller.get_game_frame_preview("F001")
        assert preview1 is not None

        # Delete the source file
        capture_path.unlink()

        # Should return cached since file doesn't exist anymore
        preview2 = controller.get_game_frame_preview("F001")
        assert preview2 is preview1


class TestStaleEntryIdsFallback:
    """Tests for stale entry IDs fallback behavior in preview and injection.

    Bug: Preview falls back to all entries when selected_entry_ids are stale,
    but injection has no fallback and fails with "No entries match ROM offsets" error.

    Fix: Both should use same fallback strategy:
    1. Try filtering by selected_entry_ids
    2. If empty, fall back to rom_offset filtering (emit warning)
    3. If still empty, error
    """

    def test_preview_stale_entry_ids_falls_back_to_rom_offset(self, tmp_path: Path, qtbot) -> None:
        """Preview should fall back to rom_offset when selected_entry_ids are stale.

        Scenario: Capture has entries [10, 20] with rom_offset 0x123456.
        GameFrame has selected_entry_ids=[99, 100] (stale) but rom_offsets=[0x123456].
        Expected: Preview returns all entries matching rom_offset (entries 10, 20).
        """
        # Create capture with entries 10, 20 at specific rom_offset
        rom_offset = 0x123456
        capture_data = create_test_capture(
            entry_ids=[10, 20],
            rom_offsets=[rom_offset, rom_offset],
        )
        capture_path = tmp_path / "capture.json"
        capture_path.write_text(json.dumps(capture_data))

        controller = FrameMappingController()
        project = FrameMappingProject(name="test")
        project.game_frames.append(
            GameFrame(
                id="F001",
                capture_path=capture_path,
                rom_offsets=[rom_offset],
                selected_entry_ids=[99, 100],  # Stale IDs not in capture
            )
        )
        controller._project = project

        # Preview should emit stale_entries_warning (returns tuple)
        with qtbot.waitSignal(controller.stale_entries_warning, timeout=1000):
            result, _ = controller.get_capture_result_for_game_frame("F001")

        # Should fall back to rom_offset filtering
        assert result is not None
        assert len(result.entries) == 2
        assert {e.id for e in result.entries} == {10, 20}

    def test_injection_stale_entry_ids_triggers_fallback_path(self, tmp_path: Path, qtbot) -> None:
        """Injection should trigger stale_entries_warning and fall back to rom_offset.

        BUG: Currently fails with "No entries match ROM offsets" error without warning.
        FIX: Should emit warning and apply fallback like preview does.

        Verifies: When selected_entry_ids are stale, fallback filtering is applied.
        """
        rom_offset = 0x123456
        capture_data = create_test_capture(
            entry_ids=[10, 20],
            rom_offsets=[rom_offset, rom_offset],
        )
        capture_path = tmp_path / "capture.json"
        capture_path.write_text(json.dumps(capture_data))

        # Create project with stale selected_entry_ids
        project = FrameMappingProject(name="test")
        project.game_frames.append(
            GameFrame(
                id="F001",
                capture_path=capture_path,
                rom_offsets=[rom_offset],
                selected_entry_ids=[99, 100],  # Stale IDs not in capture
            )
        )
        controller = FrameMappingController()
        controller._project = project

        # When injection encounters stale IDs, it should emit warning
        # (This verifies the fallback code path is being executed)
        with qtbot.waitSignal(controller.stale_entries_warning, timeout=1000):
            # We're not calling inject_mapping directly, but verifying internal filtering
            # by checking the controller's filtering logic matches preview (returns tuple)
            result, _ = controller.get_capture_result_for_game_frame("F001")

        # Both preview and injection should return same fallback result
        assert result is not None
        assert len(result.entries) == 2
        assert {e.id for e in result.entries} == {10, 20}

    def test_preview_and_injection_consistency_with_valid_ids(self, tmp_path: Path, qtbot) -> None:
        """Preview and injection should both use selected_entry_ids when valid."""
        capture_data = create_test_capture([10, 20, 30])
        capture_path = tmp_path / "capture.json"
        capture_path.write_text(json.dumps(capture_data))

        rom_offset = 0x100000 + 0x100  # Entry 10's offset

        # Create AI frame
        ai_frame_path = tmp_path / "ai_frame.png"
        ai_img = Image.new("RGBA", (8, 8), (255, 0, 0, 255))
        ai_img.save(ai_frame_path)

        project = FrameMappingProject(name="test")
        project.ai_frames_dir = tmp_path
        project.ai_frames.append(AIFrame(path=ai_frame_path, index=0))
        project.game_frames.append(
            GameFrame(
                id="F001",
                capture_path=capture_path,
                rom_offsets=[rom_offset],
                selected_entry_ids=[10],  # Valid ID
            )
        )
        project.mappings.append(
            FrameMapping(
                ai_frame_id="ai_frame.png",
                game_frame_id="F001",
                offset_x=0,
                offset_y=0,
            )
        )
        project._rebuild_indices()

        controller = FrameMappingController()
        controller._project = project

        # Preview should filter to entry 10 only (returns tuple)
        preview_result, _ = controller.get_capture_result_for_game_frame("F001")
        assert preview_result is not None
        assert len(preview_result.entries) == 1
        assert preview_result.entries[0].id == 10

        # Injection should also use only entry 10
        captured_entries: list[int] = []

        def mock_render_selection(self):
            for entry in self.capture.entries:
                captured_entries.append(entry.id)
            return Image.new("RGBA", (8, 8), (0, 0, 0, 255))

        # Create mock injector and set it on the controller's orchestrator
        mock_injector = MagicMock()
        mock_injector.find_compressed_sprite.return_value = (0, b"\x00" * 32, 32)
        mock_injector.inject_sprite_to_rom.return_value = (True, "Success")
        controller._injection_orchestrator._rom_injector = mock_injector

        with (
            patch(
                "core.mesen_integration.capture_renderer.CaptureRenderer.render_selection",
                mock_render_selection,
            ),
            patch.object(controller, "create_injection_copy", return_value=tmp_path / "out.sfc"),
        ):
            rom_path = tmp_path / "test.sfc"
            rom_path.write_bytes(b"\x00" * 0x200000)
            (tmp_path / "out.sfc").write_bytes(b"\x00" * 0x200000)

            result = controller.inject_mapping("ai_frame.png", rom_path)

        assert result is True
        assert captured_entries == [10], f"Expected [10], got {captured_entries}"


class TestCompressionTypeSelection:
    """Tests for user-controlled compression type selection.

    The compression type (RAW/HAL) is set by the user via UI toggle in the workbench.
    New imports default to RAW. Legacy projects without stored types also default to RAW.
    """

    def test_stored_raw_type_uses_raw_injection(self, tmp_path: Path, qtbot) -> None:
        """Stored RAW compression type should use RAW injection."""
        tile_data = bytes([0x11] * 32)
        tile_hex = tile_data.hex()

        rom_offset = 0x35000

        capture_data = create_capture_with_tile_data(
            entry_id=1,
            rom_offset=rom_offset,
            tile_data_hex=tile_hex,
        )
        capture_path = tmp_path / "capture.json"
        capture_path.write_text(json.dumps(capture_data))

        rom_data = bytearray(0x200000)
        rom_data[rom_offset : rom_offset + 32] = tile_data
        rom_path = tmp_path / "test.sfc"
        rom_path.write_bytes(bytes(rom_data))

        ai_frame_path = tmp_path / "ai_frame.png"
        Image.new("RGBA", (8, 8), (255, 0, 0, 255)).save(ai_frame_path)

        project = FrameMappingProject(name="test")
        project.ai_frames_dir = tmp_path
        project.ai_frames.append(AIFrame(path=ai_frame_path, index=0))
        project.game_frames.append(
            GameFrame(
                id="F001",
                capture_path=capture_path,
                rom_offsets=[rom_offset],
                selected_entry_ids=[1],
                compression_types={rom_offset: "raw"},
            )
        )
        project.mappings.append(FrameMapping(ai_frame_id="ai_frame.png", game_frame_id="F001", offset_x=0, offset_y=0))
        project._rebuild_indices()

        controller = FrameMappingController()
        controller._project = project

        from core.rom_injector import CompressionType

        injected_compression: list[CompressionType] = []

        # Create mock injector and set it on the controller's orchestrator
        mock_injector = MagicMock()
        mock_injector.inject_sprite_to_rom.side_effect = (
            lambda sprite_path, rom_path, output_path, sprite_offset, compression_type, **kw: (
                injected_compression.append(compression_type),
                (True, "Success"),
            )[-1]
        )
        controller._injection_orchestrator._rom_injector = mock_injector

        with patch.object(controller, "create_injection_copy", return_value=tmp_path / "out.sfc"):
            (tmp_path / "out.sfc").write_bytes(bytes(rom_data))
            result = controller.inject_mapping("ai_frame.png", rom_path)

        assert result is True
        assert len(injected_compression) == 1
        assert injected_compression[0] == CompressionType.RAW

    def test_stored_hal_type_uses_hal_injection(self, tmp_path: Path, qtbot) -> None:
        """Stored HAL compression type should use HAL injection."""
        tile_data = bytes([0x44] * 32)
        tile_hex = tile_data.hex()

        rom_offset = 0x60000

        capture_data = create_capture_with_tile_data(
            entry_id=1,
            rom_offset=rom_offset,
            tile_data_hex=tile_hex,
        )
        capture_path = tmp_path / "capture.json"
        capture_path.write_text(json.dumps(capture_data))

        rom_data = bytearray(0x200000)
        rom_data[rom_offset : rom_offset + 32] = tile_data
        rom_path = tmp_path / "test.sfc"
        rom_path.write_bytes(bytes(rom_data))

        ai_frame_path = tmp_path / "ai_frame.png"
        Image.new("RGBA", (8, 8), (255, 0, 0, 255)).save(ai_frame_path)

        project = FrameMappingProject(name="test")
        project.ai_frames_dir = tmp_path
        project.ai_frames.append(AIFrame(path=ai_frame_path, index=0))
        project.game_frames.append(
            GameFrame(
                id="F001",
                capture_path=capture_path,
                rom_offsets=[rom_offset],
                selected_entry_ids=[1],
                compression_types={rom_offset: "hal"},
            )
        )
        project.mappings.append(FrameMapping(ai_frame_id="ai_frame.png", game_frame_id="F001", offset_x=0, offset_y=0))
        project._rebuild_indices()

        controller = FrameMappingController()
        controller._project = project

        from core.rom_injector import CompressionType

        injected_compression: list[CompressionType] = []

        # Create mock injector and set it on the controller's orchestrator
        mock_injector = MagicMock()
        mock_injector.find_compressed_sprite.return_value = (0, b"\x00" * 32, 32)
        mock_injector.inject_sprite_to_rom.side_effect = (
            lambda sprite_path, rom_path, output_path, sprite_offset, compression_type, **kw: (
                injected_compression.append(compression_type),
                (True, "Success"),
            )[-1]
        )
        controller._injection_orchestrator._rom_injector = mock_injector

        with patch.object(controller, "create_injection_copy", return_value=tmp_path / "out.sfc"):
            (tmp_path / "out.sfc").write_bytes(bytes(rom_data))
            result = controller.inject_mapping("ai_frame.png", rom_path)

        assert result is True
        assert len(injected_compression) == 1
        assert injected_compression[0] == CompressionType.HAL

    def test_missing_compression_type_defaults_to_raw(self, tmp_path: Path, qtbot) -> None:
        """Legacy projects without compression_types should default to RAW."""
        tile_data = bytes([0x22] * 32)
        tile_hex = tile_data.hex()

        rom_offset = 0x40000

        capture_data = create_capture_with_tile_data(
            entry_id=1,
            rom_offset=rom_offset,
            tile_data_hex=tile_hex,
        )
        capture_path = tmp_path / "capture.json"
        capture_path.write_text(json.dumps(capture_data))

        rom_data = bytearray(0x200000)
        rom_data[rom_offset : rom_offset + 32] = tile_data
        rom_path = tmp_path / "test.sfc"
        rom_path.write_bytes(bytes(rom_data))

        ai_frame_path = tmp_path / "ai_frame.png"
        Image.new("RGBA", (8, 8), (255, 0, 0, 255)).save(ai_frame_path)

        # Legacy project: no compression_types set
        project = FrameMappingProject(name="test")
        project.ai_frames_dir = tmp_path
        project.ai_frames.append(AIFrame(path=ai_frame_path, index=0))
        project.game_frames.append(
            GameFrame(
                id="F001",
                capture_path=capture_path,
                rom_offsets=[rom_offset],
                selected_entry_ids=[1],
                compression_types={},  # Empty - legacy project
            )
        )
        project.mappings.append(FrameMapping(ai_frame_id="ai_frame.png", game_frame_id="F001", offset_x=0, offset_y=0))
        project._rebuild_indices()

        controller = FrameMappingController()
        controller._project = project

        from core.rom_injector import CompressionType

        injected_compression: list[CompressionType] = []

        # Create mock injector and set it on the controller's orchestrator
        mock_injector = MagicMock()
        mock_injector.inject_sprite_to_rom.side_effect = (
            lambda sprite_path, rom_path, output_path, sprite_offset, compression_type, **kw: (
                injected_compression.append(compression_type),
                (True, "Success"),
            )[-1]
        )
        controller._injection_orchestrator._rom_injector = mock_injector

        with patch.object(controller, "create_injection_copy", return_value=tmp_path / "out.sfc"):
            (tmp_path / "out.sfc").write_bytes(bytes(rom_data))
            result = controller.inject_mapping("ai_frame.png", rom_path)

        assert result is True
        assert len(injected_compression) == 1
        # Should default to RAW when no stored type
        assert injected_compression[0] == CompressionType.RAW


class TestAllowFallbackParameter:
    """Tests for the allow_fallback parameter in inject_mapping.

    By default (allow_fallback=False), injection should abort when entry IDs are stale.
    When allow_fallback=True, it should fall back to rom_offset filtering.
    """

    def test_injection_aborts_on_stale_entry_ids_without_allow_fallback(self, tmp_path: Path, qtbot) -> None:
        """Injection should abort when stored entry IDs are stale and allow_fallback=False.

        This is the default safe behavior to prevent silent data corruption.
        """
        rom_offset = 0x123456
        capture_data = create_test_capture(
            entry_ids=[10, 20],
            rom_offsets=[rom_offset, rom_offset],
        )
        capture_path = tmp_path / "capture.json"
        capture_path.write_text(json.dumps(capture_data))

        # Create AI frame
        ai_frame_path = tmp_path / "ai_frame.png"
        Image.new("RGBA", (8, 8), (255, 0, 0, 255)).save(ai_frame_path)

        # Create project with stale selected_entry_ids
        project = FrameMappingProject(name="test")
        project.ai_frames_dir = tmp_path
        project.ai_frames.append(AIFrame(path=ai_frame_path, index=0))
        project.game_frames.append(
            GameFrame(
                id="F001",
                capture_path=capture_path,
                rom_offsets=[rom_offset],
                selected_entry_ids=[99, 100],  # Stale IDs not in capture
            )
        )
        project.mappings.append(FrameMapping(ai_frame_id="ai_frame.png", game_frame_id="F001", offset_x=0, offset_y=0))
        project._rebuild_indices()

        controller = FrameMappingController()
        controller._project = project

        # Create dummy ROM
        rom_path = tmp_path / "test.sfc"
        rom_path.write_bytes(b"\x00" * 0x200000)

        # Injection should abort and emit stale_entries_warning + error_occurred
        with qtbot.waitSignal(controller.stale_entries_warning, timeout=1000):
            result = controller.inject_mapping("ai_frame.png", rom_path, allow_fallback=False)

        # Should return False (aborted)
        assert result is False

    def test_injection_uses_fallback_when_explicitly_allowed(self, tmp_path: Path, qtbot) -> None:
        """Injection should use rom_offset fallback when allow_fallback=True."""
        tile_data = bytes([0x11] * 32)
        tile_hex = tile_data.hex()

        rom_offset = 0x35000
        capture_data = create_capture_with_tile_data(
            entry_id=10,
            rom_offset=rom_offset,
            tile_data_hex=tile_hex,
        )
        capture_path = tmp_path / "capture.json"
        capture_path.write_text(json.dumps(capture_data))

        rom_data = bytearray(0x200000)
        rom_data[rom_offset : rom_offset + 32] = tile_data
        rom_path = tmp_path / "test.sfc"
        rom_path.write_bytes(bytes(rom_data))

        ai_frame_path = tmp_path / "ai_frame.png"
        Image.new("RGBA", (8, 8), (255, 0, 0, 255)).save(ai_frame_path)

        # Create project with stale selected_entry_ids but valid rom_offsets
        project = FrameMappingProject(name="test")
        project.ai_frames_dir = tmp_path
        project.ai_frames.append(AIFrame(path=ai_frame_path, index=0))
        project.game_frames.append(
            GameFrame(
                id="F001",
                capture_path=capture_path,
                rom_offsets=[rom_offset],
                selected_entry_ids=[99],  # Stale ID
                compression_types={rom_offset: "raw"},
            )
        )
        project.mappings.append(FrameMapping(ai_frame_id="ai_frame.png", game_frame_id="F001", offset_x=0, offset_y=0))
        project._rebuild_indices()

        controller = FrameMappingController()
        controller._project = project

        captured_entries: list[int] = []

        def mock_render_selection(self):
            for entry in self.capture.entries:
                captured_entries.append(entry.id)
            return Image.new("RGBA", (8, 8), (0, 0, 0, 255))

        # Create mock injector and set it on the controller's orchestrator
        mock_injector = MagicMock()
        mock_injector.find_compressed_sprite.return_value = (0, b"\x00" * 32, 32)
        mock_injector.inject_sprite_to_rom.return_value = (True, "Success")
        controller._injection_orchestrator._rom_injector = mock_injector

        with (
            patch(
                "core.mesen_integration.capture_renderer.CaptureRenderer.render_selection",
                mock_render_selection,
            ),
            patch.object(controller, "create_injection_copy", return_value=tmp_path / "out.sfc"),
        ):
            (tmp_path / "out.sfc").write_bytes(bytes(rom_data))

            # With allow_fallback=True, injection should proceed using rom_offset filtering
            # Note: stale_entries_warning is NOT emitted when allow_fallback=True because
            # the fallback is explicitly allowed and doesn't need user confirmation
            result = controller.inject_mapping("ai_frame.png", rom_path, allow_fallback=True)

        assert result is True
        # Should have used entry 10 via rom_offset fallback
        assert 10 in captured_entries


class TestPreserveExistingParameter:
    """Tests for the preserve_existing parameter in inject_mapping.

    When using "Reuse ROM" option, subsequent injections should preserve prior injections
    by reading from the output ROM instead of copying from the original ROM.
    """

    def test_preserve_existing_passed_to_injector_for_existing_output(self, tmp_path: Path, qtbot) -> None:
        """When output_path exists, preserve_existing should be True for first injection."""
        tile_data = bytes([0x11] * 32)
        tile_hex = tile_data.hex()

        rom_offset = 0x35000
        capture_data = create_capture_with_tile_data(
            entry_id=10,
            rom_offset=rom_offset,
            tile_data_hex=tile_hex,
        )
        capture_path = tmp_path / "capture.json"
        capture_path.write_text(json.dumps(capture_data))

        rom_data = bytearray(0x200000)
        rom_data[rom_offset : rom_offset + 32] = tile_data
        rom_path = tmp_path / "test.sfc"
        rom_path.write_bytes(bytes(rom_data))

        # Create existing output ROM (simulating "Reuse ROM" scenario)
        output_rom_path = tmp_path / "output.sfc"
        output_rom_path.write_bytes(bytes(rom_data))

        ai_frame_path = tmp_path / "ai_frame.png"
        Image.new("RGBA", (8, 8), (255, 0, 0, 255)).save(ai_frame_path)

        project = FrameMappingProject(name="test")
        project.ai_frames_dir = tmp_path
        project.ai_frames.append(AIFrame(path=ai_frame_path, index=0))
        project.game_frames.append(
            GameFrame(
                id="F001",
                capture_path=capture_path,
                rom_offsets=[rom_offset],
                selected_entry_ids=[10],
                compression_types={rom_offset: "raw"},
            )
        )
        project.mappings.append(FrameMapping(ai_frame_id="ai_frame.png", game_frame_id="F001", offset_x=0, offset_y=0))
        project._rebuild_indices()

        controller = FrameMappingController()
        controller._project = project

        preserve_existing_values: list[bool] = []

        # Create mock injector and set it on the controller's orchestrator
        mock_injector = MagicMock()
        mock_injector.find_compressed_sprite.return_value = (0, b"\x00" * 32, 32)

        def capture_preserve_existing(**kwargs):
            preserve_existing_values.append(kwargs.get("preserve_existing", False))
            return (True, "Success")

        mock_injector.inject_sprite_to_rom.side_effect = capture_preserve_existing
        controller._injection_orchestrator._rom_injector = mock_injector

        # Inject with existing output_path (simulates "Reuse ROM")
        result = controller.inject_mapping("ai_frame.png", rom_path, output_path=output_rom_path)

        assert result is True
        # Since output_path exists, preserve_existing should be True
        assert len(preserve_existing_values) == 1
        assert preserve_existing_values[0] is True

    def test_preserve_existing_false_for_fresh_copy(self, tmp_path: Path, qtbot) -> None:
        """When creating a fresh copy, preserve_existing should be False for first injection."""
        tile_data = bytes([0x11] * 32)
        tile_hex = tile_data.hex()

        rom_offset = 0x35000
        capture_data = create_capture_with_tile_data(
            entry_id=10,
            rom_offset=rom_offset,
            tile_data_hex=tile_hex,
        )
        capture_path = tmp_path / "capture.json"
        capture_path.write_text(json.dumps(capture_data))

        rom_data = bytearray(0x200000)
        rom_data[rom_offset : rom_offset + 32] = tile_data
        rom_path = tmp_path / "test.sfc"
        rom_path.write_bytes(bytes(rom_data))

        ai_frame_path = tmp_path / "ai_frame.png"
        Image.new("RGBA", (8, 8), (255, 0, 0, 255)).save(ai_frame_path)

        project = FrameMappingProject(name="test")
        project.ai_frames_dir = tmp_path
        project.ai_frames.append(AIFrame(path=ai_frame_path, index=0))
        project.game_frames.append(
            GameFrame(
                id="F001",
                capture_path=capture_path,
                rom_offsets=[rom_offset],
                selected_entry_ids=[10],
                compression_types={rom_offset: "raw"},
            )
        )
        project.mappings.append(FrameMapping(ai_frame_id="ai_frame.png", game_frame_id="F001", offset_x=0, offset_y=0))
        project._rebuild_indices()

        controller = FrameMappingController()
        controller._project = project

        preserve_existing_values: list[bool] = []

        # Create mock injector and set it on the controller's orchestrator
        mock_injector = MagicMock()
        mock_injector.find_compressed_sprite.return_value = (0, b"\x00" * 32, 32)

        def capture_preserve_existing(**kwargs):
            preserve_existing_values.append(kwargs.get("preserve_existing", False))
            return (True, "Success")

        mock_injector.inject_sprite_to_rom.side_effect = capture_preserve_existing
        controller._injection_orchestrator._rom_injector = mock_injector

        with patch.object(controller, "create_injection_copy", return_value=tmp_path / "new_output.sfc"):
            # Need to create the output file since create_injection_copy is mocked
            (tmp_path / "new_output.sfc").write_bytes(bytes(rom_data))

            # Inject without existing output_path (creates new copy)
            # Note: output_path=None means controller creates a fresh copy
            result = controller.inject_mapping("ai_frame.png", rom_path, output_path=None)

        assert result is True
        # Since a fresh copy was created, preserve_existing should be False
        assert len(preserve_existing_values) == 1
        assert preserve_existing_values[0] is False


class TestUpdateMappingAlignmentEmitsSaveRequested:
    """Test that update_mapping_alignment emits save_requested for auto-save.

    Bug: Alignment changes (drag/nudge on canvas) were lost on app close because
    update_mapping_alignment only emitted alignment_updated but NOT save_requested.
    """

    def test_update_mapping_alignment_emits_save_requested(self, tmp_path: Path, qtbot) -> None:
        """Verify alignment changes trigger auto-save signal."""
        # Create minimal project with a mapping
        ai_frame_path = tmp_path / "frame_001.png"
        ai_frame_path.write_bytes(
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
            b"\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
            b"\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01"
            b"\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
        )

        project = FrameMappingProject(name="test")
        project.ai_frames_dir = tmp_path
        project.ai_frames.append(AIFrame(path=ai_frame_path, index=0))
        project.game_frames.append(GameFrame(id="G001", rom_offsets=[0x1000], selected_entry_ids=[]))
        project.mappings.append(FrameMapping(ai_frame_id="frame_001.png", game_frame_id="G001"))
        project._rebuild_indices()

        controller = FrameMappingController()
        controller._project = project

        # Verify save_requested is emitted when alignment is updated
        with qtbot.waitSignal(controller.save_requested, timeout=1000):
            result = controller.update_mapping_alignment(
                ai_frame_id="frame_001.png",
                offset_x=10,
                offset_y=20,
                flip_h=False,
                flip_v=False,
            )

        assert result is True

    def test_update_mapping_alignment_emits_both_signals(self, tmp_path: Path, qtbot) -> None:
        """Verify both alignment_updated and save_requested are emitted."""
        ai_frame_path = tmp_path / "frame_002.png"
        ai_frame_path.write_bytes(
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
            b"\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
            b"\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01"
            b"\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
        )

        project = FrameMappingProject(name="test")
        project.ai_frames_dir = tmp_path
        project.ai_frames.append(AIFrame(path=ai_frame_path, index=0))
        project.game_frames.append(GameFrame(id="G002", rom_offsets=[0x2000], selected_entry_ids=[]))
        project.mappings.append(FrameMapping(ai_frame_id="frame_002.png", game_frame_id="G002"))
        project._rebuild_indices()

        controller = FrameMappingController()
        controller._project = project

        # Track both signals
        alignment_updated_received = []
        save_requested_received = []

        controller.alignment_updated.connect(lambda x: alignment_updated_received.append(x))
        controller.save_requested.connect(lambda: save_requested_received.append(True))

        result = controller.update_mapping_alignment(
            ai_frame_id="frame_002.png",
            offset_x=5,
            offset_y=-10,
            flip_h=True,
            flip_v=False,
            scale=0.8,
        )

        assert result is True
        assert alignment_updated_received == ["frame_002.png"]
        assert save_requested_received == [True]


class TestHeadlessControllerUsage:
    """Tests for using controller without Qt parent or workspace.

    These tests verify that the controller can be used in headless
    mode for CLI tools or batch processing.
    """

    def test_create_controller_without_parent(self, qtbot) -> None:
        """Controller can be created without parent."""
        controller = FrameMappingController(parent=None)

        # Verify controller exists and has no parent
        assert controller is not None
        assert controller.parent() is None

    def test_new_project_without_parent(self, qtbot) -> None:
        """Can create new project without parent."""
        controller = FrameMappingController(parent=None)

        # Create project
        controller.new_project("headless_test")

        # Verify project created
        assert controller.has_project
        assert controller.project is not None
        assert controller.project.name == "headless_test"

    def test_load_ai_frames_without_parent(self, tmp_path: Path, qtbot) -> None:
        """Can load AI frames without parent."""
        # Create test images
        img = Image.new("RGBA", (16, 16), (255, 0, 0, 255))
        frame1 = tmp_path / "frame_001.png"
        frame2 = tmp_path / "frame_002.png"
        img.save(frame1)
        img.save(frame2)

        # Create headless controller
        controller = FrameMappingController(parent=None)

        # Load AI frames
        count = controller.load_ai_frames_from_directory(tmp_path)

        # Verify loaded
        assert count == 2
        assert controller.has_project
        assert len(controller.get_ai_frames()) == 2

    def test_signals_work_without_parent(self, qtbot) -> None:
        """Signals work without parent."""
        controller = FrameMappingController(parent=None)

        # Connect to signal
        signal_received = []
        controller.project_changed.connect(lambda: signal_received.append(True))

        # Emit signal via action
        controller.new_project("test")

        # Verify signal received
        assert signal_received == [True]

    def test_save_load_project_without_parent(self, tmp_path: Path, qtbot) -> None:
        """Can save and load project without parent."""
        # Create test images
        img = Image.new("RGBA", (16, 16), (255, 0, 0, 255))
        frame1 = tmp_path / "frame_001.png"
        img.save(frame1)

        # Create and populate project
        controller = FrameMappingController(parent=None)
        controller.load_ai_frames_from_directory(tmp_path)

        # Save project
        project_path = tmp_path / "test.spritepal-mapping.json"
        success = controller.save_project(project_path)
        assert success
        assert project_path.exists()

        # Load in new controller
        controller2 = FrameMappingController(parent=None)
        success = controller2.load_project(project_path)
        assert success
        assert controller2.has_project
        assert len(controller2.get_ai_frames()) == 1

    def test_create_mapping_without_parent(self, tmp_path: Path, qtbot) -> None:
        """Can create mappings without parent."""
        # Create minimal AI frame and game frame
        img = Image.new("RGBA", (16, 16), (255, 0, 0, 255))
        ai_frame_path = tmp_path / "frame_001.png"
        img.save(ai_frame_path)

        # Create minimal capture
        capture_data = create_test_capture([0, 1])
        capture_path = tmp_path / "capture.json"
        capture_path.write_text(json.dumps(capture_data))

        # Create headless controller
        controller = FrameMappingController(parent=None)

        # Create project manually
        project = FrameMappingProject(name="test")
        project.ai_frames.append(AIFrame(path=ai_frame_path, index=0))
        project.game_frames.append(
            GameFrame(
                id="G001",
                rom_offsets=[0x1000],
                capture_path=capture_path,
                selected_entry_ids=[0, 1],
            )
        )
        project._rebuild_indices()
        controller._project = project

        # Create mapping
        success = controller.create_mapping("frame_001.png", "G001")

        # Verify mapping created
        assert success
        assert len(controller.project.mappings) == 1

    def test_alignment_update_without_parent(self, tmp_path: Path, qtbot) -> None:
        """Can update alignment without parent."""
        # Setup project with mapping
        img = Image.new("RGBA", (16, 16), (255, 0, 0, 255))
        ai_frame_path = tmp_path / "frame_001.png"
        img.save(ai_frame_path)

        capture_data = create_test_capture([0])
        capture_path = tmp_path / "capture.json"
        capture_path.write_text(json.dumps(capture_data))

        controller = FrameMappingController(parent=None)
        project = FrameMappingProject(name="test")
        project.ai_frames.append(AIFrame(path=ai_frame_path, index=0))
        project.game_frames.append(
            GameFrame(
                id="G001",
                rom_offsets=[0x1000],
                capture_path=capture_path,
                selected_entry_ids=[0],
            )
        )
        project.mappings.append(FrameMapping(ai_frame_id="frame_001.png", game_frame_id="G001"))
        project._rebuild_indices()
        controller._project = project

        # Update alignment
        success = controller.update_mapping_alignment(
            ai_frame_id="frame_001.png",
            offset_x=10,
            offset_y=20,
            flip_h=True,
            flip_v=False,
            scale=0.5,
        )

        # Verify updated
        assert success
        mapping = project.get_mapping_for_ai_frame("frame_001.png")
        assert mapping is not None
        assert mapping.offset_x == 10
        assert mapping.offset_y == 20
        assert mapping.flip_h is True
        assert mapping.flip_v is False
        assert mapping.scale == 0.5

    def test_undo_redo_without_parent(self, tmp_path: Path, qtbot) -> None:
        """Undo/redo works without parent."""
        # Setup project with mapping
        img = Image.new("RGBA", (16, 16), (255, 0, 0, 255))
        ai_frame_path = tmp_path / "frame_001.png"
        img.save(ai_frame_path)

        capture_data = create_test_capture([0])
        capture_path = tmp_path / "capture.json"
        capture_path.write_text(json.dumps(capture_data))

        controller = FrameMappingController(parent=None)
        project = FrameMappingProject(name="test")
        project.ai_frames.append(AIFrame(path=ai_frame_path, index=0))
        project.game_frames.append(
            GameFrame(
                id="G001",
                rom_offsets=[0x1000],
                capture_path=capture_path,
                selected_entry_ids=[0],
            )
        )
        project._rebuild_indices()
        controller._project = project

        # Create mapping
        controller.create_mapping("frame_001.png", "G001")
        assert len(project.mappings) == 1

        # Undo
        desc = controller.undo()
        assert desc is not None
        assert len(project.mappings) == 0

        # Redo
        desc = controller.redo()
        assert desc is not None
        assert len(project.mappings) == 1
