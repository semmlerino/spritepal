"""Tests for FrameMappingController RAW slot detection and injection.

Covers raw slot size detection by finding padding boundaries and
ensuring RAW injection respects detected slot sizes.
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


class TestRawSlotDetection:
    """Tests for RAW slot size detection."""

    def test_raw_slot_detection_finds_padding_boundary(self, qtbot) -> None:
        """Detects slot size by finding all-zero padding after tiles."""
        controller = FrameMappingController()

        # Create ROM data: 3 tiles of real data, then zero padding
        tile_data = b"\x12\x34" * 16  # Non-zero tile (32 bytes)
        padding = b"\x00" * 32  # Zero padding (32 bytes)
        rom_data = tile_data * 3 + padding + b"\xff" * 1000

        # Offset 0, no SMC header
        detected = controller._injection_orchestrator._staging_manager.detect_raw_slot_size(rom_data, 0)

        assert detected == 3, f"Expected 3 tiles, got {detected}"

    def test_raw_slot_detection_finds_ff_padding(self, qtbot) -> None:
        """Detects slot size by finding all-0xFF padding after tiles."""
        controller = FrameMappingController()

        # Create ROM data: 5 tiles of real data, then 0xFF padding
        tile_data = b"\xab\xcd" * 16  # Non-zero, non-FF tile (32 bytes)
        padding = b"\xff" * 32  # 0xFF padding (32 bytes)
        rom_data = tile_data * 5 + padding

        # Offset 0, no SMC header
        detected = controller._injection_orchestrator._staging_manager.detect_raw_slot_size(rom_data, 0)

        assert detected == 5, f"Expected 5 tiles, got {detected}"

    def test_raw_slot_detection_accounts_for_smc_header(self, qtbot) -> None:
        """Accounts for 512-byte SMC header when present."""
        controller = FrameMappingController()

        # Create ROM with SMC header: total size must be N * 0x8000 + 512
        # SMC header detection: len(rom_data) % 0x8000 == 512
        smc_header = b"\x00" * 512
        tile_data = b"\x12\x34" * 16  # Non-zero tile (32 bytes)
        padding = b"\x00" * 32

        # Make data portion so total = 32768 + 512 = 33280 (= 0x8200)
        # data_portion needs to be 32768 bytes
        data_portion = tile_data * 4 + padding + b"\xff" * (32768 - 4 * 32 - 32)
        rom_data = smc_header + data_portion

        assert len(rom_data) == 33280, f"ROM should be 33280 bytes, got {len(rom_data)}"
        assert len(rom_data) % 0x8000 == 512, "ROM should have SMC header"

        # Offset 0 (file offset, not accounting for header yet)
        # The method should add 512 for the SMC header and find tiles at actual offset 512
        detected = controller._injection_orchestrator._staging_manager.detect_raw_slot_size(rom_data, 0)

        assert detected == 4, f"Expected 4 tiles, got {detected}"

    def test_raw_slot_detection_returns_none_when_no_boundary(self, qtbot) -> None:
        """Returns None when no padding boundary is found within max_tiles."""
        controller = FrameMappingController()

        # Create ROM data: all non-zero, non-FF data
        tile_data = b"\x12\x34" * 16  # Non-zero tile (32 bytes)
        rom_data = tile_data * 300  # More than default max_tiles (256)

        detected = controller._injection_orchestrator._staging_manager.detect_raw_slot_size(rom_data, 0, max_tiles=10)

        assert detected is None, "Should return None when no boundary found"

    def test_raw_slot_detection_returns_none_for_invalid_offset(self, qtbot) -> None:
        """Returns None for out-of-bounds offset."""
        controller = FrameMappingController()

        rom_data = b"\x12" * 1000

        # Offset past end of ROM
        detected = controller._injection_orchestrator._staging_manager.detect_raw_slot_size(rom_data, 0x100000)

        assert detected is None, "Should return None for invalid offset"


class TestRawInjectionSlotRespect:
    """Tests that RAW injection respects detected slot size."""

    def test_raw_injection_respects_detected_slot_size(self, tmp_path: Path, qtbot) -> None:
        """RAW injection limits tiles to detected slot size.

        Scenario: Capture has 5 tiles, ROM slot only has room for 3.
        Expected: Only 3 tiles worth of data extracted from canvas.

        Note: The grid layout may use 2x2=4 slots for 3 tiles, but only
        3 vram_addrs are processed (the 4th slot is empty/transparent).
        """
        # Create capture with 5 entries (5 tiles)
        rom_offset = 0x100000
        capture_data = create_test_capture(
            entry_ids=[1, 2, 3, 4, 5],
            rom_offsets=[rom_offset] * 5,
        )
        capture_path = tmp_path / "capture.json"
        capture_path.write_text(json.dumps(capture_data))

        # Create AI frame image (larger than slot)
        ai_frame_path = tmp_path / "ai_frame.png"
        ai_img = Image.new("RGBA", (40, 8), (255, 0, 0, 255))  # 5 tiles wide
        ai_img.save(ai_frame_path)

        # Create ROM with 3-tile slot (then padding)
        tile_data = b"\x12\x34" * 16  # 32 bytes per tile
        padding = b"\x00" * 32
        # Ensure no SMC header for simplicity
        rom_content = b"\xff" * rom_offset + tile_data * 3 + padding + b"\xff" * 0x100000
        rom_path = tmp_path / "test.sfc"
        rom_path.write_bytes(rom_content)

        # Create project
        project = FrameMappingProject(name="test")
        project.ai_frames_dir = tmp_path
        project.ai_frames.append(AIFrame(path=ai_frame_path, index=0))
        project.add_game_frame(
            GameFrame(
                id="F001",
                capture_path=capture_path,
                rom_offsets=[rom_offset],
                selected_entry_ids=[1, 2, 3, 4, 5],
                compression_types={rom_offset: "raw"},  # Force RAW
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

        # Verify slot detection works correctly
        detected = controller._injection_orchestrator._staging_manager.detect_raw_slot_size(rom_content, rom_offset)
        assert detected == 3, f"Slot detection should find 3 tiles, got {detected}"

        def mock_inject(
            sprite_path,
            rom_path,
            output_path,
            sprite_offset,
            **kwargs,
        ):
            Path(output_path).write_bytes(Path(rom_path).read_bytes())
            return (True, "Success")

        # Mock verification to pass
        mock_verification = ROMVerificationResult(
            total=5,
            matched_hal=0,
            matched_raw=5,
            not_found=0,
            corrections={},
        )

        # Create mock injector and set it on the controller's orchestrator
        mock_injector = MagicMock()
        mock_injector.find_compressed_sprite.return_value = (0, b"\x00" * 32, 32)
        mock_injector.inject_sprite_to_rom.side_effect = mock_inject
        controller._injection_orchestrator._rom_injector = mock_injector

        mock_verifier = MagicMock()
        mock_verifier.verify_offsets.return_value = mock_verification

        with patch(
            "core.services.injection_orchestrator.ROMVerificationService",
            return_value=mock_verifier,
        ):
            result = controller.inject_mapping("ai_frame.png", rom_path)

        # Injection should succeed
        assert result is True

    def test_raw_fallback_when_no_boundary_detected(self, tmp_path: Path, qtbot) -> None:
        """RAW injection uses captured count when no boundary detected.

        Scenario: ROM has no padding boundary (continuous data).
        Expected: All captured tiles are injected (fallback behavior).
        """
        # Create capture with 3 tiles
        rom_offset = 0x100000
        capture_data = create_test_capture(
            entry_ids=[1, 2, 3],
            rom_offsets=[rom_offset] * 3,
        )
        capture_path = tmp_path / "capture.json"
        capture_path.write_text(json.dumps(capture_data))

        # Create AI frame image
        ai_frame_path = tmp_path / "ai_frame.png"
        ai_img = Image.new("RGBA", (24, 8), (255, 0, 0, 255))  # 3 tiles wide
        ai_img.save(ai_frame_path)

        # Create ROM with NO padding (continuous non-zero data)
        tile_data = b"\x12\x34" * 16  # 32 bytes per tile
        # No padding - continuous data
        rom_content = b"\x12\x34" * (rom_offset // 2) + tile_data * 1000
        rom_path = tmp_path / "test.sfc"
        rom_path.write_bytes(rom_content)

        # Create project
        project = FrameMappingProject(name="test")
        project.ai_frames_dir = tmp_path
        project.ai_frames.append(AIFrame(path=ai_frame_path, index=0))
        project.add_game_frame(
            GameFrame(
                id="F001",
                capture_path=capture_path,
                rom_offsets=[rom_offset],
                selected_entry_ids=[1, 2, 3],
                compression_types={rom_offset: "raw"},
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

        # Verify no boundary is detected
        detected = controller._injection_orchestrator._staging_manager.detect_raw_slot_size(rom_content, rom_offset)
        assert detected is None, "Should not detect boundary in continuous data"

        def mock_inject(
            sprite_path,
            rom_path,
            output_path,
            sprite_offset,
            **kwargs,
        ):
            Path(output_path).write_bytes(Path(rom_path).read_bytes())
            return (True, "Success")

        mock_verification = ROMVerificationResult(
            total=3,
            matched_hal=0,
            matched_raw=3,
            not_found=0,
            corrections={},
        )

        # Create mock injector and set it on the controller's orchestrator
        mock_injector = MagicMock()
        mock_injector.find_compressed_sprite.return_value = (0, b"\x00" * 32, 32)
        mock_injector.inject_sprite_to_rom.side_effect = mock_inject
        controller._injection_orchestrator._rom_injector = mock_injector

        mock_verifier = MagicMock()
        mock_verifier.verify_offsets.return_value = mock_verification

        with patch(
            "core.services.injection_orchestrator.ROMVerificationService",
            return_value=mock_verifier,
        ):
            result = controller.inject_mapping("ai_frame.png", rom_path)

        assert result is True
