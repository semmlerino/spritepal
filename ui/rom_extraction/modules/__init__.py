"""
Modules for ROM extraction panel.

These modules encapsulate subsystem logic and manage lifecycle
of components, removing AppContext dependencies from panels.
"""

from __future__ import annotations

from ui.rom_extraction.modules.mesen2_module import Mesen2Module

__all__ = [
    "Mesen2Module",
]
