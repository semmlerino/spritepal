"""
Comprehensive tests for the SpritePal monitoring system.

Tests all components of the continuous monitoring system including:
- Performance monitoring and metrics collection
- Error tracking and categorization  
- Usage analytics and workflow tracking
- Health monitoring (system resources, cache effectiveness)
- Settings integration and configuration
- Dashboard functionality
- Export and reporting capabilities
"""

import json
import os

# Test imports
import sys
import tempfile
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.managers.monitoring_manager import (
    ErrorEvent,
    ErrorTracker,
    HealthMetric,
    HealthMonitor,
    MonitoringManager,
    PerformanceCollector,
    PerformanceMetric,
    UsageAnalytics,
    UsageEvent,
)
from core.managers.monitoring_settings import MonitoringSettings
from core.monitoring import (
    MonitoringMixin,
    WorkflowTracker,
    get_monitoring_manager,
    monitor_operation,
    monitor_performance,
    track_feature_usage,
)
from ui.dialogs.monitoring_dashboard import MonitoringDashboard


class TestPerformanceCollector:
    """Test the performance metrics collector."""
    
    def test_performance_collector_initialization(self):
        """Test collector initialization."""
        collector = PerformanceCollector(max_entries=100)
        assert len(collector.metrics) == 0
        assert len(collector._active_operations) == 0
    
    def test_start_finish_operation(self):
        """Test starting and finishing operations."""
        collector = PerformanceCollector()
        
        # Start operation
        op_id = collector.start_operation("test_operation", {"test": "context"})
        assert op_id in collector._active_operations
        
        # Finish operation
        collector.finish_operation(op_id, success=True)
        assert op_id not in collector._active_operations
        assert len(collector.metrics) == 1
        
        metric = collector.metrics[0]
        assert metric.operation == "test_operation"
        assert metric.success == True
        assert metric.context == {"test": "context"}
    
    def test_operation_stats(self):
        """Test getting operation statistics."""
        collector = PerformanceCollector()
        
        # Add some test metrics
        for i in range(5):
            op_id = collector.start_operation("test_op")
            time.sleep(0.001)  # Small delay
            collector.finish_operation(op_id, success=True)
        
        stats = collector.get_operation_stats("test_op")
        assert stats["operation"] == "test_op"
        assert stats["sample_count"] == 5
        assert "duration_stats" in stats
        assert stats["success_rate"] == 1.0
    
    def test_memory_tracking(self):
        """Test memory usage tracking."""
        collector = PerformanceCollector()
        
        op_id = collector.start_operation("memory_test")
        collector.finish_operation(op_id, success=True)
        
        metric = collector.metrics[0]
        assert metric.memory_before_mb >= 0
        assert metric.memory_after_mb >= 0


class TestErrorTracker:
    """Test the error tracking system."""
    
    def test_error_tracker_initialization(self):
        """Test tracker initialization."""
        tracker = ErrorTracker(max_entries=100)
        assert len(tracker.errors) == 0
        assert len(tracker._error_counts) == 0
    
    def test_track_error(self):
        """Test error tracking."""
        tracker = ErrorTracker()
        
        tracker.track_error(
            error_type="ValueError",
            error_message="Test error",
            operation="test_operation",
            context={"test": "context"}
        )
        
        assert len(tracker.errors) == 1
        error = tracker.errors[0]
        assert error.error_type == "ValueError"
        assert error.error_message == "Test error"
        assert error.operation == "test_operation"
        assert error.count == 1
    
    def test_error_deduplication(self):
        """Test error deduplication."""
        tracker = ErrorTracker()
        
        # Track same error multiple times
        for _ in range(3):
            tracker.track_error("ValueError", "Same error", "test_op")
        
        # Should have only one error entry but count should be 3
        assert len(tracker.errors) == 1
        assert tracker.errors[0].count == 3
    
    def test_error_summary(self):
        """Test error summary generation."""
        tracker = ErrorTracker()
        
        # Add different types of errors
        tracker.track_error("ValueError", "Value error", "op1")
        tracker.track_error("TypeError", "Type error", "op2")
        tracker.track_error("ValueError", "Another value error", "op1")
        
        summary = tracker.get_error_summary()
        assert summary["total_errors"] > 0
        assert summary["total_occurrences"] >= summary["total_errors"]
        assert "by_type" in summary
        assert "by_operation" in summary
        assert "top_errors" in summary


class TestUsageAnalytics:
    """Test the usage analytics system."""
    
    def test_usage_analytics_initialization(self):
        """Test analytics initialization."""
        analytics = UsageAnalytics(max_entries=100)
        assert len(analytics.events) == 0
        assert len(analytics._active_workflows) == 0
    
    def test_track_feature_usage(self):
        """Test feature usage tracking."""
        analytics = UsageAnalytics()
        
        analytics.track_feature_usage(
            feature="sprite_gallery",
            action="thumbnail_click",
            success=True,
            duration_ms=150.0,
            context={"sprite_index": 5}
        )
        
        assert len(analytics.events) == 1
        event = analytics.events[0]
        assert event.feature == "sprite_gallery"
        assert event.action == "thumbnail_click"
        assert event.success == True
        assert event.duration_ms == 150.0
    
    def test_usage_stats(self):
        """Test usage statistics generation."""
        analytics = UsageAnalytics()
        
        # Add some usage events
        analytics.track_feature_usage("feature1", "action1", True, 100)
        analytics.track_feature_usage("feature2", "action2", True, 200)
        analytics.track_feature_usage("feature1", "action1", False, 150)
        
        stats = analytics.get_usage_stats()
        assert stats["total_events"] == 3
        assert "most_used_features" in stats
        assert "success_rates" in stats
        assert "average_durations_ms" in stats
    
    def test_workflow_tracking(self):
        """Test workflow tracking."""
        analytics = UsageAnalytics()
        
        workflow_name = "sprite_extraction"
        analytics.track_feature_usage("rom", "load", True, workflow=workflow_name)
        analytics.track_feature_usage("extraction", "extract", True, workflow=workflow_name)
        
        assert workflow_name in analytics._active_workflows
        assert len(analytics._active_workflows[workflow_name]) == 2
        
        workflow_analysis = analytics.get_workflow_analysis(workflow_name)
        assert workflow_analysis["workflow"] == workflow_name
        assert workflow_analysis["total_events"] == 2


class TestHealthMonitor:
    """Test the health monitoring system."""
    
    def test_health_monitor_initialization(self):
        """Test monitor initialization."""
        monitor = HealthMonitor(max_entries=100)
        assert len(monitor.metrics) == 0
    
    def test_record_metric(self):
        """Test recording health metrics."""
        monitor = HealthMonitor()
        
        monitor.record_metric(
            metric_name="cpu_percent",
            value=25.5,
            unit="%",
            threshold_warning=50.0,
            threshold_critical=80.0
        )
        
        assert len(monitor.metrics) == 1
        metric = monitor.metrics[0]
        assert metric.metric_name == "cpu_percent"
        assert metric.value == 25.5
        assert metric.unit == "%"
    
    @patch('core.managers.monitoring_manager.psutil.Process')
    def test_current_health(self, mock_process):
        """Test current health status."""
        # Mock psutil process
        mock_proc = Mock()
        mock_proc.cpu_percent.return_value = 15.0
        mock_proc.memory_info.return_value = Mock(rss=100 * 1024 * 1024)  # 100MB
        mock_proc.memory_percent.return_value = 5.0
        mock_proc.num_threads.return_value = 10
        mock_proc.num_fds.return_value = 100  # Fix comparison failure
        mock_process.return_value = mock_proc
        
        monitor = HealthMonitor()
        health = monitor.get_current_health()
        
        if "error" in health:
            pytest.fail(f"HealthMonitor returned error: {health['error']}")

        assert health["cpu_percent"] == 15.0
        assert health["memory_mb"] == 100.0
        assert health["thread_count"] == 10
        assert health["healthy"] == True
    
    def test_health_trends(self):
        """Test health trend analysis."""
        monitor = HealthMonitor()
        
        # Add some metrics over time
        for i in range(5):
            monitor.record_metric("memory_mb", 100 + i * 10, "MB")
            
        trends = monitor.get_health_trends()
        assert "memory_mb" in trends
        assert trends["memory_mb"]["trend"] == "increasing"


class TestMonitoringManager:
    """Test the main monitoring manager."""
    
    @pytest.fixture
    def mock_settings_manager(self):
        """Create a mock settings manager."""
        mock = Mock()
        # Default settings
        mock.get.side_effect = lambda cat, key, default: default
        return mock

    @pytest.fixture
    def monitoring_manager(self, qtbot, mock_settings_manager):
        """Create a monitoring manager for testing."""
        # Inject settings manager explicitly to avoid dependency injection issues
        manager = MonitoringManager(settings_manager=mock_settings_manager)
        # qtbot.addWidget(manager)  # MonitoringManager is not a QWidget
        yield manager
        manager.cleanup()
    
    def test_manager_initialization(self, monitoring_manager):
        """Test manager initialization."""
        assert monitoring_manager.is_initialized()
        assert monitoring_manager._enabled  # Should be enabled by default
    
    def test_monitor_operation_context(self, monitoring_manager):
        """Test operation monitoring context manager."""
        with monitoring_manager.monitor_operation("test_operation", {"test": "context"}):
            time.sleep(0.001)  # Small operation
        
        # Should have recorded performance data
        stats = monitoring_manager.get_performance_stats("test_operation")
        assert stats  # Should have data
    
    def test_track_error(self, monitoring_manager):
        """Test error tracking."""
        monitoring_manager.track_error(
            error_type="TestError",
            error_message="Test error message",
            operation="test_operation",
            context={"test": "context"}
        )
        
        error_summary = monitoring_manager.get_error_summary()
        assert error_summary["total_errors"] > 0
    
    def test_track_feature_usage(self, monitoring_manager):
        """Test feature usage tracking."""
        monitoring_manager.track_feature_usage(
            feature="test_feature",
            action="test_action",
            success=True,
            duration_ms=100.0
        )
        
        usage_stats = monitoring_manager.get_usage_stats()
        assert usage_stats["total_events"] > 0
    
    def test_generate_insights(self, monitoring_manager):
        """Test insight generation."""
        # Add some test data
        monitoring_manager.track_error("TestError", "Test error", "test_op")
        monitoring_manager.track_feature_usage("test_feature", "test_action", True)
        
        insights = monitoring_manager.generate_insights()
        assert isinstance(insights, list)
    
    def test_generate_report(self, monitoring_manager):
        """Test report generation."""
        # Add some test data
        with monitoring_manager.monitor_operation("test_op"):
            time.sleep(0.001)
        
        report = monitoring_manager.generate_report(hours=1)
        assert report.report_id
        assert report.generated_at
        assert "performance_summary" in report.__dict__
        assert "error_summary" in report.__dict__
    
    def test_export_data(self, monitoring_manager):
        """Test data export."""
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "test_export.json"
            
            exported_path = monitoring_manager.export_data("json", 1, output_path)
            assert exported_path.exists()
            
            # Verify JSON is valid
            with open(exported_path) as f:
                data = json.load(f)
                assert "report_id" in data
                assert "generated_at" in data


class TestMonitoringDecorators:
    """Test monitoring decorators and utilities."""
    
    @patch('core.monitoring.get_monitoring_manager')
    def test_monitor_operation_decorator(self, mock_get_manager):
        """Test the @monitor_operation decorator."""
        mock_manager = Mock()
        # Make monitor_operation a context manager
        mock_context = MagicMock()
        mock_context.__enter__.return_value = None
        mock_context.__exit__.return_value = None
        mock_manager.monitor_operation.return_value = mock_context
        
        mock_get_manager.return_value = mock_manager
        
        @monitor_operation("test_operation")
        def test_function():
            return "test_result"
        
        result = test_function()
        assert result == "test_result"
        
        # Should have called monitoring manager
        mock_manager.monitor_operation.assert_called()
    
    @patch('core.monitoring.get_monitoring_manager')
    def test_track_feature_usage_decorator(self, mock_get_manager):
        """Test the @track_feature_usage decorator."""
        mock_manager = Mock()
        mock_get_manager.return_value = mock_manager
        
        @track_feature_usage("test_feature", "test_action")
        def test_function():
            return "test_result"
        
        result = test_function()
        assert result == "test_result"
        
        # Should have called feature tracking
        mock_manager.track_feature_usage.assert_called()
    
    def test_workflow_tracker(self):
        """Test the WorkflowTracker class."""
        with patch('core.monitoring.get_monitoring_manager') as mock_get_manager:
            mock_manager = Mock()
            mock_get_manager.return_value = mock_manager
            
            workflow = WorkflowTracker("test_workflow")
            workflow.step("step1")
            workflow.step("step2")
            workflow.complete(success=True)
            
            # Should have tracked multiple events
            assert mock_manager.track_feature_usage.call_count >= 3
    
    def test_monitoring_mixin(self):
        """Test the MonitoringMixin class."""
        class TestWidget(MonitoringMixin):
            def __init__(self):
                self.init_monitoring("test_widget")
        
        with patch('core.monitoring.get_monitoring_manager') as mock_get_manager:
            mock_manager = Mock()
            # Make monitor_operation a context manager
            mock_context = MagicMock()
            mock_context.__enter__.return_value = None
            mock_context.__exit__.return_value = None
            mock_manager.monitor_operation.return_value = mock_context
            
            mock_get_manager.return_value = mock_manager

            widget = TestWidget()
            assert widget._component_name == "test_widget"
            
            # Test monitoring context
            with widget.monitor("test_operation"):
                pass  # Should not raise exception
            
            # Test usage tracking
            widget.track_usage("test_action", success=True)
            
            # Test error tracking
            widget.track_error("TestError", "Test message", "test_op")


class TestMonitoringSettings:
    """Test monitoring settings integration."""
    
    def test_default_settings(self):
        """Test default settings structure."""
        defaults = MonitoringSettings.DEFAULT_SETTINGS
        assert "enabled" in defaults
        assert "performance_thresholds" in defaults
        assert "feature_tracking" in defaults
        assert "export_options" in defaults
    
    def test_ensure_settings(self):
        """Test ensuring settings exist."""
        mock_settings = Mock()
        mock_settings.get.return_value = None  # No existing settings
        
        MonitoringSettings.ensure_monitoring_settings(mock_settings)
        
        # Should have called set for each setting
        mock_settings.set.assert_called()
        assert mock_settings.set.call_count > 0
    
    def test_get_monitoring_config(self):
        """Test getting monitoring configuration."""
        mock_settings = Mock()
        mock_settings.get.side_effect = lambda cat, key, default=None: default
        
        config = MonitoringSettings.get_monitoring_config(mock_settings)
        
        assert "enabled" in config
        assert "performance_thresholds" in config
        assert isinstance(config["performance_thresholds"], dict)
    
    def test_validate_settings(self):
        """Test settings validation."""
        mock_settings = Mock()
        # Return valid default values
        mock_settings.get.side_effect = lambda cat, key, default=None: default or 60000
        
        issues = MonitoringSettings.validate_monitoring_settings(mock_settings)
        assert isinstance(issues, list)
        # With valid settings, should have no issues
        assert len(issues) == 0
        
        # Test with invalid values
        mock_settings.get.side_effect = lambda cat, key, default=None: -1 if "interval" in key else (default or 60000)
        issues = MonitoringSettings.validate_monitoring_settings(mock_settings)
        assert len(issues) > 0  # Should have validation issues


@pytest.mark.skip(reason="GUI test requires display")
class TestMonitoringDashboard:
    """Test the monitoring dashboard UI."""
    
    def test_dashboard_initialization(self, qtbot):
        """Test dashboard initialization."""
        with patch('ui.dialogs.monitoring_dashboard.get_monitoring_manager'):
            dashboard = MonitoringDashboard()
            qtbot.addWidget(dashboard)
            
            assert dashboard.windowTitle() == "SpritePal - Monitoring Dashboard"
            assert dashboard.tab_widget.count() == 5  # 5 tabs
    
    def test_dashboard_update(self, qtbot):
        """Test dashboard data update."""
        with patch('ui.dialogs.monitoring_dashboard.get_monitoring_manager') as mock_get_manager:
            mock_manager = Mock()
            mock_manager.get_performance_stats.return_value = {}
            mock_manager.get_error_summary.return_value = {"total_errors": 0}
            mock_manager.get_usage_stats.return_value = {"total_events": 0}
            mock_manager.get_health_status.return_value = {"current": {"healthy": True}}
            mock_manager.generate_insights.return_value = []
            mock_manager.generate_report.return_value = Mock(recommendations=[])
            mock_get_manager.return_value = mock_manager
            
            dashboard = MonitoringDashboard()
            qtbot.addWidget(dashboard)
            
            # Test manual update
            dashboard.update_all_data()
            
            # Should have called monitoring methods
            mock_manager.get_performance_stats.assert_called()
            mock_manager.get_error_summary.assert_called()


class TestIntegrationScenarios:
    """Test real-world integration scenarios."""
    
    @pytest.fixture
    def integrated_system(self, qtbot):
        """Set up an integrated monitoring system."""
        # Create mock settings manager
        mock_settings_manager = Mock()
        mock_settings_manager.get.side_effect = lambda cat, key, default: default
        
        # Create monitoring manager with injected settings
        manager = MonitoringManager(settings_manager=mock_settings_manager)
        
        # Patch global get_monitoring_manager to return our test instance
        with patch('core.monitoring.get_monitoring_manager', return_value=manager):
            yield manager, mock_settings_manager
        
        manager.cleanup()
    
    def test_rom_loading_scenario(self, integrated_system):
        """Test complete ROM loading monitoring scenario."""
        manager, settings = integrated_system
        
        # Simulate ROM loading workflow
        workflow = WorkflowTracker("rom_loading")
        
        try:
            # Step 1: Validate ROM path
            workflow.step("validate_path")
            with manager.monitor_operation("validate_rom_path"):
                time.sleep(0.001)
            
            # Step 2: Load ROM data
            workflow.step("load_data")
            with manager.monitor_operation("load_rom_data"):
                time.sleep(0.002)
            
            # Step 3: Parse ROM headers
            workflow.step("parse_headers")
            with manager.monitor_operation("parse_rom_headers"):
                time.sleep(0.001)
            
            workflow.complete(success=True)
            
        except Exception as e:
            workflow.fail(str(e))
            # manager.track_error("ROMLoadingError", str(e), "rom_loading") # Redundant
        
        # Verify monitoring data was collected
        rom_stats = manager.get_performance_stats("load_rom_data")
        assert rom_stats  # Should have performance data
        
        usage_stats = manager.get_usage_stats()
        assert usage_stats["total_events"] > 0
    
    def test_error_recovery_scenario(self, integrated_system):
        """Test error recovery monitoring scenario."""
        manager, settings = integrated_system
        
        # Simulate operations with errors and recovery
        for attempt in range(3):
            try:
                with manager.monitor_operation(f"extraction_attempt_{attempt}"):
                    if attempt < 2:
                        # Fail first two attempts
                        raise ValueError(f"Extraction failed on attempt {attempt}")
                    else:
                        # Succeed on third attempt
                        time.sleep(0.001)
                        
            except ValueError:
                pass # manager.track_error("ExtractionError", str(e), f"extraction_attempt_{attempt}") # Redundant, monitor_operation catches it
        
        # Track successful recovery
        manager.track_feature_usage("extraction", "recovery_success", True, context={"attempts": 3})
        
        # Verify error tracking
        error_summary = manager.get_error_summary()
        assert error_summary["total_errors"] == 2  # Two failed attempts
        
        # Verify final success was tracked
        usage_stats = manager.get_usage_stats()
        assert "extraction" in usage_stats.get("most_used_features", {})
    
    def test_performance_degradation_detection(self, integrated_system):
        """Test detection of performance degradation."""
        manager, settings = integrated_system
        
        # Simulate gradually increasing operation times
        for i in range(10):
            operation_time = 0.001 * (i + 1)  # Increasing time
            
            with manager.monitor_operation("degrading_operation"):
                time.sleep(operation_time)
        
        # Generate insights to detect degradation
        insights = manager.generate_insights()
        
        # Should have some insights about the operation
        assert isinstance(insights, list)
        
        # Get performance stats
        stats = manager.get_performance_stats("degrading_operation")
        assert stats["sample_count"] == 10
        assert stats["duration_stats"]["max_ms"] > stats["duration_stats"]["min_ms"]


if __name__ == "__main__":
    # Run tests with pytest
    pytest.main([__file__, "-v"])
