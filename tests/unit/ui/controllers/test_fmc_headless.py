"""Tests for headless FrameMappingController usage.

Verifies that the controller can be used without Qt parent or workspace,
enabling CLI tools and batch processing scenarios.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from PIL import Image

from core.frame_mapping_project import AIFrame, FrameMapping, FrameMappingProject, GameFrame
from tests.fixtures.frame_mapping_helpers import create_test_capture
from ui.frame_mapping.controllers.frame_mapping_controller import FrameMappingController


class TestHeadlessControllerUsage:
    """Tests for using controller without Qt parent or workspace.

    These tests verify that the controller can be used in headless
    mode for CLI tools or batch processing.
    """

    def test_create_controller_without_parent(self, qtbot) -> None:
        """Controller can be created without parent."""
        controller = FrameMappingController(parent=None)

        assert controller is not None
        assert controller.parent() is None

    def test_new_project_without_parent(self, qtbot) -> None:
        """Can create new project without parent."""
        controller = FrameMappingController(parent=None)

        controller.new_project("headless_test")

        assert controller.has_project
        assert controller.project is not None
        assert controller.project.name == "headless_test"

    def test_load_ai_frames_without_parent(self, tmp_path: Path, qtbot) -> None:
        """Can load AI frames without parent."""
        img = Image.new("RGBA", (16, 16), (255, 0, 0, 255))
        frame1 = tmp_path / "frame_001.png"
        frame2 = tmp_path / "frame_002.png"
        img.save(frame1)
        img.save(frame2)

        controller = FrameMappingController(parent=None)

        count = controller.load_ai_frames_from_directory(tmp_path)

        assert count == 2
        assert controller.has_project
        assert len(controller.get_ai_frames()) == 2

    def test_signals_work_without_parent(self, qtbot) -> None:
        """Signals work without parent."""
        controller = FrameMappingController(parent=None)

        signal_received = []
        controller.project_changed.connect(lambda: signal_received.append(True))

        controller.new_project("test")

        assert signal_received == [True]

    def test_save_load_project_without_parent(self, tmp_path: Path, qtbot) -> None:
        """Can save and load project without parent."""
        img = Image.new("RGBA", (16, 16), (255, 0, 0, 255))
        frame1 = tmp_path / "frame_001.png"
        img.save(frame1)

        controller = FrameMappingController(parent=None)
        controller.load_ai_frames_from_directory(tmp_path)

        project_path = tmp_path / "test.spritepal-mapping.json"
        success = controller.save_project(project_path)
        assert success
        assert project_path.exists()

        controller2 = FrameMappingController(parent=None)
        success = controller2.load_project(project_path)
        assert success
        assert controller2.has_project
        assert len(controller2.get_ai_frames()) == 1

    def test_create_mapping_without_parent(self, tmp_path: Path, qtbot) -> None:
        """Can create mappings without parent, emits signals and enables undo."""
        img = Image.new("RGBA", (16, 16), (255, 0, 0, 255))
        ai_frame_path = tmp_path / "frame_001.png"
        img.save(ai_frame_path)

        capture_data = create_test_capture([0, 1])
        capture_path = tmp_path / "capture.json"
        capture_path.write_text(json.dumps(capture_data))

        controller = FrameMappingController(parent=None)

        project = FrameMappingProject(name="test")
        project.ai_frames.append(AIFrame(path=ai_frame_path, index=0))
        project.add_game_frame(
            GameFrame(
                id="G001",
                rom_offsets=[0x1000],
                capture_path=capture_path,
                selected_entry_ids=[0, 1],
            )
        )
        project._rebuild_indices()
        controller._project = project

        assert not controller.can_undo()

        with qtbot.waitSignals(
            [controller.mapping_created, controller.save_requested],
            timeout=1000,
        ):
            success = controller.create_mapping("frame_001.png", "G001")

        assert success
        assert len(controller.project.mappings) == 1
        assert controller.can_undo()

    def test_alignment_update_without_parent(self, tmp_path: Path, qtbot) -> None:
        """Can update alignment without parent."""
        img = Image.new("RGBA", (16, 16), (255, 0, 0, 255))
        ai_frame_path = tmp_path / "frame_001.png"
        img.save(ai_frame_path)

        capture_data = create_test_capture([0])
        capture_path = tmp_path / "capture.json"
        capture_path.write_text(json.dumps(capture_data))

        controller = FrameMappingController(parent=None)
        project = FrameMappingProject(name="test")
        project.ai_frames.append(AIFrame(path=ai_frame_path, index=0))
        project.add_game_frame(
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

        success = controller.update_mapping_alignment(
            ai_frame_id="frame_001.png",
            offset_x=10,
            offset_y=20,
            flip_h=True,
            flip_v=False,
            scale=0.5,
        )

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
        img = Image.new("RGBA", (16, 16), (255, 0, 0, 255))
        ai_frame_path = tmp_path / "frame_001.png"
        img.save(ai_frame_path)

        capture_data = create_test_capture([0])
        capture_path = tmp_path / "capture.json"
        capture_path.write_text(json.dumps(capture_data))

        controller = FrameMappingController(parent=None)
        project = FrameMappingProject(name="test")
        project.ai_frames.append(AIFrame(path=ai_frame_path, index=0))
        project.add_game_frame(
            GameFrame(
                id="G001",
                rom_offsets=[0x1000],
                capture_path=capture_path,
                selected_entry_ids=[0],
            )
        )
        project._rebuild_indices()
        controller._project = project

        controller.create_mapping("frame_001.png", "G001")
        assert len(project.mappings) == 1

        desc = controller.undo()
        assert desc is not None
        assert len(project.mappings) == 0

        desc = controller.redo()
        assert desc is not None
        assert len(project.mappings) == 1


class TestUpdateMappingAlignmentEmitsSaveRequested:
    """Test that update_mapping_alignment emits save_requested for auto-save.

    Bug: Alignment changes (drag/nudge on canvas) were lost on app close because
    update_mapping_alignment only emitted alignment_updated but NOT save_requested.
    """

    def test_update_mapping_alignment_emits_save_requested(self, tmp_path: Path, qtbot) -> None:
        """Verify alignment changes trigger auto-save signal."""
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
        project.add_game_frame(GameFrame(id="G001", rom_offsets=[0x1000], selected_entry_ids=[]))
        project.mappings.append(FrameMapping(ai_frame_id="frame_001.png", game_frame_id="G001"))
        project._rebuild_indices()

        controller = FrameMappingController()
        controller._project = project

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
        project.add_game_frame(GameFrame(id="G002", rom_offsets=[0x2000], selected_entry_ids=[]))
        project.mappings.append(FrameMapping(ai_frame_id="frame_002.png", game_frame_id="G002"))
        project._rebuild_indices()

        controller = FrameMappingController()
        controller._project = project

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
