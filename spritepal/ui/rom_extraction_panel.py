"""
ROM extraction panel for SpritePal
"""

from __future__ import annotations

import threading
from operator import itemgetter
from pathlib import Path
from typing import Any

from PySide6.QtCore import Signal
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QSpacerItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)
from typing_extensions import override

from core.managers import get_extraction_manager
from ui.common import WorkerManager
from ui.components.navigation import SpriteNavigator
from ui.dialogs import ResumeScanDialog, UnifiedManualOffsetDialog, UserErrorDialog
from ui.rom_extraction.state_manager import (
    ExtractionState,
    ExtractionStateManager,
)
from ui.rom_extraction.widgets import (
    CGRAMSelectorWidget,
    ModeSelectorWidget,
    OutputNameWidget,
    ROMFileWidget,
    SpriteSelectorWidget,
)
from ui.rom_extraction.workers import SpriteScanWorker
from ui.rom_extraction.workers.similarity_indexing_worker import (
    SimilarityIndexingWorker,
)
from ui.workers.rom_info_loader_worker import ROMHeaderLoaderWorker, ROMInfoLoaderWorker
from utils.constants import (
    SETTINGS_KEY_LAST_INPUT_ROM,
    SETTINGS_NS_ROM_INJECTION,
)
from utils.logging_config import get_logger
from utils.settings_manager import get_settings_manager
from utils.thread_safe_singleton import QtThreadSafeSingleton

logger = get_logger(__name__)

class ScanDialog(QDialog):
    """Dialog for sprite scanning with typed attributes."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        # Typed attributes that will be set during initialization
        self.cache_status_label: QLabel
        self.progress_bar: QProgressBar
        self.results_text: QTextEdit
        self.button_box: QDialogButtonBox
        self.apply_btn: QPushButton | None
        self.rom_cache: Any = None  # Cache object, type depends on implementation

# UI Spacing Constants
SPACING_SMALL = 6
SPACING_MEDIUM = 10
SPACING_LARGE = 16
SPACING_XLARGE = 20
BUTTON_MIN_HEIGHT = 32
COMBO_MIN_WIDTH = 200
BUTTON_MAX_WIDTH = 150
LABEL_MIN_WIDTH = 120

class ManualOffsetDialogSingleton(QtThreadSafeSingleton["UnifiedManualOffsetDialog"]):
    """
    Thread-safe application-wide singleton for manual offset dialog.
    Ensures only one dialog instance exists across the entire application.

    This singleton uses proper thread synchronization and Qt thread affinity checking
    to prevent crashes when accessed from worker threads.
    """
    _instance: UnifiedManualOffsetDialog | None = None
    _creator_panel: ROMExtractionPanel | None = None
    _destroyed: bool = False  # Track if the dialog has been destroyed
    _lock = threading.Lock()

    @classmethod
    @override
    def _create_instance(cls, creator_panel: ROMExtractionPanel | None = None) -> UnifiedManualOffsetDialog:
        """Create a new dialog instance (thread-safe, main thread only)."""
        # Ensure we're on the main thread for Qt object creation
        cls._ensure_main_thread()

        logger.debug("Creating new ManualOffsetDialog singleton instance")

        # Reset destroyed flag when creating new instance
        cls._destroyed = False

        # Create new instance with None as parent to avoid widget hierarchy contamination
        try:
            logger.debug("Creating UnifiedManualOffsetDialog instance...")
            instance = UnifiedManualOffsetDialog(None)
            cls._creator_panel = creator_panel

            logger.debug(f"New dialog created with ID: {getattr(instance, '_debug_id', 'Unknown')}")

            # Test if the dialog object is still valid
            logger.debug(f"DEBUGGING: Dialog object type: {type(instance)}")
            logger.debug(f"DEBUGGING: Dialog isVisible(): {instance.isVisible()}")
            logger.debug(f"DEBUGGING: Dialog windowTitle(): {instance.windowTitle()}")

            # Try to access the finished signal to see if it exists
            logger.debug("DEBUGGING: About to test signal access...")
            try:
                signal_obj = instance.finished
                logger.debug(f"DEBUGGING: Successfully accessed finished signal: {signal_obj}")
            except Exception as e:
                logger.error(f"DEBUGGING: Cannot access finished signal: {e}")

            # Defer signal connection until dialog is shown to avoid Qt race condition
            logger.debug("Deferring signal connection until dialog is shown...")

            def _connect_signals_when_shown():
                """Connect signals after dialog is fully shown and ready."""
                try:
                    logger.debug("Connecting Qt dialog signals via QtDialogSignalManager...")
                    # Connect to QtDialogSignalManager instead of corrupted inherited signals
                    qt_signal_manager = instance.get_component("qt_dialog_signals")
                    if qt_signal_manager:
                        qt_signal_manager.finished.connect(cls._on_dialog_closed)
                        qt_signal_manager.rejected.connect(cls._on_dialog_closed)
                        qt_signal_manager.destroyed.connect(cls._on_dialog_destroyed)
                        logger.debug("All Qt dialog signals connected successfully via QtDialogSignalManager")
                    else:
                        logger.error("QtDialogSignalManager component not found - cannot connect Qt dialog signals")
                except Exception as e:
                    logger.error(f"Failed to connect signals after show: {e}")

            # Store the connection function to call after show
            instance._deferred_signal_connection = _connect_signals_when_shown

        except Exception as e:
            logger.error(f"Error during dialog creation or signal connection: {e}")
            import traceback
            logger.error(f"Full traceback: {traceback.format_exc()}")
            raise

        return instance

    @classmethod
    def get_dialog(cls, creator_panel: ROMExtractionPanel) -> UnifiedManualOffsetDialog:
        """Get or create the singleton dialog instance (thread-safe)."""
        logger.debug("ManualOffsetDialogSingleton.get_dialog called")
        logger.debug(f"Current instance exists: {cls._instance is not None}")

        # Get instance using thread-safe pattern
        instance = cls.get(creator_panel)

        # Check if the dialog was marked as destroyed
        if cls._destroyed:
            logger.debug("Dialog was destroyed, creating new instance")
            cls.reset()
            instance = cls.get(creator_panel)

        # Check if existing instance is still valid (only on main thread)
        if cls.safe_qt_call(lambda: instance.isVisible()):
            logger.debug(f"Reusing existing ManualOffsetDialog singleton instance (ID: {getattr(instance, '_debug_id', 'Unknown')})")
            return instance
        # Dialog exists but is not visible - check if it's still valid
        try:
            cls._ensure_main_thread()
            # Test if the dialog is still valid by accessing windowTitle (this will throw RuntimeError if deleted)
            _ = instance.windowTitle()
            logger.debug("[DEBUG] Existing dialog not visible, but still valid")
        except RuntimeError:
            # Dialog has been destroyed by Qt but our reference is stale
            logger.debug("Stale dialog reference detected, cleaning up")
            cls.reset()
            # Get new instance
            instance = cls.get(creator_panel)

        return instance

    @classmethod
    def _on_dialog_closed(cls):
        """Handle dialog close event for cleanup (thread-safe)."""
        logger.debug("Manual offset dialog closed, scheduling cleanup")

        # Use thread-safe cleanup
        with cls._lock:
            if cls._instance is not None:
                # Schedule deletion on main thread
                instance = cls._instance  # Capture reference to avoid race condition
                cls.safe_qt_call(lambda: instance.deleteLater() if instance else None)  # type: ignore[arg-type]
                cls._cleanup_instance(cls._instance)
                cls._instance = None  # Clear the instance reference

    @classmethod
    def _on_dialog_destroyed(cls):
        """Handle dialog destroyed signal for ultimate cleanup (thread-safe)."""
        logger.debug("Manual offset dialog destroyed signal received")
        with cls._lock:
            cls._destroyed = True
        cls.reset()

    @classmethod
    @override
    def reset(cls):
        """Reset the singleton instance and all associated state."""
        cls._destroyed = False
        super().reset()

    @classmethod
    @override
    def _cleanup_instance(cls, instance: UnifiedManualOffsetDialog) -> None:
        """Clean up the singleton instance (thread-safe)."""
        logger.debug("Cleaning up ManualOffsetDialog singleton instance")
        cls._creator_panel = None
        # Parent class handles instance cleanup

    @classmethod
    def is_dialog_open(cls) -> bool:
        """Check if dialog is currently open (thread-safe)."""
        if cls._instance is None:
            return False

        # Use safe Qt call to check visibility
        instance = cls._instance  # Capture reference to avoid race condition
        is_visible = cls.safe_qt_call(lambda: instance.isVisible() if instance else False)  # type: ignore[arg-type]
        return is_visible is True  # Handle None return from safe_qt_call

    @classmethod
    def get_current_dialog(cls) -> UnifiedManualOffsetDialog | None:
        """Get current dialog instance if it exists and is visible (thread-safe)."""
        if cls._instance is None:
            return None

        # Check if dialog is visible using thread-safe method
        instance = cls._instance  # Capture reference to avoid race condition
        is_visible = cls.safe_qt_call(lambda: instance.isVisible() if instance else False)  # type: ignore[arg-type]
        return cls._instance if is_visible else None

class ROMExtractionPanel(QWidget):
    """Panel for ROM-based sprite extraction"""

    # Signals
    files_changed = Signal()
    extraction_ready = Signal(bool)
    rom_extraction_requested = Signal(
        str, int, str, str
    )  # rom_path, offset, output_base, sprite_name
    output_name_changed = Signal(str)  # Emit when output name changes in ROM panel

    def __init__(self, parent: Any | None = None):
        super().__init__(parent)
        self.rom_path = ""
        self.sprite_locations = {}
        # Get extraction manager and ROM extractor
        self.extraction_manager = get_extraction_manager()
        self.rom_extractor = self.extraction_manager.get_rom_extractor()
        self.rom_size = 0  # Track ROM size for slider limits
        self._manual_offset_mode = True  # Default to manual offset mode

        # State manager for coordinating operations
        self.state_manager = ExtractionStateManager()
        self.state_manager.state_changed.connect(self._on_state_changed)

        # Worker references to track and clean up
        self.search_worker = None
        self.scan_worker = None
        self.similarity_indexing_worker = None
        self._header_loader: ROMHeaderLoaderWorker | None = None
        self._sprite_location_loader: ROMInfoLoaderWorker | None = None

        # Navigation components
        self.sprite_navigator = None

        self._setup_ui()
        self._load_last_rom()

    def _setup_ui(self):
        """Initialize the user interface"""
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(0, 0, 0, 0)

        # Create main panel with controls
        main_panel = self._create_main_panel()
        main_layout.addWidget(main_panel)
        self.setLayout(main_layout)

    def _create_main_panel(self) -> QWidget:
        """Create the main panel containing all controls.

        Returns:
            QWidget: The configured main panel
        """
        main_panel = QWidget(self)
        layout = QVBoxLayout()
        layout.setSpacing(SPACING_LARGE)
        layout.setContentsMargins(SPACING_MEDIUM, SPACING_MEDIUM, SPACING_MEDIUM, SPACING_MEDIUM)

        # Add all widget groups
        self._add_rom_controls(layout)
        self._add_navigation_controls(layout)
        self._add_mode_controls(layout)
        self._add_manual_offset_controls(layout)
        self._add_status_indicators(layout)
        self._add_output_controls(layout)

        # Add vertical spacer at the bottom
        layout.addItem(QSpacerItem(0, 20, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Preferred))
        main_panel.setLayout(layout)
        return main_panel

    def _add_rom_controls(self, layout: QVBoxLayout):
        """Add ROM file selection controls to the layout.

        Args:
            layout: Layout to add controls to
        """
        self.rom_file_widget = ROMFileWidget()
        self.rom_file_widget.browse_clicked.connect(self._browse_rom)
        self.rom_file_widget.partial_scan_detected.connect(self._on_partial_scan_detected)
        layout.addWidget(self.rom_file_widget)

    def _add_navigation_controls(self, layout: QVBoxLayout):
        """Add sprite navigation controls to the layout.

        Args:
            layout: Layout to add controls to
        """
        self.sprite_navigator = SpriteNavigator()
        self.sprite_navigator.offset_changed.connect(self._on_navigator_offset_changed)
        self.sprite_navigator.sprite_selected.connect(self._on_navigator_sprite_selected)
        self.sprite_navigator.setMaximumHeight(120)  # Drastically limit height
        self.sprite_navigator.setVisible(False)  # Hide by default in manual mode
        layout.addWidget(self.sprite_navigator)

    def _add_mode_controls(self, layout: QVBoxLayout):
        """Add mode selection and sprite selector controls to the layout.

        Args:
            layout: Layout to add controls to
        """
        # Mode selector widget
        self.mode_selector_widget = ModeSelectorWidget()
        self.mode_selector_widget.mode_changed.connect(self._on_mode_changed)
        layout.addWidget(self.mode_selector_widget)

        # Sprite selector widget
        self.sprite_selector_widget = SpriteSelectorWidget()
        self.sprite_selector_widget.sprite_changed.connect(self._on_sprite_changed)
        self.sprite_selector_widget.find_sprites_clicked.connect(self._find_sprites)
        self.sprite_selector_widget.setVisible(False)  # Hide by default (manual mode is default)
        layout.addWidget(self.sprite_selector_widget)

    def _add_manual_offset_controls(self, layout: QVBoxLayout):
        """Add manual offset control button and status to the layout.

        Args:
            layout: Layout to add controls to
        """
        # Create and style the manual offset button
        self.manual_offset_button = self._create_manual_offset_button()
        layout.addWidget(self.manual_offset_button)

        # Manual offset status label
        self.manual_offset_status = self._create_manual_offset_status()
        layout.addWidget(self.manual_offset_status)

        # Initialize dialog reference
        self._manual_offset_dialog = None  # Legacy - now managed by singleton
        self._manual_offset = 0x200000  # Default offset

    def _create_manual_offset_button(self) -> QPushButton:
        """Create and configure the manual offset control button.

        Returns:
            QPushButton: The configured button
        """
        button = QPushButton("Open Manual Offset Control")
        button.setMinimumHeight(40)  # Reasonable height
        _ = button.clicked.connect(self._open_manual_offset_dialog)
        button.setVisible(True)  # Show by default (manual mode)
        button.setToolTip("Open advanced manual offset control window (Ctrl+M)")
        button.setStyleSheet(self._get_manual_offset_button_style())
        return button

    def _get_manual_offset_button_style(self) -> str:
        """Get the stylesheet for the manual offset button.

        Returns:
            str: CSS stylesheet
        """
        return """
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #5a9fd4, stop:1 #306998);
                color: white;
                font-weight: bold;
                font-size: 13px;
                border-radius: 6px;
                padding: 8px 16px;
                border: 1px solid #2e5a84;
                min-height: 36px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #6aafea, stop:1 #4079a8);
                border: 1px solid #4488dd;
            }
            QPushButton:pressed {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #306998, stop:1 #204060);
            }
        """

    def _create_manual_offset_status(self) -> QLabel:
        """Create and configure the manual offset status label.

        Returns:
            QLabel: The configured status label
        """
        status = QLabel("Use Manual Offset Control to explore ROM offsets")
        status.setStyleSheet("""
            padding: 8px;
            background: #2b2b2b;
            border: 1px solid #444444;
            border-radius: 4px;
            color: #cccccc;
        """)
        status.setWordWrap(True)
        status.setVisible(True)
        return status

    def _add_status_indicators(self, layout: QVBoxLayout):
        """Add similarity status indicator to the layout.

        Args:
            layout: Layout to add indicators to
        """
        self.similarity_status = QLabel("Similarity search ready")
        if self.similarity_status:
            self.similarity_status.setStyleSheet(self._get_similarity_status_style())
        self.similarity_status.setWordWrap(True)
        self.similarity_status.setVisible(False)  # Hidden until ROM is loaded
        layout.addWidget(self.similarity_status)

    def _get_similarity_status_style(self) -> str:
        """Get the stylesheet for the similarity status label.

        Returns:
            str: CSS stylesheet
        """
        return """
            padding: 6px;
            background: #1a3d5c;
            border: 1px solid #2196f3;
            border-radius: 4px;
            color: #bbdefb;
            font-size: 12px;
        """

    def _add_output_controls(self, layout: QVBoxLayout):
        """Add CGRAM and output name controls to the layout.

        Args:
            layout: Layout to add controls to
        """
        # CGRAM selector widget
        self.cgram_selector_widget = CGRAMSelectorWidget()
        self.cgram_selector_widget.browse_clicked.connect(self._browse_cgram)
        layout.addWidget(self.cgram_selector_widget)

        # Output name widget
        self.output_name_widget = OutputNameWidget()
        self.output_name_widget.text_changed.connect(self._check_extraction_ready)
        self.output_name_widget.text_changed.connect(self.output_name_changed.emit)
        layout.addWidget(self.output_name_widget)

    def _browse_rom(self):
        """Browse for ROM file"""
        settings = get_settings_manager()
        default_dir = settings.get_default_directory()

        filename, _ = QFileDialog.getOpenFileName(
            self,
            "Select ROM File",
            default_dir,
            "SNES ROM Files (*.sfc *.smc);;All Files (*.*)"
        )

        if filename:
            self._load_rom_file(filename)

    def _on_partial_scan_detected(self, scan_info: dict[str, Any]):
        """Handle detection of partial scan cache"""
        # Show resume dialog to ask user what to do
        user_choice = ResumeScanDialog.show_resume_dialog(scan_info, self)

        if user_choice == ResumeScanDialog.RESUME:
            # User wants to resume - trigger scan dialog
            self._find_sprites()
        elif user_choice == ResumeScanDialog.START_FRESH:
            # User wants fresh scan - will be handled when they click Find Sprites
            # Just inform them
            QMessageBox.information(
                self,
                "Fresh Scan",
                "The partial scan cache will be ignored. \n"
                "Click 'Find Sprites' to start a fresh scan."
            )
        # If CANCEL, do nothing

    def _load_last_rom(self):
        """Load the last used ROM file from settings"""
        try:
            settings = get_settings_manager()
            last_rom = settings.get_value(
                SETTINGS_NS_ROM_INJECTION, SETTINGS_KEY_LAST_INPUT_ROM, ""
            )

            if last_rom and Path(last_rom).exists():
                logger.info(f"Loading last used ROM: {last_rom}")
                self._load_rom_file(last_rom)
            elif last_rom:
                logger.warning(f"Last used ROM not found: {last_rom}")
            else:
                logger.debug("No last used ROM in settings")

        except Exception:
            logger.exception("Error loading last ROM")

    def _load_rom_file(self, filename: str):
        """Load a ROM file and update UI"""
        try:
            logger.info(f"Loading ROM file: {filename}")

            # Update internal state
            self.rom_path = filename
            self.rom_file_widget.set_rom_path(filename)

            # Get ROM size for slider limits
            try:
                with Path(filename).open("rb") as f:
                    f.seek(0, 2)  # Seek to end
                    self.rom_size = f.tell()
                    # Update dialog if it exists
                    current_dialog = ManualOffsetDialogSingleton.get_current_dialog()
                    if current_dialog is not None:
                        current_dialog.set_rom_data(self.rom_path, self.rom_size, self.extraction_manager)
                    # Update navigator
                    if self.sprite_navigator is not None:
                        self.sprite_navigator.set_rom_data(self.rom_path, self.rom_size, self.extraction_manager)
                    logger.debug(f"ROM size: {self.rom_size} bytes (0x{self.rom_size:X})")
            except Exception as e:
                logger.warning(f"Could not determine ROM size: {e}")
                self.rom_size = 0x400000  # Default 4MB

            # Save to settings
            settings = get_settings_manager()
            settings.set_value(SETTINGS_NS_ROM_INJECTION, SETTINGS_KEY_LAST_INPUT_ROM, filename)
            settings.set_last_used_directory(str(Path(filename).parent))
            logger.debug(f"Saved ROM to settings: {filename}")

            # Read ROM header asynchronously to prevent UI freeze
            self.rom_file_widget.set_info_text('<span style="color: gray;">Loading ROM header...</span>')
            self._start_header_loading(filename)

            # Note: _load_rom_sprites() and _init_similarity_indexing_worker() will be called
            # from _on_header_loaded callback to ensure proper sequencing

            # Notify that files changed
            self.files_changed.emit()

            logger.info(f"Successfully loaded ROM: {Path(filename).name}")

        except Exception:
            logger.exception("Error loading ROM file %s", filename)
            # Clear ROM on error
            self.rom_path = ""
            self.rom_file_widget.set_rom_path("")

    def _start_header_loading(self, filename: str) -> None:
        """Start async ROM header loading.

        Args:
            filename: Path to ROM file
        """
        # Clean up existing header loader
        if self._header_loader is not None:
            WorkerManager.cleanup_worker(self._header_loader)
            self._header_loader = None

        # Create and start background worker
        self._header_loader = ROMHeaderLoaderWorker(
            rom_path=filename,
            rom_injector=self.rom_extractor.rom_injector,
            sprite_config_loader=self.rom_extractor.sprite_config_loader,
        )

        # Connect signals
        self._header_loader.header_loaded.connect(self._on_header_loaded)
        self._header_loader.error.connect(self._on_header_load_error)

        # Start loading
        logger.debug(f"Starting async header load for: {filename}")
        self._header_loader.start()

    def _on_header_loaded(self, result: dict[str, Any]) -> None:
        """Handle ROM header loaded from background worker.

        Args:
            result: Dict with 'header' and 'sprite_configs' keys
        """
        header = result.get("header")
        sprite_configs = result.get("sprite_configs")

        if header is None:
            self.rom_file_widget.set_info_text('<span style="color: red;">Error reading ROM header</span>')
        else:
            # Update ROM info display
            info_text = f"<b>Title:</b> {header.title}<br>"
            info_text += f"<b>Checksum:</b> 0x{header.checksum:04X}<br>"

            # Check if this matches known configurations
            if sprite_configs:
                info_text += '<span style="color: green;"><b>Status:</b> Configuration found ✓</span>'
            else:
                info_text += '<span style="color: orange;"><b>Status:</b> Unknown ROM version - use "Find Sprites" to scan</span>'

            self.rom_file_widget.set_info_text(info_text)

        # Now continue with sprite location loading and similarity indexing
        self._load_rom_sprites()
        self._init_similarity_indexing_worker()

    def _on_header_load_error(self, message: str, exception: Exception) -> None:
        """Handle ROM header loading error.

        Args:
            message: Error message
            exception: Exception that occurred
        """
        logger.warning(f"Could not read ROM header: {message}")
        self.rom_file_widget.set_info_text('<span style="color: red;">Error reading ROM header</span>')
        # Still try to load sprite locations even if header fails
        self._load_rom_sprites()
        self._init_similarity_indexing_worker()

    def _open_manual_offset_dialog(self):
        """Open the manual offset control dialog using singleton pattern"""
        logger.debug("[DEBUG] _open_manual_offset_dialog called")

        if not self.rom_path:
            UserErrorDialog.show_error(
                self,
                "Please load a ROM file first",
                "A ROM must be loaded before using manual offset control."
            )
            return

        # Get or create singleton dialog instance
        logger.debug("[DEBUG] Getting dialog from singleton...")
        dialog = ManualOffsetDialogSingleton.get_dialog(self)
        logger.debug(f"[DEBUG] Got dialog: {dialog} (ID: {getattr(dialog, '_debug_id', 'Unknown')})")

        # Defer custom signal connections to avoid Qt timing issues
        if not hasattr(dialog, "_custom_signals_connected"):
            def _connect_custom_signals():
                """Connect custom dialog signals after dialog is shown."""
                try:
                    logger.debug("Connecting custom dialog signals...")
                    # Connect directly to dialog signals
                    dialog.offset_changed.connect(self._on_dialog_offset_changed)
                    dialog.sprite_found.connect(self._on_dialog_sprite_found)
                    dialog._custom_signals_connected = True
                    logger.debug("Custom dialog signals connected successfully")
                except Exception as e:
                    logger.error(f"Failed to connect custom dialog signals: {e}")

            # Add to existing deferred signal connection or create new one
            existing_deferred = getattr(dialog, '_deferred_signal_connection', None)
            if existing_deferred:
                # Chain the custom signal connection with existing deferred connection
                def _combined_deferred():
                    existing_deferred()
                    _connect_custom_signals()
                dialog._deferred_signal_connection = _combined_deferred
            else:
                dialog._deferred_signal_connection = _connect_custom_signals

        # Update dialog with current ROM data every time it's opened
        dialog.set_rom_data(
            self.rom_path, self.rom_size, self.extraction_manager
        )

        # Set current offset
        dialog.set_offset(self._manual_offset)

        # Show the dialog (or bring to front if already visible)
        if not dialog.isVisible():
            logger.debug("[DEBUG] Dialog not visible, showing and raising")
            dialog.show()
            dialog.raise_()  # Also raise to ensure it's on top
            dialog.activateWindow()  # And activate to ensure focus
            # Process events to ensure the show takes effect immediately
            QApplication.processEvents()

            # Connect deferred signals now that dialog is fully shown
            if hasattr(dialog, '_deferred_signal_connection'):
                logger.debug("[DEBUG] Calling deferred signal connection...")
                dialog._deferred_signal_connection()
                delattr(dialog, '_deferred_signal_connection')  # Clean up

            logger.debug("[DEBUG] Showed and raised ManualOffsetDialog singleton")
        else:
            # Bring to front if already visible
            logger.debug("[DEBUG] Dialog already visible, raising to front")
            dialog.raise_()
            dialog.activateWindow()
            logger.debug("[DEBUG] Brought ManualOffsetDialog singleton to front")

        # Update legacy reference for compatibility
        self._manual_offset_dialog = dialog

    def _on_dialog_offset_changed(self, offset: int):
        """Handle offset changes from the dialog"""
        self._manual_offset = offset
        # Preview now handled in manual offset dialog
        # Update status label
        if self.manual_offset_status:
            self.manual_offset_status.setText(f"Current offset: 0x{offset:06X}")

    def _on_dialog_sprite_found(self, offset: int, sprite_name: str):
        """Handle sprite found signal from dialog"""
        self._manual_offset = offset
        # Update status to show sprite was selected
        if self.manual_offset_status:
            self.manual_offset_status.setText(f"Selected sprite at 0x{offset:06X}")
        # Check extraction readiness
        self._check_extraction_ready()

    def _browse_cgram(self):
        """Browse for CGRAM file"""
        settings = get_settings_manager()

        # Try to use ROM directory as default
        default_dir = (
            str(Path(self.rom_path).parent)
            if self.rom_path
            else settings.get_default_directory()
        )

        filename, _ = QFileDialog.getOpenFileName(
            self,
            "Select CGRAM File ()",
            default_dir,
            "CGRAM Files (*.dmp *.bin);;All Files (*.*)"
        )

        if filename:
            self.cgram_selector_widget.set_cgram_path(filename)
            settings.set_last_used_directory(str(Path(filename).parent))

    def _load_rom_sprites(self):
        """Load known sprite locations from ROM asynchronously."""
        if self.sprite_selector_widget:
            self.sprite_selector_widget.clear()
            self.sprite_selector_widget.add_sprite("Loading sprite locations...", None)
        self.sprite_locations = {}

        if not self.rom_path:
            return

        # Check cache status first (fast operation)
        try:
            from utils.rom_cache import get_rom_cache
            rom_cache = get_rom_cache()
            cached_locations = rom_cache.get_sprite_locations(self.rom_path)
            self._is_sprites_from_cache = bool(cached_locations)
        except Exception:
            self._is_sprites_from_cache = False

        # Clean up existing worker
        if self._sprite_location_loader is not None:
            WorkerManager.cleanup_worker(self._sprite_location_loader)
            self._sprite_location_loader = None

        # Start async sprite location loading
        self._sprite_location_loader = ROMInfoLoaderWorker(
            rom_path=self.rom_path,
            injection_manager=None,  # Not needed for sprite locations
            extraction_manager=self.extraction_manager,
            load_header=False,  # Header already loaded separately
            load_sprite_locations=True,
        )

        # Connect signals
        self._sprite_location_loader.sprite_locations_loaded.connect(
            self._on_sprite_locations_loaded
        )
        self._sprite_location_loader.error.connect(self._on_sprite_locations_error)

        # Start loading
        logger.debug(f"Starting async sprite location load for: {self.rom_path}")
        self._sprite_location_loader.start()

    def _on_sprite_locations_loaded(self, locations: dict[str, Any]) -> None:
        """Handle sprite locations loaded from background worker.

        Args:
            locations: Dict of sprite name -> SpritePointer
        """
        if self.sprite_selector_widget:
            self.sprite_selector_widget.clear()

        is_from_cache = getattr(self, '_is_sprites_from_cache', False)

        if locations:
            # Show count of known sprites to make it clear they're available
            cache_text = " (cached)" if is_from_cache else ""
            self.sprite_selector_widget.add_sprite(
                f"-- {len(locations)} Known Sprites Available{cache_text} --", None
            )

            # Add separator for clarity
            self.sprite_selector_widget.insert_separator(1)

            for name, pointer in locations.items():
                display_name = name.replace("_", " ").title()
                # Add cache indicator if sprites came from cache
                cache_indicator = " 💾" if is_from_cache else ""
                self.sprite_selector_widget.add_sprite(
                    f"{display_name} (0x{pointer.offset:06X}){cache_indicator}",
                    (name, pointer.offset)
                )
            self.sprite_locations = locations
            self.sprite_selector_widget.set_enabled(True)

            # Change button text to indicate scanner is optional
            self.sprite_selector_widget.set_find_button_text("Scan for More Sprites")
            self.sprite_selector_widget.set_find_button_tooltip(
                ": Scan ROM for additional sprites not in the known list"
            )
            self.sprite_selector_widget.set_find_button_enabled(True)
        else:
            self.sprite_selector_widget.add_sprite("No known sprites - use scanner", None)
            self.sprite_selector_widget.set_enabled(False)

            # Change button text to indicate scanner is needed
            self.sprite_selector_widget.set_find_button_text("Find Sprites")
            self.sprite_selector_widget.set_find_button_tooltip(
                "Scan ROM for valid sprite offsets (required for unknown ROMs)"
            )
            self.sprite_selector_widget.set_find_button_enabled(True)

    def _on_sprite_locations_error(self, message: str, exception: Exception) -> None:
        """Handle sprite locations loading error.

        Args:
            message: Error message
            exception: Exception that occurred
        """
        logger.exception(f"Failed to load sprite locations: {message}")
        if self.sprite_selector_widget:
            self.sprite_selector_widget.clear()
            self.sprite_selector_widget.add_sprite("Error loading ROM", None)
            self.sprite_selector_widget.set_enabled(False)

    def _init_similarity_indexing_worker(self):
        """Initialize similarity indexing worker for the current ROM"""
        if not self.rom_path:
            return

        try:
            # Clean up existing worker if any
            if self.similarity_indexing_worker is not None:
                WorkerManager.cleanup_worker(self.similarity_indexing_worker)
                self.similarity_indexing_worker = None

            # Create new similarity indexing worker
            self.similarity_indexing_worker = SimilarityIndexingWorker(self.rom_path)

            # Connect signals for progress updates
            self.similarity_indexing_worker.progress.connect(self._on_similarity_progress)
            self.similarity_indexing_worker.sprite_indexed.connect(self._on_sprite_indexed)
            self.similarity_indexing_worker.index_saved.connect(self._on_index_saved)
            self.similarity_indexing_worker.index_loaded.connect(self._on_index_loaded)
            self.similarity_indexing_worker.operation_finished.connect(self._on_similarity_finished)
            self.similarity_indexing_worker.error.connect(self._on_similarity_error)

            # Show similarity status
            self.similarity_status.setVisible(True)
            indexed_count = self.similarity_indexing_worker.get_indexed_count()
            if indexed_count > 0:
                if self.similarity_status:
                    self.similarity_status.setText(f"Similarity index ready ({indexed_count} sprites loaded)")
            elif self.similarity_status:
                self.similarity_status.setText("Similarity indexing ready - sprites will be indexed as found")

            logger.info(f"Initialized similarity indexing worker for ROM: {Path(self.rom_path).name}")

        except Exception as e:
            logger.exception(f"Failed to initialize similarity indexing worker: {e}")
            if self.similarity_status:
                self.similarity_status.setText(f"Similarity indexing error: {e}")
            if self.similarity_status:
                self.similarity_status.setStyleSheet("""
                padding: 6px;
                background: #3d1a1a;
                border: 1px solid #f44336;
                border-radius: 4px;
                color: #ffcdd2;
                font-size: 12px;
            """)

    def _on_similarity_progress(self, percent: int, message: str):
        """Handle similarity indexing progress updates"""
        if self.similarity_status:
            self.similarity_status.setText(f"Indexing sprites: {percent}% - {message}")

    def _on_sprite_indexed(self, offset: int):
        """Handle individual sprite indexing completion"""
        logger.debug(f"Sprite at 0x{offset:X} indexed for similarity search")

    def _on_index_saved(self, index_path: str):
        """Handle similarity index save completion"""
        logger.info(f"Similarity index saved to: {index_path}")

    def _on_index_loaded(self, sprite_count: int):
        """Handle similarity index loading"""
        logger.info(f"Loaded {sprite_count} sprites from similarity index")

    def _on_similarity_finished(self, success: bool, message: str):
        """Handle similarity indexing completion"""
        if success:
            indexed_count = self.similarity_indexing_worker.get_indexed_count() if self.similarity_indexing_worker else 0
            if self.similarity_status:
                self.similarity_status.setText(f"Similarity index ready ({indexed_count} sprites)")
            logger.info(f"Similarity indexing complete: {message}")
        else:
            if self.similarity_status:
                self.similarity_status.setText(f"Similarity indexing failed: {message}")
            logger.error(f"Similarity indexing failed: {message}")

    def _on_similarity_error(self, error_message: str, exception: Exception):
        """Handle similarity indexing errors"""
        if self.similarity_status:
            self.similarity_status.setText(f"Similarity error: {error_message}")
        if self.similarity_status:
            self.similarity_status.setStyleSheet("""
            padding: 6px;
            background: #3d1a1a;
            border: 1px solid #f44336;
            border-radius: 4px;
            color: #ffcdd2;
            font-size: 12px;
        """)
        logger.error(f"Similarity indexing error: {error_message}", exc_info=exception)

    def _on_sprite_changed(self, index: int):
        """Handle sprite selection change"""
        logger.debug(f"Sprite selection changed to index: {index}")
        try:
            if index > 0:
                logger.debug("Sprite selected, getting data")
                data = self.sprite_selector_widget.get_current_data()
                logger.debug(f"Combo data: {data}")

                if data:
                    sprite_name, offset = data
                    logger.debug(f"Parsed sprite: {sprite_name}, offset: 0x{offset:06X}")

                    self.sprite_selector_widget.set_offset_text(f"0x{offset:06X}")
                    logger.debug("Updated offset label")

                    # Auto-generate output name based on sprite
                    current_output = self.output_name_widget.get_output_name()
                    if not current_output:
                        new_name = f"{sprite_name}_sprites"
                        logger.debug(f"Auto-generating output name: {new_name}")
                        self.output_name_widget.set_output_name(new_name)

                    # Show preview of selected sprite
                    logger.debug("Showing preview of selected sprite")
                    # Preview now handled in manual offset dialog
                else:
                    logger.warning("No data found for selected sprite")
            else:
                logger.debug("No sprite selected, clearing displays")
                self.sprite_selector_widget.set_offset_text("--")

            logger.debug("Calling _check_extraction_ready")
            self._check_extraction_ready()
            logger.debug("Sprite change handling completed successfully")

        except Exception:
            logger.exception("Error in _on_sprite_changed")
            # Try to clear displays on error
            try:
                self.sprite_selector_widget.set_offset_text("Error")
            except Exception:
                pass  # Silently ignore errors when trying to clear displays

    def _check_extraction_ready(self):
        """Check if extraction is ready - override to handle manual mode"""
        try:
            # Check common requirements
            has_rom = bool(self.rom_path)
            has_output_name = bool(self.output_name_widget.get_output_name())

            if self._manual_offset_mode:
                # In manual mode, just need ROM and output name
                ready = has_rom and has_output_name
            else:
                # In preset mode, also need sprite selection
                has_sprite = self.sprite_selector_widget.get_current_index() > 0
                ready = has_rom and has_sprite and has_output_name

            logger.debug(f"Extraction ready: {ready} (manual_mode={self._manual_offset_mode})")
            self.extraction_ready.emit(ready)

        except Exception:
            logger.exception("Error in _check_extraction_ready")
            self.extraction_ready.emit(False)

    def get_extraction_params(self) -> dict[str, Any] | None:
        """Get parameters for ROM extraction"""
        if not self.rom_path:
            return None

        # Handle manual mode
        if self._manual_offset_mode:
            offset = self._manual_offset
            sprite_name = f"manual_0x{offset:X}"
        else:
            # Preset mode
            if self.sprite_selector_widget.get_current_index() <= 0:
                return None
            data = self.sprite_selector_widget.get_current_data()
            if not data:
                return None
            sprite_name, offset = data

        return {
            "rom_path": self.rom_path,
            "sprite_offset": offset,
            "sprite_name": sprite_name,
            "output_base": self.output_name_widget.get_output_name(),
            "cgram_path": (
                self.cgram_selector_widget.get_cgram_path() if self.cgram_selector_widget.get_cgram_path() else None
            ),
        }

    def clear_files(self):
        """Clear all file selections"""
        self.rom_path = ""
        if self.rom_file_widget:
            self.rom_file_widget.clear()
        if self.cgram_selector_widget:
            self.cgram_selector_widget.clear()
        if self.output_name_widget:
            self.output_name_widget.clear()
        if self.sprite_selector_widget:
            self.sprite_selector_widget.clear()
        self.sprite_locations = {}
        self._check_extraction_ready()
        self.rom_file_widget.set_info_text("No ROM loaded")

    # Preview functionality removed - now handled in manual offset dialog

    def _find_sprites(self):
        """Open dialog to scan for sprite offsets"""
        if not self.rom_path:
            return

        # Check if we can start scanning
        if not self.state_manager.can_scan:
            logger.warning("Cannot start scan - another operation is in progress")
            return

        # Transition to scanning state
        if not self.state_manager.start_scanning():
            logger.error("Failed to transition to scanning state")
            return

        try:
            dialog = self._create_scan_dialog()
            self._setup_scan_worker(dialog)
            dialog.exec()
        except Exception as e:
            logger.exception("Error in sprite scanning")
            self.state_manager.finish_scanning(success=False, error=str(e))
            UserErrorDialog.show_error(
                self,
                "Failed to scan for sprites",
                f"Technical details: {e!s}"
            )

    def _create_scan_dialog(self) -> ScanDialog:
        """Create and configure the sprite scanning dialog.

        Returns:
            Configured ScanDialog instance
        """
        dialog = ScanDialog(self)
        dialog.setWindowTitle("Find Sprites")
        dialog.setMinimumSize(600, 400)

        # Build dialog UI
        layout = QVBoxLayout()

        # Create UI components
        cache_status_label = self._create_cache_status_label()
        progress_bar = self._create_progress_bar()
        results_text = self._create_results_text()
        button_box = self._create_button_box()

        # Add to layout
        layout.addWidget(cache_status_label)
        layout.addWidget(progress_bar)
        layout.addWidget(results_text)
        layout.addWidget(button_box)

        dialog.setLayout(layout)

        # Store references for later access
        dialog.cache_status_label = cache_status_label
        dialog.progress_bar = progress_bar
        dialog.results_text = results_text
        dialog.button_box = button_box
        dialog.apply_btn = button_box.button(QDialogButtonBox.StandardButton.Apply)

        return dialog

    def _create_cache_status_label(self) -> QLabel:
        """Create the cache status label."""
        label = QLabel("Checking cache...")
        label.setStyleSheet(self._get_cache_status_style("checking"))
        return label

    def _create_progress_bar(self) -> QProgressBar:
        """Create the progress bar."""
        progress_bar = QProgressBar()
        progress_bar.setTextVisible(True)
        return progress_bar

    def _create_results_text(self) -> QTextEdit:
        """Create the results text area."""
        results_text = QTextEdit()
        results_text.setReadOnly(True)
        results_text.setPlainText("Starting sprite scan...\n\n")
        return results_text

    def _create_button_box(self) -> QDialogButtonBox:
        """Create the button box with Close and Apply buttons."""
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Close | QDialogButtonBox.StandardButton.Apply
        )
        apply_btn = button_box.button(QDialogButtonBox.StandardButton.Apply)
        if apply_btn:
            apply_btn.setText("Use Selected Offset")
            apply_btn.setEnabled(False)
        return button_box

    def _get_cache_status_style(self, status: str) -> str:
        """Get the stylesheet for cache status label based on status.

        Args:
            status: Status type (checking, resuming, fresh, saved, error)

        Returns:
            CSS stylesheet string
        """
        styles = {
            "checking": """
                QLabel {
                    background-color: #e3f2fd;
                    border: 1px solid #2196f3;
                    border-radius: 4px;
                    padding: 8px;
                    font-weight: bold;
                    color: #1976d2;
                }
            """,
            "resuming": """
                QLabel {
                    background-color: #e8f5e9;
                    border: 1px solid #4caf50;
                    border-radius: 4px;
                    padding: 8px;
                    font-weight: bold;
                    color: #2e7d32;
                }
            """,
            "fresh": """
                QLabel {
                    background-color: #fff3e0;
                    border: 1px solid #ff9800;
                    border-radius: 4px;
                    padding: 8px;
                    font-weight: bold;
                    color: #e65100;
                }
            """,
            "saving": """
                QLabel {
                    background-color: #e1f5fe;
                    border: 1px solid #039be5;
                    border-radius: 4px;
                    padding: 8px;
                    font-weight: bold;
                    color: #01579b;
                }
            """,
            "saved": """
                QLabel {
                    background-color: #c8e6c9;
                    border: 1px solid #4caf50;
                    border-radius: 4px;
                    padding: 8px;
                    font-weight: bold;
                    color: #1b5e20;
                }
            """
        }
        return styles.get(status, styles["checking"])

    def _setup_scan_worker(self, dialog: ScanDialog) -> None:
        """Set up the scan worker and connect signals.

        Args:
            dialog: The scan dialog containing UI elements
        """
        # Clean up any existing scan worker
        WorkerManager.cleanup_worker(self.scan_worker)

        # Check cache and get user preference
        use_cache = self._check_scan_cache(dialog)
        if use_cache is None:
            # User cancelled
            dialog.reject()
            return

        # Create scan worker
        self.scan_worker = SpriteScanWorker(self.rom_path, self.rom_extractor, use_cache=use_cache, parent=self)

        # Create scan context to pass data between handlers
        scan_context = ScanContext()

        # Connect worker signals
        self._connect_scan_signals(dialog, scan_context)

        # Connect dialog signals
        self._connect_dialog_signals(dialog, scan_context)

        # Start scanning
        self.scan_worker.start()

    def _check_scan_cache(self, dialog: ScanDialog) -> bool | None:
        """Check for cached scan results and get user preference.

        Args:
            dialog: The scan dialog

        Returns:
            True to use cache, False to start fresh, None if cancelled
        """
        from utils.rom_cache import get_rom_cache  # Delayed import
        rom_cache = get_rom_cache()

        # Define scan parameters (must match SpriteScanWorker)
        scan_params = {
            "start_offset": 0xC0000,
            "end_offset": 0xF0000,
            "alignment": 0x100
        }

        partial_cache = rom_cache.get_partial_scan_results(self.rom_path, scan_params)

        # Store cache reference for later use
        dialog.rom_cache = rom_cache

        if partial_cache and not partial_cache.get("completed", False):
            # Show resume dialog
            user_choice = ResumeScanDialog.show_resume_dialog(partial_cache, self)

            if user_choice == ResumeScanDialog.CANCEL:
                return None
            if user_choice == ResumeScanDialog.START_FRESH:
                self._update_cache_status(dialog, "fresh", "Starting fresh scan (ignoring cache)")
                return False
            # RESUME
            self._update_cache_status(dialog, "resuming", "📊 Resuming from cached progress...")
            return True
        self._update_cache_status(dialog, "fresh", "No cache found - starting fresh scan")
        return True

    def _update_cache_status(self, dialog: ScanDialog, status: str, text: str) -> None:
        """Update the cache status label.

        Args:
            dialog: The scan dialog
            status: Status type for styling
            text: Status text to display
        """
        dialog.cache_status_label.setText(text)
        dialog.cache_status_label.setStyleSheet(self._get_cache_status_style(status))

    def _connect_scan_signals(self, dialog: ScanDialog, context: ScanContext) -> None:
        """Connect scan worker signals to handlers.

        Args:
            dialog: The scan dialog
            context: Scan context for sharing data
        """
        if self.scan_worker:
            self.scan_worker.progress_detailed.connect(
                lambda c, t: self._on_scan_progress(dialog, c, t)
            )
            self.scan_worker.sprite_found.connect(
                lambda info: self._on_sprite_found(dialog, context, info)
            )
            self.scan_worker.finished.connect(
                lambda: self._on_scan_complete(dialog, context)
            )
            self.scan_worker.cache_status.connect(
                lambda status: self._on_cache_status(dialog, status)
            )
            self.scan_worker.cache_progress.connect(
                lambda progress: self._on_cache_progress(dialog, progress)
            )

        # Connect to similarity indexing if available
        if self.similarity_indexing_worker is not None and self.scan_worker:
            self.scan_worker.sprite_found.connect(self.similarity_indexing_worker.on_sprite_found)
            self.scan_worker.finished.connect(self.similarity_indexing_worker.on_scan_finished)

    def _on_scan_progress(self, dialog: ScanDialog, current: int, total: int) -> None:
        """Handle scan progress update."""
        dialog.progress_bar.setValue(int((current / total) * 100))
        dialog.progress_bar.setFormat(f"Scanning... {current}/{total}")

    def _on_sprite_found(self, dialog: ScanDialog, context: ScanContext, sprite_info: dict[str, Any]) -> None:
        """Handle sprite found during scan."""
        context.found_offsets.append(sprite_info)

        # Update results text
        text = self._format_sprite_info(sprite_info)
        current_text = dialog.results_text.toPlainText()
        dialog.results_text.setPlainText(current_text + text)

        # Update navigator
        if self.sprite_navigator is not None:
            self.sprite_navigator.add_found_sprite(
                sprite_info["offset"], sprite_info.get("quality", 1.0)
            )

        # Enable apply button after first find
        if len(context.found_offsets) == 1 and dialog.apply_btn:
            dialog.apply_btn.setEnabled(True)

    def _format_sprite_info(self, sprite_info: dict[str, Any]) -> str:
        """Format sprite info for display."""
        text = f"Found sprite at {sprite_info['offset_hex']}:\n"
        text += f"  - Tiles: {sprite_info['tile_count']}\n"
        text += f"  - Alignment: {sprite_info['alignment']}\n"
        text += f"  - Quality: {sprite_info['quality']:.2f}\n"
        text += f"  - Size: {sprite_info['compressed_size']} bytes compressed\n"
        if "size_limit_used" in sprite_info:
            text += f"  - Size limit: {sprite_info['size_limit_used']} bytes\n"
        text += "\n"
        return text

    def _on_scan_complete(self, dialog: ScanDialog, context: ScanContext) -> None:
        """Handle scan completion."""
        dialog.progress_bar.setValue(100)
        dialog.progress_bar.setFormat("Scan complete")

        # Update results text
        summary_text = self._format_scan_summary(context.found_offsets)
        current_text = dialog.results_text.toPlainText()
        dialog.results_text.setPlainText(current_text + summary_text)

        if context.found_offsets:
            # Save results to cache
            self._save_scan_results_to_cache(dialog, context.found_offsets)

            # Update navigator
            if self.sprite_navigator is not None:
                sprites_with_quality = [(s["offset"], s.get("quality", 1.0))
                                      for s in context.found_offsets]
                self.sprite_navigator.set_found_sprites(sprites_with_quality)
        # No sprites found
        elif dialog.apply_btn:
            dialog.apply_btn.setEnabled(False)

    def _format_scan_summary(self, found_offsets: list[Any]) -> str:
        """Format scan completion summary."""
        text = f"\nScan complete! Found {len(found_offsets)} valid sprite locations.\n"

        if found_offsets:
            text += "\nBest quality sprites:\n"
            # Sort by quality
            sorted_sprites = sorted(found_offsets, key=itemgetter("quality"), reverse=True)

            for i, sprite in enumerate(sorted_sprites[:5]):
                size_info = ""
                if "size_limit_used" in sprite:
                    size_info = f", {sprite['size_limit_used']/1024:.0f}KB limit"
                text += (f"{i+1}. {sprite['offset_hex']} - Quality: {sprite['quality']:.2f}, "
                        f"{sprite['tile_count']} tiles{size_info}\n")
        else:
            text += "\nNo valid sprites found in scanned range.\n"

        return text

    def _save_scan_results_to_cache(self, dialog: ScanDialog, found_offsets: list[Any]) -> None:
        """Save scan results to cache."""
        self._update_cache_status(dialog, "saving", "💾 Saving results to cache...")
        QApplication.processEvents()

        # Convert to cache format
        sprite_locations = {}
        for sprite in found_offsets:
            name = f"scanned_0x{sprite['offset']:X}"
            sprite_locations[name] = {
                "offset": sprite["offset"],
                "compressed_size": sprite.get("compressed_size"),
                "quality": sprite.get("quality", 0.0)
            }

        # Save to cache
        if dialog.rom_cache and dialog.rom_cache.save_sprite_locations(self.rom_path, sprite_locations):
            self._update_cache_status(dialog, "saved",
                                     f"✅ Saved {len(found_offsets)} sprites to cache")
            # Update results text
            current_text = dialog.results_text.toPlainText()
            dialog.results_text.setPlainText(
                current_text + "\n✅ Results saved to cache for faster future scans.\n"
            )
        else:
            dialog.cache_status_label.setText("⚠️ Could not save to cache")
            current_text = dialog.results_text.toPlainText()
            dialog.results_text.setPlainText(
                current_text + "\n⚠️ Could not save results to cache.\n"
            )

    def _on_cache_status(self, dialog: ScanDialog, status: str) -> None:
        """Handle cache status update."""
        dialog.cache_status_label.setText(f"💾 {status}")

        # Update style based on status
        if "Saving" in status:
            style_type = "saving"
        elif "Resuming" in status:
            style_type = "resuming"
        else:
            style_type = "checking"

        dialog.cache_status_label.setStyleSheet(self._get_cache_status_style(style_type))

    def _on_cache_progress(self, dialog: ScanDialog, progress: int) -> None:
        """Handle cache progress update."""
        if progress > 0:
            dialog.cache_status_label.setText(f"💾 Saving progress ({progress}%)...")

    def _connect_dialog_signals(self, dialog: ScanDialog, context: ScanContext) -> None:
        """Connect dialog button signals.

        Args:
            dialog: The scan dialog
            context: Scan context for sharing data
        """
        # Connect dialog finished signal
        dialog.finished.connect(lambda result: self._on_dialog_finished(dialog, result, context))

        # Connect button box signals
        dialog.button_box.rejected.connect(dialog.reject)

        if dialog.apply_btn:
            dialog.apply_btn.clicked.connect(lambda: self._on_apply_clicked(dialog, context))

    def _on_apply_clicked(self, dialog: ScanDialog, context: ScanContext) -> None:
        """Handle Apply button click."""
        if context.found_offsets:
            # Use the best quality offset
            context.selected_offset = context.found_offsets[0]["offset"]
            dialog.accept()

    def _on_dialog_finished(self, dialog: ScanDialog, result: int, context: ScanContext) -> None:
        """Handle dialog close."""
        # Clean up worker
        WorkerManager.cleanup_worker(self.scan_worker)
        self.scan_worker = None

        # Transition back to idle state
        self.state_manager.finish_scanning()

        # Handle accepted dialog with selected offset
        if result == QDialog.DialogCode.Accepted and context.selected_offset is not None:
            self._add_selected_sprite(context.selected_offset)

    def _add_selected_sprite(self, offset: int) -> None:
        """Add the selected sprite to the combo box.

        Args:
            offset: The selected sprite offset
        """
        sprite_name = f"custom_0x{offset:X}"
        display_name = f"Custom Sprite (0x{offset:06X})"

        # Check if already exists
        for i in range(self.sprite_selector_widget.count()):
            data = self.sprite_selector_widget.item_data(i)
            if data and data[0] == sprite_name:
                self.sprite_selector_widget.set_current_index(i)
                return

        # Add separator if needed
        self._add_scanner_section_separator()

        # Add new sprite with cache indicator
        self.sprite_selector_widget.add_sprite(f"{display_name} 💾", (sprite_name, offset))
        self.sprite_selector_widget.set_current_index(self.sprite_selector_widget.count() - 1)

        logger.info(f"User selected custom sprite offset: 0x{offset:X}")

    def _add_scanner_section_separator(self) -> None:
        """Add a separator for scanner results if needed."""
        if not self.sprite_locations or self.sprite_selector_widget.count() <= 2:
            return

        # Check if scanner section already exists
        for i in range(self.sprite_selector_widget.count()):
            text = self.sprite_selector_widget.item_text(i)
            if "Scanner Results" in text:
                return

        # Add separator
        self.sprite_selector_widget.add_sprite("-- Scanner Results (now cached) --", None)

    def _on_mode_changed(self, index: int):
        """Handle extraction mode change"""
        self._manual_offset_mode = (index == 1)

        # Show/hide appropriate controls
        self.sprite_selector_widget.setVisible(not self._manual_offset_mode)
        self.manual_offset_button.setVisible(self._manual_offset_mode)
        self.manual_offset_status.setVisible(self._manual_offset_mode)

        # Mode switching handled

        # Update extraction ready state
        self._check_extraction_ready()

        # If switching to manual mode with ROM loaded, show current offset preview
        if self._manual_offset_mode and self.rom_path:
            # Preview now handled in manual offset dialog
            pass

    def _on_navigator_offset_changed(self, offset: int):
        """Handle offset change from navigator"""
        self._manual_offset = offset
        if self.manual_offset_status:
            self.manual_offset_status.setText(f"Navigator: 0x{offset:06X}")

        # Update manual offset dialog if open
        current_dialog = ManualOffsetDialogSingleton.get_current_dialog()
        if current_dialog is not None:
            current_dialog.set_offset(offset)

        # Update extraction readiness
        self._check_extraction_ready()

    def _on_navigator_sprite_selected(self, offset: int, sprite_name: str):
        """Handle sprite selection from navigator"""
        self._manual_offset = offset

        # If in preset mode, try to find and select the sprite
        if not self._manual_offset_mode:
            # Look for sprite in combo box
            for i in range(self.sprite_selector_widget.count()):
                data = self.sprite_selector_widget.item_data(i)
                if data and len(data) >= 2 and data[1] == offset:
                    self.sprite_selector_widget.set_current_index(i)
                    break
        # In manual mode, just update the offset
        elif self.manual_offset_status:
            self.manual_offset_status.setText(f"Selected sprite at 0x{offset:06X}")

        # Update extraction readiness
        self._check_extraction_ready()

    # Manual preview functionality removed - now handled in manual offset dialog

    def _find_next_sprite(self):
        """Find next valid sprite offset - now handled by dialog"""
        # Open dialog if not already open
        if ManualOffsetDialogSingleton.is_dialog_open():
            # Dialog will handle the search
            pass
        else:
            self._open_manual_offset_dialog()

    def _find_prev_sprite(self):
        """Find previous valid sprite offset - now handled by dialog"""
        # Open dialog if not already open
        if ManualOffsetDialogSingleton.is_dialog_open():
            # Dialog will handle the search
            pass
        else:
            self._open_manual_offset_dialog()

    def _on_search_sprite_found(self, offset: int, quality: float):
        """Handle sprite found during search"""
        self._manual_offset = offset
        if self.manual_offset_status:
            self.manual_offset_status.setText(
            f"Found sprite at 0x{offset:06X} (quality: {quality:.2f})"
        )
        # Update dialog if open
        current_dialog = ManualOffsetDialogSingleton.get_current_dialog()
        if current_dialog is not None:
            current_dialog.set_offset(offset)
            current_dialog.add_found_sprite(offset, quality)
        # Update navigator
        if self.sprite_navigator is not None:
            self.sprite_navigator.add_found_sprite(offset, quality)

    def _on_search_complete(self, found: bool):
        """Handle search completion"""
        if not found and self.manual_offset_status:
            self.manual_offset_status.setText(
            "No valid sprites found in search range. Try a different area."
            )

    def _on_state_changed(self, old_state: ExtractionState, new_state: ExtractionState):
        """Handle state changes to update UI accordingly"""
        # Update UI elements based on state
        if new_state == ExtractionState.IDLE:
            # Re-enable all controls
            if self.rom_file_widget:
                self.rom_file_widget.setEnabled(True)
            if self.mode_selector_widget:
                self.mode_selector_widget.setEnabled(True)
            self.sprite_selector_widget.set_find_button_enabled(True)
            if self.manual_offset_button:
                self.manual_offset_button.setEnabled(True)

        elif new_state in {ExtractionState.LOADING_ROM, ExtractionState.EXTRACTING}:
            # Disable all controls during critical operations
            if self.rom_file_widget:
                self.rom_file_widget.setEnabled(False)
            if self.mode_selector_widget:
                self.mode_selector_widget.setEnabled(False)
            self.sprite_selector_widget.set_find_button_enabled(False)
            if self.manual_offset_button:
                self.manual_offset_button.setEnabled(False)

        elif new_state == ExtractionState.SCANNING_SPRITES:
            # Disable sprite selection during scan
            self.sprite_selector_widget.set_find_button_enabled(False)

        elif new_state == ExtractionState.SEARCHING_SPRITE:
            # Disable navigation during search
            if self.manual_offset_button:
                self.manual_offset_button.setEnabled(False)

        # Log state transitions for debugging
        logger.debug(f"State transition: {old_state.name} -> {new_state.name}")

    def _cleanup_workers(self):
        """Clean up any running worker threads"""
        logger.debug("Cleaning up ROM extraction panel workers")

        # List of all worker attributes to clean up
        worker_attrs = [
            'search_worker',
            'scan_worker',
            'similarity_indexing_worker'
        ]

        # Clean up each worker
        for attr_name in worker_attrs:
            worker = getattr(self, attr_name, None)
            if worker is not None:
                logger.debug(f"Cleaning up {attr_name}")
                try:
                    # First try to cancel if it's a BaseWorker
                    if hasattr(worker, 'cancel'):
                        worker.cancel()

                    # Use WorkerManager for thorough cleanup
                    WorkerManager.cleanup_worker(worker)
                except Exception as e:
                    logger.warning(f"Error cleaning up {attr_name}: {e}")
                finally:
                    # Always clear the reference
                    setattr(self, attr_name, None)

        # Also check sprite navigator for any preview workers
        if hasattr(self, 'sprite_navigator') and self.sprite_navigator is not None:
            if hasattr(self.sprite_navigator, 'preview_workers'):
                logger.debug("Cleaning up sprite navigator preview workers")
                for worker in self.sprite_navigator.preview_workers:
                    try:
                        WorkerManager.cleanup_worker(worker)
                    except Exception as e:
                        logger.warning(f"Error cleaning up preview worker: {e}")
                self.sprite_navigator.preview_workers.clear()

    @override
    def closeEvent(self, a0: QCloseEvent | None) -> None:
        """Handle panel close event"""
        # Clean up workers before closing
        self._cleanup_workers()

        # Close manual offset dialog if it exists (singleton pattern)
        current_dialog = ManualOffsetDialogSingleton.get_current_dialog()
        if current_dialog is not None:
            current_dialog.close()

        # Call parent implementation
        if a0 is not None:
            super().closeEvent(a0)

    def __del__(self):
        """Destructor to ensure cleanup even if closeEvent isn't called"""
        try:
            # Ensure workers are cleaned up
            self._cleanup_workers()
        except Exception as e:
            # Don't raise in destructor, just log
            logger.debug(f"Error in ROMExtractionPanel destructor: {e}")

class ScanContext:
    """Context object for sharing data between scan event handlers."""

    def __init__(self):
        self.found_offsets: list[dict[str, Any]] = []
        self.selected_offset: int | None = None
