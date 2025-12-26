"""
Integration tests for drag & drop functionality using real Qt components.

Tests file drop handling across UI components with real DropZone widgets.
Uses programmatic file setting (set_file()) and verifies signal emissions.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from PySide6.QtTest import QSignalSpy

from ui.extraction_panel import DropZone
from utils.constants import VRAM_SPRITE_OFFSET

# Real Qt widget tests - require gui environment
pytestmark = [
    pytest.mark.gui,
    pytest.mark.integration,
]


# ============================================================================
# Test Fixtures
# ============================================================================


@pytest.fixture
def sample_files(tmp_path):
    """Create sample files for drag & drop testing.

    Uses tmp_path fixture for parallel-safe test file creation.
    """
    # Create valid dump files
    vram_data = bytearray(0x10000)  # 64KB VRAM
    cgram_data = bytearray(512)  # 512 bytes CGRAM
    oam_data = bytearray(544)  # 544 bytes OAM

    files = {}
    files["vram"] = tmp_path / "test_VRAM.dmp"
    files["cgram"] = tmp_path / "test_CGRAM.dmp"
    files["oam"] = tmp_path / "test_OAM.dmp"
    files["invalid"] = tmp_path / "invalid.txt"

    # Write valid files
    files["vram"].write_bytes(vram_data)
    files["cgram"].write_bytes(cgram_data)
    files["oam"].write_bytes(oam_data)
    files["invalid"].write_text("invalid content")

    # Create backup files for overwrite testing
    files["vram_backup"] = tmp_path / "backup_VRAM.dmp"
    files["vram_backup"].write_bytes(vram_data)

    return files


@pytest.fixture
def vram_drop_zone(qtbot, isolated_managers):
    """Create a real DropZone widget for VRAM files."""
    from core.app_context import get_app_context

    drop_zone = DropZone(file_type="VRAM", settings_manager=get_app_context().application_state_manager)
    qtbot.addWidget(drop_zone)
    return drop_zone


@pytest.fixture
def cgram_drop_zone(qtbot, isolated_managers):
    """Create a real DropZone widget for CGRAM files."""
    from core.app_context import get_app_context

    drop_zone = DropZone(file_type="CGRAM", settings_manager=get_app_context().application_state_manager)
    qtbot.addWidget(drop_zone)
    return drop_zone


@pytest.fixture
def oam_drop_zone(qtbot, isolated_managers):
    """Create a real DropZone widget for OAM files."""
    from core.app_context import get_app_context

    drop_zone = DropZone(file_type="OAM", settings_manager=get_app_context().application_state_manager)
    qtbot.addWidget(drop_zone)
    return drop_zone


# ============================================================================
# DropZone Widget Tests - Real Component Behavior
# ============================================================================


class TestDropZoneIntegration:
    """Test DropZone widget with real Qt components."""

    def test_drop_zone_initialization(self, qtbot, vram_drop_zone):
        """Test DropZone initializes correctly."""
        assert vram_drop_zone.file_type == "VRAM"
        assert vram_drop_zone.file_path == ""
        assert not vram_drop_zone.has_file()
        assert vram_drop_zone.get_file_path() == ""

    def test_set_file_emits_signal(self, qtbot, vram_drop_zone, sample_files):
        """Test that set_file() emits file_dropped signal."""
        # Set up signal spy
        spy = QSignalSpy(vram_drop_zone.file_dropped)

        # Set file programmatically
        vram_path = str(sample_files["vram"])
        vram_drop_zone.set_file(vram_path)

        # Verify signal was emitted
        assert spy.count() == 1
        assert spy.at(0)[0] == vram_path

        # Verify state
        assert vram_drop_zone.has_file()
        assert vram_drop_zone.get_file_path() == vram_path
        assert vram_drop_zone.file_path == vram_path

    def test_clear_drop_zone(self, qtbot, vram_drop_zone, sample_files):
        """Test clearing a drop zone."""
        # First set a file
        vram_path = str(sample_files["vram"])
        vram_drop_zone.set_file(vram_path)
        assert vram_drop_zone.has_file()

        # Clear the drop zone
        vram_drop_zone.clear()

        # Verify cleared state
        assert not vram_drop_zone.has_file()
        assert vram_drop_zone.get_file_path() == ""
        assert vram_drop_zone.file_path == ""

    def test_overwrite_file(self, qtbot, vram_drop_zone, sample_files):
        """Test overwriting a file in drop zone."""
        spy = QSignalSpy(vram_drop_zone.file_dropped)

        # Set first file
        vram_path = str(sample_files["vram"])
        vram_drop_zone.set_file(vram_path)
        assert vram_drop_zone.get_file_path() == vram_path
        assert spy.count() == 1

        # Set second file (overwrite)
        backup_path = str(sample_files["vram_backup"])
        vram_drop_zone.set_file(backup_path)

        # Verify overwrite
        assert vram_drop_zone.get_file_path() == backup_path
        assert spy.count() == 2
        assert spy.at(1)[0] == backup_path

    def test_set_nonexistent_file(self, qtbot, vram_drop_zone, tmp_path):
        """Test setting a non-existent file path.

        Note: DropZone.set_file() only emits file_dropped if Path.exists() is True.
        This is by design - invalid files are rejected at the widget level.
        """
        spy = QSignalSpy(vram_drop_zone.file_dropped)

        # Try to set non-existent file
        nonexistent = str(tmp_path / "nonexistent.dmp")
        vram_drop_zone.set_file(nonexistent)

        # Widget rejects non-existent files - no signal emitted
        assert spy.count() == 0
        # File path should NOT be set for non-existent files
        assert not vram_drop_zone.has_file()

    def test_multiple_drop_zones_independent(self, qtbot, vram_drop_zone, cgram_drop_zone, sample_files):
        """Test that multiple drop zones are independent."""
        vram_spy = QSignalSpy(vram_drop_zone.file_dropped)
        cgram_spy = QSignalSpy(cgram_drop_zone.file_dropped)

        # Set files in each drop zone
        vram_drop_zone.set_file(str(sample_files["vram"]))
        cgram_drop_zone.set_file(str(sample_files["cgram"]))

        # Verify each drop zone has its own file
        assert vram_drop_zone.get_file_path() == str(sample_files["vram"])
        assert cgram_drop_zone.get_file_path() == str(sample_files["cgram"])

        # Verify signals were emitted independently
        assert vram_spy.count() == 1
        assert cgram_spy.count() == 1


class TestDropZoneFileTypeValidation:
    """Test DropZone with different file types."""

    def test_vram_drop_zone_file_type(self, qtbot, vram_drop_zone):
        """Test VRAM drop zone has correct file type."""
        assert vram_drop_zone.file_type == "VRAM"

    def test_cgram_drop_zone_file_type(self, qtbot, cgram_drop_zone):
        """Test CGRAM drop zone has correct file type."""
        assert cgram_drop_zone.file_type == "CGRAM"

    def test_oam_drop_zone_file_type(self, qtbot, oam_drop_zone):
        """Test OAM drop zone has correct file type."""
        assert oam_drop_zone.file_type == "OAM"


class TestDropZoneStateManagement:
    """Test DropZone state management scenarios."""

    def test_sequential_set_clear_cycles(self, qtbot, vram_drop_zone, sample_files):
        """Test multiple set/clear cycles.

        Note: clear() emits file_dropped with empty string if there was a previous file.
        So each cycle generates 2 emissions: one for set_file, one for clear.
        """
        spy = QSignalSpy(vram_drop_zone.file_dropped)

        for i in range(3):
            # Set file - emits with file path
            vram_drop_zone.set_file(str(sample_files["vram"]))
            assert vram_drop_zone.has_file()
            # Each cycle: set emits (2*i+1), clear emits (2*i+2)
            # After set in cycle i: count = 2*i + 1
            assert spy.count() == 2 * i + 1

            # Clear - emits with empty string
            vram_drop_zone.clear()
            assert not vram_drop_zone.has_file()
            # After clear in cycle i: count = 2*i + 2
            assert spy.count() == 2 * i + 2

    def test_clear_empty_drop_zone(self, qtbot, vram_drop_zone):
        """Test clearing an already empty drop zone."""
        assert not vram_drop_zone.has_file()

        # Clear should be safe to call on empty drop zone
        vram_drop_zone.clear()

        assert not vram_drop_zone.has_file()
        assert vram_drop_zone.get_file_path() == ""


# ============================================================================
# Multi-Component Integration Tests
# ============================================================================


class TestMultiDropZoneWorkflow:
    """Test workflows involving multiple drop zones."""

    def test_complete_file_set_workflow(
        self,
        qtbot,
        vram_drop_zone,
        cgram_drop_zone,
        oam_drop_zone,
        sample_files,
    ):
        """Test setting files in all three drop zones."""
        # Set up spies
        vram_spy = QSignalSpy(vram_drop_zone.file_dropped)
        cgram_spy = QSignalSpy(cgram_drop_zone.file_dropped)
        oam_spy = QSignalSpy(oam_drop_zone.file_dropped)

        # Set files in order
        vram_drop_zone.set_file(str(sample_files["vram"]))
        cgram_drop_zone.set_file(str(sample_files["cgram"]))
        oam_drop_zone.set_file(str(sample_files["oam"]))

        # Verify all files set
        assert vram_drop_zone.has_file()
        assert cgram_drop_zone.has_file()
        assert oam_drop_zone.has_file()

        # Verify signals
        assert vram_spy.count() == 1
        assert cgram_spy.count() == 1
        assert oam_spy.count() == 1

        # Verify paths
        assert vram_drop_zone.get_file_path() == str(sample_files["vram"])
        assert cgram_drop_zone.get_file_path() == str(sample_files["cgram"])
        assert oam_drop_zone.get_file_path() == str(sample_files["oam"])

    def test_partial_file_workflow(
        self,
        qtbot,
        vram_drop_zone,
        cgram_drop_zone,
        oam_drop_zone,
        sample_files,
    ):
        """Test workflow with only required files (VRAM + CGRAM)."""
        # Set only required files
        vram_drop_zone.set_file(str(sample_files["vram"]))
        cgram_drop_zone.set_file(str(sample_files["cgram"]))

        # Verify required files set
        assert vram_drop_zone.has_file()
        assert cgram_drop_zone.has_file()

        # OAM should still be empty
        assert not oam_drop_zone.has_file()

    def test_clear_all_drop_zones(
        self,
        qtbot,
        vram_drop_zone,
        cgram_drop_zone,
        oam_drop_zone,
        sample_files,
    ):
        """Test clearing all drop zones."""
        # Set all files
        vram_drop_zone.set_file(str(sample_files["vram"]))
        cgram_drop_zone.set_file(str(sample_files["cgram"]))
        oam_drop_zone.set_file(str(sample_files["oam"]))

        # Clear all
        vram_drop_zone.clear()
        cgram_drop_zone.clear()
        oam_drop_zone.clear()

        # Verify all cleared
        assert not vram_drop_zone.has_file()
        assert not cgram_drop_zone.has_file()
        assert not oam_drop_zone.has_file()


# ============================================================================
# Edge Case Tests
# ============================================================================


class TestDropZoneEdgeCases:
    """Test edge cases in drop zone behavior."""

    def test_empty_path_string(self, qtbot, vram_drop_zone):
        """Test setting empty path string."""
        spy = QSignalSpy(vram_drop_zone.file_dropped)

        # Set empty string
        vram_drop_zone.set_file("")

        # Should emit signal with empty string
        assert spy.count() == 1

    def test_path_with_spaces(self, qtbot, vram_drop_zone, tmp_path):
        """Test file path with spaces."""
        spy = QSignalSpy(vram_drop_zone.file_dropped)

        # Create file with spaces in name
        spaced_file = tmp_path / "file with spaces.dmp"
        spaced_file.write_bytes(bytearray(0x10000))

        # Set file
        vram_drop_zone.set_file(str(spaced_file))

        # Verify
        assert spy.count() == 1
        assert vram_drop_zone.get_file_path() == str(spaced_file)

    def test_unicode_path(self, qtbot, vram_drop_zone, tmp_path):
        """Test file path with unicode characters."""
        spy = QSignalSpy(vram_drop_zone.file_dropped)

        # Create file with unicode name
        unicode_file = tmp_path / "测试文件.dmp"
        unicode_file.write_bytes(bytearray(0x10000))

        # Set file
        vram_drop_zone.set_file(str(unicode_file))

        # Verify
        assert spy.count() == 1
        assert vram_drop_zone.get_file_path() == str(unicode_file)

    def test_very_long_path(self, qtbot, vram_drop_zone, tmp_path):
        """Test handling of long file paths."""
        spy = QSignalSpy(vram_drop_zone.file_dropped)

        # Create nested directory structure
        deep_path = tmp_path
        for i in range(10):
            deep_path = deep_path / f"nested_dir_{i}"
        deep_path.mkdir(parents=True, exist_ok=True)

        # Create file in deep path
        deep_file = deep_path / "deep_file.dmp"
        deep_file.write_bytes(bytearray(0x10000))

        # Set file
        vram_drop_zone.set_file(str(deep_file))

        # Verify
        assert spy.count() == 1
        assert vram_drop_zone.get_file_path() == str(deep_file)


# ============================================================================
# Signal Flow Integration Tests
# ============================================================================


class TestDropZoneSignalFlow:
    """Test signal flow and connections."""

    def test_signal_contains_file_path(self, qtbot, vram_drop_zone, sample_files):
        """Test that emitted signal contains correct file path."""
        received_paths = []

        def capture_path(path):
            received_paths.append(path)

        vram_drop_zone.file_dropped.connect(capture_path)

        # Set file
        vram_path = str(sample_files["vram"])
        vram_drop_zone.set_file(vram_path)

        # Verify signal payload
        assert len(received_paths) == 1
        assert received_paths[0] == vram_path

    def test_multiple_signal_connections(self, qtbot, vram_drop_zone, sample_files):
        """Test that multiple signal connections all receive events."""
        received_1 = []
        received_2 = []
        received_3 = []

        vram_drop_zone.file_dropped.connect(lambda p: received_1.append(p))
        vram_drop_zone.file_dropped.connect(lambda p: received_2.append(p))
        vram_drop_zone.file_dropped.connect(lambda p: received_3.append(p))

        # Set file
        vram_path = str(sample_files["vram"])
        vram_drop_zone.set_file(vram_path)

        # All connections should receive
        assert received_1 == [vram_path]
        assert received_2 == [vram_path]
        assert received_3 == [vram_path]
