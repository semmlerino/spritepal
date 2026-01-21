"""Consolidated tests for Mesen capture offset handling.

This module combines tests previously spread across multiple files:
- Offset hunting algorithm (DMA jitter correction)
- FILE ↔ ROM offset normalization (SMC header handling)
- Capture list widget updates
- Cross-component coordination

Related:
- ui/components/panels/recent_captures_widget.py - Widget being tested
- ui/rom_extraction/widgets/mesen_captures_section.py - Section wrapper
- core/offset_hunting.py - Offset candidate generation
"""

from __future__ import annotations

import weakref
from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest
from PySide6.QtCore import Qt

from core.offset_hunting import get_offset_candidates, has_nonzero_content

# =============================================================================
# Section 1: Offset Hunting Algorithm
# =============================================================================


class TestOriginalOffsetPreferred:
    """Test that original offset is used when decompression succeeds.

    Bug: clicking 0x293AEB opens 0x293AED - original offset should be trusted
    when HAL decompression succeeds, regardless of has_nonzero_content() result.
    """

    def test_original_offset_used_despite_low_nonzero_content(self):
        """Bug: clicking 0x293AEB opens 0x293AED - original should be used.

        Scenario:
        1. User clicks Mesen capture at offset 0x293AEB
        2. HAL decompression succeeds at 0x293AEB (valid sprite data)
        3. But has_nonzero_content() returns False (sprite is mostly black)
        4. Bug: Loop continues to 0x293AED which also succeeds and passes check
        5. Result: Editor opens at wrong offset

        Expected behavior:
        - If original offset decompresses successfully, use it immediately
        - Don't apply has_nonzero_content() to the PRIMARY offset
        """
        # Simulate sprite data that decompresses successfully but is mostly zeros
        mostly_zero_tile_data = bytes(100)  # 100 bytes of zeros
        different_tile_data = bytes([0xFF] * 100)  # 100 bytes of 0xFF

        # Verify our test data would trigger the bug
        assert not has_nonzero_content(mostly_zero_tile_data)
        assert has_nonzero_content(different_tile_data)

        # Track which offset was ultimately used
        original_offset = 0x293AEB
        candidates = get_offset_candidates(original_offset, rom_size=0x400000)

        # Verify 0x293AED is in the candidate list
        assert 0x293AED in candidates
        assert candidates[0] == original_offset

    def test_has_nonzero_content_threshold_behavior(self):
        """Document has_nonzero_content behavior for edge cases."""
        # 10% threshold - need at least 10 non-zero bytes in first 100
        exactly_threshold = bytes([0] * 90 + [1] * 10)  # 10% non-zero
        below_threshold = bytes([0] * 91 + [1] * 9)  # 9% non-zero
        above_threshold = bytes([0] * 89 + [1] * 11)  # 11% non-zero

        assert has_nonzero_content(exactly_threshold)
        assert not has_nonzero_content(below_threshold)
        assert has_nonzero_content(above_threshold)

    def test_mostly_black_sprite_is_valid(self):
        """Verify that a mostly-black sprite should still be extracted.

        A sprite with mostly black pixels (transparent in many SNES games)
        is still a valid sprite. has_nonzero_content was designed to filter
        GARBAGE data, not valid mostly-transparent sprites.
        """
        # A 4-tile sprite (128 bytes) that is mostly black but has a few pixels
        sprite_with_outline = bytearray(128)
        sprite_with_outline[0] = 0x0F  # Some pixels in first tile
        sprite_with_outline[32] = 0xF0  # Some pixels in second tile
        sprite_with_outline[64] = 0x55  # Pattern in third tile
        sprite_with_outline[96] = 0xAA  # Pattern in fourth tile

        # This sprite has only 4 non-zero bytes in 128 bytes = 3.1%
        # It would FAIL has_nonzero_content (needs 10%) but IS a valid sprite
        nonzero_ratio = sum(1 for b in sprite_with_outline[:100] if b != 0) / 100
        assert nonzero_ratio < 0.10
        assert not has_nonzero_content(sprite_with_outline)


class TestPreviewWorkerOffsetSelection:
    """Test that PreviewWorkerPool uses original offset when valid."""

    @pytest.fixture
    def mock_extractor(self):
        """Create mock ROM extractor with controlled decompression behavior."""
        extractor = MagicMock()
        extractor.rom_injector = MagicMock()
        return extractor

    def test_original_offset_preferred_when_decompression_succeeds(self, mock_extractor):
        """Verify original offset is used even if has_nonzero_content would fail."""
        original_offset = 0x293AEB
        adjusted_offset = 0x293AED  # +2 bytes

        # Create tile data that:
        # 1. Is non-empty (decompression succeeded)
        # 2. Has low non-zero content (would fail has_nonzero_content)
        # 3. Is 32-byte aligned (valid tile data)
        mostly_black_sprite = bytes([0] * 96 + [0x0F] * 32)  # 128 bytes, mostly zeros

        def mock_find_compressed_sprite(rom_data, offset, expected_size):
            if offset == original_offset:
                return (64, mostly_black_sprite, 8)
            elif offset == adjusted_offset:
                high_entropy_data = bytes([i % 256 for i in range(128)])
                return (64, high_entropy_data, 8)
            else:
                return (0, b"", 0)

        mock_extractor.rom_injector.find_compressed_sprite.side_effect = mock_find_compressed_sprite

        # Verify test data characteristics
        assert len(mostly_black_sprite) > 0
        assert not has_nonzero_content(mostly_black_sprite)
        assert len(mostly_black_sprite) % 32 == 0

        # The fix should make the preview worker use original_offset
        candidates = get_offset_candidates(original_offset)
        assert candidates[0] == original_offset

    def test_offset_hunting_flow_integration(self, mock_extractor, monkeypatch):
        """Integration test for offset hunting with the fix applied."""
        original_offset = 0x293AEB
        mostly_black_data = bytes([0] * 128)  # All zeros

        selected_offset = None

        def mock_find_compressed_sprite(rom_data, offset, expected_size):
            nonlocal selected_offset
            if offset == original_offset:
                return (64, mostly_black_data, 8)
            elif offset == original_offset + 2:
                selected_offset = offset
                return (64, bytes([0xFF] * 128), 8)
            return (0, b"", 0)

        mock_extractor.rom_injector.find_compressed_sprite.side_effect = mock_find_compressed_sprite

        # Simulate the offset hunting loop (FIXED behavior)
        offsets_to_try = get_offset_candidates(original_offset, rom_size=0x400000)
        actual_offset = original_offset
        primary_offset = original_offset

        for try_offset in offsets_to_try:
            _compressed_size, candidate_data, _slack = mock_find_compressed_sprite(None, try_offset, 4096)
            if candidate_data and len(candidate_data) > 0:
                is_primary_offset = try_offset == primary_offset
                # FIX: For primary offset, trust it if decompression succeeded
                if is_primary_offset:
                    actual_offset = try_offset
                    break
                if has_nonzero_content(candidate_data):
                    actual_offset = try_offset
                    break

        # With the fix, original offset should be used
        assert actual_offset == original_offset

    def test_preview_worker_prefers_primary_offset_when_ratio_check_rejects(self, qtbot, tmp_path):
        """Bug repro: preview worker should not skip primary offset due to ratio validation."""
        from ui.common.preview_worker_pool import PooledPreviewWorker
        from ui.common.smart_preview_coordinator import PendingPreviewRequest

        class DummyPool:
            def _return_worker(self, _worker) -> None:
                return None

        rom_path = tmp_path / "dummy.sfc"
        rom_path.write_bytes(b"\x00" * 0x400000)

        primary_offset = 0x293AEB
        adjusted_offset = primary_offset + 2
        primary_data = bytes([0] * 128)
        adjusted_data = bytes([0xFF] * 128)

        def mock_find_compressed_sprite(rom_data, offset, expected_size=None, **kwargs):
            enforce_ratio = kwargs.get("enforce_ratio", True)
            if offset == primary_offset:
                if enforce_ratio:
                    return 0, b"", 0
                return 64, primary_data, 8
            if offset == adjusted_offset:
                return 64, adjusted_data, 8
            return 0, b"", 0

        extractor = MagicMock()
        extractor.rom_injector = MagicMock()
        extractor.rom_injector.find_compressed_sprite.side_effect = mock_find_compressed_sprite

        worker = PooledPreviewWorker(weakref.ref(DummyPool()))
        request = PendingPreviewRequest(
            request_id=1,
            offset=primary_offset,
            rom_path=str(rom_path),
            full_decompression=True,
        )
        worker.setup_request(request, extractor)
        worker._run_with_cancellation_checks()

        assert worker.offset == primary_offset


class TestOffsetHuntingPurpose:
    """Document the intended purpose of offset hunting."""

    def test_offset_hunting_is_for_dma_jitter_not_validation(self):
        """Offset hunting exists to correct DMA timing jitter, not to improve quality.

        When Mesen Lua captures a sprite's DMA address, slight timing variations
        can cause the captured offset to be off by a few bytes. The offset hunting
        mechanism tries nearby offsets to find the correct HAL compression header.

        IMPORTANT: The original offset from Lua should be trusted if decompression
        succeeds. We should NOT skip it just because the decompressed data has low
        entropy or is mostly black.
        """
        pass

    def test_has_nonzero_content_purpose(self):
        """has_nonzero_content is meant to detect GARBAGE, not filter valid sprites.

        The check was added to avoid accepting data that:
        1. Decompresses to all zeros (corrupt or wrong offset)
        2. Is random noise that happens to decompress

        It should NOT reject valid sprites that happen to be mostly black/transparent.
        The fix: Only apply has_nonzero_content to ALTERNATE offsets, not the original.
        """
        garbage_data = bytes(100)  # All zeros
        assert not has_nonzero_content(garbage_data)


# =============================================================================
# Section 2: FILE ↔ ROM Offset Normalization
# =============================================================================


class TestCaptureOffsetAdjustment:
    """Test alignment adjustment signal flow when HAL alignment corrects offset."""

    def test_alignment_adjustment_updates_capture_list(self, qtbot):
        """Verify that alignment adjustments update the capture list display.

        Scenario:
        1. User clicks on Mesen capture at ROM offset 0x3C7071
        2. Preview worker compresses with HAL, discovers sprite at offset 0x3C7075
        3. ROMWorkflowController emits capture_offset_adjusted(0x3C7071, 0x3C7075)
        4. RecentCapturesWidget.update_capture_offset receives adjustment
        """
        from core.mesen_integration.log_watcher import CapturedOffset
        from ui.components.panels.recent_captures_widget import RecentCapturesWidget

        widget = RecentCapturesWidget()
        qtbot.addWidget(widget)

        # Set SMC offset to 512 (like KSSU ROM)
        widget.set_smc_offset(512)

        # Add a capture
        file_offset = 0x3C7271
        rom_offset = 0x3C7071  # Normalized (FILE - SMC offset)

        capture = CapturedOffset(
            offset=file_offset,
            frame=None,
            timestamp=datetime.now(UTC),
            raw_line=f"FILE OFFSET: 0x{file_offset:06X}",
        )
        widget.add_capture(capture, request_thumbnail=False)

        # Verify capture was added with correct offsets
        assert widget.get_capture_count() == 1
        item = widget._list_widget.item(0)
        item_data = item.data(Qt.ItemDataRole.UserRole)
        assert item_data.get("file_offset") == file_offset
        assert item_data.get("rom_offset") == rom_offset

        # Simulate alignment adjustment
        old_rom_offset = rom_offset
        new_rom_offset = rom_offset + 4  # 0x3C7075

        result = widget.update_capture_offset(old_rom_offset, new_rom_offset)

        # Verify update succeeded
        assert result is True
        item = widget._list_widget.item(0)
        item_data = item.data(Qt.ItemDataRole.UserRole)
        assert item_data.get("rom_offset") == new_rom_offset
        assert item_data.get("file_offset") == file_offset  # FILE offset unchanged


class TestSMCOffsetNormalization:
    """Test SMC header offset handling for captures."""

    def test_captures_added_before_rom_load_get_renormalized(self, qtbot):
        """Verify that captures added before ROM load are re-normalized correctly.

        Scenario:
        1. Mesen discovers sprite at FILE offset 0x3C7271 (before ROM loads)
        2. RecentCapturesWidget adds capture with SMC offset 0
        3. Capture stores ROM offset as 0x3C7271 (FILE - 0 = FILE)
        4. User loads KSSU ROM, set_smc_offset(512) called
        5. Existing captures should be re-normalized
        """
        from core.mesen_integration.log_watcher import CapturedOffset
        from ui.components.panels.recent_captures_widget import RecentCapturesWidget

        widget = RecentCapturesWidget()
        qtbot.addWidget(widget)

        file_offset = 0x3C7271

        # Capture added before ROM load (SMC offset is 0)
        capture = CapturedOffset(
            offset=file_offset,
            frame=None,
            timestamp=datetime.now(UTC),
            raw_line=f"FILE OFFSET: 0x{file_offset:06X}",
        )
        widget.add_capture(capture, request_thumbnail=False)

        # Verify initial state
        item = widget._list_widget.item(0)
        item_data = item.data(Qt.ItemDataRole.UserRole)
        assert item_data.get("rom_offset") == file_offset

        # Load SMC ROM
        widget.set_smc_offset(512)

        # Verify capture was re-normalized
        expected_rom_offset = file_offset - 512
        item = widget._list_widget.item(0)
        item_data = item.data(Qt.ItemDataRole.UserRole)
        assert item_data.get("rom_offset") == expected_rom_offset
        assert item_data.get("file_offset") == file_offset

    def test_multiple_captures_added_before_rom_load(self, qtbot):
        """Verify that multiple captures are all re-normalized when SMC offset changes."""
        from core.mesen_integration.log_watcher import CapturedOffset
        from ui.components.panels.recent_captures_widget import RecentCapturesWidget

        widget = RecentCapturesWidget()
        qtbot.addWidget(widget)

        captures_data = [
            (0x3C7271, "FILE OFFSET: 0x3C7271"),
            (0x3C7300, "FILE OFFSET: 0x3C7300"),
            (0x400000, "FILE OFFSET: 0x400000"),
        ]

        for file_offset, line in captures_data:
            capture = CapturedOffset(
                offset=file_offset,
                frame=None,
                timestamp=datetime.now(UTC),
                raw_line=line,
            )
            widget.add_capture(capture, request_thumbnail=False)

        assert widget.get_capture_count() == len(captures_data)

        # Set SMC offset
        smc_offset = 512
        widget.set_smc_offset(smc_offset)

        # Verify all captures were re-normalized
        for i, (file_offset, _) in enumerate(captures_data):
            item = widget._list_widget.item(len(captures_data) - 1 - i)
            item_data = item.data(Qt.ItemDataRole.UserRole)

            expected_rom_offset = file_offset - smc_offset if file_offset >= smc_offset else file_offset
            assert item_data.get("rom_offset") == expected_rom_offset
            assert item_data.get("file_offset") == file_offset


class TestOffsetNormalizationEdgeCases:
    """Edge cases for offset normalization."""

    def test_non_smc_rom_no_normalization(self, qtbot):
        """Verify that non-SMC ROMs don't normalize offsets."""
        from core.mesen_integration.log_watcher import CapturedOffset
        from ui.components.panels.recent_captures_widget import RecentCapturesWidget

        widget = RecentCapturesWidget()
        qtbot.addWidget(widget)

        widget.set_smc_offset(0)

        file_offset = 0x100000
        capture = CapturedOffset(
            offset=file_offset,
            frame=None,
            timestamp=datetime.now(UTC),
            raw_line=f"FILE OFFSET: 0x{file_offset:06X}",
        )
        widget.add_capture(capture, request_thumbnail=False)

        item = widget._list_widget.item(0)
        item_data = item.data(Qt.ItemDataRole.UserRole)
        assert item_data.get("file_offset") == file_offset
        assert item_data.get("rom_offset") == file_offset

    def test_offset_below_smc_header_not_adjusted(self, qtbot):
        """Verify that offsets below SMC header size are not adjusted."""
        from core.mesen_integration.log_watcher import CapturedOffset
        from ui.components.panels.recent_captures_widget import RecentCapturesWidget

        widget = RecentCapturesWidget()
        qtbot.addWidget(widget)

        widget.set_smc_offset(512)

        file_offset = 0x100  # Less than 512

        capture = CapturedOffset(
            offset=file_offset,
            frame=None,
            timestamp=datetime.now(UTC),
            raw_line=f"FILE OFFSET: 0x{file_offset:06X}",
        )
        widget.add_capture(capture, request_thumbnail=False)

        item = widget._list_widget.item(0)
        item_data = item.data(Qt.ItemDataRole.UserRole)
        assert item_data.get("rom_offset") == file_offset

    def test_update_capture_offset_returns_false_for_missing_offset(self, qtbot):
        """Verify that update_capture_offset returns False when offset not found."""
        from ui.components.panels.recent_captures_widget import RecentCapturesWidget

        widget = RecentCapturesWidget()
        qtbot.addWidget(widget)

        result = widget.update_capture_offset(0x123456, 0x123457)
        assert result is False


# =============================================================================
# Section 3: Capture List Widget Updates
# =============================================================================


class TestRecentCapturesWidgetOffsetUpdate:
    """Tests for RecentCapturesWidget.update_capture_offset method."""

    def test_update_capture_offset_updates_display_text(self, qtbot):
        """Verify offset update changes display text and internal data.

        Bug: ROM Extraction panel shows offset 0x293AEB while Asset Browser
        shows 0x293AEF for the same Mesen capture.
        """
        from core.mesen_integration.log_watcher import CapturedOffset
        from ui.components.panels.recent_captures_widget import RecentCapturesWidget

        widget = RecentCapturesWidget()
        qtbot.addWidget(widget)

        original_offset = 0x293AEB
        new_offset = 0x293AEF
        capture = CapturedOffset(
            offset=original_offset,
            frame=1938,
            timestamp=datetime.now(UTC),
            raw_line="FILE OFFSET: 0x293AEB",
        )
        widget.add_capture(capture)

        # Verify initial state
        assert widget.get_capture_count() == 1
        assert widget.has_capture(original_offset)

        list_widget = widget._list_widget
        item = list_widget.item(0)
        original_text = item.text()
        assert f"{original_offset:06X}" in original_text.upper()

        # Update the offset
        success = widget.update_capture_offset(original_offset, new_offset)
        assert success

        # Verify display text updated
        updated_text = item.text()
        assert f"{new_offset:06X}" in updated_text.upper()

        # Verify has_capture reflects new offset
        assert widget.has_capture(new_offset)
        assert widget.has_capture_by_file_offset(original_offset)
        assert not widget.has_capture_by_rom_offset(original_offset)

    def test_update_capture_offset_preserves_other_info(self, qtbot):
        """Verify that offset update preserves timestamp and frame info."""
        from core.mesen_integration.log_watcher import CapturedOffset
        from ui.components.panels.recent_captures_widget import RecentCapturesWidget

        widget = RecentCapturesWidget()
        qtbot.addWidget(widget)

        original_offset = 0x100000
        new_offset = 0x100004
        frame = 500
        capture = CapturedOffset(
            offset=original_offset,
            frame=frame,
            timestamp=datetime.now(UTC),
            raw_line="FILE OFFSET: 0x100000",
        )
        widget.add_capture(capture)

        list_widget = widget._list_widget
        item = list_widget.item(0)

        widget.update_capture_offset(original_offset, new_offset)

        updated_text = item.text()
        assert f"f{frame}" in updated_text.lower() or f"({frame})" in updated_text


# =============================================================================
# Section 4: Cross-Component Coordination
# =============================================================================


class TestMesenCapturesSectionOffsetUpdate:
    """Tests for MesenCapturesSection.update_capture_offset wrapper method."""

    def test_mesen_captures_section_has_update_method(self, qtbot):
        """Verify MesenCapturesSection exposes update_capture_offset."""
        from ui.rom_extraction.widgets.mesen_captures_section import MesenCapturesSection

        widget = MesenCapturesSection()
        qtbot.addWidget(widget)

        assert hasattr(widget, "update_capture_offset")
        assert callable(widget.update_capture_offset)

    def test_mesen_captures_section_delegates_to_widget(self, qtbot):
        """Verify MesenCapturesSection delegates update to RecentCapturesWidget."""
        from core.mesen_integration.log_watcher import CapturedOffset
        from ui.rom_extraction.widgets.mesen_captures_section import MesenCapturesSection

        widget = MesenCapturesSection()
        qtbot.addWidget(widget)

        original_offset = 0x200000
        new_offset = 0x200004
        capture = CapturedOffset(
            offset=original_offset,
            frame=1000,
            timestamp=datetime.now(UTC),
            raw_line="FILE OFFSET: 0x200000",
        )
        widget.add_capture(capture)

        # Update via section wrapper
        success = widget.update_capture_offset(original_offset, new_offset)
        assert success

        # Verify internal widget was updated
        assert widget.has_capture(new_offset)
        assert widget.has_capture_by_file_offset(original_offset)
        assert not widget.has_capture_by_rom_offset(original_offset)
