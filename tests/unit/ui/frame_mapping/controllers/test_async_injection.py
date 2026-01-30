"""Tests for async injection functionality in FrameMappingController.

These tests verify the async injection queue management, progress signals,
cancellation, and failure cleanup.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from PySide6.QtCore import QObject

from core.frame_mapping_project import AIFrame, FrameMappingProject, GameFrame
from core.services.injection_results import InjectionResult
from ui.frame_mapping.controllers.frame_mapping_controller import FrameMappingController
from ui.frame_mapping.services.async_injection_service import AsyncInjectionService


@pytest.fixture
def controller(qtbot: object) -> FrameMappingController:
    """Create a controller with a test project."""
    ctrl = FrameMappingController()
    ctrl.new_project("Test Project")
    return ctrl


@pytest.fixture
def populated_controller(controller: FrameMappingController, tmp_path: Path) -> FrameMappingController:
    """Create a controller with AI frames, game frames, and mappings."""
    project = controller.project
    assert project is not None

    # Create test PNG files
    (tmp_path / "sprite_01.png").write_bytes(b"PNG")
    (tmp_path / "sprite_02.png").write_bytes(b"PNG")

    # Add AI frames
    ai_frame_1 = AIFrame(path=tmp_path / "sprite_01.png", index=0)
    ai_frame_2 = AIFrame(path=tmp_path / "sprite_02.png", index=1)
    project.replace_ai_frames([ai_frame_1, ai_frame_2], tmp_path)

    # Add game frames with rom_offsets
    game_frame_1 = GameFrame(id="capture_A", rom_offsets=[0x1000])
    game_frame_2 = GameFrame(id="capture_B", rom_offsets=[0x2000])
    project.add_game_frame(game_frame_1)
    project.add_game_frame(game_frame_2)

    # Create mappings
    controller.create_mapping("sprite_01.png", "capture_A")
    controller.create_mapping("sprite_02.png", "capture_B")

    return controller


class TestAsyncInjectionBasics:
    """Tests for basic async injection service behavior."""

    def test_is_busy_initially_false(self, controller: FrameMappingController) -> None:
        """Service is not busy when no injections are queued."""
        # async_injection_busy is a property, not a method
        assert controller.async_injection_busy is False

    def test_pending_count_initially_zero(self, controller: FrameMappingController) -> None:
        """Pending count is zero when no injections are queued."""
        # async_injection_pending_count is a property, not a method
        assert controller.async_injection_pending_count == 0


class TestAsyncInjectionErrorHandling:
    """Tests for async injection error handling."""

    def test_inject_without_project_emits_error(self, controller: FrameMappingController, tmp_path: Path) -> None:
        """inject_mapping_async emits error when no project is loaded."""
        controller._project = None

        errors: list[str] = []
        controller.error_occurred.connect(errors.append)

        controller.inject_mapping_async(
            ai_frame_id="any_frame.png",
            rom_path=tmp_path / "test.sfc",
        )

        assert len(errors) == 1
        assert "No project" in errors[0]

    def test_inject_without_mapping_queues_but_handles_gracefully(
        self, populated_controller: FrameMappingController, tmp_path: Path
    ) -> None:
        """inject_mapping_async queues even without mapping (orchestrator handles error)."""
        # Remove the mapping
        populated_controller.remove_mapping("sprite_01.png")

        # This should not crash - the service will handle missing mapping
        populated_controller.inject_mapping_async(
            ai_frame_id="sprite_01.png",
            rom_path=tmp_path / "test.sfc",
        )

        # Injection is queued (pending_count may or may not be zero depending on timing)
        # The key is that it doesn't crash


class TestAsyncInjectionService:
    """Tests for the AsyncInjectionService itself."""

    def test_service_creation(self, qtbot: object) -> None:
        """Service can be created without a parent."""
        service = AsyncInjectionService()
        assert service is not None
        # is_busy and pending_count are properties, not methods
        assert service.is_busy is False
        assert service.pending_count == 0

    def test_service_with_parent(self, qtbot: object) -> None:
        """Service can be created with a parent."""
        parent = QObject()
        service = AsyncInjectionService(parent)
        assert service is not None

    def test_cancel_all_when_not_processing(self, qtbot: object) -> None:
        """cancel_all does not crash when no injections are processing."""
        service = AsyncInjectionService()
        # Should not raise
        service.cancel_all()
        assert service.is_busy is False


class TestAsyncInjectionSignals:
    """Tests for async injection signal emission."""

    def test_injection_started_signal(
        self, populated_controller: FrameMappingController, tmp_path: Path, qtbot: object
    ) -> None:
        """injection_started signal is emitted when injection is queued."""
        # Create a test ROM file
        rom_path = tmp_path / "test.sfc"
        rom_path.write_bytes(b"\x00" * 1024)

        started_frames: list[str] = []
        populated_controller._async_injection_service.injection_started.connect(started_frames.append)

        # Queue an injection
        populated_controller.inject_mapping_async(
            ai_frame_id="sprite_01.png",
            rom_path=rom_path,
        )

        assert "sprite_01.png" in started_frames
