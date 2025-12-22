"""
Custom exceptions for SpritePal.

This module contains all exceptions that can be raised throughout the application.
All exception classes are defined here to maintain a single source of truth.
"""
from __future__ import annotations


# Base exception for all SpritePal errors
class SpritePalError(Exception):
    """Base exception for all SpritePal errors."""


# Manager-related exceptions (inherit from SpritePalError for unified hierarchy)
class ManagerError(SpritePalError):
    """Base exception for all manager-related errors."""


class ExtractionError(ManagerError):
    """Exception raised during extraction operations."""


class SessionError(ManagerError):
    """Exception raised during session/settings operations."""


class ValidationError(ManagerError):
    """Exception raised when parameter validation fails."""


class InjectionError(ManagerError):
    """Exception raised during injection operations."""


class PreviewError(ManagerError):
    """Exception raised during preview generation."""


class FileOperationError(ManagerError):
    """Exception raised during file operations."""


class CacheError(ManagerError):
    """Exception raised during cache operations."""

    def __init__(self, message: str, cache_path: str | None = None) -> None:
        super().__init__(message)
        self.cache_path = cache_path


class NavigationError(ManagerError):
    """Exception raised during navigation operations."""


# File and format exceptions
class FileFormatError(SpritePalError):
    """Raised for unsupported or invalid file formats."""


class TileError(SpritePalError):
    """Raised for tile processing errors."""
