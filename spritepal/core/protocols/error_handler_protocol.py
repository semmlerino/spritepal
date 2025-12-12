"""
Error handler protocol for SpritePal.

Defines the interface for error handling throughout the application.
Both ConsoleErrorHandler and UI-based handlers should implement this protocol.
"""
from __future__ import annotations

from typing import Any, Protocol


class ErrorHandlerProtocol(Protocol):
    """
    Protocol defining the error handler interface for type safety.

    Implementations:
    - ConsoleErrorHandler: Logs to console/file (for headless/testing)
    - ErrorHandler (ui/common/error_handler.py): Qt signal-based (for UI)

    Usage:
        def process_data(error_handler: ErrorHandlerProtocol) -> None:
            try:
                # ... processing ...
            except ValueError as e:
                error_handler.handle_warning("Validation", str(e))
    """

    def handle_exception(self, exception: Exception, context: str = "") -> None:
        """
        Handle an exception with optional context.

        Args:
            exception: The exception that occurred
            context: Description of what operation was being performed
        """
        ...

    def handle_critical_error(self, title: str, message: str) -> None:
        """
        Handle a critical error that may require user attention.

        Args:
            title: Short title for the error
            message: Detailed error message
        """
        ...

    def handle_warning(self, title: str, message: str) -> None:
        """
        Handle a warning that doesn't prevent operation but should be noted.

        Args:
            title: Short title for the warning
            message: Warning message
        """
        ...

    def handle_info(self, title: str, message: str) -> None:
        """
        Handle an informational message.

        Args:
            title: Short title
            message: Info message
        """
        ...

    def handle_validation_error(
        self,
        error: Exception,
        context_info: str,
        user_input: str | None = None,
        **context_kwargs: Any,
    ) -> Any:
        """
        Handle a validation error with context.

        Args:
            error: The validation exception
            context_info: Description of what was being validated
            user_input: The user input that failed validation (if applicable)
            **context_kwargs: Additional context information
        """
        ...
