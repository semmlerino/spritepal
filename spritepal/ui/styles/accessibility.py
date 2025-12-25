"""
Global accessibility styles for SpritePal application.
Provides consistent focus indicators, keyboard navigation hints, and WCAG 2.1 compliance.

NOTE: This file uses dark theme compatible colors from theme.py.
Focus states use bright borders instead of light backgrounds.
"""
from __future__ import annotations

from typing import cast

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from .theme import COLORS


def apply_global_accessibility_styles() -> None:
    """Apply global accessibility styles to the application."""
    app = QApplication.instance()
    if not app:
        return

    # Cast to QApplication for type checker
    app = cast(QApplication, app)

    # Global accessibility stylesheet with focus indicators
    # Uses dark theme compatible colors - bright borders instead of light backgrounds
    global_style = f"""
    /* ===== FOCUS INDICATORS (Dark Theme Compatible) ===== */
    /* All focusable widgets get a clear focus outline (3px for visibility) */
    QWidget:focus {{
        outline: 3px solid {COLORS["border_focus"]};
        outline-offset: 1px;
    }}

    /* Text input fields - dark background with bright border */
    QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {{
        border: 3px solid {COLORS["border_focus"]};
        background-color: {COLORS["focus_background"]};
        color: {COLORS["text_primary"]};
    }}

    /* Buttons - dark background with bright border */
    QPushButton:focus {{
        border: 3px solid {COLORS["border_focus"]};
        padding: 3px;
        background-color: {COLORS["focus_background"]};
        color: {COLORS["text_primary"]};
    }}

    QPushButton:default {{
        font-weight: bold;
        border-width: 2px;
    }}

    /* Dropdowns and spinners */
    QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus {{
        border: 3px solid {COLORS["border_focus"]};
        background-color: {COLORS["focus_background"]};
        color: {COLORS["text_primary"]};
    }}

    /* Sliders */
    QSlider:focus {{
        border: 1px solid {COLORS["border_focus"]};
        background-color: {COLORS["focus_background_subtle"]};
        color: {COLORS["text_primary"]};
    }}

    /* Checkboxes and radio buttons - subtle focus indication */
    QCheckBox:focus, QRadioButton:focus {{
        color: {COLORS["text_primary"]};
    }}

    QCheckBox:focus::indicator, QRadioButton:focus::indicator {{
        border: 1px solid {COLORS["border"]};
    }}

    /* Tab widgets */
    QTabBar::tab:focus {{
        border: 3px solid {COLORS["border_focus"]};
        background-color: {COLORS["focus_background"]};
        color: {COLORS["text_primary"]};
    }}

    QTabBar::tab:selected {{
        font-weight: bold;
        background-color: {COLORS["panel_background"]};
        color: {COLORS["text_primary"]};
    }}

    /* List widgets */
    QListWidget:focus, QTreeWidget:focus, QTableWidget:focus {{
        border: 2px solid {COLORS["border_focus"]};
    }}

    QListWidget::item:focus, QTreeWidget::item:focus, QTableWidget::item:focus {{
        background-color: {COLORS["border_focus"]};
        color: {COLORS["text_primary"]};
    }}

    /* ===== TOOLTIPS (Dark Theme) ===== */
    QToolTip {{
        background-color: {COLORS["panel_background"]};
        color: {COLORS["text_primary"]};
        border: 1px solid {COLORS["border_focus"]};
        padding: 5px;
        font-size: 10pt;
    }}

    /* Status bar messages */
    QStatusBar {{
        font-size: 10pt;
        color: {COLORS["text_primary"]};
        background-color: {COLORS["panel_background"]};
    }}

    /* ===== KEYBOARD NAVIGATION HINTS ===== */
    /* Menu bar items */
    QMenuBar::item:selected {{
        background-color: {COLORS["border_focus"]};
        color: {COLORS["text_primary"]};
    }}

    QMenuBar::item:focus {{
        border: 2px solid {COLORS["border_focus"]};
    }}

    /* Menu items */
    QMenu::item:selected {{
        background-color: {COLORS["border_focus"]};
        color: {COLORS["text_primary"]};
    }}

    QMenu::item:focus {{
        background-color: {COLORS["border_focus"]};
        color: {COLORS["text_primary"]};
        font-weight: bold;
    }}

    /* Toolbar buttons */
    QToolButton:focus {{
        border: 2px solid {COLORS["border_focus"]};
        background-color: {COLORS["focus_background"]};
    }}

    /* ===== DISABLED STATES (Dark Theme) ===== */
    /* Clear visual distinction for disabled items */
    QWidget:disabled {{
        color: {COLORS["disabled_text"]};
        background-color: {COLORS["disabled"]};
    }}

    QPushButton:disabled {{
        color: {COLORS["disabled_text"]};
        background-color: {COLORS["disabled"]};
        border: 1px solid {COLORS["border"]};
    }}

    QLineEdit:disabled, QTextEdit:disabled {{
        color: {COLORS["disabled_text"]};
        background-color: {COLORS["disabled"]};
        border: 1px solid {COLORS["border"]};
    }}

    /* ===== GROUP BOXES (Dark Theme) ===== */
    /* Make group boxes more visible - tighter margins, more internal padding */
    QGroupBox {{
        font-weight: bold;
        border: 2px solid {COLORS["border"]};
        border-radius: 5px;
        margin-top: 8px;
        padding-top: 12px;
    }}

    QGroupBox::title {{
        subcontrol-origin: margin;
        left: 10px;
        padding: 0 5px 0 5px;
        background-color: {COLORS["panel_background"]};
        color: {COLORS["text_primary"]};
    }}

    QGroupBox:focus {{
        border: 2px solid {COLORS["border_focus"]};
    }}

    /* ===== SCROLL BARS (Dark Theme) ===== */
    /* Larger scroll bars for better accessibility */
    QScrollBar:vertical {{
        width: 16px;
        background-color: {COLORS["background"]};
    }}

    QScrollBar:horizontal {{
        height: 16px;
        background-color: {COLORS["background"]};
    }}

    QScrollBar::handle {{
        background-color: {COLORS["border"]};
        border-radius: 3px;
    }}

    QScrollBar::handle:hover {{
        background-color: {COLORS["light_gray"]};
    }}

    QScrollBar::handle:focus {{
        background-color: {COLORS["border_focus"]};
    }}

    /* ===== SPLITTERS (Dark Theme) ===== */
    /* More visible splitter handles */
    QSplitter::handle {{
        background-color: {COLORS["separator"]};
    }}

    QSplitter::handle:hover {{
        background-color: {COLORS["border"]};
    }}

    QSplitter::handle:focus {{
        background-color: {COLORS["border_focus"]};
    }}

    /* ===== ERROR STATES (Dark Theme) ===== */
    /* Clear error indication */
    QLineEdit[hasError="true"], QTextEdit[hasError="true"] {{
        border: 2px solid {COLORS["border_error"]};
        background-color: #3d1a1a;
        color: {COLORS["text_primary"]};
    }}

    /* ===== SELECTION COLORS ===== */
    /* High contrast selection */
    QWidget::selection {{
        background-color: {COLORS["border_focus"]};
        color: {COLORS["text_primary"]};
    }}

    /* ===== DIALOG BUTTONS ===== */
    /* Standard dialog buttons */
    QDialogButtonBox QPushButton {{
        min-width: 80px;
        min-height: 25px;
    }}

    QDialogButtonBox QPushButton:default {{
        background-color: {COLORS["border_focus"]};
        color: {COLORS["text_primary"]};
        font-weight: bold;
    }}

    QDialogButtonBox QPushButton:default:focus {{
        background-color: #005a9e;
        border: 2px solid {COLORS["highlight"]};
    }}
    """

    # Apply the stylesheet
    current_style = app.styleSheet()
    app.setStyleSheet(current_style + global_style)

    # Set application-wide attributes for better accessibility
    # Note: UI animation effects are controlled by Qt's UIEffect enum
    try:
        # These are Qt5/Qt6 specific - may not be available in all versions
        app.setEffectEnabled(Qt.UIEffect.UI_AnimateCombo, False)  # Disable animations that can be distracting
        app.setEffectEnabled(Qt.UIEffect.UI_AnimateTooltip, False)
    except (AttributeError, TypeError):
        # UIEffect may not be available in this Qt version
        pass

    # Ensure high DPI support for better readability
    try:
        # These attributes may vary between Qt versions
        app.setAttribute(Qt.ApplicationAttribute.AA_UseHighDpiPixmaps, True)
        app.setAttribute(Qt.ApplicationAttribute.AA_EnableHighDpiScaling, True)
    except (AttributeError, TypeError):
        # Some attributes may not be available in this Qt version
        pass

def configure_accessibility_settings() -> None:
    """Configure application-wide accessibility settings."""
    app = QApplication.instance()
    if not app:
        return

    # Cast to QApplication for type checker
    app = cast(QApplication, app)

    # Set default font size for better readability
    font = app.font()
    if font.pointSize() < 10:
        font.setPointSize(10)
        app.setFont(font)

    # Note: setNavigationMode is not available in Qt6/PySide6
    # Keyboard navigation is enabled by default in modern Qt

    # Set double-click interval for users with motor impairments
    try:
        app.setDoubleClickInterval(600)  # 600ms instead of default 400ms
    except AttributeError:
        # This method might not be available in all Qt versions
        pass

def initialize_accessibility() -> None:
    """Initialize all accessibility features for the application."""
    apply_global_accessibility_styles()
    configure_accessibility_settings()
