"""Unit tests for ExtractionParamsController."""
from __future__ import annotations

import pytest
from PySide6.QtCore import SignalInstance

from ui.controllers.extraction_params_controller import (
    ROM_SIZE_2MB,
    ExtractionParams,
    ExtractionParamsController,
)


class TestExtractionParams:
    """Tests for ExtractionParams dataclass."""

    def test_creation(self) -> None:
        """Should create params with all required fields."""
        params = ExtractionParams(
            rom_path="/path/to/rom.sfc",
            sprite_offset=0x100000,
            sprite_name="test_sprite",
            output_base="output",
            cgram_path="/path/to/cgram.dmp",
        )
        assert params.rom_path == "/path/to/rom.sfc"
        assert params.sprite_offset == 0x100000
        assert params.sprite_name == "test_sprite"
        assert params.output_base == "output"
        assert params.cgram_path == "/path/to/cgram.dmp"

    def test_optional_cgram(self) -> None:
        """Should allow None cgram_path."""
        params = ExtractionParams(
            rom_path="/path/to/rom.sfc",
            sprite_offset=0x100000,
            sprite_name="test_sprite",
            output_base="output",
        )
        assert params.cgram_path is None

    def test_to_dict(self) -> None:
        """Should convert to dict for backward compatibility."""
        params = ExtractionParams(
            rom_path="/path/to/rom.sfc",
            sprite_offset=0x100000,
            sprite_name="test_sprite",
            output_base="output",
            cgram_path="/path/to/cgram.dmp",
        )
        result = params.to_dict()
        assert result["rom_path"] == "/path/to/rom.sfc"
        assert result["sprite_offset"] == 0x100000
        assert result["sprite_name"] == "test_sprite"
        assert result["output_base"] == "output"
        assert result["cgram_path"] == "/path/to/cgram.dmp"

    def test_frozen(self) -> None:
        """Params should be immutable."""
        params = ExtractionParams(
            rom_path="/path/to/rom.sfc",
            sprite_offset=0x100000,
            sprite_name="test_sprite",
            output_base="output",
        )
        with pytest.raises(AttributeError):
            params.rom_path = "/other/path"  # type: ignore[misc]


class TestExtractionParamsControllerInit:
    """Tests for controller initialization."""

    def test_initial_state(self) -> None:
        """Should initialize in preset mode with default offset."""
        controller = ExtractionParamsController()
        assert controller.is_manual_mode is False
        assert controller.manual_offset == ROM_SIZE_2MB

    def test_has_signals(self) -> None:
        """Should have expected signals."""
        controller = ExtractionParamsController()
        assert isinstance(controller.readiness_changed, SignalInstance)
        assert isinstance(controller.mode_changed, SignalInstance)


class TestModeManagement:
    """Tests for mode switching."""

    def test_set_manual_mode(self, qtbot) -> None:
        """Should switch to manual mode and emit signal."""
        controller = ExtractionParamsController()

        with qtbot.waitSignal(controller.mode_changed, timeout=1000) as blocker:
            controller.set_manual_mode(True, offset=0x150000)

        assert blocker.args == [True]
        assert controller.is_manual_mode is True
        assert controller.manual_offset == 0x150000

    def test_set_preset_mode(self, qtbot) -> None:
        """Should switch to preset mode and emit signal."""
        controller = ExtractionParamsController()
        controller._manual_mode = True  # Start in manual mode

        with qtbot.waitSignal(controller.mode_changed, timeout=1000) as blocker:
            controller.set_preset_mode()

        assert blocker.args == [False]
        assert controller.is_manual_mode is False

    def test_set_manual_mode_without_offset(self, qtbot) -> None:
        """Should keep existing offset when not provided."""
        controller = ExtractionParamsController()
        controller._manual_offset = 0x123456

        with qtbot.waitSignal(controller.mode_changed, timeout=1000):
            controller.set_manual_mode(True)

        assert controller.manual_offset == 0x123456

    def test_no_signal_when_mode_unchanged(self, qtbot) -> None:
        """Should not emit signal when mode doesn't change."""
        controller = ExtractionParamsController()
        assert controller.is_manual_mode is False

        # Setting to same mode should not emit
        with qtbot.assertNotEmitted(controller.mode_changed, wait=100):
            controller.set_manual_mode(False)

    def test_set_offset(self) -> None:
        """Should update offset without changing mode."""
        controller = ExtractionParamsController()
        controller.set_offset(0x300000)
        assert controller.manual_offset == 0x300000
        assert controller.is_manual_mode is False  # Mode unchanged


class TestReadinessChecking:
    """Tests for readiness validation."""

    def test_ready_in_preset_mode(self, qtbot) -> None:
        """Should be ready with all requirements in preset mode."""
        controller = ExtractionParamsController()

        with qtbot.waitSignal(controller.readiness_changed, timeout=1000) as blocker:
            result = controller.check_readiness(
                has_rom=True,
                has_sprite=True,
                has_output_name=True,
            )

        assert result.ready is True
        assert blocker.args == [True, ""]

    def test_not_ready_without_rom(self, qtbot) -> None:
        """Should not be ready without ROM."""
        controller = ExtractionParamsController()

        with qtbot.waitSignal(controller.readiness_changed, timeout=1000) as blocker:
            result = controller.check_readiness(
                has_rom=False,
                has_sprite=True,
                has_output_name=True,
            )

        assert result.ready is False
        assert "Load a ROM file" in result.reasons
        assert blocker.args[0] is False

    def test_not_ready_without_sprite_in_preset_mode(self, qtbot) -> None:
        """Should not be ready without sprite in preset mode."""
        controller = ExtractionParamsController()

        with qtbot.waitSignal(controller.readiness_changed, timeout=1000) as blocker:
            result = controller.check_readiness(
                has_rom=True,
                has_sprite=False,
                has_output_name=True,
            )

        assert result.ready is False
        assert "Select a sprite preset" in result.reasons
        assert blocker.args[0] is False

    def test_ready_without_sprite_in_manual_mode(self, qtbot) -> None:
        """Should be ready without sprite in manual mode."""
        controller = ExtractionParamsController()
        controller.set_manual_mode(True)

        with qtbot.waitSignal(controller.readiness_changed, timeout=1000) as blocker:
            result = controller.check_readiness(
                has_rom=True,
                has_sprite=False,
                has_output_name=True,
            )

        assert result.ready is True
        assert blocker.args == [True, ""]

    def test_not_ready_without_output_name(self, qtbot) -> None:
        """Should not be ready without output name."""
        controller = ExtractionParamsController()

        with qtbot.waitSignal(controller.readiness_changed, timeout=1000) as blocker:
            result = controller.check_readiness(
                has_rom=True,
                has_sprite=True,
                has_output_name=False,
            )

        assert result.ready is False
        assert "Enter an output name" in result.reasons
        assert blocker.args[0] is False

    def test_no_signal_when_readiness_unchanged(self, qtbot) -> None:
        """Should not emit signal when readiness doesn't change."""
        controller = ExtractionParamsController()

        # First call - should emit
        with qtbot.waitSignal(controller.readiness_changed, timeout=1000):
            controller.check_readiness(
                has_rom=True,
                has_sprite=True,
                has_output_name=True,
            )

        # Same state - should not emit
        with qtbot.assertNotEmitted(controller.readiness_changed, wait=100):
            controller.check_readiness(
                has_rom=True,
                has_sprite=True,
                has_output_name=True,
            )


class TestBuildParams:
    """Tests for building extraction parameters."""

    def test_build_params_preset_mode(self) -> None:
        """Should build params from sprite data in preset mode."""
        controller = ExtractionParamsController()

        params = controller.build_params(
            rom_path="/path/to/rom.sfc",
            output_base="output",
            sprite_data=("kirby", 0x100000),
            cgram_path="/path/to/cgram.dmp",
        )

        assert params is not None
        assert params.rom_path == "/path/to/rom.sfc"
        assert params.sprite_offset == 0x100000
        assert params.sprite_name == "kirby"
        assert params.output_base == "output"
        assert params.cgram_path == "/path/to/cgram.dmp"

    def test_build_params_manual_mode(self) -> None:
        """Should use stored offset in manual mode."""
        controller = ExtractionParamsController()
        controller.set_manual_mode(True, offset=0x250000)

        params = controller.build_params(
            rom_path="/path/to/rom.sfc",
            output_base="output",
            sprite_data=None,  # Not needed in manual mode
        )

        assert params is not None
        assert params.sprite_offset == 0x250000
        assert params.sprite_name == "manual_0x250000"

    def test_build_params_no_rom(self) -> None:
        """Should return None without ROM path."""
        controller = ExtractionParamsController()

        params = controller.build_params(
            rom_path="",
            output_base="output",
            sprite_data=("kirby", 0x100000),
        )

        assert params is None

    def test_build_params_no_sprite_data_preset_mode(self) -> None:
        """Should return None without sprite data in preset mode."""
        controller = ExtractionParamsController()

        params = controller.build_params(
            rom_path="/path/to/rom.sfc",
            output_base="output",
            sprite_data=None,
        )

        assert params is None

    def test_get_params_dict(self) -> None:
        """Should return dict for backward compatibility."""
        controller = ExtractionParamsController()

        result = controller.get_params_dict(
            rom_path="/path/to/rom.sfc",
            output_base="output",
            sprite_data=("kirby", 0x100000),
        )

        assert result is not None
        assert isinstance(result, dict)
        assert result["rom_path"] == "/path/to/rom.sfc"

    def test_get_params_dict_returns_none(self) -> None:
        """Should return None when params can't be built."""
        controller = ExtractionParamsController()

        result = controller.get_params_dict(
            rom_path="",
            output_base="output",
            sprite_data=None,
        )

        assert result is None

    def test_build_params_accepts_path_objects(self, tmp_path) -> None:
        """Should accept Path objects for paths."""
        controller = ExtractionParamsController()

        rom_path = tmp_path / "rom.sfc"
        cgram_path = tmp_path / "cgram.dmp"

        params = controller.build_params(
            rom_path=rom_path,
            output_base="output",
            sprite_data=("kirby", 0x100000),
            cgram_path=cgram_path,
        )

        assert params is not None
        assert params.rom_path == str(rom_path)
        assert params.cgram_path == str(cgram_path)


class TestReset:
    """Tests for controller reset."""

    def test_reset(self, qtbot) -> None:
        """Should reset to initial state."""
        controller = ExtractionParamsController()
        controller._manual_mode = True
        controller._manual_offset = 0x999999

        with qtbot.waitSignal(controller.mode_changed, timeout=1000) as blocker:
            controller.reset()

        assert blocker.args == [False]
        assert controller.is_manual_mode is False
        assert controller.manual_offset == ROM_SIZE_2MB
