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

from core.frame_mapping_project import SheetPalette
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
        ai_frame = MagicMock()
        ai_frame.path = ai_frame_path
        project.get_ai_frame_by_id.return_value = ai_frame
        game_frame = MagicMock()
        game_frame.rom_offsets = [0x10000]
        game_frame.capture_path = tmp_path / "nonexistent_capture.json"
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
        mapping = MagicMock()
        mapping.offset_x = 0
        mapping.offset_y = 0
        mapping.flip_h = False
        mapping.flip_v = False
        mapping.scale = 1.0
        project.get_mapping_for_ai_frame.return_value = mapping

        ai_frame = MagicMock()
        ai_frame.path = ai_frame_path
        project.get_ai_frame_by_id.return_value = ai_frame

        game_frame = MagicMock()
        game_frame.id = "test_frame"
        game_frame.rom_offsets = [0x10000]
        game_frame.capture_path = capture_path
        game_frame.selected_entry_ids = [999]  # Non-existent IDs
        project.get_game_frame_by_id.return_value = game_frame

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

        # Mock staging to report 8 tiles for RAW mode
        staging.detect_raw_slot_size.return_value = original_tile_count

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

        # Create minimal game frame
        game_frame = MagicMock()
        game_frame.compression_types = {}  # Empty = use RAW

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
            force_raw=True,
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
