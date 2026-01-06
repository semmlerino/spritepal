#!/usr/bin/env python3
"""
Tab widgets for the sprite editor.
"""

from .edit_tab import EditTab
from .extract_tab import ExtractTab
from .inject_tab import InjectTab
from .multi_palette_tab import MultiPaletteTab, MultiPaletteViewer
from .rom_workflow_tab import ROMWorkflowTab

__all__ = [
    "EditTab",
    "ExtractTab",
    "InjectTab",
    "MultiPaletteTab",
    "MultiPaletteViewer",
    "ROMWorkflowTab",
]
