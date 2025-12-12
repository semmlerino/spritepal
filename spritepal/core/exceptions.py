"""
Custom exceptions for SpritePal core operations.

This module contains all core exceptions that can be raised throughout the application.
Exception classes were moved here from core/managers/exceptions.py to fix layer
boundary violations (core services should not import from managers).
"""
from __future__ import annotations


class ManagerError(Exception):
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


class CacheCorruptionError(CacheError):
    """Exception raised when cache database is corrupted."""


class CachePermissionError(CacheError):
    """Exception raised when cache access is denied due to permissions."""


class NavigationError(ManagerError):
    """Exception raised during navigation operations."""
