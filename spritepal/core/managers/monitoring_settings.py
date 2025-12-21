"""
Monitoring Settings Integration for SpritePal

Extends the settings system to include monitoring configuration options.
These settings control how monitoring data is collected and exported.
"""
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.protocols.manager_protocols import SettingsManagerProtocol


class MonitoringSettings:
    """Monitoring-specific settings management."""

    # Default monitoring settings
    DEFAULT_SETTINGS = {
        "enabled": True,  # Master monitoring enable/disable
        "health_check_interval_ms": 60000,  # 1 minute health checks
        "retention_hours": 168,  # 1 week data retention
        "export_format": "json",  # Default export format (json, csv)
        "max_performance_entries": 10000,  # Max performance metrics to keep
        "max_error_entries": 5000,  # Max error events to keep
        "max_usage_entries": 20000,  # Max usage events to keep
        "max_health_entries": 1000,  # Max health metrics to keep
        "privacy_mode": True,  # Respect privacy (no personal data)
        "auto_export_enabled": False,  # Auto-export reports
        "auto_export_interval_hours": 24,  # Auto-export frequency
        "auto_export_keep_reports": 7,  # Number of reports to keep
        "performance_thresholds": {
            "rom_loading_warning_ms": 2000,  # 2 seconds
            "rom_loading_critical_ms": 5000,  # 5 seconds
            "extraction_warning_ms": 3000,  # 3 seconds
            "extraction_critical_ms": 10000,  # 10 seconds
            "thumbnail_warning_ms": 1000,  # 1 second
            "thumbnail_critical_ms": 3000,  # 3 seconds
            "injection_warning_ms": 2000,  # 2 seconds
            "injection_critical_ms": 8000,  # 8 seconds
            "memory_warning_mb": 500,  # 500MB
            "memory_critical_mb": 1000,  # 1GB
            "cpu_warning_percent": 50,  # 50% CPU
            "cpu_critical_percent": 80,  # 80% CPU
        },
        "feature_tracking": {
            "track_ui_interactions": True,
            "track_workflow_patterns": True,
            "track_error_patterns": True,
            "track_performance_bottlenecks": True,
            "track_cache_effectiveness": True,
        },
        "export_options": {
            "include_raw_data": False,  # Include raw metrics in exports
            "anonymize_paths": True,  # Remove user-specific paths
            "compress_exports": True,  # Compress export files
            "export_location": "",  # Custom export location (empty = default)
        }
    }

    @staticmethod
    def ensure_monitoring_settings(settings_manager: SettingsManagerProtocol) -> None:
        """Ensure monitoring settings exist with defaults."""
        for category, settings in MonitoringSettings.DEFAULT_SETTINGS.items():
            if isinstance(settings, dict):
                # Handle nested settings
                for key, value in settings.items():
                    if settings_manager.get("monitoring", f"{category}_{key}") is None:
                        settings_manager.set("monitoring", f"{category}_{key}", value)
            # Handle flat settings
            elif settings_manager.get("monitoring", category) is None:
                settings_manager.set("monitoring", category, settings)

    @staticmethod
    def get_monitoring_config(settings_manager: SettingsManagerProtocol) -> dict[str, object]:
        """Get complete monitoring configuration."""
        MonitoringSettings.ensure_monitoring_settings(settings_manager)

        config = {}

        # Get flat settings
        for key in ["enabled", "health_check_interval_ms", "retention_hours",
                   "export_format", "max_performance_entries", "max_error_entries",
                   "max_usage_entries", "max_health_entries", "privacy_mode",
                   "auto_export_enabled", "auto_export_interval_hours",
                   "auto_export_keep_reports"]:
            config[key] = settings_manager.get("monitoring", key,
                                             MonitoringSettings.DEFAULT_SETTINGS[key])

        # Get nested settings
        config["performance_thresholds"] = {}
        perf_thresholds = MonitoringSettings.DEFAULT_SETTINGS["performance_thresholds"]
        assert isinstance(perf_thresholds, dict)
        for key, default in perf_thresholds.items():
            config["performance_thresholds"][key] = settings_manager.get(
                "monitoring", f"performance_thresholds_{key}", default)

        config["feature_tracking"] = {}
        feature_tracking = MonitoringSettings.DEFAULT_SETTINGS["feature_tracking"]
        assert isinstance(feature_tracking, dict)
        for key, default in feature_tracking.items():
            config["feature_tracking"][key] = settings_manager.get(
                "monitoring", f"feature_tracking_{key}", default)

        config["export_options"] = {}
        export_options = MonitoringSettings.DEFAULT_SETTINGS["export_options"]
        assert isinstance(export_options, dict)
        for key, default in export_options.items():
            config["export_options"][key] = settings_manager.get(
                "monitoring", f"export_options_{key}", default)

        return config

    @staticmethod
    def update_monitoring_config(settings_manager: SettingsManagerProtocol, config: dict[str, object]) -> None:
        """Update monitoring configuration."""
        # Update flat settings
        for key in ["enabled", "health_check_interval_ms", "retention_hours",
                   "export_format", "max_performance_entries", "max_error_entries",
                   "max_usage_entries", "max_health_entries", "privacy_mode",
                   "auto_export_enabled", "auto_export_interval_hours",
                   "auto_export_keep_reports"]:
            if key in config:
                settings_manager.set("monitoring", key, config[key])

        # Update nested settings
        if "performance_thresholds" in config:
            perf_thresholds = config["performance_thresholds"]
            if isinstance(perf_thresholds, dict):
                for key, value in perf_thresholds.items():
                    settings_manager.set("monitoring", f"performance_thresholds_{key}", value)

        if "feature_tracking" in config:
            feature_tracking = config["feature_tracking"]
            if isinstance(feature_tracking, dict):
                for key, value in feature_tracking.items():
                    settings_manager.set("monitoring", f"feature_tracking_{key}", value)

        if "export_options" in config:
            export_options = config["export_options"]
            if isinstance(export_options, dict):
                for key, value in export_options.items():
                    settings_manager.set("monitoring", f"export_options_{key}", value)

        # Save settings
        settings_manager.save_settings()

    @staticmethod
    def get_export_directory(settings_manager: SettingsManagerProtocol) -> Path:
        """Get the directory for monitoring exports."""
        custom_location = settings_manager.get("monitoring", "export_options_export_location", "")

        if custom_location and isinstance(custom_location, (str, Path)) and Path(custom_location).exists():
            return Path(custom_location)

        # Default to monitoring_reports in the application directory
        default_dir = Path.cwd() / "monitoring_reports"
        default_dir.mkdir(parents=True, exist_ok=True)
        return default_dir

    @staticmethod
    def is_monitoring_enabled(settings_manager: SettingsManagerProtocol) -> bool:
        """Check if monitoring is enabled."""
        return bool(settings_manager.get("monitoring", "enabled", True))

    @staticmethod
    def should_track_feature(settings_manager: SettingsManagerProtocol, feature: str) -> bool:
        """Check if a specific feature should be tracked."""
        if not MonitoringSettings.is_monitoring_enabled(settings_manager):
            return False

        feature_key = f"feature_tracking_{feature}"
        return bool(settings_manager.get("monitoring", feature_key, True))

    @staticmethod
    def get_performance_threshold(settings_manager: SettingsManagerProtocol, metric: str) -> float:
        """Get performance threshold for a metric."""
        threshold_key = f"performance_thresholds_{metric}"
        thresholds = MonitoringSettings.DEFAULT_SETTINGS["performance_thresholds"]
        assert isinstance(thresholds, dict)
        default = thresholds.get(metric, 1000)
        value = settings_manager.get("monitoring", threshold_key, default)
        return float(value) if isinstance(value, (int, float, str)) else float(default)

    @staticmethod
    def validate_monitoring_settings(settings_manager: SettingsManagerProtocol) -> list[str]:
        """Validate monitoring settings and return list of issues."""
        issues = []

        # Check intervals
        health_interval = settings_manager.get("monitoring", "health_check_interval_ms", 60000)
        if isinstance(health_interval, (int, float)):
            if health_interval < 1000:  # Minimum 1 second
                issues.append("Health check interval too short (minimum 1 second)")
            if health_interval > 300000:  # Maximum 5 minutes
                issues.append("Health check interval too long (maximum 5 minutes)")

        # Check retention
        retention = settings_manager.get("monitoring", "retention_hours", 168)
        if isinstance(retention, (int, float)):
            if retention < 1:
                issues.append("Data retention too short (minimum 1 hour)")
            if retention > 8760:  # 1 year
                issues.append("Data retention too long (maximum 1 year)")

        # Check entry limits
        for entry_type in ["performance", "error", "usage", "health"]:
            max_entries = settings_manager.get("monitoring", f"max_{entry_type}_entries", 1000)
            if isinstance(max_entries, (int, float)):
                if max_entries < 100:
                    issues.append(f"Max {entry_type} entries too low (minimum 100)")
                if max_entries > 100000:
                    issues.append(f"Max {entry_type} entries too high (maximum 100,000)")

        # Check export format
        export_format = settings_manager.get("monitoring", "export_format", "json")
        if export_format not in ["json", "csv"]:
            issues.append(f"Invalid export format: {export_format} (must be json or csv)")

        # Check thresholds
        thresholds = MonitoringSettings.DEFAULT_SETTINGS["performance_thresholds"]
        assert isinstance(thresholds, dict)
        for threshold_name in thresholds:
            value = settings_manager.get("monitoring", f"performance_thresholds_{threshold_name}",
                                       thresholds[threshold_name])
            if isinstance(value, (int, float)) and value <= 0:
                issues.append(f"Performance threshold {threshold_name} must be positive")

        return issues

    @staticmethod
    def reset_to_defaults(settings_manager: SettingsManagerProtocol) -> None:
        """Reset monitoring settings to defaults."""
        # Clear existing monitoring settings
        session_data = settings_manager.get_session_data()
        if isinstance(session_data, dict) and "monitoring" in session_data:
            del session_data["monitoring"]
            settings_manager.save_session_data(session_data)

        # Ensure defaults are set
        MonitoringSettings.ensure_monitoring_settings(settings_manager)
        settings_manager.save_settings()

    @staticmethod
    def export_settings(settings_manager: SettingsManagerProtocol) -> dict[str, object]:
        """Export monitoring settings for backup/sharing."""
        config = MonitoringSettings.get_monitoring_config(settings_manager)

        # Remove sensitive/system-specific settings
        export_options = config.get("export_options")
        if isinstance(export_options, dict) and export_options.get("anonymize_paths"):
            if "export_location" in export_options:
                export_options["export_location"] = ""

        return {
            "monitoring_settings": config,
            "version": "1.0",
            "exported_at": str(Path.cwd())  # Current directory as reference
        }

    @staticmethod
    def import_settings(settings_manager: SettingsManagerProtocol, settings_data: dict[str, object]) -> bool:
        """Import monitoring settings from backup."""
        try:
            if "monitoring_settings" not in settings_data:
                return False

            config = settings_data["monitoring_settings"]
            if not isinstance(config, dict):
                return False

            # Validate imported settings
            temp_settings = MonitoringSettings.DEFAULT_SETTINGS.copy()
            temp_settings.update(config)

            # Apply settings
            MonitoringSettings.update_monitoring_config(settings_manager, config)
            return True

        except Exception:
            # If import fails, don't modify settings
            return False


# Convenience functions for common monitoring settings operations

def enable_monitoring(settings_manager: SettingsManagerProtocol) -> None:
    """Enable monitoring system."""
    settings_manager.set("monitoring", "enabled", True)
    settings_manager.save_settings()


def disable_monitoring(settings_manager: SettingsManagerProtocol) -> None:
    """Disable monitoring system."""
    settings_manager.set("monitoring", "enabled", False)
    settings_manager.save_settings()


def set_monitoring_privacy_mode(settings_manager: SettingsManagerProtocol, enabled: bool) -> None:
    """Enable or disable privacy mode."""
    settings_manager.set("monitoring", "privacy_mode", enabled)
    settings_manager.save_settings()


def set_health_check_interval(settings_manager: SettingsManagerProtocol, interval_seconds: int) -> None:
    """Set health check interval."""
    interval_ms = max(1000, min(300000, interval_seconds * 1000))  # 1s to 5min
    settings_manager.set("monitoring", "health_check_interval_ms", interval_ms)
    settings_manager.save_settings()


def set_data_retention(settings_manager: SettingsManagerProtocol, hours: int) -> None:
    """Set data retention period."""
    hours = max(1, min(8760, hours))  # 1 hour to 1 year
    settings_manager.set("monitoring", "retention_hours", hours)
    settings_manager.save_settings()


def configure_auto_export(settings_manager: SettingsManagerProtocol, enabled: bool, interval_hours: int = 24) -> None:
    """Configure automatic report export."""
    settings_manager.set("monitoring", "auto_export_enabled", enabled)
    if enabled:
        interval_hours = max(1, min(168, interval_hours))  # 1 hour to 1 week
        settings_manager.set("monitoring", "auto_export_interval_hours", interval_hours)
    settings_manager.save_settings()


def get_current_monitoring_status(settings_manager: SettingsManagerProtocol) -> dict[str, object]:
    """Get current monitoring system status."""
    config = MonitoringSettings.get_monitoring_config(settings_manager)

    health_check_interval_ms = config.get("health_check_interval_ms", 60000)
    health_check_interval = int(health_check_interval_ms) // 1000 if isinstance(health_check_interval_ms, (int, float)) else 60

    feature_tracking_data = config.get("feature_tracking", {})
    if not isinstance(feature_tracking_data, dict):
        feature_tracking_data = {}

    return {
        "enabled": config.get("enabled", True),
        "privacy_mode": config.get("privacy_mode", True),
        "health_check_interval": health_check_interval,  # Convert to seconds
        "data_retention_hours": config.get("retention_hours", 168),
        "auto_export": config.get("auto_export_enabled", False),
        "export_format": config.get("export_format", "json"),
        "feature_tracking": {
            "ui_interactions": feature_tracking_data.get("track_ui_interactions", True),
            "workflows": feature_tracking_data.get("track_workflow_patterns", True),
            "errors": feature_tracking_data.get("track_error_patterns", True),
            "performance": feature_tracking_data.get("track_performance_bottlenecks", True),
            "cache": feature_tracking_data.get("track_cache_effectiveness", True),
        }
    }
