"""Decorator for standardized operation handling in managers.

This module provides a Protocol-based decorator that works with any
manager class implementing the required interface.
"""
from __future__ import annotations

import functools
from collections.abc import Callable
from typing import Any, Protocol, TypeVar

from core.exceptions import ValidationError

from .error_helpers import (
    handle_data_format_error,
    handle_file_io_error,
    handle_operation_error,
)

T = TypeVar("T")


class OperationManager(Protocol):
    """Protocol for managers that support operation handling.

    Defines the minimal interface required by with_operation_handling.
    Any class implementing these methods can use the decorator.
    """

    def _start_operation(self, operation: str) -> bool:
        """Start tracking an operation. Returns True if started, False if already active."""
        ...

    def _finish_operation(self, operation: str) -> None:
        """Finish tracking an operation."""
        ...

    def _update_progress(self, operation: str, current: int, total: int) -> None:
        """Update operation progress."""
        ...

    def _handle_error(self, error: Exception, operation: str | None = None) -> None:
        """Handle error with logging and signal emission."""
        ...


def with_operation_handling(
    operation: str,
    context: str,
    *,
    with_progress: bool = True,
    exclusive: bool = True,
    target_error: type[Exception] | None = None,
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """Decorator for operations with standardized error handling.

    Handles:
    - Operation lifecycle (start/finish)
    - Progress updates (optional)
    - Categorized exception handling for File I/O, data format, and general errors

    Args:
        operation: Operation identifier for tracking
        context: Human-readable context for error messages
        with_progress: If True, emit progress at 0% and 100%
        exclusive: If True, raise if operation already in progress
        target_error: Exception type for wrapping unexpected errors (default: Exception)

    Usage:
        @with_operation_handling("extraction", "file extraction", with_progress=True)
        def extract(self, path: str) -> list[str]:
            return self._service.extract(path)
    """
    final_target_error = target_error if target_error is not None else Exception

    def decorator(method: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(method)
        def wrapper(
            self: OperationManager,
            *args: Any,  # pyright: ignore[reportExplicitAny] - generic decorator
            **kwargs: Any,  # pyright: ignore[reportExplicitAny] - generic decorator
        ) -> T:
            started = self._start_operation(operation)
            if exclusive and not started:
                raise final_target_error(f"{operation} already in progress")

            try:
                if with_progress:
                    self._update_progress(operation, 0, 100)
                result = method(self, *args, **kwargs)
                if with_progress:
                    self._update_progress(operation, 100, 100)
                return result
            except (OSError, PermissionError) as e:
                enhanced = handle_file_io_error(
                    e, operation, context, on_error=self._handle_error
                )
                raise enhanced from e
            except (ValueError, TypeError) as e:
                enhanced = handle_data_format_error(
                    e, operation, context, on_error=self._handle_error
                )
                raise enhanced from e
            except ValidationError:
                raise
            except Exception as e:
                if not isinstance(e, final_target_error):
                    enhanced = handle_operation_error(
                        e, operation, final_target_error, context, on_error=self._handle_error
                    )
                    raise enhanced from e
                raise
            finally:
                if started:
                    self._finish_operation(operation)

        return wrapper

    return decorator
