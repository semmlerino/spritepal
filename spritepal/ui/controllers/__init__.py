"""
UI Controllers package.

Controllers handle business logic coordination between UI panels and core services.
They own state, emit signals, and provide clean APIs for panels to use.

Controllers follow the QObject pattern with signals for async communication.
"""

from __future__ import annotations

from .extraction_params_controller import ExtractionParams, ExtractionParamsController
from .offset_controller import (
    BYTES_PER_TILE,
    DEFAULT_STEP_INDEX,
    PRESET_CUSTOM_RANGE,
    PRESET_KIRBY_SPRITES,
    STEP_SIZES,
    JumpLocation,
    OffsetController,
    OffsetDisplayInfo,
)
from .rom_session_controller import (
    HeaderDisplayInfo,
    ROMInfo,
    ROMSessionController,
)
from .session_file_controller import (
    EXTRACTION_PANEL_CONFIG,
    ROM_PANEL_CONFIG,
    SessionFileConfig,
    SessionFileController,
    SessionFileEntry,
    ValidatedSessionData,
    create_extraction_panel_controller,
    create_rom_panel_controller,
)
from .sprite_display_formatter import (
    CACHE_INDICATOR,
    FormattedSpriteList,
    SpriteDisplayItem,
    format_custom_sprite_text,
    format_header_text,
    format_manual_sprite_text,
    format_offset,
    format_sprite_display_text,
    format_sprite_list,
    format_sprite_name,
    get_custom_sprite_name,
    get_internal_name_from_offset,
    get_manual_sprite_name,
)

__all__: list[str] = [
    # offset_controller
    "BYTES_PER_TILE",
    # sprite_display_formatter
    "CACHE_INDICATOR",
    "DEFAULT_STEP_INDEX",
    # session_file_controller
    "EXTRACTION_PANEL_CONFIG",
    "PRESET_CUSTOM_RANGE",
    "PRESET_KIRBY_SPRITES",
    "ROM_PANEL_CONFIG",
    "STEP_SIZES",
    # extraction_params_controller
    "ExtractionParams",
    "ExtractionParamsController",
    "FormattedSpriteList",
    # rom_session_controller
    "HeaderDisplayInfo",
    "JumpLocation",
    "OffsetController",
    "OffsetDisplayInfo",
    "ROMInfo",
    "ROMSessionController",
    "SessionFileConfig",
    "SessionFileController",
    "SessionFileEntry",
    "SpriteDisplayItem",
    "ValidatedSessionData",
    "create_extraction_panel_controller",
    "create_rom_panel_controller",
    "format_custom_sprite_text",
    "format_header_text",
    "format_manual_sprite_text",
    "format_offset",
    "format_sprite_display_text",
    "format_sprite_list",
    "format_sprite_name",
    "get_custom_sprite_name",
    "get_internal_name_from_offset",
    "get_manual_sprite_name",
]
