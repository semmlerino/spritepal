"""
Theme constants and styling foundations for SpritePal UI
"""
from __future__ import annotations

# Dark Theme Color Palette
COLORS = {
    # Primary action colors - enhanced for dark theme
    "primary": "#ff7f50",           # Coral Orange - Arrange Rows button
    "primary_hover": "#ff6347",
    "primary_pressed": "#cd5c5c",

    "secondary": "#4169e1",         # Royal Blue - Grid Arrange button
    "secondary_hover": "#6495ed",
    "secondary_pressed": "#1e90ff",

    "accent": "#9370db",            # Medium Purple - Inject button
    "accent_hover": "#ba55d3",
    "accent_pressed": "#8a2be2",

    # Additional action colors
    "extract": "#00bfff",           # Deep Sky Blue - Extract button
    "extract_hover": "#87ceeb",
    "extract_pressed": "#4682b4",

    "editor": "#32cd32",            # Lime Green - Open Editor button
    "editor_hover": "#98fb98",
    "editor_pressed": "#228b22",

    # Status colors - vibrant for dark theme
    "success": "#00ff7f",           # Spring Green
    "warning": "#ffd700",           # Gold
    "danger": "#ff6347",            # Tomato
    "info": "#87ceeb",              # Sky Blue

    # Dark theme neutral colors
    "white": "#ffffff",
    "light_gray": "#404040",         # Dark gray for panels
    "gray": "#808080",              # Medium gray for text
    "dark_gray": "#2d2d30",         # Main dark background
    "darker_gray": "#1e1e1e",       # Darker panels
    "disabled": "#555555",
    "disabled_text": "#b0b0b0",  # Brightened for WCAG AA contrast on dark backgrounds
    "black": "#000000",

    # Dark theme background colors
    "background": "#2d2d30",        # Main dark background
    "panel_background": "#383838",  # Lighter dark for panels
    "input_background": "#2b2b2b",  # Dark input fields
    "preview_background": "#1e1e1e", # Very dark for image previews

    # Dark theme border colors
    "border": "#555555",            # Medium gray borders
    "border_focus": "#0078d4",      # Blue focus border
    "border_error": "#ff6347",      # Red error border

    # Text colors for dark theme
    "text_primary": "#ffffff",      # Primary white text
    "text_secondary": "#cccccc",    # Secondary light gray text
    "text_muted": "#999999",        # Muted gray text

    # Browse/Navigation action colors
    "browse": "#5a9fd4",            # Teal-blue for Browse ROM button
    "browse_hover": "#6aafea",
    "browse_pressed": "#306998",
    "browse_gradient_start": "#5a9fd4",
    "browse_gradient_end": "#306998",

    # Focus colors (dark-theme compatible)
    "focus_background": "#1a3a5c",  # Dark blue for focused inputs
    "focus_background_subtle": "#252535",  # Very subtle highlight

    # Cache status semantic colors
    "cache_checking_bg": "#1a3a5c",
    "cache_checking_border": "#4a9eff",
    "cache_checking_text": "#7fbfff",
    "cache_resuming_bg": "#1a3d1a",
    "cache_resuming_border": "#4caf50",
    "cache_resuming_text": "#7fff7f",
    "cache_fresh_bg": "#3d2a1a",
    "cache_fresh_border": "#ff9800",
    "cache_fresh_text": "#ffbf4a",
    "cache_saving_bg": "#1a2d3d",
    "cache_saving_border": "#039be5",
    "cache_saving_text": "#4ac4ff",

    # Highlight colors for important UI elements
    "highlight": "#4488dd",
    "highlight_hover": "#5599ee",
    "highlight_border": "#66aaff",

    # Interactive surface colors
    "surface_hover": "#404040",
    "surface_pressed": "#353535",
    "surface_selected": "#505050",

    # Separator/divider
    "separator": "#3c3c3c",
}

# Typography
FONTS = {
    "default_family": "Arial, sans-serif",
    "monospace_family": "Consolas, Monaco, monospace",

    "small_size": "11px",
    "default_size": "12px",
    "medium_size": "14px",
    "large_size": "16px",

    "normal_weight": "normal",
    "bold_weight": "bold",
}

# Layout Dimensions
DIMENSIONS = {
    # Spacing - reduced for more compact interface
    "spacing_xs": 3,
    "spacing_sm": 4,
    "spacing_md": 8,
    "spacing_lg": 12,
    "spacing_xl": 16,

    # Component heights - more compact
    "button_height": 28,
    "input_height": 28,
    "combo_height": 28,

    # Component widths
    "button_min_width": 100,
    "button_max_width": 150,
    "combo_min_width": 200,
    "label_min_width": 120,

    # Border radius
    "border_radius": 4,
    "border_radius_small": 2,
    "border_radius_large": 8,

    # Border widths
    "border_width": 1,
    "border_width_thick": 2,
}

def get_theme_style() -> str:
    """
    Get base dark theme styles that should be applied globally

    Returns:
        CSS string with global dark theme styles
    """
    return f"""
    QWidget {{
        font-family: {FONTS['default_family']};
        font-size: {FONTS['default_size']};
        color: {COLORS['text_primary']};
        background-color: {COLORS['background']};
    }}

    QGroupBox {{
        font-weight: {FONTS['bold_weight']};
        border: {DIMENSIONS['border_width']}px solid {COLORS['border']};
        border-radius: {DIMENSIONS['border_radius']}px;
        margin-top: {DIMENSIONS['spacing_sm']}px;
        padding-top: {DIMENSIONS['spacing_md']}px;
        background-color: {COLORS['panel_background']};
        color: {COLORS['text_primary']};
    }}

    QGroupBox::title {{
        subcontrol-origin: margin;
        left: {DIMENSIONS['spacing_md']}px;
        padding: 0 {DIMENSIONS['spacing_sm']}px 0 {DIMENSIONS['spacing_sm']}px;
        color: {COLORS['text_primary']};
    }}

    QLabel {{
        color: {COLORS['text_primary']};
        font-size: {FONTS['default_size']};
    }}

    QStatusBar {{
        background-color: {COLORS['panel_background']};
        border-top: {DIMENSIONS['border_width']}px solid {COLORS['border']};
        color: {COLORS['text_primary']};
    }}
    """

def get_disabled_state_style() -> str:
    """Get CSS for disabled widget states"""
    return f"""
    :disabled {{
        background-color: {COLORS['disabled']};
        color: {COLORS['disabled_text']};
        border-color: {COLORS['disabled']};
    }}
    """

class Theme:
    """Theme class providing easy access to dark theme color constants."""

    # Primary colors
    PRIMARY = COLORS["primary"]
    PRIMARY_LIGHT = COLORS["primary_hover"]
    PRIMARY_DARK = COLORS["primary_pressed"]

    # Secondary colors
    SECONDARY = COLORS["secondary"]
    SECONDARY_LIGHT = COLORS["secondary_hover"]
    SECONDARY_DARK = COLORS["secondary_pressed"]

    # Accent colors
    ACCENT = COLORS["accent"]
    ACCENT_LIGHT = COLORS["accent_hover"]
    ACCENT_DARK = COLORS["accent_pressed"]

    # Dark theme backgrounds
    BACKGROUND = COLORS["background"]          # Main dark background
    SURFACE = COLORS["panel_background"]       # Panel background
    INPUT_BACKGROUND = COLORS["input_background"]  # Input field background
    PREVIEW_BACKGROUND = COLORS["preview_background"]  # Preview area background

    # Dark theme text colors
    TEXT = COLORS["text_primary"]              # Primary white text
    TEXT_SECONDARY = COLORS["text_secondary"]  # Secondary gray text
    TEXT_MUTED = COLORS["text_muted"]          # Muted gray text
    TEXT_DISABLED = COLORS["disabled_text"]    # Disabled text

    # Border colors
    BORDER = COLORS["border"]
    BORDER_FOCUS = COLORS["border_focus"]
    BORDER_ERROR = COLORS["border_error"]

    # Status colors
    SUCCESS = COLORS["success"]
    WARNING = COLORS["warning"]
    DANGER = COLORS["danger"]
    INFO = COLORS["info"]

    # Action colors
    EXTRACT = COLORS["extract"]
    EDITOR = COLORS["editor"]

    # Browse/Navigation colors
    BROWSE = COLORS["browse"]
    BROWSE_HOVER = COLORS["browse_hover"]
    BROWSE_PRESSED = COLORS["browse_pressed"]

    # Focus colors
    FOCUS_BACKGROUND = COLORS["focus_background"]
    FOCUS_BACKGROUND_SUBTLE = COLORS["focus_background_subtle"]

    # Highlight colors
    HIGHLIGHT = COLORS["highlight"]
    HIGHLIGHT_HOVER = COLORS["highlight_hover"]
