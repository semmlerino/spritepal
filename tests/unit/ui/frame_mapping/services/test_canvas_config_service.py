"""Tests for CanvasConfigService."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from ui.frame_mapping.services.canvas_config_service import CanvasConfig, CanvasConfigService


class TestCanvasConfig:
    """Tests for CanvasConfig dataclass."""

    def test_default_values(self) -> None:
        """Test default configuration values."""
        config = CanvasConfig()
        assert config.size == 300
        assert config.display_scale == 2
        assert config.tile_calc_debounce_ms == 100
        assert config.preview_debounce_ms == 150
        assert config.pixel_hover_debounce_ms == 50
        assert config.pixel_highlight_debounce_ms == 100

    def test_custom_values(self) -> None:
        """Test custom configuration values."""
        config = CanvasConfig(
            size=400,
            display_scale=4,
            tile_calc_debounce_ms=200,
            preview_debounce_ms=300,
            pixel_hover_debounce_ms=75,
            pixel_highlight_debounce_ms=125,
        )
        assert config.size == 400
        assert config.display_scale == 4
        assert config.tile_calc_debounce_ms == 200
        assert config.preview_debounce_ms == 300
        assert config.pixel_hover_debounce_ms == 75
        assert config.pixel_highlight_debounce_ms == 125


class TestCanvasConfigService:
    """Tests for CanvasConfigService."""

    def test_default_configs_no_state_manager(self) -> None:
        """Test default configs when no state manager provided."""
        service = CanvasConfigService(state_manager=None)

        # Verify workbench defaults
        workbench = service.get_config("workbench")
        assert workbench.size == 300
        assert workbench.display_scale == 2

        # Verify alignment defaults
        alignment = service.get_config("alignment")
        assert alignment.size == 320
        assert alignment.display_scale == 4

        # Verify comparison defaults
        comparison = service.get_config("comparison")
        assert comparison.size == 350
        assert comparison.display_scale == 4

    def test_unknown_canvas_type_returns_workbench_defaults(self) -> None:
        """Test unknown canvas type returns workbench defaults."""
        service = CanvasConfigService(state_manager=None)
        config = service.get_config("unknown_type")
        assert config.size == 300
        assert config.display_scale == 2

    def test_set_display_scale_updates_config(self) -> None:
        """Test setting display scale updates configuration."""
        service = CanvasConfigService(state_manager=None)

        # Update workbench scale
        service.set_display_scale("workbench", 4)
        config = service.get_config("workbench")
        assert config.display_scale == 4

    def test_set_display_scale_clamps_to_valid_range(self) -> None:
        """Test display scale is clamped to [1, 8]."""
        service = CanvasConfigService(state_manager=None)

        # Too small - clamp to 1
        service.set_display_scale("workbench", 0)
        assert service.get_config("workbench").display_scale == 1

        # Too large - clamp to 8
        service.set_display_scale("workbench", 10)
        assert service.get_config("workbench").display_scale == 8

    def test_set_canvas_size_updates_config(self) -> None:
        """Test setting canvas size updates configuration."""
        service = CanvasConfigService(state_manager=None)

        # Update alignment size
        service.set_canvas_size("alignment", 400)
        config = service.get_config("alignment")
        assert config.size == 400

    def test_set_canvas_size_clamps_to_valid_range(self) -> None:
        """Test canvas size is clamped to [50, 1000]."""
        service = CanvasConfigService(state_manager=None)

        # Too small - clamp to 50
        service.set_canvas_size("comparison", 10)
        assert service.get_config("comparison").size == 50

        # Too large - clamp to 1000
        service.set_canvas_size("comparison", 2000)
        assert service.get_config("comparison").size == 1000

    def test_persistence_with_state_manager(self) -> None:
        """Test configuration persistence via ApplicationStateManager."""
        # Create mock state manager
        mock_state = MagicMock()
        mock_state._settings = {}
        mock_state.save_settings = MagicMock()

        # Initialize service
        service = CanvasConfigService(state_manager=mock_state)

        # Update a config
        service.set_display_scale("workbench", 4)

        # Verify save was called
        mock_state.save_settings.assert_called_once()

        # Verify settings structure
        assert "frame_mapping" in mock_state._settings
        assert "canvas_configs" in mock_state._settings["frame_mapping"]
        assert "workbench" in mock_state._settings["frame_mapping"]["canvas_configs"]

        workbench_data = mock_state._settings["frame_mapping"]["canvas_configs"]["workbench"]
        assert workbench_data["display_scale"] == 4

    def test_load_configs_from_state_manager(self) -> None:
        """Test loading configurations from ApplicationStateManager."""
        # Create mock state manager with existing config
        mock_state = MagicMock()
        mock_state._settings = {
            "frame_mapping": {
                "canvas_configs": {
                    "workbench": {
                        "size": 400,
                        "display_scale": 8,
                        "tile_calc_debounce_ms": 200,
                        "preview_debounce_ms": 250,
                        "pixel_hover_debounce_ms": 60,
                        "pixel_highlight_debounce_ms": 110,
                    }
                }
            }
        }
        mock_state.save_settings = MagicMock()

        # Initialize service (should load from state manager)
        service = CanvasConfigService(state_manager=mock_state)

        # Verify loaded config
        workbench = service.get_config("workbench")
        assert workbench.size == 400
        assert workbench.display_scale == 8
        assert workbench.tile_calc_debounce_ms == 200
        assert workbench.preview_debounce_ms == 250

    def test_load_configs_fills_missing_defaults(self) -> None:
        """Test loading configs fills in missing types with defaults."""
        # Create mock state manager with partial config (only workbench)
        mock_state = MagicMock()
        mock_state._settings = {
            "frame_mapping": {
                "canvas_configs": {
                    "workbench": {
                        "size": 400,
                        "display_scale": 8,
                        "tile_calc_debounce_ms": 200,
                        "preview_debounce_ms": 250,
                        "pixel_hover_debounce_ms": 60,
                        "pixel_highlight_debounce_ms": 110,
                    }
                }
            }
        }
        mock_state.save_settings = MagicMock()

        service = CanvasConfigService(state_manager=mock_state)

        # Verify workbench is loaded from state
        workbench = service.get_config("workbench")
        assert workbench.size == 400

        # Verify alignment gets default (not in state)
        alignment = service.get_config("alignment")
        assert alignment.size == 320
        assert alignment.display_scale == 4

    def test_load_configs_handles_invalid_data(self) -> None:
        """Test loading configs gracefully handles invalid data."""
        # Create mock state manager with malformed config
        mock_state = MagicMock()
        mock_state._settings = {
            "frame_mapping": {
                "canvas_configs": {
                    "workbench": "invalid_data",  # Not a dict
                    "alignment": {
                        "size": "not_an_int",  # Wrong type
                    },
                }
            }
        }
        mock_state.save_settings = MagicMock()

        # Should not raise, should use defaults
        service = CanvasConfigService(state_manager=mock_state)

        # Verify defaults are used for invalid entries
        workbench = service.get_config("workbench")
        assert workbench.size == 300  # Default
        assert workbench.display_scale == 2  # Default

    def test_persistence_round_trip(self) -> None:
        """Test full round-trip: save and load configuration."""
        # Create mock state manager
        mock_state = MagicMock()
        mock_state._settings = {}
        mock_state.save_settings = MagicMock()

        # First service: set custom values
        service1 = CanvasConfigService(state_manager=mock_state)
        service1.set_display_scale("workbench", 4)
        service1.set_canvas_size("alignment", 400)

        # Second service: should load the saved values
        service2 = CanvasConfigService(state_manager=mock_state)
        workbench = service2.get_config("workbench")
        alignment = service2.get_config("alignment")

        assert workbench.display_scale == 4
        assert alignment.size == 400

    def test_no_state_manager_no_persistence(self) -> None:
        """Test that changes without state manager don't persist."""
        service1 = CanvasConfigService(state_manager=None)
        service1.set_display_scale("workbench", 4)

        # New service without state manager gets defaults
        service2 = CanvasConfigService(state_manager=None)
        workbench = service2.get_config("workbench")
        assert workbench.display_scale == 2  # Default, not 4
