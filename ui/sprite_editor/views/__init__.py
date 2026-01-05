#!/usr/bin/env python3
"""
View components for the sprite editor.
Includes widgets, panels, tabs, and main window.
"""

from .main_window import SpriteEditorMainWindow
from .panels import OptionsPanel, PalettePanel, PreviewPanel, ToolPanel
from .tabs import EditTab, ExtractTab, InjectTab, MultiPaletteTab, MultiPaletteViewer
from .widgets import ColorPaletteWidget, HexLineEdit, PixelCanvas

__all__ = [
    # Widgets
    "ColorPaletteWidget",
    # Tabs
    "EditTab",
    "ExtractTab",
    "HexLineEdit",
    "InjectTab",
    "MultiPaletteTab",
    "MultiPaletteViewer",
    # Panels
    "OptionsPanel",
    "PalettePanel",
    "PixelCanvas",
    "PreviewPanel",
    # Main Window
    "SpriteEditorMainWindow",
    "ToolPanel",
]
