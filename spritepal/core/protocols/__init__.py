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
    ManualOffsetDialogFactoryProtocol,
    ManualOffsetDialogProtocol,
)
from .manager_protocols import (
    ApplicationStateManagerProtocol,
    ConfigurationServiceProtocol,
    ExtractionManagerProtocol,
    InjectionManagerProtocol,
    ROMCacheProtocol,
    ROMExtractorProtocol,
    ROMServiceProtocol,
    SettingsManagerProtocol,
    SpritePresetManagerProtocol,
    VRAMServiceProtocol,
)
from .preview_protocols import (
    PreviewCoordinatorProtocol,
)
from .worker_protocols import (
    PreviewWorkerPoolProtocol,
)

__all__ = [
    "ApplicationStateManagerProtocol",
    "ArrangementDialogProtocol",
    "ConfigurationServiceProtocol",
    "DialogFactoryProtocol",
    "ExtractionManagerProtocol",
    "InjectionDialogProtocol",
    "InjectionManagerProtocol",
    "ManualOffsetDialogFactoryProtocol",
    "ManualOffsetDialogProtocol",
    "PreviewCoordinatorProtocol",
    "PreviewWorkerPoolProtocol",
    "ROMCacheProtocol",
    "ROMExtractorProtocol",
    "ROMServiceProtocol",
    "SettingsManagerProtocol",
    "SpritePresetManagerProtocol",
    "VRAMServiceProtocol",
]
