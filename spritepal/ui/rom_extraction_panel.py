"""
ROM extraction panel for SpritePal.

This panel coordinates ROM-based sprite extraction using:
- ROMWorkerOrchestrator: Background worker management
- ScanController: Sprite scanning workflow and cache
- OffsetDialogManager: Manual offset dialog lifecycle
"""

from __future__ import annotations

import contextlib
from collections.abc import Mapping
from pathlib import Path
from typing import TYPE_CHECKING, cast, override

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ui.common.file_dialogs import browse_for_open_file

if TYPE_CHECKING:
    from core.managers.core_operations_manager import CoreOperationsManager
    from core.rom_extractor import ROMExtractor
    from core.rom_validator import ROMHeader
    from core.types import SpritePreset

# ExtractionManager accessed via get_app_context().core_operations_manager
from core.managers.workflow_state_manager import ExtractionState
from ui.controllers import (
    ExtractionParamsController,
    ROMSessionController,
    format_sprite_list,
)

# Import extracted components
from ui.rom_extraction import OffsetDialogManager, ROMWorkerOrchestrator, ScanController
from ui.rom_extraction.widgets import (
    CGRAMSelectorWidget,
    ROMFileWidget,
    SpriteSelectorWidget,
)
from ui.styles.components import get_manual_offset_button_style
from ui.styles.theme import COLORS
from utils.constants import (
    ROM_SIZE_4MB,
    SETTINGS_KEY_LAST_INPUT_ROM,
    SETTINGS_NS_ROM_INJECTION,
)
from utils.logging_config import get_logger

logger = get_logger(__name__)

# UI Spacing Constants (imported from centralized module)
from ui.common.spacing_constants import (
    BUTTON_HEIGHT,
    SPACING_COMPACT_MEDIUM,
    SPACING_COMPACT_SMALL,
)


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
    rom_extraction_requested = Signal(str, int, str, str)  # rom_path, offset, output_base, sprite_name
    output_name_changed = Signal(str)  # Emit when output name changes in ROM panel

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        extraction_manager: CoreOperationsManager,
    ) -> None:
        super().__init__(parent)

        self.rom_path = ""
        self.sprite_locations: dict[str, Mapping[str, object]] = {}
        # Use injected extraction manager
        self.extraction_manager = extraction_manager
        self.rom_extractor: ROMExtractor = self.extraction_manager.get_rom_extractor()
        self.rom_size = 0  # Track ROM size for slider limits
        self._current_header: ROMHeader | None = None  # Stored header for preset matching

        # Controllers for extraction logic
        self._params_controller = ExtractionParamsController(parent=self)
        self._rom_session = ROMSessionController(parent=self)

        # State manager for coordinating operations (ApplicationStateManager)
        from core.app_context import get_app_context

        context = get_app_context()
        self.state_manager = context.application_state_manager
        self.state_manager.workflow_state_changed.connect(self._on_state_changed)

        # Initialize extracted components
        self._worker_orchestrator = ROMWorkerOrchestrator(
            self,
            rom_cache=context.rom_cache,
            settings_manager=self.state_manager,
        )
        self._offset_dialog_manager = OffsetDialogManager(parent_widget=self, parent=self)
        self._scan_controller = ScanController(state_manager=self.state_manager, parent=self)
        self._scan_controller.sprite_selected.connect(self._add_selected_sprite)
        self.scan_worker = None

        # Connect orchestrator signals
        self._connect_orchestrator_signals()

        # Connect dialog manager signals
        self._offset_dialog_manager.offset_changed.connect(self._on_dialog_offset_changed)
        self._offset_dialog_manager.sprite_found.connect(self._on_dialog_sprite_found)

        # Output name (set via signal from OutputSettingsManager)
        self._output_name: str = ""

        # Connect controller signals
        self._params_controller.readiness_changed.connect(self.extraction_ready.emit)

        self._setup_ui()
        self._load_last_rom()

    def _connect_orchestrator_signals(self) -> None:
        """Connect signals from the worker orchestrator."""
        # Header loading
        self._worker_orchestrator.header_loaded.connect(self._on_header_loaded)
        self._worker_orchestrator.header_error.connect(self._on_header_load_error)

        # Sprite locations
        self._worker_orchestrator.sprite_locations_loaded.connect(self._on_sprite_locations_loaded)
        self._worker_orchestrator.sprite_locations_error.connect(self._on_sprite_locations_error)

        # Similarity indexing (logging only)
        self._worker_orchestrator.similarity_progress.connect(self._on_similarity_progress)
        self._worker_orchestrator.sprite_indexed.connect(self._on_sprite_indexed)
        self._worker_orchestrator.index_saved.connect(self._on_index_saved)
        self._worker_orchestrator.index_loaded.connect(self._on_index_loaded)
        self._worker_orchestrator.similarity_finished.connect(self._on_similarity_finished)
        self._worker_orchestrator.similarity_error.connect(self._on_similarity_error)

    def set_output_name(self, name: str) -> None:
        """Set the output name (slot for OutputSettingsManager.output_name_changed signal).

        Args:
            name: The current output name string
        """
        self._output_name = name

    def _get_output_name(self) -> str:
        """Get the current output name.

        Returns:
            Output name string, or empty string if not set
        """
        return self._output_name

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
        layout.setSpacing(SPACING_COMPACT_MEDIUM)  # 10px between sections
        layout.setContentsMargins(
            SPACING_COMPACT_SMALL, SPACING_COMPACT_SMALL, SPACING_COMPACT_SMALL, SPACING_COMPACT_SMALL
        )

        # Add all widget groups
        self._add_rom_controls(layout)
        self._add_mode_controls(layout)
        self._add_manual_offset_controls(layout)
        self._add_output_controls(layout)

        # No spacer needed here - main_window handles vertical expansion via scroll area
        main_panel.setLayout(layout)
        return main_panel

    def _add_rom_controls(self, layout: QVBoxLayout):
        """Add ROM file selection controls to the layout.

        Args:
            layout: Layout to add controls to
        """
        from core.app_context import get_app_context

        self.rom_file_widget = ROMFileWidget(rom_cache=get_app_context().rom_cache)
        self.rom_file_widget.browse_clicked.connect(self._browse_rom)
        self.rom_file_widget.partial_scan_detected.connect(self._on_partial_scan_detected)
        layout.addWidget(self.rom_file_widget)

        # Hint label - shown when ROM loaded but auto-fill failed (rare edge case)
        # Most times, output name is auto-filled from ROM filename
        self.output_hint_label = QLabel("↓ Enter output name in the Output Settings section below")
        self.output_hint_label.setStyleSheet(f"color: {COLORS['warning']}; font-size: 11px; font-style: italic;")
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
        self.sprite_selector_widget.manage_presets_clicked.connect(self._open_presets_dialog)
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
        self.advanced_toggle.setText("Manual Offset Browser")
        self.advanced_toggle.setCheckable(True)
        self.advanced_toggle.setChecked(False)
        self.advanced_toggle.setArrowType(Qt.ArrowType.RightArrow)
        self.advanced_toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.advanced_toggle.setToolTip(
            "Manually browse sprites at any ROM offset\ninstead of using the preset sprite list above"
        )
        self.advanced_toggle.setStyleSheet(
            "QToolButton { border: none; padding: 4px; font-weight: bold; }"
            "QToolButton:hover { background-color: rgba(255, 255, 255, 0.1); }"
            "QToolButton::right-arrow { subcontrol-position: center left; }"
            "QToolButton::down-arrow { subcontrol-position: center left; }"
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
        button.setToolTip("Open advanced sprite browser to explore ROM offsets manually\nKeyboard shortcut: Ctrl+M")
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
        filename = browse_for_open_file(self, "Select ROM File", "SNES ROM Files (*.sfc *.smc);;All Files (*.*)")

        if filename:
            self._load_rom_file(filename)

    def _on_partial_scan_detected(self, scan_info: Mapping[str, object]) -> None:
        """Handle detection of partial scan cache"""
        from ui.dialogs import ResumeScanDialog  # Lazy import to avoid cross-UI coupling

        # Show resume dialog to ask user what to do
        user_choice = ResumeScanDialog.show_resume_dialog(dict(scan_info), self)

        if user_choice == ResumeScanDialog.RESUME:
            # User wants to resume - trigger scan dialog
            self._find_sprites()
        elif user_choice == ResumeScanDialog.START_FRESH:
            # User wants fresh scan - will be handled when they click Find Sprites
            # Just inform them
            QMessageBox.information(
                self,
                "Fresh Scan",
                "The partial scan cache will be ignored. \nClick 'Find Sprites' to start a fresh scan.",
            )
        # If CANCEL, do nothing

    def _load_last_rom(self) -> None:
        """Load the last used ROM file from settings."""
        last_rom = self._rom_session.get_last_rom_path()
        if last_rom:
            logger.info(f"Loading last used ROM: {last_rom}")
            self._load_rom_file(last_rom)

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
                self.rom_size = ROM_SIZE_4MB  # Default 4MB

            # Save to settings
            from core.app_context import get_app_context

            settings = get_app_context().application_state_manager
            settings.set(SETTINGS_NS_ROM_INJECTION, SETTINGS_KEY_LAST_INPUT_ROM, filename)
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

    def _on_header_loaded(self, result: Mapping[str, object]) -> None:
        """Handle ROM header loaded from orchestrator.

        Args:
            result: Dict with 'header' and 'sprite_configs' keys
        """
        # Hide loading indicator
        self.rom_file_widget.hide_loading()

        header = cast("ROMHeader | None", result.get("header"))
        sprite_configs = result.get("sprite_configs")

        # Store header for preset matching
        self._current_header = header

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

    def _open_manual_offset_dialog(self) -> None:
        """Open the manual offset control dialog using manager."""
        from ui.dialogs import UserErrorDialog  # Lazy import to avoid cross-UI coupling

        logger.debug("_open_manual_offset_dialog called")

        if not self.rom_path:
            UserErrorDialog.display_error(
                self, "Please load a ROM file first", "A ROM must be loaded before using manual offset control."
            )
            return

        # Use dialog manager to open the dialog
        dialog = self._offset_dialog_manager.open_dialog(
            rom_path=self.rom_path,
            extractor=self.rom_extractor,
            rom_size=self.rom_size,
            extraction_manager=self.extraction_manager,
            initial_offset=self._params_controller.manual_offset,
        )

        if dialog:
            logger.debug("Opened ManualOffsetDialog via manager")

    def _on_dialog_offset_changed(self, offset: int) -> None:
        """Handle offset changes from the dialog."""
        self._params_controller.set_manual_mode(enabled=True, offset=offset)
        self._check_extraction_ready()
        # Preview now handled in manual offset dialog

    def _on_dialog_sprite_found(self, sprite_data: Mapping[str, object]) -> None:
        """Handle sprite found signal from dialog."""
        offset = cast(int, sprite_data.get("offset", 0))
        self._params_controller.set_manual_mode(enabled=True, offset=offset)
        self._check_extraction_ready()

    def _open_presets_dialog(self) -> None:
        """Open the sprite presets management dialog."""
        from ui.dialogs.sprite_preset_dialog import SpritePresetDialog

        # Get current ROM info for auto-filtering
        game_title: str | None = None
        checksum: int | None = None
        if self._current_header is not None:
            game_title = self._current_header.title
            checksum = self._current_header.checksum

        dialog = SpritePresetDialog(
            current_game_title=game_title or "",
            current_checksum=checksum,
            parent=self,
        )

        # Connect preset_selected signal to handle the selection
        dialog.preset_selected.connect(self._on_preset_applied)
        dialog.exec()

    def _on_preset_applied(self, preset: SpritePreset) -> None:
        """Handle applying a preset from the dialog.

        Args:
            preset: The SpritePreset to apply
        """
        logger.info(f"Applying preset '{preset.name}' at offset 0x{preset.offset:06X}")

        # Set the manual offset from the preset via controller
        self._params_controller.set_manual_mode(enabled=True, offset=preset.offset)

        # Update the offset display
        if self.sprite_selector_widget:
            self.sprite_selector_widget.set_offset_text(f"0x{preset.offset:06X}")

        # Check extraction readiness
        self._check_extraction_ready()

    def _browse_cgram(self):
        """Browse for CGRAM file"""
        # Try to use ROM directory as default
        initial_path = str(Path(self.rom_path).parent) if self.rom_path else ""

        filename = browse_for_open_file(
            self, "Select CGRAM File", "CGRAM Files (*.dmp *.bin);;All Files (*.*)", initial_path
        )

        if filename:
            self.cgram_selector_widget.set_cgram_path(filename)

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
            from core.app_context import get_app_context

            rom_cache = get_app_context().rom_cache
            cached_locations = rom_cache.get_sprite_locations(self.rom_path)
            self._is_sprites_from_cache = bool(cached_locations)
        except Exception:
            self._is_sprites_from_cache = False

        # Use orchestrator to load sprite locations
        self._worker_orchestrator.load_sprite_locations(self.rom_path, self.rom_extractor)

    def _on_sprite_locations_loaded(self, locations: list[Mapping[str, object]]) -> None:
        """Handle sprite locations loaded from orchestrator.

        Args:
            locations: List of sprite location dictionaries
        """
        if self.sprite_selector_widget:
            self.sprite_selector_widget.clear()

        is_from_cache = getattr(self, "_is_sprites_from_cache", False)

        # Use formatter to get display items
        formatted = format_sprite_list(locations, is_from_cache=is_from_cache)

        # Build locations dict for internal tracking
        locations_dict: dict[str, Mapping[str, object]] = {}
        for loc in locations:
            name = cast(str, loc.get("name", f"sprite_0x{cast(int, loc.get('offset', 0)):X}"))
            locations_dict[name] = loc

        # Populate sprite selector with formatted items
        for item in formatted.items:
            if item.is_separator:
                self.sprite_selector_widget.insert_separator(self.sprite_selector_widget.count())
            else:
                self.sprite_selector_widget.add_sprite(item.display_text, item.data)

        self.sprite_locations = locations_dict
        self.sprite_selector_widget.set_enabled(formatted.has_sprites)

        # Update button text and tooltip
        self.sprite_selector_widget.set_find_button_text(formatted.button_text)
        self.sprite_selector_widget.set_find_button_tooltip(formatted.button_tooltip)
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

    def _on_sprite_indexed(self, sprite_data: Mapping[str, object]) -> None:
        """Handle individual sprite indexing completion"""
        offset = cast(int, sprite_data.get("offset", 0))
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

    def _on_sprite_changed(self, index: int) -> None:
        """Handle sprite selection change."""
        try:
            if index > 0:
                data = self.sprite_selector_widget.get_current_data()
                if data:
                    sprite_name, offset = data
                    # Switch to preset mode via controller
                    self._params_controller.set_preset_mode(offset=offset)
                    self.sprite_selector_widget.set_offset_text(f"0x{offset:06X}")

                    # Auto-suggest output name based on sprite
                    if not self._get_output_name():
                        self.output_name_changed.emit(f"{sprite_name}_sprites")
                else:
                    logger.warning("No data found for selected sprite")
            else:
                self.sprite_selector_widget.set_offset_text("--")

            self._check_extraction_ready()
        except Exception:
            logger.exception("Error in _on_sprite_changed")
            with contextlib.suppress(Exception):
                self.sprite_selector_widget.set_offset_text("Error")

    def _check_extraction_ready(self) -> None:
        """Check if extraction is ready using controller."""
        try:
            has_rom = bool(self.rom_path)
            has_output_name = bool(self._get_output_name())
            has_sprite = self.sprite_selector_widget.get_current_index() > 0

            # Show/hide output name hint (appears when ROM loaded but no output name)
            if hasattr(self, "output_hint_label") and self.output_hint_label:
                show_hint = has_rom and not has_output_name
                self.output_hint_label.setVisible(show_hint)

            # Delegate to controller (emits readiness_changed -> extraction_ready)
            self._params_controller.check_readiness(
                has_rom=has_rom,
                has_sprite=has_sprite,
                has_output_name=has_output_name,
            )

        except Exception:
            logger.exception("Error in _check_extraction_ready")
            self.extraction_ready.emit(False, "Internal error")

    def get_extraction_params(self) -> dict[str, object] | None:
        """Get parameters for ROM extraction using controller.

        Returns:
            Dict with keys: rom_path, sprite_offset, sprite_name, output_base, cgram_path
        """
        # Get sprite data for preset mode
        sprite_data: tuple[str, int] | None = None
        if not self._params_controller.is_manual_mode:
            if self.sprite_selector_widget.get_current_index() > 0:
                sprite_data = self.sprite_selector_widget.get_current_data()

        return self._params_controller.get_params_dict(
            rom_path=self.rom_path,
            output_base=self._get_output_name(),
            sprite_data=sprite_data,
            cgram_path=self.cgram_selector_widget.get_cgram_path() or None,
        )

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

    def _find_sprites(self) -> None:
        """Open dialog to scan for sprite offsets.

        Delegates to ScanController which handles:
        - State manager coordination
        - Dialog creation and management
        - Worker lifecycle
        - Cache operations
        """
        if not self.rom_path:
            return

        self._scan_controller.start_scan(
            rom_path=self.rom_path,
            extractor=self.rom_extractor,
            parent_widget=self,
        )

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
        self.sprite_selector_widget.add_sprite(f"{display_name} \U0001f4be", (sprite_name, offset))
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
        from ui.common import WorkerManager

        if self.scan_worker is not None:
            try:
                if hasattr(self.scan_worker, "cancel"):
                    self.scan_worker.cancel()
            except Exception as e:
                logger.warning(f"Error cancelling scan_worker: {e}")
        try:
            WorkerManager.cleanup_worker_attr(self, "scan_worker")
        except Exception as e:
            logger.warning(f"Error cleaning up scan_worker: {e}")

    def _disconnect_signals(self) -> None:
        """Disconnect all signals to prevent stale handler calls after close."""
        import warnings

        # Suppress PySide6 disconnect warnings (emitted before exception is raised)
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", "Failed to disconnect", RuntimeWarning)

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

    def cleanup(self) -> None:
        """Clean up resources when panel is closed.

        This must be called explicitly from MainWindow._cleanup_managers()
        because child widget closeEvent is NOT called when parent window closes.
        """
        self._disconnect_signals()
        self._cleanup_workers()
        self._offset_dialog_manager.close()
