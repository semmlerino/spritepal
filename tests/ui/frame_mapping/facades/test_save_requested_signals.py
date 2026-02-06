"""Tests verifying that facade mutator methods emit save_requested signals.

Bug 1: Several facade methods modify project state but don't emit save_requested,
causing unsaved changes to not be tracked.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from ui.frame_mapping.facades.ai_frames_facade import AIFramesFacade
from ui.frame_mapping.facades.game_frames_facade import GameFramesFacade
from ui.frame_mapping.facades.palette_facade import PaletteFacade


class TestAIFramesFacadeSaveRequested:
    """Test AIFramesFacade methods emit save_requested."""

    def test_load_from_directory_emits_save_requested(self) -> None:
        """Test load_from_directory emits save_requested after loading frames."""
        # Setup signals
        signals = MagicMock()

        # Setup context with project
        context = MagicMock()
        mock_project = MagicMock()
        mock_project.filter_mappings_by_valid_ai_ids.return_value = 0
        context.project = mock_project

        # Setup AI frame service
        ai_frame_service = MagicMock()
        mock_frame = MagicMock()
        mock_frame.id = "test_frame_id"
        ai_frame_service.load_frames_from_directory.return_value = ([mock_frame], 0)

        # Setup organization service, undo stack, command context
        org_service = MagicMock()
        undo_stack = MagicMock()
        get_cmd_ctx = MagicMock()

        # Setup directory path
        directory = MagicMock(spec=Path)
        directory.is_dir.return_value = True

        # Setup clear_undo callback
        clear_undo = MagicMock()

        # Create facade
        facade = AIFramesFacade(context, signals, ai_frame_service, org_service, undo_stack, get_cmd_ctx)

        # Execute
        facade.load_from_directory(directory, clear_undo=clear_undo)

        # Verify save_requested was emitted
        signals.emit_save_requested.assert_called_once()

    def test_add_from_file_emits_save_requested(self) -> None:
        """Test add_from_file emits save_requested after adding frame."""
        # Setup signals
        signals = MagicMock()

        # Setup context with project
        context = MagicMock()
        context.project = MagicMock()

        # Setup AI frame service
        ai_frame_service = MagicMock()
        mock_frame = MagicMock()
        mock_frame.id = "new_frame_id"
        ai_frame_service.create_frame_from_file.return_value = mock_frame

        # Setup organization service, undo stack, command context
        org_service = MagicMock()
        undo_stack = MagicMock()
        get_cmd_ctx = MagicMock()

        # Setup file path
        file_path = MagicMock(spec=Path)
        file_path.is_file.return_value = True
        file_path.suffix = ".png"

        # Create facade
        facade = AIFramesFacade(context, signals, ai_frame_service, org_service, undo_stack, get_cmd_ctx)

        # Execute
        facade.add_from_file(file_path)

        # Verify save_requested was emitted
        signals.emit_save_requested.assert_called_once()

    def test_remove_emits_save_requested(self) -> None:
        """Test remove emits save_requested after removing frame."""
        # Setup signals
        signals = MagicMock()

        # Setup context with project
        context = MagicMock()
        mock_project = MagicMock()
        mock_project.get_mapping_for_ai_frame.return_value = None
        mock_project.remove_ai_frame.return_value = True
        context.project = mock_project

        # Setup services
        ai_frame_service = MagicMock()
        org_service = MagicMock()
        undo_stack = MagicMock()
        get_cmd_ctx = MagicMock()

        # Create facade
        facade = AIFramesFacade(context, signals, ai_frame_service, org_service, undo_stack, get_cmd_ctx)

        # Execute
        facade.remove("frame_id_to_remove")

        # Verify save_requested was emitted
        signals.emit_save_requested.assert_called_once()

    def test_remove_batch_emits_save_requested(self) -> None:
        """Test remove_batch emits save_requested after removing frames."""
        # Setup signals
        signals = MagicMock()

        # Setup context with project
        context = MagicMock()
        mock_project = MagicMock()
        mock_project.get_mapping_for_ai_frame.return_value = None
        mock_project.remove_ai_frame.return_value = True
        context.project = mock_project

        # Setup services
        ai_frame_service = MagicMock()
        org_service = MagicMock()
        undo_stack = MagicMock()
        get_cmd_ctx = MagicMock()

        # Create facade
        facade = AIFramesFacade(context, signals, ai_frame_service, org_service, undo_stack, get_cmd_ctx)

        # Execute
        facade.remove_batch(["frame_id_1", "frame_id_2"])

        # Verify save_requested was emitted
        signals.emit_save_requested.assert_called_once()

    def test_reorder_emits_save_requested(self) -> None:
        """Test reorder emits save_requested after reordering frames."""
        # Setup signals
        signals = MagicMock()

        # Setup context with project
        context = MagicMock()
        context.project = MagicMock()

        # Setup AI frame service
        ai_frame_service = MagicMock()
        ai_frame_service.validate_reorder.return_value = (0, 1)

        # Setup organization service
        org_service = MagicMock()

        # Setup undo stack
        undo_stack = MagicMock()

        # Setup command context
        get_cmd_ctx = MagicMock()

        # Create facade
        facade = AIFramesFacade(context, signals, ai_frame_service, org_service, undo_stack, get_cmd_ctx)

        # Execute
        facade.reorder(0, 1)

        # Verify save_requested was emitted
        signals.emit_save_requested.assert_called_once()


class TestGameFramesFacadeSaveRequested:
    """Test GameFramesFacade methods emit save_requested."""

    def test_remove_emits_save_requested(self) -> None:
        """Test remove emits save_requested after removing game frame."""
        # Setup signals
        signals = MagicMock()

        # Setup context with project
        context = MagicMock()
        mock_project = MagicMock()
        mock_project.mappings = []
        mock_project.remove_game_frame.return_value = True
        context.project = mock_project

        # Setup preview service
        preview_service = MagicMock()

        # Setup organization service, undo stack, command context
        org_service = MagicMock()
        undo_stack = MagicMock()
        get_cmd_ctx = MagicMock()

        # Create facade
        facade = GameFramesFacade(context, signals, preview_service, org_service, undo_stack, get_cmd_ctx)

        # Execute
        facade.remove("game_frame_id")

        # Verify save_requested was emitted
        signals.emit_save_requested.assert_called_once()


class TestPaletteFacadeSaveRequested:
    """Test PaletteFacade methods emit save_requested."""

    def test_set_sheet_palette_emits_save_requested(self) -> None:
        """Test set_sheet_palette emits save_requested after setting palette."""
        # Setup signals (MagicMock auto-creates emit_save_requested)
        signals = MagicMock()

        # Setup context with project
        context = MagicMock()
        context.project = MagicMock()

        # Setup palette service
        palette_service = MagicMock()

        # Create facade
        facade = PaletteFacade(context, signals, palette_service)

        # Mock palette
        mock_palette = MagicMock()

        # Execute
        facade.set_sheet_palette(mock_palette)

        # Verify save_requested was emitted
        signals.emit_save_requested.assert_called_once()

    def test_set_sheet_palette_color_emits_save_requested(self) -> None:
        """Test set_sheet_palette_color emits save_requested after setting color."""
        # Setup signals (MagicMock auto-creates emit_save_requested)
        signals = MagicMock()

        # Setup context with project
        context = MagicMock()
        context.project = MagicMock()

        # Setup palette service
        palette_service = MagicMock()

        # Create facade
        facade = PaletteFacade(context, signals, palette_service)

        # Execute
        facade.set_sheet_palette_color(0, (255, 0, 0))

        # Verify save_requested was emitted
        signals.emit_save_requested.assert_called_once()
