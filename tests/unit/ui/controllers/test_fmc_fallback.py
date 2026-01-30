"""Tests for FrameMappingController fallback behavior and entry ID handling.

Covers stale entry ID fallback, rom offset correction, injection rollback,
and allow_fallback parameter behavior.
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


def create_capture_with_tile_data(
    entry_id: int,
    rom_offset: int,
    tile_data_hex: str,
) -> dict:
    """Create a capture with specific tile data for ROM offset correction tests."""
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
        """Injection should trigger stale_entries_warning and fall back to rom_offset."""
        rom_offset = 0x123456
        capture_data = create_test_capture(
            entry_ids=[10, 20],
            rom_offsets=[rom_offset, rom_offset],
        )
        capture_path = tmp_path / "capture.json"
        capture_path.write_text(json.dumps(capture_data))

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

        with qtbot.waitSignal(controller.stale_entries_warning, timeout=1000):
            result, _ = controller.get_capture_result_for_game_frame("F001")

        assert result is not None
        assert len(result.entries) == 2
        assert {e.id for e in result.entries} == {10, 20}

    def test_preview_and_injection_consistency_with_valid_ids(self, tmp_path: Path, qtbot) -> None:
        """Preview and injection should both use selected_entry_ids when valid."""
        capture_data = create_test_capture([10, 20, 30])
        capture_path = tmp_path / "capture.json"
        capture_path.write_text(json.dumps(capture_data))

        rom_offset = 0x100000 + 0x100  # Entry 10's offset

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


class TestEntryFallbackFlag:
    """Tests for entry ID fallback flag in get_capture_result_for_game_frame."""

    def test_returns_false_when_entry_ids_match(self, tmp_path: Path, qtbot) -> None:
        """Returns used_fallback=False when stored entry IDs exist in capture."""
        capture_data = create_test_capture(entry_ids=[1, 2])
        capture_path = tmp_path / "capture.json"
        capture_path.write_text(json.dumps(capture_data))

        project = FrameMappingProject(name="test")
        project.game_frames.append(
            GameFrame(
                id="F001",
                capture_path=capture_path,
                rom_offsets=[0x100000, 0x100100],
                selected_entry_ids=[1, 2],
            )
        )

        controller = FrameMappingController()
        controller._project = project

        result, used_fallback = controller.get_capture_result_for_game_frame("F001")

        assert result is not None
        assert used_fallback is False, "Should not use fallback when entry IDs match"
        assert len(result.entries) == 2

    def test_returns_true_when_entry_ids_stale(self, tmp_path: Path, qtbot) -> None:
        """Returns used_fallback=True when stored entry IDs don't exist in capture."""
        rom_offsets = [0x100000, 0x100100]
        capture_data = create_test_capture(entry_ids=[10, 20], rom_offsets=rom_offsets)
        capture_path = tmp_path / "capture.json"
        capture_path.write_text(json.dumps(capture_data))

        project = FrameMappingProject(name="test")
        project.game_frames.append(
            GameFrame(
                id="F001",
                capture_path=capture_path,
                rom_offsets=rom_offsets,
                selected_entry_ids=[1, 2],  # Stale entry IDs
            )
        )

        controller = FrameMappingController()
        controller._project = project

        result, used_fallback = controller.get_capture_result_for_game_frame("F001")

        assert result is not None
        assert used_fallback is True, "Should use fallback when entry IDs are stale"
        assert len(result.entries) == 2

    def test_emits_stale_warning_signal_on_fallback(self, tmp_path: Path, qtbot) -> None:
        """Emits stale_entries_warning signal when fallback is used."""
        rom_offsets = [0x100000]
        capture_data = create_test_capture(entry_ids=[99], rom_offsets=rom_offsets)
        capture_path = tmp_path / "capture.json"
        capture_path.write_text(json.dumps(capture_data))

        project = FrameMappingProject(name="test")
        project.game_frames.append(
            GameFrame(
                id="F002",
                capture_path=capture_path,
                rom_offsets=rom_offsets,
                selected_entry_ids=[1],  # Stale
            )
        )

        controller = FrameMappingController()
        controller._project = project

        signal_received: list[str] = []
        controller.stale_entries_warning.connect(lambda fid: signal_received.append(fid))

        controller.get_capture_result_for_game_frame("F002")

        assert len(signal_received) == 1
        assert signal_received[0] == "F002"

    def test_returns_false_when_no_selected_entry_ids(self, tmp_path: Path, qtbot) -> None:
        """Returns used_fallback=False when game frame has no stored selection."""
        capture_data = create_test_capture(entry_ids=[1, 2, 3])
        capture_path = tmp_path / "capture.json"
        capture_path.write_text(json.dumps(capture_data))

        project = FrameMappingProject(name="test")
        project.game_frames.append(
            GameFrame(
                id="F001",
                capture_path=capture_path,
                rom_offsets=[0x100000],
                selected_entry_ids=[],  # No selection stored
            )
        )

        controller = FrameMappingController()
        controller._project = project

        result, used_fallback = controller.get_capture_result_for_game_frame("F001")

        assert result is not None
        assert used_fallback is False
        assert len(result.entries) == 3

    def test_returns_none_for_missing_game_frame(self, qtbot) -> None:
        """Returns (None, False) for non-existent game frame ID."""
        project = FrameMappingProject(name="test")

        controller = FrameMappingController()
        controller._project = project

        result, used_fallback = controller.get_capture_result_for_game_frame("NONEXISTENT")

        assert result is None
        assert used_fallback is False

    def test_returns_none_when_no_project(self, qtbot) -> None:
        """Returns (None, False) when no project is loaded."""
        controller = FrameMappingController()

        result, used_fallback = controller.get_capture_result_for_game_frame("F001")

        assert result is None
        assert used_fallback is False


class TestRomOffsetCorrection:
    """Tests for automatic ROM offset correction of stale VRAM attribution."""

    def test_corrects_stale_offset_for_raw_tile(self, tmp_path: Path, qtbot) -> None:
        """Stale offset should be corrected by finding tile in ROM via raw search."""
        tile_data = bytes(range(32))
        tile_hex = tile_data.hex()

        stale_offset = 0x100000
        correct_offset = 0x50000

        capture_data = create_capture_with_tile_data(
            entry_id=1,
            rom_offset=stale_offset,
            tile_data_hex=tile_hex,
        )
        capture_path = tmp_path / "capture.json"
        capture_path.write_text(json.dumps(capture_data))

        rom_data = bytearray(0x200000)
        rom_data[correct_offset : correct_offset + 32] = tile_data
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
                rom_offsets=[stale_offset],
                selected_entry_ids=[1],
            )
        )
        project.mappings.append(FrameMapping(ai_frame_id="ai_frame.png", game_frame_id="F001", offset_x=0, offset_y=0))
        project._rebuild_indices()

        controller = FrameMappingController()
        controller._project = project

        injected_offsets: list[int] = []

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

        assert len(injected_offsets) == 1, f"Expected 1 injection, got {len(injected_offsets)}"
        assert injected_offsets[0] == correct_offset, (
            f"Expected injection at corrected offset 0x{correct_offset:X}, "
            f"but got 0x{injected_offsets[0]:X} (stale offset not corrected)"
        )

    def test_uses_original_offset_when_tile_found_at_attributed_location(self, tmp_path: Path, qtbot) -> None:
        """When tile is found at the attributed offset, no correction needed."""
        tile_data = bytes([0xAB, 0xCD] * 16)
        tile_hex = tile_data.hex()

        correct_offset = 0x80000

        capture_data = create_capture_with_tile_data(
            entry_id=1,
            rom_offset=correct_offset,
            tile_data_hex=tile_hex,
        )
        capture_path = tmp_path / "capture.json"
        capture_path.write_text(json.dumps(capture_data))

        rom_data = bytearray(0x200000)
        rom_data[correct_offset : correct_offset + 32] = tile_data
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
                rom_offsets=[correct_offset],
                selected_entry_ids=[1],
            )
        )
        project.mappings.append(FrameMapping(ai_frame_id="ai_frame.png", game_frame_id="F001", offset_x=0, offset_y=0))
        project._rebuild_indices()

        controller = FrameMappingController()
        controller._project = project

        injected_offsets: list[int] = []

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

        assert len(injected_offsets) == 1
        assert injected_offsets[0] == correct_offset

    def test_emits_error_when_no_tiles_found_in_rom(self, tmp_path: Path, qtbot) -> None:
        """Should emit error when tiles can't be found anywhere in ROM."""
        tile_data = bytes([0xDE, 0xAD, 0xBE, 0xEF] * 8)
        tile_hex = tile_data.hex()

        capture_data = create_capture_with_tile_data(
            entry_id=1,
            rom_offset=0x100000,
            tile_data_hex=tile_hex,
        )
        capture_path = tmp_path / "capture.json"
        capture_path.write_text(json.dumps(capture_data))

        rom_data = bytes(0x200000)
        rom_path = tmp_path / "test.sfc"
        rom_path.write_bytes(rom_data)

        ai_frame_path = tmp_path / "ai_frame.png"
        Image.new("RGBA", (8, 8), (255, 0, 0, 255)).save(ai_frame_path)

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


class TestAllowFallbackParameter:
    """Tests for the allow_fallback parameter in inject_mapping."""

    def test_injection_aborts_on_stale_entry_ids_without_allow_fallback(self, tmp_path: Path, qtbot) -> None:
        """Injection should abort when stored entry IDs are stale and allow_fallback=False."""
        rom_offset = 0x123456
        capture_data = create_test_capture(
            entry_ids=[10, 20],
            rom_offsets=[rom_offset, rom_offset],
        )
        capture_path = tmp_path / "capture.json"
        capture_path.write_text(json.dumps(capture_data))

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
                selected_entry_ids=[99, 100],  # Stale IDs
            )
        )
        project.mappings.append(FrameMapping(ai_frame_id="ai_frame.png", game_frame_id="F001", offset_x=0, offset_y=0))
        project._rebuild_indices()

        controller = FrameMappingController()
        controller._project = project

        rom_path = tmp_path / "test.sfc"
        rom_path.write_bytes(b"\x00" * 0x200000)

        with qtbot.waitSignal(controller.stale_entries_warning, timeout=1000):
            result = controller.inject_mapping("ai_frame.png", rom_path, allow_fallback=False)

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

            result = controller.inject_mapping("ai_frame.png", rom_path, allow_fallback=True)

        assert result is True
        assert 10 in captured_entries


class TestInjectionRollback:
    """Tests for injection rollback mechanism preventing ROM corruption."""

    def test_partial_injection_failure_preserves_original_rom(self, tmp_path: Path, qtbot) -> None:
        """When injection fails mid-loop, original ROM is unchanged."""
        rom_offsets = [0x100000, 0x100100, 0x100200]
        capture_data = create_test_capture(
            entry_ids=[1, 2, 3],
            rom_offsets=rom_offsets,
        )
        capture_path = tmp_path / "capture.json"
        capture_path.write_text(json.dumps(capture_data))

        ai_frame_path = tmp_path / "ai_frame.png"
        ai_img = Image.new("RGBA", (24, 8), (255, 0, 0, 255))
        ai_img.save(ai_frame_path)

        original_content = b"\xaa" * 0x200000
        rom_path = tmp_path / "test.sfc"
        rom_path.write_bytes(original_content)

        project = FrameMappingProject(name="test")
        project.ai_frames_dir = tmp_path
        project.ai_frames.append(AIFrame(path=ai_frame_path, index=0))
        project.game_frames.append(
            GameFrame(
                id="F001",
                capture_path=capture_path,
                rom_offsets=rom_offsets,
                selected_entry_ids=[1, 2, 3],
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

        injection_call_count = [0]

        def mock_inject(
            sprite_path,
            rom_path,
            output_path,
            sprite_offset,
            **kwargs,
        ):
            injection_call_count[0] += 1
            if sprite_offset == 0x100100:  # Fail on second offset
                return (False, "Simulated failure")
            return (True, "Success")

        mock_verification = ROMVerificationResult(
            total=3,
            matched_hal=0,
            matched_raw=3,
            not_found=0,
            corrections={},
        )

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

        assert result is False
        assert injection_call_count[0] >= 1

        final_content = rom_path.read_bytes()
        assert final_content == original_content, (
            "Original ROM was modified despite injection failure. Staging rollback did not work correctly."
        )

    def test_partial_injection_cleans_staging_file(self, tmp_path: Path, qtbot) -> None:
        """Staging file is deleted after injection failure."""
        capture_data = create_test_capture([1], rom_offsets=[0x100000])
        capture_path = tmp_path / "capture.json"
        capture_path.write_text(json.dumps(capture_data))

        ai_frame_path = tmp_path / "ai_frame.png"
        ai_img = Image.new("RGBA", (8, 8), (255, 0, 0, 255))
        ai_img.save(ai_frame_path)

        rom_path = tmp_path / "test.sfc"
        rom_path.write_bytes(b"\x00" * 0x200000)

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
            )
        )
        project._rebuild_indices()

        controller = FrameMappingController()
        controller._project = project

        mock_verification = ROMVerificationResult(
            total=1,
            matched_hal=0,
            matched_raw=1,
            not_found=0,
            corrections={},
        )

        mock_injector = MagicMock()
        mock_injector.find_compressed_sprite.return_value = (0, b"\x00" * 32, 32)
        mock_injector.inject_sprite_to_rom.return_value = (False, "Simulated failure")
        controller._injection_orchestrator._rom_injector = mock_injector

        mock_verifier = MagicMock()
        mock_verifier.verify_offsets.return_value = mock_verification

        with patch(
            "core.services.injection_orchestrator.ROMVerificationService",
            return_value=mock_verifier,
        ):
            controller.inject_mapping("ai_frame.png", rom_path)

        staging_files = list(tmp_path.glob("*.staging"))
        assert len(staging_files) == 0, f"Staging file(s) not cleaned up: {staging_files}"

    def test_successful_injection_commits_staging(self, tmp_path: Path, qtbot) -> None:
        """Successful injection commits staging and updates ROM."""
        capture_data = create_test_capture([1], rom_offsets=[0x100000])
        capture_path = tmp_path / "capture.json"
        capture_path.write_text(json.dumps(capture_data))

        ai_frame_path = tmp_path / "ai_frame.png"
        ai_img = Image.new("RGBA", (8, 8), (255, 0, 0, 255))
        ai_img.save(ai_frame_path)

        original_content = b"\xaa" * 0x200000
        rom_path = tmp_path / "test.sfc"
        rom_path.write_bytes(original_content)

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
            )
        )
        project._rebuild_indices()

        controller = FrameMappingController()
        controller._project = project

        written_paths: list[str] = []

        def mock_inject(
            sprite_path,
            rom_path,
            output_path,
            sprite_offset,
            **kwargs,
        ):
            written_paths.append(output_path)
            Path(output_path).write_bytes(b"\xbb" * 0x200000)
            return (True, "Success")

        mock_verification = ROMVerificationResult(
            total=1,
            matched_hal=0,
            matched_raw=1,
            not_found=0,
            corrections={},
        )

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
        assert len(written_paths) >= 1
        assert any(".staging" in p for p in written_paths), f"Expected writes to staging file, got: {written_paths}"

        staging_files = list(tmp_path.glob("*.staging"))
        assert len(staging_files) == 0, f"Staging file(s) not cleaned up after commit: {staging_files}"

        injected_files = list(tmp_path.glob("*_injected_*.sfc"))
        assert len(injected_files) == 1
        assert injected_files[0].read_bytes() == b"\xbb" * 0x200000
