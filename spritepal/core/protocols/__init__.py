"""
Protocol definitions for SpritePal core components.

These protocols define the interfaces that components depend on,
enabling dependency injection and better testability.

NOTE: Use concrete classes directly via DI:
- inject(CoreOperationsManager) for operations
- inject(ROMCache) for ROM caching
- inject(ROMExtractor) for ROM extraction
"""
from __future__ import annotations

from .dialog_protocols import (
    ArrangementDialogProtocol,
    DialogFactoryProtocol,
)

__all__ = [
    "ArrangementDialogProtocol",
    "DialogFactoryProtocol",
]
