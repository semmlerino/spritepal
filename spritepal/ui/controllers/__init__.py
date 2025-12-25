"""
UI Controllers package.

Controllers handle business logic coordination between UI panels and core services.
They own state, emit signals, and provide clean APIs for panels to use.

Controllers follow the QObject pattern with signals for async communication.
"""
from __future__ import annotations

from .extraction_params_controller import ExtractionParams, ExtractionParamsController
from .rom_session_controller import (
    HeaderDisplayInfo,
    ROMInfo,
    ROMSessionController,
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
from .offset_controller import (
    BYTES_PER_TILE,
    DEFAULT_STEP_INDEX,
    JumpLocation,
    OffsetController,
    OffsetDisplayInfo,
    PRESET_CUSTOM_RANGE,
    PRESET_KIRBY_SPRITES,
    STEP_SIZES,
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

__all__: list[str] = [
    # extraction_params_controller
    "ExtractionParams",
    "ExtractionParamsController",
    # rom_session_controller
    "HeaderDisplayInfo",
    "ROMInfo",
    "ROMSessionController",
    # sprite_display_formatter
    "CACHE_INDICATOR",
    "FormattedSpriteList",
    "SpriteDisplayItem",
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
    # offset_controller
    "BYTES_PER_TILE",
    "DEFAULT_STEP_INDEX",
    "JumpLocation",
    "OffsetController",
    "OffsetDisplayInfo",
    "PRESET_CUSTOM_RANGE",
    "PRESET_KIRBY_SPRITES",
    "STEP_SIZES",
    # session_file_controller
    "EXTRACTION_PANEL_CONFIG",
    "ROM_PANEL_CONFIG",
    "SessionFileConfig",
    "SessionFileController",
    "SessionFileEntry",
    "ValidatedSessionData",
    "create_extraction_panel_controller",
    "create_rom_panel_controller",
]
