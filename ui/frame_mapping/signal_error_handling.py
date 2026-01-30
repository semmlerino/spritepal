"""Error boundary decorator for Qt signal handlers.

Signal handlers that raise exceptions can crash or freeze the UI since
exceptions propagate to the Qt event loop. This decorator catches and
logs exceptions to prevent UI corruption.
"""

from collections.abc import Callable
from functools import wraps
from typing import Any, TypeVar

from utils.logging_config import get_logger

logger = get_logger(__name__)
F = TypeVar("F", bound=Callable[..., None])


def signal_error_boundary(handler_name: str | None = None) -> Callable[[F], F]:
    """Catch and log exceptions in signal handlers.

    Args:
        handler_name: Optional name for logging. Defaults to function name.

    Returns:
        Decorated function that catches exceptions and logs them.

    Example:
        @signal_error_boundary()
        def _on_some_signal(self, value: int) -> None:
            # If this raises, error is logged but UI doesn't freeze
            ...
    """

    def decorator(func: F) -> F:
        name = handler_name or func.__name__

        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> None:  # pyright: ignore[reportExplicitAny]
            try:
                return func(*args, **kwargs)
            except Exception:
                logger.exception("Error in signal handler '%s'", name)

        return wrapper  # type: ignore[return-value]

    return decorator
