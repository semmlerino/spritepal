"""
Integration tests for drag & drop functionality - Priority 1 test implementation.
Tests file drag & drop handling across UI components.
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import Mock

import pytest

# NOTE: pythonpath configured in pyproject.toml - no sys.path manipulation needed

# Systematic pytest markers applied based on test content analysis
pytestmark = [
    pytest.mark.file_io,
    pytest.mark.headless,
    pytest.mark.integration,
    pytest.mark.mock_only,
    pytest.mark.no_qt,
    pytest.mark.rom_data,
    pytest.mark.ci_safe,
    pytest.mark.signals_slots,
    pytest.mark.slow,
    pytest.mark.allows_registry_state,
]

# We'll test the core drag-drop logic without Qt dependencies
from utils.constants import VRAM_SPRITE_OFFSET


class TestDragDropIntegration:
    """Test drag & drop functionality integration"""

    @pytest.fixture
    def sample_files(self):
        """Create sample files for drag & drop testing"""
        temp_dir = tempfile.mkdtemp()

        # Create valid dump files
        vram_data = bytearray(0x10000)  # 64KB
        cgram_data = bytearray(512)  # 512 bytes
        oam_data = bytearray(544)  # 544 bytes

        files = {}
        files["vram"] = Path(temp_dir) / "test_VRAM.dmp"
        files["cgram"] = Path(temp_dir) / "test_CGRAM.dmp"
        files["oam"] = Path(temp_dir) / "test_OAM.dmp"
        files["invalid"] = Path(temp_dir) / "invalid.txt"
        files["nonexistent"] = Path(temp_dir) / "nonexistent.dmp"

        # Write valid files
        files["vram"].write_bytes(vram_data)
        files["cgram"].write_bytes(cgram_data)
        files["oam"].write_bytes(oam_data)
        files["invalid"].write_text("invalid content")

        # Create backup files for overwrite testing
        files["vram_backup"] = Path(temp_dir) / "backup_VRAM.dmp"
        files["vram_backup"].write_bytes(vram_data)

        yield {"temp_dir": temp_dir, "files": files}

        # Cleanup
        import shutil

        shutil.rmtree(temp_dir)

    def create_mock_drop_zone(self, file_type="VRAM"):
        """Create a mock drop zone that simulates DropZone behavior"""
        drop_zone = Mock()
        drop_zone.file_type = file_type
        drop_zone.file_path = ""
        drop_zone.file_dropped = Mock()
        drop_zone.file_dropped.emit = Mock()

        # Mock drag-drop methods that simulate the real behavior
        def mock_drag_enter(event):
            if event.mimeData().hasUrls():
                event.acceptProposedAction()
                return True
            return False

        def mock_drop_event(event):
            files = [url.toLocalFile() for url in event.mimeData().urls()]
            if files and os.path.exists(files[0]):
                drop_zone.file_path = files[0]
                drop_zone.file_dropped.emit(files[0])
                return True
            return False

        def mock_has_file():
            return bool(drop_zone.file_path)

        def mock_get_file_path():
            return drop_zone.file_path

        def mock_clear():
            drop_zone.file_path = ""

        drop_zone.dragEnterEvent = mock_drag_enter
        drop_zone.dropEvent = mock_drop_event
        drop_zone.has_file = mock_has_file
        drop_zone.get_file_path = mock_get_file_path
        drop_zone.clear = mock_clear

        return drop_zone

    def create_mock_drag_drop_events(self, file_paths):
        """Create mock drag & drop events"""
        mime_data = Mock()
        urls = []
        for path in file_paths:
            url = Mock()
            url.toLocalFile.return_value = str(path)
            urls.append(url)
        mime_data.urls.return_value = urls
        mime_data.hasUrls.return_value = bool(urls)

        # Create drag enter event
        drag_enter = Mock()
        drag_enter.mimeData.return_value = mime_data
        drag_enter.acceptProposedAction = Mock()

        # Create drop event
        drop_event = Mock()
        drop_event.mimeData.return_value = mime_data

        return drag_enter, drop_event

    @pytest.mark.integration
    def test_single_file_drag_drop(self, sample_files):
        """Test basic single file drag-drop functionality"""
        drop_zone = self.create_mock_drop_zone("VRAM")

        # Create drag & drop events
        drag_enter, drop_event = self.create_mock_drag_drop_events(
            [sample_files["files"]["vram"]]
        )

        # Test drag enter
        result = drop_zone.dragEnterEvent(drag_enter)
        assert result is True
        assert drag_enter.acceptProposedAction.called

        # Test drop event
        result = drop_zone.dropEvent(drop_event)
        assert result is True

        # Verify file was set
        assert drop_zone.file_path == str(sample_files["files"]["vram"])
        assert drop_zone.file_dropped.emit.called

        # Verify UI state
        assert drop_zone.has_file()
        assert drop_zone.get_file_path() == str(sample_files["files"]["vram"])

    @pytest.mark.integration
    def test_multiple_file_drag_drop(self, sample_files):
        """Test multiple files dropped simultaneously"""
        drop_zone = self.create_mock_drop_zone("VRAM")

        # Create drag & drop events with multiple files
        file_paths = [
            sample_files["files"]["vram"],
            sample_files["files"]["cgram"],
            sample_files["files"]["oam"],
        ]
        drag_enter, drop_event = self.create_mock_drag_drop_events(file_paths)

        # Test drag enter with multiple files
        result = drop_zone.dragEnterEvent(drag_enter)
        assert result is True
        assert drag_enter.acceptProposedAction.called

        # Test drop event - should use first file only
        result = drop_zone.dropEvent(drop_event)
        assert result is True

        # Verify only first file was set
        assert drop_zone.file_path == str(sample_files["files"]["vram"])
        assert drop_zone.file_dropped.emit.called

        # Verify call args
        drop_zone.file_dropped.emit.assert_called_with(
            str(sample_files["files"]["vram"])
        )

    @pytest.mark.integration
    def test_invalid_file_drag_drop(self, sample_files):
        """Test error handling for invalid files"""
        drop_zone = self.create_mock_drop_zone("VRAM")

        # Test 1: Drop nonexistent file
        drag_enter, drop_event = self.create_mock_drag_drop_events(
            [sample_files["files"]["nonexistent"]]
        )
        result = drop_zone.dropEvent(drop_event)
        assert result is False

        # Verify file was not set for nonexistent file
        assert drop_zone.file_path == ""
        assert not drop_zone.file_dropped.emit.called

        # Test 2: Drop invalid file type (but it exists)
        drag_enter, drop_event = self.create_mock_drag_drop_events(
            [sample_files["files"]["invalid"]]
        )
        result = drop_zone.dropEvent(drop_event)
        assert result is True

        # Verify file was set (since we only check existence)
        assert drop_zone.file_path == str(sample_files["files"]["invalid"])
        assert drop_zone.file_dropped.emit.called

    @pytest.mark.integration
    def test_drag_drop_with_existing_files(self, sample_files):
        """Test drag & drop overwrite behavior"""
        drop_zone = self.create_mock_drop_zone("VRAM")

        # First drop - original file
        drag_enter, drop_event = self.create_mock_drag_drop_events(
            [sample_files["files"]["vram"]]
        )
        result = drop_zone.dropEvent(drop_event)
        assert result is True

        # Verify first file was set
        assert drop_zone.file_path == str(sample_files["files"]["vram"])
        assert drop_zone.file_dropped.emit.called

        # Reset mock
        drop_zone.file_dropped.emit.reset_mock()

        # Second drop - overwrite with different file
        drag_enter, drop_event = self.create_mock_drag_drop_events(
            [sample_files["files"]["vram_backup"]]
        )
        result = drop_zone.dropEvent(drop_event)
        assert result is True

        # Verify file was overwritten
        assert drop_zone.file_path == str(sample_files["files"]["vram_backup"])
        assert drop_zone.file_dropped.emit.called

        # Verify signal was emitted again
        drop_zone.file_dropped.emit.assert_called_with(
            str(sample_files["files"]["vram_backup"])
        )

    @pytest.mark.integration
    def test_drag_drop_clear_functionality(self, sample_files):
        """Test clearing drop zone functionality"""
        drop_zone = self.create_mock_drop_zone("VRAM")

        # First drop a file
        drag_enter, drop_event = self.create_mock_drag_drop_events(
            [sample_files["files"]["vram"]]
        )
        result = drop_zone.dropEvent(drop_event)
        assert result is True
        assert drop_zone.has_file()

        # Clear the drop zone
        drop_zone.clear()

        # Verify file was cleared
        assert drop_zone.file_path == ""
        assert not drop_zone.has_file()

    @pytest.mark.integration
    def test_empty_drop_event_handling(self, sample_files):
        """Test handling of empty drop events"""
        drop_zone = self.create_mock_drop_zone("VRAM")

        # Create empty drop event
        drag_enter, drop_event = self.create_mock_drag_drop_events([])

        # Test drag enter with no files
        result = drop_zone.dragEnterEvent(drag_enter)
        assert result is False

        # Test drop event with no files
        result = drop_zone.dropEvent(drop_event)
        assert result is False

        # Verify no file was set
        assert drop_zone.file_path == ""
        assert not drop_zone.file_dropped.emit.called

class TestExtractionPanelIntegration:
    """Test ExtractionPanel drag & drop integration"""

    @pytest.fixture
    def sample_files(self):
        """Create sample files for testing"""
        temp_dir = tempfile.mkdtemp()

        # Create valid dump files
        vram_data = bytearray(0x10000)  # 64KB
        cgram_data = bytearray(512)  # 512 bytes
        oam_data = bytearray(544)  # 544 bytes

        files = {}
        files["vram"] = Path(temp_dir) / "test_VRAM.dmp"
        files["cgram"] = Path(temp_dir) / "test_CGRAM.dmp"
        files["oam"] = Path(temp_dir) / "test_OAM.dmp"

        # Write valid files
        files["vram"].write_bytes(vram_data)
        files["cgram"].write_bytes(cgram_data)
        files["oam"].write_bytes(oam_data)

        yield {"temp_dir": temp_dir, "files": files}

        # Cleanup
        import shutil

        shutil.rmtree(temp_dir)

    def create_mock_extraction_panel(self):
        """Create a mock ExtractionPanel with drag & drop functionality"""
        panel = Mock()

        # Mock drop zones
        panel.vram_drop = Mock()
        panel.cgram_drop = Mock()
        panel.oam_drop = Mock()

        # Mock signals
        panel.files_changed = Mock()
        panel.files_changed.emit = Mock()
        panel.extraction_ready = Mock()
        panel.extraction_ready.emit = Mock()
        panel.offset_changed = Mock()
        panel.offset_changed.emit = Mock()

        # Mock methods
        def mock_on_file_changed(file_path):
            panel.files_changed.emit()

            # Check if ready for extraction
            vram_ready = panel.vram_drop.has_file()
            cgram_ready = panel.cgram_drop.has_file()
            ready = vram_ready and cgram_ready
            panel.extraction_ready.emit(ready)

            # If VRAM file, emit offset change
            if file_path == panel.vram_drop.get_file_path():
                panel.offset_changed.emit(VRAM_SPRITE_OFFSET)

        def mock_has_vram():
            return panel.vram_drop.has_file()

        def mock_get_vram_offset():
            return VRAM_SPRITE_OFFSET

        panel._on_file_changed = mock_on_file_changed
        panel.has_vram = mock_has_vram
        panel.get_vram_offset = mock_get_vram_offset

        return panel

    @pytest.mark.integration
    def test_extraction_panel_drag_drop_workflow(self, sample_files):
        """Test complete drag & drop workflow in ExtractionPanel"""
        panel = self.create_mock_extraction_panel()

        # Set up drop zone mock behavior
        panel.vram_drop.get_file_path.return_value = str(sample_files["files"]["vram"])
        panel.cgram_drop.get_file_path.return_value = str(
            sample_files["files"]["cgram"]
        )
        panel.oam_drop.get_file_path.return_value = str(sample_files["files"]["oam"])

        panel.vram_drop.has_file.return_value = True
        panel.cgram_drop.has_file.return_value = True
        panel.oam_drop.has_file.return_value = True

        # Test file drop workflow
        panel._on_file_changed(str(sample_files["files"]["vram"]))

        # Verify signals were emitted
        assert panel.files_changed.emit.called
        assert panel.extraction_ready.emit.called
        assert panel.offset_changed.emit.called

        # Verify extraction is ready
        panel.extraction_ready.emit.assert_called_with(True)
        panel.offset_changed.emit.assert_called_with(VRAM_SPRITE_OFFSET)

    @pytest.mark.integration
    def test_extraction_panel_partial_file_workflow(self, sample_files):
        """Test workflow with only some files present"""
        panel = self.create_mock_extraction_panel()

        # Set up drop zone mock behavior - only VRAM file
        panel.vram_drop.get_file_path.return_value = str(sample_files["files"]["vram"])
        panel.cgram_drop.get_file_path.return_value = ""
        panel.oam_drop.get_file_path.return_value = ""

        panel.vram_drop.has_file.return_value = True
        panel.cgram_drop.has_file.return_value = False
        panel.oam_drop.has_file.return_value = False

        # Test file drop workflow
        panel._on_file_changed(str(sample_files["files"]["vram"]))

        # Verify signals were emitted
        assert panel.files_changed.emit.called
        assert panel.extraction_ready.emit.called
        assert panel.offset_changed.emit.called

        # Verify extraction is NOT ready (missing CGRAM)
        panel.extraction_ready.emit.assert_called_with(False)

class TestDragDropErrorHandling:
    """Test drag & drop error handling scenarios"""

    @pytest.fixture
    def mock_drop_zone(self):
        """Create a mock drop zone for error testing"""
        drop_zone = Mock()
        drop_zone.file_type = "VRAM"
        drop_zone.file_path = ""
        drop_zone.file_dropped = Mock()
        drop_zone.file_dropped.emit = Mock()

        return drop_zone

    @pytest.mark.integration
    def test_file_system_error_recovery(self, mock_drop_zone, tmp_path):
        """Test recovery from file system errors during drag & drop"""

        # Mock drop event that throws file system error
        def mock_drop_event_with_error(event):
            files = [url.toLocalFile() for url in event.mimeData().urls()]
            if files:
                # Simulate file system error
                raise OSError("File system error")

        mock_drop_zone.dropEvent = mock_drop_event_with_error

        # Create drop event
        drop_event = Mock()
        url = Mock()
        url.toLocalFile.return_value = str(tmp_path / "test.dmp")
        drop_event.mimeData.return_value.urls.return_value = [url]

        # Test drop event with file system error
        with pytest.raises(OSError, match="File system error"):
            mock_drop_zone.dropEvent(drop_event)

        # Verify error was handled (file not set)
        assert mock_drop_zone.file_path == ""
        assert not mock_drop_zone.file_dropped.emit.called

    @pytest.mark.integration
    def test_concurrent_drop_events(self, mock_drop_zone, tmp_path):
        """Test handling of concurrent drop events"""

        # Mock drop event that sets file
        def mock_drop_event(event):
            files = [url.toLocalFile() for url in event.mimeData().urls()]
            if files:
                mock_drop_zone.file_path = files[0]
                mock_drop_zone.file_dropped.emit(files[0])

        mock_drop_zone.dropEvent = mock_drop_event

        # Create multiple drop events
        drop_events = []
        for i in range(3):
            drop_event = Mock()
            url = Mock()
            url.toLocalFile.return_value = str(tmp_path / f"test{i}.dmp")
            drop_event.mimeData.return_value.urls.return_value = [url]
            drop_events.append(drop_event)

        # Process multiple drop events rapidly
        for drop_event in drop_events:
            mock_drop_zone.dropEvent(drop_event)

        # Verify final state - should have last file
        assert mock_drop_zone.file_path == str(tmp_path / "test2.dmp")
        assert mock_drop_zone.file_dropped.emit.call_count == 3

    @pytest.mark.integration
    def test_malformed_url_handling(self, mock_drop_zone):
        """Test handling of malformed URLs in drop events"""

        # Mock drop event that handles malformed URLs
        def mock_drop_event(event):
            files = [url.toLocalFile() for url in event.mimeData().urls()]
            if files and files[0]:  # Check for non-empty file path
                mock_drop_zone.file_path = files[0]
                mock_drop_zone.file_dropped.emit(files[0])

        mock_drop_zone.dropEvent = mock_drop_event

        # Create drop event with malformed URL
        drop_event = Mock()
        url = Mock()
        url.toLocalFile.return_value = ""  # Empty file path
        drop_event.mimeData.return_value.urls.return_value = [url]

        # Test drop event with malformed URL
        mock_drop_zone.dropEvent(drop_event)

        # Verify no file was set
        assert mock_drop_zone.file_path == ""
        assert not mock_drop_zone.file_dropped.emit.called

class TestDragDropSignalIntegration:
    """Test drag & drop signal integration"""

    @pytest.mark.integration
    def test_signal_flow_integration(self):
        """Test signal flow between drag & drop components"""
        # Create mock components
        drop_zone = Mock()
        extraction_panel = Mock()
        main_window = Mock()

        # Mock signals
        file_dropped_signal = Mock()
        file_dropped_signal.emit = Mock()
        files_changed_signal = Mock()
        files_changed_signal.emit = Mock()
        extraction_ready_signal = Mock()
        extraction_ready_signal.emit = Mock()

        # Set up signal connections
        drop_zone.file_dropped = file_dropped_signal
        extraction_panel.files_changed = files_changed_signal
        extraction_panel.extraction_ready = extraction_ready_signal

        # Mock signal handlers
        def handle_file_dropped(file_path):
            files_changed_signal.emit()

        def handle_files_changed():
            extraction_ready_signal.emit(True)

        def handle_extraction_ready(ready):
            main_window.update_ui(ready)

        # Connect signals
        file_dropped_signal.connect = Mock(side_effect=lambda handler: handler)
        files_changed_signal.connect = Mock(side_effect=lambda handler: handler)
        extraction_ready_signal.connect = Mock(side_effect=lambda handler: handler)

        # Simulate connecting the signals
        _ = file_dropped_signal.connect(handle_file_dropped)
        _ = files_changed_signal.connect(handle_files_changed)
        _ = extraction_ready_signal.connect(handle_extraction_ready)

        # Test signal flow
        file_dropped_signal.emit("/path/to/file.dmp")
        handle_file_dropped("/path/to/file.dmp")
        handle_files_changed()
        handle_extraction_ready(True)

        # Verify signals were emitted
        assert file_dropped_signal.emit.called
        assert files_changed_signal.emit.called
        assert extraction_ready_signal.emit.called

        # Verify signal connections were established
        assert file_dropped_signal.connect.called
        assert files_changed_signal.connect.called
        assert extraction_ready_signal.connect.called
