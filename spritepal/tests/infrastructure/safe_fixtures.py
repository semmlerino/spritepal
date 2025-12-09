# pyright: recommended  # Enhanced typing for fixture safety
# pyright: reportPrivateUsage=false  # Fixtures may access private members for safety
# pyright: reportUnknownMemberType=warning  # Mock fixtures have dynamic attributes
# pyright: reportUntypedFunctionDecorator=error  # Type all decorators

"""
Safe fixture wrappers to prevent Qt initialization crashes in headless environments.

This module provides comprehensive fixture wrappers that:
1. Detect environment before creating Qt widgets
2. Provide mock alternatives in headless mode
3. Maintain same API for test compatibility
4. Handle cleanup properly
5. Override standard pytest-qt fixtures

Key Components:
- SafeQtBot: Mock qtbot for headless environments
- SafeQApplication: Safe QApplication creation/mocking
- SafeWidgetFactory: Widget creation with environment detection
- SafeDialogFactory: Dialog creation with crash prevention
- Fixture validation and error reporting

Usage:
    from tests.infrastructure.safe_fixtures import (
        create_safe_qtbot,
        create_safe_qapp,
        create_safe_widget_factory
    )

    @pytest.fixture
    def qtbot(request):
        return create_safe_qtbot(request)

Environment Detection:
- Uses centralized environment detection from environment_detection.py
- Automatically chooses appropriate fixture type based on environment
- Provides clear error messages when display needed
- Handles xvfb availability detection

Safety Features:
- Prevents Qt initialization crashes in headless mode
- Provides mock alternatives that maintain test compatibility
- Thread-safe resource cleanup
- Comprehensive error handling and reporting
- Validation of fixture behavior across environments

Architecture:
- Factory pattern for creating safe fixtures
- Protocol-based interfaces for type safety
- Centralized configuration and detection
- Extensible design for additional fixture types
"""

from __future__ import annotations

import logging
import threading
import warnings
import weakref
from collections.abc import Callable, Generator
from contextlib import contextmanager, suppress
from typing import (
    TYPE_CHECKING,
    Any,
    Protocol,
    TypeVar,
    runtime_checkable,
)
from unittest.mock import Mock

if TYPE_CHECKING:
    from pytest import FixtureRequest

# Import existing infrastructure
from .environment_detection import (
    HeadlessModeError,
    get_environment_info,
    is_headless_environment,
)
from .qt_mocks import (
    MockQApplication,
    MockQDialog,
    MockQThread,
    MockQWidget,
)

# Configure logging
logger = logging.getLogger(__name__)

# Type variables for generic fixtures
T = TypeVar('T')
FixtureType = TypeVar('FixtureType')

# Global registry for tracking active fixtures
_active_fixtures: weakref.WeakSet[Any] = weakref.WeakSet()
_fixture_cleanup_lock = threading.Lock()

@runtime_checkable
class SafeQtBotProtocol(Protocol):
    """Protocol for safe qtbot implementations (real or mock)."""

    def wait(self, timeout: int = 1000) -> None: ...
    def waitSignal(self, signal: Any, timeout: int = 5000, **kwargs: Any) -> Any: ...
    def wait_signal(self, signal: Any, timeout: int = 5000, **kwargs: Any) -> Any: ...
    def waitSignals(self, signals: list[Any], timeout: int = 5000, **kwargs: Any) -> Any: ...
    def wait_signals(self, signals: list[Any], timeout: int = 5000, **kwargs: Any) -> Any: ...
    def waitUntil(self, callback: Callable[[], bool], timeout: int = 5000) -> None: ...
    def wait_until(self, callback: Callable[[], bool], timeout: int = 5000) -> None: ...
    def addWidget(self, widget: Any) -> None: ...
    def screenshot(self, widget: Any | None = None) -> str | None: ...
    def keyPress(self, widget: Any, key: Any, modifier: Any = None) -> None: ...
    def mouseClick(self, widget: Any, button: Any, **kwargs: Any) -> None: ...

@runtime_checkable
class SafeQApplicationProtocol(Protocol):
    """Protocol for safe QApplication implementations (real or mock)."""

    def processEvents(self) -> None: ...
    def quit(self) -> None: ...
    def exit(self, exit_code: int = 0) -> None: ...
    def primaryScreen(self) -> Any: ...
    @classmethod
    def instance(cls) -> Any: ...

@runtime_checkable
class SafeWidgetProtocol(Protocol):
    """Protocol for safe widget implementations (real or mock)."""

    def show(self) -> None: ...
    def hide(self) -> None: ...
    def close(self) -> None: ...
    def setVisible(self, visible: bool) -> None: ...
    def isVisible(self) -> bool: ...
    def update(self) -> None: ...
    def resize(self, width: int, height: int) -> None: ...

class SafeQtBot:
    """
    Safe qtbot implementation that works in both headless and GUI environments.

    In headless mode, provides mock qtbot functionality.
    In GUI mode, delegates to real pytest-qt qtbot.
    """

    def __init__(self, real_qtbot: Any = None, headless: bool = False):
        self._real_qtbot = real_qtbot
        self._headless = headless
        self._widgets: list[Any] = []
        self._signals_waiting: list[Any] = []

        if headless:
            logger.debug("Creating mock qtbot for headless environment")
        else:
            logger.debug("Creating real qtbot wrapper for GUI environment")

    def wait(self, timeout: int = 1000) -> None:
        """Wait for specified timeout.

        NOTE: Always uses time.sleep in offscreen mode to avoid Qt event loop
        segfaults. The qtbot.wait() method calls QEventLoop.exec() which
        segfaults in offscreen mode on WSL2.
        """
        import os
        import time

        # In offscreen mode, ALWAYS use time.sleep to avoid segfaults
        # regardless of whether we have a real qtbot
        is_offscreen = os.environ.get('QT_QPA_PLATFORM') == 'offscreen'

        if self._headless or is_offscreen:
            # Safe wait - use time.sleep
            time.sleep(min(0.1, timeout / 1000))  # Brief pause (max 100ms)
        elif self._real_qtbot:
            self._real_qtbot.wait(timeout)

    def waitSignal(self, signal: Any, timeout: int = 5000, **kwargs: Any) -> Any:
        """Wait for signal emission with timeout."""
        if self._headless:
            # Mock signal waiting - return immediately with mock blocker
            mock_blocker = Mock()
            mock_blocker.args = ()
            mock_blocker.connect = Mock()
            mock_blocker.disconnect = Mock()
            mock_blocker.wait = Mock()
            # Store reference for cleanup
            self._signals_waiting.append(mock_blocker)
            return mock_blocker
        if self._real_qtbot:
            return self._real_qtbot.waitSignal(signal, timeout=timeout, **kwargs)
        raise HeadlessModeError("waitSignal requires real qtbot")

    # Snake case alias for pytest-qt compatibility
    wait_signal = waitSignal

    def waitSignals(self, signals: list[Any], timeout: int = 5000, **kwargs: Any) -> Any:
        """Wait for multiple signals emission with timeout."""
        if self._headless:
            # Mock signals waiting - return immediately with mock blocker
            mock_blocker = Mock()
            mock_blocker.args = []
            mock_blocker.all_signals_and_args = []
            mock_blocker.connect = Mock()
            mock_blocker.disconnect = Mock()
            mock_blocker.wait = Mock()
            # Store reference for cleanup
            self._signals_waiting.append(mock_blocker)
            return mock_blocker
        if self._real_qtbot:
            return self._real_qtbot.waitSignals(signals, timeout=timeout, **kwargs)
        raise HeadlessModeError("waitSignals requires real qtbot")

    # Snake case alias for pytest-qt compatibility
    wait_signals = waitSignals

    def waitUntil(self, callback: Callable[[], bool], timeout: int = 5000) -> None:
        """Wait until callback returns True."""
        if self._headless:
            # Mock waitUntil - assume callback would return True immediately
            try:
                if callable(callback):
                    callback()  # Call once for side effects
            except Exception:
                pass  # Ignore callback errors in mock mode
        elif self._real_qtbot:
            # pytest-qt's waitUntil requires timeout as keyword argument
            self._real_qtbot.waitUntil(callback, timeout=timeout)

    # Snake case alias for pytest-qt compatibility
    wait_until = waitUntil

    def waitForWindowShown(self, widget: Any, timeout: int = 5000) -> None:
        """Wait for window to be shown."""
        if self._headless:
            # Mock waitForWindowShown - brief pause then return
            import time
            time.sleep(0.01)
            return
        # Check if widget is a mock - handle gracefully without calling Qt functions
        is_mock = (
            isinstance(widget, MockQWidget) or
            (hasattr(widget, '__class__') and widget.__class__.__name__.startswith('Mock'))
        )
        if is_mock:
            # Mock widget - no wait needed, just return
            return
        if self._real_qtbot:
            # pytest-qt renamed waitForWindowShown to waitExposed in newer versions
            # Note: These methods accept timeout as positional argument only
            if hasattr(self._real_qtbot, 'waitForWindowShown'):
                self._real_qtbot.waitForWindowShown(widget)
            elif hasattr(self._real_qtbot, 'waitExposed'):
                self._real_qtbot.waitExposed(widget)
            else:
                # Fallback: process events to allow widget to show
                from PySide6.QtWidgets import QApplication
                QApplication.processEvents()

    def addWidget(self, widget: Any) -> None:
        """Add widget for management and cleanup."""
        # Check if widget is a mock to avoid passing to real qtbot
        is_mock = isinstance(widget, MockQWidget) or (hasattr(widget, '__class__') and widget.__class__.__name__.startswith('Mock'))

        if self._headless or is_mock:
            # Just store reference for mock cleanup
            self._widgets.append(widget)
        else:
            if self._real_qtbot:
                self._real_qtbot.addWidget(widget)
            self._widgets.append(widget)

    def screenshot(self, widget: Any | None = None) -> str | None:
        """Take screenshot of widget (mock in headless mode)."""
        if self._headless:
            # Return mock screenshot path
            return "/tmp/mock_screenshot.png"
        if self._real_qtbot and hasattr(self._real_qtbot, 'screenshot'):
            return self._real_qtbot.screenshot(widget)
        return None

    def keyPress(self, widget: Any, key: Any, modifier: Any = None) -> None:
        """Simulate key press on widget."""
        if self._headless:
            # Mock key press - just log it
            logger.debug(f"Mock keyPress: key={key}, modifier={modifier}")
        elif self._real_qtbot:
            if modifier:
                self._real_qtbot.keyPress(widget, key, modifier)
            else:
                self._real_qtbot.keyPress(widget, key)

    def mouseClick(self, widget: Any, button: Any, **kwargs: Any) -> None:
        """Simulate mouse click on widget."""
        if self._headless:
            # Mock mouse click - just log it
            logger.debug(f"Mock mouseClick: button={button}, kwargs={kwargs}")
        elif self._real_qtbot:
            self._real_qtbot.mouseClick(widget, button, **kwargs)

    def cleanup(self) -> None:
        """Cleanup resources used by this qtbot."""
        try:
            # Clear signal waiters
            self._signals_waiting.clear()

            # Clear widgets in headless mode (real qtbot handles its own cleanup)
            if self._headless:
                for widget in self._widgets:
                    with suppress(Exception):
                        if hasattr(widget, 'close'):
                            widget.close()
                        if hasattr(widget, 'deleteLater'):
                            widget.deleteLater()

            self._widgets.clear()

        except Exception as e:
            logger.warning(f"Error during qtbot cleanup: {e}")

class SafeQApplication:
    """
    Safe QApplication wrapper that works in both headless and GUI environments.

    Provides mock QApplication in headless mode, real QApplication in GUI mode.
    """

    def __init__(self, headless: bool = False, args: list[str] | None = None):
        self._headless = headless
        self._app: Any = None
        self._is_owner = False

        if headless:
            self._create_mock_app()
        else:
            self._create_or_get_real_app(args or [])

    def _create_mock_app(self) -> None:
        """Create mock QApplication for headless mode."""
        self._app = MockQApplication()
        self._is_owner = True
        logger.debug("Created mock QApplication for headless environment")

    def _create_or_get_real_app(self, args: list[str]) -> None:
        """Create or get existing real QApplication."""
        try:
            from PySide6.QtWidgets import QApplication

            # Check if app already exists
            existing_app = QApplication.instance()
            if existing_app:
                self._app = existing_app
                self._is_owner = False
                logger.debug("Using existing QApplication instance")
            else:
                # Create new QApplication
                self._app = QApplication(args)
                self._is_owner = True
                logger.debug("Created new QApplication instance")

        except Exception as e:
            logger.warning(f"Failed to create real QApplication: {e}")
            # Fallback to mock
            self._create_mock_app()

    def processEvents(self) -> None:
        """Process pending events."""
        if self._app and hasattr(self._app, 'processEvents'):
            self._app.processEvents()

    def quit(self) -> None:
        """Quit the application."""
        if self._app and hasattr(self._app, 'quit'):
            self._app.quit()

    def exit(self, exit_code: int = 0) -> None:
        """Exit with code."""
        if self._app and hasattr(self._app, 'exit'):
            self._app.exit(exit_code)

    def primaryScreen(self) -> Any:
        """Get primary screen."""
        if self._app and hasattr(self._app, 'primaryScreen'):
            return self._app.primaryScreen()
        return Mock()  # Mock screen for headless

    @classmethod
    def instance(cls) -> Any:
        """Get application instance."""
        if not hasattr(cls, '_instance'):
            cls._instance = None
        return cls._instance

    def cleanup(self) -> None:
        """Cleanup application if we own it."""
        if self._is_owner and self._app:
            try:
                if not self._headless:
                    # Process events before cleanup
                    self.processEvents()

                    # Only quit if we created the app
                    if hasattr(self._app, 'quit'):
                        self._app.quit()

                logger.debug("QApplication cleanup completed")
            except Exception as e:
                logger.warning(f"Error during QApplication cleanup: {e}")

        self._app = None

class WidgetCreationError(Exception):
    """Raised when widget creation fails."""
    pass

class SafeWidgetFactory:
    """
    Factory for creating widgets safely in any environment.

    Automatically detects environment and creates appropriate widget type.
    """

    def __init__(self, headless: bool | None = None):
        self._headless = headless if headless is not None else is_headless_environment()
        self._created_widgets: list[Any] = []

    def create_widget(self, widget_class: type | str, *args: Any, **kwargs: Any) -> Any:
        """
        Create widget safely based on environment.

        Args:
            widget_class: Widget class or string name
            *args: Positional arguments for widget constructor
            **kwargs: Keyword arguments for widget constructor

        Returns:
            Widget instance (real or mock based on environment)

        Raises:
            WidgetCreationError: If widget creation fails
        """
        try:
            if self._headless:
                widget = self._create_mock_widget(widget_class, *args, **kwargs)
            else:
                widget = self._create_real_widget(widget_class, *args, **kwargs)

            # Track created widget
            self._created_widgets.append(widget)
            return widget

        except Exception as e:
            raise WidgetCreationError(f"Failed to create widget {widget_class}: {e}") from e

    def _create_mock_widget(self, widget_class: type | str, *args: Any, **kwargs: Any) -> Any:
        """Create mock widget for headless environment."""
        if isinstance(widget_class, str):
            widget_name = widget_class
        else:
            widget_name = widget_class.__name__ if hasattr(widget_class, '__name__') else str(widget_class)

        # Map common widgets to their mock implementations
        widget_mapping = {
            'QWidget': MockQWidget,
            'QDialog': MockQDialog,
            'QThread': MockQThread,
        }

        # Check if widget is known, raise error for truly unknown widgets
        if widget_name not in widget_mapping:
            # Check if it's a known Qt widget name that we should support
            known_qt_widgets = {'QWidget', 'QDialog', 'QThread', 'QMainWindow',
                               'QPushButton', 'QLabel', 'QLineEdit', 'QTextEdit'}
            
            if widget_name in known_qt_widgets or widget_name.startswith('Q'):
                mock_class = MockQWidget
            elif 'Dialog' in widget_name:
                # Assume it's a dialog if the name implies it
                mock_class = MockQDialog
            else:
                # Fallback to generic widget mock for custom widgets
                logger.debug(f"Unknown widget type '{widget_name}', defaulting to MockQWidget")
                mock_class = MockQWidget
        else:
            mock_class = widget_mapping[widget_name]

        widget = mock_class(*args, **kwargs)

        logger.debug(f"Created mock {widget_name} for headless environment")
        return widget

    def _create_real_widget(self, widget_class: type | str, *args: Any, **kwargs: Any) -> Any:
        """Create real widget for GUI environment."""
        if isinstance(widget_class, str):
            # Import widget class by name
            try:
                widget_class = self._import_widget_class(widget_class)
            except WidgetCreationError:
                # Fallback to mock if import fails
                logger.debug(f"Failed to import {widget_class}, using mock")
                return self._create_mock_widget(widget_class, *args, **kwargs)

        try:
            widget = widget_class(*args, **kwargs)
            logger.debug(f"Created real {widget_class.__name__} for GUI environment")
            return widget
        except Exception as e:
            # Fallback to mock if widget creation fails
            logger.debug(f"Failed to create real widget, using mock: {e}")
            return self._create_mock_widget(str(widget_class), *args, **kwargs)

    def _import_widget_class(self, widget_name: str) -> type:
        """Import Qt widget class by name."""
        try:
            if widget_name.startswith('Q'):
                # Try QtWidgets first
                from PySide6.QtCore import QThread
                from PySide6.QtWidgets import QDialog, QWidget

                widget_classes = {
                    'QWidget': QWidget,
                    'QDialog': QDialog,
                    'QThread': QThread,
                }

                if widget_name in widget_classes:
                    return widget_classes[widget_name]
                # Try dynamic import
                from PySide6 import QtWidgets
                return getattr(QtWidgets, widget_name)
            raise ImportError(f"Unknown widget type: {widget_name}")

        except ImportError as e:
            raise WidgetCreationError(f"Cannot import widget class {widget_name}: {e}") from e

    def cleanup(self) -> None:
        """Cleanup all created widgets."""
        for widget in self._created_widgets:
            try:
                if hasattr(widget, 'close'):
                    widget.close()
                if hasattr(widget, 'deleteLater'):
                    widget.deleteLater()
            except Exception as e:
                logger.debug(f"Error cleaning up widget: {e}")

        self._created_widgets.clear()

class SafeDialogFactory:
    """
    Factory for creating dialogs safely with crash prevention.

    Ensures dialogs are created appropriately for the environment and provides
    comprehensive error handling and cleanup.
    """

    def __init__(self, headless: bool | None = None):
        self._headless = headless if headless is not None else is_headless_environment()
        self._created_dialogs: list[Any] = []

    def create_dialog(self, dialog_class: type | str, *args: Any, **kwargs: Any) -> Any:
        """
        Create dialog safely based on environment.

        Args:
            dialog_class: Dialog class or string name
            *args: Positional arguments for dialog constructor
            **kwargs: Keyword arguments for dialog constructor

        Returns:
            Dialog instance (real or mock based on environment)
        """
        try:
            if self._headless:
                dialog = self._create_mock_dialog(dialog_class, *args, **kwargs)
            else:
                dialog = self._create_real_dialog(dialog_class, *args, **kwargs)

            # Track created dialog
            self._created_dialogs.append(dialog)
            return dialog

        except Exception as e:
            logger.error(f"Failed to create dialog {dialog_class}: {e}")
            # Return mock dialog as fallback
            return self._create_mock_dialog(dialog_class, *args, **kwargs)

    def _create_mock_dialog(self, dialog_class: type | str, *args: Any, **kwargs: Any) -> Any:
        """Create mock dialog for headless environment."""
        dialog = MockQDialog(*args, **kwargs)

        # Add common dialog methods
        dialog.accept = Mock()
        dialog.reject = Mock()
        dialog.exec = Mock(return_value=1)  # Accepted by default
        dialog.result = Mock(return_value=1)
        dialog.setWindowTitle = Mock()
        dialog.setModal = Mock()

        # Add dialog-specific attributes based on class name
        if isinstance(dialog_class, str):
            dialog_name = dialog_class
        else:
            dialog_name = dialog_class.__name__ if hasattr(dialog_class, '__name__') else str(dialog_class)

        self._add_dialog_specific_attributes(dialog, dialog_name)

        logger.debug(f"Created mock dialog {dialog_name} for headless environment")
        return dialog

    def _create_real_dialog(self, dialog_class: type | str, *args: Any, **kwargs: Any) -> Any:
        """Create real dialog for GUI environment."""
        if isinstance(dialog_class, str):
            dialog_class = self._import_dialog_class(dialog_class)

        dialog = dialog_class(*args, **kwargs)
        logger.debug(f"Created real {dialog_class.__name__} for GUI environment")
        return dialog

    def _import_dialog_class(self, dialog_name: str) -> type:
        """Import Qt dialog class by name."""
        try:
            from PySide6.QtWidgets import QDialog, QFileDialog, QMessageBox

            dialog_classes = {
                'QDialog': QDialog,
                'QMessageBox': QMessageBox,
                'QFileDialog': QFileDialog,
            }

            if dialog_name in dialog_classes:
                return dialog_classes[dialog_name]
            # Try dynamic import
            from PySide6 import QtWidgets
            return getattr(QtWidgets, dialog_name)

        except ImportError as e:
            raise WidgetCreationError(f"Cannot import dialog class {dialog_name}: {e}") from e

    def _add_dialog_specific_attributes(self, dialog: Any, dialog_name: str) -> None:
        """Add dialog-specific mock attributes."""
        if 'FileDialog' in dialog_name:
            dialog.getOpenFileName = Mock(return_value=("/test/file.txt", "All Files (*)"))
            dialog.getSaveFileName = Mock(return_value=("/test/output.txt", "All Files (*)"))
            dialog.getExistingDirectory = Mock(return_value="/test/directory")

        elif 'MessageBox' in dialog_name:
            dialog.information = Mock(return_value=Mock())
            dialog.warning = Mock(return_value=Mock())
            dialog.critical = Mock(return_value=Mock())
            dialog.question = Mock(return_value=Mock())

    def cleanup(self) -> None:
        """Cleanup all created dialogs."""
        for dialog in self._created_dialogs:
            try:
                if hasattr(dialog, 'close'):
                    dialog.close()
                if hasattr(dialog, 'deleteLater'):
                    dialog.deleteLater()
            except Exception as e:
                logger.debug(f"Error cleaning up dialog: {e}")

        self._created_dialogs.clear()

class SafeFixtureManager:
    """
    Central manager for safe fixture lifecycle and cleanup.

    Provides centralized management of all safe fixtures with proper cleanup
    and resource management.
    """

    def __init__(self):
        self._qtbots: list[SafeQtBot] = []
        self._apps: list[SafeQApplication] = []
        self._widget_factories: list[SafeWidgetFactory] = []
        self._dialog_factories: list[SafeDialogFactory] = []
        self._cleanup_functions: list[Callable[[], None]] = []

    def register_qtbot(self, qtbot: SafeQtBot) -> None:
        """Register qtbot for cleanup."""
        self._qtbots.append(qtbot)
        _active_fixtures.add(qtbot)

    def register_app(self, app: SafeQApplication) -> None:
        """Register QApplication for cleanup."""
        self._apps.append(app)
        _active_fixtures.add(app)

    def register_widget_factory(self, factory: SafeWidgetFactory) -> None:
        """Register widget factory for cleanup."""
        self._widget_factories.append(factory)
        _active_fixtures.add(factory)

    def register_dialog_factory(self, factory: SafeDialogFactory) -> None:
        """Register dialog factory for cleanup."""
        self._dialog_factories.append(factory)
        _active_fixtures.add(factory)

    def register_cleanup(self, cleanup_func: Callable[[], None]) -> None:
        """Register custom cleanup function."""
        self._cleanup_functions.append(cleanup_func)

    def _stop_all_qthreads(self) -> None:
        """Stop all running QThreads to prevent crashes during cleanup.

        This is critical for safe cleanup - running threads that access Qt objects
        will cause fatal aborts if those objects are deleted during cleanup.
        """
        try:
            from PySide6.QtCore import QThread
        except ImportError:
            return  # No Qt available

        # Find all active QThread instances
        import gc

        threads_to_stop = []
        for obj in gc.get_objects():
            try:
                if isinstance(obj, QThread) and obj.isRunning():
                    threads_to_stop.append(obj)
            except (RuntimeError, TypeError):
                # Object might be deleted or invalid
                continue

        if not threads_to_stop:
            return

        logger.debug(f"Stopping {len(threads_to_stop)} running QThread(s) before cleanup")

        # Request all threads to stop
        for thread in threads_to_stop:
            with suppress(RuntimeError):
                # Try to stop gracefully if the thread has a stop method
                if hasattr(thread, 'stop'):
                    thread.stop()
                elif hasattr(thread, 'requestInterruption'):
                    thread.requestInterruption()

        # Wait for threads to finish (with timeout)
        for thread in threads_to_stop:
            with suppress(RuntimeError):
                if thread.isRunning():
                    thread.wait(500)  # 500ms timeout per thread

        # Process events to let threads clean up
        try:
            from PySide6.QtWidgets import QApplication
            app = QApplication.instance()
            if app:
                app.processEvents()
        except (ImportError, RuntimeError):
            pass

    def cleanup_all(self) -> None:
        """Cleanup all managed fixtures."""
        with _fixture_cleanup_lock:
            # FIRST: Stop all running QThreads to prevent crashes
            self._stop_all_qthreads()

            # Custom cleanup functions
            for cleanup_func in self._cleanup_functions:
                with suppress(Exception):
                    cleanup_func()

            # Cleanup qtbots
            for qtbot in self._qtbots:
                with suppress(Exception):
                    qtbot.cleanup()

            # Cleanup factories
            for factory in self._widget_factories + self._dialog_factories:
                with suppress(Exception):
                    factory.cleanup()

            # Cleanup apps last
            for app in self._apps:
                with suppress(Exception):
                    app.cleanup()

            # Clear all lists
            self._qtbots.clear()
            self._apps.clear()
            self._widget_factories.clear()
            self._dialog_factories.clear()
            self._cleanup_functions.clear()

# Global fixture manager instance
_fixture_manager = SafeFixtureManager()

# Factory functions for creating safe fixtures

def create_safe_qtbot(
    request: FixtureRequest | None = None,
    timeout_override: int | None = None,
    allow_mock: bool = False,
) -> SafeQtBotProtocol:
    """
    Create safe qtbot that works with real Qt in offscreen mode.

    By default, this function requires real Qt and fails loudly if unavailable.
    Use allow_mock=True only for tests that explicitly don't need real Qt behavior.

    Args:
        request: Pytest fixture request (optional)
        timeout_override: Override default timeouts for specific tests
        allow_mock: If True, allow mock fallback. If False (default), require real Qt.

    Returns:
        Safe qtbot implementation (real in offscreen mode, or mock if allow_mock=True)

    Raises:
        HeadlessModeError: If real Qt unavailable and allow_mock=False
    """
    import os

    env_info = get_environment_info()

    # In headless mode without xvfb, ensure offscreen platform is configured
    if env_info.is_headless and not env_info.xvfb_available:
        os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

    # Try to create real qtbot with offscreen rendering
    try:
        import pytestqt  # noqa: F401

        # Get real qtbot from pytest-qt if available
        real_qtbot = None
        qtbot_error: Exception | None = None
        if request and hasattr(request, 'getfixturevalue'):
            try:
                real_qtbot = request.getfixturevalue('qtbot')
            except Exception as e:
                logger.debug(f"Could not get real qtbot from request: {e}")
                qtbot_error = e

        # Fail loudly if we couldn't get real qtbot and mocks aren't allowed
        if real_qtbot is None and not allow_mock:
            error_msg = (
                f"Cannot create real qtbot: getfixturevalue('qtbot') returned None "
                f"(error: {qtbot_error})\n"
                "Options:\n"
                "  1. Ensure pytest-qt fixture is properly configured\n"
                "  2. Use mock_qtbot fixture for tests that don't need real Qt\n"
                "  3. Mark test with @pytest.mark.mock_qt"
            )
            if qtbot_error:
                raise HeadlessModeError(error_msg) from qtbot_error
            else:
                raise HeadlessModeError(error_msg)

        qtbot = SafeQtBot(real_qtbot=real_qtbot, headless=real_qtbot is None)
        if real_qtbot is not None:
            logger.info("Created real qtbot wrapper (offscreen mode if headless)")
        else:
            logger.info("Created mock qtbot wrapper (allow_mock=True)")

    except ImportError as e:
        # pytest-qt not available
        if allow_mock:
            qtbot = SafeQtBot(headless=True)
            logger.warning(f"pytest-qt not available, using mock qtbot (allow_mock=True): {e}")
        else:
            raise HeadlessModeError(
                f"Cannot create real qtbot: pytest-qt not available ({e})\n"
                "Options:\n"
                "  1. Install pytest-qt: pip install pytest-qt\n"
                "  2. Use mock_qtbot fixture for tests that don't need real Qt\n"
                "  3. Mark test with @pytest.mark.mock_qt"
            ) from e

    except Exception as e:
        # Other Qt initialization errors
        if allow_mock:
            qtbot = SafeQtBot(headless=True)
            logger.warning(f"Qt initialization failed, using mock qtbot (allow_mock=True): {e}")
        else:
            raise HeadlessModeError(
                f"Cannot create real qtbot: {e}\n"
                "Options:\n"
                "  1. Set QT_QPA_PLATFORM=offscreen for headless environments\n"
                "  2. Install xvfb and run with: xvfb-run pytest\n"
                "  3. Use mock_qtbot fixture for tests that don't need real Qt"
            ) from e

    # Register for cleanup
    _fixture_manager.register_qtbot(qtbot)

    return qtbot  # type: ignore[return-value]  # Runtime protocol compliance

def create_safe_qapp(
    args: list[str] | None = None,
    allow_mock: bool = False,
) -> SafeQApplicationProtocol:
    """
    Create safe QApplication that works with real Qt in offscreen mode.

    By default, this function requires real Qt and fails loudly if unavailable.
    Use allow_mock=True only for tests that explicitly don't need real Qt behavior.

    Args:
        args: Command line arguments for QApplication
        allow_mock: If True, allow mock fallback. If False (default), require real Qt.

    Returns:
        Safe QApplication implementation (real in offscreen mode, or mock if allow_mock=True)

    Raises:
        HeadlessModeError: If real Qt unavailable and allow_mock=False
    """
    import os

    env_info = get_environment_info()

    # In headless mode without xvfb, ensure offscreen platform is configured
    if env_info.is_headless and not env_info.xvfb_available:
        os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

    # Try to create real QApplication with offscreen rendering
    try:
        app = SafeQApplication(headless=False, args=args)
        logger.info("Created real QApplication (offscreen mode if headless)")

    except Exception as e:
        if allow_mock:
            app = SafeQApplication(headless=True, args=args)
            logger.warning(f"QApplication creation failed, using mock (allow_mock=True): {e}")
        else:
            raise HeadlessModeError(
                f"Cannot create real QApplication: {e}\n"
                "Options:\n"
                "  1. Set QT_QPA_PLATFORM=offscreen for headless environments\n"
                "  2. Install xvfb and run with: xvfb-run pytest\n"
                "  3. Use allow_mock=True for tests that don't need real Qt"
            ) from e

    # Register for cleanup
    _fixture_manager.register_app(app)

    return app  # type: ignore[return-value]  # Runtime protocol compliance

def create_safe_widget_factory() -> SafeWidgetFactory:
    """
    Create safe widget factory for environment-appropriate widget creation.

    Returns:
        SafeWidgetFactory instance
    """
    factory = SafeWidgetFactory()
    _fixture_manager.register_widget_factory(factory)
    return factory

def create_safe_dialog_factory() -> SafeDialogFactory:
    """
    Create safe dialog factory for environment-appropriate dialog creation.

    Returns:
        SafeDialogFactory instance
    """
    factory = SafeDialogFactory()
    _fixture_manager.register_dialog_factory(factory)
    return factory

@contextmanager
def safe_qt_context(request: FixtureRequest | None = None) -> Generator[dict[str, Any], None, None]:
    """
    Context manager providing complete safe Qt environment.

    Creates and manages a full Qt environment (app, qtbot, factories) with
    automatic cleanup on exit.

    Args:
        request: Pytest fixture request for integration with pytest-qt

    Yields:
        Dictionary containing Qt environment components:
        - qapp: Safe QApplication
        - qtbot: Safe qtbot
        - widget_factory: Safe widget factory
        - dialog_factory: Safe dialog factory
    """
    env_info = get_environment_info()

    # Create Qt environment components
    qapp = create_safe_qapp()
    qtbot = create_safe_qtbot(request)
    widget_factory = create_safe_widget_factory()
    dialog_factory = create_safe_dialog_factory()

    qt_context = {
        'qapp': qapp,
        'qtbot': qtbot,
        'widget_factory': widget_factory,
        'dialog_factory': dialog_factory,
        'env_info': env_info,
    }

    try:
        logger.info(f"Entering safe Qt context (headless={env_info.is_headless})")
        yield qt_context
    finally:
        # Cleanup is handled by fixture manager
        logger.info("Exiting safe Qt context")

def validate_fixture_environment() -> dict[str, Any]:
    """
    Validate that fixture environment is working correctly.

    Returns:
        Dictionary with validation results and environment information
    """
    env_info = get_environment_info()
    results = {
        'environment': {
            'headless': env_info.is_headless,
            'ci': env_info.is_ci,
            'display_available': env_info.has_display,
            'xvfb_available': env_info.xvfb_available,
            'qt_available': env_info.pyside6_available,
        },
        'fixtures': {
            'qtbot_created': False,
            'qapp_created': False,
            'widget_factory_created': False,
            'dialog_factory_created': False,
        },
        'errors': [],
    }

    # Test qtbot creation
    try:
        qtbot = create_safe_qtbot()
        results['fixtures']['qtbot_created'] = True
        qtbot.cleanup()
    except Exception as e:
        results['errors'].append(f"qtbot creation failed: {e}")

    # Test QApplication creation
    try:
        qapp = create_safe_qapp()
        results['fixtures']['qapp_created'] = True
        qapp.cleanup()
    except Exception as e:
        results['errors'].append(f"QApplication creation failed: {e}")

    # Test widget factory
    try:
        factory = create_safe_widget_factory()
        factory.create_widget('QWidget')
        results['fixtures']['widget_factory_created'] = True
        factory.cleanup()
    except Exception as e:
        results['errors'].append(f"Widget factory creation failed: {e}")

    # Test dialog factory
    try:
        factory = create_safe_dialog_factory()
        factory.create_dialog('QDialog')
        results['fixtures']['dialog_factory_created'] = True
        factory.cleanup()
    except Exception as e:
        results['errors'].append(f"Dialog factory creation failed: {e}")

    return results

def cleanup_all_fixtures() -> None:
    """Global cleanup function for all fixtures."""
    _fixture_manager.cleanup_all()

# Error reporting functions

def report_fixture_error(fixture_name: str, error: Exception, request: FixtureRequest | None = None) -> None:
    """
    Report fixture creation/usage errors with context.

    Args:
        fixture_name: Name of the fixture that failed
        error: Exception that occurred
        request: Pytest request object for context
    """
    env_info = get_environment_info()

    error_context = {
        'fixture': fixture_name,
        'error': str(error),
        'error_type': type(error).__name__,
        'environment': {
            'headless': env_info.is_headless,
            'ci': env_info.is_ci,
            'display': env_info.has_display,
            'xvfb': env_info.xvfb_available,
        }
    }

    if request:
        error_context['test'] = {
            'node_id': request.node.nodeid,
            'markers': [marker.name for marker in request.node.iter_markers()],
        }

    logger.error(f"Fixture error in {fixture_name}: {error}", extra=error_context)

    # Issue warning for test developers
    warnings.warn(
        f"Fixture {fixture_name} failed: {error}. "
        f"Environment: headless={env_info.is_headless}, "
        f"display={env_info.has_display}, xvfb={env_info.xvfb_available}",
        UserWarning,
        stacklevel=3
    )

# Compatibility and migration helpers

def migrate_to_safe_fixtures(test_function: Callable[..., Any]) -> Callable[..., Any]:
    """
    Decorator to migrate existing tests to use safe fixtures.

    This decorator helps with gradual migration by wrapping test functions
    to use safe fixtures instead of direct Qt fixture access.
    """
    from functools import wraps

    @wraps(test_function)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        # If qtbot is in kwargs, replace with safe qtbot
        if 'qtbot' in kwargs:
            try:
                kwargs['qtbot'] = create_safe_qtbot()
            except Exception as e:
                report_fixture_error('qtbot', e)
                raise

        # If qapp is in kwargs, replace with safe qapp
        if 'qapp' in kwargs:
            try:
                kwargs['qapp'] = create_safe_qapp()
            except Exception as e:
                report_fixture_error('qapp', e)
                raise

        return test_function(*args, **kwargs)

    return wrapper

# Export all public functions and classes
__all__ = [
    'SafeDialogFactory',
    'SafeFixtureManager',
    'SafeQApplication',
    'SafeQApplicationProtocol',
    # Core classes
    'SafeQtBot',
    # Protocol interfaces
    'SafeQtBotProtocol',
    'SafeWidgetFactory',
    'SafeWidgetProtocol',
    # Exceptions
    'WidgetCreationError',
    'cleanup_all_fixtures',
    'create_safe_dialog_factory',
    'create_safe_qapp',
    # Factory functions
    'create_safe_qtbot',
    'create_safe_widget_factory',
    'migrate_to_safe_fixtures',
    'report_fixture_error',
    # Context managers and utilities
    'safe_qt_context',
    'validate_fixture_environment',
]
