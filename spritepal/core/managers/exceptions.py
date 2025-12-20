"""
Custom exceptions for manager classes.

DEPRECATED: This module re-exports exceptions from core.exceptions for backward
compatibility. New code should import directly from core.exceptions.
"""
from __future__ import annotations

# Re-export all exceptions from the canonical location
from core.exceptions import (
    CacheCorruptionError,
    CacheError,
    CachePermissionError,
    CGRAMError,
    ExtractionError,
    FileFormatError,
    FileOperationError,
    InjectionError,
    ManagerError,
    NavigationError,
    OAMError,
    PreviewError,
    SessionError,
    SpritePalError,
    TileError,
    ValidationError,
    VRAMError,
)

__all__ = [
    "CGRAMError",
    "CacheCorruptionError",
    "CacheError",
    "CachePermissionError",
    "ExtractionError",
    "FileFormatError",
    "FileOperationError",
    "InjectionError",
    "ManagerError",
    "NavigationError",
    "OAMError",
    "PreviewError",
    "SessionError",
    "SpritePalError",
    "TileError",
    "VRAMError",
    "ValidationError",
]
