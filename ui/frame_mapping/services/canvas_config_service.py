"""Canvas Configuration Service for Frame Mapping subsystem.

Centralizes canvas display constants (size, scale, debounce timers) with
persistence via ApplicationStateManager. Changes persist across sessions but
require app restart to take effect (no runtime updates).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from typing import TYPE_CHECKING

from utils.logging_config import get_logger

if TYPE_CHECKING:
    from typing import ClassVar

    from core.managers.application_state_manager import ApplicationStateManager

logger = get_logger(__name__)


class CanvasType(str, Enum):
    """Canvas configuration type identifiers.

    Uses str mixin so enum values can be used as dict keys and compared with strings.
    """

    WORKBENCH = "workbench"
    ALIGNMENT = "alignment"
    COMPARISON = "comparison"


@dataclass
class CanvasConfig:
    """Configuration for a single canvas instance.

    Attributes:
        size: Canvas size in pixels (displayed size)
        display_scale: Scale factor for pixel art (1x to 8x)
        tile_calc_debounce_ms: Debounce delay for tile touch calculation (ms)
        preview_debounce_ms: Debounce delay for preview generation (ms)
        pixel_hover_debounce_ms: Debounce delay for pixel hover updates (ms)
        pixel_highlight_debounce_ms: Debounce delay for palette highlight mask (ms)
    """

    size: int = 300
    display_scale: int = 2
    tile_calc_debounce_ms: int = 100
    preview_debounce_ms: int = 150
    pixel_hover_debounce_ms: int = 50
    pixel_highlight_debounce_ms: int = 100


class CanvasConfigService:
    """Configuration service for canvas display settings.

    Provides per-canvas-type configuration with persistence. Changes are saved
    to ApplicationStateManager but require app restart to take effect.

    Default configurations:
    - workbench: size=300, display_scale=2 (interactive alignment canvas)
    - alignment: size=320, display_scale=4 (inline alignment editor)
    - comparison: size=350, display_scale=4 (overlay comparison view)
    """

    # Default configurations per canvas type
    _DEFAULT_CONFIGS: ClassVar[dict[CanvasType, CanvasConfig]] = {
        CanvasType.WORKBENCH: CanvasConfig(
            size=300,
            display_scale=2,
            tile_calc_debounce_ms=100,
            preview_debounce_ms=150,
            pixel_hover_debounce_ms=50,
            pixel_highlight_debounce_ms=100,
        ),
        CanvasType.ALIGNMENT: CanvasConfig(
            size=320,
            display_scale=4,
            tile_calc_debounce_ms=100,
            preview_debounce_ms=150,
            pixel_hover_debounce_ms=50,
            pixel_highlight_debounce_ms=100,
        ),
        CanvasType.COMPARISON: CanvasConfig(
            size=350,
            display_scale=4,
            tile_calc_debounce_ms=100,
            preview_debounce_ms=150,
            pixel_hover_debounce_ms=50,
            pixel_highlight_debounce_ms=100,
        ),
    }

    def __init__(self, state_manager: ApplicationStateManager | None = None) -> None:
        """Initialize canvas configuration service.

        Args:
            state_manager: Optional ApplicationStateManager for persistence.
                          If None, changes won't persist across sessions.
        """
        self._state_manager = state_manager
        self._configs = self._load_configs()

    def get_config(self, canvas_type: CanvasType) -> CanvasConfig:
        """Get configuration for a specific canvas type.

        Args:
            canvas_type: Canvas identifier (CanvasType enum)

        Returns:
            CanvasConfig for the specified type, or default if not configured
        """
        if canvas_type not in self._configs:
            # Return default config for this type
            default = self._DEFAULT_CONFIGS.get(canvas_type)
            if default is None:
                logger.warning(
                    "Unknown canvas type '%s', using workbench defaults",
                    canvas_type,
                )
                return self._DEFAULT_CONFIGS[CanvasType.WORKBENCH]
            return default

        return self._configs[canvas_type]

    def set_display_scale(self, canvas_type: CanvasType, scale: int) -> None:
        """Set display scale for a specific canvas type.

        Args:
            canvas_type: Canvas identifier (CanvasType enum)
            scale: Display scale factor (1-8)
        """
        if scale < 1 or scale > 8:
            logger.warning("Invalid display scale %d, clamping to [1, 8]", scale)
            scale = max(1, min(8, scale))

        config = self.get_config(canvas_type)
        config.display_scale = scale
        self._configs[canvas_type] = config
        self._save_configs()
        logger.debug(
            "Updated display scale for %s canvas to %dx",
            canvas_type,
            scale,
        )

    def set_canvas_size(self, canvas_type: CanvasType, size: int) -> None:
        """Set canvas size for a specific canvas type.

        Args:
            canvas_type: Canvas identifier (CanvasType enum)
            size: Canvas size in pixels (50-1000)
        """
        if size < 50 or size > 1000:
            logger.warning("Invalid canvas size %d, clamping to [50, 1000]", size)
            size = max(50, min(1000, size))

        config = self.get_config(canvas_type)
        config.size = size
        self._configs[canvas_type] = config
        self._save_configs()
        logger.debug("Updated canvas size for %s to %dpx", canvas_type, size)

    def _load_configs(self) -> dict[CanvasType, CanvasConfig]:
        """Load canvas configurations from ApplicationStateManager.

        Returns:
            Dictionary of canvas_type -> CanvasConfig (copies, not shared)
        """
        if self._state_manager is None:
            # No persistence - return copies of defaults to avoid sharing
            return {k: CanvasConfig(**asdict(v)) for k, v in self._DEFAULT_CONFIGS.items()}

        try:
            # Load from settings["frame_mapping"]["canvas_configs"]
            # _settings is dict[str, dict[str, object]]
            settings = self._state_manager._settings
            frame_mapping_settings: dict[str, object] = settings.get("frame_mapping", {})

            # canvas_configs should be a dict[str, dict] but stored as object
            canvas_configs_obj = frame_mapping_settings.get("canvas_configs", {})

            configs: dict[CanvasType, CanvasConfig] = {}
            # Runtime check: is canvas_configs_obj actually a dict?
            if isinstance(canvas_configs_obj, dict):
                for canvas_type_str, config_dict in canvas_configs_obj.items():
                    if isinstance(config_dict, dict):
                        try:
                            # Convert string key to enum
                            canvas_type = CanvasType(canvas_type_str)
                            configs[canvas_type] = CanvasConfig(**config_dict)
                        except (ValueError, TypeError) as e:
                            logger.warning(
                                "Failed to load config for %s: %s, using default",
                                canvas_type_str,
                                e,
                            )
                            # Try to match to a known type
                            try:
                                canvas_type = CanvasType(canvas_type_str)
                                if canvas_type in self._DEFAULT_CONFIGS:
                                    configs[canvas_type] = self._DEFAULT_CONFIGS[canvas_type]
                            except ValueError:
                                pass  # Unknown type, skip it

            # Fill in missing defaults (as copies)
            for canvas_type, default_config in self._DEFAULT_CONFIGS.items():
                if canvas_type not in configs:
                    configs[canvas_type] = CanvasConfig(**asdict(default_config))

            logger.debug("Loaded canvas configs: %s", list(configs.keys()))
            return configs

        except Exception as e:
            logger.warning("Failed to load canvas configs: %s, using defaults", e)
            return {k: CanvasConfig(**asdict(v)) for k, v in self._DEFAULT_CONFIGS.items()}

    def _save_configs(self) -> None:
        """Save canvas configurations to ApplicationStateManager."""
        if self._state_manager is None:
            logger.debug("No state manager - configs not persisted")
            return

        try:
            # Convert configs to dict format - use .value for string keys
            canvas_configs_data = {canvas_type.value: asdict(config) for canvas_type, config in self._configs.items()}

            # Update settings["frame_mapping"]["canvas_configs"]
            settings = self._state_manager._settings
            if "frame_mapping" not in settings:
                settings["frame_mapping"] = {}

            settings["frame_mapping"]["canvas_configs"] = canvas_configs_data

            # Persist to disk
            self._state_manager.save_settings()
            logger.debug("Saved canvas configs to settings")

        except Exception as e:
            logger.error("Failed to save canvas configs: %s", e)
