"""
Worker thread architecture for SpritePal.

This module provides a standardized framework for async operations using QThread.
All workers inherit from common base classes to ensure consistent interfaces,
proper error handling, and type safety.

Base Classes:
- BaseWorker: Foundation for all worker threads
- ManagedWorker: Workers that delegate to managers

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

__all__ = [
    "BaseWorker",
    "ManagedWorker",
    "ROMExtractionWorker",
    "ROMInjectionParams",
    "ROMInjectionWorker",
    "VRAMExtractionWorker",
    "VRAMInjectionParams",
    "VRAMInjectionWorker",
]
