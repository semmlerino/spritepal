"""Tests for InjectionOrchestrator.

These tests focus on the orchestrator's error handling and flow control.
Full integration tests are in tests/ui/integration/.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
from PIL import Image

from core.frame_mapping_project import AIFrame, FrameMapping, GameFrame, SheetPalette
from core.services.injection_debug_context import InjectionDebugContext
from core.services.injection_orchestrator import InjectionOrchestrator
from core.services.injection_results import InjectionRequest, InjectionResult
from core.services.rom_staging_manager import ROMStagingManager


class TestInjectionOrchestratorInit:
    """Tests for InjectionOrchestrator initialization."""

    def test_default_dependencies(self) -> None:
        """Creates default dependencies if not provided."""
        orchestrator = InjectionOrchestrator()
        assert orchestrator._staging_manager is not None
        assert orchestrator._rom_injector is not None

    def test_custom_dependencies(self) -> None:
        """Accepts custom dependencies."""
        staging = ROMStagingManager()
        mock_injector = MagicMock()

        orchestrator = InjectionOrchestrator(
            staging_manager=staging,
            rom_injector=mock_injector,
        )
        assert orchestrator._staging_manager is staging
        assert orchestrator._rom_injector is mock_injector


class TestInjectionOrchestratorValidation:
    """Tests for InjectionOrchestrator validation."""

    def test_validates_mapping_exists(self, tmp_path: Path) -> None:
        """Returns failure if AI frame is not mapped."""
        rom_path = tmp_path / "game.sfc"
        rom_path.write_bytes(b"ROM")

        # Mock project with no mapping
        project = MagicMock()
        project.get_mapping_for_ai_frame.return_value = None

        orchestrator = InjectionOrchestrator()
        request = InjectionRequest(ai_frame_id="frame_5.png", rom_path=rom_path)

        result = orchestrator.execute(request, project)

        assert result.success is False
        assert "not mapped" in result.error.lower()  # type: ignore[union-attr]

    def test_validates_ai_frame_exists(self, tmp_path: Path) -> None:
        """Returns failure if AI frame doesn't exist."""
        rom_path = tmp_path / "game.sfc"
        rom_path.write_bytes(b"ROM")

        # Mock project with mapping but missing AI frame
        project = MagicMock()
        project.get_mapping_for_ai_frame.return_value = MagicMock()
        project.get_ai_frame_by_id.return_value = None
        project.get_game_frame_by_id.return_value = MagicMock()

        orchestrator = InjectionOrchestrator()
        request = InjectionRequest(ai_frame_id="frame_0.png", rom_path=rom_path)

        result = orchestrator.execute(request, project)

        assert result.success is False
        assert "missing" in result.error.lower()  # type: ignore[union-attr]

    def test_validates_game_frame_exists(self, tmp_path: Path) -> None:
        """Returns failure if game frame doesn't exist."""
        rom_path = tmp_path / "game.sfc"
        rom_path.write_bytes(b"ROM")

        project = MagicMock()
        project.get_mapping_for_ai_frame.return_value = MagicMock()
        project.get_ai_frame_by_id.return_value = MagicMock()
        project.get_game_frame_by_id.return_value = None

        orchestrator = InjectionOrchestrator()
        request = InjectionRequest(ai_frame_id="frame_0.png", rom_path=rom_path)

        result = orchestrator.execute(request, project)

        assert result.success is False
        assert "missing" in result.error.lower()  # type: ignore[union-attr]

    def test_validates_rom_path_exists(self, tmp_path: Path) -> None:
        """Returns failure if ROM file doesn't exist."""
        nonexistent_rom = tmp_path / "nonexistent.sfc"

        project = MagicMock()
        project.get_mapping_for_ai_frame.return_value = MagicMock()
        ai_frame = MagicMock()
        ai_frame.path.exists.return_value = True
        project.get_ai_frame_by_id.return_value = ai_frame
        game_frame = MagicMock()
        game_frame.rom_offsets = [0x10000]
        game_frame.capture_path = tmp_path / "capture.json"
        project.get_game_frame_by_id.return_value = game_frame

        orchestrator = InjectionOrchestrator()
        request = InjectionRequest(ai_frame_id="frame_0.png", rom_path=nonexistent_rom)

        result = orchestrator.execute(request, project)

        assert result.success is False
        assert "rom file not found" in result.error.lower()  # type: ignore[union-attr]

    def test_validates_rom_offsets_exist(self, tmp_path: Path) -> None:
        """Returns failure if game frame has no ROM offsets."""
        rom_path = tmp_path / "game.sfc"
        rom_path.write_bytes(b"ROM")

        project = MagicMock()
        project.get_mapping_for_ai_frame.return_value = MagicMock()
        ai_frame = MagicMock()
        ai_frame.path.exists.return_value = True
        project.get_ai_frame_by_id.return_value = ai_frame
        game_frame = MagicMock()
        game_frame.rom_offsets = []  # Empty
        project.get_game_frame_by_id.return_value = game_frame

        orchestrator = InjectionOrchestrator()
        request = InjectionRequest(ai_frame_id="frame_0.png", rom_path=rom_path)

        result = orchestrator.execute(request, project)

        assert result.success is False
        assert "no rom offsets" in result.error.lower()  # type: ignore[union-attr]

    def test_validates_capture_path_exists(self, tmp_path: Path) -> None:
        """Returns failure if capture file doesn't exist."""
        rom_path = tmp_path / "game.sfc"
        rom_path.write_bytes(b"ROM")
        ai_frame_path = tmp_path / "frame.png"
        ai_frame_path.write_bytes(b"PNG")

        project = MagicMock()
        project.get_mapping_for_ai_frame.return_value = MagicMock()
        ai_frame = AIFrame(path=ai_frame_path, index=0)
        project.get_ai_frame_by_id.return_value = ai_frame
        game_frame = GameFrame(id="test_frame", rom_offsets=[0x10000], capture_path=tmp_path / "nonexistent_capture.json")
        project.get_game_frame_by_id.return_value = game_frame

        orchestrator = InjectionOrchestrator()
        request = InjectionRequest(ai_frame_id="frame_0.png", rom_path=rom_path)

        result = orchestrator.execute(request, project)

        assert result.success is False
        assert "capture file missing" in result.error.lower()  # type: ignore[union-attr]


class TestInjectionOrchestratorProgressCallback:
    """Tests for progress callback behavior."""

    def test_progress_callback_invoked(self, tmp_path: Path) -> None:
        """Progress callback is called during execution."""
        rom_path = tmp_path / "game.sfc"
        rom_path.write_bytes(b"ROM")

        # Mock project that fails validation (simplest path)
        project = MagicMock()
        project.get_mapping_for_ai_frame.return_value = None

        progress_messages: list[str] = []

        def track_progress(msg: str) -> None:
            progress_messages.append(msg)

        orchestrator = InjectionOrchestrator()
        request = InjectionRequest(ai_frame_id="frame_0.png", rom_path=rom_path)

        orchestrator.execute(request, project, on_progress=track_progress)

        # Validation failure happens early, may not emit progress
        # This test ensures no crash with callback provided


class TestInjectionOrchestratorStaleEntries:
    """Tests for stale entry handling."""

    def test_stale_entries_without_fallback_returns_stale_result(self, tmp_path: Path) -> None:
        """Returns stale entries result when allow_fallback=False."""
        rom_path = tmp_path / "game.sfc"
        rom_path.write_bytes(b"ROM")
        ai_frame_path = tmp_path / "frame.png"
        # Create valid PNG image
        img = Image.new("RGBA", (8, 8), (255, 0, 0, 255))
        img.save(ai_frame_path)
        capture_path = tmp_path / "capture.json"
        capture_path.write_text('{"frame": 1, "entries": [], "palettes": {}}')

        project = MagicMock()
        mapping = FrameMapping(ai_frame_id="frame_0.png", game_frame_id="test_frame")
        project.get_mapping_for_ai_frame.return_value = mapping

        ai_frame = AIFrame(path=ai_frame_path, index=0)
        project.get_ai_frame_by_id.return_value = ai_frame

        game_frame = GameFrame(id="test_frame", rom_offsets=[0x10000], capture_path=capture_path, selected_entry_ids=[999])
        project.get_game_frame_by_id.return_value = game_frame
        project.sheet_palette = None

        orchestrator = InjectionOrchestrator()
        request = InjectionRequest(
            ai_frame_id="frame_0.png",
            rom_path=rom_path,
            allow_fallback=False,  # Don't allow fallback
        )

        result = orchestrator.execute(request, project)

        assert result.success is False
        assert result.needs_fallback_confirmation is True
        assert result.stale_frame_id == "test_frame"


class TestInjectionOrchestratorROMCopyCreation:
    """Tests for ROM copy creation logic."""

    def test_creates_injection_copy_when_no_output_path(self, tmp_path: Path) -> None:
        """Creates numbered injection copy when no output_path provided."""
        rom_path = tmp_path / "game.sfc"
        rom_path.write_bytes(b"ROM DATA")

        # Mock project that fails validation early
        project = MagicMock()
        project.get_mapping_for_ai_frame.return_value = None

        orchestrator = InjectionOrchestrator()
        request = InjectionRequest(ai_frame_id="frame_0.png", rom_path=rom_path)

        # This will fail at validation, before ROM copy
        result = orchestrator.execute(request, project)

        assert result.success is False


class TestInjectionOrchestratorResultFactory:
    """Tests for InjectionResult factory methods."""

    def test_failure_factory(self) -> None:
        """InjectionResult.failure creates proper failure result."""
        result = InjectionResult.failure("Test error message")

        assert result.success is False
        assert result.error == "Test error message"
        assert result.tile_results == ()
        assert result.messages == ()

    def test_stale_entries_factory(self) -> None:
        """InjectionResult.stale_entries creates proper stale result."""
        result = InjectionResult.stale_entries("frame_id", "Error message")

        assert result.success is False
        assert result.needs_fallback_confirmation is True
        assert result.stale_frame_id == "frame_id"
        assert result.error == "Error message"


class TestInjectionOrchestratorTilePadding:
    """Tests for VRAM tile padding behavior."""

    def test_inject_tile_group_pads_to_original_count(self, tmp_path: Path) -> None:
        """When captured tiles < original tiles, pads image to original size.

        This prevents VRAM "ghost" artifacts where old tile data isn't overwritten.

        NOTE: Padding only applies to HAL-compressed blocks where multiple tiles
        share one ROM offset. For RAW tiles (each at its own offset), no padding
        is done to avoid overwriting adjacent tiles.
        """
        import math

        # Create orchestrator with mocked dependencies
        staging = MagicMock()
        rom_injector = MagicMock()

        orchestrator = InjectionOrchestrator(
            staging_manager=staging,
            rom_injector=rom_injector,
        )

        # Setup: 4 captured tiles, but ROM has 8 tiles originally
        captured_tile_count = 4
        original_tile_count = 8

        # Mock rom_injector.find_compressed_sprite to return original tile count for HAL
        rom_injector.find_compressed_sprite.return_value = (
            b"\x00" * 100,  # compressed data
            b"\x00" * (original_tile_count * 32),  # decompressed: 8 tiles * 32 bytes
            100,
        )

        # Mock rom_injector.inject_sprite_to_rom to capture the image being injected
        injected_images: list[Path] = []

        def capture_injection(
            sprite_path: str,
            rom_path: str,
            output_path: str,
            sprite_offset: int,
            **kwargs: object,
        ) -> tuple[bool, str]:
            # Save the path for later inspection
            injected_images.append(Path(sprite_path))
            # Read and verify the image dimensions before it gets deleted
            img = Image.open(sprite_path)
            # Store dimensions on the mock for assertions
            rom_injector._last_injected_size = img.size
            rom_injector._last_injected_image = img.copy()
            return (True, "Success")

        rom_injector.inject_sprite_to_rom.side_effect = capture_injection

        # Create 4 fake VRAM tiles at positions forming a 2x2 grid
        vram_tiles: dict[int, tuple[int, int, int, int | None, bool, bool]] = {
            0x1000: (0, 0, 0, 0, False, False),  # tile 0 at (0,0)
            0x1020: (8, 0, 0, 1, False, False),  # tile 1 at (8,0)
            0x1040: (0, 8, 0, 2, False, False),  # tile 2 at (0,8)
            0x1060: (8, 8, 0, 3, False, False),  # tile 3 at (8,8)
        }

        # Create a 16x16 masked canvas with some visible content
        masked_canvas = Image.new("RGBA", (16, 16), (255, 0, 0, 255))

        # Create minimal bounding box
        bbox = SimpleNamespace(x=0, y=0, width=16, height=16)

        # Create minimal filtered capture
        filtered_capture = SimpleNamespace(
            entries=[],
            palettes={0: [(31, 0, 0)] * 16},  # Red palette
        )

        # Create minimal project with sheet palette
        project = MagicMock()
        project.sheet_palette = SheetPalette(
            colors=[(0, 0, 0), (255, 0, 0), (0, 255, 0), (0, 0, 255)] + [(0, 0, 0)] * 12,
        )

        # Create minimal game frame with HAL compression
        game_frame = MagicMock()
        game_frame.compression_types = {0x50000: "hal"}  # Use HAL compression

        # Create debug context (disabled)
        debug = InjectionDebugContext(enabled=False)

        # Call the method
        rom_offset = 0x50000
        result = orchestrator._inject_tile_group(
            rom_offset=rom_offset,
            vram_tiles=vram_tiles,
            masked_canvas=masked_canvas,
            filtered_capture=filtered_capture,
            bbox=bbox,
            project=project,
            game_frame=game_frame,
            rom_data=b"\x00" * 0x100000,  # Dummy ROM data
            force_raw=False,  # Use HAL compression for padding test
            current_rom_path=str(tmp_path / "output.sfc"),
            source_rom_path=str(tmp_path / "source.sfc"),
            create_backup=False,
            preserve_existing=False,
            debug=debug,
        )

        # Verify result
        assert result.success is True

        # Key assertion: The injected image should be sized for 8 tiles, not 4
        # Grid for 8 tiles: ceil(sqrt(8)) = 3 width, ceil(8/3) = 3 height = 3x3 grid
        expected_grid_width = math.ceil(math.sqrt(original_tile_count))
        expected_grid_height = math.ceil(original_tile_count / expected_grid_width)
        expected_size = (expected_grid_width * 8, expected_grid_height * 8)

        actual_size = rom_injector._last_injected_size
        assert actual_size == expected_size, (
            f"Image should be sized for {original_tile_count} tiles "
            f"(expected {expected_size}), got {actual_size} "
            f"(which is for {captured_tile_count} tiles)"
        )

    def test_padded_tiles_preserve_position(self, tmp_path: Path) -> None:
        """HAL-compressed tiles are placed at their tile_index_in_block, not sequential idx.

        This prevents the "preserve_sprite leak" bug where AI tiles end up at
        wrong positions in padded slots, causing original sprite data to bleed through.

        NOTE: This only applies to HAL-compressed blocks where multiple tiles share
        one ROM offset. For RAW tiles (each at its own offset), sequential placement is used.
        """
        # Create orchestrator with mocked dependencies
        staging = MagicMock()
        rom_injector = MagicMock()

        orchestrator = InjectionOrchestrator(
            staging_manager=staging,
            rom_injector=rom_injector,
        )

        # Setup: 1 captured tile at tile_index_in_block=2, but ROM has 3 tiles
        # The tile should end up at grid position 2, NOT position 0
        original_tile_count = 3

        # Mock rom_injector.find_compressed_sprite to return original tile count for HAL
        # Returns: (compressed_data, decompressed_data, data_length)
        rom_injector.find_compressed_sprite.return_value = (
            b"\x00" * 100,  # compressed data (irrelevant)
            b"\x00" * (original_tile_count * 32),  # decompressed: 3 tiles * 32 bytes
            100,  # compressed length
        )

        # Mock rom_injector to capture the injected image
        def capture_injection(
            sprite_path: str,
            rom_path: str,
            output_path: str,
            sprite_offset: int,
            **kwargs: object,
        ) -> tuple[bool, str]:
            img = Image.open(sprite_path)
            rom_injector._last_injected_image = img.copy()
            return (True, "Success")

        rom_injector.inject_sprite_to_rom.side_effect = capture_injection

        # Create 1 VRAM tile at tile_index_in_block=2 (third tile in slot)
        # This simulates capturing only one tile from a 3-tile sprite
        vram_tiles: dict[int, tuple[int, int, int, int | None, bool, bool]] = {
            # (screen_x, screen_y, palette_idx, tile_index_in_block, flip_h, flip_v)
            0x1000: (0, 0, 0, 2, False, False),  # tile at index 2
        }

        # Create a canvas with distinct red content at (0,0)
        masked_canvas = Image.new("RGBA", (8, 8), (255, 0, 0, 255))

        bbox = SimpleNamespace(x=0, y=0, width=8, height=8)

        filtered_capture = SimpleNamespace(
            entries=[],
            palettes={0: [(31, 0, 0)] * 16},
        )

        project = MagicMock()
        project.sheet_palette = SheetPalette(
            colors=[(0, 0, 0), (255, 0, 0)] + [(0, 0, 0)] * 14,
        )

        game_frame = MagicMock()
        # Mark this ROM offset as HAL compressed
        game_frame.compression_types = {0x50000: "hal"}

        debug = InjectionDebugContext(enabled=False)

        # Call the method with force_raw=False to use HAL compression
        result = orchestrator._inject_tile_group(
            rom_offset=0x50000,
            vram_tiles=vram_tiles,
            masked_canvas=masked_canvas,
            filtered_capture=filtered_capture,
            bbox=bbox,
            project=project,
            game_frame=game_frame,
            rom_data=b"\x00" * 0x100000,
            force_raw=False,  # Use HAL compression
            current_rom_path=str(tmp_path / "output.sfc"),
            source_rom_path=str(tmp_path / "source.sfc"),
            create_backup=False,
            preserve_existing=False,
            debug=debug,
        )

        assert result.success is True

        # Get the injected image (should be a 2x2 grid for 3 tiles)
        img = rom_injector._last_injected_image
        # Grid for 3 tiles: ceil(sqrt(3))=2 width, ceil(3/2)=2 height = 16x16 pixels
        assert img.size == (16, 16), f"Expected 16x16 for 3 tiles, got {img.size}"

        # The key assertion: our red tile should be at position 2 (grid coords 0,8),
        # NOT at position 0 (grid coords 0,0) which is where idx=0 would place it
        #
        # Grid layout for 3 tiles in 2x2 grid:
        # | pos 0 (0,0) | pos 1 (8,0) |
        # | pos 2 (0,8) | pos 3 (8,8) |
        #
        # For palette mode images, index 0 = black, index 1 = red
        # Transparent areas get quantized to palette index 0 (black)
        # Our red tile content should be palette index 1

        if img.mode == "P":
            # Check palette indices directly
            pixel_idx_pos0 = img.getpixel((0, 0))  # Position 0 - should be transparent (index 0)
            pixel_idx_pos2 = img.getpixel((0, 8))  # Position 2 - should be red (index 1)

            assert pixel_idx_pos0 == 0, (
                f"Position 0 should be transparent (palette index 0), but got index {pixel_idx_pos0}. "
                "Bug: tile placed at idx position instead of tile_index_in_block"
            )

            assert pixel_idx_pos2 == 1, (
                f"Position 2 should have red tile (palette index 1), but got index {pixel_idx_pos2}. "
                "Bug: tile_index_in_block not used for placement"
            )
        else:
            # RGBA mode - check colors directly
            img_rgba = img.convert("RGBA") if img.mode != "RGBA" else img
            pixel_pos0 = img_rgba.getpixel((0, 0))
            pixel_pos2 = img_rgba.getpixel((0, 8))

            # Position 0 should be transparent or black (not red)
            assert pixel_pos0[0] < 128, (
                f"Position 0 should not be red, but got {pixel_pos0}. "
                "Bug: tile placed at idx position instead of tile_index_in_block"
            )

            # Position 2 should be red (our tile)
            assert pixel_pos2[0] > 128, (
                f"Position 2 should be red (our tile), but got {pixel_pos2}. "
                "Bug: tile_index_in_block not used for placement"
            )


class TestInjectionOrchestratorColorFidelity:
    """Tests for color fidelity between preview and injection."""

    def test_injection_snaps_palette_to_snes_colors(self, tmp_path: Path) -> None:
        """Injection uses same SNES-snapped palette as preview.

        Regression test for preview-to-ROM color fidelity bug where injection
        used unsnapped palette colors while preview snapped them to SNES-valid
        values, causing color mismatches between preview and ROM.
        """
        from core.palette_utils import snap_to_snes_color

        # Create orchestrator with mocked dependencies
        staging = MagicMock()
        rom_injector = MagicMock()

        orchestrator = InjectionOrchestrator(
            staging_manager=staging,
            rom_injector=rom_injector,
        )

        # Capture the palette passed to quantize_with_mappings
        captured_palettes: list[list[tuple[int, int, int]]] = []

        # Patch quantize_with_mappings in quantization_strategies module (where it's called)
        with patch("core.services.quantization_strategies.quantize_with_mappings") as mock_quantize:
            # Return a valid indexed image
            indexed_img = Image.new("P", (8, 8))
            indexed_img.putpalette([0] * 768)
            mock_quantize.return_value = indexed_img

            def capture_quantize(
                img: Image.Image,
                palette_rgb: list[tuple[int, int, int]],
                color_mappings: object = None,
                **kwargs: object,
            ) -> Image.Image:
                captured_palettes.append(list(palette_rgb))
                return indexed_img

            mock_quantize.side_effect = capture_quantize

            # Mock rom_injector.find_compressed_sprite for HAL compression
            rom_injector.find_compressed_sprite.return_value = (
                b"\x00" * 100,
                b"\x00" * 32,  # 1 tile
                100,
            )
            rom_injector.inject_sprite_to_rom.return_value = (True, "Success")

            # Non-SNES-valid colors (will be snapped to different values)
            non_snes_colors: list[tuple[int, int, int]] = [
                (0, 0, 0),  # Valid SNES color
                (10, 10, 10),  # Not valid - snaps to (8, 8, 8)
                (100, 100, 100),  # Not valid - snaps to (99, 99, 99)
                (200, 200, 200),  # Not valid - snaps to (206, 206, 206)
            ] + [(0, 0, 0)] * 12

            # Create minimal VRAM tiles
            vram_tiles: dict[int, tuple[int, int, int, int | None, bool, bool]] = {
                0x1000: (0, 0, 0, 0, False, False),
            }

            # Create canvas with some content
            masked_canvas = Image.new("RGBA", (8, 8), (255, 0, 0, 255))

            bbox = SimpleNamespace(x=0, y=0, width=8, height=8)

            filtered_capture = SimpleNamespace(
                entries=[],
                palettes={0: [(31, 0, 0)] * 16},
            )

            # Project with non-SNES-valid palette colors
            project = MagicMock()
            project.sheet_palette = SheetPalette(colors=non_snes_colors)

            game_frame = MagicMock()
            game_frame.compression_types = {0x50000: "hal"}

            debug = InjectionDebugContext(enabled=False)

            # Call the method
            orchestrator._inject_tile_group(
                rom_offset=0x50000,
                vram_tiles=vram_tiles,
                masked_canvas=masked_canvas,
                filtered_capture=filtered_capture,
                bbox=bbox,
                project=project,
                game_frame=game_frame,
                rom_data=b"\x00" * 0x100000,
                force_raw=False,
                current_rom_path=str(tmp_path / "output.sfc"),
                source_rom_path=str(tmp_path / "source.sfc"),
                create_backup=False,
                preserve_existing=False,
                debug=debug,
            )

        # Verify quantize_with_mappings was called
        assert len(captured_palettes) == 1, "quantize_with_mappings should be called once"

        # Key assertion: the palette passed to quantization should be SNES-snapped
        actual_palette = captured_palettes[0]
        expected_palette = [snap_to_snes_color(c) for c in non_snes_colors]

        for i, (actual, expected) in enumerate(zip(actual_palette, expected_palette, strict=True)):
            assert actual == expected, (
                f"Palette color {i} not snapped to SNES: "
                f"expected {expected}, got {actual}. "
                "Bug: injection not snapping palette colors like preview does."
            )


class TestInjectionOrchestratorPaletteInjection:
    """Tests for palette injection functionality."""

    def test_palette_injected_when_offset_provided(self, tmp_path: Path) -> None:
        """Palette is injected to ROM when palette_rom_offset is provided."""
        rom_path = tmp_path / "game.sfc"
        rom_path.write_bytes(b"ROM DATA")

        # Create mock dependencies
        staging = MagicMock()
        staging.create_injection_copy.return_value = tmp_path / "output.sfc"
        session = MagicMock()
        session.staging_path = tmp_path / "staging.sfc"
        staging.create_staging.return_value = session
        staging.commit.return_value = True

        rom_injector = MagicMock()
        rom_injector.inject_palette_to_rom.return_value = (True, "Palette injected")

        orchestrator = InjectionOrchestrator(
            staging_manager=staging,
            rom_injector=rom_injector,
        )

        # Mock project with palette
        project = MagicMock()
        project.sheet_palette = SheetPalette(
            colors=[(255, 0, 0)] * 16  # Red palette
        )

        # Mock _execute_injection to return success
        with (
            patch.object(
                orchestrator,
                "_execute_injection",
                return_value=InjectionResult(
                    success=True,
                    tile_results=(),
                    messages=("Tiles injected",),
                ),
            ),
            patch.object(
                orchestrator,
                "_validate_mapping",
                return_value=None,  # No validation error
            ),
            patch.object(
                orchestrator,
                "_prepare_images",
                return_value=(
                    Image.new("RGBA", (8, 8)),  # masked_canvas
                    MagicMock(),  # filtered_capture
                    [],  # relevant_entries
                    None,  # transformed_index_map
                ),
            ),
        ):
            request = InjectionRequest(
                ai_frame_id="frame_0.png",
                rom_path=rom_path,
                palette_rom_offset=0x467D6,  # Palette offset provided
            )

            # Mock required project methods
            mapping = MagicMock()
            mapping.game_frame_id = "test_frame"
            project.get_mapping_for_ai_frame.return_value = mapping
            ai_frame = MagicMock()
            ai_frame.path = tmp_path / "frame.png"
            ai_frame.index = 0
            project.get_ai_frame_by_id.return_value = ai_frame
            game_frame = MagicMock()
            game_frame.id = "test_frame"
            game_frame.rom_offsets = [0x10000]
            project.get_game_frame_by_id.return_value = game_frame

            result = orchestrator.execute(request, project)

        # Verify palette injection was called
        rom_injector.inject_palette_to_rom.assert_called_once()
        call_kwargs = rom_injector.inject_palette_to_rom.call_args
        assert call_kwargs[1]["palette_offset"] == 0x467D6
        assert len(call_kwargs[1]["colors"]) == 16

        # Verify success message includes palette injection
        assert result.success is True
        assert any("palette" in msg.lower() for msg in result.messages)

    def test_palette_not_injected_when_no_offset(self, tmp_path: Path) -> None:
        """Palette is not injected when palette_rom_offset is None."""
        rom_path = tmp_path / "game.sfc"
        rom_path.write_bytes(b"ROM DATA")

        staging = MagicMock()
        staging.create_injection_copy.return_value = tmp_path / "output.sfc"
        session = MagicMock()
        session.staging_path = tmp_path / "staging.sfc"
        staging.create_staging.return_value = session
        staging.commit.return_value = True

        rom_injector = MagicMock()

        orchestrator = InjectionOrchestrator(
            staging_manager=staging,
            rom_injector=rom_injector,
        )

        project = MagicMock()
        project.sheet_palette = SheetPalette(colors=[(255, 0, 0)] * 16)

        with (
            patch.object(
                orchestrator,
                "_execute_injection",
                return_value=InjectionResult(
                    success=True,
                    tile_results=(),
                    messages=("Tiles injected",),
                ),
            ),
            patch.object(
                orchestrator,
                "_validate_mapping",
                return_value=None,
            ),
            patch.object(
                orchestrator,
                "_prepare_images",
                return_value=(
                    Image.new("RGBA", (8, 8)),
                    MagicMock(),
                    [],
                    None,
                ),
            ),
        ):
            request = InjectionRequest(
                ai_frame_id="frame_0.png",
                rom_path=rom_path,
                palette_rom_offset=None,  # No palette offset
            )

            mapping = MagicMock()
            mapping.game_frame_id = "test_frame"
            project.get_mapping_for_ai_frame.return_value = mapping
            ai_frame = MagicMock()
            ai_frame.path = tmp_path / "frame.png"
            ai_frame.index = 0
            project.get_ai_frame_by_id.return_value = ai_frame
            game_frame = MagicMock()
            game_frame.id = "test_frame"
            game_frame.rom_offsets = [0x10000]
            project.get_game_frame_by_id.return_value = game_frame

            orchestrator.execute(request, project)

        # Verify palette injection was NOT called
        rom_injector.inject_palette_to_rom.assert_not_called()

    def test_palette_not_injected_when_no_sheet_palette(self, tmp_path: Path) -> None:
        """Palette is not injected when project has no sheet_palette."""
        rom_path = tmp_path / "game.sfc"
        rom_path.write_bytes(b"ROM DATA")

        staging = MagicMock()
        staging.create_injection_copy.return_value = tmp_path / "output.sfc"
        session = MagicMock()
        session.staging_path = tmp_path / "staging.sfc"
        staging.create_staging.return_value = session
        staging.commit.return_value = True

        rom_injector = MagicMock()

        orchestrator = InjectionOrchestrator(
            staging_manager=staging,
            rom_injector=rom_injector,
        )

        project = MagicMock()
        project.sheet_palette = None  # No sheet palette

        with (
            patch.object(
                orchestrator,
                "_execute_injection",
                return_value=InjectionResult(
                    success=True,
                    tile_results=(),
                    messages=("Tiles injected",),
                ),
            ),
            patch.object(
                orchestrator,
                "_validate_mapping",
                return_value=None,
            ),
            patch.object(
                orchestrator,
                "_prepare_images",
                return_value=(
                    Image.new("RGBA", (8, 8)),
                    MagicMock(),
                    [],
                    None,
                ),
            ),
        ):
            request = InjectionRequest(
                ai_frame_id="frame_0.png",
                rom_path=rom_path,
                palette_rom_offset=0x467D6,  # Offset provided but no palette
            )

            mapping = MagicMock()
            mapping.game_frame_id = "test_frame"
            project.get_mapping_for_ai_frame.return_value = mapping
            ai_frame = MagicMock()
            ai_frame.path = tmp_path / "frame.png"
            ai_frame.index = 0
            project.get_ai_frame_by_id.return_value = ai_frame
            game_frame = MagicMock()
            game_frame.id = "test_frame"
            game_frame.rom_offsets = [0x10000]
            project.get_game_frame_by_id.return_value = game_frame

            orchestrator.execute(request, project)

        # Verify palette injection was NOT called (no palette to inject)
        rom_injector.inject_palette_to_rom.assert_not_called()
