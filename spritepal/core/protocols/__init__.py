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
from .manager_protocols import (
    ApplicationStateManagerProtocol,
    ConfigurationServiceProtocol,
    ExtractionManagerProtocol,
    InjectionManagerProtocol,
    ROMCacheProtocol,
    ROMExtractorProtocol,
    SettingsManagerProtocol,
)

__all__ = [
    "ApplicationStateManagerProtocol",
    "ArrangementDialogProtocol",
    "ConfigurationServiceProtocol",
    "DialogFactoryProtocol",
    "ExtractionManagerProtocol",
    "InjectionDialogProtocol",
    "InjectionManagerProtocol",
    "ROMCacheProtocol",
    "ROMExtractorProtocol",
    "SettingsManagerProtocol",
]
