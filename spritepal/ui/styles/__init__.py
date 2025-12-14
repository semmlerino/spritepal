"""
SpritePal UI Styling System

Centralized styling system for consistent UI appearance and maintainability.
"""
from __future__ import annotations

from .components import (
    get_bold_text_style,
    get_borderless_preview_style,
    get_button_style,
    get_dialog_button_box_style,
    get_error_text_style,
    get_extraction_checklist_style,
    get_hex_label_style,
    get_input_style,
    get_link_text_style,
    get_minimal_preview_style,
    get_monospace_text_style,
    get_muted_text_style,
    get_panel_style,
    get_preview_panel_style,
    get_prominent_action_button_style,
    get_scroll_area_style,
    get_slider_style,
    get_splitter_style,
    get_status_style,
    get_success_text_style,
)
from .theme import (
    COLORS,
    DIMENSIONS,
    FONTS,
    get_theme_style,
)

__all__ = [
    "COLORS",
    "DIMENSIONS",
    "FONTS",
    "get_bold_text_style",
    "get_borderless_preview_style",
    "get_button_style",
    "get_dialog_button_box_style",
    "get_error_text_style",
    "get_extraction_checklist_style",
    "get_hex_label_style",
    "get_input_style",
    "get_link_text_style",
    "get_minimal_preview_style",
    "get_monospace_text_style",
    "get_muted_text_style",
    "get_panel_style",
    "get_preview_panel_style",
    "get_prominent_action_button_style",
    "get_scroll_area_style",
    "get_slider_style",
    "get_splitter_style",
    "get_status_style",
    "get_success_text_style",
    "get_theme_style",
]
