"""Tests for PreviewModule wrapper."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import Mock, patch

import pytest
from PySide6.QtWidgets import QSlider

from tests.fixtures.timeouts import signal_timeout
from ui.common.modules.preview_module import PreviewModule

if TYPE_CHECKING:
    from pytestqt.qtbot import QtBot

pytestmark = pytest.mark.gui


@pytest.fixture
def mock_rom_extractor() -> Mock:
    """Create mock ROMExtractor."""
    extractor = Mock()
    extractor.extract_sprite_at_offset = Mock(return_value=Mock())
    return extractor


@pytest.fixture
def preview_module(qtbot: QtBot, mock_rom_extractor: Mock) -> PreviewModule:
    """Create PreviewModule with mocked dependencies."""
    module = PreviewModule(rom_extractor=mock_rom_extractor)
    # PreviewModule is QObject, not QWidget - no need for addWidget
    # Qt will handle cleanup via parent relationships
    yield module
    # Clean up manually
    module.shutdown()


class TestPreviewModuleInit:
    """Tests for PreviewModule initialization."""

    def test_init_creates_coordinator(self, qtbot: QtBot, mock_rom_extractor: Mock) -> None:
        """Verify module creates SmartPreviewCoordinator."""
        module = PreviewModule(rom_extractor=mock_rom_extractor)

        # Should have coordinator
        assert hasattr(module, "_coordinator")
        assert module._coordinator is not None

        # Cleanup
        module.shutdown()

    def test_init_stores_rom_extractor(self, qtbot: QtBot, mock_rom_extractor: Mock) -> None:
        """Verify module stores ROM extractor reference."""
        module = PreviewModule(rom_extractor=mock_rom_extractor)

        assert module._rom_extractor is mock_rom_extractor

        # Cleanup
        module.shutdown()

    def test_init_connects_signals(self, qtbot: QtBot, mock_rom_extractor: Mock) -> None:
        """Verify module connects coordinator signals."""
        module = PreviewModule(rom_extractor=mock_rom_extractor)

        # Check signals exist
        assert hasattr(module, "preview_ready")
        assert hasattr(module, "preview_cached")
        assert hasattr(module, "preview_error")

        # Cleanup
        module.shutdown()


class TestPreviewModuleRequests:
    """Tests for preview request methods."""

    def test_request_preview_stores_rom_path(self, preview_module: PreviewModule) -> None:
        """Verify request_preview stores ROM path for provider."""
        rom_path = "/path/to/rom.sfc"
        offset = 0x123456

        preview_module.request_preview(offset, rom_path)

        assert preview_module._current_rom_path == rom_path

    @patch("ui.common.modules.preview_module.SmartPreviewCoordinator")
    def test_request_preview_forwards_to_coordinator(
        self, mock_coordinator_class: Mock, qtbot: QtBot, mock_rom_extractor: Mock
    ) -> None:
        """Verify request_preview forwards to coordinator."""
        mock_coordinator = Mock()
        mock_coordinator_class.return_value = mock_coordinator

        module = PreviewModule(rom_extractor=mock_rom_extractor)

        offset = 0x123456
        rom_path = "/path/to/rom.sfc"

        module.request_preview(offset, rom_path)

        # Should call coordinator's request_preview
        mock_coordinator.request_preview.assert_called_once_with(offset)

    @patch("ui.common.modules.preview_module.SmartPreviewCoordinator")
    def test_request_manual_preview_forwards_to_coordinator(
        self, mock_coordinator_class: Mock, qtbot: QtBot, mock_rom_extractor: Mock
    ) -> None:
        """Verify request_manual_preview forwards to coordinator."""
        mock_coordinator = Mock()
        mock_coordinator_class.return_value = mock_coordinator

        module = PreviewModule(rom_extractor=mock_rom_extractor)

        offset = 0x123456
        rom_path = "/path/to/rom.sfc"

        module.request_manual_preview(offset, rom_path)

        # Should call coordinator's request_manual_preview
        mock_coordinator.request_manual_preview.assert_called_once_with(offset)

    @patch("ui.common.modules.preview_module.SmartPreviewCoordinator")
    def test_request_background_preload_forwards_to_coordinator(
        self, mock_coordinator_class: Mock, qtbot: QtBot, mock_rom_extractor: Mock
    ) -> None:
        """Verify request_background_preload forwards to coordinator."""
        mock_coordinator = Mock()
        mock_coordinator_class.return_value = mock_coordinator

        module = PreviewModule(rom_extractor=mock_rom_extractor)

        offset = 0x123456
        rom_path = "/path/to/rom.sfc"

        module.request_background_preload(offset, rom_path)

        # Should call coordinator's request_background_preload
        mock_coordinator.request_background_preload.assert_called_once_with(offset)

    def test_request_background_preload_preserves_current_rom_path(self, preview_module: PreviewModule) -> None:
        """Verify background preload doesn't overwrite current ROM path."""
        # Set initial ROM path
        initial_path = "/path/to/rom1.sfc"
        preview_module.request_preview(0x100000, initial_path)
        assert preview_module._current_rom_path == initial_path

        # Preload should not overwrite
        preload_path = "/path/to/rom2.sfc"
        preview_module.request_background_preload(0x200000, preload_path)
        assert preview_module._current_rom_path == initial_path


class TestPreviewModuleSliderIntegration:
    """Tests for slider integration."""

    @patch("ui.common.modules.preview_module.SmartPreviewCoordinator")
    def test_connect_to_slider_forwards_to_coordinator(
        self, mock_coordinator_class: Mock, qtbot: QtBot, mock_rom_extractor: Mock
    ) -> None:
        """Verify connect_to_slider forwards to coordinator."""
        mock_coordinator = Mock()
        mock_coordinator_class.return_value = mock_coordinator

        module = PreviewModule(rom_extractor=mock_rom_extractor)

        slider = QSlider()
        qtbot.addWidget(slider)

        module.connect_to_slider(slider)

        # Should call coordinator's connect_slider
        mock_coordinator.connect_slider.assert_called_once_with(slider)

    @patch("ui.common.modules.preview_module.SmartPreviewCoordinator")
    def test_set_ui_update_callback_forwards_to_coordinator(
        self, mock_coordinator_class: Mock, qtbot: QtBot, mock_rom_extractor: Mock
    ) -> None:
        """Verify set_ui_update_callback forwards to coordinator."""
        mock_coordinator = Mock()
        mock_coordinator_class.return_value = mock_coordinator

        module = PreviewModule(rom_extractor=mock_rom_extractor)

        callback = Mock()
        module.set_ui_update_callback(callback)

        # Should call coordinator's set_ui_update_callback
        mock_coordinator.set_ui_update_callback.assert_called_once_with(callback)


class TestPreviewModuleSignalForwarding:
    """Tests for signal forwarding from coordinator."""

    def test_preview_ready_signal_forwarded(self, qtbot: QtBot, preview_module: PreviewModule) -> None:
        """Verify preview_ready signal is forwarded from coordinator."""
        # Set up signal spy
        with qtbot.waitSignal(preview_module.preview_ready, timeout=signal_timeout()) as blocker:
            # Emit from coordinator
            # Signal format: (tile_data, width, height, sprite_name, compressed_size, slack_size)
            tile_data = b"\x00\x01\x02"
            width = 8
            height = 8
            sprite_name = "test_sprite"
            compressed_size = 100
            slack_size = 0

            preview_module._coordinator.preview_ready.emit(tile_data, width, height, sprite_name, compressed_size, slack_size)

        # Verify signal was received
        assert blocker.signal_triggered
        assert blocker.args == [tile_data, width, height, sprite_name, compressed_size, slack_size]

    def test_preview_cached_signal_forwarded(self, qtbot: QtBot, preview_module: PreviewModule) -> None:
        """Verify preview_cached signal is forwarded from coordinator."""
        # Set up signal spy
        with qtbot.waitSignal(preview_module.preview_cached, timeout=signal_timeout()) as blocker:
            # Emit from coordinator
            # Signal format: (tile_data, width, height, sprite_name, compressed_size, slack_size)
            tile_data = b"\x00\x01\x02"
            width = 8
            height = 8
            sprite_name = "cached_sprite"
            compressed_size = 100
            slack_size = 0

            preview_module._coordinator.preview_cached.emit(tile_data, width, height, sprite_name, compressed_size, slack_size)

        # Verify signal was received
        assert blocker.signal_triggered
        assert blocker.args == [tile_data, width, height, sprite_name, compressed_size, slack_size]

    def test_preview_error_signal_forwarded(self, qtbot: QtBot, preview_module: PreviewModule) -> None:
        """Verify preview_error signal is forwarded from coordinator."""
        # Set up signal spy
        with qtbot.waitSignal(preview_module.preview_error, timeout=signal_timeout()) as blocker:
            # Emit from coordinator
            error_msg = "Test error message"

            preview_module._coordinator.preview_error.emit(error_msg)

        # Verify signal was received
        assert blocker.signal_triggered
        assert blocker.args == [error_msg]


class TestPreviewModuleROMDataProvider:
    """Tests for ROM data provider."""

    def test_get_rom_data_returns_none_when_no_path(self, preview_module: PreviewModule) -> None:
        """Verify _get_rom_data returns None when no ROM path set."""
        result = preview_module._get_rom_data()
        assert result is None

    def test_get_rom_data_returns_path_and_extractor(
        self, preview_module: PreviewModule, mock_rom_extractor: Mock
    ) -> None:
        """Verify _get_rom_data returns ROM path and extractor."""
        rom_path = "/path/to/rom.sfc"
        preview_module.request_preview(0x123456, rom_path)

        result = preview_module._get_rom_data()

        assert result is not None
        assert result[0] == rom_path
        assert result[1] is mock_rom_extractor


class TestPreviewModuleShutdown:
    """Tests for shutdown and cleanup."""

    @patch("ui.common.modules.preview_module.SmartPreviewCoordinator")
    def test_shutdown_calls_coordinator_cleanup(
        self, mock_coordinator_class: Mock, qtbot: QtBot, mock_rom_extractor: Mock
    ) -> None:
        """Verify shutdown calls coordinator cleanup."""
        mock_coordinator = Mock()
        mock_coordinator_class.return_value = mock_coordinator

        module = PreviewModule(rom_extractor=mock_rom_extractor)

        module.shutdown()

        # Should call coordinator's cleanup
        mock_coordinator.cleanup.assert_called_once()

    def test_cancel_pending_is_noop(self, preview_module: PreviewModule) -> None:
        """Verify cancel_pending is a no-op (coordinator handles internally)."""
        # Should not raise
        preview_module.cancel_pending()


class TestPreviewModuleParenting:
    """Tests for Qt object parenting."""

    def test_coordinator_has_module_as_parent(self, preview_module: PreviewModule) -> None:
        """Verify coordinator is parented to module for cleanup."""
        assert preview_module._coordinator.parent() is preview_module

    def test_module_with_explicit_parent(self, qtbot: QtBot, mock_rom_extractor: Mock) -> None:
        """Verify module accepts explicit parent."""
        parent_widget = QSlider()  # Use any QObject
        qtbot.addWidget(parent_widget)

        module = PreviewModule(rom_extractor=mock_rom_extractor, parent=parent_widget)

        assert module.parent() is parent_widget

        # Cleanup
        module.shutdown()
