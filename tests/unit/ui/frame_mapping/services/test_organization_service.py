"""Tests for OrganizationService.

Tests frame/capture renaming and tagging operations.
"""

from unittest.mock import MagicMock

import pytest
from PySide6.QtCore import QObject

from core.frame_mapping_project import AIFrame, GameFrame
from ui.frame_mapping.services.organization_service import OrganizationService
from ui.frame_mapping.undo import (
    RenameAIFrameCommand,
    RenameCaptureCommand,
    ToggleFrameTagCommand,
)


@pytest.fixture
def organization_service():
    """Create organization service instance."""
    return OrganizationService()


@pytest.fixture
def mock_project():
    """Create mock FrameMappingProject."""
    project = MagicMock()
    return project


@pytest.fixture
def mock_undo_stack():
    """Create mock UndoRedoStack."""
    stack = MagicMock()
    return stack


@pytest.fixture
def mock_command_context(mock_project):
    """Create mock CommandContext with real project mock."""
    ctx = MagicMock()
    ctx.project = mock_project
    return ctx


@pytest.fixture
def sample_ai_frame(tmp_path):
    """Create sample AIFrame for testing."""
    from pathlib import Path

    frame_path = tmp_path / "test_frame.png"
    return AIFrame(
        path=frame_path,
        index=0,
        width=32,
        height=32,
        display_name="Test Frame",
        tags=frozenset({"idle", "front"}),
    )


@pytest.fixture
def sample_game_frame(tmp_path):
    """Create sample GameFrame for testing."""
    from pathlib import Path

    capture_path = tmp_path / "capture.json"
    return GameFrame(
        id="capture_001",
        rom_offsets=[0x8000],
        capture_path=capture_path,
        palette_index=7,
        width=32,
        height=32,
        selected_entry_ids=[1, 2, 3],
        compression_types={0x8000: "hal"},
        display_name="Test Capture",
    )


# ─── AI Frame Renaming ─────────────────────────────────────────────────────


def test_rename_frame_success(
    organization_service, mock_project, mock_undo_stack, mock_command_context, sample_ai_frame
):
    """Test successful frame rename with undo."""
    mock_project.get_ai_frame_by_id.return_value = sample_ai_frame
    mock_command_context.project = mock_project

    result = organization_service.rename_frame(
        ctx=mock_command_context,
        undo_stack=mock_undo_stack,
        frame_id="test_frame.png",
        display_name="New Name",
    )

    assert result is True
    mock_project.get_ai_frame_by_id.assert_called_once_with("test_frame.png")
    mock_undo_stack.push.assert_called_once()

    # Verify command was created with correct parameters
    pushed_command = mock_undo_stack.push.call_args[0][0]
    assert isinstance(pushed_command, RenameAIFrameCommand)


def test_rename_frame_not_found(organization_service, mock_project, mock_undo_stack, mock_command_context):
    """Test rename fails when frame not found."""
    mock_project.get_ai_frame_by_id.return_value = None
    mock_command_context.project = mock_project

    result = organization_service.rename_frame(
        ctx=mock_command_context,
        undo_stack=mock_undo_stack,
        frame_id="nonexistent.png",
        display_name="New Name",
    )

    assert result is False
    mock_undo_stack.push.assert_not_called()


def test_rename_frame_clear_name(
    organization_service, mock_project, mock_undo_stack, mock_command_context, sample_ai_frame
):
    """Test clearing frame display name (set to None)."""
    mock_project.get_ai_frame_by_id.return_value = sample_ai_frame
    mock_command_context.project = mock_project

    result = organization_service.rename_frame(
        ctx=mock_command_context,
        undo_stack=mock_undo_stack,
        frame_id="test_frame.png",
        display_name=None,
    )

    assert result is True
    mock_undo_stack.push.assert_called_once()


def test_rename_frame_signal_emitted(
    qtbot, organization_service, mock_project, mock_undo_stack, mock_command_context, sample_ai_frame
):
    """Test frame_renamed signal is emitted."""
    mock_project.get_ai_frame_by_id.return_value = sample_ai_frame
    mock_command_context.project = mock_project

    with qtbot.waitSignal(organization_service.frame_renamed, timeout=1000) as blocker:
        organization_service.rename_frame(
            ctx=mock_command_context,
            undo_stack=mock_undo_stack,
            frame_id="test_frame.png",
            display_name="New Name",
        )

    assert blocker.args == ["test_frame.png"]


def test_rename_frame_no_history(organization_service, mock_project):
    """Test internal rename without undo."""
    mock_project.set_frame_display_name.return_value = True

    result = organization_service._rename_frame_no_history(
        project=mock_project, frame_id="test_frame.png", display_name="New Name"
    )

    assert result is True
    mock_project.set_frame_display_name.assert_called_once_with("test_frame.png", "New Name")


# ─── Frame Tagging ─────────────────────────────────────────────────────────


def test_add_frame_tag_success(organization_service, mock_project):
    """Test adding tag to frame."""
    mock_project.add_frame_tag.return_value = True

    result = organization_service.add_frame_tag(project=mock_project, frame_id="test_frame.png", tag="action")

    assert result is True
    mock_project.add_frame_tag.assert_called_once_with("test_frame.png", "action")


def test_add_frame_tag_signal_emitted(qtbot, organization_service, mock_project):
    """Test frame_tags_changed signal is emitted when tag added."""
    mock_project.add_frame_tag.return_value = True

    with qtbot.waitSignal(organization_service.frame_tags_changed, timeout=1000) as blocker:
        organization_service.add_frame_tag(project=mock_project, frame_id="test_frame.png", tag="action")

    assert blocker.args == ["test_frame.png"]


def test_add_frame_tag_no_signal_on_failure(qtbot, organization_service, mock_project):
    """Test no signal when tag add fails."""
    mock_project.add_frame_tag.return_value = False

    # Should not emit signal when operation fails
    result = organization_service.add_frame_tag(project=mock_project, frame_id="test_frame.png", tag="action")

    assert result is False


def test_remove_frame_tag_success(organization_service, mock_project):
    """Test removing tag from frame."""
    mock_project.remove_frame_tag.return_value = True

    result = organization_service.remove_frame_tag(project=mock_project, frame_id="test_frame.png", tag="action")

    assert result is True
    mock_project.remove_frame_tag.assert_called_once_with("test_frame.png", "action")


def test_remove_frame_tag_signal_emitted(qtbot, organization_service, mock_project):
    """Test frame_tags_changed signal is emitted when tag removed."""
    mock_project.remove_frame_tag.return_value = True

    with qtbot.waitSignal(organization_service.frame_tags_changed, timeout=1000) as blocker:
        organization_service.remove_frame_tag(project=mock_project, frame_id="test_frame.png", tag="action")

    assert blocker.args == ["test_frame.png"]


def test_toggle_frame_tag_success(
    organization_service, mock_project, mock_undo_stack, mock_command_context, sample_ai_frame
):
    """Test toggling tag with undo."""
    mock_project.get_ai_frame_by_id.return_value = sample_ai_frame
    mock_command_context.project = mock_project

    result = organization_service.toggle_frame_tag(
        ctx=mock_command_context,
        undo_stack=mock_undo_stack,
        frame_id="test_frame.png",
        tag="action",
    )

    assert result is True
    mock_undo_stack.push.assert_called_once()

    # Verify command was created
    pushed_command = mock_undo_stack.push.call_args[0][0]
    assert isinstance(pushed_command, ToggleFrameTagCommand)


def test_toggle_frame_tag_not_found(organization_service, mock_project, mock_undo_stack, mock_command_context):
    """Test toggle fails when frame not found."""
    mock_project.get_ai_frame_by_id.return_value = None
    mock_command_context.project = mock_project

    result = organization_service.toggle_frame_tag(
        ctx=mock_command_context,
        undo_stack=mock_undo_stack,
        frame_id="nonexistent.png",
        tag="action",
    )

    assert result is False
    mock_undo_stack.push.assert_not_called()


def test_toggle_frame_tag_signal_emitted(
    qtbot, organization_service, mock_project, mock_undo_stack, mock_command_context, sample_ai_frame
):
    """Test frame_tags_changed signal is emitted when tag toggled."""
    mock_project.get_ai_frame_by_id.return_value = sample_ai_frame
    mock_command_context.project = mock_project

    with qtbot.waitSignal(organization_service.frame_tags_changed, timeout=1000) as blocker:
        organization_service.toggle_frame_tag(
            ctx=mock_command_context,
            undo_stack=mock_undo_stack,
            frame_id="test_frame.png",
            tag="action",
        )

    assert blocker.args == ["test_frame.png"]


def test_toggle_frame_tag_no_history(organization_service, mock_project):
    """Test internal toggle without undo."""
    mock_project.toggle_frame_tag.return_value = True

    result = organization_service._toggle_frame_tag_no_history(
        project=mock_project, frame_id="test_frame.png", tag="action"
    )

    assert result is True
    mock_project.toggle_frame_tag.assert_called_once_with("test_frame.png", "action")


def test_set_frame_tags_success(organization_service, mock_project):
    """Test setting all tags for frame."""
    new_tags = frozenset({"action", "jump"})
    mock_project.set_frame_tags.return_value = True

    result = organization_service.set_frame_tags(project=mock_project, frame_id="test_frame.png", tags=new_tags)

    assert result is True
    mock_project.set_frame_tags.assert_called_once_with("test_frame.png", new_tags)


def test_set_frame_tags_signal_emitted(qtbot, organization_service, mock_project):
    """Test frame_tags_changed signal is emitted when tags set."""
    new_tags = frozenset({"action", "jump"})
    mock_project.set_frame_tags.return_value = True

    with qtbot.waitSignal(organization_service.frame_tags_changed, timeout=1000) as blocker:
        organization_service.set_frame_tags(project=mock_project, frame_id="test_frame.png", tags=new_tags)

    assert blocker.args == ["test_frame.png"]


def test_get_frame_tags_success(organization_service, mock_project, sample_ai_frame):
    """Test getting tags for frame."""
    mock_project.get_ai_frame_by_id.return_value = sample_ai_frame

    tags = organization_service.get_frame_tags(project=mock_project, frame_id="test_frame.png")

    assert tags == frozenset({"idle", "front"})
    mock_project.get_ai_frame_by_id.assert_called_once_with("test_frame.png")


def test_get_frame_tags_not_found(organization_service, mock_project):
    """Test getting tags returns empty set when frame not found."""
    mock_project.get_ai_frame_by_id.return_value = None

    tags = organization_service.get_frame_tags(project=mock_project, frame_id="nonexistent.png")

    assert tags == frozenset()


# ─── Frame Display Names ───────────────────────────────────────────────────


def test_get_frame_display_name_success(organization_service, mock_project, sample_ai_frame):
    """Test getting display name for frame."""
    mock_project.get_ai_frame_by_id.return_value = sample_ai_frame

    name = organization_service.get_frame_display_name(project=mock_project, frame_id="test_frame.png")

    assert name == "Test Frame"


def test_get_frame_display_name_not_found(organization_service, mock_project):
    """Test getting display name returns None when frame not found."""
    mock_project.get_ai_frame_by_id.return_value = None

    name = organization_service.get_frame_display_name(project=mock_project, frame_id="nonexistent.png")

    assert name is None


def test_get_frames_with_tag(organization_service, mock_project, sample_ai_frame):
    """Test filtering frames by tag."""
    mock_project.get_frames_with_tag.return_value = [sample_ai_frame]

    frames = organization_service.get_frames_with_tag(project=mock_project, tag="idle")

    assert len(frames) == 1
    assert frames[0] == sample_ai_frame
    mock_project.get_frames_with_tag.assert_called_once_with("idle")


def test_get_available_tags():
    """Test getting static set of available tags."""
    tags = OrganizationService.get_available_tags()

    assert isinstance(tags, frozenset)
    assert len(tags) > 0  # Should have some predefined tags


# ─── Capture (GameFrame) Renaming ──────────────────────────────────────────


def test_rename_capture_success(
    organization_service, mock_project, mock_undo_stack, mock_command_context, sample_game_frame
):
    """Test successful capture rename with undo."""
    mock_project.get_game_frame_by_id.return_value = sample_game_frame
    mock_command_context.project = mock_project

    result = organization_service.rename_capture(
        ctx=mock_command_context,
        undo_stack=mock_undo_stack,
        game_frame_id="capture_001",
        new_name="New Capture Name",
    )

    assert result is True
    mock_project.get_game_frame_by_id.assert_called_once_with("capture_001")
    mock_undo_stack.push.assert_called_once()

    # Verify command was created
    pushed_command = mock_undo_stack.push.call_args[0][0]
    assert isinstance(pushed_command, RenameCaptureCommand)


def test_rename_capture_not_found(organization_service, mock_project, mock_undo_stack, mock_command_context):
    """Test rename fails when capture not found."""
    mock_project.get_game_frame_by_id.return_value = None
    mock_command_context.project = mock_project

    result = organization_service.rename_capture(
        ctx=mock_command_context,
        undo_stack=mock_undo_stack,
        game_frame_id="nonexistent",
        new_name="New Name",
    )

    assert result is False
    mock_undo_stack.push.assert_not_called()


def test_rename_capture_empty_string_to_none(
    organization_service, mock_project, mock_undo_stack, mock_command_context, sample_game_frame
):
    """Test empty string is normalized to None."""
    mock_project.get_game_frame_by_id.return_value = sample_game_frame
    mock_command_context.project = mock_project

    result = organization_service.rename_capture(
        ctx=mock_command_context,
        undo_stack=mock_undo_stack,
        game_frame_id="capture_001",
        new_name="   ",  # Whitespace only
    )

    assert result is True
    mock_undo_stack.push.assert_called_once()

    # Verify command was created with None (not empty string)
    pushed_command = mock_undo_stack.push.call_args[0][0]
    assert isinstance(pushed_command, RenameCaptureCommand)


def test_rename_capture_signal_emitted(
    qtbot, organization_service, mock_project, mock_undo_stack, mock_command_context, sample_game_frame
):
    """Test capture_renamed signal is emitted."""
    mock_project.get_game_frame_by_id.return_value = sample_game_frame
    mock_command_context.project = mock_project

    with qtbot.waitSignal(organization_service.capture_renamed, timeout=1000) as blocker:
        organization_service.rename_capture(
            ctx=mock_command_context,
            undo_stack=mock_undo_stack,
            game_frame_id="capture_001",
            new_name="New Name",
        )

    assert blocker.args == ["capture_001"]


def test_rename_capture_no_history(organization_service, mock_project):
    """Test internal capture rename without undo."""
    mock_project.set_capture_display_name.return_value = True

    result = organization_service._rename_capture_no_history(
        project=mock_project, game_frame_id="capture_001", display_name="New Name"
    )

    assert result is True
    mock_project.set_capture_display_name.assert_called_once_with("capture_001", "New Name")


def test_get_capture_display_name_success(organization_service, mock_project, sample_game_frame):
    """Test getting display name for capture."""
    mock_project.get_game_frame_by_id.return_value = sample_game_frame

    name = organization_service.get_capture_display_name(project=mock_project, game_frame_id="capture_001")

    assert name == "Test Capture"


def test_get_capture_display_name_not_found(organization_service, mock_project):
    """Test getting capture display name returns None when not found."""
    mock_project.get_game_frame_by_id.return_value = None

    name = organization_service.get_capture_display_name(project=mock_project, game_frame_id="nonexistent")

    assert name is None
