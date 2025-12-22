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
    CacheStatsProtocol,
    ConfigurationServiceProtocol,
    CurrentOffsetProtocol,
    ExtractionManagerProtocol,
    InjectionManagerProtocol,
    ROMCacheProtocol,
    ROMExtractorProtocol,
    RuntimeStateProtocol,
    SessionPersistenceProtocol,
    SettingsAccessProtocol,
    SettingsManagerProtocol,
    SpritePresetManagerProtocol,
    WorkflowStateProtocol,
)
from .worker_protocols import (
    PreviewWorkerPoolProtocol,
)

__all__ = [
    "ApplicationStateManagerProtocol",
    "ArrangementDialogProtocol",
    "CacheStatsProtocol",
    "ConfigurationServiceProtocol",
    "CurrentOffsetProtocol",
    "DialogFactoryProtocol",
    "ExtractionManagerProtocol",
    "InjectionDialogProtocol",
    "InjectionManagerProtocol",
    "ManualOffsetDialogFactoryProtocol",
    "ManualOffsetDialogProtocol",
    "PreviewWorkerPoolProtocol",
    "ROMCacheProtocol",
    "ROMExtractorProtocol",
    "RuntimeStateProtocol",
    "SessionPersistenceProtocol",
    "SettingsAccessProtocol",
    "SettingsManagerProtocol",
    "SpritePresetManagerProtocol",
    "WorkflowStateProtocol",
]
