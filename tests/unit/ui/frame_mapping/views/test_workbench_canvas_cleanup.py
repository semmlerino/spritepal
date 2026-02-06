"""Tests for WorkbenchCanvas async cleanup on clear."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from ui.frame_mapping.views.workbench_canvas import WorkbenchCanvas


class TestWorkbenchCanvasCleanup:
    def test_clear_cancels_async_services(self, qtbot: object) -> None:
        """clear() should cancel async preview and highlight services."""
        canvas = WorkbenchCanvas()

        with (
            patch.object(canvas._async_preview_service, "cancel") as mock_preview_cancel,
            patch.object(canvas._async_highlight_service, "cancel") as mock_highlight_cancel,
        ):
            canvas.clear()
            mock_preview_cancel.assert_called_once()
            mock_highlight_cancel.assert_called_once()
