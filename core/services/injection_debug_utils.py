"""Utilities for injection debug context management."""

from contextlib import contextmanager
from typing import Iterator

from core.services.injection_debug_context import InjectionDebugContext


@contextmanager
def managed_debug_context(
    explicit_debug: bool = False,
) -> Iterator[InjectionDebugContext]:
    """Manage injection debug context with optional explicit override.

    Uses environment-based debug context by default. If explicit_debug=True,
    force-enables debug mode regardless of environment.

    Args:
        explicit_debug: If True, override environment settings to enable debug.

    Yields:
        InjectionDebugContext: The debug context for the current operation.

    Example:
        >>> with managed_debug_context(explicit_debug=True) as debug_ctx:
        ...     result = orchestrator.execute(..., debug_context=debug_ctx)
    """
    with InjectionDebugContext.from_env() as debug_ctx:
        # Override with explicit debug flag if passed
        if explicit_debug and not debug_ctx.enabled:
            debug_ctx = InjectionDebugContext(enabled=True)
            debug_ctx.__enter__()
            try:
                yield debug_ctx
            finally:
                debug_ctx.__exit__(None, None, None)
        else:
            yield debug_ctx
