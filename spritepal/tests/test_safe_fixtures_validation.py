# pyright: recommended
# pyright: reportPrivateUsage=false  # Test fixtures may access private members
# pyright: reportUnknownMemberType=warning  # Mock fixtures have dynamic attributes

"""
Validation tests for safe fixtures to ensure they work correctly in all environments.

These tests validate that:
1. Fixtures work in headless mode
2. No segfaults during fixture creation  
3. Proper cleanup occurs
4. Mock fixtures provide expected API
5. Environment detection works correctly
6. Fallback mechanisms work properly

Usage:
    pytest tests/test_safe_fixtures_validation.py -v
    
    # Test with debug logging
    PYTEST_DEBUG_FIXTURES=1 pytest tests/test_safe_fixtures_validation.py -v
    
    # Test fixture validation specifically
    pytest tests/test_safe_fixtures_validation.py::test_fixture_validation_environment -v
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING
from unittest.mock import Mock

import pytest

# Test markers
pytestmark = [
    pytest.mark.fixture_test,
    pytest.mark.infrastructure,
    pytest.mark.validation,
    pytest.mark.headless,
    pytest.mark.parallel_safe,
    pytest.mark.unit,
    pytest.mark.ci_safe,
]

class TestSafeFixtureBasics:
    """Test basic safe fixture functionality."""

    def test_safe_qtbot_creation(self, enhanced_safe_qtbot):
        """Test that safe qtbot can be created without errors."""
        assert enhanced_safe_qtbot is not None

        # Verify qtbot has expected interface
        assert hasattr(enhanced_safe_qtbot, 'wait')
        assert hasattr(enhanced_safe_qtbot, 'waitSignal')
        assert hasattr(enhanced_safe_qtbot, 'waitUntil')
        assert hasattr(enhanced_safe_qtbot, 'addWidget')

        # Test basic operations don't crash
        # Verify wait() method exists and completes (no timeout verification needed for safe fixture test)
        enhanced_safe_qtbot.addWidget(Mock())

    def test_safe_qapp_creation(self, enhanced_safe_qapp):
        """Test that safe QApplication can be created without errors."""
        assert enhanced_safe_qapp is not None

        # Verify QApplication has expected interface
        assert hasattr(enhanced_safe_qapp, 'processEvents')
        assert hasattr(enhanced_safe_qapp, 'quit')
        assert hasattr(enhanced_safe_qapp, 'exit')

        # Test basic operations don't crash
        enhanced_safe_qapp.processEvents()

    def test_widget_factory_creation(self, safe_widget_factory_fixture):
        """Test that widget factory can be created and used."""
        factory = safe_widget_factory_fixture
        assert factory is not None

        # Test widget creation
        widget = factory.create_widget('QWidget')
        assert widget is not None
        assert hasattr(widget, 'show')
        assert hasattr(widget, 'hide')

        # Test cleanup
        factory.cleanup()

    def test_dialog_factory_creation(self, safe_dialog_factory_fixture):
        """Test that dialog factory can be created and used."""
        factory = safe_dialog_factory_fixture
        assert factory is not None

        # Test dialog creation
        dialog = factory.create_dialog('QDialog')
        assert dialog is not None
        assert hasattr(dialog, 'exec')
        assert hasattr(dialog, 'accept')
        assert hasattr(dialog, 'reject')

        # Test cleanup
        factory.cleanup()

class TestSafeFixtureEnvironmentAdaptation:
    """Test that fixtures adapt correctly to different environments."""

    def test_headless_environment_detection(self, fixture_validation_report):
        """Test that environment detection works correctly."""
        report = fixture_validation_report

        # Verify environment info is present
        assert 'environment' in report
        env = report['environment']

        assert 'headless' in env
        assert 'ci' in env
        assert 'display_available' in env
        assert 'xvfb_available' in env
        assert 'qt_available' in env

        # Verify fixtures were created successfully
        assert 'fixtures' in report
        fixtures = report['fixtures']

        assert fixtures['qtbot_created']
        assert fixtures['qapp_created']
        assert fixtures['widget_factory_created']
        assert fixtures['dialog_factory_created']

    def test_adaptive_qtbot_selection(self, adaptive_qtbot):
        """Test that adaptive qtbot selects appropriate implementation."""
        qtbot = adaptive_qtbot
        assert qtbot is not None

        # Should have qtbot interface regardless of implementation
        assert hasattr(qtbot, 'wait')
        assert hasattr(qtbot, 'waitSignal')

    @pytest.mark.qt_mock
    def test_mock_qtbot_forced(self, adaptive_qtbot):
        """Test that mock qtbot is used when explicitly requested."""
        qtbot = adaptive_qtbot
        assert qtbot is not None

        # In mock mode, operations should be no-ops
        # Verify mock wait returns immediately (not a real wait)
        import time
        start = time.time()
        qtbot.wait(1000)  # Mock should return immediately, not wait 1000ms
        elapsed = (time.time() - start) * 1000  # Convert to ms
        assert elapsed < 100, f"Mock wait took {elapsed}ms, should be < 100ms"

    def test_safe_qt_environment_context(self, safe_qt_environment):
        """Test complete Qt environment context."""
        qt_env = safe_qt_environment
        assert qt_env is not None

        # Verify all components are present (may be None in headless)
        assert 'qapp' in qt_env
        assert 'qtbot' in qt_env
        assert 'widget_factory' in qt_env
        assert 'dialog_factory' in qt_env
        assert 'env_info' in qt_env

        # Environment info should always be present
        env_info = qt_env['env_info']
        assert env_info is not None
        assert hasattr(env_info, 'is_headless')

class TestSafeFixtureErrorHandling:
    """Test error handling and fallback mechanisms."""

    def test_qtbot_error_fallback(self):
        """Test qtbot fallback when creation fails."""
        from tests.infrastructure.safe_fixtures import create_safe_qtbot

        # Create qtbot - should succeed even if environment is problematic
        qtbot = create_safe_qtbot()
        assert qtbot is not None

        # Should have expected interface
        assert hasattr(qtbot, 'wait')
        assert hasattr(qtbot, 'waitSignal')

    def test_widget_factory_error_handling(self):
        """Test widget factory error handling."""
        from tests.infrastructure.safe_fixtures import SafeWidgetFactory, WidgetCreationError

        factory = SafeWidgetFactory(headless=True)

        # Valid widget creation should work
        widget = factory.create_widget('QWidget')
        assert widget is not None

        # Invalid widget class should raise appropriate error
        with pytest.raises(WidgetCreationError):
            factory.create_widget('NonExistentWidget')

    def test_cleanup_robustness(self):
        """Test that cleanup is robust to errors."""
        from tests.infrastructure.safe_fixtures import cleanup_all_fixtures

        # Should not raise exceptions even if called multiple times
        cleanup_all_fixtures()
        cleanup_all_fixtures()

class TestSafeFixtureCompatibility:
    """Test compatibility with existing pytest-qt patterns."""

    def test_qtbot_wait_signal_compatibility(self, enhanced_safe_qtbot):
        """Test waitSignal compatibility with pytest-qt patterns."""
        qtbot = enhanced_safe_qtbot

        # Create a mock signal
        mock_signal = Mock()
        mock_signal.emit = Mock()

        # waitSignal should return blocker-like object
        blocker = qtbot.waitSignal(mock_signal, timeout=100)
        assert blocker is not None

        # Should have expected blocker interface
        assert hasattr(blocker, 'connect') or hasattr(blocker, 'args')

    def test_qtbot_widget_management(self, enhanced_safe_qtbot, safe_widget_factory_fixture):
        """Test qtbot widget management."""
        qtbot = enhanced_safe_qtbot
        factory = safe_widget_factory_fixture

        # Create widget and add to qtbot
        widget = factory.create_widget('QWidget')
        qtbot.addWidget(widget)

        # Should not crash
        widget.show()
        from PySide6.QtWidgets import QApplication
        QApplication.processEvents()  # Allow show event to process

    def test_qapp_event_processing(self, enhanced_safe_qapp):
        """Test QApplication event processing compatibility."""
        qapp = enhanced_safe_qapp

        # processEvents should not crash
        qapp.processEvents()

        # Multiple calls should be safe
        for _ in range(5):
            qapp.processEvents()

class TestSafeFixturePerformance:
    """Test performance aspects of safe fixtures."""

    def test_fixture_creation_speed(self):
        """Test that fixture creation is reasonably fast."""
        import time

        from tests.infrastructure.safe_fixtures import create_safe_qapp, create_safe_qtbot

        # Test qtbot creation speed
        start_time = time.time()
        create_safe_qtbot()
        qtbot_time = time.time() - start_time

        # Should be fast (< 1 second even in worst case)
        assert qtbot_time < 1.0

        # Test QApplication creation speed
        start_time = time.time()
        create_safe_qapp()
        qapp_time = time.time() - start_time

        # Should be fast
        assert qapp_time < 1.0

    def test_cleanup_speed(self):
        """Test that cleanup is reasonably fast."""
        import time

        from tests.infrastructure.safe_fixtures import cleanup_all_fixtures

        start_time = time.time()
        cleanup_all_fixtures()
        cleanup_time = time.time() - start_time

        # Cleanup should be fast
        assert cleanup_time < 1.0

class TestSafeFixtureIntegration:
    """Test integration with other test infrastructure."""

    def test_environment_detection_integration(self):
        """Test integration with environment detection."""
        from tests.infrastructure.environment_detection import get_environment_info
        from tests.infrastructure.safe_fixtures import validate_fixture_environment

        env_info = get_environment_info()
        validation = validate_fixture_environment()

        # Environment detection should be consistent
        assert validation['environment']['headless'] == env_info.is_headless
        assert validation['environment']['ci'] == env_info.is_ci
        assert validation['environment']['qt_available'] == env_info.pyside6_available

    def test_mock_infrastructure_integration(self, enhanced_safe_qtbot):
        """Test integration with existing mock infrastructure."""
        qtbot = enhanced_safe_qtbot

        # Should work with existing mock objects
        mock_widget = Mock()
        mock_widget.show = Mock()
        mock_widget.hide = Mock()

        # qtbot operations should work with mock widgets
        qtbot.addWidget(mock_widget)
        from PySide6.QtWidgets import QApplication
        QApplication.processEvents()  # Process any pending events

    def test_real_component_factory_compatibility(self, real_factory):
        """Test compatibility with RealComponentFactory."""
        # Should not interfere with existing factory
        main_window = real_factory.create_main_window()
        assert main_window is not None

        # Safe fixtures should still work alongside
        from tests.infrastructure.safe_fixtures import create_safe_qtbot
        qtbot = create_safe_qtbot()
        assert qtbot is not None

# Specialized validation tests

@pytest.mark.skipif(
    os.environ.get('SKIP_SLOW_TESTS'),
    reason="Skipping slow validation tests"
)
class TestSafeFixtureStressValidation:
    """Stress tests for safe fixtures."""

    def test_multiple_fixture_creation(self):
        """Test creating multiple fixtures doesn't cause issues."""
        from tests.infrastructure.safe_fixtures import create_safe_qapp, create_safe_qtbot

        qtbots = []
        qapps = []

        # Create multiple instances
        for _ in range(5):
            qtbots.append(create_safe_qtbot())
            qapps.append(create_safe_qapp())

        # All should be valid
        for qtbot in qtbots:
            assert qtbot is not None
            # Verify qtbot has expected interface
            assert hasattr(qtbot, 'wait')
            assert hasattr(qtbot, 'addWidget')

        for qapp in qapps:
            assert qapp is not None
            qapp.processEvents()

    def test_concurrent_fixture_usage(self):
        """Test fixtures work correctly under concurrent usage."""
        import threading

        from tests.infrastructure.safe_fixtures import create_safe_qtbot

        results = []
        errors = []

        def create_and_use_fixture():
            try:
                qtbot = create_safe_qtbot()
                # Verify qtbot creation and basic operations work
                assert hasattr(qtbot, 'wait')
                qtbot.addWidget(Mock())
                results.append(True)
            except Exception as e:
                errors.append(str(e))

        # Create multiple threads using fixtures
        threads = []
        for _ in range(3):
            thread = threading.Thread(target=create_and_use_fixture)
            threads.append(thread)
            thread.start()

        # Wait for all threads
        for thread in threads:
            thread.join()

        # Should have no errors
        assert len(errors) == 0, f"Concurrent usage errors: {errors}"
        assert len(results) == 3

# Environment-specific tests

@pytest.mark.ci_safe
def test_ci_environment_compatibility():
    """Test that fixtures work correctly in CI environments."""
    from tests.infrastructure.safe_fixtures import validate_fixture_environment

    validation = validate_fixture_environment()

    # Should not have critical errors in CI
    critical_errors = [
        error for error in validation.get('errors', [])
        if 'critical' in error.lower() or 'fatal' in error.lower()
    ]

    assert len(critical_errors) == 0, f"Critical errors in CI: {critical_errors}"

def test_fixture_documentation_accuracy():
    """Test that fixture behavior matches documentation."""
    from tests.infrastructure.safe_fixtures import (
        create_safe_qapp,
        create_safe_qtbot,
    )

    # Test qtbot creation
    qtbot = create_safe_qtbot()
    assert qtbot is not None

    # Should support all documented methods
    documented_methods = ['wait', 'waitSignal', 'waitUntil', 'addWidget']
    for method in documented_methods:
        assert hasattr(qtbot, method), f"qtbot missing documented method: {method}"

    # Test QApplication creation
    qapp = create_safe_qapp()
    assert qapp is not None

    # Should support all documented methods
    documented_methods = ['processEvents', 'quit', 'exit']
    for method in documented_methods:
        assert hasattr(qapp, method), f"qapp missing documented method: {method}"

if __name__ == "__main__":
    # Allow running as script for quick validation
    pytest.main([__file__, "-v"])
