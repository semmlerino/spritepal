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
    ExtractionError,
    FileOperationError,
    InjectionError,
    ManagerError,
    NavigationError,
    PreviewError,
    SessionError,
    ValidationError,
)

__all__ = [
    "CacheCorruptionError",
    "CacheError",
    "CachePermissionError",
    "ExtractionError",
    "FileOperationError",
    "InjectionError",
    "ManagerError",
    "NavigationError",
    "PreviewError",
    "SessionError",
    "ValidationError",
]
