"""
Worker thread architecture for SpritePal.

This module provides a standardized framework for async operations using QThread.
All workers inherit from common base classes to ensure consistent interfaces,
proper error handling, and type safety.

Base Classes:
- BaseWorker: Foundation for all worker threads
- ManagedWorker: Workers that delegate to managers
- ExtractionWorkerBase: Specialized for extraction operations
- InjectionWorkerBase: Specialized for injection operations
- ScanWorkerBase: Specialized for scanning operations
- PreviewWorkerBase: Specialized for preview generation operations

Workers receive their manager via constructor (dependency injection pattern).
"""
from __future__ import annotations

from .base import BaseWorker, ManagedWorker
from .extraction import (
    ROMExtractionWorker,
    VRAMExtractionWorker,
)
from .injection import (
    ROMInjectionParams,
    ROMInjectionWorker,
    VRAMInjectionParams,
    VRAMInjectionWorker,
)
from .specialized import (
    ExtractionWorkerBase,
    InjectionWorkerBase,
    PreviewWorkerBase,
    ScanWorkerBase,
)

__all__ = [
    "BaseWorker",
    "ExtractionWorkerBase",
    "InjectionWorkerBase",
    "ManagedWorker",
    "PreviewWorkerBase",
    "ROMExtractionWorker",
    "ROMInjectionParams",
    "ROMInjectionWorker",
    "ScanWorkerBase",
    "VRAMExtractionWorker",
    "VRAMInjectionParams",
    "VRAMInjectionWorker",
]
