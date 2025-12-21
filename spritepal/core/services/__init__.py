"""
Core services package.

This package contains service classes that provide cross-cutting functionality
used by both core and UI layers. Services in this package:

- worker_lifecycle.py: WorkerManager for QThread worker lifecycle management
- preview_generator.py: PreviewGenerator for async preview image generation
- rom_service.py: ROMService for ROM-based sprite extraction operations
- vram_service.py: VRAMService for VRAM-based sprite extraction operations
- settings_manager.py: SettingsManager for application settings persistence
- rom_cache.py: ROMCache for ROM scan result caching
- signal_registry.py: SignalRegistry for tracking Qt signal connections

These services are placed in core/ rather than utils/ because they depend on Qt
or core layer types. The utils/ package is reserved for pure Python utilities
with only stdlib dependencies.
"""
from __future__ import annotations

from core.services.preview_generator import (
    LRUCache,
    PaletteData,
    PreviewGenerator,
    PreviewRequest,
    PreviewResult,
    cleanup_preview_generator,
    create_rom_preview_request,
    create_vram_preview_request,
    get_preview_generator,
)
from core.services.rom_cache import ROMCache
from core.services.rom_service import ROMService
from core.services.settings_manager import SettingsManager
from core.services.signal_registry import ConnectionInfo, SignalRegistry
from core.services.state_snapshot_service import StateSnapshotService
from core.services.vram_service import VRAMService
from core.services.worker_lifecycle import WorkerManager

__all__ = [
    # Connection tracking
    "ConnectionInfo",
    "LRUCache",
    "PaletteData",
    # Preview generator
    "PreviewGenerator",
    "PreviewRequest",
    "PreviewResult",
    # ROM and VRAM services
    "ROMCache",
    "ROMService",
    # Settings
    "SettingsManager",
    # Signal tracking
    "SignalRegistry",
    # State snapshot
    "StateSnapshotService",
    "VRAMService",
    # Worker lifecycle
    "WorkerManager",
    "cleanup_preview_generator",
    "create_rom_preview_request",
    "create_vram_preview_request",
    "get_preview_generator",
]
