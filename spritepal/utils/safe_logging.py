"""
Safe logging utilities for cleanup operations.

This module provides utilities to prevent "I/O operation on closed file" errors
during application shutdown when logging infrastructure is being torn down.
"""

from __future__ import annotations

import logging
import sys
from collections.abc import Callable
from typing import Any


def is_logging_available() -> bool:
    """Check if logging system is still functional (not shutting down)."""
    return not sys.is_finalizing()


def safe_log(logger: logging.Logger, level: int, message: str, *args: Any, **kwargs: Any) -> None:  # pyright: ignore[reportExplicitAny] - Logging args
    """
    Safely log a message, checking if logging is still active.

    Args:
        logger: Logger instance to use
        level: Log level (logging.DEBUG, logging.INFO, etc.)
        message: Message to log
        *args: Additional args for message formatting
        **kwargs: Additional kwargs for logging
    """
    if not is_logging_available():
        return

    try:
        logger.log(level, message, *args, **kwargs)
    except (ValueError, RuntimeError, OSError, AttributeError):
        # Logging system is shut down or in invalid state
        pass


def safe_debug(logger: logging.Logger, message: str, *args: Any, **kwargs: Any) -> None:  # pyright: ignore[reportExplicitAny] - Logging args
    """Safely log a debug message."""
    safe_log(logger, logging.DEBUG, message, *args, **kwargs)


def safe_info(logger: logging.Logger, message: str, *args: Any, **kwargs: Any) -> None:  # pyright: ignore[reportExplicitAny] - Logging args
    """Safely log an info message."""
    safe_log(logger, logging.INFO, message, *args, **kwargs)


def safe_warning(logger: logging.Logger, message: str, *args: Any, **kwargs: Any) -> None:  # pyright: ignore[reportExplicitAny] - Logging args
    """Safely log a warning message."""
    safe_log(logger, logging.WARNING, message, *args, **kwargs)


def suppress_logging_errors(func: Callable[..., Any]) -> Callable[..., Any]:  # pyright: ignore[reportExplicitAny] - Decorator pattern
    """
    Decorator to suppress logging errors during cleanup operations.

    This decorator catches ValueError exceptions that occur when logging
    to closed file handles and suppresses them during cleanup.
    """

    def wrapper(*args: Any, **kwargs: Any) -> Any:  # pyright: ignore[reportExplicitAny] - Wrapper args and return
        try:
            return func(*args, **kwargs)
        except ValueError as e:
            error_msg = str(e)
            if any(
                phrase in error_msg
                for phrase in ["I/O operation on closed file", "operation on a closed file", "closed file"]
            ):
                # Silently ignore logging errors during shutdown
                pass
            else:
                # Re-raise if it's not a closed file logging error
                raise
        except (RuntimeError, OSError, AttributeError) as e:
            # Also catch other common shutdown-related errors
            error_msg = str(e)
            if any(phrase in error_msg for phrase in ["logging", "handler", "closed", "shutdown"]):
                # Likely logging-related shutdown error, ignore
                pass
            else:
                # Re-raise if it's not logging-related
                raise

    return wrapper
