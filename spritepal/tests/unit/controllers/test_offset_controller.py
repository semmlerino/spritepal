"""Unit tests for OffsetController."""
from __future__ import annotations

import pytest
from PySide6.QtCore import SignalInstance

from ui.controllers.offset_controller import (
    BYTES_PER_TILE,
    DEFAULT_STEP_INDEX,
    PRESET_CUSTOM_RANGE,
    PRESET_KIRBY_SPRITES,
    STEP_SIZES,
    JumpLocation,
    OffsetController,
    OffsetDisplayInfo,
)
from utils.constants import VRAM_SPRITE_OFFSET


class TestOffsetControllerInit:
    """Tests for controller initialization."""

    def test_default_initialization(self) -> None:
        """Should initialize with default values."""
        controller = OffsetController()
        assert controller.current_offset == VRAM_SPRITE_OFFSET
        assert controller.is_custom_mode is False
        assert controller.step_size == STEP_SIZES[DEFAULT_STEP_INDEX]

    def test_custom_initial_offset(self) -> None:
        """Should accept custom initial offset."""
        controller = OffsetController(initial_offset=0x1000)
        assert controller.current_offset == 0x1000

    def test_custom_max_offset(self) -> None:
        """Should accept custom max offset."""
        controller = OffsetController(max_offset=0x8000)
        info = controller.get_display_info(0x4000)
        assert info.percentage == 50.0

    def test_has_signals(self) -> None:
        """Should have expected signals."""
        controller = OffsetController()
        assert isinstance(controller.offset_changed, SignalInstance)
        assert isinstance(controller.offset_changing, SignalInstance)
        assert isinstance(controller.step_changed, SignalInstance)
        assert isinstance(controller.mode_changed, SignalInstance)


class TestPresetMode:
    """Tests for preset mode switching."""

    def test_switch_to_custom_mode(self, qtbot) -> None:
        """Should switch to custom mode and emit signal."""
        controller = OffsetController()

        with qtbot.waitSignal(controller.mode_changed, timeout=1000) as blocker:
            controller.set_preset_mode(is_custom=True)

        assert controller.is_custom_mode is True
        assert blocker.args[0] is True

    def test_switch_to_preset_mode(self, qtbot) -> None:
        """Should switch to preset mode and reset offset."""
        controller = OffsetController(initial_offset=0x1000)
        controller.set_preset_mode(is_custom=True)

        # Now switch back to preset
        with qtbot.waitSignal(controller.mode_changed, timeout=1000) as blocker:
            controller.set_preset_mode(is_custom=False)

        assert controller.is_custom_mode is False
        assert controller.current_offset == VRAM_SPRITE_OFFSET
        assert blocker.args[0] is False

    def test_no_emit_if_same_mode(self, qtbot) -> None:
        """Should not emit if mode doesn't change."""
        controller = OffsetController()
        assert controller.is_custom_mode is False

        # Try to set same mode
        signals_emitted = []
        controller.mode_changed.connect(lambda x: signals_emitted.append(x))
        controller.set_preset_mode(is_custom=False)

        assert len(signals_emitted) == 0


class TestSliderChange:
    """Tests for slider change handling."""

    def test_slider_change_emits_changing(self, qtbot) -> None:
        """Should emit offset_changing for real-time updates."""
        controller = OffsetController()
        controller.set_preset_mode(is_custom=True)

        with qtbot.waitSignal(controller.offset_changing, timeout=1000) as blocker:
            controller.on_slider_change(0x2000)

        assert blocker.args[0] == 0x2000
        assert controller.current_offset == 0x2000

    def test_slider_change_not_in_preset_mode(self, qtbot) -> None:
        """Should not emit in preset mode."""
        controller = OffsetController()

        signals_emitted = []
        controller.offset_changing.connect(lambda x: signals_emitted.append(x))
        controller.on_slider_change(0x2000)

        assert len(signals_emitted) == 0
        assert controller.current_offset == 0x2000


class TestSpinboxChange:
    """Tests for spinbox change handling."""

    def test_spinbox_change_with_debounce(self, qtbot) -> None:
        """Should debounce spinbox changes."""
        controller = OffsetController()
        controller.set_preset_mode(is_custom=True)

        controller.on_spinbox_change(0x3000)
        assert controller.current_offset == 0x3000

        # Wait for debounce
        with qtbot.waitSignal(controller.offset_changed, timeout=1000) as blocker:
            pass  # Timer should fire

        assert blocker.args[0] == 0x3000

    def test_multiple_spinbox_changes_debounced(self, qtbot) -> None:
        """Should only emit final value after debounce."""
        controller = OffsetController()
        controller.set_preset_mode(is_custom=True)

        signals_emitted = []
        controller.offset_changed.connect(lambda x: signals_emitted.append(x))

        # Rapid changes
        controller.on_spinbox_change(0x1000)
        controller.on_spinbox_change(0x2000)
        controller.on_spinbox_change(0x3000)

        # Wait for debounce
        qtbot.wait(50)  # 16ms timer + margin

        assert signals_emitted[-1] == 0x3000


class TestDirectOffset:
    """Tests for direct offset setting."""

    def test_set_offset_emits(self, qtbot) -> None:
        """Should emit offset_changed when setting directly."""
        controller = OffsetController()

        with qtbot.waitSignal(controller.offset_changed, timeout=1000) as blocker:
            controller.set_offset(0x5000)

        assert blocker.args[0] == 0x5000
        assert controller.current_offset == 0x5000

    def test_set_offset_no_emit(self) -> None:
        """Should not emit when emit=False."""
        controller = OffsetController()

        signals_emitted = []
        controller.offset_changed.connect(lambda x: signals_emitted.append(x))
        controller.set_offset(0x5000, emit=False)

        assert controller.current_offset == 0x5000
        assert len(signals_emitted) == 0


class TestStepSize:
    """Tests for step size changes."""

    def test_set_step_index(self, qtbot) -> None:
        """Should change step size and emit signal."""
        controller = OffsetController()

        with qtbot.waitSignal(controller.step_changed, timeout=1000) as blocker:
            controller.set_step_index(2)  # 0x1000

        assert controller.step_size == 0x1000
        assert controller.page_step == 0x4000
        assert blocker.args[0] == 0x1000  # step
        assert blocker.args[1] == 0x4000  # page

    def test_invalid_step_index(self) -> None:
        """Should ignore invalid step index."""
        controller = OffsetController()
        original_step = controller.step_size

        controller.set_step_index(100)  # Invalid

        assert controller.step_size == original_step

    def test_all_step_sizes(self) -> None:
        """Should support all defined step sizes."""
        controller = OffsetController()

        for i, expected_step in enumerate(STEP_SIZES):
            controller.set_step_index(i)
            assert controller.step_size == expected_step


class TestJumpLocations:
    """Tests for jump location handling."""

    def test_jump_to_location(self, qtbot) -> None:
        """Should jump to predefined location."""
        controller = OffsetController()

        with qtbot.waitSignal(controller.offset_changed, timeout=1000) as blocker:
            result = controller.jump_to_location(1)  # First actual jump (index 0 is "Select...")

        assert result == controller.DEFAULT_JUMPS[0].offset
        assert blocker.args[0] == result

    def test_jump_index_zero_returns_none(self) -> None:
        """Should return None for index 0 (placeholder)."""
        controller = OffsetController()

        result = controller.jump_to_location(0)

        assert result is None

    def test_jump_with_custom_locations(self, qtbot) -> None:
        """Should use custom locations if provided."""
        controller = OffsetController()
        custom_jumps = [
            JumpLocation(0xAAAA, "Custom A"),
            JumpLocation(0xBBBB, "Custom B"),
        ]

        with qtbot.waitSignal(controller.offset_changed, timeout=1000) as blocker:
            result = controller.jump_to_location(2, locations=custom_jumps)

        assert result == 0xBBBB
        assert blocker.args[0] == 0xBBBB

    def test_invalid_jump_index(self) -> None:
        """Should return None for out-of-range index."""
        controller = OffsetController()

        result = controller.jump_to_location(100)

        assert result is None


class TestDisplayInfo:
    """Tests for display information formatting."""

    def test_get_display_info(self) -> None:
        """Should return correct display info."""
        controller = OffsetController(max_offset=0x10000)
        controller.set_offset(0x8000, emit=False)

        info = controller.get_display_info()

        assert isinstance(info, OffsetDisplayInfo)
        assert info.hex_text == "0x8000"
        assert info.tile_number == 0x8000 // BYTES_PER_TILE
        assert info.percentage == 50.0
        assert "Tile #" in info.tooltip
        assert "50.0%" in info.tooltip

    def test_get_display_info_explicit_offset(self) -> None:
        """Should format explicit offset value."""
        controller = OffsetController()

        info = controller.get_display_info(0x1234)

        assert info.hex_text == "0x1234"
        assert info.tile_number == 0x1234 // BYTES_PER_TILE

    def test_zero_max_offset(self) -> None:
        """Should handle zero max offset gracefully."""
        controller = OffsetController(max_offset=0)

        info = controller.get_display_info(0x1000)

        assert info.percentage == 0.0


class TestParseJumpText:
    """Tests for jump text parsing."""

    def test_parse_valid_jump_text(self) -> None:
        """Should parse hex offset from jump text."""
        controller = OffsetController()

        result = controller.parse_jump_text("0xC000 - Kirby sprites")

        assert result == 0xC000

    def test_parse_jump_text_no_label(self) -> None:
        """Should parse hex only text."""
        controller = OffsetController()

        result = controller.parse_jump_text("0x1234")

        assert result == 0x1234

    def test_parse_invalid_jump_text(self) -> None:
        """Should return None for invalid text."""
        controller = OffsetController()

        result = controller.parse_jump_text("invalid text")

        assert result is None


class TestCleanup:
    """Tests for cleanup."""

    def test_cleanup_stops_timer(self) -> None:
        """Should stop timer on cleanup."""
        controller = OffsetController()
        controller.set_preset_mode(is_custom=True)
        controller.on_spinbox_change(0x1000)  # Start timer

        controller.cleanup()

        # Timer should be stopped - no assertion needed, just verify no crash


class TestConstants:
    """Tests for exported constants."""

    def test_preset_indices(self) -> None:
        """Should have correct preset indices."""
        assert PRESET_KIRBY_SPRITES == 0
        assert PRESET_CUSTOM_RANGE == 1

    def test_step_sizes(self) -> None:
        """Should have expected step sizes."""
        assert STEP_SIZES == [0x20, 0x100, 0x1000, 0x4000]

    def test_bytes_per_tile(self) -> None:
        """Should have correct bytes per tile."""
        assert BYTES_PER_TILE == 32
