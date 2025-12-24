"""Tests for ApplicationStateManager.

This module tests the consolidated application state manager including:
- Session management
- Settings persistence
- Workflow state machine
- Cache statistics
- UI coordination
"""
from __future__ import annotations

import json
import threading
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from PySide6.QtGui import QImage

from core.exceptions import SessionError, ValidationError
from core.managers.application_state_manager import ApplicationStateManager, ExtractionState
from tests.fixtures.timeouts import signal_timeout

pytestmark = [
    pytest.mark.headless,
]


@pytest.fixture
def settings_file(tmp_path):
    """Create a temporary settings file path."""
    return tmp_path / "test_settings.json"


@pytest.fixture
def manager(settings_file, qtbot):
    """Create a fresh ApplicationStateManager for each test."""
    mgr = ApplicationStateManager(
        app_name="TestApp",
        settings_path=settings_file,
    )
    yield mgr
    # Cleanup
    mgr.cleanup()


@pytest.fixture
def manager_with_settings(settings_file, qtbot):
    """Create manager with pre-existing settings file."""
    initial_settings = {
        "session": {"vram_path": "/test/vram.dmp", "output_name": "test_sprite"},
        "ui": {"window_width": 1200, "window_height": 800},
        "cache": {"enabled": True, "max_size_mb": 250},
    }
    settings_file.write_text(json.dumps(initial_settings))

    mgr = ApplicationStateManager(
        app_name="TestApp",
        settings_path=settings_file,
    )
    yield mgr
    mgr.cleanup()


class TestApplicationStateManagerInit:
    """Tests for ApplicationStateManager initialization."""

    def test_init_with_defaults(self, settings_file):
        """Manager should initialize with default settings."""
        manager = ApplicationStateManager(
            app_name="TestApp",
            settings_path=settings_file,
        )

        assert manager.app_name == "TestApp"
        assert manager.workflow_state == ExtractionState.IDLE
        manager.cleanup()

    def test_init_with_custom_settings_path(self, tmp_path):
        """Manager should use custom settings path."""
        custom_path = tmp_path / "custom" / "settings.json"
        custom_path.parent.mkdir(parents=True)

        manager = ApplicationStateManager(
            app_name="TestApp",
            settings_path=custom_path,
        )

        # Save and verify file location
        manager.save_settings()
        assert custom_path.exists()
        manager.cleanup()

    def test_init_loads_existing_settings(self, settings_file):
        """Manager should load existing settings on init."""
        # Create settings file first
        initial = {"ui": {"window_width": 1500}}
        settings_file.write_text(json.dumps(initial))

        manager = ApplicationStateManager(
            app_name="TestApp",
            settings_path=settings_file,
        )

        assert manager.get("ui", "window_width") == 1500
        manager.cleanup()

    def test_init_merges_with_defaults(self, settings_file):
        """Manager should merge loaded settings with defaults."""
        # Partial settings (missing some categories)
        partial = {"ui": {"window_width": 1500}}
        settings_file.write_text(json.dumps(partial))

        manager = ApplicationStateManager(
            app_name="TestApp",
            settings_path=settings_file,
        )

        # Custom value preserved
        assert manager.get("ui", "window_width") == 1500
        # Default values filled in
        assert manager.get("session", "create_grayscale") is True
        manager.cleanup()

    def test_init_thread_locks_created(self, manager):
        """Manager should create thread locks on init."""
        assert hasattr(manager, "_state_lock")
        assert hasattr(manager, "_workflow_lock")
        assert hasattr(manager, "_cache_stats_lock")


class TestSettingsPersistence:
    """Tests for settings get/set/save/load."""

    def test_set_and_get_setting(self, manager):
        """set_setting and get_setting should work correctly."""
        manager.set_setting("custom", "test_key", "test_value")

        assert manager.get_setting("custom", "test_key") == "test_value"

    def test_get_setting_with_default(self, manager):
        """get_setting should return default for missing keys."""
        result = manager.get_setting("nonexistent", "key", "default_value")

        assert result == "default_value"

    def test_get_setting_missing_returns_none(self, manager):
        """get_setting should return None if no default specified."""
        result = manager.get_setting("nonexistent", "key")

        assert result is None

    def test_save_settings_creates_file(self, manager, settings_file):
        """save_settings should create settings file."""
        manager.set_setting("test", "key", "value")

        result = manager.save_settings()

        assert result is True
        assert settings_file.exists()

        # Verify content
        data = json.loads(settings_file.read_text())
        assert data["test"]["key"] == "value"

    def test_save_settings_creates_backup(self, manager, settings_file):
        """save_settings should create backup of existing file."""
        # Initial save
        manager.set_setting("version", "num", 1)
        manager.save_settings()

        # Second save should create backup
        manager.set_setting("version", "num", 2)
        manager.save_settings()

        backup_file = settings_file.with_suffix(".json.bak")
        assert backup_file.exists()

        # Backup should have old value
        backup_data = json.loads(backup_file.read_text())
        assert backup_data["version"]["num"] == 1

    def test_load_settings_from_file(self, settings_file):
        """_load_settings should load from file."""
        settings = {"test": {"loaded": True}}
        settings_file.write_text(json.dumps(settings))

        manager = ApplicationStateManager(
            app_name="TestApp",
            settings_path=settings_file,
        )

        assert manager.get("test", "loaded") is True
        manager.cleanup()

    def test_load_settings_handles_corrupted_file(self, settings_file):
        """Manager should handle corrupted settings file."""
        settings_file.write_text("not valid json {{{")

        # Should not raise, should use defaults
        manager = ApplicationStateManager(
            app_name="TestApp",
            settings_path=settings_file,
        )

        # Should have default values
        assert manager.get("cache", "enabled") is True
        manager.cleanup()

    def test_settings_saved_signal_emitted(self, manager, qtbot):
        """settings_saved signal should be emitted on save."""
        with qtbot.waitSignal(manager.settings_saved, timeout=signal_timeout()):
            manager.save_settings()


class TestWorkflowStateMachine:
    """Tests for workflow state machine transitions."""

    def test_initial_workflow_state_is_idle(self, manager):
        """Initial workflow state should be IDLE."""
        assert manager.workflow_state == ExtractionState.IDLE

    def test_transition_idle_to_loading_rom(self, manager):
        """Should allow IDLE -> LOADING_ROM transition."""
        result = manager.transition_workflow(ExtractionState.LOADING_ROM)

        assert result is True
        assert manager.workflow_state == ExtractionState.LOADING_ROM

    def test_transition_idle_to_scanning_sprites(self, manager):
        """Should allow IDLE -> SCANNING_SPRITES transition."""
        result = manager.transition_workflow(ExtractionState.SCANNING_SPRITES)

        assert result is True
        assert manager.workflow_state == ExtractionState.SCANNING_SPRITES

    def test_transition_idle_to_previewing_sprite(self, manager):
        """Should allow IDLE -> PREVIEWING_SPRITE transition."""
        result = manager.transition_workflow(ExtractionState.PREVIEWING_SPRITE)

        assert result is True
        assert manager.workflow_state == ExtractionState.PREVIEWING_SPRITE

    def test_transition_idle_to_searching_sprite(self, manager):
        """Should allow IDLE -> SEARCHING_SPRITE transition."""
        result = manager.transition_workflow(ExtractionState.SEARCHING_SPRITE)

        assert result is True
        assert manager.workflow_state == ExtractionState.SEARCHING_SPRITE

    def test_transition_idle_to_extracting(self, manager):
        """Should allow IDLE -> EXTRACTING transition."""
        result = manager.transition_workflow(ExtractionState.EXTRACTING)

        assert result is True
        assert manager.workflow_state == ExtractionState.EXTRACTING

    def test_transition_loading_rom_to_idle(self, manager):
        """Should allow LOADING_ROM -> IDLE transition."""
        manager.transition_workflow(ExtractionState.LOADING_ROM)

        result = manager.transition_workflow(ExtractionState.IDLE)

        assert result is True
        assert manager.workflow_state == ExtractionState.IDLE

    def test_transition_loading_rom_to_error(self, manager):
        """Should allow LOADING_ROM -> ERROR transition."""
        manager.transition_workflow(ExtractionState.LOADING_ROM)

        result = manager.transition_workflow(ExtractionState.ERROR, error_message="Test error")

        assert result is True
        assert manager.workflow_state == ExtractionState.ERROR
        assert manager.workflow_error_message == "Test error"

    def test_transition_error_to_idle(self, manager):
        """Should allow ERROR -> IDLE transition (reset)."""
        manager.transition_workflow(ExtractionState.LOADING_ROM)
        manager.transition_workflow(ExtractionState.ERROR, error_message="Test")

        result = manager.transition_workflow(ExtractionState.IDLE)

        assert result is True
        assert manager.workflow_state == ExtractionState.IDLE
        assert manager.workflow_error_message is None

    def test_invalid_transition_returns_false(self, manager):
        """Invalid transitions should return False."""
        # Cannot go directly from IDLE to ERROR
        result = manager.transition_workflow(ExtractionState.ERROR)

        assert result is False
        assert manager.workflow_state == ExtractionState.IDLE

    def test_invalid_transition_preserves_state(self, manager):
        """Invalid transitions should not change state."""
        manager.transition_workflow(ExtractionState.LOADING_ROM)

        # Cannot go from LOADING_ROM to EXTRACTING
        result = manager.transition_workflow(ExtractionState.EXTRACTING)

        assert result is False
        assert manager.workflow_state == ExtractionState.LOADING_ROM

    def test_workflow_state_changed_signal(self, manager, qtbot):
        """workflow_state_changed signal should be emitted."""
        with qtbot.waitSignal(manager.workflow_state_changed, timeout=signal_timeout()) as blocker:
            manager.transition_workflow(ExtractionState.LOADING_ROM)

        old_state, new_state = blocker.args
        assert old_state == ExtractionState.IDLE
        assert new_state == ExtractionState.LOADING_ROM

    def test_state_changed_signal_with_workflow_category(self, manager, qtbot):
        """state_changed signal should emit with 'workflow' category."""
        with qtbot.waitSignal(manager.state_changed, timeout=signal_timeout()) as blocker:
            manager.transition_workflow(ExtractionState.LOADING_ROM)

        category, data = blocker.args
        assert category == "workflow"
        assert data["old"] == "IDLE"
        assert data["new"] == "LOADING_ROM"

    def test_error_state_stores_message(self, manager):
        """ERROR state should store error message."""
        manager.transition_workflow(ExtractionState.LOADING_ROM)
        manager.transition_workflow(ExtractionState.ERROR, error_message="ROM load failed")

        assert manager.workflow_error_message == "ROM load failed"

    def test_reset_workflow_returns_to_idle(self, manager):
        """reset_workflow should return to IDLE from any valid state."""
        manager.transition_workflow(ExtractionState.LOADING_ROM)
        manager.transition_workflow(ExtractionState.ERROR)

        manager.reset_workflow()

        assert manager.workflow_state == ExtractionState.IDLE


class TestWorkflowStateProperties:
    """Tests for workflow state property methods."""

    def test_is_workflow_busy_in_blocking_states(self, manager):
        """is_workflow_busy should be True in blocking states."""
        blocking_states = [
            ExtractionState.LOADING_ROM,
            ExtractionState.SCANNING_SPRITES,
            ExtractionState.EXTRACTING,
        ]

        for state in blocking_states:
            manager._workflow_state = ExtractionState.IDLE  # Reset
            manager.transition_workflow(state)
            assert manager.is_workflow_busy is True, f"Should be busy in {state.name}"

    def test_is_workflow_busy_in_non_blocking_states(self, manager):
        """is_workflow_busy should be False in non-blocking states."""
        non_blocking_states = [
            ExtractionState.IDLE,
            ExtractionState.PREVIEWING_SPRITE,
            ExtractionState.SEARCHING_SPRITE,
        ]

        for state in non_blocking_states:
            manager._workflow_state = state  # Direct set for testing
            assert manager.is_workflow_busy is False, f"Should not be busy in {state.name}"

    def test_can_extract_when_idle(self, manager):
        """can_extract should be True only when IDLE."""
        assert manager.can_extract is True

        manager.transition_workflow(ExtractionState.LOADING_ROM)
        assert manager.can_extract is False

    def test_can_preview_when_idle(self, manager):
        """can_preview should be True when IDLE or SEARCHING."""
        assert manager.can_preview is True

        manager.transition_workflow(ExtractionState.SEARCHING_SPRITE)
        assert manager.can_preview is True

        manager.transition_workflow(ExtractionState.IDLE)
        manager.transition_workflow(ExtractionState.LOADING_ROM)
        assert manager.can_preview is False

    def test_can_scan_when_idle(self, manager):
        """can_scan should be True only when IDLE."""
        assert manager.can_scan is True

        manager.transition_workflow(ExtractionState.PREVIEWING_SPRITE)
        assert manager.can_scan is False

    def test_can_search_when_idle_or_previewing(self, manager):
        """can_search should be True when IDLE or PREVIEWING."""
        assert manager.can_search is True

        manager.transition_workflow(ExtractionState.PREVIEWING_SPRITE)
        assert manager.can_search is True

        manager.transition_workflow(ExtractionState.IDLE)
        manager.transition_workflow(ExtractionState.LOADING_ROM)
        assert manager.can_search is False


class TestSessionManagement:
    """Tests for session save/load/restore."""

    def test_save_session(self, manager, settings_file):
        """save_session should persist settings."""
        manager.set("session", "test_key", "test_value")

        result = manager.save_session()

        assert result is True
        assert settings_file.exists()

    def test_load_session(self, manager, settings_file):
        """load_session should load from file."""
        # Create file with data
        data = {"session": {"loaded_key": "loaded_value"}, "ui": {}}
        settings_file.write_text(json.dumps(data))

        result = manager.load_session()

        assert result is True
        assert manager.get("session", "loaded_key") == "loaded_value"

    def test_load_session_from_custom_path(self, manager, tmp_path):
        """load_session should accept custom path."""
        custom_file = tmp_path / "custom_session.json"
        data = {"session": {"custom": "data"}, "ui": {}}
        custom_file.write_text(json.dumps(data))

        result = manager.load_session(str(custom_file))

        assert result is True
        assert manager.get("session", "custom") == "data"

    def test_restore_session(self, manager, settings_file, qtbot):
        """restore_session should reload and emit signal."""
        # Save some data
        manager.set("session", "restore_test", "value")
        manager.save_session()

        # Modify in memory
        manager.set("session", "restore_test", "modified")

        # Restore should revert to saved
        with qtbot.waitSignal(manager.session_restored, timeout=signal_timeout()):
            result = manager.restore_session()

        assert result == manager.get_session_data()

    def test_get_session_data(self, manager):
        """get_session_data should return session category."""
        manager.set("session", "key1", "value1")
        manager.set("session", "key2", "value2")

        data = manager.get_session_data()

        assert data.get("key1") == "value1"
        assert data.get("key2") == "value2"

    def test_update_session_data(self, manager, qtbot):
        """update_session_data should update multiple values."""
        with qtbot.waitSignal(manager.session_changed, timeout=signal_timeout()):
            manager.update_session_data({
                "vram_path": "/new/vram.dmp",
                "cgram_path": "/new/cgram.dmp",
            })

        assert manager.get("session", "vram_path") == "/new/vram.dmp"
        assert manager.get("session", "cgram_path") == "/new/cgram.dmp"

    def test_clear_session(self, manager, qtbot):
        """clear_session should reset session to defaults."""
        manager.set("session", "custom_key", "custom_value")

        with qtbot.waitSignal(manager.session_changed, timeout=signal_timeout()):
            manager.clear_session()

        # Custom key should be gone, defaults restored
        assert manager.get("session", "custom_key") is None
        assert manager.get("session", "create_grayscale") is True

    def test_session_changed_signal_on_set(self, manager, qtbot):
        """session_changed should emit on set."""
        with qtbot.waitSignal(manager.session_changed, timeout=signal_timeout()):
            manager.set("session", "trigger", "signal")


class TestRecentFiles:
    """Tests for recent files management."""

    def test_add_recent_file(self, manager, tmp_path):
        """add_recent_file should add to list."""
        test_file = tmp_path / "test.dmp"
        test_file.touch()

        manager.add_recent_file(str(test_file))

        recent = manager.get_recent_files()
        assert str(test_file) in recent

    def test_get_recent_files(self, manager, tmp_path):
        """get_recent_files should return list."""
        # Add some files
        for i in range(3):
            f = tmp_path / f"file{i}.dmp"
            f.touch()
            manager.add_recent_file(str(f))

        recent = manager.get_recent_files()

        assert len(recent) == 3

    def test_clear_recent_files(self, manager, tmp_path):
        """clear_recent_files should clear list."""
        test_file = tmp_path / "test.dmp"
        test_file.touch()
        manager.add_recent_file(str(test_file))

        # Use internal method for typed recent files
        manager._add_recent_file("vram", str(test_file))
        manager.clear_recent_files("vram")

        # The typed list should be cleared
        assert manager.get("recent_files", "vram") == []

    def test_recent_files_max_limit(self, manager, tmp_path):
        """Recent files should be limited to max size."""
        # Add more than max (20 for add_recent_file)
        for i in range(25):
            f = tmp_path / f"file{i}.dmp"
            f.touch()
            manager.add_recent_file(str(f))

        recent = manager.get_recent_files(max_files=30)  # Request more than limit

        # Should be capped at 20
        assert len(recent) <= 20


class TestCacheStatistics:
    """Tests for cache session statistics."""

    def test_record_cache_hit(self, manager, qtbot):
        """record_cache_hit should increment hit counter."""
        with qtbot.waitSignal(manager.cache_stats_updated, timeout=signal_timeout()):
            manager.record_cache_hit()

        stats = manager.get_cache_session_stats()
        assert stats["hits"] == 1
        assert stats["total_requests"] == 1

    def test_record_cache_miss(self, manager, qtbot):
        """record_cache_miss should increment miss counter."""
        with qtbot.waitSignal(manager.cache_stats_updated, timeout=signal_timeout()):
            manager.record_cache_miss()

        stats = manager.get_cache_session_stats()
        assert stats["misses"] == 1
        assert stats["total_requests"] == 1

    def test_get_cache_session_stats(self, manager):
        """get_cache_session_stats should return read-only stats."""
        manager.record_cache_hit()
        manager.record_cache_miss()
        manager.record_cache_hit()

        stats = manager.get_cache_session_stats()

        assert stats["hits"] == 2
        assert stats["misses"] == 1
        assert stats["total_requests"] == 3

    def test_reset_cache_session_stats(self, manager, qtbot):
        """reset_cache_session_stats should zero all counters."""
        manager.record_cache_hit()
        manager.record_cache_miss()

        with qtbot.waitSignal(manager.cache_stats_updated, timeout=signal_timeout()):
            manager.reset_cache_session_stats()

        stats = manager.get_cache_session_stats()
        assert stats["hits"] == 0
        assert stats["misses"] == 0
        assert stats["total_requests"] == 0

    def test_cache_hit_rate_calculation(self, manager):
        """cache_hit_rate should calculate percentage correctly."""
        # 3 hits, 1 miss = 75% hit rate
        manager.record_cache_hit()
        manager.record_cache_hit()
        manager.record_cache_hit()
        manager.record_cache_miss()

        assert manager.cache_hit_rate == 75.0

    def test_cache_hit_rate_zero_requests(self, manager):
        """cache_hit_rate should be 0 with no requests."""
        assert manager.cache_hit_rate == 0.0

    def test_cache_stats_updated_signal(self, manager, qtbot):
        """cache_stats_updated signal should emit with stats."""
        with qtbot.waitSignal(manager.cache_stats_updated, timeout=signal_timeout()) as blocker:
            manager.record_cache_hit()

        stats = blocker.args[0]
        assert "hits" in stats
        assert "misses" in stats
        assert "total_requests" in stats


class TestWindowState:
    """Tests for window geometry persistence."""

    def test_update_window_state(self, manager):
        """update_window_state should store geometry."""
        manager.update_window_state({
            "width": 1200,
            "height": 800,
            "x": 100,
            "y": 50,
        })

        geometry = manager.get_window_geometry()

        assert geometry["width"] == 1200
        assert geometry["height"] == 800
        assert geometry["x"] == 100
        assert geometry["y"] == 50

    def test_get_window_geometry_defaults(self, manager):
        """get_window_geometry should return defaults for missing values."""
        geometry = manager.get_window_geometry()

        # Should have default values
        assert geometry["width"] == 900
        assert geometry["height"] == 600
        assert geometry["x"] == -1
        assert geometry["y"] == -1
        assert geometry["splitter_sizes"] == []

    def test_window_state_with_splitter_sizes(self, manager):
        """update_window_state should handle splitter sizes."""
        manager.update_window_state({
            "width": 1000,
            "height": 700,
            "splitter_sizes": [300, 400, 300],
        })

        geometry = manager.get_window_geometry()

        assert geometry["splitter_sizes"] == [300, 400, 300]


class TestCacheSettings:
    """Tests for cache configuration methods."""

    def test_get_cache_enabled_default(self, manager):
        """get_cache_enabled should return True by default."""
        assert manager.get_cache_enabled() is True

    def test_set_cache_enabled(self, manager):
        """set_cache_enabled should update setting."""
        manager.set_cache_enabled(False)

        assert manager.get_cache_enabled() is False

    def test_get_cache_location(self, manager):
        """get_cache_location should return empty string by default."""
        assert manager.get_cache_location() == ""

    def test_set_cache_location(self, manager, tmp_path):
        """set_cache_location should update setting."""
        custom_path = str(tmp_path / "cache")

        manager.set_cache_location(custom_path)

        assert manager.get_cache_location() == custom_path

    def test_get_cache_max_size_mb(self, manager):
        """get_cache_max_size_mb should return default 500."""
        assert manager.get_cache_max_size_mb() == 500

    def test_set_cache_max_size_mb(self, manager):
        """set_cache_max_size_mb should update with bounds checking."""
        manager.set_cache_max_size_mb(250)

        assert manager.get_cache_max_size_mb() == 250

    def test_cache_max_size_mb_bounds(self, manager):
        """set_cache_max_size_mb should enforce min/max bounds."""
        from utils.constants import CACHE_SIZE_MAX_MB, CACHE_SIZE_MIN_MB

        # Try to set below minimum
        manager.set_cache_max_size_mb(1)
        assert manager.get_cache_max_size_mb() == CACHE_SIZE_MIN_MB

        # Try to set above maximum
        manager.set_cache_max_size_mb(100000)
        assert manager.get_cache_max_size_mb() == CACHE_SIZE_MAX_MB


class TestThreadSafety:
    """Tests for thread safety."""

    def test_concurrent_get_set_operations(self, manager):
        """Concurrent get/set should not corrupt state."""
        errors: list[Exception] = []
        iterations = 100

        def writer():
            try:
                for i in range(iterations):
                    manager.set_setting("concurrent", f"key_{i % 10}", i)
            except Exception as e:
                errors.append(e)

        def reader():
            try:
                for _ in range(iterations):
                    for j in range(10):
                        manager.get_setting("concurrent", f"key_{j}")
            except Exception as e:
                errors.append(e)

        threads = [
            threading.Thread(target=writer),
            threading.Thread(target=reader),
            threading.Thread(target=writer),
            threading.Thread(target=reader),
        ]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0

    def test_concurrent_workflow_transitions(self, manager):
        """Concurrent workflow transitions should not corrupt state."""
        errors: list[Exception] = []
        iterations = 50

        def transition_loop():
            try:
                for _ in range(iterations):
                    # Try various transitions
                    manager.transition_workflow(ExtractionState.LOADING_ROM)
                    manager.transition_workflow(ExtractionState.IDLE)
            except Exception as e:
                errors.append(e)

        threads = [
            threading.Thread(target=transition_loop),
            threading.Thread(target=transition_loop),
        ]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        # Final state should be valid
        assert manager.workflow_state in ExtractionState

    def test_concurrent_cache_stats(self, manager):
        """Concurrent cache stats updates should not corrupt counters."""
        iterations = 100

        def record_hits():
            for _ in range(iterations):
                manager.record_cache_hit()

        def record_misses():
            for _ in range(iterations):
                manager.record_cache_miss()

        threads = [
            threading.Thread(target=record_hits),
            threading.Thread(target=record_misses),
        ]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        stats = manager.get_cache_session_stats()
        assert stats["hits"] == iterations
        assert stats["misses"] == iterations
        assert stats["total_requests"] == iterations * 2


class TestExportImportSettings:
    """Tests for settings export/import."""

    def test_export_settings(self, manager, tmp_path):
        """export_settings should write to file."""
        export_path = tmp_path / "exported.json"
        manager.set("test", "export_key", "export_value")

        manager.export_settings(str(export_path))

        assert export_path.exists()
        data = json.loads(export_path.read_text())
        assert data["test"]["export_key"] == "export_value"

    def test_import_settings(self, manager, tmp_path, qtbot):
        """import_settings should load from file."""
        import_path = tmp_path / "import.json"
        import_data = {
            "session": {"imported": "data"},
            "ui": {"theme": "dark"},
        }
        import_path.write_text(json.dumps(import_data))

        with qtbot.waitSignal(manager.session_changed, timeout=signal_timeout()):
            manager.import_settings(str(import_path))

        assert manager.get("session", "imported") == "data"
        assert manager.get("ui", "theme") == "dark"

    def test_import_settings_file_not_found(self, manager, tmp_path):
        """import_settings should raise for missing file."""
        with pytest.raises(ValidationError):
            manager.import_settings(str(tmp_path / "nonexistent.json"))

    def test_import_settings_invalid_format(self, manager, tmp_path):
        """import_settings should raise for invalid format."""
        invalid_path = tmp_path / "invalid.json"
        invalid_path.write_text("[]")  # Array instead of object

        with pytest.raises(ValidationError):
            manager.import_settings(str(invalid_path))


class TestUICoordination:
    """Tests for UI coordination signals."""

    def test_set_current_offset(self, manager, qtbot):
        """set_current_offset should emit signal."""
        with qtbot.waitSignal(manager.current_offset_changed, timeout=signal_timeout()) as blocker:
            manager.set_current_offset(0x1234)

        assert blocker.args[0] == 0x1234

    def test_get_current_offset(self, manager):
        """get_current_offset should return stored offset."""
        manager.set_current_offset(0xABCD)

        assert manager.get_current_offset() == 0xABCD

    def test_get_current_offset_none(self, manager):
        """get_current_offset should return None if not set."""
        assert manager.get_current_offset() is None

    def test_emit_preview_ready(self, manager, qtbot):
        """emit_preview_ready should emit signal with image."""
        test_image = QImage(10, 10, QImage.Format.Format_ARGB32)

        with qtbot.waitSignal(manager.preview_ready, timeout=signal_timeout()) as blocker:
            manager.emit_preview_ready(0x5678, test_image)

        offset, image = blocker.args
        assert offset == 0x5678
        assert image.width() == 10


class TestResetState:
    """Tests for reset_state method."""

    def test_reset_state_clears_runtime(self, manager):
        """reset_state should clear runtime state."""
        manager.set_state("temp", "key", "value")

        manager.reset_state()

        assert manager.get_state("temp", "key") is None

    def test_reset_state_resets_workflow(self, manager):
        """reset_state should reset workflow to IDLE."""
        manager.transition_workflow(ExtractionState.LOADING_ROM)

        manager.reset_state()

        assert manager.workflow_state == ExtractionState.IDLE

    def test_reset_state_full_resets_settings(self, manager):
        """reset_state with full_reset should reset settings."""
        manager.set_setting("custom", "key", "value")

        manager.reset_state(full_reset=True)

        # Custom setting should be gone
        assert manager.get_setting("custom", "key") is None

    def test_reset_state_clears_cache_stats(self, manager):
        """reset_state should clear cache statistics."""
        manager.record_cache_hit()
        manager.record_cache_miss()

        manager.reset_state()

        stats = manager.get_cache_session_stats()
        assert stats["hits"] == 0
        assert stats["misses"] == 0


class TestRuntimeState:
    """Tests for runtime state management."""

    def test_set_and_get_state(self, manager):
        """set_state and get_state should work."""
        manager.set_state("dialog", "visible", True)

        assert manager.get_state("dialog", "visible") is True

    def test_get_state_default(self, manager):
        """get_state should return default for missing."""
        result = manager.get_state("nonexistent", "key", "default")

        assert result == "default"

    def test_clear_state_namespace(self, manager):
        """clear_state should clear specific namespace."""
        manager.set_state("ns1", "key", "value")
        manager.set_state("ns2", "key", "value")

        manager.clear_state("ns1")

        assert manager.get_state("ns1", "key") is None
        assert manager.get_state("ns2", "key") == "value"

    def test_clear_state_all(self, manager):
        """clear_state without namespace should clear all."""
        manager.set_state("ns1", "key", "value")
        manager.set_state("ns2", "key", "value")

        manager.clear_state()

        assert manager.get_state("ns1", "key") is None
        assert manager.get_state("ns2", "key") is None


class TestConvenienceMethods:
    """Tests for convenience methods."""

    def test_validate_file_paths(self, manager, tmp_path):
        """validate_file_paths should check existence."""
        # Create a file that exists
        vram_file = tmp_path / "vram.dmp"
        vram_file.touch()

        manager.set("session", "vram_path", str(vram_file))
        manager.set("session", "cgram_path", "/nonexistent/path")

        validated = manager.validate_file_paths()

        assert validated["vram_path"] == str(vram_file)
        assert validated["cgram_path"] == ""  # Invalid path cleared

    def test_get_default_directory(self, manager, tmp_path):
        """get_default_directory should return appropriate path."""
        # With no last_used_dir, should return home or default dumps dir
        default = manager.get_default_directory()

        assert Path(default).is_absolute()

        # Set last_used_dir
        last_dir = tmp_path / "last"
        last_dir.mkdir()
        manager.set("paths", "last_used_dir", str(last_dir))

        assert manager.get_default_directory() == str(last_dir)

    def test_set_last_used_directory(self, manager, tmp_path):
        """set_last_used_directory should store valid paths."""
        test_dir = tmp_path / "test_dir"
        test_dir.mkdir()

        manager.set_last_used_directory(str(test_dir))

        assert manager.get("paths", "last_used_dir") == str(test_dir)

    def test_set_last_used_directory_ignores_invalid(self, manager):
        """set_last_used_directory should ignore invalid paths."""
        manager.set("paths", "last_used_dir", "original")

        manager.set_last_used_directory("/nonexistent/path")

        # Should not have changed
        assert manager.get("paths", "last_used_dir") == "original"
