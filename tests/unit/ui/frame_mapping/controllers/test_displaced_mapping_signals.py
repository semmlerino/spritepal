"""Tests for displaced mapping signal emission."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from core.frame_mapping_project import AIFrame, FrameMappingProject, GameFrame
from tests.fixtures.frame_mapping_helpers import MINIMAL_PNG_DATA
from ui.frame_mapping.controllers.frame_mapping_controller import FrameMappingController


@pytest.fixture
def controller_with_mappings(qtbot, tmp_path):
    """Create a controller with 3 AI frames and 2 game frames."""
    ai_dir = tmp_path / "ai_frames"
    ai_dir.mkdir()
    captures_dir = tmp_path / "captures"
    captures_dir.mkdir()

    # Create controller with new project
    controller = FrameMappingController()
    controller.new_project("test")
    project = controller.project
    assert project is not None

    # Create AI frame files
    ai_frames = []
    for i in range(3):
        p = ai_dir / f"frame_{i:03d}.png"
        p.write_bytes(MINIMAL_PNG_DATA)
        ai_frames.append(AIFrame(path=p, index=i, width=1, height=1))

    # Add AI frames to project
    project.replace_ai_frames(ai_frames, ai_dir)

    # Create game frames
    game_frames = []
    for i in range(2):
        capture_path = captures_dir / f"capture_{i:03d}.json"
        capture_path.write_text("{}")
        game_frame = GameFrame(
            id=f"game_{i:03d}",
            rom_offsets=[0x100000 + i * 0x100],
            capture_path=capture_path,
            palette_index=7,
            width=8,
            height=8,
            selected_entry_ids=[i],
        )
        game_frames.append(game_frame)
        project.add_game_frame(game_frame)

    return controller, ai_frames, game_frames


class TestDisplacedMappingSignals:
    """Test that displaced mapping signals are emitted correctly."""

    def test_no_displaced_signal_for_new_mapping(self, controller_with_mappings, qtbot):
        """Creating a fresh mapping should NOT emit mapping_displaced."""
        controller, ai_frames, game_frames = controller_with_mappings

        displaced_spy = []
        controller.mapping_displaced.connect(lambda ai, game: displaced_spy.append((ai, game)))

        controller.create_mapping(ai_frames[0].id, game_frames[0].id)

        assert len(displaced_spy) == 0

    def test_displaced_ai_frame_signal_emitted(self, controller_with_mappings, qtbot):
        """Remapping a game frame from one AI frame to another emits displaced signal for old AI frame."""
        controller, ai_frames, game_frames = controller_with_mappings

        # A0 → G0
        controller.create_mapping(ai_frames[0].id, game_frames[0].id)

        displaced_spy = []
        controller.mapping_displaced.connect(lambda ai, game: displaced_spy.append((ai, game)))

        # A1 → G0 (displaces A0 from G0)
        controller.create_mapping(ai_frames[1].id, game_frames[0].id)

        assert len(displaced_spy) == 1
        displaced_ai, displaced_game = displaced_spy[0]
        assert displaced_ai == ai_frames[0].id  # A0 was displaced

    def test_displaced_game_frame_signal_emitted(self, controller_with_mappings, qtbot):
        """Remapping an AI frame from one game frame to another emits displaced signal for old game frame."""
        controller, ai_frames, game_frames = controller_with_mappings

        # A0 → G0
        controller.create_mapping(ai_frames[0].id, game_frames[0].id)

        displaced_spy = []
        controller.mapping_displaced.connect(lambda ai, game: displaced_spy.append((ai, game)))

        # A0 → G1 (displaces G0)
        controller.create_mapping(ai_frames[0].id, game_frames[1].id)

        assert len(displaced_spy) == 1
        displaced_ai, displaced_game = displaced_spy[0]
        assert displaced_game == game_frames[0].id  # G0 was displaced
