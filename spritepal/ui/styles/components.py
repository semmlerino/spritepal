"""
Component-specific styling functions for SpritePal UI
"""
from __future__ import annotations

from .theme import COLORS, DIMENSIONS, FONTS, get_disabled_state_style


def get_button_style(
    style_type: str = "primary",
    min_height: int | None = None,
    font_size: str | None = None
) -> str:
    """
    Get button styling CSS

    Args:
        style_type: Button style type - "primary", "secondary", "accent", "default"
        min_height: Minimum button height in pixels
        font_size: Font size override

    Returns:
        CSS string for button styling
    """
    if min_height is None:
        min_height = DIMENSIONS["button_height"]

    if font_size is None:
        font_size = FONTS["medium_size"]

    # Color mapping for button types
    color_map = {
        "primary": {
            "bg": COLORS["primary"],
            "hover": COLORS["primary_hover"],
            "pressed": COLORS["primary_pressed"],
        },
        "secondary": {
            "bg": COLORS["secondary"],
            "hover": COLORS["secondary_hover"],
            "pressed": COLORS["secondary_pressed"],
        },
        "accent": {
            "bg": COLORS["accent"],
            "hover": COLORS["accent_hover"],
            "pressed": COLORS["accent_pressed"],
        },
        "extract": {
            "bg": COLORS["extract"],
            "hover": COLORS["extract_hover"],
            "pressed": COLORS["extract_pressed"],
        },
        "editor": {
            "bg": COLORS["editor"],
            "hover": COLORS["editor_hover"],
            "pressed": COLORS["editor_pressed"],
        },
        "edit": {
            "bg": COLORS["edit"],
            "hover": COLORS["edit_hover"],
            "pressed": COLORS["edit_pressed"],
        },
        "danger_action": {
            "bg": COLORS["danger_action"],
            "hover": COLORS["danger_action_hover"],
            "pressed": COLORS["danger_action_pressed"],
        },
        "default": {
            "bg": COLORS["light_gray"],
            "hover": COLORS["gray"],
            "pressed": COLORS["dark_gray"],
        },
        "secondary_outline": {
            "bg": "transparent",
            "hover": COLORS["panel_background"],
            "pressed": COLORS["background"],
            "border": COLORS["border"],
            "text": COLORS["text_secondary"],
        },
    }

    colors = color_map.get(style_type, color_map["default"])

    # Secondary outline uses different text color and transparent bg
    if style_type == "secondary_outline":
        text_color = colors.get("text", COLORS["text_secondary"])
    elif style_type == "default":
        text_color = COLORS["black"]
    else:
        text_color = COLORS["white"]

    # Secondary outline uses explicit border color
    border_color = colors.get("border", colors["bg"])

    return f"""
    QPushButton {{
        background-color: {colors["bg"]};
        color: {text_color};
        font-weight: {FONTS["bold_weight"]};
        font-size: {font_size};
        min-height: {min_height}px;
        border: {DIMENSIONS["border_width"]}px solid {border_color};
        border-radius: {DIMENSIONS["border_radius"]}px;
        padding: {DIMENSIONS["spacing_xs"]}px {DIMENSIONS["spacing_sm"]}px;
    }}
    QPushButton:hover {{
        background-color: {colors["hover"]};
        border-color: {colors["hover"]};
    }}
    QPushButton:pressed {{
        background-color: {colors["pressed"]};
        border-color: {colors["pressed"]};
    }}
    {get_disabled_state_style()}
    """

def get_input_style(
    input_type: str = "text",
    min_width: int | None = None
) -> str:
    """
    Get input field styling CSS

    Args:
        input_type: Input type - "text", "combo", "spin"
        min_width: Minimum width in pixels

    Returns:
        CSS string for input styling
    """
    if min_width is None:
        min_width = DIMENSIONS["combo_min_width"] if input_type == "combo" else 100

    base_style = f"""
    background-color: {COLORS["input_background"]};
    border: {DIMENSIONS["border_width"]}px solid {COLORS["border"]};
    border-radius: {DIMENSIONS["border_radius"]}px;
    padding: {DIMENSIONS["spacing_sm"]}px {DIMENSIONS["spacing_md"]}px;
    font-size: {FONTS["default_size"]};
    min-width: {min_width}px;
    min-height: {DIMENSIONS["input_height"]}px;
    """

    focus_style = f"""
    :focus {{
        border-color: {COLORS["border_focus"]};
        outline: none;
    }}
    """

    if input_type == "text":
        return f"""
        QLineEdit {{
            {base_style}
        }}
        QLineEdit{focus_style}
        {get_disabled_state_style()}
        """
    if input_type == "combo":
        return f"""
        QComboBox {{
            {base_style}
        }}
        QComboBox{focus_style}
        QComboBox::drop-down {{
            border: none;
            width: 20px;
        }}
        QComboBox::down-arrow {{
            border-left: 5px solid transparent;
            border-right: 5px solid transparent;
            border-top: 5px solid {COLORS["gray"]};
        }}
        {get_disabled_state_style()}
        """
    if input_type == "spin":
        return f"""
        QSpinBox, QDoubleSpinBox {{
            {base_style}
        }}
        QSpinBox{focus_style}
        QDoubleSpinBox{focus_style}
        {get_disabled_state_style()}
        """

    return base_style

def get_panel_style(panel_type: str = "default") -> str:
    """
    Get panel/groupbox styling CSS

    Args:
        panel_type: Panel style type - "default", "primary", "secondary"

    Returns:
        CSS string for panel styling
    """
    if panel_type == "primary":
        border_color = COLORS["primary"]
    elif panel_type == "secondary":
        border_color = COLORS["secondary"]
    else:
        border_color = COLORS["border"]

    return f"""
    QGroupBox {{
        font-weight: {FONTS["bold_weight"]};
        border: {DIMENSIONS["border_width"]}px solid {border_color};
        border-radius: {DIMENSIONS["border_radius"]}px;
        margin-top: {DIMENSIONS["spacing_md"]}px;
        padding-top: {DIMENSIONS["spacing_lg"]}px;
        background-color: {COLORS["panel_background"]};
    }}
    QGroupBox::title {{
        subcontrol-origin: margin;
        left: {DIMENSIONS["spacing_md"]}px;
        padding: 0 {DIMENSIONS["spacing_sm"]}px 0 {DIMENSIONS["spacing_sm"]}px;
        color: {border_color if panel_type != "default" else COLORS["black"]};
    }}
    """

def get_status_style(status_type: str = "info") -> str:
    """
    Get status indicator styling CSS

    Args:
        status_type: Status type - "info", "success", "warning", "danger"

    Returns:
        CSS string for status styling
    """
    color_map = {
        "info": COLORS["info"],
        "success": COLORS["success"],
        "warning": COLORS["warning"],
        "danger": COLORS["danger"],
    }

    color = color_map.get(status_type, COLORS["info"])

    return f"""
    QLabel {{
        color: {color};
        font-weight: {FONTS["bold_weight"]};
        padding: {DIMENSIONS["spacing_sm"]}px;
        border-left: {DIMENSIONS["border_width_thick"]}px solid {color};
        background-color: {COLORS["light_gray"]};
    }}
    """

def get_progress_style() -> str:
    """Get progress bar styling CSS"""
    return f"""
    QProgressBar {{
        border: {DIMENSIONS["border_width"]}px solid {COLORS["border"]};
        border-radius: {DIMENSIONS["border_radius"]}px;
        text-align: center;
        font-size: {FONTS["default_size"]};
        background-color: {COLORS["light_gray"]};
    }}
    QProgressBar::chunk {{
        background-color: {COLORS["primary"]};
        border-radius: {DIMENSIONS["border_radius_small"]}px;
    }}
    """

def get_tab_style() -> str:
    """Get tab widget styling CSS"""
    return f"""
    QTabWidget::pane {{
        border: {DIMENSIONS["border_width"]}px solid {COLORS["border"]};
        border-radius: {DIMENSIONS["border_radius"]}px;
    }}
    QTabBar::tab {{
        background-color: {COLORS["light_gray"]};
        border: {DIMENSIONS["border_width"]}px solid {COLORS["border"]};
        padding: {DIMENSIONS["spacing_md"]}px {DIMENSIONS["spacing_lg"]}px;
        margin-right: {DIMENSIONS["spacing_xs"]}px;
        border-top-left-radius: {DIMENSIONS["border_radius"]}px;
        border-top-right-radius: {DIMENSIONS["border_radius"]}px;
    }}
    QTabBar::tab:selected {{
        background-color: {COLORS["background"]};
        border-bottom: {DIMENSIONS["border_width"]}px solid {COLORS["background"]};
    }}
    QTabBar::tab:hover {{
        background-color: {COLORS["primary"]};
        color: {COLORS["white"]};
    }}
    """

def get_muted_text_style(
    italic: bool = False,
    color_level: str = "medium"
) -> str:
    """
    Get muted text styling CSS for info labels

    Args:
        italic: Whether to make text italic
        color_level: Color intensity - "light", "medium", "dark"

    Returns:
        CSS string for muted text styling
    """
    # All levels now meet WCAG AA (4.5:1 contrast on dark backgrounds)
    color_map = {
        "light": "#c8c8c8",  # Brightest - WCAG AA on #383838
        "medium": COLORS["gray"],  # Standard gray (now #a0a0a0)
        "dark": "#b0b0b0",   # Slightly muted - WCAG AA on dark backgrounds
    }

    color = color_map.get(color_level, COLORS["gray"])

    style_parts = [
        f"color: {color};",
        f"padding: {DIMENSIONS['spacing_sm']}px 0;",
        f"font-size: {FONTS['default_size']};",
    ]

    if italic:
        style_parts.append("font-style: italic;")

    return f"""
    QLabel {{
        {' '.join(style_parts)}
    }}
    """

def get_link_text_style(color: str = "extract") -> str:
    """
    Get link-style text styling CSS

    Args:
        color: Color theme - "extract", "editor", "primary", etc.

    Returns:
        CSS string for link text styling
    """
    color_map = {
        "extract": COLORS["extract"],
        "editor": COLORS["editor"],
        "primary": COLORS["primary"],
        "secondary": COLORS["secondary"],
        "accent": COLORS["accent"],
    }

    text_color = color_map.get(color, COLORS["extract"])

    return f"""
    QLabel {{
        color: {text_color};
        font-size: {FONTS['small_size']};
    }}
    """

def get_monospace_text_style(
    color: str = "default",
    font_size: str | None = None
) -> str:
    """
    Get monospace text styling CSS

    Args:
        color: Text color theme
        font_size: Font size override

    Returns:
        CSS string for monospace text styling
    """
    if font_size is None:
        font_size = FONTS["medium_size"]

    color_map = {
        "default": COLORS["text_primary"],  # White for dark theme visibility
        "extract": COLORS["extract"],
        "muted": COLORS["gray"],
    }

    text_color = color_map.get(color, COLORS["text_primary"])

    return f"""
    QLabel {{
        font-family: {FONTS["monospace_family"]};
        color: {text_color};
        font-size: {font_size};
    }}
    """

def get_bold_text_style(color: str = "default") -> str:
    """
    Get bold text styling CSS

    Args:
        color: Text color theme

    Returns:
        CSS string for bold text styling
    """
    color_map = {
        "default": COLORS["text_primary"],  # White for dark theme visibility
        "white": COLORS["white"],
        "muted": COLORS["gray"],
    }

    text_color = color_map.get(color, COLORS["text_primary"])

    return f"""
    QLabel {{
        font-weight: {FONTS["bold_weight"]};
        color: {text_color};
    }}
    """

def get_success_text_style() -> str:
    """
    Get success text styling CSS (green + bold)

    Returns:
        CSS string for success text styling
    """
    return f"""
    QLabel {{
        color: {COLORS["editor"]};
        font-weight: {FONTS["bold_weight"]};
    }}
    """

def get_error_text_style() -> str:
    """
    Get error text styling CSS (red color)

    Returns:
        CSS string for error text styling
    """
    return f"""
    QLabel {{
        color: {COLORS["danger"]};
    }}
    """

def get_hex_label_style(
    background: bool = True,
    color: str = "extract"
) -> str:
    """
    Get hex/code label styling CSS (monospace with optional background)

    Args:
        background: Whether to include background styling
        color: Color theme for text

    Returns:
        CSS string for hex label styling
    """
    color_map = {
        "extract": COLORS["extract"],
        "secondary": COLORS["secondary"],
        "accent": COLORS["accent"],
    }

    text_color = color_map.get(color, COLORS["extract"])

    base_style = f"""
    QLabel {{
        font-family: {FONTS["monospace_family"]};
        font-size: {FONTS["medium_size"]};
        font-weight: {FONTS["bold_weight"]};
        color: {text_color};
        padding: {DIMENSIONS["spacing_xs"]}px {DIMENSIONS["spacing_md"]}px;
        min-width: 80px;
    """

    if background:
        base_style += f"""
        background-color: {COLORS["dark_gray"]};
        border: {DIMENSIONS["border_width"]}px solid {COLORS["border"]};
        border-radius: {DIMENSIONS["border_radius"]}px;
        """

    base_style += "}"
    return base_style

def get_slider_style(color: str = "extract") -> str:
    """
    Get slider styling CSS

    Args:
        color: Color theme for slider handle

    Returns:
        CSS string for slider styling
    """
    color_map = {
        "extract": COLORS["extract"],
        "secondary": COLORS["secondary"],
        "accent": COLORS["accent"],
    }

    handle_color = color_map.get(color, COLORS["extract"])

    return f"""
    QSlider::groove:horizontal {{
        border: {DIMENSIONS["border_width"]}px solid {COLORS["border"]};
        height: 8px;
        background: {COLORS["dark_gray"]};
        border-radius: {DIMENSIONS["border_radius"]}px;
    }}
    QSlider::handle:horizontal {{
        background: {handle_color};
        border: {DIMENSIONS["border_width"]}px solid {handle_color};
        width: 18px;
        margin: -5px 0;
        border-radius: 9px;
    }}
    QSlider::handle:horizontal:hover {{
        background: {COLORS["extract_hover"] if color == "extract" else COLORS["primary_hover"]};
        border: {DIMENSIONS["border_width"]}px solid {COLORS["extract_hover"] if color == "extract" else COLORS["primary_hover"]};
    }}
    QSlider::sub-page:horizontal {{
        background: {COLORS["extract_pressed"] if color == "extract" else COLORS["primary_pressed"]};
        border-radius: {DIMENSIONS["border_radius"]}px;
    }}
    """

def get_preview_panel_style() -> str:
    """
    Get dark preview panel styling CSS for image displays

    Returns:
        CSS string for dark preview panel styling
    """
    return f"""
    QLabel {{
        border: {DIMENSIONS["border_width"]}px solid {COLORS["border"]};
        background-color: {COLORS["preview_background"]};
        border-radius: {DIMENSIONS["border_radius_small"]}px;
        color: {COLORS["text_primary"]};
    }}
    """

def get_minimal_preview_style() -> str:
    """
    Get minimal preview styling CSS for compact displays

    Returns:
        CSS string for minimal preview styling
    """
    return f"""
    QLabel {{
        border: 1px solid {COLORS["border"]};
        background-color: {COLORS["background"]};
        border-radius: 2px;
    }}
    """

def get_borderless_preview_style() -> str:
    """
    Get completely borderless preview styling CSS for maximum space efficiency

    Eliminates all borders, padding, margins, and background to maximize preview area.
    Perfect for space-efficient Live Preview displays that blend with parent.

    Returns:
        CSS string for borderless preview styling
    """
    return """
    QLabel {
        border: none;
        background-color: transparent;
        margin: 0px;
        padding: 0px;
    }
    """

def get_splitter_style(handle_width: int = 8) -> str:
    """
    Get splitter handle styling CSS

    Args:
        handle_width: Width of the splitter handle in pixels

    Returns:
        CSS string for splitter styling
    """
    return f"""
    QSplitter::handle {{
        background-color: {COLORS["border"]};
        border: {DIMENSIONS["border_width"]}px solid {COLORS["gray"]};
        width: {handle_width}px;
        height: {handle_width}px;
    }}
    QSplitter::handle:hover {{
        background-color: {COLORS["gray"]};
        border-color: {COLORS["dark_gray"]};
    }}
    QSplitter::handle:pressed {{
        background-color: {COLORS["dark_gray"]};
    }}
    """

def get_dialog_button_box_style() -> str:
    """
    Get dialog button box styling CSS

    Returns:
        CSS string for dialog button box styling
    """
    return f"""
    QDialogButtonBox {{
        border: none;
        padding: {DIMENSIONS["spacing_md"]}px 0;
    }}
    QDialogButtonBox QPushButton {{
        min-width: 80px;
        min-height: {DIMENSIONS["button_height"]}px;
        padding: {DIMENSIONS["spacing_xs"]}px {DIMENSIONS["spacing_md"]}px;
        font-size: {FONTS["default_size"]};
        border-radius: {DIMENSIONS["border_radius"]}px;
    }}
    """

def get_scroll_area_style(background_color: str = "background") -> str:
    """
    Get scroll area styling CSS for preview panels and lists

    Args:
        background_color: Background color theme - "background", "light_gray", "panel_background"

    Returns:
        CSS string for scroll area styling
    """
    color_map = {
        "background": COLORS["background"],
        "light_gray": COLORS["light_gray"],
        "panel_background": COLORS["panel_background"],
    }

    bg_color = color_map.get(background_color, COLORS["background"])

    return f"""
    QScrollArea {{
        background-color: {bg_color};
        border: {DIMENSIONS["border_width"]}px solid {COLORS["border"]};
        border-radius: {DIMENSIONS["border_radius"]}px;
    }}
    QScrollArea QWidget {{
        background-color: {bg_color};
    }}
    QScrollBar:vertical {{
        background-color: {COLORS["light_gray"]};
        width: 12px;
        border-radius: 6px;
    }}
    QScrollBar::handle:vertical {{
        background-color: {COLORS["gray"]};
        min-height: 20px;
        border-radius: 6px;
        margin: 2px;
    }}
    QScrollBar::handle:vertical:hover {{
        background-color: {COLORS["dark_gray"]};
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
        height: 0px;
    }}
    """

def get_dark_preview_style() -> str:
    """
    Get comprehensive dark theme styling for sprite preview areas

    Returns:
        CSS string for dark sprite preview styling
    """
    return f"""
    QLabel {{
        background-color: {COLORS["preview_background"]};
        border: {DIMENSIONS["border_width"]}px solid {COLORS["border"]};
        border-radius: {DIMENSIONS["border_radius"]}px;
        color: {COLORS["text_primary"]};
        padding: {DIMENSIONS["spacing_sm"]}px;
    }}

    QScrollArea {{
        background-color: {COLORS["preview_background"]};
        border: {DIMENSIONS["border_width"]}px solid {COLORS["border"]};
        border-radius: {DIMENSIONS["border_radius"]}px;
    }}

    QScrollArea QWidget {{
        background-color: {COLORS["preview_background"]};
    }}
    """

def get_dark_panel_style() -> str:
    """
    Get comprehensive dark theme styling for panels and group boxes

    Returns:
        CSS string for dark panel styling
    """
    return f"""
    QGroupBox {{
        background-color: {COLORS["panel_background"]};
        border: {DIMENSIONS["border_width"]}px solid {COLORS["border"]};
        border-radius: {DIMENSIONS["border_radius"]}px;
        margin-top: {DIMENSIONS["spacing_md"]}px;
        padding-top: {DIMENSIONS["spacing_lg"]}px;
        color: {COLORS["text_primary"]};
        font-weight: {FONTS["bold_weight"]};
    }}

    QGroupBox::title {{
        subcontrol-origin: margin;
        left: {DIMENSIONS["spacing_md"]}px;
        padding: 0 {DIMENSIONS["spacing_sm"]}px 0 {DIMENSIONS["spacing_sm"]}px;
        color: {COLORS["text_primary"]};
    }}

    QWidget {{
        background-color: {COLORS["background"]};
        color: {COLORS["text_primary"]};
    }}
    """


def get_action_zone_style() -> str:
    """
    Get styling for the action zone (output settings + buttons).

    This creates visual separation between the scrollable configuration
    content above and the fixed action buttons below.

    Returns:
        CSS string for action zone styling
    """
    return f"""
    #actionZone {{
        background-color: {COLORS["panel_background"]};
        border-top: 1px solid {COLORS["border"]};
        padding-top: {DIMENSIONS["spacing_sm"]}px;
    }}

    #actionZone QGroupBox {{
        background-color: transparent;
        border: none;
        margin-top: 0;
        padding: 0;
    }}

    #actionZone QGroupBox::title {{
        color: {COLORS["text_secondary"]};
        font-size: {FONTS["small_size"]};
        subcontrol-origin: margin;
        left: 0;
        padding: 0;
    }}
    """


def get_manual_offset_button_style() -> str:
    """
    Get styling for the manual offset control button.

    Creates a prominent, gradient-styled button that stands out
    as the primary action for manual sprite offset selection.

    Returns:
        CSS string for manual offset button styling
    """
    return f"""
    QPushButton {{
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
            stop:0 {COLORS["browse_gradient_start"]}, stop:1 {COLORS["browse_gradient_end"]});
        color: {COLORS["white"]};
        font-weight: {FONTS["bold_weight"]};
        font-size: {FONTS["medium_size"]};
        border-radius: {DIMENSIONS["border_radius_large"]}px;
        padding: {DIMENSIONS["spacing_md"]}px {DIMENSIONS["spacing_lg"]}px;
        border: 1px solid {COLORS["browse_pressed"]};
        min-height: 36px;
    }}
    QPushButton:hover {{
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
            stop:0 {COLORS["browse_hover"]}, stop:1 {COLORS["browse"]});
        border: 1px solid {COLORS["highlight"]};
    }}
    QPushButton:pressed {{
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
            stop:0 {COLORS["browse_pressed"]}, stop:1 {COLORS["browse_gradient_end"]});
    }}
    """


def get_cache_status_style(status: str) -> str:
    """
    Get styling for cache status labels based on status type.

    Used to visually indicate cache state (checking, resuming, fresh, saving, saved).
    Uses dark backgrounds with bright text for WCAG AA compliance on dark theme.

    Args:
        status: Status type - "checking", "resuming", "fresh", "saving", "saved"

    Returns:
        CSS string for cache status label styling
    """
    # Dark theme compatible: uses theme colors for consistency
    styles = {
        "checking": f"""
            QLabel {{
                background-color: {COLORS["cache_checking_bg"]};
                border: 1px solid {COLORS["cache_checking_border"]};
                border-radius: {DIMENSIONS["border_radius"]}px;
                padding: {DIMENSIONS["spacing_md"]}px;
                font-weight: {FONTS["bold_weight"]};
                color: {COLORS["cache_checking_text"]};
            }}
        """,
        "resuming": f"""
            QLabel {{
                background-color: {COLORS["cache_resuming_bg"]};
                border: 1px solid {COLORS["cache_resuming_border"]};
                border-radius: {DIMENSIONS["border_radius"]}px;
                padding: {DIMENSIONS["spacing_md"]}px;
                font-weight: {FONTS["bold_weight"]};
                color: {COLORS["cache_resuming_text"]};
            }}
        """,
        "fresh": f"""
            QLabel {{
                background-color: {COLORS["cache_fresh_bg"]};
                border: 1px solid {COLORS["cache_fresh_border"]};
                border-radius: {DIMENSIONS["border_radius"]}px;
                padding: {DIMENSIONS["spacing_md"]}px;
                font-weight: {FONTS["bold_weight"]};
                color: {COLORS["cache_fresh_text"]};
            }}
        """,
        "saving": f"""
            QLabel {{
                background-color: {COLORS["cache_saving_bg"]};
                border: 1px solid {COLORS["cache_saving_border"]};
                border-radius: {DIMENSIONS["border_radius"]}px;
                padding: {DIMENSIONS["spacing_md"]}px;
                font-weight: {FONTS["bold_weight"]};
                color: {COLORS["cache_saving_text"]};
            }}
        """,
        "saved": f"""
            QLabel {{
                background-color: {COLORS["cache_resuming_bg"]};
                border: 1px solid {COLORS["cache_resuming_border"]};
                border-radius: {DIMENSIONS["border_radius"]}px;
                padding: {DIMENSIONS["spacing_md"]}px;
                font-weight: {FONTS["bold_weight"]};
                color: {COLORS["cache_resuming_text"]};
            }}
        """,
    }
    return styles.get(status, styles["checking"])


def get_prominent_action_button_style() -> str:
    """
    Get styling for prominent action buttons like 'Find Sprites'.

    Uses a gradient and larger size to draw attention while maintaining
    dark theme consistency. Use for important discovery/action buttons.

    Returns:
        CSS string for prominent action button styling
    """
    return f"""
    QPushButton {{
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
            stop:0 {COLORS["browse_gradient_start"]},
            stop:1 {COLORS["browse_gradient_end"]});
        color: {COLORS["white"]};
        font-weight: {FONTS["bold_weight"]};
        font-size: {FONTS["medium_size"]};
        border-radius: {DIMENSIONS["border_radius_large"]}px;
        padding: {DIMENSIONS["spacing_md"]}px {DIMENSIONS["spacing_lg"]}px;
        border: 1px solid {COLORS["browse_pressed"]};
        min-height: 36px;
    }}
    QPushButton:hover {{
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
            stop:0 {COLORS["browse_hover"]},
            stop:1 {COLORS["browse"]});
        border: 1px solid {COLORS["highlight"]};
    }}
    QPushButton:pressed {{
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
            stop:0 {COLORS["browse_pressed"]},
            stop:1 {COLORS["browse_gradient_end"]});
    }}
    QPushButton:disabled {{
        background: {COLORS["disabled"]};
        color: {COLORS["disabled_text"]};
        border: 1px solid {COLORS["border"]};
    }}
    """


def get_extraction_checklist_style() -> str:
    """
    Get styling for extraction readiness checklist display.

    Shows extraction requirements as a checklist with visual indicators.
    Uses a left border accent to draw attention to pending items.

    Returns:
        CSS string for extraction checklist label styling
    """
    return f"""
    QLabel {{
        color: {COLORS["text_secondary"]};
        font-size: {FONTS["small_size"]};
        padding: {DIMENSIONS["spacing_sm"]}px {DIMENSIONS["spacing_md"]}px;
        background-color: {COLORS["panel_background"]};
        border-left: 3px solid {COLORS["warning"]};
        border-radius: {DIMENSIONS["border_radius_small"]}px;
        line-height: 1.4;
    }}
    """


def get_ready_status_style() -> str:
    """
    Get styling for ready/success status display.

    Shows positive status with green accent to indicate extraction is ready.
    Complements get_extraction_checklist_style() for the ready state.

    Returns:
        CSS string for ready status label styling
    """
    return f"""
    QLabel {{
        color: {COLORS["success"]};
        font-size: {FONTS["small_size"]};
        padding: {DIMENSIONS["spacing_sm"]}px {DIMENSIONS["spacing_md"]}px;
        background-color: {COLORS["panel_background"]};
        border-left: 3px solid {COLORS["success"]};
        border-radius: {DIMENSIONS["border_radius_small"]}px;
    }}
    """


def get_drop_zone_style(state: str = "empty", required: bool = True) -> str:
    """
    Get drop zone styling CSS based on state and requirement.

    Provides distinct visual states for file drop zones to clearly
    communicate what's needed and what's loaded.

    Args:
        state: Drop zone state - "empty", "loaded", "hover"
        required: Whether this drop zone is required for extraction

    Returns:
        CSS string for drop zone styling
    """
    if state == "loaded":
        # Loaded state - green accent, solid border
        return f"""
        DropZone {{
            border: 2px solid {COLORS["editor"]};
            border-radius: 8px;
            background-color: rgba(50, 205, 50, 0.1);
        }}
        """
    if state == "hover":
        # Hover/drag state - highlight border
        return f"""
        DropZone {{
            border: 2px solid {COLORS["border_focus"]};
            border-radius: 8px;
            background-color: {COLORS["panel_background"]};
        }}
        """
    # Empty states
    if required:
        # Empty + Required - subtle warning tint
        return f"""
        DropZone {{
            border: 2px dashed {COLORS["warning"]};
            border-radius: 8px;
            background-color: rgba(255, 215, 0, 0.05);
        }}
        """
    # Empty + Optional - muted/subtle
    return f"""
    DropZone {{
        border: 2px dashed {COLORS["text_muted"]};
        border-radius: 8px;
        background-color: {COLORS["input_background"]};
    }}
    """


def get_step_badge_style(state: str = "pending") -> str:
    """
    Get styling for workflow step badges (numbered step indicators).

    Creates circular badges showing step numbers with visual states
    to guide users through a multi-step workflow.

    Args:
        state: Badge state - "pending", "active", "completed"

    Returns:
        CSS string for step badge styling
    """
    styles = {
        "pending": f"""
            QLabel {{
                color: {COLORS["text_muted"]};
                background-color: {COLORS["dark_gray"]};
                border: 2px solid {COLORS["text_muted"]};
                border-radius: 12px;
                padding: 2px;
                min-width: 24px;
                max-width: 24px;
                min-height: 24px;
                max-height: 24px;
                font-weight: bold;
                font-size: 12px;
                qproperty-alignment: AlignCenter;
            }}
        """,
        "active": f"""
            QLabel {{
                color: {COLORS["white"]};
                background-color: {COLORS["highlight"]};
                border: 2px solid {COLORS["highlight_border"]};
                border-radius: 12px;
                padding: 2px;
                min-width: 24px;
                max-width: 24px;
                min-height: 24px;
                max-height: 24px;
                font-weight: bold;
                font-size: 12px;
                qproperty-alignment: AlignCenter;
            }}
        """,
        "completed": f"""
            QLabel {{
                color: {COLORS["white"]};
                background-color: {COLORS["editor"]};
                border: 2px solid {COLORS["editor"]};
                border-radius: 12px;
                padding: 2px;
                min-width: 24px;
                max-width: 24px;
                min-height: 24px;
                max-height: 24px;
                font-weight: bold;
                font-size: 12px;
                qproperty-alignment: AlignCenter;
            }}
        """,
    }
    return styles.get(state, styles["pending"])


def get_drop_zone_badge_style(badge_type: str = "required") -> str:
    """
    Get styling for drop zone badges (Required/Optional/Loaded).

    Creates small badge indicators to clarify drop zone status.

    Args:
        badge_type: Badge type - "required", "optional", "loaded"

    Returns:
        CSS string for badge label styling
    """
    styles = {
        "required": f"""
            QLabel {{
                color: {COLORS["warning"]};
                font-size: {FONTS["small_size"]};
                font-weight: {FONTS["bold_weight"]};
                background-color: rgba(255, 215, 0, 0.15);
                border: 1px solid {COLORS["warning"]};
                border-radius: 3px;
                padding: 1px 6px;
            }}
        """,
        "optional": f"""
            QLabel {{
                color: {COLORS["text_muted"]};
                font-size: {FONTS["small_size"]};
                background-color: transparent;
                border: 1px solid {COLORS["text_muted"]};
                border-radius: 3px;
                padding: 1px 6px;
            }}
        """,
        "loaded": f"""
            QLabel {{
                color: {COLORS["editor"]};
                font-size: {FONTS["small_size"]};
                font-weight: {FONTS["bold_weight"]};
                background-color: rgba(50, 205, 50, 0.15);
                border: 1px solid {COLORS["editor"]};
                border-radius: 3px;
                padding: 1px 6px;
            }}
        """,
    }
    return styles.get(badge_type, styles["required"])


def get_danger_action_button_style() -> str:
    """
    Get styling for dangerous/destructive action buttons like 'Inject'.

    Uses a warning red color to signal ROM-modifying actions that
    should be used carefully. Matches height with primary Extract button.

    Returns:
        CSS string for danger action button styling
    """
    return f"""
    QPushButton {{
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
            stop:0 {COLORS["danger_action_hover"]},
            stop:1 {COLORS["danger_action"]});
        color: {COLORS["white"]};
        font-weight: {FONTS["bold_weight"]};
        font-size: {FONTS["medium_size"]};
        border-radius: {DIMENSIONS["border_radius_large"]}px;
        padding: {DIMENSIONS["spacing_md"]}px {DIMENSIONS["spacing_lg"]}px;
        border: 1px solid {COLORS["danger_action_pressed"]};
    }}
    QPushButton:hover {{
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
            stop:0 #ff7b7b,
            stop:1 {COLORS["danger_action_hover"]});
        border: 1px solid {COLORS["danger_action"]};
    }}
    QPushButton:pressed {{
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
            stop:0 {COLORS["danger_action_pressed"]},
            stop:1 {COLORS["danger_action"]});
    }}
    QPushButton:disabled {{
        background: {COLORS["disabled"]};
        color: {COLORS["disabled_text"]};
        border: 1px solid {COLORS["border"]};
    }}
    """
