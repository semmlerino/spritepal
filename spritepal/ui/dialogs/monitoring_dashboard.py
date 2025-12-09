"""
Real-time Monitoring Dashboard for SpritePal

Provides a comprehensive dashboard for viewing monitoring data including:
- Performance metrics and trends
- Error tracking and alerts
- Usage analytics
- System health monitoring
- Actionable insights and recommendations
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from PySide6.QtCore import QTimer
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)
from typing_extensions import override

from core.monitoring import get_monitoring_manager
from utils.logging_config import get_logger


class MetricWidget(QFrame):
    """Widget for displaying a single metric with trend indication."""

    def __init__(self, title: str, value: str = "0", unit: str = "",
                 trend: str = "stable", parent: QWidget | None = None):
        super().__init__(parent)
        self.setFrameStyle(QFrame.Shape.StyledPanel)
        self.setMinimumHeight(80)

        layout = QVBoxLayout(self)

        # Title
        title_label = QLabel(title)
        title_label.setFont(QFont("Arial", 10))
        title_label.setStyleSheet("color: #666; font-weight: bold;")

        # Value with trend indicator
        value_layout = QHBoxLayout()

        self.value_label = QLabel(f"{value} {unit}")
        self.value_label.setFont(QFont("Arial", 16, QFont.Weight.Bold))

        # Trend indicator
        self.trend_label = QLabel(self._get_trend_symbol(trend))
        self.trend_label.setFont(QFont("Arial", 12))
        self.trend_label.setStyleSheet(f"color: {self._get_trend_color(trend)};")

        value_layout.addWidget(self.value_label)
        value_layout.addWidget(self.trend_label)
        value_layout.addStretch()

        layout.addWidget(title_label)
        layout.addLayout(value_layout)

    def update_metric(self, value: str, unit: str = "", trend: str = "stable"):
        """Update the metric display."""
        self.value_label.setText(f"{value} {unit}")
        self.trend_label.setText(self._get_trend_symbol(trend))
        self.trend_label.setStyleSheet(f"color: {self._get_trend_color(trend)};")

    def _get_trend_symbol(self, trend: str) -> str:
        """Get symbol for trend indication."""
        symbols = {
            'increasing': '↗',
            'decreasing': '↘',
            'stable': '→',
            'up': '↑',
            'down': '↓'
        }
        return symbols.get(trend, '→')

    def _get_trend_color(self, trend: str) -> str:
        """Get color for trend indication."""
        colors = {
            'increasing': '#ff6b6b',  # Red for bad trends like memory/CPU up
            'decreasing': '#51cf66',  # Green for good trends like errors down
            'stable': '#868e96',      # Gray for stable
            'up': '#ff6b6b',
            'down': '#51cf66'
        }
        return colors.get(trend, '#868e96')


class PerformanceTab(QWidget):
    """Tab for performance monitoring."""

    def __init__(self, parent: Any | None = None):
        super().__init__(parent)
        self.logger = get_logger("monitoring_dashboard")
        self.setup_ui()

    def setup_ui(self):
        """Set up the performance tab UI."""
        layout = QVBoxLayout(self)

        # Metrics overview
        metrics_group = QGroupBox("Performance Overview")
        metrics_layout = QGridLayout(metrics_group)

        self.rom_loading_metric = MetricWidget("ROM Loading", "0", "ms")
        self.extraction_metric = MetricWidget("Extraction", "0", "ms")
        self.thumbnail_metric = MetricWidget("Thumbnails", "0", "ms")
        self.injection_metric = MetricWidget("Injection", "0", "ms")

        metrics_layout.addWidget(self.rom_loading_metric, 0, 0)
        metrics_layout.addWidget(self.extraction_metric, 0, 1)
        metrics_layout.addWidget(self.thumbnail_metric, 1, 0)
        metrics_layout.addWidget(self.injection_metric, 1, 1)

        # Detailed performance table
        details_group = QGroupBox("Performance Details")
        details_layout = QVBoxLayout(details_group)

        self.performance_table = QTableWidget(0, 6)
        self.performance_table.setHorizontalHeaderLabels([
            "Operation", "Mean (ms)", "P95 (ms)", "Success Rate",
            "Sample Count", "Memory Impact (MB)"
        ])
        self.performance_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)

        details_layout.addWidget(self.performance_table)

        layout.addWidget(metrics_group)
        layout.addWidget(details_group)

    def update_data(self, hours: int = 24):
        """Update performance data."""
        monitoring_manager = get_monitoring_manager()
        if not monitoring_manager:
            return

        # Update metrics
        operations = ['rom_loading', 'extraction', 'thumbnail_generation', 'injection']
        metric_widgets = [
            self.rom_loading_metric, self.extraction_metric,
            self.thumbnail_metric, self.injection_metric
        ]

        for op, widget in zip(operations, metric_widgets, strict=False):
            stats = monitoring_manager.get_performance_stats(op, hours)
            if stats:
                mean_ms = stats['duration_stats']['mean_ms']
                trend = self._determine_trend(op, mean_ms)
                widget.update_metric(f"{mean_ms:.0f}", "ms", trend)

        # Update detailed table
        self.performance_table.setRowCount(0)

        for i, operation in enumerate(operations):
            stats = monitoring_manager.get_performance_stats(operation, hours)
            if not stats:
                continue

            self.performance_table.insertRow(i)

            # Operation name
            self.performance_table.setItem(i, 0, QTableWidgetItem(operation.replace('_', ' ').title()))

            # Mean duration
            mean_ms = stats['duration_stats']['mean_ms']
            self.performance_table.setItem(i, 1, QTableWidgetItem(f"{mean_ms:.1f}"))

            # P95 duration
            p95_ms = stats['duration_stats']['p95_ms']
            self.performance_table.setItem(i, 2, QTableWidgetItem(f"{p95_ms:.1f}"))

            # Success rate
            success_rate = stats['success_rate']
            self.performance_table.setItem(i, 3, QTableWidgetItem(f"{success_rate:.1%}"))

            # Sample count
            sample_count = stats['sample_count']
            self.performance_table.setItem(i, 4, QTableWidgetItem(str(sample_count)))

            # Memory impact
            memory_delta = stats['memory_stats']['mean_delta_mb']
            self.performance_table.setItem(i, 5, QTableWidgetItem(f"{memory_delta:.2f}"))

    def _determine_trend(self, operation: str, current_value: float) -> str:
        """Determine trend for a metric (simplified)."""
        # In a real implementation, this would compare with historical data
        # For now, we'll use simple thresholds
        thresholds = {
            'rom_loading': 1000,  # 1 second
            'extraction': 2000,   # 2 seconds
            'thumbnail_generation': 500,  # 0.5 seconds
            'injection': 1500     # 1.5 seconds
        }

        threshold = thresholds.get(operation, 1000)
        if current_value > threshold * 1.5:
            return 'up'  # Bad performance
        if current_value < threshold * 0.5:
            return 'down'  # Good performance
        return 'stable'


class ErrorsTab(QWidget):
    """Tab for error monitoring."""

    def __init__(self, parent: Any | None = None):
        super().__init__(parent)
        self.setup_ui()

    def setup_ui(self):
        """Set up the errors tab UI."""
        layout = QVBoxLayout(self)

        # Error summary metrics
        summary_group = QGroupBox("Error Summary")
        summary_layout = QGridLayout(summary_group)

        self.total_errors_metric = MetricWidget("Total Errors", "0", "")
        self.error_rate_metric = MetricWidget("Error Rate", "0", "/hr")
        self.top_error_metric = MetricWidget("Top Error", "None", "")
        self.critical_errors_metric = MetricWidget("Critical", "0", "")

        summary_layout.addWidget(self.total_errors_metric, 0, 0)
        summary_layout.addWidget(self.error_rate_metric, 0, 1)
        summary_layout.addWidget(self.top_error_metric, 1, 0)
        summary_layout.addWidget(self.critical_errors_metric, 1, 1)

        # Error details table
        details_group = QGroupBox("Error Details")
        details_layout = QVBoxLayout(details_group)

        self.error_table = QTableWidget(0, 5)
        self.error_table.setHorizontalHeaderLabels([
            "Error Type", "Operation", "Count", "Last Seen", "Severity"
        ])
        self.error_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)

        details_layout.addWidget(self.error_table)

        layout.addWidget(summary_group)
        layout.addWidget(details_group)

    def update_data(self, hours: int = 24):
        """Update error data."""
        monitoring_manager = get_monitoring_manager()
        if not monitoring_manager:
            return

        error_summary = monitoring_manager.get_error_summary(hours)

        # Update summary metrics
        total_errors = error_summary.get('total_occurrences', 0)
        error_rate = total_errors / hours if hours > 0 else 0

        self.total_errors_metric.update_metric(str(total_errors), "",
                                             'up' if total_errors > 10 else 'stable')
        self.error_rate_metric.update_metric(f"{error_rate:.1f}", "/hr",
                                           'up' if error_rate > 1 else 'stable')

        # Top error
        top_errors = error_summary.get('top_errors', [])
        if top_errors:
            top_error = top_errors[0]
            self.top_error_metric.update_metric(top_error['type'][:15], "",
                                              'up' if top_error['count'] > 5 else 'stable')

        # Critical errors
        critical_count = error_summary.get('by_severity', {}).get('CRITICAL', 0)
        self.critical_errors_metric.update_metric(str(critical_count), "",
                                                'up' if critical_count > 0 else 'stable')

        # Update error table
        self.error_table.setRowCount(0)

        for i, error in enumerate(top_errors[:20]):  # Show top 20 errors
            self.error_table.insertRow(i)

            self.error_table.setItem(i, 0, QTableWidgetItem(error['type']))
            self.error_table.setItem(i, 1, QTableWidgetItem(error['operation']))
            self.error_table.setItem(i, 2, QTableWidgetItem(str(error['count'])))
            self.error_table.setItem(i, 3, QTableWidgetItem(error['last_seen'][:16]))

            # Color-code severity
            severity_item = QTableWidgetItem("ERROR")  # Default
            if critical_count > 0:
                severity_item.setText("CRITICAL")
                severity_item.setBackground(QColor("#ffebee"))  # Light red
            self.error_table.setItem(i, 4, severity_item)


class UsageTab(QWidget):
    """Tab for usage analytics."""

    def __init__(self, parent: Any | None = None):
        super().__init__(parent)
        self.setup_ui()

    def setup_ui(self):
        """Set up the usage tab UI."""
        layout = QVBoxLayout(self)

        # Usage summary
        summary_group = QGroupBox("Usage Summary")
        summary_layout = QGridLayout(summary_group)

        self.total_events_metric = MetricWidget("Total Events", "0", "")
        self.top_feature_metric = MetricWidget("Top Feature", "None", "")
        self.workflows_metric = MetricWidget("Active Workflows", "0", "")
        self.success_rate_metric = MetricWidget("Overall Success", "0", "%")

        summary_layout.addWidget(self.total_events_metric, 0, 0)
        summary_layout.addWidget(self.top_feature_metric, 0, 1)
        summary_layout.addWidget(self.workflows_metric, 1, 0)
        summary_layout.addWidget(self.success_rate_metric, 1, 1)

        # Feature usage table
        features_group = QGroupBox("Feature Usage")
        features_layout = QVBoxLayout(features_group)

        self.usage_table = QTableWidget(0, 4)
        self.usage_table.setHorizontalHeaderLabels([
            "Feature", "Usage Count", "Success Rate", "Avg Duration (ms)"
        ])
        self.usage_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)

        features_layout.addWidget(self.usage_table)

        layout.addWidget(summary_group)
        layout.addWidget(features_group)

    def update_data(self, hours: int = 24):
        """Update usage data."""
        monitoring_manager = get_monitoring_manager()
        if not monitoring_manager:
            return

        usage_stats = monitoring_manager.get_usage_stats(hours)

        # Update summary
        total_events = usage_stats.get('total_events', 0)
        self.total_events_metric.update_metric(str(total_events), "")

        # Top feature
        most_used = usage_stats.get('most_used_features', {})
        if most_used:
            top_feature = next(iter(most_used.keys()))
            self.top_feature_metric.update_metric(top_feature[:15], "")

        # Workflows
        workflows = usage_stats.get('active_workflows', 0)
        self.workflows_metric.update_metric(str(workflows), "")

        # Overall success rate
        success_rates = usage_stats.get('success_rates', {})
        if success_rates:
            overall_success = sum(success_rates.values()) / len(success_rates)
            self.success_rate_metric.update_metric(f"{overall_success:.0f}", "%",
                                                 'down' if overall_success < 0.9 else 'stable')

        # Update usage table
        self.usage_table.setRowCount(0)

        durations = usage_stats.get('average_durations_ms', {})

        for i, (feature, count) in enumerate(most_used.items()):
            if i >= 20:  # Show top 20
                break

            self.usage_table.insertRow(i)

            self.usage_table.setItem(i, 0, QTableWidgetItem(feature))
            self.usage_table.setItem(i, 1, QTableWidgetItem(str(count)))

            success_rate = success_rates.get(feature, 1.0)
            self.usage_table.setItem(i, 2, QTableWidgetItem(f"{success_rate:.1%}"))

            avg_duration = durations.get(feature, 0)
            self.usage_table.setItem(i, 3, QTableWidgetItem(f"{avg_duration:.1f}"))


class HealthTab(QWidget):
    """Tab for system health monitoring."""

    def __init__(self, parent: Any | None = None):
        super().__init__(parent)
        self.setup_ui()

    def setup_ui(self):
        """Set up the health tab UI."""
        layout = QVBoxLayout(self)

        # System health metrics
        health_group = QGroupBox("System Health")
        health_layout = QGridLayout(health_group)

        self.cpu_metric = MetricWidget("CPU Usage", "0", "%")
        self.memory_metric = MetricWidget("Memory Usage", "0", "MB")
        self.threads_metric = MetricWidget("Thread Count", "0", "")
        self.health_status_metric = MetricWidget("Health Status", "Unknown", "")

        health_layout.addWidget(self.cpu_metric, 0, 0)
        health_layout.addWidget(self.memory_metric, 0, 1)
        health_layout.addWidget(self.threads_metric, 1, 0)
        health_layout.addWidget(self.health_status_metric, 1, 1)

        # Health trends
        trends_group = QGroupBox("Health Trends")
        trends_layout = QVBoxLayout(trends_group)

        self.trends_text = QTextEdit()
        self.trends_text.setMaximumHeight(150)
        self.trends_text.setReadOnly(True)

        trends_layout.addWidget(self.trends_text)

        layout.addWidget(health_group)
        layout.addWidget(trends_group)

    def update_data(self, hours: int = 24):
        """Update health data."""
        monitoring_manager = get_monitoring_manager()
        if not monitoring_manager:
            return

        health_status = monitoring_manager.get_health_status()

        # Current health
        current = health_status.get('current', {})

        cpu_percent = current.get('cpu_percent', 0)
        self.cpu_metric.update_metric(f"{cpu_percent:.1f}", "%",
                                    'up' if cpu_percent > 50 else 'stable')

        memory_mb = current.get('memory_mb', 0)
        self.memory_metric.update_metric(f"{memory_mb:.0f}", "MB",
                                       'up' if memory_mb > 500 else 'stable')

        threads = current.get('thread_count', 0)
        self.threads_metric.update_metric(str(threads), "",
                                        'up' if threads > 50 else 'stable')

        is_healthy = current.get('healthy', False)
        health_text = "Healthy" if is_healthy else "Degraded"
        health_color = 'stable' if is_healthy else 'up'
        self.health_status_metric.update_metric(health_text, "", health_color)

        # Health trends
        trends = health_status.get('trends', {})
        trends_text = "Health Trends (24h):\n\n"

        for metric, trend_data in trends.items():
            if isinstance(trend_data, dict):
                current_val = trend_data.get('current', 0)
                trend_direction = trend_data.get('trend', 'stable')
                unit = trend_data.get('unit', '')

                trends_text += f"{metric.replace('_', ' ').title()}: "
                trends_text += f"{current_val:.1f}{unit} ({trend_direction})\n"

        self.trends_text.setPlainText(trends_text)


class InsightsTab(QWidget):
    """Tab for monitoring insights and recommendations."""

    def __init__(self, parent: Any | None = None):
        super().__init__(parent)
        self.setup_ui()

    def setup_ui(self):
        """Set up the insights tab UI."""
        layout = QVBoxLayout(self)

        # Insights
        insights_group = QGroupBox("Key Insights")
        insights_layout = QVBoxLayout(insights_group)

        self.insights_text = QTextEdit()
        self.insights_text.setMaximumHeight(200)
        self.insights_text.setReadOnly(True)

        insights_layout.addWidget(self.insights_text)

        # Recommendations
        recommendations_group = QGroupBox("Recommendations")
        recommendations_layout = QVBoxLayout(recommendations_group)

        self.recommendations_text = QTextEdit()
        self.recommendations_text.setReadOnly(True)

        recommendations_layout.addWidget(self.recommendations_text)

        layout.addWidget(insights_group)
        layout.addWidget(recommendations_group)

    def update_data(self, hours: int = 24):
        """Update insights data."""
        monitoring_manager = get_monitoring_manager()
        if not monitoring_manager:
            return

        # Get insights
        insights = monitoring_manager.generate_insights(hours)
        insights_text = "Key Findings:\n\n"

        if insights:
            for i, insight in enumerate(insights, 1):
                insights_text += f"{i}. {insight}\n\n"
        else:
            insights_text += "No significant issues detected."

        self.insights_text.setPlainText(insights_text)

        # Get recommendations
        report = monitoring_manager.generate_report(hours)
        recommendations = report.recommendations

        recommendations_text = "Recommended Actions:\n\n"

        if recommendations:
            for i, rec in enumerate(recommendations, 1):
                recommendations_text += f"{i}. {rec}\n\n"
        else:
            recommendations_text += "System is operating within normal parameters."

        self.recommendations_text.setPlainText(recommendations_text)


class MonitoringDashboard(QDialog):
    """Real-time monitoring dashboard for SpritePal."""

    def __init__(self, parent: Any | None = None):
        super().__init__(parent)
        self.logger = get_logger("monitoring_dashboard")
        self.monitoring_manager = get_monitoring_manager()

        if not self.monitoring_manager:
            self.logger.warning("Monitoring manager not available")

        self.setWindowTitle("SpritePal - Monitoring Dashboard")
        self.setMinimumSize(1000, 700)

        self.setup_ui()
        self.setup_timer()

        # Initial data load
        self.update_all_data()

    def setup_ui(self):
        """Set up the dashboard UI."""
        layout = QVBoxLayout(self)

        # Header with controls
        header_layout = QHBoxLayout()

        header_layout.addWidget(QLabel("Time Range:"))

        self.time_range_combo = QComboBox()
        self.time_range_combo.addItems(["1 hour", "6 hours", "24 hours", "7 days"])
        self.time_range_combo.setCurrentText("24 hours")
        self.time_range_combo.currentTextChanged.connect(self.on_time_range_changed)

        header_layout.addWidget(self.time_range_combo)

        header_layout.addWidget(QLabel("Refresh Interval:"))

        self.refresh_interval_spin = QSpinBox()
        self.refresh_interval_spin.setRange(5, 300)  # 5 seconds to 5 minutes
        self.refresh_interval_spin.setValue(30)
        self.refresh_interval_spin.setSuffix(" sec")
        self.refresh_interval_spin.valueChanged.connect(self.on_refresh_interval_changed)

        header_layout.addWidget(self.refresh_interval_spin)

        # Manual refresh button
        self.refresh_button = QPushButton("Refresh Now")
        self.refresh_button.clicked.connect(self.update_all_data)
        header_layout.addWidget(self.refresh_button)

        # Export button
        self.export_button = QPushButton("Export Report")
        self.export_button.clicked.connect(self.export_report)
        header_layout.addWidget(self.export_button)

        header_layout.addStretch()

        # Status label
        self.status_label = QLabel("Ready")
        header_layout.addWidget(self.status_label)

        # Tab widget for different monitoring aspects
        self.tab_widget = QTabWidget()

        self.performance_tab = PerformanceTab()
        self.errors_tab = ErrorsTab()
        self.usage_tab = UsageTab()
        self.health_tab = HealthTab()
        self.insights_tab = InsightsTab()

        self.tab_widget.addTab(self.performance_tab, "Performance")
        self.tab_widget.addTab(self.errors_tab, "Errors")
        self.tab_widget.addTab(self.usage_tab, "Usage")
        self.tab_widget.addTab(self.health_tab, "Health")
        self.tab_widget.addTab(self.insights_tab, "Insights")

        layout.addLayout(header_layout)
        layout.addWidget(self.tab_widget)

    def setup_timer(self):
        """Set up the refresh timer."""
        self.refresh_timer = QTimer()
        self.refresh_timer.timeout.connect(self.update_all_data)
        self.refresh_timer.start(30000)  # 30 seconds default

    def on_time_range_changed(self, text: str):
        """Handle time range selection change."""
        self.update_all_data()

    def on_refresh_interval_changed(self, value: int):
        """Handle refresh interval change."""
        self.refresh_timer.setInterval(value * 1000)  # Convert to milliseconds

    def get_time_range_hours(self) -> int:
        """Get the selected time range in hours."""
        text = self.time_range_combo.currentText()
        if "1 hour" in text:
            return 1
        if "6 hours" in text:
            return 6
        if "24 hours" in text:
            return 24
        if "7 days" in text:
            return 168
        return 24

    def update_all_data(self):
        """Update all dashboard data."""
        if not self.monitoring_manager:
            self.status_label.setText("Monitoring not available")
            return

        try:
            self.status_label.setText("Refreshing...")
            hours = self.get_time_range_hours()

            # Update all tabs
            self.performance_tab.update_data(hours)
            self.errors_tab.update_data(hours)
            self.usage_tab.update_data(hours)
            self.health_tab.update_data(hours)
            self.insights_tab.update_data(hours)

            # Update status
            now = datetime.now(UTC)
            self.status_label.setText(f"Last updated: {now.strftime('%H:%M:%S')}")

        except Exception as e:
            self.logger.error(f"Failed to update dashboard data: {e}")
            self.status_label.setText(f"Update failed: {e!s}")

    def export_report(self):
        """Export monitoring report."""
        if not self.monitoring_manager:
            return

        try:
            hours = self.get_time_range_hours()
            output_path = self.monitoring_manager.export_data("json", hours)

            self.status_label.setText(f"Report exported to: {output_path.name}")
            self.logger.info(f"Monitoring report exported to: {output_path}")

        except Exception as e:
            self.logger.error(f"Failed to export report: {e}")
            self.status_label.setText(f"Export failed: {e!s}")

    @override
    def closeEvent(self, event: Any):
        """Handle dialog close."""
        self.refresh_timer.stop()
        super().closeEvent(event)
