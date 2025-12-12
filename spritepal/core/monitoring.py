"""
Monitoring utilities and decorators for SpritePal

Provides convenient decorators and utilities for integrating monitoring
throughout the application with minimal code changes.
"""
from __future__ import annotations

import functools
import time
import traceback
from collections.abc import Callable
from contextlib import contextmanager
from typing import Any, TypeVar

from utils.logging_config import get_logger

# Type variable for decorators
F = TypeVar('F', bound=Callable[..., Any])

logger = get_logger("monitoring")


def get_monitoring_manager():
    """Get the monitoring manager instance."""
    try:
        from core.managers.registry import ManagerRegistry
        registry = ManagerRegistry()
        # Try to get monitoring manager if it exists
        managers = registry.get_all_managers()
        return managers.get("monitoring")
    except Exception:
        return None


@contextmanager
def monitor_performance(operation: str, context: dict[str, Any] | None = None):
    """Context manager for monitoring operation performance.

    Usage:
        with monitor_performance("rom_loading", {"rom_size": 1024}):
            # Your operation here
            load_rom_data()
    """
    monitoring_manager = get_monitoring_manager()

    if monitoring_manager:
        with monitoring_manager.monitor_operation(operation, context):
            yield
    else:
        yield


def monitor_operation(operation: str | None = None, track_usage: bool = True,
                     context: dict[str, Any] | None = None):
    """Decorator for monitoring function/method performance and usage.

    Args:
        operation: Operation name (defaults to function name)
        track_usage: Whether to track as feature usage
        context: Additional context to include

    Usage:
        @monitor_operation("rom_extraction")
        def extract_sprites(self, rom_path: str):
            # Function implementation
    """
    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            # Determine operation name
            op_name = operation or f"{func.__module__}.{func.__qualname__}"

            # Extract context from self if it's a method
            call_context = context or {}
            if args and hasattr(args[0], '__class__'):
                call_context['class'] = args[0].__class__.__name__

            monitoring_manager = get_monitoring_manager()

            # Start timing
            start_time = time.perf_counter()
            success = True
            result = None

            try:
                # Use performance monitoring if available
                if monitoring_manager:
                    with monitoring_manager.monitor_operation(op_name, call_context):
                        result = func(*args, **kwargs)
                else:
                    result = func(*args, **kwargs)

            except Exception as e:
                success = False
                # Track error if monitoring available
                if monitoring_manager:
                    monitoring_manager.track_error(
                        type(e).__name__,
                        str(e),
                        op_name,
                        stack_trace=traceback.format_exc(),
                        context=call_context
                    )
                raise
            finally:
                # Track usage if requested
                if track_usage and monitoring_manager:
                    duration_ms = (time.perf_counter() - start_time) * 1000
                    monitoring_manager.track_feature_usage(
                        feature=op_name.split('.')[0] if '.' in op_name else 'core',
                        action=op_name.split('.')[-1] if '.' in op_name else op_name,
                        success=success,
                        duration_ms=duration_ms,
                        context=call_context
                    )

            return result

        return wrapper  # type: ignore[return-value]  # ParamSpec decorator typing limitation
    return decorator


def track_feature_usage(feature: str, action: str | None = None, workflow: str | None = None):
    """Decorator for tracking feature usage.

    Args:
        feature: Feature name
        action: Action name (defaults to function name)
        workflow: Workflow identifier

    Usage:
        @track_feature_usage("sprite_gallery", "thumbnail_click")
        def on_thumbnail_clicked(self, index):
            # Handle click
    """
    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            action_name = action or func.__name__

            start_time = time.perf_counter()
            success = True

            try:
                result = func(*args, **kwargs)
            except Exception:
                success = False
                raise
            finally:
                # Track usage
                monitoring_manager = get_monitoring_manager()
                if monitoring_manager:
                    duration_ms = (time.perf_counter() - start_time) * 1000
                    monitoring_manager.track_feature_usage(
                        feature=feature,
                        action=action_name,
                        success=success,
                        duration_ms=duration_ms,
                        workflow=workflow
                    )

            return result

        return wrapper  # type: ignore[return-value]  # ParamSpec decorator typing limitation
    return decorator


def monitor_cache_performance(cache_name: str):
    """Decorator for monitoring cache hit/miss performance.

    Usage:
        @monitor_cache_performance("thumbnail_cache")
        def get_cached_thumbnail(self, key):
            # Cache lookup logic
    """
    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            start_time = time.perf_counter()

            result = func(*args, **kwargs)

            # Determine if it was a cache hit or miss
            is_hit = result is not None

            monitoring_manager = get_monitoring_manager()
            if monitoring_manager:
                duration_ms = (time.perf_counter() - start_time) * 1000

                # Track cache performance
                monitoring_manager.track_feature_usage(
                    feature="cache",
                    action=f"{cache_name}_{'hit' if is_hit else 'miss'}",
                    success=True,
                    duration_ms=duration_ms,
                    context={'cache_name': cache_name, 'hit': is_hit}
                )

                # Also record as performance metric
                with monitoring_manager.monitor_operation(f"cache_{cache_name}",
                                                        {'hit': is_hit, 'cache_name': cache_name}):
                    pass  # Already completed

            return result

        return wrapper  # type: ignore[return-value]  # ParamSpec decorator typing limitation
    return decorator


class WorkflowTracker:
    """Helper class for tracking multi-step user workflows.

    Usage:
        workflow = WorkflowTracker("sprite_extraction")
        workflow.step("load_rom")
        workflow.step("select_region")
        workflow.step("extract_sprites")
        workflow.complete()
    """

    def __init__(self, workflow_name: str):
        self.workflow_name = workflow_name
        self.start_time = time.perf_counter()
        self.steps = []
        self.monitoring_manager = get_monitoring_manager()

    def step(self, step_name: str, context: dict[str, Any] | None = None):
        """Record a workflow step."""
        step_time = time.perf_counter()

        if self.monitoring_manager:
            # Calculate step duration
            step_duration = 0
            if self.steps:
                step_duration = (step_time - self.steps[-1]['timestamp']) * 1000
            else:
                step_duration = (step_time - self.start_time) * 1000

            self.monitoring_manager.track_feature_usage(
                feature="workflow",
                action=f"{self.workflow_name}_{step_name}",
                success=True,
                duration_ms=step_duration,
                context=context,
                workflow=self.workflow_name
            )

        self.steps.append({
            'step': step_name,
            'timestamp': step_time,
            'context': context
        })

    def complete(self, success: bool = True):
        """Mark workflow as complete."""
        if self.monitoring_manager:
            total_duration = (time.perf_counter() - self.start_time) * 1000

            self.monitoring_manager.track_feature_usage(
                feature="workflow",
                action=f"{self.workflow_name}_complete",
                success=success,
                duration_ms=total_duration,
                context={'steps': len(self.steps)},
                workflow=self.workflow_name
            )

    def fail(self, error_message: str):
        """Mark workflow as failed."""
        if self.monitoring_manager:
            total_duration = (time.perf_counter() - self.start_time) * 1000

            self.monitoring_manager.track_error(
                error_type="WorkflowError",
                error_message=error_message,
                operation=f"workflow_{self.workflow_name}",
                context={'steps_completed': len(self.steps)}
            )

            self.monitoring_manager.track_feature_usage(
                feature="workflow",
                action=f"{self.workflow_name}_failed",
                success=False,
                duration_ms=total_duration,
                context={'steps': len(self.steps), 'error': error_message},
                workflow=self.workflow_name
            )


class MonitoringMixin:
    """Mixin class to add monitoring capabilities to other classes.

    Usage:
        class MyWidget(QWidget, MonitoringMixin):
            def __init__(self):
                super().__init__()
                self.init_monitoring("my_widget")

            def some_action(self):
                with self.monitor("some_action"):
                    # Do work
    """

    def init_monitoring(self, component_name: str):
        """Initialize monitoring for this component."""
        self._component_name = component_name
        self._monitoring_manager = get_monitoring_manager()

    def monitor(self, operation: str, context: dict[str, Any] | None = None):
        """Create a monitoring context for an operation."""
        full_operation = f"{self._component_name}.{operation}"
        return monitor_performance(full_operation, context)

    def track_usage(self, action: str, success: bool = True,
                   duration_ms: float | None = None,
                   context: dict[str, Any] | None = None):
        """Track feature usage for this component."""
        if self._monitoring_manager:
            self._monitoring_manager.track_feature_usage(
                feature=self._component_name,
                action=action,
                success=success,
                duration_ms=duration_ms,
                context=context
            )

    def track_error(self, error_type: str, error_message: str, operation: str,
                   context: dict[str, Any] | None = None):
        """Track an error for this component."""
        if self._monitoring_manager:
            self._monitoring_manager.track_error(
                error_type=error_type,
                error_message=error_message,
                operation=f"{self._component_name}.{operation}",
                context=context
            )


# Convenience functions for common monitoring patterns

def monitor_rom_operation(func: F) -> F:
    """Decorator specifically for ROM operations."""
    return monitor_operation("rom_operation", track_usage=True)(func)


def monitor_ui_interaction(feature: str):
    """Decorator for UI interactions."""
    return track_feature_usage(feature, workflow="ui_interaction")


def monitor_file_operation(func: F) -> F:
    """Decorator for file I/O operations."""
    return monitor_operation("file_operation", track_usage=True,
                           context={'operation_type': 'file_io'})(func)


# Health monitoring utilities

def check_memory_health(threshold_mb: float = 500.0) -> bool:
    """Check if memory usage is within healthy limits."""
    monitoring_manager = get_monitoring_manager()
    if not monitoring_manager:
        return True

    health_status = monitoring_manager.get_health_status()
    current_memory = health_status.get('current', {}).get('memory_mb', 0)

    return current_memory < threshold_mb


def get_performance_summary(operation: str, hours: int = 24) -> dict[str, Any]:
    """Get performance summary for an operation."""
    monitoring_manager = get_monitoring_manager()
    if not monitoring_manager:
        return {}

    return monitoring_manager.get_performance_stats(operation, hours)


# Integration utilities

def setup_monitoring_for_manager(manager: Any) -> None:
    """Set up automatic monitoring for a manager instance."""
    monitoring_manager = get_monitoring_manager()
    if monitoring_manager:
        monitoring_manager.register_manager_monitoring(manager)


def generate_monitoring_report(hours: int = 24, export_format: str = "json") -> str | None:
    """Generate and export a monitoring report."""
    monitoring_manager = get_monitoring_manager()
    if not monitoring_manager:
        return None

    try:
        output_path = monitoring_manager.export_data(export_format, hours)
        return str(output_path)
    except Exception as e:
        logger.error(f"Failed to generate monitoring report: {e}")
        return None
