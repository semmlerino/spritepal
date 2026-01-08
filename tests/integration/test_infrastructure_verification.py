"""
Comprehensive infrastructure verification tests.
Run this to verify all fixes are properly applied.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from core.app_context import AppContext

# Serial execution required: QApplication management, HAL process pool
pytestmark = [
    pytest.mark.performance,
    pytest.mark.usefixtures("session_app_context"),
    pytest.mark.shared_state_safe,
    pytest.mark.skip_thread_cleanup(reason="Uses session_app_context which owns worker threads"),
]


class TestInfrastructureVerification:
    def test_main_window_import_doesnt_hang(self):
        """Verify MainWindow imports without circular dependency issues.

        Note: ExtractionController was removed in Phase 4e. MainWindow now handles
        extraction directly, eliminating the circular dependency.
        """
        try:
            # This import should work without hanging
            from ui.main_window import MainWindow

            # Should be importable
            assert MainWindow is not None
        except ImportError as e:
            pytest.fail(f"Import failed: {e}")

    @pytest.mark.gui
    def test_qt_infrastructure(self, qtbot):
        """Verify Qt test infrastructure works"""
        from PySide6.QtWidgets import QApplication, QWidget

        # Should have single QApplication
        app = QApplication.instance()
        assert app is not None, "No QApplication instance"

        # Create widget with qtbot
        widget = QWidget()
        qtbot.addWidget(widget)

        # Should be properly managed
        assert widget is not None

    def test_performance_benchmark(self, session_app_context: AppContext):
        """Benchmark to ensure acceptable performance"""
        import time

        times = []

        # Run multiple iterations
        for i in range(3):
            start = time.time()
            # Access manager (should be fast with session fixture)
            _ = session_app_context.core_operations_manager
            elapsed = time.time() - start
            times.append(elapsed)

        avg_time = sum(times) / len(times)

        # Should be very fast after first access
        assert avg_time < 0.1, f"Manager access too slow: {avg_time:.2f}s"
