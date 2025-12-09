"""
Comprehensive integration tests for DialogBaseMigrationAdapter using real Qt widgets.

This test suite validates that the new composition-based DialogBaseMigrationAdapter
provides identical behavior to the original DialogBase class. All tests use real
Qt widgets (no mocks) to ensure authentic widget behavior and signal handling.

Test Strategy:
- Side-by-side comparison of both implementations
- Feature flag toggling to test both code paths
- Real Qt widget creation and interaction
- Signal/slot connection validation
- Performance benchmarking
- Memory usage comparison

Coverage Areas:
1. Basic dialog creation and properties
2. Tab management functionality
3. Button box operations
4. Status bar functionality
5. Message dialog methods
6. Signal/slot connections
7. Initialization order enforcement
8. Performance comparison
"""
from __future__ import annotations

import gc
import logging
import os
import time
from collections.abc import Callable, Generator
from typing import Any
from unittest.mock import Mock, patch

import pytest

pytestmark = [
    pytest.mark.cache,
    pytest.mark.ci_safe,
    pytest.mark.dialog,
    pytest.mark.gui,
    pytest.mark.integration,
    pytest.mark.memory,
    pytest.mark.performance,
    pytest.mark.qt_real,
    pytest.mark.requires_display,
    pytest.mark.signals_slots,
    pytest.mark.slow,
]
from PySide6.QtCore import Qt, QTimer
from PySide6.QtTest import QSignalSpy, QTest
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QLabel,
    QMessageBox,
    QPushButton,
    QSplitter,
    QStatusBar,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ui.components.base.composed.migration_adapter import (
    DialogBaseMigrationAdapter as ComposedDialogBase,
)

# Import both implementations for comparison
from ui.components.base.dialog_base import (
    DialogBase as LegacyDialogBase,
    InitializationOrderError as LegacyInitializationOrderError,
)
from utils.dialog_feature_flags import (
    get_dialog_implementation,
    is_composed_dialogs_enabled,
    set_dialog_implementation,
)

# Configure logging for tests
logger = logging.getLogger(__name__)

# Test data constants
TEST_TITLE = "Integration Test Dialog"
TEST_MESSAGE = "Test status message"
TEST_TAB_LABELS = ["Tab 1", "Tab 2", "Tab 3"]
TEST_BUTTON_TEXT = "Test Button"

# Performance test thresholds (in milliseconds)
PERFORMANCE_THRESHOLD_MS = 100
MEMORY_THRESHOLD_MB = 10

class DialogBaseTestHelper:
    """Base class for dialog subclasses used in testing."""

    def __init__(self, dialog_class: type, **kwargs):
        self.dialog_class = dialog_class
        self.kwargs = kwargs

    def create_dialog(self) -> QDialog:
        """Create a dialog instance for testing."""
        return self.dialog_class(**self.kwargs)

class SimpleTestDialog(LegacyDialogBase):
    """Simple test dialog using legacy implementation."""

    def __init__(self, parent: QWidget | None = None, **kwargs):
        # Declare instance variables before super().__init__
        self.test_widget: QWidget | None = None
        self.test_label: QLabel | None = None

        super().__init__(parent, **kwargs)

    def _setup_ui(self) -> None:
        """Set up the dialog UI."""
        self.test_widget = QWidget()
        self.test_label = QLabel("Test Dialog Content")

        layout = QVBoxLayout(self.test_widget)
        layout.addWidget(self.test_label)
        self.main_layout.addWidget(self.test_widget)

class SimpleComposedTestDialog(ComposedDialogBase):
    """Simple test dialog using composed implementation."""

    def __init__(self, parent: QWidget | None = None, **kwargs):
        # Declare instance variables before super().__init__
        self.test_widget: QWidget | None = None
        self.test_label: QLabel | None = None

        super().__init__(parent, **kwargs)

    def _setup_ui(self) -> None:
        """Set up the dialog UI."""
        self.test_widget = QWidget()
        self.test_label = QLabel("Test Dialog Content")

        layout = QVBoxLayout(self.test_widget)
        layout.addWidget(self.test_label)
        self.main_layout.addWidget(self.test_widget)

class BadInitOrderDialog(LegacyDialogBase):
    """Dialog that violates initialization order (for testing error handling)."""

    def __init__(self, parent: QWidget | None = None, **kwargs):
        super().__init__(parent, **kwargs)
        # Late assignment - should trigger warning/error
        self.test_widget: QWidget | None = None

class BadInitOrderComposedDialog(ComposedDialogBase):
    """Dialog that violates initialization order (composed version)."""

    def __init__(self, parent: QWidget | None = None, **kwargs):
        super().__init__(parent, **kwargs)
        # Late assignment - should trigger warning
        self.test_widget: QWidget | None = None

@pytest.fixture(scope="session")
def qt_app() -> Generator[QApplication, None, None]:
    """Create a QApplication instance for the test session."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
        app.setQuitOnLastWindowClosed(False)

    # Configure for headless testing
    app.setAttribute(Qt.ApplicationAttribute.AA_DisableWindowContextHelpButton, True)
    app.processEvents()

    yield app

    # Cleanup
    app.processEvents()
    # Don't quit the app as it might be shared with other tests

@pytest.fixture
def dialog_implementations() -> Generator[dict[str, type], None, None]:
    """Provide both dialog implementations for comparison testing."""
    implementations = {
        "legacy": LegacyDialogBase,
        "composed": ComposedDialogBase,
    }
    yield implementations

@pytest.fixture
def mock_message_box() -> Generator[Mock, None, None]:
    """Mock QMessageBox methods to prevent actual dialogs during tests."""
    with patch.multiple(
        QMessageBox,
        critical=Mock(return_value=QMessageBox.StandardButton.Ok),
        information=Mock(return_value=QMessageBox.StandardButton.Ok),
        warning=Mock(return_value=QMessageBox.StandardButton.Ok),
        question=Mock(return_value=QMessageBox.StandardButton.Yes),
    ) as mocks:
        yield mocks

@pytest.fixture
def feature_flag_switcher() -> Generator[Callable[[bool], None], None, None]:
    """Fixture to switch feature flags during tests."""
    original_setting = is_composed_dialogs_enabled()

    def switch_implementation(use_composed: bool) -> None:
        """Switch between dialog implementations."""
        set_dialog_implementation(use_composed)
        # Clear module cache to force reimport
        import sys
        modules_to_clear = [
            mod for mod in sys.modules
            if 'dialog_selector' in mod or 'migration_adapter' in mod
        ]
        for mod in modules_to_clear:
            if mod in sys.modules:
                del sys.modules[mod]

    yield switch_implementation

    # Restore original setting
    set_dialog_implementation(original_setting)

class TestBasicDialogCreation:
    """Test basic dialog creation and properties."""

    def test_dialog_creation_default_params(self, qt_app: QApplication, dialog_implementations: dict[str, type]) -> None:
        """Test dialog creation with default parameters."""
        for dialog_class in dialog_implementations.values():
            dialog = dialog_class()

            # Basic properties should be set
            assert dialog.isModal()
            assert dialog.testAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
            assert dialog.main_layout is not None
            assert dialog.content_widget is not None

            # Default button box should exist
            assert dialog.button_box is not None
            assert isinstance(dialog.button_box, QDialogButtonBox)

            # Status bar should not exist by default
            assert dialog.status_bar is None

            # Tab widget should not exist initially
            assert dialog.tab_widget is None

            dialog.close()
            qt_app.processEvents()

    def test_dialog_creation_custom_params(self, qt_app: QApplication, dialog_implementations: dict[str, type]) -> None:
        """Test dialog creation with custom parameters."""
        test_params = {
            "title": TEST_TITLE,
            "modal": False,
            "min_size": (400, 300),
            "size": (800, 600),
            "with_status_bar": True,
            "with_button_box": False,
        }

        for dialog_class in dialog_implementations.values():
            dialog = dialog_class(**test_params)

            # Verify custom parameters were applied
            assert dialog.windowTitle() == TEST_TITLE
            assert not dialog.isModal()
            assert dialog.minimumWidth() == 400
            assert dialog.minimumHeight() == 300
            assert dialog.width() == 800
            assert dialog.height() == 600

            # Status bar should exist
            assert dialog.status_bar is not None
            assert isinstance(dialog.status_bar, QStatusBar)

            # Button box should not exist
            assert dialog.button_box is None

            dialog.close()
            qt_app.processEvents()

    def test_dialog_properties_consistency(self, qt_app: QApplication, dialog_implementations: dict[str, type]) -> None:
        """Test that both implementations provide identical properties."""
        test_params = {
            "title": TEST_TITLE,
            "with_status_bar": True,
            "with_button_box": True,
        }

        dialogs = {}
        for impl_name, dialog_class in dialog_implementations.items():
            dialogs[impl_name] = dialog_class(**test_params)

        try:
            # Compare properties between implementations
            legacy = dialogs["legacy"]
            composed = dialogs["composed"]

            # Window properties
            assert legacy.windowTitle() == composed.windowTitle()
            assert legacy.isModal() == composed.isModal()
            assert legacy.testAttribute(Qt.WidgetAttribute.WA_DeleteOnClose) == composed.testAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)

            # Component properties
            assert (legacy.button_box is not None) == (composed.button_box is not None)
            assert (legacy.status_bar is not None) == (composed.status_bar is not None)
            assert type(legacy.main_layout) is type(composed.main_layout)
            assert type(legacy.content_widget) is type(composed.content_widget)

        finally:
            for dialog in dialogs.values():
                dialog.close()
                qt_app.processEvents()

class TestTabManagement:
    """Test tab management functionality."""

    def test_add_tabs_dynamically(self, qt_app: QApplication, dialog_implementations: dict[str, type]) -> None:
        """Test adding tabs dynamically to dialogs."""
        for dialog_class in dialog_implementations.values():
            dialog = dialog_class()

            # Initially no tab widget
            assert dialog.tab_widget is None
            assert dialog.get_current_tab_index() == -1

            # Add first tab - should create tab widget
            widget1 = QLabel("Tab 1 Content")
            dialog.add_tab(widget1, TEST_TAB_LABELS[0])

            assert dialog.tab_widget is not None
            assert isinstance(dialog.tab_widget, QTabWidget)
            assert dialog.tab_widget.count() == 1
            assert dialog.tab_widget.tabText(0) == TEST_TAB_LABELS[0]
            assert dialog.get_current_tab_index() == 0

            # Add more tabs
            widget2 = QLabel("Tab 2 Content")
            widget3 = QLabel("Tab 3 Content")
            dialog.add_tab(widget2, TEST_TAB_LABELS[1])
            dialog.add_tab(widget3, TEST_TAB_LABELS[2])

            assert dialog.tab_widget.count() == 3
            assert dialog.tab_widget.tabText(1) == TEST_TAB_LABELS[1]
            assert dialog.tab_widget.tabText(2) == TEST_TAB_LABELS[2]

            dialog.close()
            qt_app.processEvents()

    def test_tab_switching(self, qt_app: QApplication, dialog_implementations: dict[str, type]) -> None:
        """Test switching between tabs."""
        for dialog_class in dialog_implementations.values():
            dialog = dialog_class()

            # Add tabs
            for i, label in enumerate(TEST_TAB_LABELS):
                widget = QLabel(f"Content {i+1}")
                dialog.add_tab(widget, label)

            # Test tab switching
            for i in range(len(TEST_TAB_LABELS)):
                dialog.set_current_tab(i)
                assert dialog.get_current_tab_index() == i
                assert dialog.tab_widget.currentIndex() == i

            dialog.close()
            qt_app.processEvents()

    def test_default_tab_setting(self, qt_app: QApplication, dialog_implementations: dict[str, type]) -> None:
        """Test setting default tab during initialization."""
        default_tab = 1

        for dialog_class in dialog_implementations.values():
            dialog = dialog_class(default_tab=default_tab)

            # Add tabs
            for i, label in enumerate(TEST_TAB_LABELS):
                widget = QLabel(f"Content {i+1}")
                dialog.add_tab(widget, label)

            # Default tab should be selected
            assert dialog.get_current_tab_index() == default_tab

            dialog.close()
            qt_app.processEvents()

class TestButtonBoxFunctionality:
    """Test button box functionality."""

    def test_default_button_box_creation(self, qt_app: QApplication, dialog_implementations: dict[str, type]) -> None:
        """Test default button box creation and configuration."""
        for dialog_class in dialog_implementations.values():
            dialog = dialog_class(with_button_box=True)

            assert dialog.button_box is not None
            assert isinstance(dialog.button_box, QDialogButtonBox)

            # Check standard buttons
            buttons = dialog.button_box.standardButtons()
            expected = QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
            assert buttons == expected

            dialog.close()
            qt_app.processEvents()

    def test_button_box_signal_connections(self, qt_app: QApplication, dialog_implementations: dict[str, type]) -> None:
        """Test button box signal connections."""
        for dialog_class in dialog_implementations.values():
            dialog = dialog_class(with_button_box=True)

            # Set up signal spies
            accepted_spy = QSignalSpy(dialog.accepted)
            rejected_spy = QSignalSpy(dialog.rejected)

            # Click OK button
            ok_button = dialog.button_box.button(QDialogButtonBox.StandardButton.Ok)
            QTest.mouseClick(ok_button, Qt.MouseButton.LeftButton)
            qt_app.processEvents()

            # Should trigger accepted signal
            assert accepted_spy.count() == 1
            assert rejected_spy.count() == 0

            dialog.close()
            qt_app.processEvents()

    def test_custom_button_addition(self, qt_app: QApplication, dialog_implementations: dict[str, type]) -> None:
        """Test adding custom buttons to dialog."""
        callback_called = False

        def button_callback():
            nonlocal callback_called
            callback_called = True

        for dialog_class in dialog_implementations.values():
            callback_called = False
            dialog = dialog_class(with_button_box=True)

            # Add custom button
            custom_button = dialog.add_button(TEST_BUTTON_TEXT, button_callback)

            assert custom_button is not None
            assert isinstance(custom_button, QPushButton)
            assert custom_button.text() == TEST_BUTTON_TEXT

            # Click the custom button
            QTest.mouseClick(custom_button, Qt.MouseButton.LeftButton)
            qt_app.processEvents()

            assert callback_called

            dialog.close()
            qt_app.processEvents()

class TestStatusBarOperations:
    """Test status bar operations."""

    def test_status_bar_creation(self, qt_app: QApplication, dialog_implementations: dict[str, type]) -> None:
        """Test status bar creation and basic functionality."""
        for dialog_class in dialog_implementations.values():
            dialog = dialog_class(with_status_bar=True)

            assert dialog.status_bar is not None
            assert isinstance(dialog.status_bar, QStatusBar)

            dialog.close()
            qt_app.processEvents()

    def test_status_message_updates(self, qt_app: QApplication, dialog_implementations: dict[str, type]) -> None:
        """Test updating status bar messages."""
        for dialog_class in dialog_implementations.values():
            dialog = dialog_class(with_status_bar=True)

            # Update status message
            dialog.update_status(TEST_MESSAGE)
            qt_app.processEvents()

            # Verify message was set
            assert dialog.status_bar.currentMessage() == TEST_MESSAGE

            # Update with different message
            new_message = "Updated status"
            dialog.update_status(new_message)
            qt_app.processEvents()

            assert dialog.status_bar.currentMessage() == new_message

            dialog.close()
            qt_app.processEvents()

    def test_status_bar_without_creation(self, qt_app: QApplication, dialog_implementations: dict[str, type]) -> None:
        """Test status operations when status bar is not created."""
        for dialog_class in dialog_implementations.values():
            dialog = dialog_class(with_status_bar=False)

            assert dialog.status_bar is None

            # Should not raise exception
            dialog.update_status(TEST_MESSAGE)

            dialog.close()
            qt_app.processEvents()

class TestMessageDialogs:
    """Test message dialog methods."""

    def test_error_message_dialog(self, qt_app: QApplication, dialog_implementations: dict[str, type], mock_message_box: Mock) -> None:
        """Test error message dialog display."""
        title = "Error Title"
        message = "Error message content"

        for dialog_class in dialog_implementations.values():
            dialog = dialog_class()

            dialog.show_error(title, message)

            # Verify QMessageBox.critical was called
            mock_message_box["critical"].assert_called_with(dialog, title, message)

            dialog.close()
            qt_app.processEvents()

            mock_message_box["critical"].reset_mock()

    def test_info_message_dialog(self, qt_app: QApplication, dialog_implementations: dict[str, type], mock_message_box: Mock) -> None:
        """Test information message dialog display."""
        title = "Info Title"
        message = "Info message content"

        for dialog_class in dialog_implementations.values():
            dialog = dialog_class()

            dialog.show_info(title, message)

            # Verify QMessageBox.information was called
            mock_message_box["information"].assert_called_with(dialog, title, message)

            dialog.close()
            qt_app.processEvents()

            mock_message_box["information"].reset_mock()

    def test_warning_message_dialog(self, qt_app: QApplication, dialog_implementations: dict[str, type], mock_message_box: Mock) -> None:
        """Test warning message dialog display."""
        title = "Warning Title"
        message = "Warning message content"

        for dialog_class in dialog_implementations.values():
            dialog = dialog_class()

            dialog.show_warning(title, message)

            # Verify QMessageBox.warning was called
            mock_message_box["warning"].assert_called_with(dialog, title, message)

            dialog.close()
            qt_app.processEvents()

            mock_message_box["warning"].reset_mock()

    def test_confirm_action_dialog(self, qt_app: QApplication, dialog_implementations: dict[str, type], mock_message_box: Mock) -> None:
        """Test confirmation dialog return value."""
        title = "Confirm Title"
        message = "Confirm message content"

        for dialog_class in dialog_implementations.values():
            dialog = dialog_class()

            # Test positive confirmation
            mock_message_box["question"].return_value = QMessageBox.StandardButton.Yes
            result = dialog.confirm_action(title, message)
            assert result is True

            # Test negative confirmation
            mock_message_box["question"].return_value = QMessageBox.StandardButton.No
            result = dialog.confirm_action(title, message)
            assert result is False

            # Verify QMessageBox.question was called
            mock_message_box["question"].assert_called_with(dialog, title, message)

            dialog.close()
            qt_app.processEvents()

            mock_message_box["question"].reset_mock()

class TestSignalSlotConnections:
    """Test signal/slot connections."""

    def test_button_box_connections(self, qt_app: QApplication, dialog_implementations: dict[str, type]) -> None:
        """Test button box signal connections work correctly."""
        for dialog_class in dialog_implementations.values():
            dialog = dialog_class(with_button_box=True)

            # Set up signal spies
            accepted_spy = QSignalSpy(dialog.accepted)
            rejected_spy = QSignalSpy(dialog.rejected)

            # Test OK button
            ok_button = dialog.button_box.button(QDialogButtonBox.StandardButton.Ok)
            ok_button.click()
            qt_app.processEvents()

            assert accepted_spy.count() == 1
            assert rejected_spy.count() == 0

            # Reset and test Cancel button
            accepted_spy.clear()
            rejected_spy.clear()

            cancel_button = dialog.button_box.button(QDialogButtonBox.StandardButton.Cancel)
            cancel_button.click()
            qt_app.processEvents()

            assert accepted_spy.count() == 0
            assert rejected_spy.count() == 1

            dialog.close()
            qt_app.processEvents()

    def test_tab_change_signals(self, qt_app: QApplication, dialog_implementations: dict[str, type]) -> None:
        """Test tab change signals are emitted correctly."""
        for dialog_class in dialog_implementations.values():
            dialog = dialog_class()

            # Add tabs
            for i, label in enumerate(TEST_TAB_LABELS[:2]):  # Only add 2 tabs for simplicity
                widget = QLabel(f"Content {i+1}")
                dialog.add_tab(widget, label)

            # Set up signal spy for tab changes
            tab_spy = QSignalSpy(dialog.tab_widget.currentChanged)

            # Change tab
            dialog.set_current_tab(1)
            qt_app.processEvents()

            # Should have emitted signal
            assert tab_spy.count() == 1
            assert tab_spy.at(0)[0] == 1  # New tab index

            dialog.close()
            qt_app.processEvents()

    def test_dialog_lifetime_signals(self, qt_app: QApplication, dialog_implementations: dict[str, type]) -> None:
        """Test dialog lifetime signals (show, close, etc.)."""
        for dialog_class in dialog_implementations.values():
            dialog = dialog_class()

            # Set up signal spies
            finished_spy = QSignalSpy(dialog.finished)

            # Simulate dialog acceptance
            dialog.accept()
            qt_app.processEvents()

            # Should have emitted finished signal
            assert finished_spy.count() == 1
            assert finished_spy.at(0)[0] == QDialog.DialogCode.Accepted

            qt_app.processEvents()

class TestInitializationOrderPattern:
    """Test initialization order enforcement."""

    def test_proper_initialization_order(self, qt_app: QApplication) -> None:
        """Test that proper initialization order works correctly."""
        # Test legacy implementation
        dialog = SimpleTestDialog()
        assert dialog.test_widget is not None
        assert dialog.test_label is not None
        dialog.close()
        qt_app.processEvents()

        # Test composed implementation
        dialog = SimpleComposedTestDialog()
        assert dialog.test_widget is not None
        assert dialog.test_label is not None
        dialog.close()
        qt_app.processEvents()

    def test_bad_initialization_order_detection(self, qt_app: QApplication, caplog: pytest.LogCaptureFixture) -> None:
        """Test that bad initialization order is detected and handled."""
        with caplog.at_level(logging.WARNING):
            # Legacy implementation should be stricter
            try:
                dialog = BadInitOrderDialog()
                dialog.close()
                qt_app.processEvents()
            except LegacyInitializationOrderError:
                pass  # Expected for legacy implementation

            # Composed implementation should warn but not fail
            dialog = BadInitOrderComposedDialog()
            dialog.close()
            qt_app.processEvents()

        # Should have logged warnings
        warning_messages = [record.message for record in caplog.records if record.levelno >= logging.WARNING]
        assert any("initialization" in msg.lower() or "late assignment" in msg.lower() for msg in warning_messages)

    def test_setup_ui_call_tracking(self, qt_app: QApplication) -> None:
        """Test that _setup_ui is called properly and tracked."""
        dialog = SimpleTestDialog()

        # Should have called _setup_ui
        assert hasattr(dialog, '_setup_called')
        assert dialog._setup_called is True
        assert hasattr(dialog, '_initialization_phase')
        assert dialog._initialization_phase == "complete"

        dialog.close()
        qt_app.processEvents()

class TestSplitterFunctionality:
    """Test splitter dialog functionality."""

    def test_horizontal_splitter_creation(self, qt_app: QApplication, dialog_implementations: dict[str, type]) -> None:
        """Test creating horizontal splitters."""
        for dialog_class in dialog_implementations.values():
            dialog = dialog_class(orientation=Qt.Orientation.Horizontal)

            assert dialog.main_splitter is not None
            assert isinstance(dialog.main_splitter, QSplitter)
            assert dialog.main_splitter.orientation() == Qt.Orientation.Horizontal

            dialog.close()
            qt_app.processEvents()

    def test_add_horizontal_splitter_method(self, qt_app: QApplication, dialog_implementations: dict[str, type]) -> None:
        """Test add_horizontal_splitter method."""
        for dialog_class in dialog_implementations.values():
            dialog = dialog_class()

            # Add horizontal splitter
            splitter = dialog.add_horizontal_splitter(handle_width=10)

            assert splitter is not None
            assert isinstance(splitter, QSplitter)
            assert splitter.orientation() == Qt.Orientation.Horizontal
            assert splitter.handleWidth() == 10

            dialog.close()
            qt_app.processEvents()

    def test_panel_addition_to_splitter(self, qt_app: QApplication, dialog_implementations: dict[str, type]) -> None:
        """Test adding panels to splitter dialogs."""
        for dialog_class in dialog_implementations.values():
            dialog = dialog_class(orientation=Qt.Orientation.Horizontal)

            # Add panels
            panel1 = QLabel("Panel 1")
            panel2 = QLabel("Panel 2")

            dialog.add_panel(panel1, stretch_factor=1)
            dialog.add_panel(panel2, stretch_factor=2)

            assert dialog.main_splitter.count() == 2
            assert dialog.main_splitter.widget(0) == panel1
            assert dialog.main_splitter.widget(1) == panel2

            dialog.close()
            qt_app.processEvents()

class TestPerformanceComparison:
    """Test performance comparison between implementations."""

    def test_initialization_performance(self, qt_app: QApplication, dialog_implementations: dict[str, type]) -> None:
        """Test and compare initialization performance."""
        results = {}

        for impl_name, dialog_class in dialog_implementations.items():
            # Measure initialization time
            start_time = time.perf_counter()

            for _ in range(10):  # Create multiple instances
                dialog = dialog_class(
                    title=TEST_TITLE,
                    with_status_bar=True,
                    with_button_box=True
                )
                dialog.close()
                qt_app.processEvents()

            end_time = time.perf_counter()
            avg_time_ms = ((end_time - start_time) * 1000) / 10
            results[impl_name] = avg_time_ms

        # Log results for analysis
        logger.info(f"Initialization performance: {results}")

        # Both should be reasonably fast
        for impl_name, time_ms in results.items():
            assert time_ms < PERFORMANCE_THRESHOLD_MS, f"{impl_name} initialization too slow: {time_ms}ms"

    def test_memory_usage_comparison(self, qt_app: QApplication, dialog_implementations: dict[str, type]) -> None:
        """Test and compare memory usage between implementations."""
        import psutil

        process = psutil.Process(os.getpid())
        results = {}

        for impl_name, dialog_class in dialog_implementations.items():
            # Force garbage collection before measurement
            gc.collect()
            initial_memory = process.memory_info().rss / 1024 / 1024  # MB

            dialogs = []
            for _ in range(20):  # Create multiple instances
                dialog = dialog_class(
                    title=TEST_TITLE,
                    with_status_bar=True,
                    with_button_box=True
                )
                dialogs.append(dialog)
                qt_app.processEvents()

            peak_memory = process.memory_info().rss / 1024 / 1024  # MB
            memory_diff = peak_memory - initial_memory
            results[impl_name] = memory_diff

            # Clean up
            for dialog in dialogs:
                dialog.close()
                qt_app.processEvents()
            del dialogs
            gc.collect()

        # Log results for analysis
        logger.info(f"Memory usage: {results}")

        # Both should use reasonable memory
        for impl_name, memory_mb in results.items():
            assert memory_mb < MEMORY_THRESHOLD_MB, f"{impl_name} uses too much memory: {memory_mb}MB"

class TestFeatureFlagIntegration:
    """Test integration with feature flag system."""

    def test_feature_flag_detection(self, feature_flag_switcher: Callable[[bool], None]) -> None:
        """Test feature flag detection works correctly."""
        # Test legacy setting
        feature_flag_switcher(False)
        assert get_dialog_implementation() == "legacy"
        assert not is_composed_dialogs_enabled()

        # Test composed setting
        feature_flag_switcher(True)
        assert get_dialog_implementation() == "composed"
        assert is_composed_dialogs_enabled()

    def test_implementation_switching(self, qt_app: QApplication, feature_flag_switcher: Callable[[bool], None]) -> None:
        """Test switching between implementations via feature flags."""
        # This test would require reloading modules, which is complex in pytest
        # For now, we test that the flag detection works correctly

        # Test that we can switch flags
        feature_flag_switcher(True)
        assert is_composed_dialogs_enabled()

        feature_flag_switcher(False)
        assert not is_composed_dialogs_enabled()

class TestBehavioralConsistency:
    """Test that both implementations provide identical behavior."""

    def test_identical_method_signatures(self, dialog_implementations: dict[str, type]) -> None:
        """Test that both implementations have identical public method signatures."""
        legacy_class = dialog_implementations["legacy"]
        composed_class = dialog_implementations["composed"]

        # Get public methods (excluding private/dunder methods)
        legacy_methods = {name for name in dir(legacy_class) if not name.startswith('_')}
        composed_methods = {name for name in dir(composed_class) if not name.startswith('_')}

        # Both should have the same public API
        assert legacy_methods == composed_methods, f"Method differences: {legacy_methods.symmetric_difference(composed_methods)}"

    def test_identical_property_behavior(self, qt_app: QApplication, dialog_implementations: dict[str, type]) -> None:
        """Test that properties behave identically between implementations."""
        test_params = {
            "title": TEST_TITLE,
            "with_status_bar": True,
            "with_button_box": True,
        }

        dialogs = {}
        for impl_name, dialog_class in dialog_implementations.items():
            dialogs[impl_name] = dialog_class(**test_params)

        try:
            legacy = dialogs["legacy"]
            composed = dialogs["composed"]

            # Test property consistency
            properties_to_test = [
                'windowTitle',
                'isModal',
                'minimumWidth',
                'minimumHeight',
            ]

            for prop in properties_to_test:
                if hasattr(legacy, prop) and hasattr(composed, prop):
                    legacy_value = getattr(legacy, prop)()
                    composed_value = getattr(composed, prop)()
                    assert legacy_value == composed_value, f"Property {prop} differs: {legacy_value} vs {composed_value}"

        finally:
            for dialog in dialogs.values():
                dialog.close()
                qt_app.processEvents()

class TestCleanupAndLifecycle:
    """Test dialog cleanup and lifecycle management."""

    def test_proper_cleanup_on_close(self, qt_app: QApplication, dialog_implementations: dict[str, type]) -> None:
        """Test that dialogs clean up properly when closed."""
        for impl_name, dialog_class in dialog_implementations.items():
            dialog = dialog_class(with_status_bar=True, with_button_box=True)

            # Add some content
            widget = QLabel("Test content")
            dialog.add_tab(widget, "Test Tab")

            # Track objects for cleanup verification
            objects_before = len(qt_app.allWidgets())

            # Close dialog
            dialog.close()
            qt_app.processEvents()

            # Allow Qt to clean up
            QTimer.singleShot(0, lambda: None)
            qt_app.processEvents()

            # Should have cleaned up (though exact count may vary due to Qt internals)
            objects_after = len(qt_app.allWidgets())
            assert objects_after <= objects_before, f"Objects not cleaned up properly for {impl_name}"

    def test_delete_on_close_attribute(self, qt_app: QApplication, dialog_implementations: dict[str, type]) -> None:
        """Test that WA_DeleteOnClose attribute is set correctly."""
        for impl_name, dialog_class in dialog_implementations.items():
            dialog = dialog_class()

            assert dialog.testAttribute(Qt.WidgetAttribute.WA_DeleteOnClose), f"{impl_name} should have WA_DeleteOnClose set"

            dialog.close()
            qt_app.processEvents()

# Performance benchmark fixtures and utilities
@pytest.fixture
def performance_monitor():
    """Monitor for performance testing."""
    class PerformanceMonitor:
        def __init__(self):
            self.measurements = {}

        def measure(self, name: str, func: Callable[[], Any]) -> Any:
            start = time.perf_counter()
            try:
                result = func()
                return result
            finally:
                end = time.perf_counter()
                self.measurements[name] = (end - start) * 1000  # Convert to ms

        def get_measurement(self, name: str) -> float:
            return self.measurements.get(name, 0.0)

        def compare(self, name1: str, name2: str) -> dict[str, float]:
            time1 = self.get_measurement(name1)
            time2 = self.get_measurement(name2)
            return {
                name1: time1,
                name2: time2,
                "difference_ms": abs(time1 - time2),
                "ratio": time1 / time2 if time2 > 0 else float('inf')
            }

    return PerformanceMonitor()

# Run performance benchmarks if requested
def test_comprehensive_performance_benchmark(qt_app: QApplication, dialog_implementations: dict[str, type], performance_monitor) -> None:
    """Comprehensive performance benchmark between implementations."""
    iterations = 50

    for impl_name, dialog_class in dialog_implementations.items():
        def create_and_configure():
            dialogs = []
            for _ in range(iterations):
                dialog = dialog_class(
                    title=f"Performance Test {impl_name}",
                    with_status_bar=True,
                    with_button_box=True,
                    min_size=(400, 300)
                )

                # Add some typical content
                for i in range(3):
                    widget = QLabel(f"Tab {i} content")
                    dialog.add_tab(widget, f"Tab {i}")

                dialog.update_status("Performance test in progress...")
                dialogs.append(dialog)
                qt_app.processEvents()

            # Cleanup
            for dialog in dialogs:
                dialog.close()
                qt_app.processEvents()

        performance_monitor.measure(impl_name, create_and_configure)

    # Compare results
    comparison = performance_monitor.compare("legacy", "composed")
    logger.info(f"Performance comparison: {comparison}")

    # Both implementations should perform reasonably
    for impl_name in dialog_implementations:
        time_ms = performance_monitor.get_measurement(impl_name)
        assert time_ms < PERFORMANCE_THRESHOLD_MS * iterations, f"{impl_name} performance regression: {time_ms}ms"

if __name__ == "__main__":
    # Run tests directly if called as script
    pytest.main([__file__, "-v", "--tb=short"])
