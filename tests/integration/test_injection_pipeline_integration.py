"""Integration tests for the full injection pipeline.

Tests the complete flow: AI frame → composite → quantize → ROM injector,
using InjectingMockROMInjector to capture the final indexed image.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from core.frame_mapping_project import (
    AIFrame,
    CompressionType,
    FrameMapping,
    FrameMappingProject,
    GameFrame,
    SheetPalette,
)
from core.services.injection_orchestrator import InjectionOrchestrator
from core.services.injection_results import InjectionRequest
from tests.infrastructure.injection_test_helpers import InjectingMockROMInjector


def _make_16x16_capture(rom_offset: int) -> dict[str, object]:
    """Create a Mesen capture with a single 16x16 entry (4 tiles at same ROM offset)."""
    return {
        "frame": 1,
        "obsel": {},
        "entries": [
            {
                "id": 0,
                "x": 0,  # Simplified: start at 0,0 to avoid offset confusion
                "y": 0,
                "tile": 0,
                "width": 16,
                "height": 16,
                "palette": 7,
                "rom_offset": rom_offset,
                "tiles": [
                    {
                        "tile_index": i,
                        "vram_addr": 0x1000 + i * 0x20,
                        "pos_x": (i % 2),  # Tile position in 8x8 units: 0, 1, 0, 1
                        "pos_y": (i // 2),  # Tile position in 8x8 units: 0, 0, 1, 1
                        "data_hex": "00" * 32,
                        "rom_offset": rom_offset,
                        "tile_index_in_block": i,
                    }
                    for i in range(4)
                ],
            }
        ],
        "palettes": {
            "7": [[0, 0, 0]] * 16,
        },
    }


@pytest.mark.integration
class TestInjectionPipelineIntegration:
    """Integration tests for full injection pipeline."""

    def test_solid_color_frame_produces_correct_indexed_image(self, tmp_path: Path) -> None:
        """Test that a solid red AI frame produces an indexed image with all pixels at index 1."""
        # 1. Create 16x16 solid red AI frame (SNES-snapped color)
        ai_img = Image.new("RGBA", (16, 16), (248, 0, 0, 255))
        ai_path = tmp_path / "ai_frame.png"
        ai_img.save(ai_path)

        # 2. Create capture with 2x2 grid of 8x8 tiles (= 16x16 sprite)
        rom_offset = 0x100
        capture_data = _make_16x16_capture(rom_offset)
        capture_path = tmp_path / "capture.json"
        capture_path.write_text(json.dumps(capture_data))

        # 3. Create minimal ROM (needs data at rom_offset for decompression check)
        rom_path = tmp_path / "test.sfc"
        rom_data = bytearray(rom_offset + 1024)  # Enough space
        rom_path.write_bytes(bytes(rom_data))

        # 4. Set up sheet palette: index 0 = black (transparent), index 1 = red
        palette_colors = [(0, 0, 0), (248, 0, 0)] + [(0, 0, 0)] * 14
        sheet_palette = SheetPalette(colors=palette_colors)

        # 5. Create project with mapping
        project = FrameMappingProject(name="test")
        ai_frame = AIFrame(path=ai_path, index=0, width=16, height=16)
        game_frame = GameFrame(
            id="G001",
            capture_path=capture_path,
            rom_offsets=[rom_offset],
            palette_index=7,
            selected_entry_ids=[0],
            compression_types={rom_offset: CompressionType.RAW},
            width=16,
            height=16,
        )
        project.add_ai_frame(ai_frame)
        project.add_game_frame(game_frame)
        project.create_mapping(ai_frame.id, game_frame.id)
        project.sheet_palette = sheet_palette

        # 6. Create orchestrator with mock ROM injector
        mock_injector = InjectingMockROMInjector(tile_count=4)
        orchestrator = InjectionOrchestrator(rom_injector=mock_injector)

        # 7. Execute
        request = InjectionRequest(
            ai_frame_id=ai_frame.id,
            rom_path=rom_path,
            output_path=tmp_path / "output.sfc",
            create_backup=False,
        )
        result = orchestrator.execute(request, project)

        # 8. Verify
        assert result.success, f"Injection failed: {result.error}"
        assert len(mock_injector.injected_images) == 1

        injected = mock_injector.injected_images[0]
        assert injected.mode == "P", f"Expected indexed mode 'P', got {injected.mode}"

        # All pixels should be palette index 1 (red)
        pixels = np.array(injected)
        unique_values = np.unique(pixels)
        assert np.all(pixels == 1), f"Expected all pixels=1 (red), got unique values: {unique_values}"

    def test_transparent_pixels_map_to_index_zero(self, tmp_path: Path) -> None:
        """Test that transparent pixels map to index 0 and opaque pixels to index 1."""
        # 1. Create 16x16 image: top half red (opaque), bottom half transparent
        ai_img = Image.new("RGBA", (16, 16), (0, 0, 0, 0))
        # Fill top half with red
        for y in range(8):
            for x in range(16):
                ai_img.putpixel((x, y), (248, 0, 0, 255))
        ai_path = tmp_path / "ai_frame.png"
        ai_img.save(ai_path)

        # 2. Create capture
        rom_offset = 0x100
        capture_data = _make_16x16_capture(rom_offset)
        capture_path = tmp_path / "capture.json"
        capture_path.write_text(json.dumps(capture_data))

        # 3. Create minimal ROM
        rom_path = tmp_path / "test.sfc"
        rom_data = bytearray(rom_offset + 1024)
        rom_path.write_bytes(bytes(rom_data))

        # 4. Set up sheet palette
        palette_colors = [(0, 0, 0), (248, 0, 0)] + [(0, 0, 0)] * 14
        sheet_palette = SheetPalette(colors=palette_colors)

        # 5. Create project with mapping
        project = FrameMappingProject(name="test")
        ai_frame = AIFrame(path=ai_path, index=0, width=16, height=16)
        game_frame = GameFrame(
            id="G001",
            capture_path=capture_path,
            rom_offsets=[rom_offset],
            palette_index=7,
            selected_entry_ids=[0],
            compression_types={rom_offset: CompressionType.RAW},
            width=16,
            height=16,
        )
        project.add_ai_frame(ai_frame)
        project.add_game_frame(game_frame)
        project.create_mapping(ai_frame.id, game_frame.id)
        project.sheet_palette = sheet_palette

        # 6. Create orchestrator with mock ROM injector
        mock_injector = InjectingMockROMInjector(tile_count=4)
        orchestrator = InjectionOrchestrator(rom_injector=mock_injector)

        # 7. Execute
        request = InjectionRequest(
            ai_frame_id=ai_frame.id,
            rom_path=rom_path,
            output_path=tmp_path / "output.sfc",
            create_backup=False,
        )
        result = orchestrator.execute(request, project)

        # 8. Verify
        assert result.success, f"Injection failed: {result.error}"
        assert len(mock_injector.injected_images) == 1

        injected = mock_injector.injected_images[0]
        assert injected.mode == "P"

        # Convert to numpy for easier checking
        pixels = np.array(injected)

        # Top half should be index 1 (red), bottom half should be index 0 (transparent)
        # The injected image is a 2x2 tile grid (16x16)
        top_half = pixels[:8, :]
        bottom_half = pixels[8:, :]

        # Check top half is all red (index 1)
        assert np.all(top_half == 1), f"Top half should be index 1, got unique values: {np.unique(top_half)}"

        # Check bottom half is all transparent (index 0)
        assert np.all(bottom_half == 0), f"Bottom half should be index 0, got unique values: {np.unique(bottom_half)}"

    def test_sheet_palette_color_mappings_override_nearest(self, tmp_path: Path) -> None:
        """Test that explicit color mappings override nearest-color matching."""
        # 1. Create 16x16 solid green AI frame
        # Green (0, 248, 0) is closest to palette index 2, but we'll map it to index 5
        ai_img = Image.new("RGBA", (16, 16), (0, 248, 0, 255))
        ai_path = tmp_path / "ai_frame.png"
        ai_img.save(ai_path)

        # 2. Create capture
        rom_offset = 0x100
        capture_data = _make_16x16_capture(rom_offset)
        capture_path = tmp_path / "capture.json"
        capture_path.write_text(json.dumps(capture_data))

        # 3. Create minimal ROM
        rom_path = tmp_path / "test.sfc"
        rom_data = bytearray(rom_offset + 1024)
        rom_path.write_bytes(bytes(rom_data))

        # 4. Set up sheet palette with color mapping override
        # Index 0 = black (transparent)
        # Index 2 = green (closest match by distance)
        # Index 5 = yellow (override target)
        palette_colors = [
            (0, 0, 0),  # 0: transparent
            (248, 0, 0),  # 1: red
            (0, 248, 0),  # 2: green (naturally closest)
            (0, 0, 248),  # 3: blue
            (248, 248, 0),  # 4: yellow
            (248, 128, 0),  # 5: orange (override target)
        ] + [(0, 0, 0)] * 10

        # Explicit mapping: (0, 248, 0) -> index 5 (not index 2)
        color_mappings = {(0, 248, 0): 5}
        sheet_palette = SheetPalette(colors=palette_colors, color_mappings=color_mappings)

        # 5. Create project with mapping
        project = FrameMappingProject(name="test")
        ai_frame = AIFrame(path=ai_path, index=0, width=16, height=16)
        game_frame = GameFrame(
            id="G001",
            capture_path=capture_path,
            rom_offsets=[rom_offset],
            palette_index=7,
            selected_entry_ids=[0],
            compression_types={rom_offset: CompressionType.RAW},
            width=16,
            height=16,
        )
        project.add_ai_frame(ai_frame)
        project.add_game_frame(game_frame)
        project.create_mapping(ai_frame.id, game_frame.id)
        project.sheet_palette = sheet_palette

        # 6. Create orchestrator with mock ROM injector
        mock_injector = InjectingMockROMInjector(tile_count=4)
        orchestrator = InjectionOrchestrator(rom_injector=mock_injector)

        # 7. Execute
        request = InjectionRequest(
            ai_frame_id=ai_frame.id,
            rom_path=rom_path,
            output_path=tmp_path / "output.sfc",
            create_backup=False,
        )
        result = orchestrator.execute(request, project)

        # 8. Verify
        assert result.success, f"Injection failed: {result.error}"
        assert len(mock_injector.injected_images) == 1

        injected = mock_injector.injected_images[0]
        assert injected.mode == "P"

        # All pixels should be palette index 5 (override), not index 2 (nearest)
        pixels = np.array(injected)
        unique_values = np.unique(pixels)
        assert np.all(pixels == 5), f"Expected all pixels=5 (override to orange), got unique values: {unique_values}"
