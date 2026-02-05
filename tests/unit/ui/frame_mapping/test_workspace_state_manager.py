"""Tests for WorkspaceStateManager."""

from pathlib import Path

import pytest

from ui.frame_mapping.workspace_state_manager import WorkspaceStateManager


class TestWorkspaceStateManagerInit:
    """Test initialization of WorkspaceStateManager."""

    def test_init_with_empty_state(self) -> None:
        """WorkspaceStateManager should initialize with empty state."""
        manager = WorkspaceStateManager()

        # Directory history should be None
        assert manager.last_ai_dir is None
        assert manager.last_capture_dir is None
        assert manager.project_path is None

        # ROM state should be None
        assert manager.rom_path is None
        assert manager.last_injected_rom is None

        # Selection state should be None
        assert manager.selected_ai_frame_id is None
        assert manager.selected_game_id is None
        assert manager.current_canvas_game_id is None

        # Auto-advance should be disabled
        assert manager.auto_advance_enabled is False

        # Stale entry tracking should be None
        assert manager.stale_entry_game_frame_id is None

        # Project identity tracking should be None
        assert manager.previous_project_id is None


class TestDirectoryHistoryManagement:
    """Test directory history management."""

    def test_set_and_get_last_ai_dir(self, tmp_path: Path) -> None:
        """Should set and get last AI directory."""
        manager = WorkspaceStateManager()
        ai_dir = tmp_path / "ai_frames"
        ai_dir.mkdir()

        manager.last_ai_dir = ai_dir
        assert manager.last_ai_dir == ai_dir

    def test_set_and_get_last_capture_dir(self, tmp_path: Path) -> None:
        """Should set and get last capture directory."""
        manager = WorkspaceStateManager()
        capture_dir = tmp_path / "captures"
        capture_dir.mkdir()

        manager.last_capture_dir = capture_dir
        assert manager.last_capture_dir == capture_dir

    def test_set_and_get_project_path(self, tmp_path: Path) -> None:
        """Should set and get project path."""
        manager = WorkspaceStateManager()
        project_path = tmp_path / "project.spritepal-mapping.json"

        manager.project_path = project_path
        assert manager.project_path == project_path

    def test_clear_directory_paths(self) -> None:
        """Should allow clearing directory paths."""
        manager = WorkspaceStateManager()
        manager.last_ai_dir = Path("/tmp/ai")
        manager.last_capture_dir = Path("/tmp/captures")
        manager.project_path = Path("/tmp/project.json")

        # Clear by setting to None
        manager.last_ai_dir = None
        manager.last_capture_dir = None
        manager.project_path = None

        assert manager.last_ai_dir is None
        assert manager.last_capture_dir is None
        assert manager.project_path is None


class TestROMStateManagement:
    """Test ROM state management."""

    def test_set_and_get_rom_path(self, tmp_path: Path) -> None:
        """Should set and get ROM path."""
        manager = WorkspaceStateManager()
        rom_path = tmp_path / "game.sfc"
        rom_path.touch()

        manager.rom_path = rom_path
        assert manager.rom_path == rom_path

    def test_set_and_get_last_injected_rom(self, tmp_path: Path) -> None:
        """Should set and get last injected ROM path."""
        manager = WorkspaceStateManager()
        injected_path = tmp_path / "game_injected.sfc"

        manager.last_injected_rom = injected_path
        assert manager.last_injected_rom == injected_path

    def test_is_rom_valid_when_path_exists(self, tmp_path: Path) -> None:
        """Should return True when ROM path exists."""
        manager = WorkspaceStateManager()
        rom_path = tmp_path / "game.sfc"
        rom_path.touch()

        manager.rom_path = rom_path
        assert manager.is_rom_valid() is True

    def test_is_rom_valid_when_path_does_not_exist(self, tmp_path: Path) -> None:
        """Should return False when ROM path does not exist."""
        manager = WorkspaceStateManager()
        rom_path = tmp_path / "missing.sfc"

        manager.rom_path = rom_path
        assert manager.is_rom_valid() is False

    def test_is_rom_valid_when_path_is_none(self) -> None:
        """Should return False when ROM path is None."""
        manager = WorkspaceStateManager()
        assert manager.is_rom_valid() is False


class TestSelectionStateManagement:
    """Test selection state management."""

    def test_set_and_get_selected_ai_frame_id(self) -> None:
        """Should set and get selected AI frame ID."""
        manager = WorkspaceStateManager()
        frame_id = "sprite_00.png"

        manager.selected_ai_frame_id = frame_id
        assert manager.selected_ai_frame_id == frame_id

    def test_set_and_get_selected_game_id(self) -> None:
        """Should set and get selected game ID."""
        manager = WorkspaceStateManager()
        game_id = "capture_001"

        manager.selected_game_id = game_id
        assert manager.selected_game_id == game_id

    def test_set_and_get_current_canvas_game_id(self) -> None:
        """Should set and get current canvas game ID."""
        manager = WorkspaceStateManager()
        canvas_id = "capture_002"

        manager.current_canvas_game_id = canvas_id
        assert manager.current_canvas_game_id == canvas_id


class TestAutoAdvanceState:
    """Test auto-advance state management."""

    def test_set_and_get_auto_advance_enabled(self) -> None:
        """Should set and get auto-advance enabled state."""
        manager = WorkspaceStateManager()
        assert manager.auto_advance_enabled is False

        manager.auto_advance_enabled = True
        assert manager.auto_advance_enabled is True

        manager.auto_advance_enabled = False
        assert manager.auto_advance_enabled is False


class TestStaleEntryTracking:
    """Test stale entry tracking."""

    def test_set_and_get_stale_entry_game_frame_id(self) -> None:
        """Should set and get stale entry frame ID."""
        manager = WorkspaceStateManager()
        frame_id = "capture_003"

        manager.stale_entry_game_frame_id = frame_id
        assert manager.stale_entry_game_frame_id == frame_id

    def test_clear_stale_entry_game_frame_id(self) -> None:
        """Should allow clearing stale entry frame ID."""
        manager = WorkspaceStateManager()
        manager.stale_entry_game_frame_id = "capture_003"

        manager.stale_entry_game_frame_id = None
        assert manager.stale_entry_game_frame_id is None


class TestProjectIdentityTracking:
    """Test project identity tracking."""

    def test_set_and_get_previous_project_id(self) -> None:
        """Should set and get previous project ID."""
        manager = WorkspaceStateManager()
        project_id = 123456789

        manager.previous_project_id = project_id
        assert manager.previous_project_id == project_id

    def test_clear_previous_project_id(self) -> None:
        """Should allow clearing previous project ID."""
        manager = WorkspaceStateManager()
        manager.previous_project_id = 123456789

        manager.previous_project_id = None
        assert manager.previous_project_id is None
