"""
Continuous Monitoring and Observability Manager for SpritePal

Provides comprehensive monitoring capabilities including:
- Performance monitoring (operation timings, memory usage, bottlenecks)
- Error tracking and categorization
- Usage analytics (feature usage, workflows, success rates)
- Health monitoring (system resources, cache effectiveness)
- Actionable insights and reporting

Privacy-conscious design: No personal data collection, respects user settings.
"""
from __future__ import annotations

import json
import os
import statistics
import threading
import time
import uuid
from collections import defaultdict, deque
from contextlib import contextmanager, suppress
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any, override
from weakref import WeakSet

import psutil

from .base_manager import BaseManager

if TYPE_CHECKING:
    from PySide6.QtCore import QObject

    from core.protocols.manager_protocols import SettingsManagerProtocol


@dataclass
class PerformanceMetric:
    """Container for performance measurement data."""
    operation: str
    duration_ms: float
    memory_before_mb: float
    memory_after_mb: float
    timestamp: datetime
    thread_id: int
    context: dict[str, Any] = field(default_factory=dict)
    success: bool = True
    error_type: str | None = None


@dataclass
class ErrorEvent:
    """Container for error tracking data."""
    error_type: str
    error_message: str
    operation: str
    timestamp: datetime
    fingerprint: str  # For deduplication
    stack_trace: str | None = None
    context: dict[str, Any] = field(default_factory=dict)
    severity: str = "ERROR"  # DEBUG, INFO, WARNING, ERROR, CRITICAL
    count: int = 1


@dataclass
class UsageEvent:
    """Container for usage analytics data."""
    feature: str
    action: str
    timestamp: datetime
    duration_ms: float | None = None
    success: bool = True
    context: dict[str, Any] = field(default_factory=dict)
    user_workflow: str | None = None


@dataclass
class HealthMetric:
    """Container for system health data."""
    metric_name: str
    value: float
    timestamp: datetime
    unit: str = ""
    threshold_warning: float | None = None
    threshold_critical: float | None = None
    context: dict[str, Any] = field(default_factory=dict)


@dataclass
class MonitoringReport:
    """Container for monitoring report data."""
    report_id: str
    generated_at: datetime
    time_range: dict[str, datetime]
    performance_summary: dict[str, Any]
    error_summary: dict[str, Any]
    usage_summary: dict[str, Any]
    health_summary: dict[str, Any]
    insights: list[str]
    recommendations: list[str]


class PerformanceCollector:
    """Collects and analyzes performance metrics."""

    def __init__(self, max_entries: int = 10000):
        self.metrics: deque[PerformanceMetric] = deque(maxlen=max_entries)
        self._lock = threading.RLock()
        self._active_operations: dict[str, dict[str, Any]] = {}

    def start_operation(self, operation: str, context: dict[str, Any] | None = None) -> str:
        """Start tracking a performance operation."""
        operation_id = str(uuid.uuid4())

        with self._lock:
            self._active_operations[operation_id] = {
                'operation': operation,
                'start_time': time.perf_counter(),
                'start_memory': self._get_memory_usage(),
                'thread_id': threading.get_ident(),
                'context': context or {}
            }

        return operation_id

    def finish_operation(self, operation_id: str, success: bool = True,
                        error_type: str | None = None) -> None:
        """Finish tracking a performance operation."""
        end_time = time.perf_counter()
        end_memory = self._get_memory_usage()

        with self._lock:
            if operation_id not in self._active_operations:
                return

            start_data = self._active_operations.pop(operation_id)
            duration_ms = (end_time - start_data['start_time']) * 1000

            metric = PerformanceMetric(
                operation=start_data['operation'],
                duration_ms=duration_ms,
                memory_before_mb=start_data['start_memory'],
                memory_after_mb=end_memory,
                timestamp=datetime.now(UTC),
                thread_id=start_data['thread_id'],
                context=start_data['context'],
                success=success,
                error_type=error_type
            )

            self.metrics.append(metric)

    def get_operation_stats(self, operation: str, hours: int = 24) -> dict[str, Any]:
        """Get performance statistics for an operation."""
        cutoff = datetime.now(UTC) - timedelta(hours=hours)

        with self._lock:
            relevant_metrics = [
                m for m in self.metrics
                if m.operation == operation and m.timestamp >= cutoff
            ]

        if not relevant_metrics:
            return {}

        durations = [m.duration_ms for m in relevant_metrics]
        memory_usage = [m.memory_after_mb - m.memory_before_mb for m in relevant_metrics]
        success_rate = sum(1 for m in relevant_metrics if m.success) / len(relevant_metrics)

        return {
            'operation': operation,
            'sample_count': len(relevant_metrics),
            'duration_stats': {
                'mean_ms': statistics.mean(durations),
                'median_ms': statistics.median(durations),
                'p95_ms': statistics.quantiles(durations, n=20)[18] if len(durations) >= 20 else max(durations),
                'min_ms': min(durations),
                'max_ms': max(durations),
                'std_dev_ms': statistics.stdev(durations) if len(durations) > 1 else 0
            },
            'memory_stats': {
                'mean_delta_mb': statistics.mean(memory_usage),
                'max_delta_mb': max(memory_usage),
                'min_delta_mb': min(memory_usage)
            },
            'success_rate': success_rate,
            'error_types': list({m.error_type for m in relevant_metrics if m.error_type})
        }

    def _get_memory_usage(self) -> float:
        """Get current memory usage in MB."""
        try:
            process = psutil.Process(os.getpid())
            return process.memory_info().rss / 1024 / 1024
        except Exception:
            return 0.0


class ErrorTracker:
    """Tracks and categorizes application errors."""

    def __init__(self, max_entries: int = 5000):
        self.errors: deque[ErrorEvent] = deque(maxlen=max_entries)
        self._lock = threading.RLock()
        self._error_counts: dict[str, int] = defaultdict(int)

    def track_error(self, error_type: str, error_message: str, operation: str,
                   stack_trace: str | None = None, context: dict[str, Any] | None = None,
                   severity: str = "ERROR") -> None:
        """Track an error event."""
        # Create fingerprint for deduplication
        fingerprint = f"{error_type}::{operation}::{hash(error_message) % 1000000}"

        with self._lock:
            # Check if we already have this error
            existing_error = None
            for error in reversed(self.errors):
                if error.fingerprint == fingerprint:
                    existing_error = error
                    break

            if existing_error and (datetime.now(UTC) - existing_error.timestamp) < timedelta(hours=1):
                # Update existing error count
                existing_error.count += 1
                existing_error.timestamp = datetime.now(UTC)
            else:
                # Create new error event
                error_event = ErrorEvent(
                    error_type=error_type,
                    error_message=error_message,
                    operation=operation,
                    timestamp=datetime.now(UTC),
                    fingerprint=fingerprint,
                    stack_trace=stack_trace,
                    context=context or {},
                    severity=severity
                )
                self.errors.append(error_event)

            self._error_counts[fingerprint] += 1

    def get_error_summary(self, hours: int = 24) -> dict[str, Any]:
        """Get error statistics for a time period."""
        cutoff = datetime.now(UTC) - timedelta(hours=hours)

        with self._lock:
            recent_errors = [e for e in self.errors if e.timestamp >= cutoff]

        if not recent_errors:
            return {'total_errors': 0}

        # Group by error type and operation
        by_type = defaultdict(int)
        by_operation = defaultdict(int)
        by_severity = defaultdict(int)
        total_occurrences = 0

        for error in recent_errors:
            by_type[error.error_type] += error.count
            by_operation[error.operation] += error.count
            by_severity[error.severity] += error.count
            total_occurrences += error.count

        return {
            'total_errors': len(recent_errors),
            'total_occurrences': total_occurrences,
            'by_type': dict(by_type),
            'by_operation': dict(by_operation),
            'by_severity': dict(by_severity),
            'top_errors': [
                {
                    'fingerprint': error.fingerprint,
                    'type': error.error_type,
                    'operation': error.operation,
                    'count': error.count,
                    'last_seen': error.timestamp.isoformat()
                }
                for error in sorted(recent_errors, key=lambda x: x.count, reverse=True)[:10]
            ]
        }


class UsageAnalytics:
    """Tracks feature usage and user workflows."""

    def __init__(self, max_entries: int = 20000):
        self.events: deque[UsageEvent] = deque(maxlen=max_entries)
        self._lock = threading.RLock()
        self._active_workflows: dict[str, list[UsageEvent]] = {}

    def track_feature_usage(self, feature: str, action: str, success: bool = True,
                          duration_ms: float | None = None,
                          context: dict[str, Any] | None = None,
                          workflow: str | None = None) -> None:
        """Track a feature usage event."""
        event = UsageEvent(
            feature=feature,
            action=action,
            timestamp=datetime.now(UTC),
            duration_ms=duration_ms,
            success=success,
            context=context or {},
            user_workflow=workflow
        )

        with self._lock:
            self.events.append(event)

            # Track workflow if specified
            if workflow:
                if workflow not in self._active_workflows:
                    self._active_workflows[workflow] = []
                self._active_workflows[workflow].append(event)

                # Clean old workflow data
                if len(self._active_workflows[workflow]) > 100:
                    self._active_workflows[workflow] = self._active_workflows[workflow][-50:]

    def get_usage_stats(self, hours: int = 24) -> dict[str, Any]:
        """Get usage statistics for a time period."""
        cutoff = datetime.now(UTC) - timedelta(hours=hours)

        with self._lock:
            recent_events = [e for e in self.events if e.timestamp >= cutoff]

        if not recent_events:
            return {'total_events': 0}

        # Analyze usage patterns
        feature_usage = defaultdict(int)
        action_usage = defaultdict(int)
        success_rates = defaultdict(list)
        durations = defaultdict(list)

        for event in recent_events:
            feature_usage[event.feature] += 1
            action_usage[event.action] += 1
            success_rates[event.feature].append(event.success)
            if event.duration_ms is not None:
                durations[event.feature].append(event.duration_ms)

        # Calculate success rates
        feature_success_rates = {
            feature: sum(successes) / len(successes)
            for feature, successes in success_rates.items()
        }

        # Calculate average durations
        feature_durations = {
            feature: statistics.mean(times)
            for feature, times in durations.items() if times
        }

        return {
            'total_events': len(recent_events),
            'most_used_features': dict(sorted(feature_usage.items(), key=lambda x: x[1], reverse=True)[:10]),
            'most_used_actions': dict(sorted(action_usage.items(), key=lambda x: x[1], reverse=True)[:10]),
            'success_rates': feature_success_rates,
            'average_durations_ms': feature_durations,
            'active_workflows': len(self._active_workflows)
        }

    def get_workflow_analysis(self, workflow: str) -> dict[str, Any]:
        """Analyze a specific user workflow."""
        with self._lock:
            if workflow not in self._active_workflows:
                return {}

            events = self._active_workflows[workflow]

        if not events:
            return {}

        # Analyze workflow patterns
        step_sequence = [f"{e.feature}::{e.action}" for e in events[-20:]]  # Last 20 steps
        total_duration = sum(e.duration_ms for e in events if e.duration_ms) or 0
        success_rate = sum(1 for e in events if e.success) / len(events)

        return {
            'workflow': workflow,
            'total_events': len(events),
            'recent_sequence': step_sequence,
            'total_duration_ms': total_duration,
            'success_rate': success_rate,
            'common_failures': [
                e.action for e in events[-10:] if not e.success
            ]
        }


class HealthMonitor:
    """Monitors system health and resource usage."""

    def __init__(self, max_entries: int = 1000):
        self.metrics: deque[HealthMetric] = deque(maxlen=max_entries)
        self._lock = threading.RLock()

    def record_metric(self, metric_name: str, value: float, unit: str = "",
                     threshold_warning: float | None = None,
                     threshold_critical: float | None = None,
                     context: dict[str, Any] | None = None) -> None:
        """Record a health metric."""
        metric = HealthMetric(
            metric_name=metric_name,
            value=value,
            timestamp=datetime.now(UTC),
            unit=unit,
            threshold_warning=threshold_warning,
            threshold_critical=threshold_critical,
            context=context or {}
        )

        with self._lock:
            self.metrics.append(metric)

    def get_current_health(self) -> dict[str, Any]:
        """Get current system health status."""
        try:
            process = psutil.Process(os.getpid())

            # CPU usage
            cpu_percent = process.cpu_percent()

            # Memory usage
            memory_info = process.memory_info()
            memory_mb = memory_info.rss / 1024 / 1024
            memory_percent = process.memory_percent()

            # Thread count
            thread_count = process.num_threads()

            # File descriptors (Unix only)
            fd_count = 0
            with suppress(Exception):
                fd_count = process.num_fds() if hasattr(process, 'num_fds') else 0

            # Record these metrics
            self.record_metric("cpu_percent", cpu_percent, "%", 50.0, 80.0)
            self.record_metric("memory_mb", memory_mb, "MB", 500.0, 1000.0)
            self.record_metric("memory_percent", memory_percent, "%", 20.0, 40.0)
            self.record_metric("thread_count", thread_count, "threads", 50, 100)
            if fd_count > 0:
                self.record_metric("file_descriptors", fd_count, "fds", 100, 200)

            return {
                'cpu_percent': cpu_percent,
                'memory_mb': memory_mb,
                'memory_percent': memory_percent,
                'thread_count': thread_count,
                'file_descriptors': fd_count,
                'healthy': (cpu_percent < 50 and memory_percent < 20 and thread_count < 50)
            }

        except Exception as e:
            return {'error': str(e), 'healthy': False}

    def get_health_trends(self, hours: int = 24) -> dict[str, Any]:
        """Get health metric trends over time."""
        cutoff = datetime.now(UTC) - timedelta(hours=hours)

        with self._lock:
            recent_metrics = [m for m in self.metrics if m.timestamp >= cutoff]

        if not recent_metrics:
            return {}

        # Group metrics by name
        by_metric = defaultdict(list)
        for metric in recent_metrics:
            by_metric[metric.metric_name].append(metric)

        trends = {}
        for metric_name, metric_list in by_metric.items():
            values = [m.value for m in metric_list]
            if values:
                trends[metric_name] = {
                    'current': values[-1],
                    'average': statistics.mean(values),
                    'min': min(values),
                    'max': max(values),
                    'trend': 'increasing' if values[-1] > values[0] else 'decreasing' if values[-1] < values[0] else 'stable',
                    'unit': metric_list[0].unit,
                    'samples': len(values)
                }

        return trends


class MonitoringManager(BaseManager):
    """Main monitoring and observability manager for SpritePal."""

    def __init__(self, parent: QObject | None = None,
                 settings_manager: SettingsManagerProtocol | None = None):
        self._performance_collector = PerformanceCollector()
        self._error_tracker = ErrorTracker()
        self._usage_analytics = UsageAnalytics()
        self._health_monitor = HealthMonitor()
        self._health_timer = None
        self._monitored_managers = WeakSet()
        self._shutting_down = False  # Flag to prevent timer race during cleanup

        # Inject settings manager or use fallback
        if settings_manager is None:
            from core.di_container import inject
            from core.protocols.manager_protocols import SettingsManagerProtocol
            self.settings_manager = inject(SettingsManagerProtocol)
        else:
            self.settings_manager = settings_manager

        super().__init__("MonitoringManager", parent)

    @override
    def _initialize(self) -> None:
        """Initialize the monitoring manager."""
        self._logger.info("Initializing MonitoringManager...")

        # Check if monitoring is enabled
        try:
            settings = self.settings_manager
            self._enabled = settings.get("monitoring", "enabled", True)
            self._health_check_interval = settings.get("monitoring", "health_check_interval_ms", 60000)  # 1 minute
            self._export_format = settings.get("monitoring", "export_format", "json")
            self._retention_hours = settings.get("monitoring", "retention_hours", 168)  # 1 week
        except Exception as e:
            self._logger.warning(f"Could not load monitoring settings: {e}")
            self._enabled = True
            self._health_check_interval = 60000
            self._export_format = "json"
            self._retention_hours = 168

        if self._enabled:
            self._setup_health_monitoring()
            self._is_initialized = True
            self._logger.info("MonitoringManager initialized successfully")
        else:
            self._is_initialized = True
            self._logger.info("MonitoringManager initialized but disabled by settings")

    def _setup_health_monitoring(self) -> None:
        """Set up periodic health monitoring."""
        def run_health_check():
            """Run health check and reschedule."""
            # Check shutdown flag to avoid race with cleanup
            if self._shutting_down:
                return
            if self._health_timer is not None:  # Check if timer should continue
                self._collect_health_metrics()
                # Reschedule next check
                self._health_timer = threading.Timer(
                    self._health_check_interval / 1000.0,  # Convert ms to seconds
                    run_health_check
                )
                self._health_timer.daemon = True
                self._health_timer.start()

        # Start first timer
        self._health_timer = threading.Timer(
            self._health_check_interval / 1000.0,  # Convert ms to seconds
            run_health_check
        )
        self._health_timer.daemon = True
        self._health_timer.start()
        self._logger.debug(f"Health monitoring started with {self._health_check_interval}ms interval")

    def _collect_health_metrics(self) -> None:
        """Collect system health metrics."""
        if not self._enabled or self._shutting_down:
            return

        try:
            health_data = self._health_monitor.get_current_health()
            if not health_data.get('healthy', False):
                # Wrap logging in try-except to handle closed streams during shutdown
                try:
                    self._logger.warning(f"System health degraded: {health_data}")
                except ValueError:
                    # I/O operation on closed file - logging streams closed during test teardown
                    pass
        except Exception as e:
            try:
                self._logger.error(f"Failed to collect health metrics: {e}")
            except ValueError:
                pass  # Streams closed during shutdown

    @contextmanager
    def monitor_operation(self, operation: str, context: dict[str, Any] | None = None):
        """Context manager for monitoring an operation's performance."""
        if not self._enabled:
            yield
            return

        operation_id = self._performance_collector.start_operation(operation, context)
        success = True
        error_type = None

        try:
            yield
        except Exception as e:
            success = False
            error_type = type(e).__name__
            # Track the error
            self.track_error(error_type, str(e), operation, context=context)
            raise
        finally:
            self._performance_collector.finish_operation(operation_id, success, error_type)

    def track_error(self, error_type: str, error_message: str, operation: str,
                   stack_trace: str | None = None, context: dict[str, Any] | None = None,
                   severity: str = "ERROR") -> None:
        """Track an error event."""
        if not self._enabled:
            return

        self._error_tracker.track_error(error_type, error_message, operation,
                                      stack_trace, context, severity)

        # Emit error signal for immediate handling
        self.error_occurred.emit(f"[{operation}] {error_type}: {error_message}")

    def track_feature_usage(self, feature: str, action: str, success: bool = True,
                          duration_ms: float | None = None,
                          context: dict[str, Any] | None = None,
                          workflow: str | None = None) -> None:
        """Track feature usage."""
        if not self._enabled:
            return

        self._usage_analytics.track_feature_usage(feature, action, success,
                                                duration_ms, context, workflow)

    def get_performance_stats(self, operation: str, hours: int = 24) -> dict[str, Any]:
        """Get performance statistics for an operation."""
        return self._performance_collector.get_operation_stats(operation, hours)

    def get_error_summary(self, hours: int = 24) -> dict[str, Any]:
        """Get error summary for a time period."""
        return self._error_tracker.get_error_summary(hours)

    def get_usage_stats(self, hours: int = 24) -> dict[str, Any]:
        """Get usage statistics for a time period."""
        return self._usage_analytics.get_usage_stats(hours)

    def get_health_status(self) -> dict[str, Any]:
        """Get current system health status."""
        current_health = self._health_monitor.get_current_health()
        health_trends = self._health_monitor.get_health_trends()

        return {
            'current': current_health,
            'trends': health_trends,
            'monitoring_enabled': self._enabled
        }

    def generate_insights(self, hours: int = 24) -> list[str]:
        """Generate actionable insights from monitoring data."""
        insights = []

        # Performance insights
        perf_stats = {}
        common_operations = ['rom_loading', 'extraction', 'thumbnail_generation', 'injection']

        for op in common_operations:
            stats = self.get_performance_stats(op, hours)
            if stats:
                perf_stats[op] = stats

                # Check for performance issues
                if stats['duration_stats']['p95_ms'] > 5000:  # 5 seconds
                    insights.append(f"Performance concern: {op} P95 latency is {stats['duration_stats']['p95_ms']:.0f}ms")

                if stats['success_rate'] < 0.9:
                    insights.append(f"Reliability concern: {op} success rate is {stats['success_rate']:.1%}")

        # Error insights
        error_summary = self.get_error_summary(hours)
        if error_summary.get('total_occurrences', 0) > 10:
            insights.append(f"High error rate: {error_summary['total_occurrences']} errors in last {hours}h")

        # Top error types
        if error_summary.get('by_type'):
            top_error = max(error_summary['by_type'].items(), key=lambda x: x[1])
            if top_error[1] > 5:
                insights.append(f"Most common error: {top_error[0]} ({top_error[1]} occurrences)")

        # Health insights
        health_trends = self._health_monitor.get_health_trends(hours)
        for metric, trend in health_trends.items():
            if trend['trend'] == 'increasing' and metric in ['memory_mb', 'cpu_percent']:
                insights.append(f"Resource usage trending up: {metric} increased to {trend['current']:.1f}{trend['unit']}")

        # Usage insights
        usage_stats = self.get_usage_stats(hours)
        if usage_stats.get('most_used_features'):
            top_feature = next(iter(usage_stats['most_used_features'].items()))
            insights.append(f"Most used feature: {top_feature[0]} ({top_feature[1]} uses)")

        return insights

    def generate_report(self, hours: int = 24, include_raw_data: bool = False) -> MonitoringReport:
        """Generate a comprehensive monitoring report."""
        end_time = datetime.now(UTC)
        start_time = end_time - timedelta(hours=hours)

        report = MonitoringReport(
            report_id=str(uuid.uuid4()),
            generated_at=end_time,
            time_range={'start': start_time, 'end': end_time},
            performance_summary={},
            error_summary=self.get_error_summary(hours),
            usage_summary=self.get_usage_stats(hours),
            health_summary=self.get_health_status(),
            insights=self.generate_insights(hours),
            recommendations=self._generate_recommendations(hours)
        )

        # Add performance summary for common operations
        common_operations = ['rom_loading', 'extraction', 'thumbnail_generation', 'injection']
        for op in common_operations:
            stats = self.get_performance_stats(op, hours)
            if stats:
                report.performance_summary[op] = stats

        return report

    def _generate_recommendations(self, hours: int = 24) -> list[str]:
        """Generate actionable recommendations based on monitoring data."""
        recommendations = []

        # Performance recommendations
        perf_stats = {}
        for op in ['rom_loading', 'extraction', 'thumbnail_generation', 'injection']:
            stats = self.get_performance_stats(op, hours)
            if stats:
                perf_stats[op] = stats

        # Memory recommendations
        health_trends = self._health_monitor.get_health_trends(hours)
        if 'memory_mb' in health_trends:
            mem_trend = health_trends['memory_mb']
            if mem_trend['current'] > 500:  # 500MB threshold
                recommendations.append("Consider implementing more aggressive caching cleanup")
            if mem_trend['trend'] == 'increasing':
                recommendations.append("Monitor for potential memory leaks in recent operations")

        # Error recommendations
        error_summary = self.get_error_summary(hours)
        if error_summary.get('total_occurrences', 0) > 20:
            recommendations.append("High error rate detected - review error handling and user input validation")

        # Cache recommendations
        self.get_usage_stats(hours)
        if 'thumbnail_generation' in perf_stats and perf_stats['thumbnail_generation']['duration_stats']['mean_ms'] > 1000:
            recommendations.append("Thumbnail generation is slow - consider cache prewarming or optimization")

        return recommendations

    def export_data(self, format: str = "json", hours: int = 24,
                   output_path: Path | None = None) -> Path:
        """Export monitoring data to various formats."""
        report = self.generate_report(hours, include_raw_data=True)

        if output_path is None:
            timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
            filename = f"spritepal_monitoring_{timestamp}.{format}"
            output_path = Path.cwd() / "monitoring_reports" / filename
            output_path.parent.mkdir(parents=True, exist_ok=True)

        if format.lower() == "json":
            self._export_json(report, output_path)
        elif format.lower() == "csv":
            self._export_csv(report, output_path)
        else:
            raise ValueError(f"Unsupported export format: {format}")

        self._logger.info(f"Monitoring data exported to: {output_path}")
        return output_path

    def _export_json(self, report: MonitoringReport, output_path: Path) -> None:
        """Export report as JSON."""
        # Convert dataclass to dict with custom serialization
        def serialize_datetime(obj: Any) -> str:
            if isinstance(obj, datetime):
                return obj.isoformat()
            raise TypeError(f"Object of type {type(obj)} is not JSON serializable")

        with output_path.open('w') as f:
            json.dump(asdict(report), f, indent=2, default=serialize_datetime)

    def _export_csv(self, report: MonitoringReport, output_path: Path) -> None:
        """Export report as CSV."""
        import csv

        # Create a simplified CSV with key metrics
        with output_path.open('w', newline='') as f:
            writer = csv.writer(f)

            # Header
            writer.writerow(['Report ID', 'Generated At', 'Time Range', 'Total Errors',
                           'Total Usage Events', 'System Health', 'Top Insight'])

            # Data row
            health_status = 'Healthy' if report.health_summary.get('current', {}).get('healthy') else 'Degraded'
            top_insight = report.insights[0] if report.insights else 'None'

            writer.writerow([
                report.report_id,
                report.generated_at.isoformat(),
                f"{report.time_range['start'].isoformat()} to {report.time_range['end'].isoformat()}",
                report.error_summary.get('total_occurrences', 0),
                report.usage_summary.get('total_events', 0),
                health_status,
                top_insight
            ])

    def register_manager_monitoring(self, manager: BaseManager) -> None:
        """Register a manager for automatic monitoring."""
        if not self._enabled or not hasattr(manager, 'operation_started'):
            return

        self._monitored_managers.add(manager)

        # Connect to manager signals for automatic monitoring
        manager.operation_started.connect(
            lambda op: self.track_feature_usage("manager", f"start_{op}", workflow="manager_operation")
        )
        manager.operation_finished.connect(
            lambda op: self.track_feature_usage("manager", f"finish_{op}", workflow="manager_operation")
        )
        manager.error_occurred.connect(
            lambda msg: self.track_error("ManagerError", msg, "manager_operation")
        )

        self._logger.debug(f"Registered {manager.get_name()} for monitoring")

    @override
    def cleanup(self) -> None:
        """Cleanup resources."""
        # Set shutdown flag first to stop health check logging
        self._shutting_down = True
        
        if self._health_timer:
            self._health_timer.cancel()
            # Wait for timer thread to actually exit to prevent thread leak detection
            self._health_timer.join(timeout=1.0)
            self._health_timer = None

        # Clear collections
        self._performance_collector.metrics.clear()
        self._error_tracker.errors.clear()
        self._usage_analytics.events.clear()
        self._health_monitor.metrics.clear()
        self._monitored_managers.clear()

        self._logger.info("MonitoringManager cleaned up")
