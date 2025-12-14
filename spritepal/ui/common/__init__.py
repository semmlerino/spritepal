"""
Common UI utilities and helpers.
"""
from __future__ import annotations

# WorkerManager moved to core/services for proper layer boundaries
# Re-exported here for backward compatibility
from core.services.worker_lifecycle import WorkerManager

from .collapsible_group_box import CollapsibleGroupBox
from .error_handler import ErrorHandler, get_error_handler, reset_error_handler
from .file_dialogs import (
    FileDialogHelper,
    browse_for_directory,
    browse_for_open_file,
    browse_for_save_file,
)

# Import spacing and sizing constants explicitly
# NOTE: Color constants moved to ui/styles/theme.py - use COLORS dict instead
from .spacing_constants import (
    BASE_UNIT,
    BORDER_THICK,
    BORDER_THIN,
    BROWSE_BUTTON_MAX_WIDTH,
    BUTTON_HEIGHT,
    CHECKER_FADE_OPACITY,
    CHECKMARK_OFFSET,
    CIRCLE_INDICATOR_MARGIN,
    CIRCLE_INDICATOR_SIZE,
    COLLAPSIBLE_ANIMATION_DURATION,
    COLLAPSIBLE_EASING,
    COMBO_BOX_MIN_WIDTH,
    COMPACT_BUTTON_HEIGHT,
    COMPACT_WIDTH,
    CONTENT_MARGIN,
    DROP_ZONE_MIN_HEIGHT,
    FONT_SIZE_LARGE,
    FONT_SIZE_MEDIUM,
    FONT_SIZE_NORMAL,
    FONT_SIZE_SMALL,
    FONT_SIZE_XLARGE,
    GROUP_PADDING,
    INPUT_HEIGHT,
    LINE_NORMAL,
    LINE_THICK,
    MAX_ZOOM,
    MEDIUM_WIDTH,
    OFFSET_LABEL_MIN_WIDTH,
    OFFSET_SPINBOX_MIN_WIDTH,
    PALETTE_PREVIEW_SIZE,
    PALETTE_SELECTOR_MIN_WIDTH,
    PANEL_PADDING,
    PREVIEW_MIN_SIZE,
    SLIDER_HEIGHT,
    SPACING_LARGE,
    SPACING_MEDIUM,
    SPACING_SMALL,
    SPACING_TINY,
    SPACING_XLARGE,
    TAB_CONTENT_PADDING,
    TAB_MAX_WIDTH,
    TAB_MIN_WIDTH,
    TAB_SECTION_SPACING,
    TILE_GRID_THICKNESS,
    WIDE_WIDTH,
)
from .tabbed_widget_base import TabbedWidgetBase
from .widget_factory import (
    WidgetFactory,
    create_browse_layout,
    create_checkbox_with_tooltip,
    create_info_label,
)

__all__ = [
    # Spacing and sizing constants
    # NOTE: Color constants removed - use ui.styles.theme.COLORS instead
    "BASE_UNIT",
    "BORDER_THICK",
    "BORDER_THIN",
    "BROWSE_BUTTON_MAX_WIDTH",
    "BUTTON_HEIGHT",
    "CHECKER_FADE_OPACITY",
    "CHECKMARK_OFFSET",
    "CIRCLE_INDICATOR_MARGIN",
    "CIRCLE_INDICATOR_SIZE",
    "COLLAPSIBLE_ANIMATION_DURATION",
    "COLLAPSIBLE_EASING",
    "COMBO_BOX_MIN_WIDTH",
    "COMPACT_BUTTON_HEIGHT",
    "COMPACT_WIDTH",
    "CONTENT_MARGIN",
    "DROP_ZONE_MIN_HEIGHT",
    "FONT_SIZE_LARGE",
    "FONT_SIZE_MEDIUM",
    "FONT_SIZE_NORMAL",
    "FONT_SIZE_SMALL",
    "FONT_SIZE_XLARGE",
    "GROUP_PADDING",
    "INPUT_HEIGHT",
    "LINE_NORMAL",
    "LINE_THICK",
    "MAX_ZOOM",
    "MEDIUM_WIDTH",
    "OFFSET_LABEL_MIN_WIDTH",
    "OFFSET_SPINBOX_MIN_WIDTH",
    "PALETTE_PREVIEW_SIZE",
    "PALETTE_SELECTOR_MIN_WIDTH",
    "PANEL_PADDING",
    "PREVIEW_MIN_SIZE",
    "SLIDER_HEIGHT",
    "SPACING_LARGE",
    "SPACING_MEDIUM",
    "SPACING_SMALL",
    "SPACING_TINY",
    "SPACING_XLARGE",
    "TAB_CONTENT_PADDING",
    "TAB_MAX_WIDTH",
    "TAB_MIN_WIDTH",
    "TAB_SECTION_SPACING",
    "TILE_GRID_THICKNESS",
    "WIDE_WIDTH",
    # Core components
    "CollapsibleGroupBox",
    "ErrorHandler",
    "FileDialogHelper",
    "TabbedWidgetBase",
    "WidgetFactory",
    "WorkerManager",
    # File dialog functions
    "browse_for_directory",
    "browse_for_open_file",
    "browse_for_save_file",
    # Widget factory functions
    "create_browse_layout",
    "create_checkbox_with_tooltip",
    "create_info_label",
    # Error handler functions
    "get_error_handler",
    "reset_error_handler",
]
