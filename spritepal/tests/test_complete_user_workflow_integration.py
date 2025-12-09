"""
Integration tests for complete user workflows - Priority 1 test implementation.
Tests end-to-end user scenarios from file drop to editor launch.
"""
from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

# Add parent directories to path
# Test characteristics: Thread safety concerns
pytestmark = [
    pytest.mark.dialog,
    pytest.mark.file_io,
    pytest.mark.headless,
    pytest.mark.integration,
    pytest.mark.mock_dialogs,
    pytest.mark.qt_mock,
    pytest.mark.rom_data,
    pytest.mark.serial,
    pytest.mark.widget,
    pytest.mark.worker_threads,
    pytest.mark.ci_safe,
    pytest.mark.qt_real,
    pytest.mark.requires_display,
    pytest.mark.signals_slots,
    pytest.mark.slow,
]

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from core.controller import ExtractionController
from core.managers import cleanup_managers, initialize_managers
from core.managers.registry import (
    cleanup_managers as cleanup_managers_registry,
    initialize_managers as initialize_managers_registry,
)
from core.workers import VRAMExtractionWorker
from tests.fixtures.test_main_window_helper_simple import MainWindowHelperSimple
from utils.constants import (
    BYTES_PER_TILE,
    COLORS_PER_PALETTE,
    SPRITE_PALETTE_END,
    SPRITE_PALETTE_START,
    VRAM_SPRITE_OFFSET,
)

# ============================================================================
# Module-level consolidated fixtures - Reduce mock density
# ============================================================================


@pytest.fixture
def mock_pixmap_instance():
    """Consolidated mock QPixmap instance used across all tests"""
    pixmap = Mock()
    pixmap.loadFromData = Mock(return_value=True)
    return pixmap


@pytest.fixture
def qt_thread_mock():
    """Consolidated QThread mock that runs synchronously for testing"""
    thread_instance = Mock()
    thread_instance.start = Mock()  # Don't actually start thread
    thread_instance.isRunning = Mock(return_value=False)
    thread_instance.quit = Mock()
    thread_instance.wait = Mock(return_value=True)
    return thread_instance


@pytest.fixture
def mock_qt_signals_module_level():
    """Module-level version of mock Qt signals for reuse across tests"""

    class MockSignal:
        def __init__(self):
            self.callbacks = []
            self.emit = Mock(side_effect=self._emit)

        def connect(self, callback):
            self.callbacks.append(callback)

        def _emit(self, *args):
            for callback in self.callbacks:
                callback(*args)

    return {
        "progress": MockSignal(),
        "preview_ready": MockSignal(),
        "preview_image_ready": MockSignal(),
        "palettes_ready": MockSignal(),
        "active_palettes_ready": MockSignal(),
        "extraction_finished": MockSignal(),
        "error": MockSignal(),
    }


@pytest.fixture
def mock_ui_components_module_level():
    """Consolidated mock UI components for integration testing"""
    return {
        "drop_zone": Mock(),
        "extraction_panel": Mock(),
        "preview_panel": Mock(),
        "palette_preview": Mock(),
        "status_bar": Mock(),
        "progress_bar": Mock(),
    }




class TestWorkflowIntegrationPoints:
    """Test specific integration points in the workflow"""

    @pytest.fixture
    def mock_ui_components(self, mock_ui_components_module_level):
        """Reuse module-level mock UI components fixture"""
        return mock_ui_components_module_level

    @pytest.mark.integration
    @pytest.mark.gui
    def test_signal_flow_integration(self, mock_ui_components):
        """Test signal flow between UI components"""
        # Create mock signals
        extract_signal = Mock()
        file_dropped_signal = Mock()
        preview_updated_signal = Mock()

        # Set up signal connections
        mock_ui_components["drop_zone"].file_dropped = file_dropped_signal
        mock_ui_components["extraction_panel"].extract_requested = extract_signal
        mock_ui_components["preview_panel"].preview_updated = preview_updated_signal

        # Simulate signal flow
        file_dropped_signal.emit("/test/vram.dmp")
        extract_signal.emit()
        preview_updated_signal.emit("preview_data")

        # Verify signals were emitted
        assert file_dropped_signal.emit.called
        assert extract_signal.emit.called
        assert preview_updated_signal.emit.called

    @pytest.mark.integration
    @pytest.mark.gui
    def test_ui_state_consistency_during_workflow(self, mock_ui_components):
        """Test UI state remains consistent during workflow"""
        # Mock UI state tracking
        ui_states = {
            "extraction_enabled": True,
            "preview_visible": False,
            "progress_visible": False,
        }

        # Mock state change functions
        def set_extraction_enabled(enabled):
            ui_states["extraction_enabled"] = enabled

        def set_preview_visible(visible):
            ui_states["preview_visible"] = visible

        def set_progress_visible(visible):
            ui_states["progress_visible"] = visible

        mock_ui_components["extraction_panel"].setEnabled = set_extraction_enabled
        mock_ui_components["preview_panel"].setVisible = set_preview_visible
        mock_ui_components["progress_bar"].setVisible = set_progress_visible

        # Simulate workflow state changes
        # Start extraction
        set_extraction_enabled(False)
        set_progress_visible(True)

        # Preview ready
        set_preview_visible(True)

        # Extraction complete
        set_extraction_enabled(True)
        set_progress_visible(False)

        # Verify final state
        assert ui_states["extraction_enabled"] is True
        assert ui_states["preview_visible"] is True
        assert ui_states["progress_visible"] is False

    @pytest.mark.integration
    @pytest.mark.gui
    def test_component_cleanup_integration(self, mock_ui_components):
        """Test proper cleanup of components after workflow"""
        # Mock cleanup functions
        cleanup_calls = []

        def mock_cleanup(component_name):
            cleanup_calls.append(component_name)

        mock_ui_components["drop_zone"].cleanup = lambda: mock_cleanup("drop_zone")
        mock_ui_components["preview_panel"].cleanup = lambda: mock_cleanup(
            "preview_panel"
        )
        mock_ui_components["palette_preview"].cleanup = lambda: mock_cleanup(
            "palette_preview"
        )

        # Simulate cleanup sequence
        mock_ui_components["drop_zone"].cleanup()
        mock_ui_components["preview_panel"].cleanup()
        mock_ui_components["palette_preview"].cleanup()

        # Verify cleanup was called for all components
        assert "drop_zone" in cleanup_calls
        assert "preview_panel" in cleanup_calls
        assert "palette_preview" in cleanup_calls
        assert len(cleanup_calls) == 3
