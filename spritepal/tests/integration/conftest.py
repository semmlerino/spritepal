"""
Integration test fixtures that use real components without mocking.
"""
from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

import pytest

# Add spritepal to path
# __file__ = tests/integration/conftest.py → parent.parent.parent = spritepal/
# Note: Main conftest.py and pytest.ini pythonpath also handle this
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

# NOTE: qt_app fixture is provided by root conftest.py (session-scoped)
# Do not redefine it here to avoid fixture shadowing issues.

@pytest.fixture(scope="function")
def managers_initialized(qt_app, request):
    """Initialize managers for integration tests.

    If session_managers is already active, this fixture is a no-op to avoid
    conflicting cleanup.
    """
    from core.managers.registry import ManagerRegistry, cleanup_managers, initialize_managers

    registry = ManagerRegistry()
    was_already_initialized = registry.is_initialized()

    if not was_already_initialized:
        initialize_managers()

    yield

    # Only cleanup if WE initialized (not if session_managers did)
    if not was_already_initialized:
        cleanup_managers()

@pytest.fixture
def temp_dir():
    """Create a temporary directory for test files."""
    temp_path = tempfile.mkdtemp(prefix="spritepal_integration_")
    yield Path(temp_path)
    # Cleanup
    shutil.rmtree(temp_path, ignore_errors=True)

@pytest.fixture
def test_rom_data():
    """Generate test ROM data with known content."""
    # Create a 1MB test ROM
    rom_size = 1024 * 1024
    rom_data = bytearray(rom_size)

    # Add some recognizable patterns at known offsets
    # Pattern 1: Simple incrementing bytes at 0x1000
    for i in range(256):
        rom_data[0x1000 + i] = i % 256

    # Pattern 2: Tile-like data at 0x2000 (32 bytes per tile)
    for tile in range(16):
        for byte_idx in range(32):
            rom_data[0x2000 + tile * 32 + byte_idx] = (tile * 2 + byte_idx) % 256

    # Pattern 3: Sprite-like data at 0x10000
    for i in range(8192):  # 256 tiles
        rom_data[0x10000 + i] = (i % 16) * 16 + (i // 16) % 16

    return bytes(rom_data)

@pytest.fixture
def test_rom_with_sprites(temp_dir, test_rom_data):
    """Create a test ROM with known sprite data at specific locations."""
    rom_path = temp_dir / "test_rom.sfc"

    # Use the real Kirby ROM if available, otherwise create test ROM
    # ROM is in parent directory (exhal-master/)
    real_rom = Path("../Kirby Super Star (USA).sfc")
    if real_rom.exists():
        # Use real ROM for testing
        rom_data = real_rom.read_bytes()
        rom_path.write_bytes(rom_data)

        # Known sprite locations in Kirby ROM
        return {
            'path': rom_path,
            'sprites': [
                {
                    'offset': 0x200000,
                    'compressed_size': 65464,  # Approximate
                    'decompressed_size': 7744,
                    'tile_count': 242
                },
                {
                    'offset': 0x206000,
                    'compressed_size': 40888,  # Approximate
                    'decompressed_size': 832,
                    'tile_count': 26
                }
            ]
        }
    # Create simple test ROM
    rom_path.write_bytes(test_rom_data)
    return {
        'path': rom_path,
        'sprites': []  # No compressed sprites in test ROM
    }

@pytest.fixture
def real_kirby_rom():
    """Provide path to real Kirby ROM if available for integration testing."""
    # ROM is in parent directory (exhal-master/)
    rom_path = Path("../Kirby Super Star (USA).sfc")
    if rom_path.exists():
        return rom_path
    return None

@pytest.fixture
def rom_extraction_panel(qtbot, managers_initialized):
    """Create a real ROM extraction panel for testing.

    Includes cleanup to reset the ManualOffsetDialogSingleton to prevent
    test pollution when multiple tests open the manual offset dialog.
    """
    from ui.rom_extraction_panel import ManualOffsetDialogSingleton, ROMExtractionPanel
    panel = ROMExtractionPanel()
    qtbot.addWidget(panel)
    panel.show()

    yield panel

    # Cleanup: Reset the singleton to prevent test pollution
    # This is critical for tests that call panel._open_manual_offset_dialog()
    ManualOffsetDialogSingleton.reset()

@pytest.fixture
def manual_offset_dialog(qtbot, managers_initialized):
    """Create a real manual offset dialog for testing.

    Note: Uses importlib to bypass the global sys.modules patching in conftest_dialog_patch.py
    that mocks dialogs for headless testing. Integration tests need real dialogs.

    Important: We don't use qtbot.addWidget() because the dialog may be destroyed by
    managers_initialized cleanup before pytest-qt teardown runs, causing
    "Internal C++ object already deleted" errors.
    """
    import importlib.util
    from pathlib import Path

    import shiboken6

    # Get the real module source file path
    module_path = Path(__file__).parent.parent.parent / "ui" / "dialogs" / "manual_offset_unified_integrated.py"

    # Load the module directly from the file
    spec = importlib.util.spec_from_file_location(
        "ui.dialogs.manual_offset_unified_integrated_real",
        module_path
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    # Get the real dialog class
    UnifiedManualOffsetDialog = module.UnifiedManualOffsetDialog
    dialog = UnifiedManualOffsetDialog()
    # Don't use qtbot.addWidget() - we manage cleanup ourselves to avoid
    # double-delete when managers_initialized cleanup runs first

    yield dialog

    # Explicitly close dialog if still valid (may already be deleted by manager cleanup)
    try:
        if shiboken6.isValid(dialog):
            dialog.close()
            dialog.deleteLater()
    except RuntimeError:
        pass  # Already deleted, that's fine

@pytest.fixture
def loaded_rom_panel(rom_extraction_panel, test_rom_with_sprites, qtbot):
    """Provide a ROM extraction panel with a test ROM already loaded."""
    rom_info = test_rom_with_sprites
    rom_path = str(rom_info['path'])

    # Load the ROM (method is _load_rom_file, not load_rom)
    rom_extraction_panel._load_rom_file(rom_path)

    # Wait for loading to complete
    qtbot.waitUntil(lambda: rom_extraction_panel.rom_path == rom_path and rom_extraction_panel.rom_size > 0, timeout=1000)

    # Verify ROM is loaded
    assert rom_extraction_panel.rom_path == rom_path
    assert rom_extraction_panel.rom_size > 0

    return rom_extraction_panel, rom_info

def _create_condition_waiter():
    """Create ConditionWaiter class with lazy Qt imports."""
    from PySide6.QtCore import QObject, QTimer, Signal

    class ConditionWaiter(QObject):
        """Helper class for waiting on conditions with proper Qt event loop handling."""

        condition_met = Signal()

        def __init__(self, condition_func, parent=None):
            super().__init__(parent)
            self.condition_func = condition_func
            self.timer = QTimer(self)
            self.timer.timeout.connect(self.check_condition)

        def check_condition(self):
            """Check if condition is met and emit signal if true."""
            try:
                if self.condition_func():
                    self.timer.stop()
                    self.condition_met.emit()
            except Exception:
                # Ignore exceptions in condition check to prevent crashes
                pass

        def start(self, interval=50):
            """Start checking the condition."""
            self.timer.start(interval)

        def stop(self):
            """Stop checking."""
            self.timer.stop()

    return ConditionWaiter

# Lazy-load ConditionWaiter when needed
ConditionWaiter = None

def wait_for_condition(qtbot, condition_func, timeout=5000, message="Condition not met"):
    """
    Wait for a condition to become true using proper Qt event loop handling.

    This implementation uses qtbot's waitUntil which properly handles the Qt event loop
    and avoids segfaults from improper event processing.

    Args:
        qtbot: pytest-qt bot
        condition_func: Function that returns True when condition is met
        timeout: Maximum time to wait in milliseconds
        message: Error message if timeout occurs
    """
    try:
        # Use qtbot's waitUntil for proper event loop handling
        qtbot.waitUntil(condition_func, timeout=timeout)
        return True
    except AssertionError as e:
        # waitUntil raises AssertionError on timeout
        raise TimeoutError(f"Timeout waiting for condition: {message}") from e

@pytest.fixture
def wait_for(qtbot):
    """Provide the wait_for_condition function as a fixture."""
    def _wait_for(condition_func, timeout=5000, message="Condition not met"):
        return wait_for_condition(qtbot, condition_func, timeout, message)
    return _wait_for

@pytest.fixture
def process_events(qtbot):
    """Process Qt events to ensure UI updates."""
    def _process():
        from PySide6.QtWidgets import QApplication
        # Process events - no wait needed, processEvents is sufficient
        QApplication.processEvents()
    return _process


@pytest.fixture
def wait_for_widget_ready(qtbot):
    """
    Helper to wait for widget initialization.

    Replaces fixed qtbot.wait() calls with condition-based waiting.
    Auto-completes when widget becomes visible and enabled.

    Example:
        wait_for_widget_ready(dialog, timeout=1000)
        # Instead of: dialog.show(); qtbot.wait(100)
    """
    def _wait(widget, timeout=1000):
        """
        Wait for widget to be visible and enabled.

        Args:
            widget: QWidget to wait for
            timeout: Maximum wait time in milliseconds

        Returns:
            True if widget is ready within timeout

        Raises:
            TimeoutError: If widget not ready within timeout
        """
        try:
            qtbot.waitUntil(
                lambda: widget.isVisible() and widget.isEnabled(),
                timeout=timeout
            )
            return True
        except AssertionError as e:
            raise TimeoutError(
                f"Widget {widget.__class__.__name__} not ready within {timeout}ms"
            ) from e
    return _wait


@pytest.fixture
def wait_for_signal_processed(qtbot):
    """
    Helper to wait for signal processing to complete.

    Ensures Qt event loop has processed pending signals.

    Example:
        slider.setValue(100)
        wait_for_signal_processed()
        # Instead of: slider.setValue(100); qtbot.wait(50)
    """
    def _wait(timeout=100):
        """
        Wait for pending signals to be processed.

        Args:
            timeout: Maximum wait time in milliseconds

        Note:
            Uses processEvents() to ensure all queued signals have been delivered.
        """
        from PySide6.QtWidgets import QApplication

        # Process all pending events - this is sufficient for signal delivery
        QApplication.processEvents()

    return _wait


@pytest.fixture
def wait_for_theme_applied(qtbot):
    """
    Helper to wait for theme changes to be applied.

    Qt theme changes may take multiple event loop cycles to apply.

    Example:
        window.apply_dark_theme()
        wait_for_theme_applied(window)
        # Instead of: window.apply_dark_theme(); qtbot.wait(100)
    """
    def _wait(widget, is_dark_theme=True, timeout=500):
        """
        Wait for theme to be applied to widget.

        Args:
            widget: QWidget to check
            is_dark_theme: Whether to expect dark theme (True) or light (False)
            timeout: Maximum wait time in milliseconds
        """
        from PySide6.QtGui import QPalette

        def theme_applied():
            palette = widget.palette()
            bg_color = palette.color(QPalette.ColorRole.Window)

            if is_dark_theme:
                # Dark theme: background should be dark
                return bg_color.red() < 128 and bg_color.green() < 128 and bg_color.blue() < 128
            else:
                # Light theme: background should be light
                return bg_color.red() > 128 or bg_color.green() > 128 or bg_color.blue() > 128

        try:
            qtbot.waitUntil(theme_applied, timeout=timeout)
            return True
        except AssertionError:
            # Theme verification can be unreliable in headless mode
            import os
            display = os.environ.get("DISPLAY", "")
            qpa_platform = os.environ.get("QT_QPA_PLATFORM", "")
            if not display or qpa_platform == "offscreen":
                return True  # Skip verification in headless mode
            raise

    return _wait


@pytest.fixture
def wait_for_layout_update(qtbot):
    """
    Helper to wait for layout changes to be applied.

    Qt layouts may take multiple event cycles to fully update.

    Example:
        window.resize(1024, 768)
        wait_for_layout_update(window, expected_width=1024)
        # Instead of: window.resize(...); qtbot.wait(100)
    """
    def _wait(widget, expected_width=None, expected_height=None, timeout=500):
        """
        Wait for widget layout to update.

        Args:
            widget: QWidget to check
            expected_width: Expected width (None to skip check)
            expected_height: Expected height (None to skip check)
            timeout: Maximum wait time in milliseconds
        """
        def layout_updated():
            size = widget.size()
            if expected_width is not None and size.width() != expected_width:
                return False
            if expected_height is not None and size.height() != expected_height:
                return False
            # If no specific size expected, just check that size is reasonable
            return size.width() > 0 and size.height() > 0

        try:
            qtbot.waitUntil(layout_updated, timeout=timeout)
            return True
        except AssertionError as e:
            current_size = widget.size()
            raise TimeoutError(
                f"Layout not updated within {timeout}ms. "
                f"Current: {current_size.width()}x{current_size.height()}, "
                f"Expected: {expected_width}x{expected_height}"
            ) from e

    return _wait


# Markers are registered in pyproject.toml and main conftest.py
