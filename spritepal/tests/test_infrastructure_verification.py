"""
Comprehensive infrastructure verification tests.
Run this to verify all fixes are properly applied.
"""
import pytest

from core.di_container import inject
from core.managers.core_operations_manager import CoreOperationsManager


def get_extraction_manager():
    """Get extraction manager via DI."""
    return inject(CoreOperationsManager)

# Serial execution required: QApplication management, HAL process pool
pytestmark = [
    pytest.mark.performance,
    pytest.mark.usefixtures("session_managers"),
    pytest.mark.shared_state_safe,
    pytest.mark.skip_thread_cleanup(reason="Uses session_managers which owns worker threads"),
]

class TestInfrastructureVerification:

    def test_circular_import_fixed(self):
        """Verify circular import is resolved"""
        try:
            # These imports should work without hanging
            from ui.extraction_controller import ExtractionController
            from ui.main_window import MainWindow

            # Should be able to reference each other through protocols
            assert MainWindow is not None
            assert ExtractionController is not None
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

    def test_performance_benchmark(self, session_managers):
        """Benchmark to ensure acceptable performance"""
        import time

        times = []

        # Run multiple iterations
        for i in range(3):
            start = time.time()
            # Access manager (should be fast with session fixture)
            get_extraction_manager()
            elapsed = time.time() - start
            times.append(elapsed)

        avg_time = sum(times) / len(times)

        # Should be very fast after first access
        assert avg_time < 0.1, f"Manager access too slow: {avg_time:.2f}s"
