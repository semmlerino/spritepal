"""
Settings dialog for SpritePal application
Provides user interface for configuring application preferences
"""
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, override

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from core.types import WidgetParent
from ui.common.file_dialogs import browse_for_directory
from ui.components.base import DialogBase
from ui.styles import get_button_style, get_muted_text_style

if TYPE_CHECKING:
    from core.managers.application_state_manager import ApplicationStateManager
    from core.services.rom_cache import ROMCache


class SettingsDialog(DialogBase):
    """Dialog for configuring SpritePal settings"""

    # Signals
    settings_changed = Signal()
    cache_cleared = Signal()

    def __init__(self, parent: WidgetParent = None, *,
                 settings_manager: ApplicationStateManager,
                 rom_cache: ROMCache):
        # Store original settings to detect changes
        self._original_settings: dict[str, object] = {}

        super().__init__(
            parent=parent,
            title="SpritePal Settings",
            modal=True,
            size=(600, 500),
            min_size=(500, 400),
            with_status_bar=True,
            with_button_box=True,
        )

        # Assign dependencies
        self.settings_manager = settings_manager
        self.rom_cache = rom_cache

        self._load_original_settings()

        # Set up the dialog content
        self._setup_ui()
        self._load_settings()
        self._update_cache_stats()

    @override
    def _setup_ui(self):
        """Set up the settings dialog UI"""
        # Create tab widget
        self.tab_widget = QTabWidget()

        # Add tabs
        self.tab_widget.addTab(self._create_general_tab(), "General")
        self.tab_widget.addTab(self._create_cache_tab(), "Cache")

        # Set the tab widget as content
        layout = QVBoxLayout()
        layout.addWidget(self.tab_widget)
        self.set_content_layout(layout)

    def _create_general_tab(self) -> QWidget:
        """Create the general settings tab"""
        widget = QWidget(self)
        layout = QVBoxLayout()

        # Single consolidated settings group for better visual balance
        settings_group = QGroupBox("Preferences", widget)
        settings_layout = QFormLayout()
        settings_layout.setVerticalSpacing(12)  # More breathing room

        # Session behavior section
        self.restore_window_check = QCheckBox("Restore window position on startup", self)
        settings_layout.addRow(self.restore_window_check)

        self.auto_save_session_check = QCheckBox("Automatically save session", self)
        settings_layout.addRow(self.auto_save_session_check)

        # Separator line for visual grouping
        separator = QLabel(self)
        separator.setFixedHeight(1)
        separator.setStyleSheet("background-color: #444444; margin: 8px 0px;")
        settings_layout.addRow(separator)

        # File paths section
        dumps_layout = QHBoxLayout()
        self.dumps_dir_edit = QLineEdit(self)
        self.dumps_dir_edit.setReadOnly(True)
        self.dumps_dir_edit.setPlaceholderText("Default location for dump files")
        dumps_layout.addWidget(self.dumps_dir_edit, 1)

        self.dumps_dir_button = QPushButton("Browse...", self)
        self.dumps_dir_button.setStyleSheet(get_button_style())
        self.dumps_dir_button.clicked.connect(self._browse_dumps_directory)
        dumps_layout.addWidget(self.dumps_dir_button)

        settings_layout.addRow("Dumps directory:", dumps_layout)

        settings_group.setLayout(settings_layout)
        layout.addWidget(settings_group)

        # Add stretch to push content to top
        layout.addStretch()

        widget.setLayout(layout)
        return widget

    def _create_cache_tab(self) -> QWidget:
        """Create the cache settings tab"""
        widget = QWidget(self)
        layout = QVBoxLayout()

        # Cache settings group
        cache_group = QGroupBox("Cache Settings", widget)
        cache_layout = QFormLayout()

        # Enable cache checkbox
        self.cache_enabled_check = QCheckBox("Enable ROM scan caching", self)
        self.cache_enabled_check.setToolTip(
            "Cache ROM scan results to speed up subsequent operations"
        )
        self.cache_enabled_check.toggled.connect(self._on_cache_enabled_changed)
        cache_layout.addRow(self.cache_enabled_check)  # Label removed - checkbox text is descriptive

        # Cache location
        location_layout = QHBoxLayout()
        self.cache_location_edit = QLineEdit(self)
        self.cache_location_edit.setPlaceholderText("Default: ~/.spritepal_rom_cache")
        location_layout.addWidget(self.cache_location_edit, 1)

        self.cache_location_button = QPushButton("Browse...", self)
        self.cache_location_button.setStyleSheet(get_button_style())
        self.cache_location_button.clicked.connect(self._browse_cache_location)
        location_layout.addWidget(self.cache_location_button)

        cache_layout.addRow("Cache folder:", location_layout)

        # Cache size limit
        size_layout = QHBoxLayout()
        self.cache_size_spin = QSpinBox(self)
        self.cache_size_spin.setRange(10, 10000)
        self.cache_size_spin.setSuffix(" MB")
        self.cache_size_spin.setToolTip("Maximum cache size in megabytes")
        size_layout.addWidget(self.cache_size_spin)
        size_layout.addStretch()

        cache_layout.addRow("Maximum size:", size_layout)

        # Cache expiration
        expiry_layout = QHBoxLayout()
        self.cache_expiry_spin = QSpinBox(self)
        self.cache_expiry_spin.setRange(1, 365)
        self.cache_expiry_spin.setSuffix(" days")
        self.cache_expiry_spin.setToolTip("Cache entries older than this will be removed")
        expiry_layout.addWidget(self.cache_expiry_spin)
        expiry_layout.addStretch()

        cache_layout.addRow("Delete entries older than:", expiry_layout)

        # Additional options (labels removed - checkbox text is descriptive)
        self.auto_cleanup_check = QCheckBox("Automatically clean up old cache entries", self)
        cache_layout.addRow(self.auto_cleanup_check)

        self.show_indicators_check = QCheckBox("Show cache indicators in UI", self)
        cache_layout.addRow(self.show_indicators_check)

        cache_group.setLayout(cache_layout)
        layout.addWidget(cache_group)

        # Cache statistics group
        stats_group = QGroupBox("Cache Statistics", widget)
        stats_layout = QFormLayout()

        # Cache stats labels
        self.cache_dir_label = QLabel("N/A", self)
        self.cache_dir_label.setStyleSheet(get_muted_text_style())
        stats_layout.addRow("Cache location:", self.cache_dir_label)

        self.cache_files_label = QLabel("0 files", self)
        self.cache_files_label.setStyleSheet(get_muted_text_style())
        stats_layout.addRow("Cached items:", self.cache_files_label)

        self.cache_size_label = QLabel("0 MB", self)
        self.cache_size_label.setStyleSheet(get_muted_text_style())
        stats_layout.addRow("Total size:", self.cache_size_label)

        # Cache actions
        actions_layout = QHBoxLayout()

        self.refresh_stats_button = QPushButton("Refresh", self)
        self.refresh_stats_button.setStyleSheet(get_button_style())
        self.refresh_stats_button.clicked.connect(self._update_cache_stats)
        actions_layout.addWidget(self.refresh_stats_button)

        self.clear_cache_button = QPushButton("Clear Cache", self)
        self.clear_cache_button.setStyleSheet(get_button_style("danger"))
        self.clear_cache_button.clicked.connect(self._clear_cache)
        actions_layout.addWidget(self.clear_cache_button)

        actions_layout.addStretch()
        stats_layout.addRow(actions_layout)  # Label removed - buttons are self-explanatory

        stats_group.setLayout(stats_layout)
        layout.addWidget(stats_group)

        # Add stretch to push content to top
        layout.addStretch()

        # Update enable state
        self._update_cache_controls_state()

        widget.setLayout(layout)
        return widget

    def _load_original_settings(self):
        """Load original settings for change detection"""
        self._original_settings = {
            "restore_window": self.settings_manager.get("ui", "restore_position", True),
            "auto_save_session": self.settings_manager.get("session", "auto_save", True),
            "dumps_dir": self.settings_manager.get("paths", "default_dumps_dir", ""),
            "cache_enabled": self.settings_manager.get_cache_enabled(),
            "cache_location": self.settings_manager.get_cache_location(),
            "cache_max_size": self.settings_manager.get_cache_max_size_mb(),
            "cache_expiry": self.settings_manager.get_cache_expiration_days(),
            "auto_cleanup": self.settings_manager.get("cache", "auto_cleanup", True),
            "show_indicators": self.settings_manager.get("cache", "show_indicators", True),
        }

    def _load_settings(self):
        """Load current settings into UI"""
        # General settings
        self.restore_window_check.setChecked(
            bool(self.settings_manager.get("ui", "restore_position", True))
        )
        self.auto_save_session_check.setChecked(
            bool(self.settings_manager.get("session", "auto_save", True))
        )
        self.dumps_dir_edit.setText(
            str(self.settings_manager.get("paths", "default_dumps_dir", ""))
        )

        # Cache settings
        self.cache_enabled_check.setChecked(self.settings_manager.get_cache_enabled())
        self.cache_location_edit.setText(self.settings_manager.get_cache_location())
        self.cache_size_spin.setValue(self.settings_manager.get_cache_max_size_mb())
        self.cache_expiry_spin.setValue(self.settings_manager.get_cache_expiration_days())
        self.auto_cleanup_check.setChecked(
            bool(self.settings_manager.get("cache", "auto_cleanup", True))
        )
        self.show_indicators_check.setChecked(
            bool(self.settings_manager.get("cache", "show_indicators", True))
        )

        # Update original settings to reflect what was just loaded
        self._load_original_settings()

    def _save_settings(self):
        """Save settings from UI"""
        # General settings
        self.settings_manager.set("ui", "restore_position", self.restore_window_check.isChecked())
        self.settings_manager.set("session", "auto_save", self.auto_save_session_check.isChecked())
        self.settings_manager.set("paths", "default_dumps_dir", self.dumps_dir_edit.text())

        # Cache settings
        self.settings_manager.set_cache_enabled(self.cache_enabled_check.isChecked())
        self.settings_manager.set_cache_location(self.cache_location_edit.text())
        self.settings_manager.set_cache_max_size_mb(self.cache_size_spin.value())
        self.settings_manager.set_cache_expiration_days(self.cache_expiry_spin.value())
        self.settings_manager.set("cache", "auto_cleanup", self.auto_cleanup_check.isChecked())
        self.settings_manager.set("cache", "show_indicators", self.show_indicators_check.isChecked())

        # Save to disk
        self.settings_manager.save_settings()

        # Emit signal
        self.settings_changed.emit()

    def _update_cache_stats(self):
        """Update cache statistics display"""
        try:
            stats = self.rom_cache.get_cache_stats()

            # Update directory
            cache_dir_val = stats.get("cache_dir", "Unknown")
            cache_dir = str(cache_dir_val)
            if cache_dir and len(cache_dir) > 50:
                # Truncate long paths
                cache_dir = "..." + cache_dir[-47:]
            self.cache_dir_label.setText(cache_dir)

            # Update file count
            total_files_val = stats.get("total_files", 0)
            total_files = int(total_files_val) if isinstance(total_files_val, (int, float)) else 0
            sprite_caches_val = stats.get("sprite_location_caches", 0)
            sprite_caches = int(sprite_caches_val) if isinstance(sprite_caches_val, (int, float)) else 0
            rom_caches_val = stats.get("rom_info_caches", 0)
            rom_caches = int(rom_caches_val) if isinstance(rom_caches_val, (int, float)) else 0
            scan_caches_val = stats.get("scan_progress_caches", 0)
            scan_caches = int(scan_caches_val) if isinstance(scan_caches_val, (int, float)) else 0

            file_text = f"{total_files} files"
            if total_files > 0:
                file_text += f" ({sprite_caches} sprites, {rom_caches} ROMs, {scan_caches} scans)"
            self.cache_files_label.setText(file_text)

            # Update size
            size_bytes_val = stats.get("total_size_bytes", 0)
            size_bytes = int(size_bytes_val) if isinstance(size_bytes_val, (int, float)) else 0
            size_mb = size_bytes / (1024 * 1024)
            self.cache_size_label.setText(f"{size_mb:.1f} MB")

            # Update status bar
            if self.status_bar is not None:
                self.status_bar.showMessage(f"Cache refreshed: {total_files} files, {size_mb:.1f} MB")

        except Exception as e:
            # Handle errors gracefully
            self.cache_dir_label.setText("Error reading cache")
            self.cache_files_label.setText("N/A")
            self.cache_size_label.setText("N/A")
            if self.status_bar is not None:
                self.status_bar.showMessage(f"Error reading cache: {e!s}")

    def _on_cache_enabled_changed(self, checked: bool):
        """Handle cache enabled state change"""
        self._update_cache_controls_state()

    def _update_cache_controls_state(self):
        """Update the enabled state of cache controls"""
        enabled = self.cache_enabled_check.isChecked()

        # Enable/disable cache controls
        self.cache_location_edit.setEnabled(enabled)
        self.cache_location_button.setEnabled(enabled)
        self.cache_size_spin.setEnabled(enabled)
        self.cache_expiry_spin.setEnabled(enabled)
        self.auto_cleanup_check.setEnabled(enabled)
        self.show_indicators_check.setEnabled(enabled)
        self.clear_cache_button.setEnabled(enabled)

    def _browse_dumps_directory(self):
        """Browse for default dumps directory"""
        current_dir = self.dumps_dir_edit.text() or str(Path.home())

        dir_path = browse_for_directory(
            self,
            "Select Default Dumps Directory",
            current_dir
        )

        if dir_path:
            self.dumps_dir_edit.setText(dir_path)

    def _browse_cache_location(self):
        """Browse for cache directory"""
        current_dir = self.cache_location_edit.text() or str(Path.home())

        dir_path = browse_for_directory(
            self,
            "Select Cache Directory",
            current_dir
        )

        if dir_path:
            self.cache_location_edit.setText(dir_path)

    def _clear_cache(self):
        """Clear the ROM cache"""
        # Confirm action
        reply = QMessageBox.question(
            self,
            "Clear Cache",
            "Are you sure you want to clear all cached ROM data?\n\n"
            "This will remove all cached scan results and you'll need to "
            "rescan ROMs to rebuild the cache.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            try:
                removed_count = self.rom_cache.clear_cache()

                # Update stats
                self._update_cache_stats()

                # Show result
                if self.status_bar is not None:
                    self.status_bar.showMessage(f"Cache cleared: {removed_count} files removed")

                # Emit signal
                self.cache_cleared.emit()

                QMessageBox.information(
                    self,
                    "Cache Cleared",
                    f"Successfully removed {removed_count} cache files."
                )
            except Exception as e:
                QMessageBox.critical(
                    self,
                    "Error",
                    f"Failed to clear cache: {e!s}"
                )

    @override
    def accept(self):
        """Handle dialog acceptance"""
        # Check if settings have changed
        if self._has_settings_changed():
            self._save_settings()

        super().accept()

    def _has_settings_changed(self) -> bool:
        """Check if any settings have changed"""
        current = {
            "restore_window": self.restore_window_check.isChecked(),
            "auto_save_session": self.auto_save_session_check.isChecked(),
            "dumps_dir": self.dumps_dir_edit.text(),
            "cache_enabled": self.cache_enabled_check.isChecked(),
            "cache_location": self.cache_location_edit.text(),
            "cache_max_size": self.cache_size_spin.value(),
            "cache_expiry": self.cache_expiry_spin.value(),
            "auto_cleanup": self.auto_cleanup_check.isChecked(),
            "show_indicators": self.show_indicators_check.isChecked(),
        }

        return current != self._original_settings
