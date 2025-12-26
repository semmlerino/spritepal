"""
Console-based error handler for fallback scenarios.

This provides a real implementation that logs errors to console instead of
silently swallowing them like MockErrorHandler does.
"""

from __future__ import annotations

import sys
import traceback
from typing import override

from utils.logging_config import get_logger

logger = get_logger(__name__)


class ConsoleErrorHandler:
    """
    Console-based error handler that provides real error handling functionality.

    This replaces MockErrorHandler in production code, ensuring errors are
    properly logged instead of silently ignored.
    """

    def __init__(self, show_dialogs: bool = False) -> None:
        """
        Initialize the console error handler.

        Args:
            show_dialogs: Whether to show dialog boxes (always False for console handler)
        """
        self._show_dialogs = False  # Console handler never shows dialogs
        self._error_count = 0
        self._warning_count = 0

    def handle_exception(self, exception: Exception, context: str = "") -> None:
        """
        Handle an exception by logging it to console.

        Args:
            exception: The exception to handle
            context: Optional context information
        """
        self._error_count += 1

        # Log the full exception with traceback
        logger.error(f"Exception in {context or 'unknown context'}: {exception}")

        # Also print to stderr for visibility
        print(f"ERROR [{context}]: {exception}", file=sys.stderr)

        # Log traceback if available
        if sys.exc_info()[0] is not None:
            logger.error("Traceback:\n%s", traceback.format_exc())

    def handle_critical_error(self, title: str, message: str) -> None:
        """
        Handle a critical error by logging it prominently.

        Args:
            title: Error title
            message: Error message
        """
        self._error_count += 1

        # Log as critical
        logger.critical(f"CRITICAL ERROR - {title}: {message}")

        # Print to stderr with emphasis
        print(f"\n{'=' * 60}", file=sys.stderr)
        print(f"CRITICAL ERROR: {title}", file=sys.stderr)
        print(f"{message}", file=sys.stderr)
        print(f"{'=' * 60}\n", file=sys.stderr)

    def handle_warning(self, title: str, message: str) -> None:
        """
        Handle a warning by logging it.

        Args:
            title: Warning title
            message: Warning message
        """
        self._warning_count += 1

        # Log as warning
        logger.warning(f"{title}: {message}")

        # Print to stderr
        print(f"WARNING [{title}]: {message}", file=sys.stderr)

    def handle_info(self, title: str, message: str) -> None:
        """
        Handle an info message by logging it.

        Args:
            title: Info title
            message: Info message
        """
        # Log as info
        logger.info(f"{title}: {message}")

        # Print to stdout
        print(f"INFO [{title}]: {message}")

    def handle_validation_error(
        self, error: Exception, context_info: str, user_input: str | None = None, **context_kwargs: object
    ) -> None:
        """
        Handle a validation error with context.

        Args:
            error: The validation error
            context_info: Context information
            user_input: Optional user input that caused the error
            **context_kwargs: Additional context
        """
        self._error_count += 1

        # Build detailed error message
        error_msg = f"Validation Error in {context_info}: {error}"

        if user_input:
            error_msg += f"\nUser input: {user_input}"

        if context_kwargs:
            error_msg += f"\nContext: {context_kwargs}"

        # Log the validation error
        logger.error(error_msg)

        # Print to stderr
        print(f"VALIDATION ERROR: {error_msg}", file=sys.stderr)

    def set_show_dialogs(self, show: bool) -> None:
        """
        Set whether to show dialog boxes (no-op for console handler).

        Args:
            show: Whether to show dialogs (ignored)
        """
        # Console handler never shows dialogs
        self._show_dialogs = False

    def get_error_count(self) -> int:
        """Get the total number of errors handled."""
        return self._error_count

    def get_warning_count(self) -> int:
        """Get the total number of warnings handled."""
        return self._warning_count

    def reset_counts(self) -> None:
        """Reset error and warning counts."""
        self._error_count = 0
        self._warning_count = 0

    @override
    def __repr__(self) -> str:
        """String representation of the handler."""
        return f"ConsoleErrorHandler(errors={self._error_count}, warnings={self._warning_count})"
