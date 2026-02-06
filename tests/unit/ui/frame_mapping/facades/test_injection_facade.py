"""Tests for InjectionFacade.inject_mapping()."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from core.frame_mapping_project import (
    AIFrame,
    FrameMapping,
    FrameMappingProject,
    GameFrame,
    MappingStatus,
)
from core.services.injection_results import InjectionResult
from ui.frame_mapping.facades.controller_context import ControllerContext
from ui.frame_mapping.facades.injection_facade import InjectionFacade


@pytest.fixture
def mock_signals() -> MagicMock:
    """Create mock signals protocol."""
    signals = MagicMock()
    signals.emit_status_update = MagicMock()
    signals.emit_stale_entries_warning = MagicMock()
    signals.emit_mapping_injected = MagicMock()
    signals.emit_error = MagicMock()
    signals.emit_project_changed = MagicMock()
    signals.emit_save_requested = MagicMock()
    return signals


@pytest.fixture
def mock_orchestrator() -> MagicMock:
    """Create mock injection orchestrator."""
    orchestrator = MagicMock()
    return orchestrator


@pytest.fixture
def mock_async_service() -> MagicMock:
    """Create mock async injection service."""
    service = MagicMock()
    service.is_busy = False
    service.pending_count = 0
    return service


@pytest.fixture
def mock_palette_calculator_getter() -> MagicMock:
    """Create mock palette offset calculator getter."""
    calculator = MagicMock()
    calculator.calculate = MagicMock(return_value=0x1000)
    getter = MagicMock(return_value=calculator)
    return getter


@pytest.fixture
def test_project(tmp_path: Path) -> FrameMappingProject:
    """Create a test project with mappings."""
    # Create test paths
    ai_frame_path = tmp_path / "ai_frame.png"
    ai_frame_path.write_text("dummy")
    game_frame_path = tmp_path / "game_frame.png"
    game_frame_path.write_text("dummy")

    # Create project
    project = FrameMappingProject(
        name="test_project",
        ai_frames_dir=tmp_path / "ai_frames",
    )

    # Add AI frame
    ai_frame = AIFrame(path=ai_frame_path, index=0, width=16, height=16)
    project.ai_frames.append(ai_frame)

    # Add game frame
    game_frame = GameFrame(
        id="F001",
        rom_offsets=[0x10000],
        capture_path=game_frame_path,
        palette_index=0,
        width=16,
        height=16,
    )
    project.game_frames.append(game_frame)

    # Add mapping
    mapping = FrameMapping(
        ai_frame_id=ai_frame.id,
        game_frame_id=game_frame.id,
        status=MappingStatus.MAPPED,
    )
    project.mappings.append(mapping)

    # Rebuild indices for lookups
    project._rebuild_indices()

    return project


@pytest.fixture
def injection_facade(
    mock_signals: MagicMock,
    mock_orchestrator: MagicMock,
    mock_async_service: MagicMock,
    mock_palette_calculator_getter: MagicMock,
) -> InjectionFacade:
    """Create an InjectionFacade with mocked dependencies."""
    context = ControllerContext()
    facade = InjectionFacade(
        context=context,
        signals=mock_signals,
        injection_orchestrator=mock_orchestrator,
        async_injection_service=mock_async_service,
        palette_offset_calculator_getter=mock_palette_calculator_getter,
    )
    return facade


class TestInjectMapping:
    """Tests for InjectionFacade.inject_mapping()."""

    def test_returns_false_when_no_project(
        self,
        injection_facade: InjectionFacade,
        mock_signals: MagicMock,
        tmp_path: Path,
    ) -> None:
        """inject_mapping returns False and emits error when no project loaded."""
        # Ensure no project is loaded
        rom_path = tmp_path / "rom.smc"
        rom_path.write_text("dummy")

        with patch("ui.frame_mapping.facades.injection_facade.managed_debug_context"):
            result = injection_facade.inject_mapping(
                ai_frame_id="test.png",
                rom_path=rom_path,
            )

        assert result is False
        mock_signals.emit_error.assert_called_once_with("No project loaded")

    def test_successful_injection_updates_status(
        self,
        injection_facade: InjectionFacade,
        test_project: FrameMappingProject,
        mock_orchestrator: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Successful injection updates mapping status to INJECTED."""
        # Set up context with project
        injection_facade._context.project = test_project
        ai_frame_id = test_project.ai_frames[0].id

        # Mock successful injection result
        success_result = InjectionResult(
            success=True,
            new_mapping_status=MappingStatus.INJECTED,
            messages=("Injection successful",),
        )
        mock_orchestrator.execute.return_value = success_result

        rom_path = tmp_path / "rom.smc"
        rom_path.write_text("dummy")

        with patch("ui.frame_mapping.facades.injection_facade.managed_debug_context"):
            result = injection_facade.inject_mapping(
                ai_frame_id=ai_frame_id,
                rom_path=rom_path,
            )

        assert result is True
        mapping = test_project.get_mapping_for_ai_frame(ai_frame_id)
        assert mapping is not None
        assert mapping.status == MappingStatus.INJECTED

    def test_successful_injection_emits_signals(
        self,
        injection_facade: InjectionFacade,
        test_project: FrameMappingProject,
        mock_orchestrator: MagicMock,
        mock_signals: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Successful injection emits mapping_injected, project_changed, save_requested."""
        # Set up context with project
        injection_facade._context.project = test_project
        ai_frame_id = test_project.ai_frames[0].id

        # Mock successful injection result
        success_result = InjectionResult(
            success=True,
            new_mapping_status=MappingStatus.INJECTED,
            messages=("Injection successful", "Tiles written"),
        )
        mock_orchestrator.execute.return_value = success_result

        rom_path = tmp_path / "rom.smc"
        rom_path.write_text("dummy")

        with patch("ui.frame_mapping.facades.injection_facade.managed_debug_context"):
            injection_facade.inject_mapping(
                ai_frame_id=ai_frame_id,
                rom_path=rom_path,
                emit_project_changed=True,
            )

        # Check signal emissions
        mock_signals.emit_mapping_injected.assert_called_once()
        args = mock_signals.emit_mapping_injected.call_args[0]
        assert args[0] == ai_frame_id
        assert "Injection successful" in args[1]

        mock_signals.emit_project_changed.assert_called_once()
        mock_signals.emit_save_requested.assert_called_once()

    def test_failed_injection_emits_error(
        self,
        injection_facade: InjectionFacade,
        test_project: FrameMappingProject,
        mock_orchestrator: MagicMock,
        mock_signals: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Failed injection emits error signal and returns False."""
        # Set up context with project
        injection_facade._context.project = test_project
        ai_frame_id = test_project.ai_frames[0].id

        # Mock failed injection result
        failure_result = InjectionResult.failure("ROM write failed")
        mock_orchestrator.execute.return_value = failure_result

        rom_path = tmp_path / "rom.smc"
        rom_path.write_text("dummy")

        with patch("ui.frame_mapping.facades.injection_facade.managed_debug_context"):
            result = injection_facade.inject_mapping(
                ai_frame_id=ai_frame_id,
                rom_path=rom_path,
            )

        assert result is False
        mock_signals.emit_error.assert_called_once_with("ROM write failed")

    def test_failed_injection_does_not_update_status(
        self,
        injection_facade: InjectionFacade,
        test_project: FrameMappingProject,
        mock_orchestrator: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Failed injection does not change mapping status."""
        # Set up context with project
        injection_facade._context.project = test_project
        ai_frame_id = test_project.ai_frames[0].id

        # Get initial status
        mapping = test_project.get_mapping_for_ai_frame(ai_frame_id)
        assert mapping is not None
        initial_status = mapping.status

        # Mock failed injection result
        failure_result = InjectionResult.failure("ROM write failed")
        mock_orchestrator.execute.return_value = failure_result

        rom_path = tmp_path / "rom.smc"
        rom_path.write_text("dummy")

        with patch("ui.frame_mapping.facades.injection_facade.managed_debug_context"):
            injection_facade.inject_mapping(
                ai_frame_id=ai_frame_id,
                rom_path=rom_path,
            )

        # Status should be unchanged
        mapping = test_project.get_mapping_for_ai_frame(ai_frame_id)
        assert mapping is not None
        assert mapping.status == initial_status

    def test_stale_entries_emits_warning(
        self,
        injection_facade: InjectionFacade,
        test_project: FrameMappingProject,
        mock_orchestrator: MagicMock,
        mock_signals: MagicMock,
        tmp_path: Path,
    ) -> None:
        """When result has stale entries, emits stale_entries_warning signal."""
        # Set up context with project
        injection_facade._context.project = test_project
        ai_frame_id = test_project.ai_frames[0].id

        # Mock result with stale entries
        stale_result = InjectionResult.stale_entries(
            frame_id="F001",
            error="VRAM entry IDs are stale",
        )
        mock_orchestrator.execute.return_value = stale_result

        rom_path = tmp_path / "rom.smc"
        rom_path.write_text("dummy")

        with patch("ui.frame_mapping.facades.injection_facade.managed_debug_context"):
            result = injection_facade.inject_mapping(
                ai_frame_id=ai_frame_id,
                rom_path=rom_path,
            )

        assert result is False
        mock_signals.emit_stale_entries_warning.assert_called_once_with("F001")
        mock_signals.emit_error.assert_called_once_with("VRAM entry IDs are stale")
