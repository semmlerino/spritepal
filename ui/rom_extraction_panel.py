"""
ROM extraction panel for SpritePal.

This panel coordinates ROM-based sprite extraction using:
- ROMWorkerOrchestrator: Background worker management
- ScanController: Sprite scanning workflow and cache
- OffsetDialogManager: Manual offset dialog lifecycle
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import TYPE_CHECKING, cast, override

from PySide6.QtCore import Signal
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QLabel,
    QLineEdit,
    QMessageBox,
    QVBoxLayout,
    QWidget,
)

from ui.common.file_dialogs import browse_for_open_file
from ui.common.signal_utils import safe_disconnect

if TYPE_CHECKING:
    from core.managers.application_state_manager import ApplicationStateManager
    from core.managers.core_operations_manager import CoreOperationsManager
    from core.rom_extractor import ROMExtractor
    from core.rom_validator import ROMHeader
    from core.services.rom_cache import ROMCache
    from core.types import SpritePreset
    from ui.rom_extraction.modules import Mesen2Module

from core.managers.workflow_state_manager import ExtractionState

# Import extracted components
from ui.controllers import (
    ExtractionParamsController,
    ROMSessionController,
    format_sprite_list,
)
from ui.rom_extraction import OffsetDialogManager, ROMWorkerOrchestrator, ScanController
from ui.rom_extraction.widgets import (
    CGRAMSelectorWidget,
    ManualOffsetSection,
    MesenCapturesSection,
    ROMFileWidget,
    SpriteSelectorWidget,
)
from ui.styles import get_section_label_style
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
    rom_loaded = Signal(str)  # Emitted when a ROM is successfully loaded
    extraction_ready = Signal(bool, str)  # (ready, reason_if_not_ready)
    rom_extraction_requested = Signal(str, int, str, str)  # rom_path, offset, output_base, sprite_name
    output_name_changed = Signal(str)  # Emit when output name changes in ROM panel
    open_in_sprite_editor = Signal(int)  # Emitted when user wants to open offset in sprite editor
    mesen2_watching_changed = Signal(bool)  # Emitted when log watcher status changes

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        extraction_manager: CoreOperationsManager,
        state_manager: ApplicationStateManager,
        rom_cache: ROMCache,
        mesen2_module: Mesen2Module | None = None,
    ) -> None:
        super().__init__(parent)

        self.rom_path = ""
        self.sprite_locations: dict[str, Mapping[str, object]] = {}
        # Use injected dependencies
        self.extraction_manager = extraction_manager
        self.state_manager = state_manager
        self.rom_cache = rom_cache
        self._mesen2_module = mesen2_module
        self.rom_extractor: ROMExtractor = self.extraction_manager.get_rom_extractor()
        self.rom_size = 0  # Track ROM size for slider limits
        self._current_header: ROMHeader | None = None  # Stored header for preset matching

        # Controllers for extraction logic
        self._params_controller = ExtractionParamsController(parent=self)
        self._rom_session = ROMSessionController(parent=self, settings_manager=self.state_manager)

        # Connect state manager signals
        self.state_manager.workflow_state_changed.connect(self._on_state_changed)

        # Initialize extracted components
        self._worker_orchestrator = ROMWorkerOrchestrator(
            self,
            rom_cache=self.rom_cache,
            settings_manager=self.state_manager,
        )
        self._offset_dialog_manager = OffsetDialogManager(parent_widget=self, parent=self)
        self._scan_controller = ScanController(parent=self, cache=self.rom_cache, state_manager=self.state_manager)
        self._scan_controller.sprite_selected.connect(self._add_selected_sprite)
        self.scan_worker = None

        # Connect orchestrator signals
        self._connect_orchestrator_signals()

        # Connect dialog manager signals
        self._offset_dialog_manager.offset_changed.connect(self._on_dialog_offset_changed)
        self._offset_dialog_manager.sprite_found.connect(self._on_dialog_sprite_found)

        # Output name provider (set by MainWindow to read from OutputSettingsManager)
        self._output_name_provider: Callable[[], str] | None = None

        # Connect controller signals
        self._params_controller.readiness_changed.connect(self.extraction_ready.emit)
        self._params_controller.mode_changed.connect(self._on_mode_changed)

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

    def set_output_name_provider(self, provider: Callable[[], str]) -> None:
        """Set the output name provider (reads from OutputSettingsManager).

        Args:
            provider: Callable that returns the current output name
        """
        self._output_name_provider = provider

    def set_output_name(self, name: str) -> None:
        """Set the output name (slot for OutputSettingsManager.output_name_changed signal).

        Syncs the inline output name field with the main OutputSettingsManager.

        Args:
            name: The current output name string
        """
        if hasattr(self, "output_name_edit") and self.output_name_edit:
            self.output_name_edit.blockSignals(True)
            self.output_name_edit.setText(name)
            self.output_name_edit.blockSignals(False)

    def _get_output_name(self) -> str:
        """Get the current output name from the provider.

        Returns:
            Output name string, or empty string if provider not set
        """
        if self._output_name_provider is not None:
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
        layout.setSpacing(SPACING_COMPACT_MEDIUM)  # 10px between sections
        layout.setContentsMargins(
            SPACING_COMPACT_SMALL, SPACING_COMPACT_SMALL, SPACING_COMPACT_SMALL, SPACING_COMPACT_SMALL
        )

        # Add all widget groups
        self._add_rom_controls(layout)
        self._add_mesen2_captures(layout)  # Mesen2 offset discovery
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
        self.rom_file_widget = ROMFileWidget(rom_cache=self.rom_cache)
        self.rom_file_widget.browse_clicked.connect(self._browse_rom)
        self.rom_file_widget.partial_scan_detected.connect(self._on_partial_scan_detected)
        layout.addWidget(self.rom_file_widget)

        # Hint label - shown when ROM loaded but auto-fill failed (rare edge case)
        # Most times, output name is auto-filled from ROM filename
        self.output_hint_label = QLabel("↓ Enter output name in the Output Settings section below")
        self.output_hint_label.setStyleSheet(f"color: {COLORS['warning']}; font-size: 11px; font-style: italic;")
        self.output_hint_label.setVisible(False)
        layout.addWidget(self.output_hint_label)

    def _add_mesen2_captures(self, layout: QVBoxLayout) -> None:
        """Add Mesen2 captures widget for offset discovery.

        This widget shows recently discovered ROM offsets from Mesen2's
        sprite_rom_finder.lua script. Users can click on captures to
        jump directly to those offsets.

        Args:
            layout: Layout to add the widget to
        """
        # Create MesenCapturesSection widget
        self.mesen_captures_section = MesenCapturesSection(self)
        layout.addWidget(self.mesen_captures_section)

        # Connect widget signals to panel handlers
        self.mesen_captures_section.offset_selected.connect(self._on_mesen2_offset_selected)
        self.mesen_captures_section.offset_activated.connect(self._on_mesen2_offset_activated)
        self.mesen_captures_section.watching_changed.connect(self.mesen2_watching_changed.emit)

        # Wire up log watcher if module provided (dependency injection)
        if self._mesen2_module is not None:
            # Module handles all LogWatcher connections and lifecycle
            self._mesen2_module.connect_to_widget(self.mesen_captures_section)
            logger.debug("Mesen2Module connected to captures widget")

    def _on_mesen2_offset_selected(self, offset: int) -> None:
        """Handle offset selection (single-click) from captures widget.

        Shows preview at the selected offset.

        Args:
            offset: ROM offset that was selected
        """
        logger.debug("Mesen2 offset selected: 0x%06X", offset)
        # Update the offset dialog if it's open
        if self._offset_dialog_manager._dialog is not None:
            self._offset_dialog_manager._dialog.set_offset(offset)

    def _on_mesen2_offset_activated(self, offset: int) -> None:
        """Handle offset activation (double-click) from captures widget.

        Opens the offset in the Sprite Editor tab.

        Args:
            offset: ROM offset to jump to
        """
        logger.info("Mesen2 offset activated: 0x%06X - opening in sprite editor", offset)
        # Emit signal for MainWindow to switch to sprite editor tab
        self.open_in_sprite_editor.emit(offset)

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
        # Create manual offset section widget
        self.manual_offset_section = ManualOffsetSection()
        self.manual_offset_section.browse_clicked.connect(self.open_manual_offset_dialog)
        layout.addWidget(self.manual_offset_section)

    def _add_output_controls(self, layout: QVBoxLayout):
        """Add output and CGRAM controls to the layout.

        Args:
            layout: Layout to add controls to
        """
        # Output Name section (Vertical layout for better resizing behavior)
        output_section = QVBoxLayout()
        output_section.setSpacing(SPACING_COMPACT_SMALL)  # 6px spacing

        output_label = QLabel("Output Name:")
        output_label.setStyleSheet(get_section_label_style())
        output_section.addWidget(output_label)

        self.output_name_edit = QLineEdit()
        self.output_name_edit.setPlaceholderText("e.g. kirby_sprites")
        self.output_name_edit.textChanged.connect(self._on_output_name_text_changed)
        self.output_name_edit.setMinimumHeight(32)  # Standard input height
        output_section.addWidget(self.output_name_edit)

        layout.addLayout(output_section)

        # CGRAM selector widget
        self.cgram_selector_widget = CGRAMSelectorWidget()
        self.cgram_selector_widget.browse_clicked.connect(self._browse_cgram)
        layout.addWidget(self.cgram_selector_widget)

    def _on_output_name_text_changed(self, text: str) -> None:
        """Handle output name text change from inline field.

        Emits signal to notify MainWindow, which updates OutputSettingsManager.
        """
        self.output_name_changed.emit(text)
        self._check_extraction_ready()

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
            self.state_manager.set(SETTINGS_NS_ROM_INJECTION, SETTINGS_KEY_LAST_INPUT_ROM, filename)
            self.state_manager.set_last_used_directory(str(Path(filename).parent))
            logger.debug(f"Saved ROM to settings: {filename}")

            # Read ROM header asynchronously using orchestrator
            self.rom_file_widget.show_loading("Loading ROM header...")
            self._worker_orchestrator.load_header(filename, self.rom_extractor)

            # Notify that files changed
            self.files_changed.emit()
            self.rom_loaded.emit(filename)

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

    def open_manual_offset_dialog(self) -> None:
        """Open the manual offset control dialog using manager."""
        from ui.dialogs import UserErrorDialog  # Lazy import to avoid cross-UI coupling

        logger.debug("open_manual_offset_dialog called")

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
            cached_locations = self.rom_cache.get_sprite_locations(self.rom_path)
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

    def _on_sprite_changed(self, data: object) -> None:
        """Handle sprite selection change."""
        try:
            if data:
                # Assuming data is tuple (name, offset)
                if isinstance(data, tuple) and len(data) >= 2:
                    sprite_name, offset = data
                    # Switch to preset mode via controller
                    self._params_controller.set_preset_mode(offset=offset)
                    self.sprite_selector_widget.set_offset_text(f"0x{offset:06X}")

                    # Auto-suggest output name based on sprite
                    if not self._get_output_name():
                        suggested_name = f"{sprite_name}_sprites"
                        self.output_name_edit.setText(suggested_name)
                        self.output_name_changed.emit(suggested_name)
                else:
                    logger.warning(f"Invalid data format for selected sprite: {data}")
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
            has_sprite = self.sprite_selector_widget.get_current_data() is not None

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

    def get_last_mesen_offset(self) -> int | None:
        """Get the last selected Mesen2 capture offset.

        This is a public interface to the Mesen2 captures widget. When the user
        clicks on a captured sprite offset from Mesen2, this method returns that
        offset so the UI can jump to it in the sprite editor or offset dialog.

        Returns:
            The offset if one is selected, None otherwise.
        """
        return self.mesen_captures_section.get_selected_offset()

    def get_extraction_params(self) -> dict[str, object] | None:
        """Get parameters for ROM extraction using controller.

        Returns:
            Dict with keys: rom_path, sprite_offset, sprite_name, output_base, cgram_path
        """
        # Get sprite data for preset mode
        sprite_data: tuple[str, int] | None = None
        if not self._params_controller.is_manual_mode:
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
        """Add the selected sprite to the tree.

        Args:
            offset: The selected sprite offset
        """
        sprite_name = f"custom_0x{offset:X}"
        # Use category prefix for tree organization
        display_name = f"Custom - Sprite (0x{offset:06X})"
        sprite_data = (sprite_name, offset)

        # Select if exists
        self.sprite_selector_widget.select_item_by_data(sprite_data)

        # If not selected (meaning not found), add it
        current_data = self.sprite_selector_widget.get_current_data()
        if current_data != sprite_data:
            self.sprite_selector_widget.add_sprite(f"{display_name} \U0001f4be", sprite_data)
            self.sprite_selector_widget.select_item_by_data(sprite_data)

        logger.info(f"User selected custom sprite offset: 0x{offset:X}")

    def _on_advanced_toggled(self, expanded: bool):
        """Handle advanced section expand/collapse.

        Args:
            expanded: Whether the advanced section is expanded
        """
        # Widget handles its own toggle state - this is now just a placeholder
        # for any additional logic needed when section expands/collapses
        pass

    def _on_mode_changed(self, is_manual: bool) -> None:
        """Handle extraction mode change.

        Args:
            is_manual: Whether manual offset mode is active
        """
        # Update sprite selector state
        # When manual mode is active, disable sprite selector (visual indication is sufficient)
        self.sprite_selector_widget.setEnabled(not is_manual)

        # Update manual offset indicator
        if hasattr(self, "manual_offset_section"):
            if is_manual:
                offset = self._params_controller.manual_offset
                self.manual_offset_section.set_offset_display(f"Manual offset: 0x{offset:06X}")
            else:
                self.manual_offset_section.set_offset_display("")

    def _on_state_changed(self, old_state: ExtractionState, new_state: ExtractionState):
        """Handle state changes to update UI accordingly"""
        # Update UI elements based on state
        if new_state == ExtractionState.IDLE:
            # Re-enable all controls
            if self.rom_file_widget:
                self.rom_file_widget.setEnabled(True)
            if hasattr(self, "manual_offset_section"):
                self.manual_offset_section.setEnabled(True)
            self.sprite_selector_widget.set_find_button_enabled(True)

        elif new_state in {ExtractionState.LOADING_ROM, ExtractionState.EXTRACTING}:
            # Disable all controls during critical operations
            if self.rom_file_widget:
                self.rom_file_widget.setEnabled(False)
            if hasattr(self, "manual_offset_section"):
                self.manual_offset_section.setEnabled(False)
            self.sprite_selector_widget.set_find_button_enabled(False)

        elif new_state == ExtractionState.SCANNING_SPRITES:
            # Disable sprite selection during scan
            self.sprite_selector_widget.set_find_button_enabled(False)

        elif new_state == ExtractionState.SEARCHING_SPRITE:
            # Disable navigation during search
            if hasattr(self, "manual_offset_section"):
                self.manual_offset_section.set_browse_enabled(False)

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
            if hasattr(self._worker_orchestrator, signal_name):
                safe_disconnect(getattr(self._worker_orchestrator, signal_name))

        # State manager signals
        safe_disconnect(self.state_manager.workflow_state_changed)

        # Dialog manager signals
        safe_disconnect(self._offset_dialog_manager.offset_changed)
        safe_disconnect(self._offset_dialog_manager.sprite_found)

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
