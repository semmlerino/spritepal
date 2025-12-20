"""
Custom exceptions for SpritePal.

DEPRECATED: This module re-exports exceptions from core.exceptions for backward
compatibility. New code should import directly from core.exceptions.
"""
from __future__ import annotations

# Re-export all exceptions from the canonical location
from core.exceptions import (
    CGRAMError,
    ExtractionError,
    FileFormatError,
    InjectionError,
    OAMError,
    SpritePalError,
    TileError,
    ValidationError,
    VRAMError,
)

__all__ = [
    "CGRAMError",
    "ExtractionError",
    "FileFormatError",
    "InjectionError",
    "OAMError",
    "SpritePalError",
    "TileError",
    "VRAMError",
    "ValidationError",
]
