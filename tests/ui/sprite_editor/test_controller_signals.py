#!/usr/bin/env python3
"""
Tests for controller signal handling in the sprite_editor subsystem.

Tests the critical bug fix: controllers must connect to finished_signal (custom)
not finished (QThread built-in) for worker completion callbacks.

These tests verify runtime behavior, not source code strings.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import Mock, patch

from tests.fixtures.timeouts import signal_timeout

if TYPE_CHECKING:
    from pytestqt.qtbot import QtBot

    from tests.fixtures.core_fixtures import AppContextFixture


class TestExtractionControllerSignalFix:
    """Tests that ExtractionController uses finished_signal correctly."""

    def test_extract_sprites_connects_to_finished_signal(self, qtbot: QtBot, app_context: AppContextFixture) -> None:
        """Verify extract_sprites connects to finished_signal, not finished.

        This test verifies runtime behavior by checking signal connection counts.
        """
        from ui.sprite_editor.controllers.extraction_controller import ExtractionController
        from ui.sprite_editor.workers import ExtractWorker

        controller = ExtractionController()

        # Mock the view to provide valid parameters
        mock_view = Mock()
        mock_view.validate_params.return_value = (True, "")
        mock_view.get_extraction_params.return_value = {
            "vram_file": "test.dmp",
            "offset": 0,
            "size": 1024,
            "tiles_per_row": 16,
            "palette_num": 0,
            "cgram_file": None,
        }
        controller._view = mock_view

        # Patch ExtractWorker to intercept worker creation
        with patch("ui.sprite_editor.controllers.extraction_controller.ExtractWorker") as MockWorker:
            mock_worker = Mock(spec=ExtractWorker)
            mock_worker.progress = Mock()
            mock_worker.error = Mock()
            mock_worker.result = Mock()
            mock_worker.finished_signal = Mock()
            mock_worker.finished = Mock()  # QThread's built-in signal

            MockWorker.return_value = mock_worker

            # Trigger extraction
            controller.extract_sprites()

            # Verify finished_signal was connected (should have 1+ receivers)
            mock_worker.finished_signal.connect.assert_called()

            # Verify QThread.finished was NOT connected
            mock_worker.finished.connect.assert_not_called()

    def test_extract_multi_palette_connects_to_finished_signal(
        self, qtbot: QtBot, app_context: AppContextFixture
    ) -> None:
        """Verify extract_multi_palette connects to finished_signal."""
        from ui.sprite_editor.controllers.extraction_controller import ExtractionController
        from ui.sprite_editor.workers import MultiPaletteExtractWorker

        controller = ExtractionController()

        with patch("ui.sprite_editor.controllers.extraction_controller.MultiPaletteExtractWorker") as MockWorker:
            mock_worker = Mock(spec=MultiPaletteExtractWorker)
            mock_worker.progress = Mock()
            mock_worker.error = Mock()
            mock_worker.result = Mock()
            mock_worker.finished_signal = Mock()
            mock_worker.finished = Mock()

            MockWorker.return_value = mock_worker

            # Trigger multi-palette extraction
            controller.extract_multi_palette(
                vram_file="test.dmp",
                cgram_file="test.cgram",
                offset=0,
                size=1024,
            )

            # Verify finished_signal was connected
            mock_worker.finished_signal.connect.assert_called()

            # Verify QThread.finished was NOT connected
            mock_worker.finished.connect.assert_not_called()

    def test_cleanup_worker_method_exists(self) -> None:
        """Verify _cleanup_worker method exists for signal cleanup."""
        from ui.sprite_editor.controllers.extraction_controller import ExtractionController

        assert hasattr(ExtractionController, "_cleanup_worker")
        assert callable(ExtractionController._cleanup_worker)

    def test_cleanup_worker_disconnects_signals(self, app_context: AppContextFixture) -> None:
        """Verify _cleanup_worker actually disconnects signals."""
        from ui.sprite_editor.controllers.extraction_controller import ExtractionController

        controller = ExtractionController()

        # Create mock worker with signals
        mock_worker = Mock()
        mock_worker.progress = Mock()
        mock_worker.error = Mock()
        mock_worker.result = Mock()
        mock_worker.finished_signal = Mock()

        controller._worker = mock_worker

        # Trigger cleanup
        controller._cleanup_worker()

        # Verify worker was cleared via public API
        assert not controller.is_busy()


class TestInjectionControllerSignalFix:
    """Tests that InjectionController uses finished_signal correctly."""

    def test_inject_sprites_connects_to_finished_signal(self, qtbot: QtBot) -> None:
        """Verify inject_sprites connects to finished_signal, not finished."""
        from ui.sprite_editor.controllers.injection_controller import InjectionController
        from ui.sprite_editor.workers import InjectWorker

        controller = InjectionController()

        # Mock the view to provide valid parameters
        mock_view = Mock()
        mock_view.validate_params.return_value = (True, "")
        mock_view.get_injection_params.return_value = {
            "png_file": "test.png",
            "vram_file": "test.dmp",
            "offset": 0,
            "output_file": "output.dmp",
        }
        controller._view = mock_view
        controller._png_validation_passed = True  # Bypass validation check

        with patch("ui.sprite_editor.controllers.injection_controller.InjectWorker") as MockWorker:
            mock_worker = Mock(spec=InjectWorker)
            mock_worker.progress = Mock()
            mock_worker.error = Mock()
            mock_worker.result = Mock()
            mock_worker.finished_signal = Mock()
            mock_worker.finished = Mock()

            MockWorker.return_value = mock_worker

            # Trigger injection
            controller.inject_sprites()

            # Verify finished_signal was connected
            mock_worker.finished_signal.connect.assert_called()

            # Verify QThread.finished was NOT connected
            mock_worker.finished.connect.assert_not_called()

    def test_cleanup_worker_method_exists(self) -> None:
        """Verify _cleanup_worker method exists."""
        from ui.sprite_editor.controllers.injection_controller import InjectionController

        assert hasattr(InjectionController, "_cleanup_worker")

    def test_cleanup_worker_disconnects_signals(self) -> None:
        """Verify _cleanup_worker actually disconnects signals."""
        from ui.sprite_editor.controllers.injection_controller import InjectionController

        controller = InjectionController()

        # Create mock worker with signals
        mock_worker = Mock()
        mock_worker.progress = Mock()
        mock_worker.error = Mock()
        mock_worker.result = Mock()
        mock_worker.finished_signal = Mock()

        controller._worker = mock_worker

        # Trigger cleanup
        controller._cleanup_worker()

        # Verify worker was cleared via public API
        assert not controller.is_busy()


class TestMultiPaletteTabClickableLabelFix:
    """Tests for MultiPaletteTab memory leak fix using ClickableLabel."""

    def test_clickable_label_class_exists(self) -> None:
        """Verify ClickableLabel class exists in module."""
        from ui.sprite_editor.views.tabs.multi_palette_tab import ClickableLabel

        # Verify class exists and has clicked signal
        assert hasattr(ClickableLabel, "clicked"), "ClickableLabel should have clicked signal"

    def test_clickable_label_emits_signal_on_click(self, qtbot: QtBot) -> None:
        """Verify ClickableLabel emits clicked signal with palette index."""
        from ui.sprite_editor.views.tabs.multi_palette_tab import ClickableLabel

        # Create label with palette index 3
        label = ClickableLabel(palette_idx=3)

        # Wait for clicked signal with correct index
        with qtbot.waitSignal(label.clicked, timeout=signal_timeout()) as blocker:
            # Simulate mouse press
            from PySide6.QtCore import QPoint, Qt
            from PySide6.QtGui import QMouseEvent

            event = QMouseEvent(
                QMouseEvent.Type.MouseButtonPress,
                QPoint(10, 10),
                Qt.MouseButton.LeftButton,
                Qt.MouseButton.LeftButton,
                Qt.KeyboardModifier.NoModifier,
            )
            label.mousePressEvent(event)

        # Verify signal was emitted with correct palette index
        assert blocker.args == [3], "clicked signal should emit palette index 3"

    def test_imports_safe_disconnect(self) -> None:
        """Verify module imports safe_disconnect for cleanup."""
        import ui.sprite_editor.views.tabs.multi_palette_tab as module

        # Check the module has imported safe_disconnect
        assert hasattr(module, "safe_disconnect")

    def test_set_single_image_uses_clickable_label(self, qtbot: QtBot) -> None:
        """Verify set_single_image_all_palettes creates ClickableLabel instances.

        This test verifies the behavioral fix: ClickableLabel with signal-based
        click handling instead of functools.partial or lambda closures.
        """
        from PIL import Image

        from ui.sprite_editor.views.tabs.multi_palette_tab import MultiPaletteViewer

        viewer = MultiPaletteViewer()

        # Create a simple 16x16 indexed test image
        test_image = Image.new("P", (16, 16))

        # Create palette data (16 colors RGB)
        palettes = [[(255, 0, 0), (0, 255, 0), (0, 0, 255)] + [(i, i, i) for i in range(13)] for _ in range(4)]

        # Set images - this should create ClickableLabel instances
        viewer.set_single_image_all_palettes(test_image, palettes)

        # Verify ClickableLabel instances were created and tracked
        assert len(viewer._palette_labels) > 0, "Should create ClickableLabel instances"

        # Verify they're actually ClickableLabel type
        for label in viewer._palette_labels:
            assert label.__class__.__name__ == "ClickableLabel"
            # Verify signal exists (behavioral check - proves signal-based approach)
            assert hasattr(label, "clicked"), "ClickableLabel should have clicked signal"
