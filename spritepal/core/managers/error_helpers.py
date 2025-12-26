"""Standalone error handling helpers for manager operations.

These functions can be used independently or integrated with BaseManager
via the on_error callback parameter.
"""

from __future__ import annotations

from collections.abc import Callable

# Type for the error callback that handles logging + signal emission
# Signature matches BaseManager._handle_error(error, operation)
ErrorCallback = Callable[[Exception, str | None], None]


def handle_categorized_error(
    error: Exception,
    operation: str,
    category: str,
    context: str = "",
    error_class: type[Exception] | None = None,
    *,
    on_error: ErrorCallback | None = None,
) -> Exception:
    """Create and optionally report a categorized error.

    This function builds an enhanced exception with category and context
    information, optionally calls the on_error callback for logging/signals,
    and returns the exception for the caller to raise.

    Args:
        error: The original exception
        operation: Operation name for context
        category: Error category (e.g., "File I/O", "Data format")
        context: Additional context for the error message
        error_class: Exception class for wrapping. If None, uses original type.
        on_error: Callback for logging/signals. If None, error is returned without
                  side effects (useful for pure exception creation).

    Returns:
        The enhanced exception (not raised, caller decides)
    """
    context_suffix = f" {context}" if context else ""
    enhanced_msg = f"{category} error during {operation}{context_suffix}: {error!s}"

    exc_class = error_class if error_class is not None else type(error)
    enhanced_error = exc_class(enhanced_msg)
    enhanced_error.__cause__ = error

    if on_error is not None:
        on_error(enhanced_error, operation)

    return enhanced_error


def handle_file_io_error(
    error: Exception,
    operation: str,
    context: str = "",
    *,
    on_error: ErrorCallback | None = None,
) -> Exception:
    """Handle file I/O errors (OSError, PermissionError, etc.).

    Args:
        error: The original exception
        operation: Operation name for context
        context: Additional context for the error message
        on_error: Callback for logging/signals

    Returns:
        The enhanced exception with "File I/O" category
    """
    return handle_categorized_error(error, operation, "File I/O", context, on_error=on_error)


def handle_data_format_error(
    error: Exception,
    operation: str,
    context: str = "",
    *,
    on_error: ErrorCallback | None = None,
) -> Exception:
    """Handle data format errors (ValueError, TypeError, etc.).

    Args:
        error: The original exception
        operation: Operation name for context
        context: Additional context for the error message
        on_error: Callback for logging/signals

    Returns:
        The enhanced exception with "Data format" category
    """
    return handle_categorized_error(error, operation, "Data format", context, on_error=on_error)


def handle_operation_error(
    error: Exception,
    operation: str,
    error_class: type[Exception],
    context: str = "",
    *,
    on_error: ErrorCallback | None = None,
) -> Exception:
    """Handle operation-specific errors with custom exception wrapping.

    Args:
        error: The original exception
        operation: Operation name (also used as category via title())
        error_class: Exception class for wrapping
        context: Additional context for the error message
        on_error: Callback for logging/signals

    Returns:
        The enhanced exception with operation name as category
    """
    return handle_categorized_error(error, operation, operation.title(), context, error_class, on_error=on_error)
