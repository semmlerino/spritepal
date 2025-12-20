"""
ROM extraction panel for SpritePal.

This panel coordinates ROM-based sprite extraction using:
- ROMWorkerOrchestrator: Background worker management
- ScanController: Sprite scanning workflow and cache
- OffsetDialogManager: Manual offset dialog lifecycle
"""

from __future__ import annotations

from collections.abc import Callable
from operator import itemgetter
from pathlib import Path
from typing import TYPE_CHECKING, Any, override

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QSpacerItem,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

if TYPE_CHECKING:
    from core.managers.application_state_manager import ApplicationStateManager
    from core.managers.core_operations_manager import CoreOperationsManager

# ExtractionManager accessed via DI: inject(ExtractionManagerProtocol)
from core.managers.application_state_manager import ExtractionState

# Import extracted components
from ui.rom_extraction import OffsetDialogManager, ROMWorkerOrchestrator, ScanController
from ui.rom_extraction.widgets import (
    CGRAMSelectorWidget,
    ROMFileWidget,
    SpriteSelectorWidget,
)

# Dialog imports moved to lazy imports in methods that use them (see _on_partial_scan_detected, _open_manual_offset_dialog, _find_sprites, _check_scan_cache)
from ui.rom_extraction.workers import SpriteScanWorker
from ui.styles.components import get_cache_status_style, get_manual_offset_button_style
from ui.styles.theme import COLORS
from utils.constants import (
    SETTINGS_KEY_LAST_INPUT_ROM,
    SETTINGS_NS_ROM_INJECTION,
)
from utils.logging_config import get_logger

logger = get_logger(__name__)

# UI Spacing Constants (imported from centralized module)
from ui.common.spacing_constants import (
    BUTTON_HEIGHT,
    SPACING_COMPACT_LARGE as SPACING_LARGE,
    SPACING_COMPACT_MEDIUM as SPACING_MEDIUM,
)


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


class ScanContext:
    """Context object for sharing data between scan event handlers."""

    def __init__(self):
        self.found_offsets: list[dict[str, Any]] = []
        self.selected_offset: int | None = None


class ROMExtractionPanel(QWidget):
    """Panel for ROM-based sprite extraction.

    This panel coordinates:
    - ROM file selection and header loading
    - Sprite location loading (from cache or ROM)
    - Manual offset browsing via dialog
    - Sprite scanning workflow
    """

    # Signals
    files_changed = Signal()
    extraction_ready = Signal(bool, str)  # (ready, reason_if_not_ready)
    rom_extraction_requested = Signal(
        str, int, str, str
    )  # rom_path, offset, output_base, sprite_name
    output_name_changed = Signal(str)  # Emit when output name changes in ROM panel

    def __init__(
        self,
        parent: Any | None = None,
        *,
        extraction_manager: ExtractionManager,
    ):
        super().__init__(parent)

        self.rom_path = ""
        self.sprite_locations: dict[str, Any] = {}
        # Use injected extraction manager
        self.extraction_manager = extraction_manager
        self.rom_extractor = self.extraction_manager.get_rom_extractor()
        self.rom_size = 0  # Track ROM size for slider limits
        self._manual_offset_mode = False  # Default to preset mode (sprite picker visible)

        # State manager for coordinating operations (ApplicationStateManager)
        from core.di_container import inject
        from core.protocols.manager_protocols import ApplicationStateManagerProtocol
        self.state_manager: ApplicationStateManager = inject(ApplicationStateManagerProtocol)  # type: ignore[assignment]
        self.state_manager.workflow_state_changed.connect(self._on_state_changed)

        # Initialize extracted components
        self._worker_orchestrator = ROMWorkerOrchestrator(self)
        self._offset_dialog_manager = OffsetDialogManager(parent_widget=self, parent=self)
        self._scan_controller: ScanController | None = None  # Created on first use

        # Connect orchestrator signals
        self._connect_orchestrator_signals()

        # Connect dialog manager signals
        self._offset_dialog_manager.offset_changed.connect(self._on_dialog_offset_changed)
        self._offset_dialog_manager.sprite_found.connect(self._on_dialog_sprite_found)

        # Legacy worker reference for scan worker (still managed locally for now)
        self.scan_worker: SpriteScanWorker | None = None

        # Output name provider callback (injected from main window)
        self._output_name_provider: Callable[[], str] | None = None

        # Manual offset tracking
        self._manual_offset = 0x200000  # Default offset

        self._setup_ui()
        self._load_last_rom()

    def _connect_orchestrator_signals(self) -> None:
        """Connect signals from the worker orchestrator."""
        # Header loading
        self._worker_orchestrator.header_loaded.connect(self._on_header_loaded)
        self._worker_orchestrator.header_error.connect(self._on_header_load_error)

        # Sprite locations
        self._worker_orchestrator.sprite_locations_loaded.connect(
            self._on_sprite_locations_loaded
        )
        self._worker_orchestrator.sprite_locations_error.connect(
            self._on_sprite_locations_error
        )

        # Similarity indexing (logging only)
        self._worker_orchestrator.similarity_progress.connect(self._on_similarity_progress)
        self._worker_orchestrator.sprite_indexed.connect(self._on_sprite_indexed)
        self._worker_orchestrator.index_saved.connect(self._on_index_saved)
        self._worker_orchestrator.index_loaded.connect(self._on_index_loaded)
        self._worker_orchestrator.similarity_finished.connect(self._on_similarity_finished)
        self._worker_orchestrator.similarity_error.connect(self._on_similarity_error)

    def set_output_name_provider(self, provider: Callable[[], str]) -> None:
        """Set the callback to get output name from shared OutputSettingsManager.

        Args:
            provider: Callable that returns the current output name string
        """
        self._output_name_provider = provider

    def _get_output_name(self) -> str:
        """Get the current output name from the shared provider.

        Returns:
            Output name string, or empty string if provider not set
        """
        if self._output_name_provider:
            return self._output_name_provider()
        return ""

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
        self._add_mode_controls(layout)
        self._add_manual_offset_controls(layout)
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

        # Hint label - shown when ROM loaded but auto-fill failed (rare edge case)
        # Most times, output name is auto-filled from ROM filename
        self.output_hint_label = QLabel("↓ Enter output name in the Output Settings section below")
        self.output_hint_label.setStyleSheet(
            f"color: {COLORS['warning']}; font-size: 11px; font-style: italic;"
        )
        self.output_hint_label.setVisible(False)
        layout.addWidget(self.output_hint_label)

    def _add_mode_controls(self, layout: QVBoxLayout):
        """Add sprite selector controls to the layout (always visible, preset mode is default).

        Args:
            layout: Layout to add controls to
        """
        # Sprite selector widget - always visible (preset mode is primary)
        self.sprite_selector_widget = SpriteSelectorWidget()
        self.sprite_selector_widget.sprite_changed.connect(self._on_sprite_changed)
        self.sprite_selector_widget.find_sprites_clicked.connect(self._find_sprites)
        layout.addWidget(self.sprite_selector_widget)

    def _add_manual_offset_controls(self, layout: QVBoxLayout):
        """Add manual offset control in a collapsible advanced section.

        Args:
            layout: Layout to add controls to
        """
        # Create collapsible advanced section
        advanced_row = QHBoxLayout()
        advanced_row.setContentsMargins(0, 0, 0, 0)

        self.advanced_toggle = QToolButton()
        self.advanced_toggle.setText("Advanced: Manual Offset Exploration")
        self.advanced_toggle.setCheckable(True)
        self.advanced_toggle.setChecked(False)
        self.advanced_toggle.setArrowType(Qt.ArrowType.RightArrow)
        self.advanced_toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.advanced_toggle.setStyleSheet(
            "QToolButton { border: none; padding: 4px; font-weight: bold; }"
            "QToolButton:hover { background-color: rgba(255, 255, 255, 0.1); }"
        )
        self.advanced_toggle.toggled.connect(self._on_advanced_toggled)
        advanced_row.addWidget(self.advanced_toggle)
        advanced_row.addStretch()

        layout.addLayout(advanced_row)

        # Create and style the manual offset button (hidden by default)
        self.manual_offset_button = self._create_manual_offset_button()
        self.manual_offset_button.setVisible(False)  # Hidden until advanced section expanded
        layout.addWidget(self.manual_offset_button)

    def _create_manual_offset_button(self) -> QPushButton:
        """Create and configure the manual offset control button.

        Returns:
            QPushButton: The configured button
        """
        button = QPushButton("Browse Sprites (Ctrl+M)")
        button.setMinimumHeight(BUTTON_HEIGHT)  # Standard button height
        _ = button.clicked.connect(self._open_manual_offset_dialog)
        button.setVisible(True)  # Always visible (enabled/disabled based on mode)
        button.setToolTip(
            "Open advanced sprite browser to explore ROM offsets manually\n"
            "Keyboard shortcut: Ctrl+M"
        )
        button.setStyleSheet(get_manual_offset_button_style())
        return button

    def _add_output_controls(self, layout: QVBoxLayout):
        """Add CGRAM controls to the layout.

        Note: Output name is now handled by shared OutputSettingsManager in main window.

        Args:
            layout: Layout to add controls to
        """
        # CGRAM selector widget
        self.cgram_selector_widget = CGRAMSelectorWidget()
        self.cgram_selector_widget.browse_clicked.connect(self._browse_cgram)
        layout.addWidget(self.cgram_selector_widget)

    def _browse_rom(self):
        """Browse for ROM file"""
        from core.di_container import inject
        from core.protocols.manager_protocols import SettingsManagerProtocol
        settings = inject(SettingsManagerProtocol)
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
        from ui.dialogs import ResumeScanDialog  # Lazy import to avoid cross-UI coupling

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
            from core.di_container import inject
            from core.protocols.manager_protocols import SettingsManagerProtocol
            settings = inject(SettingsManagerProtocol)
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
                    current_dialog = self._offset_dialog_manager.get_current_dialog()
                    if current_dialog is not None:
                        current_dialog.set_rom_data(self.rom_path, self.rom_size, self.extraction_manager)
                    logger.debug(f"ROM size: {self.rom_size} bytes (0x{self.rom_size:X})")
            except Exception as e:
                logger.warning(f"Could not determine ROM size: {e}")
                self.rom_size = 0x400000  # Default 4MB

            # Save to settings
            from core.di_container import inject
            from core.protocols.manager_protocols import SettingsManagerProtocol
            settings = inject(SettingsManagerProtocol)
            settings.set_value(SETTINGS_NS_ROM_INJECTION, SETTINGS_KEY_LAST_INPUT_ROM, filename)
            settings.set_last_used_directory(str(Path(filename).parent))
            logger.debug(f"Saved ROM to settings: {filename}")

            # Read ROM header asynchronously using orchestrator
            self.rom_file_widget.show_loading("Loading ROM header...")
            self._worker_orchestrator.load_header(filename, self.rom_extractor)

            # Notify that files changed
            self.files_changed.emit()

            # Auto-fill output name from ROM filename if not already set
            if not self._get_output_name():
                rom_stem = Path(filename).stem
                suggested_name = f"{rom_stem}_sprites"
                self.output_name_changed.emit(suggested_name)
                logger.debug(f"Auto-filled output name: {suggested_name}")

            logger.info(f"Successfully loaded ROM: {Path(filename).name}")

        except Exception:
            logger.exception("Error loading ROM file %s", filename)
            # Clear ROM on error
            self.rom_path = ""
            self.rom_file_widget.set_rom_path("")

    def _on_header_loaded(self, result: dict[str, Any]) -> None:
        """Handle ROM header loaded from orchestrator.

        Args:
            result: Dict with 'header' and 'sprite_configs' keys
        """
        # Hide loading indicator
        self.rom_file_widget.hide_loading()

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
                info_text += '<span style="color: green;"><b>Status:</b> Configuration found</span>'
            else:
                info_text += '<span style="color: orange;"><b>Status:</b> Unknown ROM version - use "Find Sprites" to scan</span>'

            self.rom_file_widget.set_info_text(info_text)

        # Continue with sprite location loading and similarity indexing
        self._load_rom_sprites()
        self._init_similarity_indexing()

    def _on_header_load_error(self, message: str) -> None:
        """Handle ROM header loading error.

        Args:
            message: Error message
        """
        logger.warning(f"Could not read ROM header: {message}")
        self.rom_file_widget.hide_loading()
        self.rom_file_widget.set_info_text('<span style="color: red;">Error reading ROM header</span>')
        # Still try to load sprite locations even if header fails
        self._load_rom_sprites()
        self._init_similarity_indexing()

    def _open_manual_offset_dialog(self):
        """Open the manual offset control dialog using manager"""
        from ui.dialogs import UserErrorDialog  # Lazy import to avoid cross-UI coupling

        logger.debug("_open_manual_offset_dialog called")

        if not self.rom_path:
            UserErrorDialog.display_error(
                self,
                "Please load a ROM file first",
                "A ROM must be loaded before using manual offset control."
            )
            return

        # Use dialog manager to open the dialog
        dialog = self._offset_dialog_manager.open_dialog(
            rom_path=self.rom_path,
            extractor=self.rom_extractor,
            rom_size=self.rom_size,
            extraction_manager=self.extraction_manager,
            initial_offset=self._manual_offset,
        )

        if dialog:
            logger.debug("Opened ManualOffsetDialog via manager")

    def _on_dialog_offset_changed(self, offset: int):
        """Handle offset changes from the dialog"""
        self._manual_offset = offset
        self._manual_offset_mode = True  # User chose manual offset mode
        self._check_extraction_ready()
        # Preview now handled in manual offset dialog

    def _on_dialog_sprite_found(self, sprite_data: dict[str, Any]):
        """Handle sprite found signal from dialog"""
        offset = sprite_data.get("offset", 0)
        self._manual_offset = offset
        self._manual_offset_mode = True  # User chose manual offset mode via dialog
        # Check extraction readiness
        self._check_extraction_ready()

    def _browse_cgram(self):
        """Browse for CGRAM file"""
        from core.di_container import inject
        from core.protocols.manager_protocols import SettingsManagerProtocol
        settings = inject(SettingsManagerProtocol)

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
        """Load known sprite locations from ROM using orchestrator."""
        if self.sprite_selector_widget:
            self.sprite_selector_widget.clear()
            self.sprite_selector_widget.add_sprite("Loading sprite locations...", None)
        self.sprite_locations = {}

        if not self.rom_path:
            return

        # Check cache status first (fast operation)
        try:
            from core.di_container import inject
            from core.protocols.manager_protocols import ROMCacheProtocol
            rom_cache = inject(ROMCacheProtocol)
            cached_locations = rom_cache.get_sprite_locations(self.rom_path)
            self._is_sprites_from_cache = bool(cached_locations)
        except Exception:
            self._is_sprites_from_cache = False

        # Use orchestrator to load sprite locations
        self._worker_orchestrator.load_sprite_locations(self.rom_path, self.rom_extractor)

    def _on_sprite_locations_loaded(self, locations: list[dict[str, Any]]) -> None:
        """Handle sprite locations loaded from orchestrator.

        Args:
            locations: List of sprite location dictionaries
        """
        if self.sprite_selector_widget:
            self.sprite_selector_widget.clear()

        is_from_cache = getattr(self, '_is_sprites_from_cache', False)

        # Convert list to dict format expected by sprite selector
        locations_dict: dict[str, Any] = {}
        for loc in locations:
            name = loc.get("name", f"sprite_0x{loc.get('offset', 0):X}")
            locations_dict[name] = loc

        if locations_dict:
            # Show count of known sprites to make it clear they're available
            cache_text = " (cached)" if is_from_cache else ""
            self.sprite_selector_widget.add_sprite(
                f"-- {len(locations_dict)} Known Sprites Available{cache_text} --", None
            )

            # Add separator for clarity
            self.sprite_selector_widget.insert_separator(1)

            for name, info in locations_dict.items():
                offset = info.get("offset", 0)
                display_name = name.replace("_", " ").title()
                # Add cache indicator if sprites came from cache
                cache_indicator = " \U0001F4BE" if is_from_cache else ""  # floppy disk emoji
                self.sprite_selector_widget.add_sprite(
                    f"{display_name} (0x{offset:06X}){cache_indicator}",
                    (name, offset)
                )
            self.sprite_locations = locations_dict
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

    def _on_sprite_locations_error(self, message: str) -> None:
        """Handle sprite locations loading error.

        Args:
            message: Error message
        """
        logger.exception(f"Failed to load sprite locations: {message}")
        if self.sprite_selector_widget:
            self.sprite_selector_widget.clear()
            self.sprite_selector_widget.add_sprite("Error loading ROM", None)
            self.sprite_selector_widget.set_enabled(False)

    def _init_similarity_indexing(self):
        """Initialize similarity indexing using orchestrator."""
        if not self.rom_path:
            return

        try:
            # Start similarity indexing via orchestrator
            self._worker_orchestrator.start_similarity_indexing(
                rom_path=self.rom_path,
                sprites=[],  # Will be populated by scan
            )
            logger.info(f"Initialized similarity indexing for ROM: {Path(self.rom_path).name}")
        except Exception as e:
            logger.exception(f"Failed to initialize similarity indexing: {e}")

    def _on_similarity_progress(self, message: str):
        """Handle similarity indexing progress updates"""
        logger.debug(f"Indexing sprites: {message}")

    def _on_sprite_indexed(self, sprite_data: dict[str, Any]):
        """Handle individual sprite indexing completion"""
        offset = sprite_data.get("offset", 0)
        logger.debug(f"Sprite at 0x{offset:X} indexed for similarity search")

    def _on_index_saved(self, index_path: str):
        """Handle similarity index save completion"""
        logger.info(f"Similarity index saved to: {index_path}")

    def _on_index_loaded(self, load_path: str):
        """Handle similarity index loading"""
        logger.info(f"Loaded similarity index from: {load_path}")

    def _on_similarity_finished(self):
        """Handle similarity indexing completion"""
        logger.info("Similarity indexing complete")

    def _on_similarity_error(self, error_message: str):
        """Handle similarity indexing errors"""
        logger.error(f"Similarity indexing error: {error_message}")

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

                    # User selected a preset sprite - switch to preset mode
                    self._manual_offset_mode = False

                    self.sprite_selector_widget.set_offset_text(f"0x{offset:06X}")
                    logger.debug("Updated offset label")

                    # Auto-suggest output name based on sprite (via shared OutputSettingsManager)
                    current_output = self._get_output_name()
                    if not current_output:
                        new_name = f"{sprite_name}_sprites"
                        logger.debug(f"Auto-suggesting output name: {new_name}")
                        self.output_name_changed.emit(new_name)

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
                pass  # Silently ignore errors when trying to clear displays  # Silently ignore errors when trying to clear displays

    def _check_extraction_ready(self):
        """Check if extraction is ready - override to handle manual mode"""
        try:
            # Build list of missing requirements for user feedback
            reasons: list[str] = []

            has_rom = bool(self.rom_path)
            if not has_rom:
                reasons.append("Load a ROM file")

            has_output_name = bool(self._get_output_name())
            if not has_output_name:
                reasons.append("Enter output name")

            # Show/hide output name hint (appears when ROM loaded but no output name)
            if hasattr(self, "output_hint_label") and self.output_hint_label:
                show_hint = has_rom and not has_output_name
                self.output_hint_label.setVisible(show_hint)

            if self._manual_offset_mode:
                # In manual mode, just need ROM and output name
                ready = has_rom and has_output_name
            else:
                # In preset mode, also need sprite selection
                has_sprite = self.sprite_selector_widget.get_current_index() > 0
                if not has_sprite:
                    reasons.append("Select a sprite")
                ready = has_rom and has_sprite and has_output_name

            reason_text = " | ".join(reasons) if reasons else ""
            logger.debug(f"Extraction ready: {ready} (manual_mode={self._manual_offset_mode})")
            self.extraction_ready.emit(ready, reason_text)

        except Exception:
            logger.exception("Error in _check_extraction_ready")
            self.extraction_ready.emit(False, "Internal error")

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
            "output_base": self._get_output_name(),
            "cgram_path": (
                self.cgram_selector_widget.get_cgram_path() if self.cgram_selector_widget.get_cgram_path() else None
            ),
        }

    def clear_files(self):
        """Clear all file selections.

        Note: Output name clearing is handled by main window's OutputSettingsManager.
        """
        self.rom_path = ""
        if self.rom_file_widget:
            self.rom_file_widget.clear()
        if self.cgram_selector_widget:
            self.cgram_selector_widget.clear()
        if self.sprite_selector_widget:
            self.sprite_selector_widget.clear()
        self.sprite_locations = {}
        self._check_extraction_ready()
        self.rom_file_widget.set_info_text("No ROM loaded")

    # ========== Sprite Scanning ==========

    def _find_sprites(self):
        """Open dialog to scan for sprite offsets"""
        from ui.dialogs import UserErrorDialog  # Lazy import to avoid cross-UI coupling

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
            UserErrorDialog.display_error(
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
        label.setStyleSheet(get_cache_status_style("checking"))
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

    def _setup_scan_worker(self, dialog: ScanDialog) -> None:
        """Set up the scan worker and connect signals.

        Args:
            dialog: The scan dialog containing UI elements
        """
        from ui.common import WorkerManager

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
        from core.di_container import inject  # Delayed import
        from core.protocols.manager_protocols import ROMCacheProtocol
        from ui.dialogs import ResumeScanDialog  # Lazy import to avoid cross-UI coupling
        rom_cache = inject(ROMCacheProtocol)

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
            self._update_cache_status(dialog, "resuming", "\U0001F4CA Resuming from cached progress...")
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
        dialog.cache_status_label.setStyleSheet(get_cache_status_style(status))

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
        self._update_cache_status(dialog, "saving", "\U0001F4BE Saving results to cache...")
        # Defer actual save to next event loop iteration to allow UI update
        QTimer.singleShot(0, lambda: self._do_cache_save(dialog, found_offsets))

    def _do_cache_save(self, dialog: ScanDialog, found_offsets: list[Any]) -> None:
        """Perform the actual cache save operation."""
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
                                     f"\u2705 Saved {len(found_offsets)} sprites to cache")
            # Update results text
            current_text = dialog.results_text.toPlainText()
            dialog.results_text.setPlainText(
                current_text + "\n\u2705 Results saved to cache for faster future scans.\n"
            )
        else:
            dialog.cache_status_label.setText("\u26A0\uFE0F Could not save to cache")
            current_text = dialog.results_text.toPlainText()
            dialog.results_text.setPlainText(
                current_text + "\n\u26A0\uFE0F Could not save results to cache.\n"
            )

    def _on_cache_status(self, dialog: ScanDialog, status: str) -> None:
        """Handle cache status update."""
        dialog.cache_status_label.setText(f"\U0001F4BE {status}")

        # Update style based on status
        if "Saving" in status:
            style_type = "saving"
        elif "Resuming" in status:
            style_type = "resuming"
        else:
            style_type = "checking"

        dialog.cache_status_label.setStyleSheet(get_cache_status_style(style_type))

    def _on_cache_progress(self, dialog: ScanDialog, progress: int) -> None:
        """Handle cache progress update."""
        if progress > 0:
            dialog.cache_status_label.setText(f"\U0001F4BE Saving progress ({progress}%)...")

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
        from ui.common import WorkerManager

        # Disconnect signals BEFORE cleanup to prevent crashes from queued signals
        if self.scan_worker:
            self.scan_worker.blockSignals(True)
            # Disconnect lambda signals to prevent accessing deleted dialog
            try:
                self.scan_worker.progress_detailed.disconnect()
                self.scan_worker.sprite_found.disconnect()
                self.scan_worker.finished.disconnect()
                self.scan_worker.cache_status.disconnect()
                self.scan_worker.cache_progress.disconnect()
            except (RuntimeError, TypeError):
                pass  # Already disconnected

        # NOW safe to cleanup
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
        self.sprite_selector_widget.add_sprite(f"{display_name} \U0001F4BE", (sprite_name, offset))
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
        """Handle extraction mode change (legacy - kept for compatibility)."""
        # This method is no longer used since we removed the mode combo.
        # Mode is now determined by whether user selects preset sprite or manual offset.
        pass

    def _on_advanced_toggled(self, expanded: bool):
        """Handle advanced section expand/collapse.

        Args:
            expanded: Whether the advanced section is expanded
        """
        # Update arrow direction
        arrow = Qt.ArrowType.DownArrow if expanded else Qt.ArrowType.RightArrow
        self.advanced_toggle.setArrowType(arrow)

        # Show/hide manual offset button
        self.manual_offset_button.setVisible(expanded)

    def _find_next_sprite(self):
        """Find next valid sprite offset - now handled by dialog"""
        # Open dialog if not already open
        if self._offset_dialog_manager.is_open():
            # Dialog will handle the search
            pass
        else:
            self._open_manual_offset_dialog()

    def _find_prev_sprite(self):
        """Find previous valid sprite offset - now handled by dialog"""
        # Open dialog if not already open
        if self._offset_dialog_manager.is_open():
            # Dialog will handle the search
            pass
        else:
            self._open_manual_offset_dialog()

    def _on_search_sprite_found(self, offset: int, quality: float):
        """Handle sprite found during search"""
        self._manual_offset = offset
        logger.debug(f"Found sprite at 0x{offset:06X} (quality: {quality:.2f})")
        # Update dialog if open
        current_dialog = self._offset_dialog_manager.get_current_dialog()
        if current_dialog is not None:
            current_dialog.set_offset(offset)
            current_dialog.add_found_sprite(offset, quality)

    def _on_search_complete(self, found: bool):
        """Handle search completion"""
        if not found:
            logger.debug("No valid sprites found in search range")

    def _on_state_changed(self, old_state: ExtractionState, new_state: ExtractionState):
        """Handle state changes to update UI accordingly"""
        # Update UI elements based on state
        if new_state == ExtractionState.IDLE:
            # Re-enable all controls
            if self.rom_file_widget:
                self.rom_file_widget.setEnabled(True)
            if hasattr(self, "advanced_toggle") and self.advanced_toggle:
                self.advanced_toggle.setEnabled(True)
            self.sprite_selector_widget.set_find_button_enabled(True)
            if self.manual_offset_button:
                self.manual_offset_button.setEnabled(True)

        elif new_state in {ExtractionState.LOADING_ROM, ExtractionState.EXTRACTING}:
            # Disable all controls during critical operations
            if self.rom_file_widget:
                self.rom_file_widget.setEnabled(False)
            if hasattr(self, "advanced_toggle") and self.advanced_toggle:
                self.advanced_toggle.setEnabled(False)
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

        # Use orchestrator cleanup
        self._worker_orchestrator.cleanup()

        # Clean up scan worker (still managed locally)
        if self.scan_worker is not None:
            from ui.common import WorkerManager
            try:
                if hasattr(self.scan_worker, 'cancel'):
                    self.scan_worker.cancel()
                WorkerManager.cleanup_worker(self.scan_worker)
            except Exception as e:
                logger.warning(f"Error cleaning up scan_worker: {e}")
            finally:
                self.scan_worker = None

    def _disconnect_signals(self) -> None:
        """Disconnect all signals to prevent stale handler calls after close."""
        # Orchestrator signals (most critical - these come from background workers)
        orchestrator_signals = [
            "header_loaded",
            "header_error",
            "sprite_locations_loaded",
            "sprite_locations_error",
            "similarity_progress",
            "sprite_indexed",
            "index_saved",
            "index_loaded",
            "similarity_finished",
            "similarity_error",
        ]
        for signal_name in orchestrator_signals:
            try:
                getattr(self._worker_orchestrator, signal_name).disconnect()
            except (RuntimeError, AttributeError):
                pass  # Already disconnected or destroyed

        # State manager signals
        try:
            self.state_manager.workflow_state_changed.disconnect(self._on_state_changed)
        except (RuntimeError, AttributeError):
            pass

        # Dialog manager signals
        try:
            self._offset_dialog_manager.offset_changed.disconnect()
            self._offset_dialog_manager.sprite_found.disconnect()
        except (RuntimeError, AttributeError):
            pass

    @override
    def closeEvent(self, a0: QCloseEvent | None) -> None:
        """Handle panel close event"""
        # Disconnect signals FIRST to prevent stale handler calls
        self._disconnect_signals()

        # Clean up workers before closing
        self._cleanup_workers()

        # Close manual offset dialog via manager
        self._offset_dialog_manager.close()

        # Call parent implementation
        if a0 is not None:
            super().closeEvent(a0)
