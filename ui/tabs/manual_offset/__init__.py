"""
Manual offset tab widgets.

This module provides tab widgets for the manual offset dialog:
- SimpleBrowseTab: Navigation controls and search
- SimpleSmartTab: Region-based smart navigation
"""

from __future__ import annotations

from .browse_tab import SimpleBrowseTab
from .smart_tab import SimpleSmartTab

__all__ = [
    "SimpleBrowseTab",
    "SimpleSmartTab",
]
