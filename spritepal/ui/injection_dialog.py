"""
Injection dialog for SpritePal
Allows users to configure sprite injection parameters
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path
from typing import TYPE_CHECKING, cast, override

if TYPE_CHECKING:
    from core.managers.application_state_manager import ApplicationStateManager
    from core.managers.core_operations_manager import CoreOperationsManager

from PySide6.QtCore import Qt
from PySide6.QtGui import QCloseEvent, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QSplitter,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

# CoreOperationsManager accessed via get_app_context().core_operations_manager
from core.sprite_validator import SpriteValidator
from ui.common import WorkerManager
from ui.common.spacing_constants import EXTRACTION_LABEL_MIN_WIDTH, SPACING_SMALL
from ui.components import (
    FileSelector,
    FormRow,
    HexOffsetInput,
    TabbedDialog,
)
from ui.styles import get_splitter_style
from ui.utils.accessibility import AccessibilityHelper
from ui.widgets.sprite_preview_widget import SpritePreviewWidget
from ui.workers.rom_info_loader_worker import ROMInfoLoaderWorker
from utils.logging_config import get_logger

logger = get_logger(__name__)


class InjectionDialog(TabbedDialog):
    """Dialog for configuring sprite injection parameters"""

    def __init__(
        self,
        parent: QWidget | None = None,
        sprite_path: str = "",
        metadata_path: str = "",
        input_vram: str = "",
        *,
        injection_manager: CoreOperationsManager,
        settings_manager: ApplicationStateManager,
    ):
        # Step 1: Declare instance variables BEFORE super().__init__()
        self.sprite_path = sprite_path
        self.metadata_path = metadata_path
        self.suggested_input_vram = input_vram
        self.metadata: Mapping[str, object] | None = None
        self.extraction_vram_offset: str | None = None
        self.rom_extraction_info: Mapping[str, object] | None = None
        self.injection_manager = injection_manager
        self.settings_manager = settings_manager

        # Initialize UI components that will be created in setup methods
        self.extraction_group: QGroupBox | None = None
        self.extraction_info: QTextEdit | None = None
        self.tab_widget: QTabWidget | None = None
        self.preview_widget: SpritePreviewWidget | None = None
        self.rom_info_group: QGroupBox | None = None
        self.rom_info_text: QTextEdit | None = None

        # File selectors
        self.sprite_file_selector: FileSelector | None = None
        self.input_vram_selector: FileSelector | None = None
        self.output_vram_selector: FileSelector | None = None
        self.input_rom_selector: FileSelector | None = None
        self.output_rom_selector: FileSelector | None = None

        # Input widgets
        self.vram_offset_input: HexOffsetInput | None = None
        self.rom_offset_input: HexOffsetInput | None = None
        self.sprite_location_combo: QComboBox | None = None
        self.fast_compression_check: QCheckBox | None = None

        # Background workers for async operations
        self._rom_info_loader: ROMInfoLoaderWorker | None = None

        # Guard flag to prevent signal callbacks on closing/deleted dialog
        self._is_closing: bool = False

        # Pending offset to restore after async ROM info load completes
        # This fixes a race condition where combo matching was attempted
        # before the combo was populated by the background worker
        self._pending_rom_offset: int | None = None
        self._pending_custom_offset: str | None = None

        # Step 2: Call parent init (this will call _setup_ui)
        super().__init__(
            parent=parent,
            title="Inject Sprite",
            modal=True,
            size=(1400, 900),  # Increased default size for better layout
            min_size=(1200, 800),  # Increased minimum size
            with_status_bar=False,
            default_tab=1,  # ROM injection tab as default
        )
        self._load_metadata()
        self._set_initial_paths()

    @override
    def _setup_ui(self) -> None:
        """Initialize the user interface"""
        # Call parent setup first to initialize tab widget
        super()._setup_ui()

        # Create shared preview widget
        self.preview_widget = SpritePreviewWidget("Sprite to Inject")

        # Create shared sprite file selector at dialog level
        self.sprite_file_selector = FileSelector(
            label_text="Sprite File:",
            placeholder="Select sprite file to inject...",
            browse_text="Browse...",
            mode="open",
            file_filter="PNG Files (*.png);;All Files (*.*)",
            read_only=False,
            settings_manager=self.settings_manager,
        )
        self.sprite_file_selector.set_path(self.sprite_path)
        self.sprite_file_selector.path_changed.connect(self._on_sprite_path_changed)
        self.sprite_file_selector.setToolTip("Select the PNG sprite file to inject into VRAM or ROM")

        # Add sprite selector above tabs - insert directly into main_layout
        tab_widget = self._main_tab_widget

        # Remove tab widget from main layout so we can insert sprite group first
        if tab_widget:
            self.main_layout.removeWidget(tab_widget)

        # Create sprite group
        sprite_group = QGroupBox("Sprite to Inject")
        sprite_layout = QVBoxLayout()
        sprite_layout.addWidget(self.sprite_file_selector)
        sprite_group.setLayout(sprite_layout)

        # Insert sprite group at position 0, tab widget at position 1
        self.main_layout.insertWidget(0, sprite_group)
        if tab_widget:
            self.main_layout.insertWidget(1, tab_widget)

        # Set spacing on main layout (was on container_layout before)
        self.main_layout.setSpacing(SPACING_SMALL)

        # Create VRAM injection tab
        vram_tab_widget = self._create_vram_tab()
        self.add_tab(vram_tab_widget, "VRAM Injection")

        # Create ROM injection tab
        rom_tab_widget = self._create_rom_tab()
        self.add_tab(rom_tab_widget, "ROM Injection")

        # Setup keyboard shortcuts
        self._setup_keyboard_shortcuts()

        # Load sprite preview and validate if available
        if self.sprite_path and Path(self.sprite_path).exists():
            self._load_sprite_preview()
            self._validate_sprite()

    def _create_splitter_tab(self, add_controls_method: Callable[[QVBoxLayout], None]) -> QWidget:
        """Create a tab with splitter layout for left controls and right preview.

        Args:
            add_controls_method: Method to call to add mode-specific controls to the layout

        Returns:
            The tab container widget
        """
        container = QWidget(self)
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(0, 0, 0, 0)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setHandleWidth(8)
        splitter.setStyleSheet(get_splitter_style(8))

        left_widget = QWidget(self)
        layout = QVBoxLayout(left_widget)
        layout.setContentsMargins(0, 0, 0, 0)

        add_controls_method(layout)

        splitter.addWidget(left_widget)
        splitter.setStretchFactor(0, 30)

        if self.preview_widget:
            splitter.addWidget(self.preview_widget)
            splitter.setStretchFactor(1, 70)

        splitter.setSizes([400, 1000])

        container_layout.addWidget(splitter)
        return container

    def _create_vram_tab(self) -> QWidget:
        """Create VRAM injection tab with splitter layout"""
        return self._create_splitter_tab(self._add_vram_controls)

    def _create_rom_tab(self) -> QWidget:
        """Create ROM injection tab with splitter layout"""
        return self._create_splitter_tab(self._add_rom_controls)

    def _setup_keyboard_shortcuts(self) -> None:
        """Setup keyboard shortcuts for the dialog"""
        # Apply accessibility enhancements
        self._apply_accessibility_enhancements()

        # Ctrl+S to apply/accept
        apply_shortcut = QShortcut(QKeySequence("Ctrl+S"), self)
        apply_shortcut.activated.connect(self.accept)

        # Escape to cancel
        escape_shortcut = QShortcut(QKeySequence("Escape"), self)
        escape_shortcut.activated.connect(self.reject)

        # Tab navigation shortcuts
        next_tab_shortcut = QShortcut(QKeySequence("Ctrl+Tab"), self)
        next_tab_shortcut.activated.connect(self._next_tab)

        prev_tab_shortcut = QShortcut(QKeySequence("Ctrl+Shift+Tab"), self)
        prev_tab_shortcut.activated.connect(self._prev_tab)

        # Update button box if it exists
        if hasattr(self, "button_box") and self.button_box:
            ok_button = self.button_box.button(QDialogButtonBox.StandardButton.Ok)
            if ok_button:
                ok_button.setText("&Apply")
                ok_button.setToolTip("Apply injection settings (Ctrl+S)")
                AccessibilityHelper.make_accessible(
                    ok_button, "Apply Injection", "Apply sprite injection settings and close dialog", "Ctrl+S"
                )

            cancel_button = self.button_box.button(QDialogButtonBox.StandardButton.Cancel)
            if cancel_button:
                cancel_button.setText("&Cancel")
                cancel_button.setToolTip("Cancel without applying changes (Escape)")
                AccessibilityHelper.make_accessible(
                    cancel_button, "Cancel", "Cancel without applying changes", "Escape"
                )

    def _next_tab(self) -> None:
        """Switch to next tab"""
        if self._tab_widget:
            current = self._tab_widget.currentIndex()
            next_index = (current + 1) % self._tab_widget.count()
            if self._tab_widget:
                self._tab_widget.setCurrentIndex(next_index)

    def _prev_tab(self) -> None:
        """Switch to previous tab"""
        if self._tab_widget:
            current = self._tab_widget.currentIndex()
            prev_index = (current - 1) % self._tab_widget.count()
            if self._tab_widget:
                self._tab_widget.setCurrentIndex(prev_index)

    def _apply_accessibility_enhancements(self) -> None:
        """Apply comprehensive accessibility enhancements to the dialog"""
        # Set dialog accessible name and description
        AccessibilityHelper.make_accessible(
            self, "Sprite Injection Dialog", "Configure parameters for injecting sprites into VRAM or ROM files"
        )

        # Add focus indicators
        AccessibilityHelper.add_focus_indicators(self)

        # Make tab widget accessible if it exists
        if hasattr(self, "_main_tab_widget") and self._main_tab_widget:
            self._main_tab_widget.setAccessibleName("Injection Mode Tabs")
            self._main_tab_widget.setAccessibleDescription("Choose between VRAM or ROM injection mode")

        # Make preview widget accessible
        if self.preview_widget:
            AccessibilityHelper.make_accessible(
                self.preview_widget, "Sprite Preview", "Preview of the sprite to be injected"
            )

        # Make sprite file selector accessible
        if self.sprite_file_selector:
            AccessibilityHelper.make_accessible(
                self.sprite_file_selector, "Sprite File Selector", "Select the PNG sprite file to inject", "Alt+S"
            )

    def _add_vram_controls(self, layout: QVBoxLayout) -> None:
        """Add VRAM-specific controls to layout"""
        # Extraction info (if metadata available)
        self.extraction_group = QGroupBox("&Original Extraction Info", self)
        AccessibilityHelper.add_group_box_navigation(self.extraction_group)
        extraction_layout = QVBoxLayout()

        self.extraction_info = QTextEdit()
        if self.extraction_info:
            self.extraction_info.setMaximumHeight(80)
            self.extraction_info.setReadOnly(True)
            self.extraction_info.setToolTip("Information about the original sprite extraction")
        AccessibilityHelper.make_accessible(
            self.extraction_info, "Extraction Information", "Read-only information about the original sprite extraction"
        )
        extraction_layout.addWidget(self.extraction_info)

        if self.extraction_group:
            self.extraction_group.setLayout(extraction_layout)
        layout.addWidget(self.extraction_group)

        # VRAM settings
        vram_group = QGroupBox("&VRAM Settings", self)
        AccessibilityHelper.add_group_box_navigation(vram_group)
        vram_layout = QVBoxLayout()

        # Input VRAM
        self.input_vram_selector = FileSelector(
            label_text="Input VRAM:",
            placeholder="Select VRAM file to modify...",
            browse_text="Browse...",
            mode="open",
            file_filter="VRAM Files (*.dmp *.bin);;All Files (*.*)",
            settings_manager=self.settings_manager,
        )
        self.input_vram_selector.path_changed.connect(self._on_input_vram_changed)
        self.input_vram_selector.setToolTip("Select the VRAM dump file to inject the sprite into")

        vram_layout.addWidget(self.input_vram_selector)

        # Output VRAM
        self.output_vram_selector = FileSelector(
            label_text="Output VRAM:",
            placeholder="Save modified VRAM as...",
            browse_text="Browse...",
            mode="save",
            file_filter="VRAM Files (*.dmp);;All Files (*.*)",
            settings_manager=self.settings_manager,
        )
        self.output_vram_selector.path_changed.connect(self._on_output_vram_changed)
        self.output_vram_selector.setToolTip("Specify where to save the modified VRAM with the injected sprite")

        vram_layout.addWidget(self.output_vram_selector)

        # Offset
        offset_row = FormRow(
            label_text="Injection Offset:",
            input_widget=None,  # Will be set below
            orientation="horizontal",
        )

        self.vram_offset_input = HexOffsetInput(
            placeholder="0xC000", with_decimal_display=True, input_width=100, decimal_width=60
        )
        self.vram_offset_input.text_changed.connect(self._on_vram_offset_changed)
        self.vram_offset_input.setToolTip("Memory offset in VRAM where the sprite will be injected (e.g., 0xC000)")
        offset_row.set_input_widget(self.vram_offset_input)

        vram_layout.addWidget(offset_row)

        vram_group.setLayout(vram_layout)
        layout.addWidget(vram_group)

        # Set initial focus
        self.input_vram_selector.setFocus()

    def _add_rom_controls(self, layout: QVBoxLayout) -> None:
        """Add ROM-specific controls to layout"""
        # ROM settings
        rom_group = QGroupBox("&ROM Settings", self)
        AccessibilityHelper.add_group_box_navigation(rom_group)
        rom_layout = QVBoxLayout()

        # Input ROM
        self.input_rom_selector = FileSelector(
            label_text="&Input ROM:",
            placeholder="Select ROM file to modify...",
            browse_text="Browse...",
            mode="open",
            file_filter="SNES ROM Files (*.sfc *.smc);;All Files (*.*)",
            settings_manager=self.settings_manager,
        )
        self.input_rom_selector.path_changed.connect(self._on_input_rom_changed)
        self.input_rom_selector.setToolTip("Select the ROM file to inject the sprite into")
        AccessibilityHelper.make_accessible(
            self.input_rom_selector, "Input ROM Selector", "Select the ROM file to inject the sprite into"
        )

        rom_layout.addWidget(self.input_rom_selector)

        # Output ROM
        self.output_rom_selector = FileSelector(
            label_text="&Output ROM:",
            placeholder="Save modified ROM as...",
            browse_text="Browse...",
            mode="save",
            file_filter="SNES ROM Files (*.sfc *.smc);;All Files (*.*)",
            settings_manager=self.settings_manager,
        )
        self.output_rom_selector.path_changed.connect(self._on_output_rom_changed)
        self.output_rom_selector.setToolTip("Specify where to save the modified ROM with the injected sprite")
        AccessibilityHelper.make_accessible(
            self.output_rom_selector,
            "Output ROM Selector",
            "Specify where to save the modified ROM with the injected sprite",
        )

        rom_layout.addWidget(self.output_rom_selector)

        # Sprite location selector - using FormRow for consistent alignment
        self.sprite_location_combo = QComboBox(self)
        if self.sprite_location_combo:
            self.sprite_location_combo.setMinimumWidth(200)
        # These will be populated dynamically when ROM is loaded
        if self.sprite_location_combo:
            self.sprite_location_combo.addItem("Select sprite location...", None)
        if self.sprite_location_combo:
            self.sprite_location_combo.currentIndexChanged.connect(self._on_sprite_location_changed)
            self.sprite_location_combo.setToolTip("Select a predefined sprite location in the ROM")
        AccessibilityHelper.make_accessible(
            self.sprite_location_combo,
            "Sprite Location",
            "Select a predefined sprite location in the ROM or enter custom offset",
        )

        self.rom_offset_input = HexOffsetInput(placeholder="0x0", with_decimal_display=False, input_width=100)
        self.rom_offset_input.text_changed.connect(self._on_rom_offset_changed)
        self.rom_offset_input.setToolTip("Enter a custom ROM offset for sprite injection (e.g., 0x8000)")
        AccessibilityHelper.make_accessible(
            self.rom_offset_input, "Custom ROM Offset", "Enter a custom ROM offset for sprite injection"
        )

        # Create container for combo + custom offset controls
        location_container = QWidget()
        container_layout = QHBoxLayout(location_container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(SPACING_SMALL)
        container_layout.addWidget(self.sprite_location_combo)
        custom_label = QLabel("or Custom &Offset:")
        custom_label.setBuddy(self.rom_offset_input)
        container_layout.addWidget(custom_label)
        container_layout.addWidget(self.rom_offset_input)
        container_layout.addStretch()

        location_row = FormRow(
            label_text="Sprite &Location:",
            input_widget=location_container,
            orientation="horizontal",
            label_width=EXTRACTION_LABEL_MIN_WIDTH,
        )
        # Set buddy for accessibility
        location_row.label.setBuddy(self.sprite_location_combo)
        rom_layout.addWidget(location_row)

        # Compression options
        compression_layout = QHBoxLayout()
        self.fast_compression_check = QCheckBox("&Fast compression (larger file size)", self)
        if self.fast_compression_check:
            self.fast_compression_check.setToolTip(
                "Use faster compression algorithm that may result in larger file size"
            )
        AccessibilityHelper.make_accessible(
            self.fast_compression_check,
            "Fast Compression",
            "Use faster compression algorithm that may result in larger file size",
            "Alt+F",
        )
        compression_layout.addWidget(self.fast_compression_check)
        compression_layout.addStretch()
        rom_layout.addLayout(compression_layout)

        rom_group.setLayout(rom_layout)
        layout.addWidget(rom_group)

        # ROM info display
        self.rom_info_group = QGroupBox("ROM Information", self)
        rom_info_layout = QVBoxLayout()

        self.rom_info_text = QTextEdit()
        if self.rom_info_text:
            self.rom_info_text.setMaximumHeight(100)
            self.rom_info_text.setReadOnly(True)
            self.rom_info_text.setToolTip("Information about the selected ROM file")
        rom_info_layout.addWidget(self.rom_info_text)

        if self.rom_info_group:
            self.rom_info_group.setLayout(rom_info_layout)
            self.rom_info_group.hide()  # Hidden until ROM is loaded
        layout.addWidget(self.rom_info_group)

        layout.addStretch()

    def _load_metadata(self) -> None:
        """Load metadata if available"""
        metadata_info: Mapping[str, object] | None = self.injection_manager.load_metadata(self.metadata_path)

        if metadata_info:
            metadata_raw = metadata_info.get("metadata")
            self.metadata = cast(Mapping[str, object], metadata_raw) if isinstance(metadata_raw, dict) else None
            vram_offset_raw = metadata_info.get("extraction_vram_offset")
            self.extraction_vram_offset = vram_offset_raw if isinstance(vram_offset_raw, str) else None
            rom_info_raw = metadata_info.get("rom_extraction_info")
            self.rom_extraction_info = (
                cast(Mapping[str, object], rom_info_raw) if isinstance(rom_info_raw, dict) else None
            )

            # Display extraction info
            if metadata_info.get("extraction"):
                extraction = cast(Mapping[str, object], metadata_info["extraction"])
                source_type = metadata_info["source_type"]

                if source_type == "rom" and self.rom_extraction_info:
                    # ROM extraction metadata
                    info_text = f"Original ROM: {self.rom_extraction_info.get('rom_source', 'Unknown')}\n"
                    info_text += f"Sprite: {self.rom_extraction_info.get('sprite_name', 'Unknown')}\n"
                    info_text += f"ROM Offset: {self.rom_extraction_info.get('rom_offset', 'Unknown')}\n"
                    info_text += f"Tiles: {self.rom_extraction_info.get('tile_count', 'Unknown')}"
                    if self.extraction_info:
                        self.extraction_info.setText(info_text)

                    # Set default VRAM offset
                    if self.vram_offset_input:
                        default_vram_offset = metadata_info.get("default_vram_offset", "0xC000")
                        self.vram_offset_input.set_text(cast(str, default_vram_offset))
                else:
                    # VRAM extraction metadata
                    info_text = f"Original VRAM: {extraction.get('vram_source', 'Unknown')}\n"
                    info_text += f"Offset: {extraction.get('vram_offset', '0xC000')}\n"
                    info_text += f"Tiles: {extraction.get('tile_count', 'Unknown')}"
                    if self.extraction_info:
                        self.extraction_info.setText(info_text)

                    # Set VRAM offset from extraction
                    if self.extraction_vram_offset is not None and self.vram_offset_input:
                        self.vram_offset_input.set_text(self.extraction_vram_offset)
            elif self.extraction_group:
                self.extraction_group.hide()
        else:
            if self.extraction_group:
                self.extraction_group.hide()
            # Set default offset
            if self.vram_offset_input:
                self.vram_offset_input.set_text("0xC000")
            self.extraction_vram_offset = None
            self.rom_extraction_info = None
            self.metadata = None

    def _on_vram_offset_changed(self, text: str) -> None:
        """Handle VRAM offset changes (callback for HexOffsetInput)"""
        logger.debug(f"VRAM offset changed to: '{text}' via HexOffsetInput")
        # HexOffsetInput handles all validation and decimal display internally
        # This method is just for logging and any additional processing if needed

    def _on_rom_offset_changed(self, text: str) -> None:
        """Handle ROM offset changes (callback for HexOffsetInput)"""
        logger.debug(f"ROM offset changed to: '{text}' via HexOffsetInput")
        # Clear combo box selection when manual offset is entered
        if text and self.sprite_location_combo and self.sprite_location_combo.currentIndex() > 0:
            logger.debug("Manual ROM offset entered, clearing sprite location selection")
            self.sprite_location_combo.blockSignals(True)
            try:
                self.sprite_location_combo.setCurrentIndex(0)
            finally:
                self.sprite_location_combo.blockSignals(False)

    def _on_sprite_path_changed(self, path: str) -> None:
        """Handle sprite file path changes"""
        logger.debug(f"Sprite path changed to: '{path}'")
        self.sprite_path = path
        if path and Path(path).exists():
            self._load_sprite_preview()
            self._validate_sprite()

    def _on_input_vram_changed(self, path: str) -> None:
        """Handle input VRAM path changes"""
        logger.debug(f"Input VRAM path changed to: '{path}'")
        if path and self.output_vram_selector and not self.output_vram_selector.get_path():
            # Auto-suggest output filename
            self.output_vram_selector.set_path(self.injection_manager.suggest_output_vram_path(path))

    def _on_output_vram_changed(self, path: str) -> None:
        """Handle output VRAM path changes"""
        logger.debug(f"Output VRAM path changed to: '{path}'")

    def _on_input_rom_changed(self, path: str) -> None:
        """Handle input ROM path changes"""
        logger.debug(f"Input ROM path changed to: '{path}'")
        if path:
            # Load ROM info and populate sprite locations
            self._load_rom_info(path)
            # Auto-suggest output filename
            if self.output_rom_selector and not self.output_rom_selector.get_path():
                self.output_rom_selector.set_path(self.injection_manager.suggest_output_rom_path(path))

    def _on_output_rom_changed(self, path: str) -> None:
        """Handle output ROM path changes"""
        logger.debug(f"Output ROM path changed to: '{path}'")

    def _load_rom_info(self, rom_path: str) -> None:
        """Load ROM information asynchronously to prevent UI freezes.

        Uses ROMInfoLoaderWorker to perform file I/O in a background thread.
        """
        # Clear UI state first in case of errors
        self._clear_rom_ui_state()

        # Show loading state
        if self.sprite_location_combo:
            self.sprite_location_combo.clear()
            self.sprite_location_combo.addItem("Loading ROM info...", None)

        # Clean up any existing worker
        WorkerManager.cleanup_worker_attr(self, "_rom_info_loader")

        # Create and start background worker
        self._rom_info_loader = ROMInfoLoaderWorker(
            rom_path=rom_path,
            injection_manager=self.injection_manager,
            extraction_manager=None,  # Injection dialog only needs injection_manager
            load_header=True,
            load_sprite_locations=False,  # Sprite locations come from injection_manager.load_rom_info
        )

        # Connect signals
        self._rom_info_loader.rom_info_loaded.connect(self._on_rom_info_loaded)
        self._rom_info_loader.error.connect(self._on_rom_info_error)
        self._rom_info_loader.operation_finished.connect(self._on_rom_info_finished)

        # Start loading
        logger.debug(f"Starting async ROM info load for: {rom_path}")
        self._rom_info_loader.start()

    def _on_rom_info_loaded(self, rom_info: Mapping[str, object]) -> None:
        """Handle ROM info loaded from background worker."""
        # Guard: skip if dialog is closing to prevent crash on deleted widget
        if self._is_closing:
            return
        if not rom_info:
            return

        # Check for errors
        if "error" in rom_info:
            error_msg = rom_info["error"]
            error_type = rom_info.get("error_type", "Exception")

            if error_type == "FileNotFoundError":
                logger.error("ROM file not found")
                _ = QMessageBox.critical(
                    self, "ROM File Not Found", f"The selected ROM file could not be found:\n\n{error_msg}"
                )
            elif error_type == "PermissionError":
                logger.error("ROM file permission error")
                _ = QMessageBox.critical(self, "ROM File Access Error", f"Cannot access the ROM file:\n\n{error_msg}")
            elif error_type == "ValueError":
                logger.error("Invalid ROM file")
                _ = QMessageBox.warning(
                    self, "Invalid ROM File", f"The selected file is not a valid SNES ROM:\n\n{error_msg}"
                )
            else:
                logger.error("Failed to load ROM info")
                _ = QMessageBox.warning(self, "ROM Load Error", f"Failed to load ROM information:\n\n{error_msg}")
            return

        # Display ROM info
        header = cast(Mapping[str, object], rom_info["header"])
        info_text = f"Title: {header['title']}\n"
        info_text += f"ROM Type: 0x{header['rom_type']:02X}\n"
        info_text += f"Checksum: 0x{header['checksum']:04X}"
        if self.rom_info_text:
            self.rom_info_text.setText(info_text)
        if self.rom_info_group:
            self.rom_info_group.show()

        # Populate sprite locations
        sprite_locations = cast(Mapping[str, int], rom_info.get("sprite_locations", {}))
        if sprite_locations:
            if self.sprite_location_combo:
                # Clear any existing items first to prevent duplicates
                self.sprite_location_combo.clear()
                self.sprite_location_combo.addItem("Select sprite location...", None)

            for display_name, offset in sprite_locations.items():
                if self.sprite_location_combo:
                    self.sprite_location_combo.addItem(f"{display_name} (0x{offset:06X})", offset)

            # Check for sprite location loading error
            if "sprite_locations_error" in rom_info:
                logger.warning(f"Failed to load some sprite locations: {rom_info['sprite_locations_error']}")

            # Apply pending offset that was stored before async load started
            # This fixes the race condition where offset matching was attempted
            # before the combo was populated
            self._apply_pending_offset()

            # Now restore the saved sprite location if we were loading defaults
            try:
                self._restore_saved_sprite_location()
            except Exception as restore_error:
                logger.warning(f"Failed to restore sprite location: {restore_error}")
        # Not a Kirby ROM or no sprite locations
        elif "KIRBY" not in cast(str, header["title"]).upper():
            if self.sprite_location_combo:
                self.sprite_location_combo.addItem(f"No sprite data available for: {header['title']}", None)
        elif self.sprite_location_combo:
            self.sprite_location_combo.addItem("Error loading sprite locations", None)

    def _on_rom_info_error(self, message: str, exception: Exception) -> None:
        """Handle ROM info loading error from worker."""
        # Guard: skip if dialog is closing to prevent crash on deleted widget
        if self._is_closing:
            return
        logger.error(f"ROM info loading failed: {message}")
        if self.sprite_location_combo:
            self.sprite_location_combo.clear()
            self.sprite_location_combo.addItem("Error loading ROM", None)

    def _on_rom_info_finished(self, success: bool, message: str) -> None:
        """Handle ROM info worker completion."""
        # Guard: skip if dialog is closing to prevent crash on deleted widget
        if self._is_closing:
            return
        logger.debug(f"ROM info loading finished: success={success}, message={message}")

    def _clear_rom_ui_state(self) -> None:
        """Clear ROM-related UI state"""
        if self.sprite_location_combo:
            self.sprite_location_combo.clear()
        if self.sprite_location_combo:
            self.sprite_location_combo.addItem("Load ROM file first...", None)
        if self.rom_info_text:
            self.rom_info_text.clear()
        if self.rom_info_group:
            self.rom_info_group.hide()

    def _on_sprite_location_changed(self, index: int) -> None:
        """Update offset field when sprite location is selected"""
        if index > 0 and self.sprite_location_combo:  # Skip "Select sprite location..."
            offset = self.sprite_location_combo.currentData()
            if offset is not None and self.rom_offset_input:
                # Block signals to prevent recursion with _on_rom_offset_changed
                if self.rom_offset_input.hex_edit:
                    self.rom_offset_input.hex_edit.blockSignals(True)
                try:
                    self.rom_offset_input.set_text(f"0x{offset:X}")
                finally:
                    if self.rom_offset_input.hex_edit:
                        self.rom_offset_input.hex_edit.blockSignals(False)

    def _validate_common_inputs(self) -> str | None:
        """Validate common input requirements.

        Returns:
            Error message if validation fails, None if valid
        """
        if not self.sprite_file_selector or not self.sprite_file_selector.get_path():
            return "Please select a sprite file"
        return None

    def _validate_vram_inputs(self) -> tuple[str | None, dict[str, object] | None]:
        """Validate VRAM injection inputs and build parameters.

        Returns:
            Tuple of (error_message, parameters_dict)
            If error_message is not None, validation failed
        """
        # Check input VRAM file
        if not self.input_vram_selector or not self.input_vram_selector.get_path():
            return "Please select an input VRAM file", None

        # Check output VRAM file
        if not self.output_vram_selector or not self.output_vram_selector.get_path():
            return "Please specify an output VRAM file", None

        # Parse and validate offset
        offset_text = self.vram_offset_input.get_text() if self.vram_offset_input else "0xC000"
        offset = self.vram_offset_input.get_value() if self.vram_offset_input else None
        if offset is None:
            error_msg = (
                f"Invalid VRAM offset value: '{offset_text}'"
                + "\n"
                + "Please enter a valid hexadecimal value (e.g., 0xC000, C000)"
            )
            return error_msg, None

        # Build parameters dictionary
        params: dict[str, object] = {
            "mode": "vram",
            "sprite_path": self.sprite_file_selector.get_path() if self.sprite_file_selector else "",
            "input_vram": self.input_vram_selector.get_path() if self.input_vram_selector else "",
            "output_vram": self.output_vram_selector.get_path() if self.output_vram_selector else "",
            "offset": offset,
            "metadata_path": self.metadata_path if self.metadata else None,
        }

        return None, params

    def _validate_rom_inputs(self) -> tuple[str | None, dict[str, object] | None]:
        """Validate ROM injection inputs and build parameters.

        Returns:
            Tuple of (error_message, parameters_dict)
            If error_message is not None, validation failed
        """
        # Check input ROM file
        if not self.input_rom_selector or not self.input_rom_selector.get_path():
            return "Please select an input ROM file", None

        # Check output ROM file
        if not self.output_rom_selector or not self.output_rom_selector.get_path():
            return "Please specify an output ROM file", None

        # Get offset from combo box or manual entry
        offset = None
        if self.sprite_location_combo and self.sprite_location_combo.currentIndex() > 0:
            offset = self.sprite_location_combo.currentData()
        elif self.rom_offset_input and self.rom_offset_input.get_text():
            offset_text = self.rom_offset_input.get_text()
            offset = self.rom_offset_input.get_value()
            if offset is None:
                error_msg = (
                    f"Invalid ROM offset value: '{offset_text}'"
                    + "\n"
                    + "Please enter a valid hexadecimal value (e.g., 0x8000, 8000)"
                )
                return error_msg, None

        # Ensure an offset was provided
        if offset is None:
            return "Please select a sprite location or enter a custom offset", None

        # Build parameters dictionary
        params: dict[str, object] = {
            "mode": "rom",
            "sprite_path": self.sprite_file_selector.get_path() if self.sprite_file_selector else "",
            "input_rom": self.input_rom_selector.get_path() if self.input_rom_selector else "",
            "output_rom": self.output_rom_selector.get_path() if self.output_rom_selector else "",
            "offset": offset,
            "fast_compression": self.fast_compression_check.isChecked() if self.fast_compression_check else False,
            "metadata_path": self.metadata_path if self.metadata else None,
        }

        return None, params

    def get_parameters(self) -> dict[str, object] | None:
        """Get injection parameters if dialog accepted.

        Validates all inputs and returns parameters dictionary for injection,
        or None if validation fails or dialog was not accepted.

        Returns:
            Parameters dictionary if valid, None otherwise
        """
        # Early return if dialog not accepted
        if self.result() != QDialog.DialogCode.Accepted:
            return None

        # Validate common inputs (sprite file)
        common_error = self._validate_common_inputs()
        if common_error:
            _ = QMessageBox.warning(self, "Invalid Input", common_error)
            return None

        # Validate tab-specific inputs
        current_tab = self.get_current_tab_index()
        if current_tab == 0:  # VRAM injection
            error, params = self._validate_vram_inputs()
        else:  # ROM injection
            error, params = self._validate_rom_inputs()

        if error:
            _ = QMessageBox.warning(self, "Invalid Input", error)
            return None

        return params

    def _set_initial_paths(self) -> None:
        """Set initial paths based on suggestions"""
        # Set input VRAM if we have a suggestion
        if self.suggested_input_vram and self.input_vram_selector:
            self.input_vram_selector.set_path(self.suggested_input_vram)
        else:
            # Try to find and auto-fill input VRAM
            suggested_input = self.injection_manager.find_suggested_input_vram(
                self.sprite_path, self.metadata if hasattr(self, "metadata") else None, self.suggested_input_vram
            )
            if suggested_input and self.input_vram_selector:
                self.input_vram_selector.set_path(suggested_input)

        # Set ROM injection parameters from saved settings or metadata
        self._set_rom_injection_defaults()

        # Set output VRAM suggestion
        if self.input_vram_selector and self.output_vram_selector and self.input_vram_selector.get_path():
            self.output_vram_selector.set_path(
                self.injection_manager.suggest_output_vram_path(self.input_vram_selector.get_path())
            )

    def _set_rom_injection_defaults(self) -> None:
        """Set ROM injection parameters from saved settings or metadata"""
        metadata_dict: dict[str, object] | None = None
        if hasattr(self, "metadata"):
            metadata_dict = {
                "metadata": self.metadata,
                "rom_extraction_info": self.rom_extraction_info,
                "extraction_vram_offset": self.extraction_vram_offset,
            }

        defaults: Mapping[str, object] = self.injection_manager.load_rom_injection_defaults(
            self.sprite_path, metadata_dict
        )

        # Set input ROM
        input_rom = cast(str, defaults["input_rom"]) if defaults["input_rom"] else ""
        if input_rom and self.input_rom_selector:
            self.input_rom_selector.set_path(input_rom)
            output_rom = cast(str, defaults["output_rom"]) if defaults["output_rom"] else ""
            if output_rom and self.output_rom_selector:
                self.output_rom_selector.set_path(output_rom)

            # Store pending offset to restore after async ROM info load completes
            # This fixes a race condition where we tried to match offsets in the
            # combo box before it was populated by the background worker
            rom_offset = defaults["rom_offset"]
            if rom_offset is not None:
                self._pending_rom_offset = cast(int, rom_offset)
                custom_offset = defaults["custom_offset"]
                self._pending_custom_offset = cast(str, custom_offset) if custom_offset else None
            elif defaults["custom_offset"]:
                self._pending_custom_offset = cast(str, defaults["custom_offset"])

            # Load ROM info to populate sprite locations (async)
            # The pending offset will be applied in _on_rom_info_loaded()
            self._load_rom_info(input_rom)
        else:
            # No ROM to load, but still restore other settings
            self._restore_saved_sprite_location()

        # Set custom offset if we don't have a ROM offset match
        custom_offset = defaults["custom_offset"]
        if custom_offset and defaults["rom_offset"] is None and self.rom_offset_input:
            self.rom_offset_input.set_text(cast(str, custom_offset))

        # Set fast compression
        if self.fast_compression_check:
            self.fast_compression_check.setChecked(cast(bool, defaults["fast_compression"]))

    def _apply_pending_offset(self) -> None:
        """Apply pending offset that was stored before async ROM info load.

        This method is called after the combo box is populated to apply
        any offset that was pending from _set_rom_injection_defaults().
        """
        if self._pending_rom_offset is None and self._pending_custom_offset is None:
            return  # Nothing pending

        try:
            # Try to find matching sprite location in combo box
            if self._pending_rom_offset is not None and self.sprite_location_combo:
                for i in range(self.sprite_location_combo.count()):
                    offset_data = self.sprite_location_combo.itemData(i)
                    if offset_data == self._pending_rom_offset:
                        self.sprite_location_combo.setCurrentIndex(i)
                        logger.debug(f"Applied pending ROM offset: 0x{self._pending_rom_offset:X}")
                        return  # Found match, done

            # If no exact match in combo, set custom offset
            if self._pending_custom_offset and self.rom_offset_input:
                self.rom_offset_input.set_text(self._pending_custom_offset)
                logger.debug(f"Applied pending custom offset: {self._pending_custom_offset}")
        finally:
            # Always clear pending values to prevent re-application
            self._pending_rom_offset = None
            self._pending_custom_offset = None

    def _restore_saved_sprite_location(self) -> None:
        """Restore saved sprite location in combo box"""
        # Build sprite locations dict from combo box
        sprite_locations = {}
        if self.sprite_location_combo:
            for i in range(1, self.sprite_location_combo.count()):  # Skip index 0 ("Select sprite location...")
                text = self.sprite_location_combo.itemText(i)
                offset = self.sprite_location_combo.itemData(i)
                if offset is not None:
                    # Extract display name (before the offset in parentheses)
                    display_name = text.split(" (0x")[0] if " (0x" in text else text
                    sprite_locations[display_name] = offset

        restore_info: Mapping[str, object] = self.injection_manager.restore_saved_sprite_location(
            self.extraction_vram_offset, sprite_locations
        )

        sprite_location_index = restore_info["sprite_location_index"]
        if sprite_location_index is not None:
            if self.sprite_location_combo:
                idx = cast(int, sprite_location_index)
                # Bounds check before setting index
                if 0 <= idx < self.sprite_location_combo.count():
                    self.sprite_location_combo.setCurrentIndex(idx)
                else:
                    logger.warning(
                        f"Saved sprite location index {idx} out of bounds (count: {self.sprite_location_combo.count()})"
                    )
        else:
            custom_offset = restore_info["custom_offset"]
            if custom_offset and self.rom_offset_input:
                self.rom_offset_input.set_text(cast(str, custom_offset))

    def save_rom_injection_parameters(self) -> None:
        """Save ROM injection parameters to settings for future use"""
        self.injection_manager.save_rom_injection_settings(
            input_rom=self.input_rom_selector.get_path() if self.input_rom_selector else "",
            sprite_location_text=self.sprite_location_combo.currentText() if self.sprite_location_combo else "",
            custom_offset=self.rom_offset_input.get_text() if self.rom_offset_input else "",
            fast_compression=self.fast_compression_check.isChecked() if self.fast_compression_check else False,
        )

    def _load_sprite_preview(self) -> None:
        """Load and display sprite preview"""
        if not self.sprite_path or not Path(self.sprite_path).exists():
            if self.preview_widget:
                self.preview_widget.clear()
            return

        try:
            # Try to detect sprite name from metadata or filename
            sprite_name: str | None = None
            if self.metadata and "extraction" in self.metadata:
                extraction_data = cast(Mapping[str, object], self.metadata["extraction"])
                sprite_name_raw = extraction_data.get("sprite_name", "")
                sprite_name = cast(str, sprite_name_raw) if sprite_name_raw else None

            if not sprite_name:
                # Extract from filename (e.g., "kirby_normal_sprites.png" -> "kirby_normal")
                base_name = Path(self.sprite_path).stem
                for suffix in ["_sprites_editor", "_sprites", "_editor"]:
                    if base_name.endswith(suffix):
                        sprite_name = base_name[: -len(suffix)]
                        break
                else:
                    sprite_name = base_name

            # Load the sprite preview
            if self.preview_widget:
                self.preview_widget.load_sprite_from_png(self.sprite_path, sprite_name)

        except Exception as e:
            logger.exception("Failed to load sprite preview")
            if self.preview_widget:
                self.preview_widget.clear()
                if self.preview_widget.info_label:
                    self.preview_widget.info_label.setText(f"Error loading preview: {e}")

    def _validate_sprite(self) -> None:
        """Validate sprite and show warnings/errors"""
        if not self.sprite_path or not Path(self.sprite_path).exists():
            return

        # Perform validation
        _is_valid, errors, warnings = SpriteValidator.validate_sprite_comprehensive(
            self.sprite_path, self.metadata_path
        )

        # Create validation message
        if errors or warnings:
            msg_parts = []

            if errors:
                msg_parts.append("ERRORS:")
                for error in errors:
                    msg_parts.append(f"  • {error}")

            if warnings:
                if errors:
                    msg_parts.append("")  # Empty line
                msg_parts.append("WARNINGS:")
                for warning in warnings:
                    msg_parts.append(f"  • {warning}")

            # Show validation results in a message box
            if errors:
                _ = QMessageBox.critical(self, "Sprite Validation Failed", "\n".join(msg_parts))
            else:
                # Just warnings - show as information
                _ = QMessageBox.information(self, "Sprite Validation Warnings", "\n".join(msg_parts))

        # Also estimate compressed size
        uncompressed, estimated_compressed = SpriteValidator.estimate_compressed_size(self.sprite_path)
        if uncompressed > 0:
            size_info = f"Estimated size: {uncompressed} bytes uncompressed, ~{estimated_compressed} bytes compressed"

            # Update preview widget info
            if self.preview_widget and self.preview_widget.info_label:
                current_info = self.preview_widget.info_label.text()
                if "Size:" in current_info:
                    # Append to existing info
                    self.preview_widget.info_label.setText(f"{current_info} | {size_info}")
                else:
                    self.preview_widget.info_label.setText(size_info)

    @override
    def closeEvent(self, event: QCloseEvent | None) -> None:
        """Handle dialog close with worker cleanup."""
        # Set closing flag FIRST to guard against queued signal callbacks
        self._is_closing = True

        if self._rom_info_loader is not None:
            # Block signals FIRST to prevent race with queued signals
            self._rom_info_loader.blockSignals(True)

            # Then disconnect signals to break references
            try:
                self._rom_info_loader.rom_info_loaded.disconnect(self._on_rom_info_loaded)
                self._rom_info_loader.error.disconnect(self._on_rom_info_error)
                self._rom_info_loader.operation_finished.disconnect(self._on_rom_info_finished)
            except (RuntimeError, TypeError):
                pass  # Already disconnected or object deleted

            if self._rom_info_loader.isRunning():
                logger.debug("Stopping ROM info loader on dialog close")
            WorkerManager.cleanup_worker_attr(self, "_rom_info_loader", timeout=3000)

        if event:
            super().closeEvent(event)
