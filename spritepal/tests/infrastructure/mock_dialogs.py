"""
Mock Dialog Infrastructure for Testing

This module provides mock implementations of all dialogs to avoid metaclass
and Qt initialization issues during test collection, following Qt Testing Best Practices.

Key Patterns Applied:
- Pattern 1: Real components with mocked dependencies (QT_TESTING_BEST_PRACTICES.md:93-123)
- Pattern 2: Mock dialog exec() methods (QT_TESTING_BEST_PRACTICES.md:449-479)
- Pitfall 1: Qt Container Truthiness (QT_TESTING_BEST_PRACTICES.md:314-331)
"""
from __future__ import annotations

import contextlib
import threading
from collections.abc import Callable
from typing import Any
from unittest.mock import MagicMock, Mock

from .mock_dialogs_base import CallbackSignal, MockDialogBase


class MockDialog(MockDialogBase):
    """
    Pure Python test dialog that provides callback-based signals without Qt dependencies.

    Following updated best practices to avoid all Qt inheritance in mocks
    to prevent metaclass conflicts and "Fatal Python error: Aborted" crashes.
    """

    def __init__(self, parent: Any | None = None):
        super().__init__(parent)
        self.visible = False
        self.modal = True
        self._window_title = ""

    def exec(self) -> int:
        """Mock exec() to prevent blocking (Pattern 2)."""
        return self.result_value

    def show(self) -> None:
        """Mock show() method."""
        self.visible = True

    def hide(self) -> None:
        """Mock hide() method."""
        self.visible = False

    def close(self) -> bool:
        """Mock close() method."""
        self.visible = False
        # Emit rejected signal via callbacks
        for callback in self.rejected_callbacks:
            with contextlib.suppress(Exception):
                callback()
        return True

    def accept(self) -> None:
        """Mock accept() method."""
        self.result_value = self.DialogCode.Accepted
        self.visible = False
        # Emit accepted signal via callbacks
        for callback in self.accepted_callbacks:
            with contextlib.suppress(Exception):
                callback()
        # Emit finished signal via callbacks
        for callback in self.finished_callbacks:
            with contextlib.suppress(Exception):
                callback(self.DialogCode.Accepted)

    def reject(self) -> None:
        """Mock reject() method."""
        self.result_value = self.DialogCode.Rejected
        self.visible = False
        # Emit rejected signal via callbacks
        for callback in self.rejected_callbacks:
            with contextlib.suppress(Exception):
                callback()
        # Emit finished signal via callbacks
        for callback in self.finished_callbacks:
            with contextlib.suppress(Exception):
                callback(self.DialogCode.Rejected)

    def isVisible(self) -> bool:
        """Mock isVisible() method."""
        return self.visible

    def setWindowTitle(self, title: str) -> None:
        """Mock setWindowTitle() method."""
        self._window_title = title

    def windowTitle(self) -> str:
        """Mock windowTitle() method."""
        return self._window_title

    def setModal(self, modal: bool) -> None:
        """Mock setModal() method."""
        self.modal = modal

    def isModal(self) -> bool:
        """Mock isModal() method."""
        return self.modal

class MockUnifiedOffsetDialog(MockDialog):
    """
    Mock implementation of UnifiedManualOffsetDialog.

    Provides all the signals and methods without triggering
    the DialogBase metaclass initialization issues.
    """

    def __init__(
        self,
        parent: Any | None = None,
        rom_cache: Any | None = None,
        settings_manager: Any | None = None,
        extraction_manager: Any | None = None,
        rom_extractor: Any | None = None,
    ) -> None:
        super().__init__(parent)

        # Store injected dependencies for potential inspection in tests
        self._rom_cache = rom_cache
        self._settings_manager = settings_manager

        # External signal callbacks for ROM extraction panel integration
        self.offset_changed_callbacks: list[Callable[[int], None]] = []
        self.sprite_found_callbacks: list[Callable[[int, str], None]] = []  # offset, name
        self.validation_failed_callbacks: list[Callable[[str], None]] = []

        # Mock UI components - initialized to Mock objects for initialization tests
        # Ensure these don't evaluate to False when empty (Qt container truthiness issue)
        self.tab_widget = Mock()
        self.tab_widget.__bool__ = lambda: True

        self.browse_tab = Mock()
        self.browse_tab.__bool__ = lambda: True

        self.smart_tab = Mock()
        self.smart_tab.__bool__ = lambda: True

        self.history_tab = Mock()
        self.history_tab.__bool__ = lambda: True

        self.preview_widget = Mock()
        self.preview_widget.__bool__ = lambda: True

        self.status_panel = Mock()
        self.status_panel.__bool__ = lambda: True

        self.status_collapsible = Mock()
        self.status_collapsible.__bool__ = lambda: True

        self.apply_btn = Mock()
        self.apply_btn.__bool__ = lambda: True

        self.mini_rom_map = Mock()
        self.mini_rom_map.__bool__ = lambda: True

        self.bookmarks_menu = Mock()
        self.bookmarks_menu.__bool__ = lambda: True
        self.bookmarks = []

        # Business logic state
        self.rom_path = ""
        self.rom_size = 0x400000

        # Mock manager references (use injected or create mocks)
        self.extraction_manager = extraction_manager if extraction_manager else None
        self.rom_extractor = rom_extractor if rom_extractor else None
        self._manager_mutex = Mock()

        # Mock ROM cache (use injected or create mock)
        if rom_cache:
            self.rom_cache = rom_cache
        else:
            self.rom_cache = Mock()
            self.rom_cache.get_cache_stats.return_value = {"hits": 0, "misses": 0}
        self._cache_stats = {"hits": 0, "misses": 0, "total_requests": 0}
        self._adjacent_offsets_cache = set()

        # Mock workers
        self.preview_worker = None
        self.search_worker = None

        # Mock preview coordinator
        self.smart_preview_coordinator = Mock()

    def set_rom_data(self, rom_path: str, rom_size: int, extraction_manager: Any = None) -> None:
        """Mock method to set ROM data."""
        self.rom_path = rom_path
        self.rom_size = rom_size
        if extraction_manager is not None:
            self.extraction_manager = extraction_manager

    def set_managers(self, extraction_manager: Any, rom_extractor: Any) -> None:
        """Mock method to set managers."""
        self.extraction_manager = extraction_manager
        self.rom_extractor = rom_extractor

    def update_offset(self, offset: int) -> None:
        """Mock method to update offset."""
        for callback in self.offset_changed_callbacks:
            with contextlib.suppress(Exception):
                callback(offset)

    def set_offset(self, offset: int) -> bool:
        """Mock method to set offset (called by tests)."""
        # Store the offset
        self._current_offset = offset
        # Trigger callbacks
        for callback in self.offset_changed_callbacks:
            with contextlib.suppress(Exception):
                callback(offset)
        return True

    def get_current_offset(self) -> int:
        """Mock method to get current offset."""
        return getattr(self, '_current_offset', 0)

    def cleanup(self) -> None:
        """Mock cleanup method."""
        pass

    # Signal-like properties for compatibility
    @property
    def offset_changed(self):
        """Offset changed signal interface."""
        return CallbackSignal(self.offset_changed_callbacks)

    @property
    def sprite_found(self):
        """Sprite found signal interface."""
        return CallbackSignal(self.sprite_found_callbacks)

    @property
    def validation_failed(self):
        """Validation failed signal interface."""
        return CallbackSignal(self.validation_failed_callbacks)

class MockSettingsDialogImpl(MockDialog):
    """Test implementation of SettingsDialog."""

    def __init__(self, parent: Any | None = None):
        super().__init__(parent)
        self.settings_changed_callbacks: list[Callable[[dict], None]] = []
        self.settings = {}
        self.setWindowTitle("SpritePal Settings")

        # Mock UI components for initialization tests
        # Ensure widgets don't evaluate to False when empty
        self.tab_widget = Mock()
        self.tab_widget.__bool__ = lambda: True
        # Set up tab widget mock to return expected values
        self.tab_widget.count.return_value = 2
        self.tab_widget.tabText.side_effect = lambda idx: ["General", "Cache"][idx] if idx < 2 else ""

        # Mock checkboxes
        self.restore_window_check = Mock()
        self.restore_window_check.__bool__ = lambda: True
        self.restore_window_check.isChecked.return_value = True
        self.restore_window_check.setChecked = Mock()

        self.auto_save_session_check = Mock()
        self.auto_save_session_check.__bool__ = lambda: True
        self.auto_save_session_check.isChecked.return_value = False
        self.auto_save_session_check.setChecked = Mock()

        # Mock line edits
        self.dumps_dir_edit = Mock()
        self.dumps_dir_edit.__bool__ = lambda: True
        self.dumps_dir_edit.text.return_value = "/test/dumps"
        self.dumps_dir_edit.setText = Mock()

        # Cache settings
        self.cache_enabled_check = Mock()
        self.cache_enabled_check.__bool__ = lambda: True
        self.cache_enabled_check.isChecked.return_value = False
        self.cache_enabled_check.setChecked = Mock()

        self.cache_location_edit = Mock()
        self.cache_location_edit.__bool__ = lambda: True
        self.cache_location_edit.text.return_value = "/custom/cache"
        self.cache_location_edit.setText = Mock()

        self.cache_size_spin = Mock()
        self.cache_size_spin.__bool__ = lambda: True
        self.cache_size_spin.value.return_value = 250
        self.cache_size_spin.setValue = Mock()

        self.cache_expiration_spin = Mock()
        self.cache_expiration_spin.__bool__ = lambda: True
        self.cache_expiration_spin.value.return_value = 14
        self.cache_expiration_spin.setValue = Mock()

        self.auto_cleanup_check = Mock()
        self.auto_cleanup_check.__bool__ = lambda: True
        self.auto_cleanup_check.isChecked.return_value = True
        self.auto_cleanup_check.setChecked = Mock()

        self.show_indicators_check = Mock()
        self.show_indicators_check.__bool__ = lambda: True
        self.show_indicators_check.isChecked.return_value = False
        self.show_indicators_check.setChecked = Mock()

    def get_settings(self) -> dict:
        """Get current settings."""
        return self.settings

    def set_settings(self, settings: dict) -> None:
        """Set settings."""
        self.settings = settings
        for callback in self.settings_changed_callbacks:
            with contextlib.suppress(Exception):
                callback(settings)

    @property
    def settings_changed(self):
        """Settings changed signal interface."""
        return CallbackSignal(self.settings_changed_callbacks)

class MockGridArrangementDialogImpl(MockDialog):
    """Test implementation of GridArrangementDialog."""

    def __init__(self, parent: Any | None = None):
        super().__init__(parent)
        self.arrangement_changed_callbacks: list[Callable[[list], None]] = []
        self.tiles = []
        self.arrangement = []

        # Mock UI components
        self.preview_widget = Mock()
        self.preview_widget.__bool__ = lambda: True

        self.columns_slider = Mock()
        self.columns_slider.__bool__ = lambda: True
        self.columns_slider.value.return_value = 4

    def set_tiles(self, tiles: list) -> None:
        """Set tiles for arrangement."""
        self.tiles = tiles

    def get_arrangement(self) -> list:
        """Get current arrangement."""
        return self.arrangement

    @property
    def arrangement_changed(self):
        """Arrangement changed signal interface."""
        return CallbackSignal(self.arrangement_changed_callbacks)

class MockRowArrangementDialogImpl(MockDialog):
    """Test implementation of RowArrangementDialog."""

    def __init__(self, parent: Any | None = None):
        super().__init__(parent)
        self.arrangement_updated_callbacks: list[Callable[[list], None]] = []
        self.sprites = []
        self.arrangement = []

        # Mock UI components
        self.preview_widget = Mock()
        self.preview_widget.__bool__ = lambda: True

        self.preview_area = Mock()
        self.preview_area.__bool__ = lambda: True

        self.arrangement_list = Mock()
        self.arrangement_list.__bool__ = lambda: True

    def set_sprites(self, sprites: list) -> None:
        """Set sprites for arrangement."""
        self.sprites = sprites

    def get_arrangement(self) -> list:
        """Get current arrangement."""
        return self.arrangement

    @property
    def arrangement_updated(self):
        """Arrangement updated signal interface."""
        return CallbackSignal(self.arrangement_updated_callbacks)

class MockAdvancedSearchDialogImpl(MockDialog):
    """Test implementation of AdvancedSearchDialog."""

    def __init__(self, parent: Any | None = None):
        super().__init__(parent)
        self.search_requested_callbacks: list[Callable[[dict], None]] = []
        self.result_selected_callbacks: list[Callable[[int], None]] = []
        self.search_params = {}
        self.results = []

    def set_search_params(self, params: dict) -> None:
        """Set search parameters."""
        self.search_params = params

    def add_result(self, offset: int, data: dict) -> None:
        """Add a search result."""
        self.results.append((offset, data))

    def clear_results(self) -> None:
        """Clear all results."""
        self.results = []

    @property
    def search_requested(self):
        """Search requested signal interface."""
        return CallbackSignal(self.search_requested_callbacks)

    @property
    def result_selected(self):
        """Result selected signal interface."""
        return CallbackSignal(self.result_selected_callbacks)

class MockResumeScanDialogImpl(MockDialog):
    """Test implementation of ResumeScanDialog."""

    # Dialog result constants
    RESUME = "RESUME"
    START_FRESH = "START_FRESH"
    CANCEL = "CANCEL"

    def __init__(self, scan_info: Any = None, parent: Any | None = None):
        # Initialize callbacks first
        self.resume_requested_callbacks: list[Callable[[int], None]] = []
        self.skip_requested_callbacks: list[Callable[[], None]] = []

        # Handle both dict (scan_info) and parent widget parameters
        if isinstance(scan_info, dict):
            super().__init__(parent)
            self.scan_info = scan_info
            self.last_offset = scan_info.get("current_offset", 0)
            self.sprite_count = scan_info.get("total_found", 0)
        else:
            # scan_info might be the parent widget
            super().__init__(scan_info if scan_info is not None else parent)
            self.scan_info = {}
            self.last_offset = 0
            self.sprite_count = 0

        self.setWindowTitle("Resume Sprite Scan?")
        self.user_choice = self.CANCEL  # Default choice

        # Mock UI components - ensure they don't evaluate to False when empty
        self.message_label = Mock()
        self.message_label.__bool__ = lambda: True

        self.resume_button = Mock()
        self.resume_button.__bool__ = lambda: True
        self.resume_button.text = Mock(return_value="Resume Scan")
        self.resume_button.isDefault = Mock(return_value=True)
        self.resume_button.click = Mock()

        self.fresh_button = Mock()
        self.fresh_button.__bool__ = lambda: True
        self.fresh_button.text = Mock(return_value="Start Fresh")
        self.fresh_button.click = Mock()

        self.cancel_button = Mock()
        self.cancel_button.__bool__ = lambda: True
        self.cancel_button.text = Mock(return_value="Cancel")
        self.cancel_button.click = Mock()

        self.skip_button = Mock()
        self.skip_button.__bool__ = lambda: True

        # Connect button clicks to choice setting
        self.resume_button.click.side_effect = lambda: self._set_choice_and_accept(self.RESUME)
        self.fresh_button.click.side_effect = lambda: self._set_choice_and_accept(self.START_FRESH)
        self.cancel_button.click.side_effect = lambda: self._set_choice_and_reject(self.CANCEL)

    def _set_choice_and_accept(self, choice: str) -> None:
        """Set user choice and accept dialog."""
        self.user_choice = choice
        self.accept()

    def _set_choice_and_reject(self, choice: str) -> None:
        """Set user choice and reject dialog."""
        self.user_choice = choice
        self.reject()

    def set_scan_info(self, last_offset: int, sprite_count: int) -> None:
        """Set scan information."""
        self.last_offset = last_offset
        self.sprite_count = sprite_count

    def get_user_choice(self) -> str:
        """Get the user's choice."""
        return self.user_choice

    def _format_progress_info(self) -> str:
        """Format progress information for display."""
        if not self.scan_info:
            return "Progress: No scan data available\nSprites found: 0"

        # Calculate progress percentage
        scan_range = self.scan_info.get("scan_range", {})
        start = scan_range.get("start", 0)
        end = scan_range.get("end", 0)
        current = self.scan_info.get("current_offset", start)

        if end > start:
            progress = min(100.0, max(0.0, (current - start) / (end - start) * 100))
        else:
            progress = 0.0

        # Format the progress info
        total_found = self.scan_info.get("total_found", 0)
        lines = [
            f"Progress: {progress:.1f}% complete",
            f"Sprites found: {total_found}",
            f"Last position: 0x{current:06X}",
        ]

        if scan_range:
            lines.append(f"Scan range: 0x{start:06X} - 0x{end:06X}")

        return "\n".join(lines)

    @property
    def resume_requested(self):
        """Resume requested signal interface."""
        return CallbackSignal(self.resume_requested_callbacks)

    @property
    def skip_requested(self):
        """Skip requested signal interface."""
        return CallbackSignal(self.skip_requested_callbacks)

    @classmethod
    def show_resume_dialog(cls, scan_info: dict, parent: Any | None = None) -> str:
        """Convenience method to show dialog and return user choice."""
        dialog = cls(scan_info, parent)
        dialog.exec()
        return dialog.get_user_choice()

class MockUserErrorDialogImpl(MockDialog):
    """Test implementation of UserErrorDialog."""

    def __init__(self, error_message: str, technical_details: str = "", parent: Any | None = None):
        super().__init__(parent)
        self.error_message = error_message
        self.details = technical_details
        self._window_title = "Error"  # Default title

    def set_details(self, details: str) -> None:
        """Set error details."""
        self.details = details

    @staticmethod
    def show_error(
        parent: Any | None,
        error_message: str,
        technical_details: str | None = None
    ) -> None:
        """Convenience method to show error dialog (non-blocking in tests)."""
        # In tests, this is a no-op to avoid blocking modal dialogs
        pass

class MockDialogSingleton:
    """
    Test implementation of dialog singleton pattern.

    Avoids QtThreadSafeSingleton issues during testing.
    """
    _instance = None
    _destroyed = False
    _lock = threading.Lock()

    @classmethod
    def get_dialog(cls, parent=None):
        """Get or create the singleton dialog instance."""
        if cls._instance is not None:
            try:
                if cls._instance.isVisible():
                    return cls._instance
            except (RuntimeError, AttributeError):
                cls._instance = None

        with cls._lock:
            if cls._instance is None:
                cls._instance = cls._create_instance(parent)
            return cls._instance

    @classmethod
    def _create_instance(cls, parent=None):
        """Create a new dialog instance."""
        return MockUnifiedOffsetDialog(parent)

    @classmethod
    def is_dialog_open(cls):
        """Check if dialog is open."""
        if cls._instance is None:
            return False
        try:
            return cls._instance.isVisible()
        except (RuntimeError, AttributeError):
            return False

    @classmethod
    def get_current_dialog(cls):
        """Get current dialog if visible."""
        if cls.is_dialog_open():
            return cls._instance
        return None

    @classmethod
    def _cleanup_instance(cls, instance=None):
        """Cleanup the instance."""
        # Handle both calling patterns: _cleanup_instance() and _cleanup_instance(instance)
        cleanup_target = instance or cls._instance
        if cleanup_target:
            try:
                cleanup_target.close()
            except (RuntimeError, AttributeError):
                pass  # Widget might already be destroyed
        cls._instance = None
        cls._destroyed = True

def create_test_dialog(dialog_class_name: str, parent: Any | None = None) -> MockDialog:
    """
    Factory function to create mock dialogs by class name.

    Args:
        dialog_class_name: Name of the dialog class to mock
        parent: Optional parent widget

    Returns:
        Mock dialog instance
    """
    dialog_map = {
        "UnifiedManualOffsetDialog": MockUnifiedOffsetDialog,
        "SettingsDialog": MockSettingsDialogImpl,
        "GridArrangementDialog": MockGridArrangementDialogImpl,
        "RowArrangementDialog": MockRowArrangementDialogImpl,
        "AdvancedSearchDialog": MockAdvancedSearchDialogImpl,
        "ResumeScanDialog": MockResumeScanDialogImpl,
        "UserErrorDialog": MockUserErrorDialogImpl,
    }

    dialog_class = dialog_map.get(dialog_class_name, MockDialog)
    return dialog_class(parent)

def patch_dialog_imports():
    """
    Patch all dialog imports to use mock implementations.

    This should be called in test setup to prevent real dialog imports
    that trigger DialogBase metaclass issues.
    """
    import sys

    # Create test modules for all dialog imports
    test_modules = {
        'ui.dialogs.manual_offset_unified_integrated': MagicMock(
            UnifiedManualOffsetDialog=MockUnifiedOffsetDialog
        ),
        'ui.dialogs.settings_dialog': MagicMock(
            SettingsDialog=MockSettingsDialogImpl
        ),
        'ui.dialogs.grid_arrangement_dialog': MagicMock(
            GridArrangementDialog=MockGridArrangementDialogImpl
        ),
        'ui.dialogs.row_arrangement_dialog': MagicMock(
            RowArrangementDialog=MockRowArrangementDialogImpl
        ),
        'ui.dialogs.advanced_search_dialog': MagicMock(
            AdvancedSearchDialog=MockAdvancedSearchDialogImpl
        ),
        'ui.dialogs.resume_scan_dialog': MagicMock(
            ResumeScanDialog=MockResumeScanDialogImpl
        ),
        'ui.dialogs.user_error_dialog': MagicMock(
            UserErrorDialog=MockUserErrorDialogImpl
        ),
        # NOTE: We no longer patch 'ui.dialogs' itself as a MagicMock since that
        # breaks imports of other dialogs like monitoring_dashboard. Individual
        # submodule patches above are sufficient.
    }

    # Patch sys.modules
    for module_name, test_module in test_modules.items():
        sys.modules[module_name] = test_module

    return test_modules

# Backward compatibility aliases
MockQDialog = MockDialog
MockUnifiedManualOffsetDialog = MockUnifiedOffsetDialog
MockSettingsDialog = MockSettingsDialogImpl
MockGridArrangementDialog = MockGridArrangementDialogImpl
MockRowArrangementDialog = MockRowArrangementDialogImpl
MockAdvancedSearchDialog = MockAdvancedSearchDialogImpl
MockResumeScanDialog = MockResumeScanDialogImpl
MockUserErrorDialog = MockUserErrorDialogImpl
create_mock_dialog = create_test_dialog
