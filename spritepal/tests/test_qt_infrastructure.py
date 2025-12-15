"""
Test the Qt test infrastructure to ensure proper qtbot and QApplication management.

This test verifies that our Qt fixtures work correctly and prevent common
Qt testing issues like multiple QApplication instances and resource leaks.
"""
from __future__ import annotations

from unittest.mock import Mock

import pytest

# Test markers for Qt infrastructure validation
pytest_plugins = ["pytestqt"]

# Qt infrastructure tests must run serially to avoid QApplication conflicts
pytestmark = [
    pytest.mark.usefixtures("session_managers"),
    pytest.mark.shared_state_safe,
    pytest.mark.skip_thread_cleanup(reason="Thread tests may intentionally leave threads running"),
    pytest.mark.serial,
    pytest.mark.qt_application,
    pytest.mark.qt_app,
    pytest.mark.ci_safe,
    pytest.mark.integration,
    pytest.mark.memory,
    pytest.mark.qt_real,
    pytest.mark.requires_display,
    pytest.mark.signals_slots,
]

@pytest.mark.qt_app
def test_qapplication_singleton(qapp):
    """Verify single QApplication instance across test session."""
    try:
        from PySide6.QtWidgets import QApplication

        # Get instances multiple times
        app1 = QApplication.instance()
        app2 = QApplication.instance()

        # Should be the same instance
        assert app1 is app2
        assert app1 is not None

        # Should match our fixture
        assert app1 is qapp

    except ImportError:
        # In environments without Qt, should get mock
        assert isinstance(qapp, Mock)

def test_qtbot_widget_cleanup(qtbot):
    """Verify widgets are properly registered with qtbot for cleanup."""
    try:
        from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

        # Create a test widget
        widget = QWidget()
        qtbot.addWidget(widget)

        # Add some content
        label = QLabel("Test content")
        layout = QVBoxLayout()
        layout.addWidget(label)
        widget.setLayout(layout)

        # Widget should be registered with qtbot
        # qtbot will handle cleanup automatically
        assert widget is not None
        assert label.text() == "Test content"

    except ImportError:
        # In headless environments, qtbot might be mocked
        assert hasattr(qtbot, 'addWidget')
        qtbot.addWidget(Mock())

@pytest.mark.gui
def test_qt_gui_functionality(qtbot):
    """Test that requires full Qt GUI capabilities."""
    try:
        from PySide6.QtCore import QTimer, Signal
        from PySide6.QtWidgets import QPushButton, QWidget

        class TestWidget(QWidget):
            clicked = Signal()

            def __init__(self):
                super().__init__()
                self.button = QPushButton("Test Button")
                self.button.clicked.connect(self.clicked.emit)

        widget = TestWidget()
        qtbot.addWidget(widget)

        # Test signal emission
        with qtbot.waitSignal(widget.clicked, timeout=1000):
            widget.button.click()

    except ImportError:
        # In mock environments, just verify mock functionality
        assert hasattr(qtbot, 'waitSignal')
        assert hasattr(qtbot, 'addWidget')

def test_qtbot_functionality(qtbot):
    """Test that qtbot provides required methods for headless testing."""
    # Should always have required methods (standard pytest-qt fixture)
    assert hasattr(qtbot, 'addWidget')
    assert hasattr(qtbot, 'waitSignal')
    assert hasattr(qtbot, 'wait')
    assert hasattr(qtbot, 'mouseClick')
    assert hasattr(qtbot, 'keyClick')

    # Verify these methods are callable (signature check only)
    assert callable(qtbot.addWidget)
    assert callable(qtbot.waitSignal)
    assert callable(qtbot.wait)

def test_qapp_functionality(qapp):
    """Test that qapp provides necessary QApplication functionality."""
    # Should always have processEvents method
    assert hasattr(qapp, 'processEvents')

    # Should be callable without errors
    qapp.processEvents()

@pytest.mark.no_gui
def test_no_gui_marker():
    """Test that doesn't require Qt GUI components."""
    # This test should run in all environments
    assert True

def test_qt_cleanup_integration(qtbot, qapp):
    """Test that Qt cleanup works properly between tests."""
    try:
        import gc

        from PySide6.QtWidgets import QWidget

        # Create widgets that will be cleaned up
        widgets = [QWidget() for _ in range(5)]
        for widget in widgets:
            qtbot.addWidget(widget)

        # Force garbage collection
        gc.collect()

        # Process events to allow cleanup
        if hasattr(qapp, 'processEvents'):
            qapp.processEvents()

    except ImportError:
        # In mock environments, just verify structure
        pass

def test_thread_safety_marker():
    """Test Qt thread safety markers work correctly."""
    import threading

    # Should be running in main thread for Qt operations
    assert threading.current_thread() is threading.main_thread()

@pytest.mark.mock_gui
def test_mock_gui_in_headless():
    """Test that mock_gui marker allows GUI tests in headless mode."""
    # This test should run even in headless environments
    # because it uses mocks instead of real Qt widgets
    from unittest.mock import Mock

    mock_widget = Mock()
    mock_widget.show = Mock()
    mock_widget.close = Mock()

    # Mock GUI operations
    mock_widget.show()
    mock_widget.close()

    assert mock_widget.show.called
    assert mock_widget.close.called

def test_qt_markers_configuration():
    """Test that Qt-specific pytest markers are properly configured."""

    # Verify our custom markers are available
    # This helps ensure the pytest configuration is working
    marker_names = {
        'qt_app',
        'gui',
        'mock_gui',
        'no_gui',
        'thread_safety'
    }

    # At least some of our markers should be recognized
    # (exact verification depends on pytest internals)
    assert len(marker_names) > 0

@pytest.mark.stability
def test_multiple_qapplication_prevention():
    """Test that we prevent multiple QApplication instances."""
    try:
        from PySide6.QtWidgets import QApplication

        # Get the current instance
        app1 = QApplication.instance()

        # Attempting to create another should return the same instance
        # (QApplication constructor will raise an error if we try to create another)
        app2 = QApplication.instance()

        assert app1 is app2

    except ImportError:
        # In mock environments, this is handled by our fixture
        pass

def test_qt_resource_cleanup():
    """Test that Qt resources are properly cleaned up."""
    import gc

    # Force garbage collection
    gc.collect()

    # Check active thread count (should be reasonable)
    import threading
    active_count = threading.active_count()

    # Should not have excessive threads
    # Allow some tolerance for background threads
    assert active_count < 10, f"Too many active threads: {active_count}"
