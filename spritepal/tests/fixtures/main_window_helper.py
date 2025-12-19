"""
Simplified helper for testing MainWindow functionality without creating Qt widgets
"""
from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import Mock

import pytest
from PySide6.QtCore import QObject, Signal

# Systematic pytest markers applied based on test content analysis
pytestmark = [
    pytest.mark.file_io,
    pytest.mark.headless,
    pytest.mark.integration,
    pytest.mark.mock_only,
    pytest.mark.qt_mock,
    pytest.mark.rom_data,
    pytest.mark.widget,
    pytest.mark.cache,
    pytest.mark.ci_safe,
    pytest.mark.signals_slots,
]

class MainWindowHelperSimple(QObject):
    """Simplified helper for MainWindow testing without real Qt widgets"""

    # Define signals that MainWindow has
    extract_requested = Signal()
    open_in_editor_requested = Signal(str)
    arrange_rows_requested = Signal(str)
    arrange_grid_requested = Signal(str)
    inject_requested = Signal()

    def __init__(self, temp_dir: str | None = None):
        """Initialize helper with optional temporary directory"""
        super().__init__()
        self.temp_dir = temp_dir or tempfile.mkdtemp()
        self.temp_path = Path(self.temp_dir)

        # Track state without creating Qt widgets
        self._extracted_files: list[str] = []
        self._output_path = ""
        self._extraction_params: dict[str, Any] = {}
        self._status_message = "Ready to extract sprites"
        self._preview_info_text = "No sprites loaded"

        # Initialize mock components to None
        self._mock_status_bar: Any | None = None
        self._mock_sprite_preview: Any | None = None
        self._mock_palette_preview: Any | None = None
        self._mock_preview_info: Any | None = None
        self._mock_extraction_panel: Any | None = None
        self._mock_preview_coordinator: Any | None = None
        self._mock_status_bar_manager: Any | None = None
        self._mock_rom_extraction_panel: Any | None = None

        # Track signal emissions for testing
        self.signal_emissions: dict[str, list[Any]] = {
            "extract_requested": [],
            "open_in_editor_requested": [],
            "arrange_rows_requested": [],
            "arrange_grid_requested": [],
            "inject_requested": [],
            "extraction_complete": [],
            "extraction_failed": [],
            "status_messages": [],
            "preview_updates": [],
            "palette_updates": []
        }

        # Connect signals to track emissions
        self.extract_requested.connect(lambda: self.signal_emissions["extract_requested"].append(True))
        self.open_in_editor_requested.connect(lambda path: self.signal_emissions["open_in_editor_requested"].append(path))
        self.arrange_rows_requested.connect(lambda path: self.signal_emissions["arrange_rows_requested"].append(path))
        self.arrange_grid_requested.connect(lambda path: self.signal_emissions["arrange_grid_requested"].append(path))
        self.inject_requested.connect(lambda: self.signal_emissions["inject_requested"].append(True))

        # Use TestDataFactory for file creation (DRY consolidation)
        from tests.fixtures.test_data_factory import TestDataFactory

        paths = TestDataFactory.create_test_files(self.temp_path)
        self.vram_file = paths.vram_path
        self.cgram_file = paths.cgram_path
        self.oam_file = paths.oam_path
        self.rom_file = paths.rom_path

    def get_extraction_params(self) -> dict[str, Any]:
        """Get extraction parameters (mimics MainWindow.get_extraction_params)"""
        # Return default test parameters if none set
        if not self._extraction_params:
            return {
                "vram_path": str(self.vram_file),
                "cgram_path": str(self.cgram_file),
                "output_base": str(self.temp_path / "test_sprite"),
                "create_grayscale": True,
                "create_metadata": True,
                "oam_path": str(self.oam_file),
                "vram_offset": 0xC000,
                "sprite_size": (8, 8),
            }
        return self._extraction_params.copy()

    def set_extraction_params(self, params: dict[str, Any]):
        """Set extraction parameters for testing"""
        self._extraction_params = params.copy()

    def get_output_path(self) -> str:
        """Get output path for extraction (required by MainWindowProtocol)"""
        return self._output_path or str(self.temp_path / "test_output")

    def show_cache_operation_badge(self, badge_text: str) -> None:
        """Show cache operation badge (required by MainWindowProtocol)"""
        self.signal_emissions["status_messages"].append(f"Cache badge: {badge_text}")

    def hide_cache_operation_badge(self) -> None:
        """Hide cache operation badge (required by MainWindowProtocol)"""
        self.signal_emissions["status_messages"].append("Cache badge hidden")

    def update_cache_status(self) -> None:
        """Update cache status (required by MainWindowProtocol)"""
        self.signal_emissions["status_messages"].append("Cache status updated")

    def extraction_complete(self, extracted_files: list[str]):
        """Handle extraction completion (mimics MainWindow.extraction_complete)"""
        self._extracted_files = extracted_files
        self.signal_emissions["extraction_complete"].append(extracted_files)

        # Update status message
        sprite_file = None
        for file_path in extracted_files:
            if file_path.endswith(".png"):
                sprite_file = file_path
                break

        if sprite_file:
            self._preview_info_text = f"Extracted {len(extracted_files)} files"
            self._status_message = "Extraction complete!"
            self.signal_emissions["status_messages"].append("Extraction complete!")
        else:
            self._status_message = "Extraction failed"
            self.signal_emissions["status_messages"].append("Extraction failed")

    def extraction_failed(self, error_message: str):
        """Handle extraction failure (mimics MainWindow.extraction_failed)"""
        self.signal_emissions["extraction_failed"].append(error_message)
        self._status_message = "Extraction failed"
        self.signal_emissions["status_messages"].append("Extraction failed")

    # Mock MainWindow UI component interface
    class MockStatusBar:
        def __init__(self, helper):
            self.helper = helper

        def showMessage(self, message: str):
            self.helper._status_message = message
            self.helper.signal_emissions["status_messages"].append(message)

        def currentMessage(self):
            return self.helper._status_message

    class MockPreviewInfo:
        def __init__(self, helper):
            self.helper = helper

        def setText(self, text: str):
            self.helper._preview_info_text = text

        def text(self):
            return self.helper._preview_info_text

    class MockSpritePreview:
        def __init__(self, helper):
            self.helper = helper

        def set_preview(self, pixmap, tile_count=0):
            self.helper.signal_emissions["preview_updates"].append({"pixmap": pixmap, "tile_count": tile_count})

        def set_palettes(self, palettes):
            self.helper.signal_emissions["palette_updates"].append({"sprite_palettes": palettes})

        def set_grayscale_image(self, pil_image):
            self.helper.signal_emissions["preview_updates"].append({"grayscale_image": pil_image})

    class MockPalettePreview:
        def __init__(self, helper):
            self.helper = helper

        def set_all_palettes(self, palettes_data):
            self.helper.signal_emissions["palette_updates"].append(palettes_data)

        def highlight_active_palettes(self, active_palettes: list[int]):
            self.helper.signal_emissions["palette_updates"].append({"active_palettes": active_palettes})

    class MockExtractionPanel:
        def __init__(self, helper):
            self.helper = helper
            # Mock signal for offset changes
            self.offset_changed = Mock()
            self.offset_changed.connect = Mock()

    class MockPreviewCoordinator:
        def __init__(self, helper):
            self.helper = helper

        @property
        def preview_info(self):
            """Get preview_info for backward compatibility"""
            return self.helper.preview_info

        def update_preview_info(self, text: str):
            """Update preview info text through coordinator"""
            self.helper._preview_info_text = text

    class MockStatusBarManager:
        def __init__(self, helper):
            self.helper = helper

        def show_message(self, message: str):
            self.helper._status_message = message
            self.helper.signal_emissions["status_messages"].append(message)

    class MockROMExtractionPanel:
        def __init__(self, helper):
            self.helper = helper

    @property
    def status_bar(self):
        """Get mock status bar"""
        if self._mock_status_bar is None:
            self._mock_status_bar = self.MockStatusBar(self)
        return self._mock_status_bar

    @property
    def sprite_preview(self):
        """Get mock sprite preview"""
        if self._mock_sprite_preview is None:
            self._mock_sprite_preview = self.MockSpritePreview(self)
        return self._mock_sprite_preview

    @property
    def palette_preview(self):
        """Get mock palette preview"""
        if self._mock_palette_preview is None:
            self._mock_palette_preview = self.MockPalettePreview(self)
        return self._mock_palette_preview

    @property
    def preview_info(self):
        """Get mock preview info"""
        if self._mock_preview_info is None:
            self._mock_preview_info = self.MockPreviewInfo(self)
        return self._mock_preview_info

    @property
    def extraction_panel(self):
        """Get mock extraction panel"""
        if self._mock_extraction_panel is None:
            self._mock_extraction_panel = self.MockExtractionPanel(self)
        return self._mock_extraction_panel

    @property
    def preview_coordinator(self):
        """Get mock preview coordinator"""
        if self._mock_preview_coordinator is None:
            self._mock_preview_coordinator = self.MockPreviewCoordinator(self)
        return self._mock_preview_coordinator

    @property
    def status_bar_manager(self):
        """Get mock status bar manager"""
        if self._mock_status_bar_manager is None:
            self._mock_status_bar_manager = self.MockStatusBarManager(self)
        return self._mock_status_bar_manager

    @property
    def rom_extraction_panel(self):
        """Get mock ROM extraction panel"""
        if self._mock_rom_extraction_panel is None:
            self._mock_rom_extraction_panel = self.MockROMExtractionPanel(self)
        return self._mock_rom_extraction_panel

    def get_extracted_files(self) -> list[str]:
        """Get list of extracted files"""
        return self._extracted_files.copy()

    def get_status_message(self) -> str:
        """Get current status bar message"""
        return self._status_message

    def get_preview_info_text(self) -> str:
        """Get current preview info text"""
        return self._preview_info_text

    def simulate_extract_request(self):
        """Simulate user clicking extract button"""
        self.extract_requested.emit()

    def simulate_open_in_editor_request(self, sprite_path: str):
        """Simulate user requesting to open sprite in editor"""
        self.open_in_editor_requested.emit(sprite_path)

    def simulate_arrange_rows_request(self, sprite_path: str):
        """Simulate user requesting row arrangement"""
        self.arrange_rows_requested.emit(sprite_path)

    def simulate_arrange_grid_request(self, sprite_path: str):
        """Simulate user requesting grid arrangement"""
        self.arrange_grid_requested.emit(sprite_path)

    def clear_signal_tracking(self):
        """Clear signal emission tracking"""
        for key in self.signal_emissions:
            self.signal_emissions[key].clear()

    def get_signal_emissions(self) -> dict[str, list[Any]]:
        """Get copy of signal emissions for testing"""
        return {key: value.copy() for key, value in self.signal_emissions.items()}

    def cleanup(self):
        """Cleanup helper resources"""
        # Cleanup temp files
        import shutil
        try:
            shutil.rmtree(self.temp_dir)
        except Exception:
            pass  # Best effort cleanup

    # Convenience methods for common test scenarios
    def create_vram_extraction_scenario(self) -> dict[str, Any]:
        """Create a typical VRAM extraction scenario"""
        params = {
            "vram_path": str(self.vram_file),
            "cgram_path": str(self.cgram_file),
            "output_base": str(self.temp_path / "vram_extraction"),
            "create_grayscale": True,
            "create_metadata": True,
            "oam_path": str(self.oam_file),
            "vram_offset": 0xC000,
            "sprite_size": (8, 8),
        }
        self.set_extraction_params(params)
        return params

    def create_rom_extraction_scenario(self) -> dict[str, Any]:
        """Create a typical ROM extraction scenario"""
        params = {
            "rom_path": str(self.rom_file),
            "offset": 0x8000,
            "output_base": str(self.temp_path / "rom_extraction"),
            "sprite_name": "test_sprite",
            "cgram_path": str(self.cgram_file),
        }
        self.set_extraction_params(params)
        return params

    def verify_workflow_signals(self, expected_signals: list[str]) -> bool:
        """Verify that expected workflow signals were emitted"""
        for signal_name in expected_signals:
            if signal_name not in self.signal_emissions:
                return False
            if not self.signal_emissions[signal_name]:
                return False
        return True

    def get_workflow_summary(self) -> dict[str, Any]:
        """Get summary of workflow state for testing"""
        return {
            "extracted_files_count": len(self._extracted_files),
            "status_message": self.get_status_message(),
            "preview_info": self.get_preview_info_text(),
            "signals_emitted": {k: len(v) for k, v in self.signal_emissions.items()},
            "has_preview_data": len(self.signal_emissions["preview_updates"]) > 0,
            "has_palette_data": len(self.signal_emissions["palette_updates"]) > 0,
        }
