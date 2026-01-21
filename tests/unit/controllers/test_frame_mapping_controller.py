"""Tests for FrameMappingController selected_entry_ids filtering.

Verifies that get_capture_result_for_game_frame respects the stored
selected_entry_ids when returning capture results. Also verifies that
inject_mapping uses the same filtering and applies scale transforms.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image

from core.frame_mapping_project import AIFrame, FrameMapping, FrameMappingProject, GameFrame
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

        # Get capture result
        result = controller.get_capture_result_for_game_frame("F001")

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

        # Get capture result
        result = controller.get_capture_result_for_game_frame("F001")

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

        # Get capture result - should preserve capture file order
        result = controller.get_capture_result_for_game_frame("F001")

        assert result is not None
        assert len(result.entries) == 3
        # Order should match capture file, not selected_entry_ids order
        assert [e.id for e in result.entries] == [10, 20, 40]

    def test_returns_none_when_no_entries_match(self, tmp_path: Path, qtbot) -> None:
        """Returns None when no entries match selected IDs."""
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

        # Get capture result - should return None
        result = controller.get_capture_result_for_game_frame("F001")

        assert result is None

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

        # Get capture result
        result = controller.get_capture_result_for_game_frame("F001")

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
                ai_frame_index=0,
                game_frame_id="F001",
                offset_x=0,
                offset_y=0,
            )
        )

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
            patch.object(controller, "_create_injection_copy", return_value=tmp_path / "out.sfc"),
            patch("ui.frame_mapping.controllers.frame_mapping_controller.ROMInjector") as mock_injector_class,
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
            controller.inject_mapping(0, rom_path)

        # Should only have processed entry 10
        # BUG: Will have both [10, 20] because filtering uses rom_offset
        assert captured_entries == [10], (
            f"Expected only entry 10 from selected_entry_ids, "
            f"but got {captured_entries} (filtering by rom_offset includes all matching entries)"
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
                ai_frame_index=0,
                game_frame_id="F001",
                offset_x=0,
                offset_y=0,
                scale=0.5,  # Scale to 50% (16x16 -> 8x8)
            )
        )

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
            patch.object(controller, "_create_injection_copy", return_value=tmp_path / "out.sfc"),
            patch("ui.frame_mapping.controllers.frame_mapping_controller.ROMInjector") as mock_injector_class,
        ):
            mock_injector = MagicMock()
            mock_injector.find_compressed_sprite.return_value = (0, b"\x00" * 32, 32)
            mock_injector.inject_sprite_to_rom.return_value = (True, "Success")
            mock_injector_class.return_value = mock_injector

            # Create fake ROM files
            rom_path = tmp_path / "test.sfc"
            rom_path.write_bytes(b"\x00" * 0x200000)
            (tmp_path / "out.sfc").write_bytes(b"\x00" * 0x200000)

            controller.inject_mapping(0, rom_path)

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
