"""
DEPRECATED: This module has been moved to core/workers/injection_worker.py

This file is maintained only for backward compatibility.
Please update imports to use: from core.workers.injection_worker import InjectionWorker
"""
import warnings

warnings.warn(
    "ui.workers.injection_worker is deprecated. "
    "Use core.workers.injection_worker instead.",
    DeprecationWarning,
    stacklevel=2,
)

from core.workers.injection_worker import InjectionWorker

__all__ = ["InjectionWorker"]
