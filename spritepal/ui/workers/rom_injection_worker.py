"""
DEPRECATED: This module has been moved to core/workers/rom_injection_worker.py

This file is maintained only for backward compatibility.
Please update imports to use: from core.workers.rom_injection_worker import ROMInjectionWorker
"""
import warnings

warnings.warn(
    "ui.workers.rom_injection_worker is deprecated. "
    "Use core.workers.rom_injection_worker instead.",
    DeprecationWarning,
    stacklevel=2,
)

from core.workers.rom_injection_worker import ROMInjectionWorker

__all__ = ["ROMInjectionWorker"]
