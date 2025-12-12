"""
Protocol definitions for SpritePal core components.

These protocols define the interfaces that components depend on,
enabling dependency injection and better testability.
"""
from __future__ import annotations

from .dialog_protocols import (
    ArrangementDialogProtocol,
    DialogFactoryProtocol,
    InjectionDialogProtocol,
)
from .error_handler_protocol import ErrorHandlerProtocol
from .manager_protocols import (
    ExtractionManagerProtocol,
    InjectionManagerProtocol,
    MainWindowProtocol,
    SessionManagerProtocol,
)
from .worker_protocol import WorkerManagerProtocol

__all__ = [
    "ArrangementDialogProtocol",
    "DialogFactoryProtocol",
    "ErrorHandlerProtocol",
    "ExtractionManagerProtocol",
    "InjectionDialogProtocol",
    "InjectionManagerProtocol",
    "MainWindowProtocol",
    "SessionManagerProtocol",
    "WorkerManagerProtocol",
]
