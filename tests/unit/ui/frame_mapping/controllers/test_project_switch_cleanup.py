"""Tests for project switch cleanup of async services."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from ui.frame_mapping.controllers.frame_mapping_controller import FrameMappingController


class TestProjectSwitchCancellation:
    def test_new_project_cancels_async_injection(self, controller: FrameMappingController) -> None:
        """new_project() should cancel in-flight async injections."""
        with patch.object(controller._async_injection_service, "cancel_all") as mock_cancel:
            controller.new_project("New")
            mock_cancel.assert_called_once()

    def test_new_project_cancels_async_preview(self, controller: FrameMappingController) -> None:
        """new_project() should cancel in-flight async previews."""
        with patch.object(controller._async_preview_service, "cancel") as mock_cancel:
            controller.new_project("New")
            mock_cancel.assert_called_once()

    def test_load_project_cancels_async_services(self, controller: FrameMappingController, tmp_path: Path) -> None:
        """load_project() should cancel async services before loading."""
        # Create a minimal valid project file
        project_file = tmp_path / "test.spritepal-mapping.json"
        project_file.write_text(
            '{"version": 4, "name": "Test", "ai_frames_dir": null, "ai_frames": [], "game_frames": [], "mappings": [], "sheet_palette": null}'
        )

        with (
            patch.object(controller._async_injection_service, "cancel_all") as mock_inj_cancel,
            patch.object(controller._async_preview_service, "cancel") as mock_prev_cancel,
        ):
            controller.load_project(project_file)
            mock_inj_cancel.assert_called_once()
            mock_prev_cancel.assert_called_once()
