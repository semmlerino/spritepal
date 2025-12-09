"""
Unit tests for specialized worker base classes.

Tests the ExtractionWorkerBase, InjectionWorkerBase, ScanWorkerBase,
and PreviewWorkerBase classes for proper specialized signal handling.
"""
from __future__ import annotations

from unittest.mock import Mock

import pytest
from PySide6.QtTest import QSignalSpy

from core.managers.base_manager import BaseManager
from core.workers.specialized import (
    ExtractionWorkerBase,
    InjectionWorkerBase,
    PreviewWorkerBase,
    ScanWorkerBase,
)

# Serial execution required: QApplication management, Thread safety concerns
pytestmark = [
    pytest.mark.serial,
    pytest.mark.qt_application,
    pytest.mark.thread_safety,
    pytest.mark.cache,
    pytest.mark.gui,
    pytest.mark.requires_display,
    pytest.mark.signals_slots,
]

class TestExtractionWorkerBase:
    """Test the ExtractionWorkerBase specialized class."""

    def test_extraction_worker_initialization(self, qtbot):
        """Test extraction worker initialization with manager."""

        class TestExtractionWorker(ExtractionWorkerBase):
            def perform_operation(self):
                pass

        manager = Mock(spec=BaseManager)
        worker = TestExtractionWorker(manager)
        qtbot.addWidget(worker)

        assert worker.manager is manager
        assert worker._operation_name == "ExtractionWorker"

    def test_extraction_specific_signals(self, qtbot):
        """Test extraction-specific signal definitions."""

        class TestExtractionWorker(ExtractionWorkerBase):
            def perform_operation(self):
                pass

        manager = Mock(spec=BaseManager)
        worker = TestExtractionWorker(manager)
        qtbot.addWidget(worker)

        # Test all extraction-specific signals exist
        assert hasattr(worker, "preview_ready")
        assert hasattr(worker, "preview_image_ready")
        assert hasattr(worker, "palettes_ready")
        assert hasattr(worker, "active_palettes_ready")
        assert hasattr(worker, "extraction_finished")

        # Test signal emission
        preview_spy = QSignalSpy(worker.preview_ready)
        palettes_spy = QSignalSpy(worker.palettes_ready)
        extraction_spy = QSignalSpy(worker.extraction_finished)

        # Emit signals with test data - UPDATED FOR BUG #26: Workers emit PIL Image, not QPixmap
        mock_pil_image = Mock()  # Mock PIL Image instead of QPixmap for Qt threading safety
        worker.preview_ready.emit(mock_pil_image, 10)
        assert preview_spy.count() == 1
        assert preview_spy.at(0) == [mock_pil_image, 10]

        mock_palettes = {"palette1": [1, 2, 3]}
        worker.palettes_ready.emit(mock_palettes)
        assert palettes_spy.count() == 1
        assert palettes_spy.at(0) == [mock_palettes]

        mock_files = ["file1.png", "file2.pal.json"]
        worker.extraction_finished.emit(mock_files)
        assert extraction_spy.count() == 1
        assert extraction_spy.at(0) == [mock_files]

class TestInjectionWorkerBase:
    """Test the InjectionWorkerBase specialized class."""

    def test_injection_worker_initialization(self, qtbot):
        """Test injection worker initialization with manager."""

        class TestInjectionWorker(InjectionWorkerBase):
            def perform_operation(self):
                pass

        manager = Mock(spec=BaseManager)
        worker = TestInjectionWorker(manager)
        qtbot.addWidget(worker)

        assert worker.manager is manager
        assert worker._operation_name == "InjectionWorker"

    def test_injection_specific_signals(self, qtbot):
        """Test injection-specific signal definitions."""

        class TestInjectionWorker(InjectionWorkerBase):
            def perform_operation(self):
                pass

        manager = Mock(spec=BaseManager)
        worker = TestInjectionWorker(manager)
        qtbot.addWidget(worker)

        # Test all injection-specific signals exist
        assert hasattr(worker, "progress_percent")
        assert hasattr(worker, "compression_info")
        assert hasattr(worker, "injection_finished")

        # Test signal emission
        progress_spy = QSignalSpy(worker.progress_percent)
        compression_spy = QSignalSpy(worker.compression_info)
        injection_spy = QSignalSpy(worker.injection_finished)

        # Emit signals with test data
        worker.progress_percent.emit(75)
        assert progress_spy.count() == 1
        assert progress_spy.at(0) == [75]

        mock_compression = {"original_size": 1000, "compressed_size": 500}
        worker.compression_info.emit(mock_compression)
        assert compression_spy.count() == 1
        assert compression_spy.at(0) == [mock_compression]

        worker.injection_finished.emit(True, "Injection successful")
        assert injection_spy.count() == 1
        assert injection_spy.at(0) == [True, "Injection successful"]

class TestScanWorkerBase:
    """Test the ScanWorkerBase specialized class."""

    def test_scan_worker_initialization(self, qtbot):
        """Test scan worker initialization."""

        class TestScanWorker(ScanWorkerBase):
            def run(self):
                pass

        worker = TestScanWorker()
        qtbot.addWidget(worker)

        assert worker._operation_name == "ScanWorker"

    def test_scan_specific_signals(self, qtbot):
        """Test scan-specific signal definitions."""

        class TestScanWorker(ScanWorkerBase):
            def run(self):
                pass

        worker = TestScanWorker()
        qtbot.addWidget(worker)

        # Test all scan-specific signals exist
        assert hasattr(worker, "item_found")
        assert hasattr(worker, "scan_stats")
        assert hasattr(worker, "scan_progress")
        assert hasattr(worker, "scan_finished")
        assert hasattr(worker, "cache_status")
        assert hasattr(worker, "cache_progress")

        # Test signal emission
        item_spy = QSignalSpy(worker.item_found)
        stats_spy = QSignalSpy(worker.scan_stats)
        progress_spy = QSignalSpy(worker.scan_progress)
        finished_spy = QSignalSpy(worker.scan_finished)
        cache_status_spy = QSignalSpy(worker.cache_status)
        cache_progress_spy = QSignalSpy(worker.cache_progress)

        # Emit signals with test data
        mock_item = {"name": "sprite1", "offset": 0x1000}
        worker.item_found.emit(mock_item)
        assert item_spy.count() == 1
        assert item_spy.at(0) == [mock_item]

        mock_stats = {"total_found": 5, "scan_time": 2.5}
        worker.scan_stats.emit(mock_stats)
        assert stats_spy.count() == 1
        assert stats_spy.at(0) == [mock_stats]

        worker.scan_progress.emit(3, 10)
        assert progress_spy.count() == 1
        assert progress_spy.at(0) == [3, 10]

        worker.scan_finished.emit(True)
        assert finished_spy.count() == 1
        assert finished_spy.at(0) == [True]

        worker.cache_status.emit("Loading from cache...")
        assert cache_status_spy.count() == 1
        assert cache_status_spy.at(0) == ["Loading from cache..."]

        worker.cache_progress.emit(50)
        assert cache_progress_spy.count() == 1
        assert cache_progress_spy.at(0) == [50]

    def test_scan_helper_methods(self, qtbot):
        """Test scan worker helper methods."""

        class TestScanWorker(ScanWorkerBase):
            def run(self):
                pass

        worker = TestScanWorker()
        qtbot.addWidget(worker)

        item_spy = QSignalSpy(worker.item_found)
        progress_spy = QSignalSpy(worker.scan_progress)
        standard_progress_spy = QSignalSpy(worker.progress)

        # Test emit_item_found
        test_item = {"sprite": "test", "size": 100}
        worker.emit_item_found(test_item)
        assert item_spy.count() == 1
        assert item_spy.at(0) == [test_item]

        # Test emit_scan_progress
        worker.emit_scan_progress(5, 20)
        assert progress_spy.count() == 1
        assert progress_spy.at(0) == [5, 20]

        # Should also emit standard progress percentage
        assert standard_progress_spy.count() == 1
        assert standard_progress_spy.at(0) == [25, "Scanning 5/20"]  # 5/20 * 100 = 25%

    def test_scan_progress_edge_cases(self, qtbot):
        """Test scan progress with edge cases."""

        class TestScanWorker(ScanWorkerBase):
            def run(self):
                pass

        worker = TestScanWorker()
        qtbot.addWidget(worker)

        standard_progress_spy = QSignalSpy(worker.progress)

        # Test with zero total (should not crash)
        worker.emit_scan_progress(0, 0)
        # Should not emit standard progress when total is 0
        assert standard_progress_spy.count() == 0

        # Test with current > total
        worker.emit_scan_progress(15, 10)
        assert standard_progress_spy.count() == 1
        assert standard_progress_spy.at(0) == [100, "Scanning 15/10"]  # Should cap at 100%

class TestPreviewWorkerBase:
    """Test the PreviewWorkerBase specialized class."""

    def test_preview_worker_initialization(self, qtbot):
        """Test preview worker initialization."""

        class TestPreviewWorker(PreviewWorkerBase):
            def run(self):
                pass

        worker = TestPreviewWorker()
        qtbot.addWidget(worker)

        assert worker._operation_name == "PreviewWorker"

    def test_preview_specific_signals(self, qtbot):
        """Test preview-specific signal definitions."""

        class TestPreviewWorker(PreviewWorkerBase):
            def run(self):
                pass

        worker = TestPreviewWorker()
        qtbot.addWidget(worker)

        # Test all preview-specific signals exist
        assert hasattr(worker, "preview_ready")
        assert hasattr(worker, "preview_failed")

        # Test signal emission
        ready_spy = QSignalSpy(worker.preview_ready)
        failed_spy = QSignalSpy(worker.preview_failed)

        # Emit signals with test data - UPDATED FOR BUG #26: Workers emit PIL Image, not QPixmap
        mock_preview = Mock()  # Mock PIL Image for Qt threading safety
        worker.preview_ready.emit(mock_preview)
        assert ready_spy.count() == 1
        assert ready_spy.at(0) == [mock_preview]

        worker.preview_failed.emit("Preview generation failed")
        assert failed_spy.count() == 1
        assert failed_spy.at(0) == ["Preview generation failed"]

    def test_preview_helper_methods(self, qtbot):
        """Test preview worker helper methods."""

        class TestPreviewWorker(PreviewWorkerBase):
            def run(self):
                pass

        worker = TestPreviewWorker()
        qtbot.addWidget(worker)

        ready_spy = QSignalSpy(worker.preview_ready)
        failed_spy = QSignalSpy(worker.preview_failed)
        error_spy = QSignalSpy(worker.error)

        # Test emit_preview_ready - UPDATED FOR BUG #26: Workers emit PIL Image, not QPixmap
        mock_preview = Mock()  # Mock PIL Image for Qt threading safety
        worker.emit_preview_ready(mock_preview)
        assert ready_spy.count() == 1
        assert ready_spy.at(0) == [mock_preview]

        # Test emit_preview_failed
        worker.emit_preview_failed("Test error")
        assert failed_spy.count() == 1
        assert failed_spy.at(0) == ["Test error"]

        # Should also emit standard error signal
        assert error_spy.count() == 1
        assert error_spy.at(0)[0] == "Test error"

@pytest.fixture
def qtbot():
    """Provide qtbot for Qt testing."""
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance()
    if app is None:
        app = QApplication([])

    class QtBot:
        def addWidget(self, widget):
            pass

    return QtBot()
