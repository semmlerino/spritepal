#!/usr/bin/env python3
"""
Tests for controller signal handling in the sprite_editor subsystem.

Tests the critical bug fix: controllers must connect to finished_signal (custom)
not finished (QThread built-in) for worker completion callbacks.
"""

from __future__ import annotations

import inspect
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path


class TestExtractionControllerSignalFix:
    """Tests that ExtractionController uses finished_signal correctly."""

    def test_extract_sprites_connects_to_finished_signal(self) -> None:
        """Verify extract_sprites connects to finished_signal, not finished.

        This is a code inspection test that verifies the bug fix is in place.
        """
        from ui.sprite_editor.controllers.extraction_controller import ExtractionController

        # Get the source code of extract_sprites method
        source = inspect.getsource(ExtractionController.extract_sprites)

        # Verify it uses finished_signal, not finished
        assert "finished_signal.connect" in source, "extract_sprites should connect to finished_signal, not finished"
        assert ".finished.connect" not in source, "extract_sprites should NOT connect to QThread.finished"

    def test_extract_multi_palette_connects_to_finished_signal(self) -> None:
        """Verify extract_multi_palette connects to finished_signal."""
        from ui.sprite_editor.controllers.extraction_controller import ExtractionController

        source = inspect.getsource(ExtractionController.extract_multi_palette)

        assert "finished_signal.connect" in source
        assert ".finished.connect" not in source

    def test_cleanup_worker_method_exists(self) -> None:
        """Verify _cleanup_worker method exists for signal cleanup."""
        from ui.sprite_editor.controllers.extraction_controller import ExtractionController

        assert hasattr(ExtractionController, "_cleanup_worker")
        assert callable(ExtractionController._cleanup_worker)

    def test_cleanup_worker_uses_safe_disconnect(self) -> None:
        """Verify _cleanup_worker uses safe_disconnect for signal cleanup."""
        from ui.sprite_editor.controllers.extraction_controller import ExtractionController

        source = inspect.getsource(ExtractionController._cleanup_worker)

        assert "safe_disconnect" in source, "_cleanup_worker should use safe_disconnect for signal cleanup"


class TestInjectionControllerSignalFix:
    """Tests that InjectionController uses finished_signal correctly."""

    def test_inject_sprites_connects_to_finished_signal(self) -> None:
        """Verify inject_sprites connects to finished_signal, not finished."""
        from ui.sprite_editor.controllers.injection_controller import InjectionController

        source = inspect.getsource(InjectionController.inject_sprites)

        assert "finished_signal.connect" in source
        assert ".finished.connect" not in source

    def test_cleanup_worker_method_exists(self) -> None:
        """Verify _cleanup_worker method exists."""
        from ui.sprite_editor.controllers.injection_controller import InjectionController

        assert hasattr(InjectionController, "_cleanup_worker")

    def test_cleanup_worker_uses_safe_disconnect(self) -> None:
        """Verify _cleanup_worker uses safe_disconnect."""
        from ui.sprite_editor.controllers.injection_controller import InjectionController

        source = inspect.getsource(InjectionController._cleanup_worker)

        assert "safe_disconnect" in source


class TestMainControllerTempFiles:
    """Tests for MainController temp file cleanup."""

    def test_temp_file_list_initialized(self) -> None:
        """Test that temp files list is initialized."""
        from ui.sprite_editor.controllers.main_controller import MainController

        controller = MainController()
        assert hasattr(controller, "_temp_files")
        assert isinstance(controller._temp_files, list)
        assert len(controller._temp_files) == 0

    def test_cleanup_temp_files_method_exists(self) -> None:
        """Test that _cleanup_temp_files method exists."""
        from ui.sprite_editor.controllers.main_controller import MainController

        assert hasattr(MainController, "_cleanup_temp_files")

    def test_temp_file_cleanup(self, tmp_path: Path) -> None:
        """Test that temp files are cleaned up."""
        from ui.sprite_editor.controllers.main_controller import MainController

        controller = MainController()

        # Create a temp file manually
        temp_file = tmp_path / "test_temp.png"
        temp_file.write_bytes(b"test")

        # Track it
        controller._temp_files.append(str(temp_file))

        # Verify file exists
        assert temp_file.exists()

        # Cleanup
        controller._cleanup_temp_files()

        # Verify file is gone
        assert not temp_file.exists()
        assert len(controller._temp_files) == 0

    def test_cleanup_handles_missing_files(self, tmp_path: Path) -> None:
        """Test that cleanup handles already-deleted files gracefully."""
        from ui.sprite_editor.controllers.main_controller import MainController

        controller = MainController()

        # Track a non-existent file
        controller._temp_files.append(str(tmp_path / "nonexistent.png"))

        # Cleanup should not raise
        controller._cleanup_temp_files()

        assert len(controller._temp_files) == 0

    def test_injection_completed_triggers_cleanup(self) -> None:
        """Verify _on_injection_completed calls _cleanup_temp_files."""
        from ui.sprite_editor.controllers.main_controller import MainController

        source = inspect.getsource(MainController._on_injection_completed)

        assert "_cleanup_temp_files" in source, "_on_injection_completed should call _cleanup_temp_files"


class TestMultiPaletteTabClickableLabelFix:
    """Tests for MultiPaletteTab memory leak fix using ClickableLabel."""

    def test_uses_clickable_label_not_partial(self) -> None:
        """Verify set_single_image_all_palettes uses ClickableLabel with signals."""
        from ui.sprite_editor.views.tabs.multi_palette_tab import MultiPaletteViewer

        source = inspect.getsource(MultiPaletteViewer.set_single_image_all_palettes)

        # Should use ClickableLabel class
        assert "ClickableLabel" in source, "set_single_image_all_palettes should use ClickableLabel class"

        # Should connect signal instead of monkey-patching
        assert ".clicked.connect" in source, "Should connect clicked signal instead of monkey-patching mousePressEvent"

        # Should NOT use partial (causes circular references)
        assert "partial" not in source, "Should not use functools.partial (causes memory leak)"

        # Should NOT have lambda pattern
        assert "lambda e, idx" not in source, "Should not use lambda with self capture (memory leak)"

    def test_clickable_label_class_exists(self) -> None:
        """Verify ClickableLabel class exists in module."""
        from ui.sprite_editor.views.tabs.multi_palette_tab import ClickableLabel

        assert hasattr(ClickableLabel, "clicked"), "ClickableLabel should have clicked signal"

    def test_imports_safe_disconnect(self) -> None:
        """Verify module imports safe_disconnect for cleanup."""
        import ui.sprite_editor.views.tabs.multi_palette_tab as module

        # Check the module has imported safe_disconnect
        assert hasattr(module, "safe_disconnect")
