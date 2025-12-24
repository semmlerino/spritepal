"""
Protocol definitions for SpritePal core components.

These protocols define the interfaces that components depend on,
enabling dependency injection and better testability.

NOTE: ExtractionManagerProtocol and InjectionManagerProtocol have been removed.
Use CoreOperationsManager directly via inject(CoreOperationsManager).
"""
from __future__ import annotations

from .dialog_protocols import (
    ArrangementDialogProtocol,
    DialogFactoryProtocol,
)
from .manager_protocols import (
    ROMCacheProtocol,
    ROMExtractorProtocol,
)

__all__ = [
    "ArrangementDialogProtocol",
    "DialogFactoryProtocol",
    # DEPRECATED: ROMCacheProtocol, ROMExtractorProtocol kept for backward compat
    "ROMCacheProtocol",
    "ROMExtractorProtocol",
]
