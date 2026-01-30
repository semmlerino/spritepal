"""Unit tests for PreviewResultProcessor.

Tests the pure decision logic extracted from ROMWorkflowController._on_preview_ready().
"""

import pytest

from core.services.signal_payloads import PreviewData
from core.types import CompressionType
from ui.sprite_editor.services.preview_result_processor import (
    PreviewActions,
    PreviewResultProcessor,
)


class TestPreviewResultProcessor:
    """Tests for PreviewResultProcessor.process()."""

    @pytest.fixture
    def hal_payload(self) -> PreviewData:
        """Create a standard HAL-compressed preview payload."""
        return PreviewData(
            tile_data=b"\x00" * 1024,  # 32 tiles (32 bytes each)
            width=8,
            height=4,
            sprite_name="Test Sprite",
            compressed_size=512,
            slack_size=64,
            actual_offset=0x10000,
            hal_succeeded=True,
            header_bytes=b"",
        )

    @pytest.fixture
    def raw_payload(self) -> PreviewData:
        """Create a raw (non-compressed) preview payload."""
        return PreviewData(
            tile_data=b"\x00" * 512,
            width=4,
            height=4,
            sprite_name="Raw Sprite",
            compressed_size=0,
            slack_size=0,
            actual_offset=0x20000,
            hal_succeeded=False,
            header_bytes=b"",
        )

    def test_process_hal_success_no_adjustment(self, hal_payload: PreviewData) -> None:
        """HAL-compressed preview with no offset adjustment."""
        actions = PreviewResultProcessor.process(
            hal_payload,
            current_offset=0x10000,
            pending_open_in_editor=False,
            pending_open_offset=-1,
        )

        assert actions.offset_adjusted is False
        assert actions.actual_offset == 0x10000
        assert actions.compression_type == CompressionType.HAL
        assert "512 bytes" in actions.status_message
        assert "+64 slack" in actions.status_message
        assert actions.should_auto_open is False
        assert actions.should_warn_unusual_size is False

    def test_process_offset_adjustment(self, hal_payload: PreviewData) -> None:
        """Preview with offset alignment correction."""
        # Simulate preview returning adjusted offset
        actions = PreviewResultProcessor.process(
            hal_payload,  # actual_offset=0x10000
            current_offset=0x0FFFE,  # Original offset was 2 bytes off
            pending_open_in_editor=False,
            pending_open_offset=-1,
        )

        assert actions.offset_adjusted is True
        assert actions.old_offset == 0x0FFFE
        assert actions.actual_offset == 0x10000
        assert actions.offset_delta == 2
        assert "Aligned to 0x010000" in actions.status_message

    def test_process_raw_sprite(self, raw_payload: PreviewData) -> None:
        """Raw (non-HAL) sprite preview."""
        actions = PreviewResultProcessor.process(
            raw_payload,
            current_offset=0x20000,
            pending_open_in_editor=False,
            pending_open_offset=-1,
        )

        assert actions.compression_type == CompressionType.RAW
        assert "Raw sprite data" in actions.status_message
        assert "no HAL compression" in actions.status_message

    def test_process_auto_open_matching_offset(self, hal_payload: PreviewData) -> None:
        """Auto-open triggered with matching offset."""
        actions = PreviewResultProcessor.process(
            hal_payload,
            current_offset=0x10000,
            pending_open_in_editor=True,
            pending_open_offset=0x10000,  # Matches actual_offset
        )

        assert actions.should_auto_open is True

    def test_process_auto_open_any_offset(self, hal_payload: PreviewData) -> None:
        """Auto-open with -1 (any offset) pending."""
        actions = PreviewResultProcessor.process(
            hal_payload,
            current_offset=0x10000,
            pending_open_in_editor=True,
            pending_open_offset=-1,  # Any offset
        )

        assert actions.should_auto_open is True

    def test_process_no_auto_open_offset_mismatch(self, hal_payload: PreviewData) -> None:
        """Auto-open blocked when offset doesn't match."""
        actions = PreviewResultProcessor.process(
            hal_payload,
            current_offset=0x10000,
            pending_open_in_editor=True,
            pending_open_offset=0x20000,  # Different offset
        )

        assert actions.should_auto_open is False

    def test_process_warn_unusual_size(self) -> None:
        """Warn when tile data size is not a multiple of 32."""
        payload = PreviewData(
            tile_data=b"\x00" * 100,  # Not divisible by 32
            width=2,
            height=2,
            sprite_name="Unusual Sprite",
            compressed_size=0,
            slack_size=0,
            actual_offset=0x30000,
            hal_succeeded=False,
            header_bytes=b"",
        )

        actions = PreviewResultProcessor.process(
            payload,
            current_offset=0x30000,
            pending_open_in_editor=True,
            pending_open_offset=-1,
        )

        assert actions.should_warn_unusual_size is True

    def test_process_no_warn_if_no_auto_open(self) -> None:
        """Don't warn about unusual size if not auto-opening."""
        payload = PreviewData(
            tile_data=b"\x00" * 100,  # Not divisible by 32
            width=2,
            height=2,
            sprite_name="Unusual Sprite",
            compressed_size=0,
            slack_size=0,
            actual_offset=0x30000,
            hal_succeeded=False,
            header_bytes=b"",
        )

        actions = PreviewResultProcessor.process(
            payload,
            current_offset=0x30000,
            pending_open_in_editor=False,
            pending_open_offset=-1,
        )

        # Unusual size, but not auto-opening, so no warning needed
        assert actions.should_warn_unusual_size is False

    def test_process_passes_through_payload_fields(self, hal_payload: PreviewData) -> None:
        """All payload fields are correctly passed through to actions."""
        actions = PreviewResultProcessor.process(
            hal_payload,
            current_offset=0x10000,
            pending_open_in_editor=False,
            pending_open_offset=-1,
        )

        assert actions.tile_data == hal_payload.tile_data
        assert actions.width == hal_payload.width
        assert actions.height == hal_payload.height
        assert actions.sprite_name == hal_payload.sprite_name
        assert actions.compressed_size == hal_payload.compressed_size
        assert actions.slack_size == hal_payload.slack_size
        assert actions.header_bytes == hal_payload.header_bytes

    def test_process_default_offset(self) -> None:
        """Use current_offset when payload.actual_offset is -1."""
        payload = PreviewData(
            tile_data=b"\x00" * 64,
            width=2,
            height=1,
            sprite_name="Default Offset",
            compressed_size=32,
            slack_size=0,
            actual_offset=-1,  # Not specified
            hal_succeeded=True,
            header_bytes=b"",
        )

        actions = PreviewResultProcessor.process(
            payload,
            current_offset=0x40000,
            pending_open_in_editor=False,
            pending_open_offset=-1,
        )

        assert actions.actual_offset == 0x40000
        assert actions.offset_adjusted is False


class TestPreviewActionsDataclass:
    """Tests for PreviewActions dataclass properties."""

    def test_preview_actions_is_frozen(self) -> None:
        """PreviewActions should be immutable."""
        actions = PreviewActions(
            offset_adjusted=False,
            old_offset=0,
            actual_offset=0x10000,
            offset_delta=0,
            tile_data=b"",
            width=1,
            height=1,
            sprite_name="",
            compressed_size=0,
            slack_size=0,
            header_bytes=b"",
            compression_type=CompressionType.HAL,
            status_message="",
            should_auto_open=False,
            should_warn_unusual_size=False,
        )

        with pytest.raises(Exception):  # FrozenInstanceError
            actions.actual_offset = 0x20000  # type: ignore[misc]
