"""
Protocol definitions for SpritePal core components.

These protocols define the interfaces that components depend on,
enabling dependency injection and better testability.
"""
from __future__ import annotations

from .dialog_protocols import (
    ArrangementDialogProtocol,
    DialogFactoryProtocol,
    ManualOffsetDialogFactoryProtocol,
)
from .manager_protocols import (
    ExtractionManagerProtocol,
    InjectionManagerProtocol,
    ROMCacheProtocol,
    ROMExtractorProtocol,
)

__all__ = [
    "ArrangementDialogProtocol",
    "DialogFactoryProtocol",
    "ExtractionManagerProtocol",
    "InjectionManagerProtocol",
    "ManualOffsetDialogFactoryProtocol",
    "ROMCacheProtocol",
    "ROMExtractorProtocol",
]
