"""Tests for compression type toggle in the ROM workflow.

These tests verify that users can explicitly choose between HAL compressed
and raw (uncompressed) extraction modes.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest

from core.services.signal_payloads import PreviewData
from core.types import CompressionType
from ui.sprite_editor.views.widgets.source_bar import SourceBar
from ui.sprite_editor.views.workspaces.rom_workflow_page import ROMWorkflowPage

if TYPE_CHECKING:
    from pytestqt.qtbot import QtBot


pytestmark = pytest.mark.gui


# =============================================================================
# SourceBar Tests
# =============================================================================


@pytest.fixture
def source_bar(qtbot: QtBot) -> SourceBar:
    """Create SourceBar widget."""
    widget = SourceBar()
    qtbot.addWidget(widget)
    return widget


class TestSourceBarCompressionDropdown:
    """Tests for the compression type dropdown in SourceBar."""

    def test_dropdown_exists(self, source_bar: SourceBar) -> None:
        """Verify compression dropdown is present."""
        assert hasattr(source_bar, "compression_combo")
        assert source_bar.compression_combo is not None

    def test_dropdown_has_hal_and_raw_options(self, source_bar: SourceBar) -> None:
        """Verify dropdown has both compression options."""
        combo = source_bar.compression_combo
        assert combo.count() == 2

        # Check item data
        hal_index = combo.findData(CompressionType.HAL)
        raw_index = combo.findData(CompressionType.RAW)
        assert hal_index >= 0, "HAL option not found"
        assert raw_index >= 0, "RAW option not found"

    def test_default_is_hal(self, source_bar: SourceBar) -> None:
        """Verify default selection is HAL (compressed)."""
        assert source_bar.get_compression_type() == CompressionType.HAL

    def test_signal_emitted_on_change(self, source_bar: SourceBar, qtbot: QtBot) -> None:
        """Verify signal is emitted when user changes selection."""
        with qtbot.waitSignal(
            source_bar.compression_type_changed,
            check_params_cb=lambda val: val == CompressionType.RAW,
        ):
            # Find and select RAW option
            raw_index = source_bar.compression_combo.findData(CompressionType.RAW)
            source_bar.compression_combo.setCurrentIndex(raw_index)

    def test_set_compression_type_updates_dropdown(self, source_bar: SourceBar) -> None:
        """Verify set_compression_type updates the dropdown selection."""
        source_bar.set_compression_type(CompressionType.RAW)
        assert source_bar.get_compression_type() == CompressionType.RAW

        source_bar.set_compression_type(CompressionType.HAL)
        assert source_bar.get_compression_type() == CompressionType.HAL

    def test_set_compression_type_does_not_emit_signal(self, source_bar: SourceBar, qtbot: QtBot) -> None:
        """Verify programmatic changes don't emit signal (blockSignals)."""
        with qtbot.assertNotEmitted(source_bar.compression_type_changed):
            source_bar.set_compression_type(CompressionType.RAW)


# =============================================================================
# ROMWorkflowPage Tests
# =============================================================================


@pytest.fixture
def rom_workflow_page(qtbot: QtBot) -> ROMWorkflowPage:
    """Create ROMWorkflowPage widget."""
    widget = ROMWorkflowPage()
    qtbot.addWidget(widget)
    return widget


class TestROMWorkflowPageCompressionSignal:
    """Tests for compression signal forwarding in ROMWorkflowPage."""

    def test_signal_forwarded_from_source_bar(self, rom_workflow_page: ROMWorkflowPage, qtbot: QtBot) -> None:
        """Verify page forwards compression_type_changed signal from source bar."""
        with qtbot.waitSignal(
            rom_workflow_page.compression_type_changed,
            check_params_cb=lambda val: val == CompressionType.RAW,
        ):
            # Change source bar dropdown
            source_bar = rom_workflow_page.source_bar
            raw_index = source_bar.compression_combo.findData(CompressionType.RAW)
            source_bar.compression_combo.setCurrentIndex(raw_index)

    def test_facade_methods_exist(self, rom_workflow_page: ROMWorkflowPage) -> None:
        """Verify facade methods exist."""
        assert hasattr(rom_workflow_page, "set_compression_type")
        assert hasattr(rom_workflow_page, "get_compression_type")

    def test_facade_set_compression_type(self, rom_workflow_page: ROMWorkflowPage) -> None:
        """Verify facade set_compression_type works."""
        rom_workflow_page.set_compression_type(CompressionType.RAW)
        assert rom_workflow_page.get_compression_type() == CompressionType.RAW


# =============================================================================
# SmartPreviewCoordinator Tests
# =============================================================================


class TestSmartPreviewCoordinatorCompressionType:
    """Tests for force_compression_type in SmartPreviewCoordinator."""

    def test_set_force_compression_type(self) -> None:
        """Verify set_force_compression_type stores the value."""
        from ui.common.smart_preview_coordinator import SmartPreviewCoordinator

        coordinator = SmartPreviewCoordinator()

        try:
            # Default is None (auto-detect)
            assert coordinator.get_force_compression_type() is None

            # Set to HAL
            coordinator.set_force_compression_type(CompressionType.HAL)
            assert coordinator.get_force_compression_type() == CompressionType.HAL

            # Set to RAW
            coordinator.set_force_compression_type(CompressionType.RAW)
            assert coordinator.get_force_compression_type() == CompressionType.RAW

            # Reset to None
            coordinator.set_force_compression_type(None)
            assert coordinator.get_force_compression_type() is None
        finally:
            coordinator.cleanup()

    def test_cache_key_respects_force_compression_type(self, tmp_path: Path) -> None:
        """Verify cache lookups include the forced compression type."""
        from ui.common.smart_preview_coordinator import SmartPreviewCoordinator

        coordinator = SmartPreviewCoordinator()
        rom_path = tmp_path / "test_rom.sfc"
        rom_path.write_bytes(b"\x00")

        try:
            coordinator.set_rom_data_provider(lambda: (str(rom_path), object()))
            offset = 0x1000
            preview_data = (b"\x01", 8, 8, "sprite", 0, 0, offset, True, b"")
            cache_key = coordinator._cache.make_key(str(rom_path), offset, "hal|preview")
            coordinator._cache.put(cache_key, preview_data)

            coordinator._current_offset = offset
            coordinator.set_force_compression_type(CompressionType.HAL)
            assert coordinator._try_show_cached_preview() is True

            coordinator.set_force_compression_type(CompressionType.RAW)
            assert coordinator._try_show_cached_preview() is False
        finally:
            coordinator.cleanup()

    def test_full_preview_cache_hit_resets_pending_flag(self, tmp_path: Path) -> None:
        """Verify full preview cache hits clear the pending full flag."""
        from ui.common.smart_preview_coordinator import SmartPreviewCoordinator

        coordinator = SmartPreviewCoordinator()
        rom_path = tmp_path / "test_rom.sfc"
        rom_path.write_bytes(b"\x00")

        try:
            coordinator.set_rom_data_provider(lambda: (str(rom_path), object()))
            offset = 0x2000
            preview_data = (b"\x02", 8, 8, "sprite", 0, 0, offset, True, b"")
            cache_key = coordinator._cache.make_key(str(rom_path), offset, "auto|full")
            coordinator._cache.put(cache_key, preview_data)

            coordinator._current_offset = offset
            coordinator._pending_full_decompression = True
            coordinator.set_force_compression_type(None)

            assert coordinator._try_show_cached_preview() is True
            assert coordinator._pending_full_decompression is False
        finally:
            coordinator.cleanup()


# =============================================================================
# SliderPreviewRequest Tests
# =============================================================================


class TestSliderPreviewRequestCompressionType:
    """Tests for force_compression_type in SliderPreviewRequest."""

    def test_default_is_none(self) -> None:
        """Verify default force_compression_type is None."""
        from ui.common.smart_preview_coordinator import SliderPreviewRequest

        request = SliderPreviewRequest(
            request_id=1,
            offset=0x1000,
            rom_path="/path/to/rom.sfc",
        )
        assert request.force_compression_type is None

    def test_can_specify_hal(self) -> None:
        """Verify HAL mode can be specified."""
        from ui.common.smart_preview_coordinator import SliderPreviewRequest

        request = SliderPreviewRequest(
            request_id=1,
            offset=0x1000,
            rom_path="/path/to/rom.sfc",
            force_compression_type=CompressionType.HAL,
        )
        assert request.force_compression_type == CompressionType.HAL

    def test_can_specify_raw(self) -> None:
        """Verify RAW mode can be specified."""
        from ui.common.smart_preview_coordinator import SliderPreviewRequest

        request = SliderPreviewRequest(
            request_id=1,
            offset=0x1000,
            rom_path="/path/to/rom.sfc",
            force_compression_type=CompressionType.RAW,
        )
        assert request.force_compression_type == CompressionType.RAW


# =============================================================================
# PooledPreviewWorker Tests
# =============================================================================


class TestPooledPreviewWorkerCompressionType:
    """Tests for force_compression_type in PooledPreviewWorker."""

    def test_setup_request_stores_force_compression_type(self) -> None:
        """Verify setup_request stores the force_compression_type from request."""
        import weakref

        from ui.common.preview_worker_pool import PooledPreviewWorker, PreviewWorkerPool
        from ui.common.smart_preview_coordinator import SliderPreviewRequest

        # Create a pool and worker
        pool = PreviewWorkerPool(max_workers=1)
        worker = PooledPreviewWorker(weakref.ref(pool))

        try:
            # Create a request with RAW mode
            request = SliderPreviewRequest(
                request_id=1,
                offset=0x1000,
                rom_path="/path/to/rom.sfc",
                force_compression_type=CompressionType.RAW,
            )

            # Mock the extractor
            mock_extractor = MagicMock()

            # Setup the request
            worker.setup_request(request, mock_extractor)

            # Verify the force_compression_type is stored
            assert worker._force_compression_type == CompressionType.RAW
        finally:
            # Cleanup
            pool.cleanup()


# =============================================================================
# ROMWorkflowController Integration Tests
# =============================================================================


class TestROMWorkflowControllerCompressionToggle:
    """Tests for compression toggle handling in ROMWorkflowController."""

    def test_compression_change_updates_coordinator(self, app_context: MagicMock) -> None:
        """Verify compression change updates preview coordinator."""
        from ui.sprite_editor.controllers.rom_workflow_controller import (
            ROMWorkflowController,
        )

        # Create mock editing controller
        mock_editing = MagicMock()

        # Create controller
        controller = ROMWorkflowController(parent=None, editing_controller=mock_editing)

        # Simulate compression type change
        controller._on_compression_type_changed(CompressionType.RAW)

        # Verify user mode is stored
        assert controller._user_compression_mode == CompressionType.RAW

        # Verify coordinator is updated
        assert controller.preview_coordinator.get_force_compression_type() == CompressionType.RAW

    def test_compression_change_triggers_reextraction_when_offset_loaded(self, app_context: MagicMock) -> None:
        """Verify changing compression mode triggers re-extraction if offset is loaded."""
        from ui.sprite_editor.controllers.rom_workflow_controller import (
            ROMWorkflowController,
        )

        # Create mock editing controller
        mock_editing = MagicMock()

        # Create controller
        controller = ROMWorkflowController(parent=None, editing_controller=mock_editing)

        # Set up state as if ROM is loaded with an offset
        controller.rom_path = "/path/to/rom.sfc"
        controller.current_offset = 0x1000

        # Mock the request_full_preview method
        controller.preview_coordinator.request_full_preview = MagicMock()

        # Simulate compression type change
        controller._on_compression_type_changed(CompressionType.RAW)

        # Verify re-extraction was triggered
        controller.preview_coordinator.request_full_preview.assert_called_once_with(0x1000)

    def test_compression_change_reopens_editor_when_editing(self, app_context: MagicMock) -> None:
        """Verify compression toggle reopens the editor when already editing."""
        from ui.sprite_editor.controllers.rom_workflow_controller import (
            ROMWorkflowController,
        )

        # Create mock editing controller
        mock_editing = MagicMock()

        # Create controller
        controller = ROMWorkflowController(parent=None, editing_controller=mock_editing)

        # Simulate edit state with a loaded offset
        controller.state = "edit"
        controller.rom_path = "/path/to/rom.sfc"
        controller.current_offset = 0x1000
        controller._current_source_type = "rom"

        # Mock set_offset to avoid UI side effects
        controller.set_offset = MagicMock()

        # Simulate compression type change
        controller._on_compression_type_changed(CompressionType.RAW)

        # Verify we reopen editor via set_offset
        controller.set_offset.assert_called_once_with(
            0x1000,
            auto_open=True,
            source_type="rom",
        )

    def test_preview_ready_syncs_dropdown(self, app_context: MagicMock) -> None:
        """Verify _on_preview_ready syncs the compression dropdown."""
        from ui.sprite_editor.controllers.rom_workflow_controller import (
            ROMWorkflowController,
        )

        # Create mock editing controller
        mock_editing = MagicMock()

        # Patch SmartPreviewCoordinator to avoid Qt worker initialization
        with patch("ui.sprite_editor.controllers.rom_workflow_controller.SmartPreviewCoordinator"):
            # Create controller
            controller = ROMWorkflowController(parent=None, editing_controller=mock_editing)

            # Create mock view with source bar
            mock_view = MagicMock()
            controller._view = mock_view

            # Simulate preview ready with HAL success
            controller._on_preview_ready(
                PreviewData(
                    tile_data=b"\x00" * 64,
                    width=8,
                    height=8,
                    sprite_name="test_sprite",
                    compressed_size=32,
                    slack_size=0,
                    actual_offset=0x1000,
                    hal_succeeded=True,
                    header_bytes=b"",
                )
            )

            # Verify dropdown was synced to HAL
            mock_view.set_compression_type.assert_called_with(CompressionType.HAL)

            # Now simulate preview ready with RAW (HAL failed)
            controller._on_preview_ready(
                PreviewData(
                    tile_data=b"\x00" * 64,
                    width=8,
                    height=8,
                    sprite_name="test_sprite",
                    compressed_size=0,
                    slack_size=0,
                    actual_offset=0x2000,
                    hal_succeeded=False,
                    header_bytes=b"",
                )
            )

            # Verify dropdown was synced to RAW
            mock_view.set_compression_type.assert_called_with(CompressionType.RAW)

            # Cleanup
            controller.cleanup()
