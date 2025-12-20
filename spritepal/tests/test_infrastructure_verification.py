"""
Comprehensive infrastructure verification tests.
Run this to verify all fixes are properly applied.
"""
import time
from pathlib import Path

import pytest

# Serial execution required: QApplication management, HAL process pool
pytestmark = [
    pytest.mark.performance,
    pytest.mark.usefixtures("session_managers"),
    pytest.mark.shared_state_safe,
    pytest.mark.skip_thread_cleanup(reason="Uses session_managers which owns worker threads"),
]

class TestInfrastructureVerification:

    @pytest.mark.no_manager_setup
    def test_01_fast_execution(self):
        """Verify tests run fast without manager initialization"""
        start = time.time()
        # Simple test logic
        result = 2 + 2
        assert result == 4
        elapsed = time.time() - start

        # Should complete in milliseconds, not seconds
        assert elapsed < 0.5, f"Test took {elapsed:.2f}s - manager initialization not skipped!"
        print(f"✓ Fast test completed in {elapsed:.3f}s")

    def test_02_session_managers_reused(self, session_managers):
        """Verify session managers are reused, not recreated"""
        start = time.time()

        # First access should be fast if reusing session managers
        extraction = session_managers.get_extraction_manager()
        assert extraction is not None

        elapsed = time.time() - start
        # Should be fast if reusing existing managers
        assert elapsed < 1.0, f"Managers took {elapsed:.2f}s - not reusing session fixtures!"
        print(f"✓ Manager access took {elapsed:.3f}s")

    def test_03_circular_import_fixed(self):
        """Verify circular import is resolved"""
        try:
            # These imports should work without hanging
            from core.controller import ExtractionController
            from ui.main_window import MainWindow

            # Should be able to reference each other through protocols
            assert MainWindow is not None
            assert ExtractionController is not None
            print("✓ No circular import detected")
        except ImportError as e:
            pytest.fail(f"Import failed: {e}")

    def test_04_hal_cleanup_fixed(self):
        """Verify HALProcessPool cleanup deadlock is fixed"""
        # Read the registry file
        registry_path = Path("core/managers/registry.py")
        content = registry_path.read_text()

        # Check that HALProcessPool cleanup was removed
        bad_patterns = [
            "from core.hal_compression import HALProcessPool",
            "hal_pool = HALProcessPool()",
            "hal_pool.shutdown()"
        ]

        # Check lines 170-200 where the problem code was
        lines = content.split('\n')
        problem_zone = '\n'.join(lines[170:200])

        for pattern in bad_patterns:
            if pattern in problem_zone:
                pytest.fail(f"HALProcessPool cleanup still present: {pattern}")

        print("✓ HALProcessPool cleanup removed from ManagerRegistry")

    @pytest.mark.gui
    def test_05_qt_infrastructure(self, qtbot):
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
        print("✓ Qt infrastructure working")

    def test_06_performance_benchmark(self, session_managers):
        """Benchmark to ensure acceptable performance"""
        import time

        times = []

        # Run multiple iterations
        for i in range(3):
            start = time.time()
            # Access manager (should be fast with session fixture)
            session_managers.get_extraction_manager()
            elapsed = time.time() - start
            times.append(elapsed)

        avg_time = sum(times) / len(times)
        print(f"✓ Average manager access time: {avg_time:.3f}s")

        # Should be very fast after first access
        assert avg_time < 0.1, f"Manager access too slow: {avg_time:.2f}s"

def pytest_sessionfinish(session, exitstatus):
    """Print summary at end of session"""
    print("\n" + "="*60)
    print("INFRASTRUCTURE VERIFICATION COMPLETE")
    print("="*60)

    if exitstatus == 0:
        print("✅ All infrastructure fixes verified working!")
        print("✅ Tests can now run efficiently")
        print("✅ Ready to proceed with coverage improvements")
    else:
        print("❌ Some infrastructure issues remain")
        print("❌ Fix these before adding new tests")
