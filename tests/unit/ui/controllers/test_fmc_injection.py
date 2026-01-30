"""Tests for FrameMappingController injection operations.

Covers flip handling, scale transforms, compression type selection,
and preserve_existing parameter.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image

from core.frame_mapping_project import AIFrame, FrameMapping, FrameMappingProject, GameFrame
from core.services.rom_verification_service import ROMVerificationResult
from tests.fixtures.frame_mapping_helpers import create_test_capture
from ui.frame_mapping.controllers.frame_mapping_controller import FrameMappingController


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
        """With flip_h=True, tile at pos_x=0 should appear at right edge."""
        from tests.infrastructure.injection_test_helpers import InjectingMockROMInjector

        capture_data = create_flipped_capture(entry_id=1, flip_h=True, flip_v=False)
        capture_path = tmp_path / "capture.json"
        capture_path.write_text(json.dumps(capture_data))

        # Create AI frame with distinct quadrants
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

        mock_verification = ROMVerificationResult(
            corrections={0x100000: 0x100000},
            matched_hal=4,
            matched_raw=0,
            not_found=0,
            total=4,
        )
        mock_verifier = MagicMock()
        mock_verifier.verify_offsets.return_value = mock_verification
        mock_verifier.apply_corrections.return_value = 0

        mock_injector = InjectingMockROMInjector(tile_count=4)

        controller = FrameMappingController()
        controller._project = project
        controller._injection_orchestrator._rom_injector = mock_injector

        with (
            patch.object(controller, "create_injection_copy", return_value=tmp_path / "out.sfc"),
            patch(
                "core.services.injection_orchestrator.ROMVerificationService",
                return_value=mock_verifier,
            ),
        ):
            rom_path = tmp_path / "test.sfc"
            rom_path.write_bytes(b"\x00" * 0x200000)
            (tmp_path / "out.sfc").write_bytes(b"\x00" * 0x200000)

            controller.inject_mapping("ai_frame.png", rom_path)

        assert len(mock_injector.injected_images) >= 1, "Expected at least one injection"

        img = mock_injector.last_injected_image
        assert img is not None
        if img.mode != "RGBA":
            img = img.convert("RGBA")

        center_pixel = img.getpixel((4, 4))
        is_green = center_pixel[1] > center_pixel[0] and center_pixel[1] > center_pixel[2]

        assert is_green, (
            f"With flip_h=True, tile at pos_x=0 should extract from canvas x=8 (green quadrant), "
            f"but center pixel was {center_pixel}. Position calculation ignores flip_h."
        )

    def test_tile_data_counter_flipped_for_flip_h(self, tmp_path: Path, qtbot) -> None:
        """Extracted tiles must be counter-flipped before ROM injection."""
        from tests.infrastructure.injection_test_helpers import InjectingMockROMInjector

        capture_data = create_flipped_capture(entry_id=1, flip_h=True, flip_v=False, width=8, height=8)
        capture_path = tmp_path / "capture.json"
        capture_path.write_text(json.dumps(capture_data))

        ai_frame_path = tmp_path / "ai_frame.png"
        ai_img = Image.new("RGBA", (8, 8), (0, 0, 0, 0))
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

        mock_verification = ROMVerificationResult(
            corrections={0x100000: 0x100000},
            matched_hal=1,
            matched_raw=0,
            not_found=0,
            total=1,
        )
        mock_verifier = MagicMock()
        mock_verifier.verify_offsets.return_value = mock_verification
        mock_verifier.apply_corrections.return_value = 0

        mock_injector = InjectingMockROMInjector(tile_count=1)

        controller = FrameMappingController()
        controller._project = project
        controller._injection_orchestrator._rom_injector = mock_injector

        with (
            patch.object(controller, "create_injection_copy", return_value=tmp_path / "out.sfc"),
            patch(
                "core.services.injection_orchestrator.ROMVerificationService",
                return_value=mock_verifier,
            ),
        ):
            rom_path = tmp_path / "test.sfc"
            rom_path.write_bytes(b"\x00" * 0x200000)
            (tmp_path / "out.sfc").write_bytes(b"\x00" * 0x200000)

            controller.inject_mapping("ai_frame.png", rom_path)

        assert len(mock_injector.injected_images) >= 1, "Expected at least one injection"

        img = mock_injector.last_injected_image
        assert img is not None

        if img.mode != "RGBA":
            img = img.convert("RGBA")

        left_pixel = img.getpixel((0, 4))
        is_blue = left_pixel[2] > left_pixel[0]

        assert is_blue, (
            f"With flip_h=True, tile data should be counter-flipped before injection. "
            f"Left edge should be blue (counter-flipped), but got {left_pixel}. "
            f"Tile data not counter-flipped for flip_h."
        )


class TestInjectMappingScale:
    """Tests that inject_mapping applies scale transform to AI image."""

    def test_inject_mapping_applies_scale(self, tmp_path: Path, qtbot) -> None:
        """Injection should resize AI image when mapping.scale != 1.0."""
        from tests.infrastructure.injection_test_helpers import InjectingMockROMInjector

        capture_data = create_test_capture(entry_ids=[1])
        capture_path = tmp_path / "capture.json"
        capture_path.write_text(json.dumps(capture_data))

        ai_frame_path = tmp_path / "ai_frame.png"
        ai_img = Image.new("RGBA", (16, 16), (255, 0, 0, 255))
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
        project.mappings.append(
            FrameMapping(
                ai_frame_id="ai_frame.png",
                game_frame_id="F001",
                offset_x=0,
                offset_y=0,
                scale=0.5,
            )
        )
        project._rebuild_indices()

        mock_verification = ROMVerificationResult(
            corrections={0x100000: 0x100000},
            matched_hal=1,
            matched_raw=0,
            not_found=0,
            total=1,
        )
        mock_verifier = MagicMock()
        mock_verifier.verify_offsets.return_value = mock_verification
        mock_verifier.apply_corrections.return_value = 0

        mock_injector = InjectingMockROMInjector(tile_count=1)

        controller = FrameMappingController()
        controller._project = project
        controller._injection_orchestrator._rom_injector = mock_injector

        with (
            patch.object(controller, "create_injection_copy", return_value=tmp_path / "out.sfc"),
            patch(
                "core.services.injection_orchestrator.ROMVerificationService",
                return_value=mock_verifier,
            ),
        ):
            rom_path = tmp_path / "test.sfc"
            rom_path.write_bytes(b"\x00" * 0x200000)
            (tmp_path / "out.sfc").write_bytes(b"\x00" * 0x200000)

            controller.inject_mapping("ai_frame.png", rom_path)

        assert len(mock_injector.injected_images) >= 1, "Expected at least one injection"

        img = mock_injector.last_injected_image
        assert img is not None

        assert img.size == (8, 8), (
            f"AI image should be scaled to 8x8 (50% of 16x16) before injection, "
            f"but injected image size is {img.size}. Scale transform not applied."
        )


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
            result = controller.inject_mapping("ai_frame.png", rom_path, output_path=None)

        assert result is True
        # Since a fresh copy was created, preserve_existing should be False
        assert len(preserve_existing_values) == 1
        assert preserve_existing_values[0] is False
