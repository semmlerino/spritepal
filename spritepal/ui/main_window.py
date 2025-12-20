"""
Main window for SpritePal application
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from core.controller import ExtractionController
    from core.protocols.manager_protocols import (
        ApplicationStateManagerProtocol,
        ROMCacheProtocol,
        SettingsManagerProtocol,
    )

from typing import override

from PySide6.QtCore import Qt, Signal

if TYPE_CHECKING:
    from PySide6.QtGui import QCloseEvent, QKeyEvent
else:
    from PySide6.QtGui import QCloseEvent, QKeyEvent
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QMainWindow,
    QMessageBox,
    QScrollArea,
    QSplitter,
    QStatusBar,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

# Session manager accessed via DI: inject(ApplicationStateManagerProtocol)
# Dialog imports moved to lazy imports in methods that use them (see show_settings, extraction_failed)
from core.types import VRAMExtractionParams
from ui.common.spacing_constants import (
    SPACING_COMPACT_SMALL,
    SPACING_SMALL,
)
from ui.extraction_panel import ExtractionPanel
from ui.managers import (
    KeyboardShortcutHandler,
    MenuBarManager,
    OutputSettingsManager,
    PreviewCoordinator,
    SessionCoordinator,
    StatusBarManager,
    TabCoordinator,
    ToolbarManager,
)
from ui.palette_preview import PalettePreviewWidget
from ui.rom_extraction_panel import ROMExtractionPanel
from ui.styles.components import get_action_zone_style
from ui.zoomable_preview import PreviewPanel

# Layout constants for consistent sizing and spacing
MAIN_WINDOW_MIN_SIZE = (1000, 650)  # Much more compact
DEFAULT_SPLITTER_RATIO = 0.45  # Give left panel a bit more space
MIN_PANEL_WIDTH = 380  # Slightly smaller minimum
LAYOUT_MARGINS = SPACING_SMALL  # 8px - standard margins
LAYOUT_SPACING = SPACING_COMPACT_SMALL  # 6px - compact spacing


class MainWindow(QMainWindow):
    """Main application window for SpritePal"""

    # Signals
    extract_requested = Signal()
    open_in_editor_requested = Signal(str)  # sprite file path
    arrange_rows_requested = Signal(str)  # sprite file path for arrangement
    arrange_grid_requested = Signal(str)  # sprite file path for grid arrangement
    inject_requested = Signal()  # inject sprite to VRAM

    # Completion signals for controller communication
    extraction_completed = Signal(list)  # list of extracted files
    extraction_error_occurred = Signal(str)     # error message

    def __init__(
        self,
        settings_manager: SettingsManagerProtocol,
        rom_cache: ROMCacheProtocol,
        session_manager: ApplicationStateManagerProtocol,
    ) -> None:
        super().__init__()
        # Declare instance variables with type hints
        self._output_path: str
        self._extracted_files: list[str]
        self._controller: ExtractionController | None
        self.left_panel: QWidget
        self.extraction_tabs: QTabWidget
        self.rom_extraction_panel: ROMExtractionPanel
        self.extraction_panel: ExtractionPanel
        self.sprite_preview: PreviewPanel
        self.palette_preview: PalettePreviewWidget

        # Store injected dependencies
        self.settings_manager = settings_manager
        self.rom_cache = rom_cache
        self.session_manager = session_manager

        # Manager instances
        self.menu_bar_manager: MenuBarManager
        self.toolbar_manager: ToolbarManager
        self.status_bar_manager: StatusBarManager
        self.output_settings_manager: OutputSettingsManager
        self.tab_coordinator: TabCoordinator
        self.preview_coordinator: PreviewCoordinator
        self.keyboard_handler: KeyboardShortcutHandler
        self.session_coordinator: SessionCoordinator

        self._output_path = ""
        self._extracted_files = []
        self._controller = None  # Lazy initialization to break circular dependency

        self._setup_ui()
        self._setup_managers()  # This creates all UI widgets via managers
        self._connect_signals()

        # Controller will be created on first access via property
        # This breaks the circular dependency: tests can create MainWindow without hanging

        # Restore session after UI is set up
        self.session_coordinator.restore_session()

        # Update initial UI state (after managers are fully set up)
        self._update_initial_ui_state()

    def _setup_ui(self) -> None:
        """Initialize the user interface"""
        self.setWindowTitle("SpritePal - Sprite Extraction Tool")
        self.setMinimumSize(*MAIN_WINDOW_MIN_SIZE)

        # Create central widget
        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)

        # Main horizontal splitter
        main_splitter = QSplitter(Qt.Orientation.Horizontal)
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(LAYOUT_MARGINS, LAYOUT_MARGINS, LAYOUT_MARGINS, LAYOUT_MARGINS)
        main_layout.setSpacing(0)  # Splitter handles spacing
        main_layout.addWidget(main_splitter)

        # Left panel - Input and controls
        self.left_panel = self._create_left_panel()

        # Right panel - Previews (will be created by PreviewCoordinator)
        self.sprite_preview = PreviewPanel()
        self.palette_preview = PalettePreviewWidget()

        # Add panels to main splitter (right panel created by manager)
        main_splitter.addWidget(self.left_panel)
        # Right panel will be added by PreviewCoordinator

        # Configure main splitter with proper stretch factors
        # Calculate initial sizes based on DEFAULT_SPLITTER_RATIO
        total_width = MAIN_WINDOW_MIN_SIZE[0] - (2 * LAYOUT_MARGINS)
        left_width = int(total_width * DEFAULT_SPLITTER_RATIO)
        right_width = total_width - left_width
        main_splitter.setSizes([left_width, right_width])
        main_splitter.setStretchFactor(0, 1)  # Left panel stretches proportionally
        main_splitter.setStretchFactor(1, 2)  # Right panel stretches more

        # Set minimum sizes for panels
        self.left_panel.setMinimumWidth(MIN_PANEL_WIDTH)

        # Status bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Ready to extract sprites")

    def _create_left_panel(self) -> QWidget:
        """Create the left panel with scrollable tabs and pinned action zone.
        
        Structure:
        - Content Zone (top, scrollable): Contains extraction tabs
        - Action Zone (bottom, fixed): Contains output settings + action buttons
        
        This ensures action buttons are always visible regardless of tab content height.
        """
        left_panel = QWidget(self)
        main_layout = QVBoxLayout(left_panel)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # CONTENT ZONE: Scrollable area for extraction tabs
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        
        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(LAYOUT_MARGINS, LAYOUT_MARGINS, LAYOUT_MARGINS, 0)
        content_layout.setSpacing(LAYOUT_SPACING)

        # Create tab widget for extraction methods
        self.extraction_tabs = QTabWidget(self)
        from PySide6.QtWidgets import QSizePolicy
        self.extraction_tabs.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)

        # ROM extraction tab (first tab, selected by default)
        from core.di_container import inject
        from core.protocols.manager_protocols import ExtractionManagerProtocol
        extraction_manager = inject(ExtractionManagerProtocol)
        self.rom_extraction_panel = ROMExtractionPanel(
            parent=self,
            extraction_manager=extraction_manager
        )
        self.extraction_tabs.addTab(self.rom_extraction_panel, "ROM Extraction")

        # VRAM extraction tab
        self.extraction_panel = ExtractionPanel(settings_manager=self.settings_manager)
        self.extraction_tabs.addTab(self.extraction_panel, "VRAM Extraction")

        # Add tab navigation shortcuts
        self.extraction_tabs.setToolTip("Switch tabs with Ctrl+Tab/Ctrl+Shift+Tab")

        content_layout.addWidget(self.extraction_tabs)
        content_layout.addStretch()  # Push tabs to top when content is small
        
        scroll_area.setWidget(content_widget)
        main_layout.addWidget(scroll_area, stretch=1)  # Takes all available vertical space

        # ACTION ZONE: Fixed height, pinned to bottom
        self.action_zone = QWidget()
        self.action_zone.setObjectName("actionZone")
        self.action_zone.setStyleSheet(get_action_zone_style())
        action_zone_layout = QVBoxLayout(self.action_zone)
        action_zone_layout.setContentsMargins(LAYOUT_MARGINS, 0, LAYOUT_MARGINS, LAYOUT_MARGINS)
        action_zone_layout.setSpacing(LAYOUT_SPACING)

        # Visual separator line
        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.HLine)
        separator.setFrameShadow(QFrame.Shadow.Sunken)
        action_zone_layout.addWidget(separator)

        # Output settings and buttons will be added by managers in _setup_managers()
        
        main_layout.addWidget(self.action_zone)  # No stretch = fixed size based on content

        return left_panel

    def _setup_managers(self) -> None:
        """Set up all UI managers"""
        # Create managers in dependency order
        self.menu_bar_manager = MenuBarManager(self, self)
        self.status_bar_manager = StatusBarManager(self.status_bar, settings_manager=self.settings_manager, rom_cache=self.rom_cache)
        self.output_settings_manager = OutputSettingsManager(self, self)

        # Connect ROM panel to shared output name (removes redundant output field from ROM panel)
        self.rom_extraction_panel.set_output_name_provider(
            self.output_settings_manager.get_output_name
        )

        self.toolbar_manager = ToolbarManager(self, self)
        self.preview_coordinator = PreviewCoordinator(self.sprite_preview, self.palette_preview)

        # Backward compatibility: expose preview_info for existing code/tests
        self.preview_info = self.preview_coordinator.preview_info

        self.session_coordinator = SessionCoordinator(
            self, self.extraction_panel, self.output_settings_manager,
            settings_manager=self.settings_manager,
            session_manager=self.session_manager
        )

        # Tab coordinator needs several managers
        self.tab_coordinator = TabCoordinator(
            self.extraction_tabs,
            self.rom_extraction_panel,
            self.extraction_panel,
            self.output_settings_manager,
            self.toolbar_manager,
            self
        )

        # Keyboard handler needs several managers
        self.keyboard_handler = KeyboardShortcutHandler(
            self.tab_coordinator,
            self.output_settings_manager,
            self.toolbar_manager,
            self
        )

        # Initialize manager UIs
        self.menu_bar_manager.create_menus()
        self.status_bar_manager.setup_status_bar_indicators()

        # Add output settings and buttons to the pinned action zone
        action_zone_layout = self.action_zone.layout()
        if action_zone_layout is not None and isinstance(action_zone_layout, QVBoxLayout):
            # Add output settings group to action zone
            output_group = self.output_settings_manager.create_output_settings_group()
            action_zone_layout.addWidget(output_group)

            # Add toolbar buttons
            button_layout = QGridLayout()
            button_layout.setContentsMargins(0, LAYOUT_SPACING, 0, 0)
            button_layout.setSpacing(LAYOUT_SPACING)
            self.toolbar_manager.create_action_buttons(button_layout)
            action_zone_layout.addLayout(button_layout)

        # Add preview panel to main splitter
        main_splitter = self.centralWidget().findChild(QSplitter)
        if main_splitter:
            right_panel = self.preview_coordinator.create_preview_panel(self)
            main_splitter.addWidget(right_panel)
            right_panel.setMinimumWidth(MIN_PANEL_WIDTH)
            # Ensure right panel has proper size policy
            from PySide6.QtWidgets import QSizePolicy
            right_panel.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def _update_initial_ui_state(self) -> None:
        """Update initial UI state after setup"""
        # Update output info label
        self.output_settings_manager.update_output_info_label(
            is_vram_tab=False,  # ROM tab is default
            is_grayscale_mode=False
        )

        # Update extraction mode
        self._on_extraction_mode_changed(self.extraction_panel.mode_combo.currentIndex())

    def _setup_status_bar_indicators(self) -> None:
        """Set up permanent status bar indicators"""
        # Delegate to status bar manager
        self.status_bar_manager.setup_status_bar_indicators()

    # Protocol method implementations for managers

    # MenuBarActionsProtocol
    def new_extraction(self) -> None:
        """Start a new extraction"""
        # Reset UI
        self.extraction_panel.clear_files()
        self.output_settings_manager.clear_output_name()
        self.preview_coordinator.clear_previews()
        self.toolbar_manager.reset_buttons()
        self._output_path = ""
        self._extracted_files = []
        self.status_bar_manager.show_message("Ready to extract sprites")

        # Clear session data
        self.session_coordinator.clear_session()

    def show_settings(self) -> None:
        """Show the settings dialog"""
        from ui.dialogs import SettingsDialog  # Lazy import to avoid cross-UI coupling

        dialog = SettingsDialog(self, settings_manager=self.settings_manager, rom_cache=self.rom_cache)
        dialog.settings_changed.connect(self._on_settings_changed)
        dialog.cache_cleared.connect(self._on_cache_cleared)
        dialog.exec()

    def show_cache_manager(self) -> None:
        """Show the cache manager dialog"""
        from ui.dialogs import SettingsDialog  # Lazy import to avoid cross-UI coupling

        dialog = SettingsDialog(self, settings_manager=self.settings_manager, rom_cache=self.rom_cache)
        if dialog.tab_widget:
            dialog.tab_widget.setCurrentIndex(1)  # Switch to cache tab
        dialog.settings_changed.connect(self._on_settings_changed)
        dialog.cache_cleared.connect(self._on_cache_cleared)
        dialog.exec()

    def clear_all_caches(self) -> None:
        """Clear all ROM caches with confirmation"""
        rom_cache = self.rom_cache
        try:
            removed_count = rom_cache.clear_cache()

            self.status_bar_manager.show_message(f"Cleared {removed_count} cache files")

            QMessageBox.information(
                self,
                "Cache Cleared",
                f"Successfully removed {removed_count} cache files."
            )
        except (OSError, PermissionError) as e:
            QMessageBox.critical(
                self,
                "File Error",
                f"Cannot access cache files: {e}"
            )
        except Exception as e:
            QMessageBox.critical(
                self,
                "Error",
                f"Failed to clear cache: {e!s}"
            )

    # ToolbarActionsProtocol
    def on_extract_clicked(self) -> None:
        """Handle extract button click"""
        # Check which tab is active
        if self.tab_coordinator.is_rom_tab_active():
            self._handle_rom_extraction()
        else:
            self._handle_vram_extraction()

    def on_open_editor_clicked(self) -> None:
        """Handle open in editor button click"""
        if self._output_path:
            sprite_file = f"{self._output_path}.png"
            self.open_in_editor_requested.emit(sprite_file)

    def on_arrange_rows_clicked(self) -> None:
        """Handle arrange rows button click"""
        if self._output_path:
            sprite_file = f"{self._output_path}.png"
            self.arrange_rows_requested.emit(sprite_file)

    def on_arrange_grid_clicked(self) -> None:
        """Handle arrange grid button click"""
        if self._output_path:
            sprite_file = f"{self._output_path}.png"
            self.arrange_grid_requested.emit(sprite_file)

    def on_inject_clicked(self) -> None:
        """Handle inject to VRAM button click"""
        if self._output_path:
            self.inject_requested.emit()

    # OutputSettingsActionsProtocol
    def get_current_vram_path(self) -> str:
        """Get current VRAM path for browse dialog default directory"""
        current_files = self.extraction_panel.get_session_data()
        vram_path = current_files.get("vram_path", "")
        return str(vram_path) if vram_path else ""

    # TabCoordinatorActionsProtocol
    def get_rom_extraction_params(self) -> dict[str, Any] | None:
        """Get ROM extraction parameters"""
        return self.rom_extraction_panel.get_extraction_params()

    def is_vram_extraction_ready(self) -> bool:
        """Check if VRAM extraction is ready"""
        if self.extraction_panel.is_grayscale_mode():
            return self.extraction_panel.has_vram()
        return (self.extraction_panel.has_vram() and
               self.extraction_panel.has_cgram())

    def is_grayscale_mode(self) -> bool:
        """Check if in grayscale mode"""
        return self.extraction_panel.is_grayscale_mode()

    def get_extraction_mode_index(self) -> int:
        """Get current extraction mode index"""
        return self.extraction_panel.mode_combo.currentIndex()

    # KeyboardActionsProtocol
    def can_open_manual_offset_dialog(self) -> bool:
        """Check if manual offset dialog can be opened"""
        return (self.tab_coordinator.is_rom_tab_active() and
                hasattr(self.rom_extraction_panel, "_manual_offset_mode") and
                self.rom_extraction_panel._manual_offset_mode)

    def open_manual_offset_dialog(self) -> None:
        """Open manual offset dialog"""
        self.rom_extraction_panel._open_manual_offset_dialog()

    def _handle_rom_extraction(self) -> None:
        """Handle ROM extraction"""
        params = self.rom_extraction_panel.get_extraction_params()
        if params:
            # Use the shared output name
            params["output_base"] = self.output_settings_manager.get_output_name()

            # Validate parameters using extraction manager
            # Delayed import to avoid initialization order issues
            from core.di_container import inject
            from core.protocols.manager_protocols import ExtractionManagerProtocol
            try:
                extraction_manager = inject(ExtractionManagerProtocol)
                extraction_manager.validate_extraction_params(params)
            except (ValueError, TypeError) as e:
                QMessageBox.warning(
                    self,
                    "Validation Error",
                    f"Invalid extraction parameters: {e}"
                )
                return
            except Exception as e:
                QMessageBox.warning(
                    self,
                    "Validation Error",
                    str(e)
                )
                return

            self._output_path = params["output_base"]
            self.status_bar_manager.show_message("Extracting sprites from ROM...")
            self.toolbar_manager.set_extract_enabled(False)
            self.controller.start_rom_extraction(params)

    def _handle_vram_extraction(self) -> None:
        """Handle VRAM extraction"""
        # VRAM extraction - validation will be handled by controller
        self._output_path = self.output_settings_manager.get_output_name()
        self.status_bar_manager.show_message("Extracting sprites from VRAM...")
        self.toolbar_manager.set_extract_enabled(False)

        # Emit signal for controller to handle extraction
        self.extract_requested.emit()

    def show_cache_operation_badge(self, operation: str) -> None:
        """Show cache operation badge in status bar

        Args:
            operation: Operation description (e.g., "Loading", "Saving", "Reading")
        """
        self.status_bar_manager.show_cache_operation_badge(operation)

    def hide_cache_operation_badge(self) -> None:
        """Hide cache operation badge"""
        self.status_bar_manager.hide_cache_operation_badge()

    # Menu creation now handled by MenuBarManager in _setup_managers()

    def _connect_signals(self) -> None:
        """Connect internal signals"""
        # Connect extraction panel signals
        self.extraction_panel.files_changed.connect(self._on_files_changed)
        self.extraction_panel.extraction_ready.connect(self._on_vram_extraction_ready)
        self.extraction_panel.mode_changed.connect(self._on_extraction_mode_changed)

        # Connect ROM extraction panel signals
        self.rom_extraction_panel.files_changed.connect(self._on_rom_files_changed)
        self.rom_extraction_panel.extraction_ready.connect(
            self._on_rom_extraction_ready
        )
        self.rom_extraction_panel.output_name_changed.connect(
            self._on_rom_output_name_changed
        )

        # Connect output settings manager signals
        # Note: No longer sync TO ROM panel - output name is now shared (ROM panel uses provider callback)
        self.output_settings_manager.grayscale_toggled.connect(self._update_output_info_label)
        self.output_settings_manager.metadata_toggled.connect(self._update_output_info_label)

    def _on_files_changed(self) -> None:
        """Handle when input files change"""
        # Update output name based on input files
        if self.extraction_panel.has_vram():
            vram_path = Path(self.extraction_panel.get_vram_path())
            base_name = vram_path.stem

            # Clean up common suffixes
            for suffix in ["_VRAM", ".SnesVideoRam", "_VideoRam", ".VRAM"]:
                if base_name.endswith(suffix):
                    base_name = base_name[: -len(suffix)]
                    break

            # Convert to lowercase and add suffix
            output_name = f"{base_name.lower()}_sprites_editor"
            self.output_settings_manager.set_output_name(output_name)

        # Save session data when files change
        self.session_coordinator.save_session()

    def _on_vram_extraction_ready(self, ready: bool, reason: str = "") -> None:
        """Handle VRAM extraction ready state change"""
        # Only enable if VRAM tab is active
        if self.tab_coordinator.is_vram_tab_active():
            self.toolbar_manager.set_extract_enabled(ready, reason)

    def _on_extraction_mode_changed(self, mode_index: int) -> None:
        """Handle extraction mode change"""
        # Update checkboxes based on mode
        is_grayscale_mode = mode_index == 1

        # Delegate to output settings manager
        self.output_settings_manager.set_extraction_mode_options(is_grayscale_mode)

        # Update output info label
        self._update_output_info_label()

    def _update_output_info_label(self) -> None:
        """Update the label showing which files will be created"""
        is_vram_tab = self.tab_coordinator.is_vram_tab_active()
        is_grayscale_mode = self.extraction_panel.is_grayscale_mode()

        self.output_settings_manager.update_output_info_label(is_vram_tab, is_grayscale_mode)

    def _on_rom_extraction_ready(self, ready: bool, reason: str = "") -> None:
        """Handle ROM extraction ready state change"""
        # Only enable if ROM tab is active
        if self.tab_coordinator.is_rom_tab_active():
            self.toolbar_manager.set_extract_enabled(ready, reason)

    def _on_rom_files_changed(self) -> None:
        """Handle when ROM extraction files change"""
        # ROM extraction handles its own output naming

    def _on_rom_output_name_changed(self, text: str) -> None:
        """Handle ROM panel output name change"""
        # Update main output field without triggering sync back
        self.output_settings_manager.set_output_name(text)

    # Tab change handling now managed by TabCoordinator

    # Browse output now handled by OutputSettingsManager

    # Button click handlers now managed by ToolbarManager

    # New extraction now handled by MenuBarManager protocol method

    # About dialog now handled by MenuBarManager

    # Keyboard shortcuts dialog now handled by MenuBarManager

    # Settings dialogs now handled by MenuBarManager protocol methods

    def _on_settings_changed(self) -> None:
        """Handle settings change from settings dialog"""
        # Reload any settings that affect the main window
        settings_manager = self.settings_manager
        cache_enabled = settings_manager.get_cache_enabled()
        show_indicators = settings_manager.get("cache", "show_indicators", True)

        # Refresh ROM cache settings
        rom_cache = self.rom_cache
        rom_cache.refresh_settings()

        # Update or hide cache status indicators through manager
        if show_indicators:
            if not hasattr(self.status_bar_manager, "cache_status_widget") or self.status_bar_manager.cache_status_widget is None:
                # Re-create indicators if they were previously hidden
                self.status_bar_manager.setup_status_bar_indicators()
            else:
                # Update existing indicators
                self.status_bar_manager.update_cache_status()
        else:
            # Hide indicators if disabled
            self.status_bar_manager.remove_cache_indicators()

        if cache_enabled and show_indicators:
            self.status_bar_manager.show_message("Settings updated - cache enabled", 3000)
        else:
            self.status_bar_manager.show_message("Settings updated", 3000)

    def _on_cache_cleared(self) -> None:
        """Handle cache cleared signal from settings dialog"""
        self.status_bar_manager.show_message("ROM cache cleared", 3000)
        # Update cache status indicator
        self.status_bar_manager.update_cache_status()

    def get_extraction_params(self) -> VRAMExtractionParams:
        """Get extraction parameters from UI"""
        return {
            "vram_path": self.extraction_panel.get_vram_path(),
            "cgram_path": self.extraction_panel.get_cgram_path() if not self.extraction_panel.is_grayscale_mode() else "",
            "oam_path": self.extraction_panel.get_oam_path(),
            "vram_offset": self.extraction_panel.get_vram_offset(),
            "output_base": self.output_settings_manager.get_output_name(),
            "create_grayscale": self.output_settings_manager.get_grayscale_enabled(),
            "create_metadata": self.output_settings_manager.get_metadata_enabled(),
            "grayscale_mode": self.extraction_panel.is_grayscale_mode(),
        }

    def get_output_path(self) -> str:
        """Get the current output path

        Returns:
            The current output path string, or empty string if not set
        """
        return self._output_path

    def extraction_complete(self, extracted_files: list[str]) -> None:
        """Called when extraction is complete"""
        self._extracted_files = extracted_files

        # CRITICAL FIX FOR BUG #7: Update _output_path based on actual extracted files
        # This ensures UI state consistency with what was actually extracted
        sprite_file = None
        for file_path in extracted_files:
            if file_path.endswith(".png"):
                sprite_file = file_path
                # Derive the actual output base path by removing .png extension
                self._output_path = file_path[:-4]  # Remove ".png"
                break

        # Enable buttons only if we successfully found a sprite file
        if sprite_file:
            self.toolbar_manager.set_extract_enabled(True)
            self.toolbar_manager.set_post_extraction_buttons_enabled(True)

            # Update preview info with successful extraction
            self.preview_coordinator.update_preview_info(f"Extracted {len(extracted_files)} files")
            self.status_bar_manager.show_message("Extraction complete!")
        else:
            # No PNG file found - this shouldn't happen with successful extraction
            self.status_bar_manager.show_message("Extraction failed: No sprite file created")

        # Emit signal for controller/test communication
        self.extraction_completed.emit(extracted_files)

    def extraction_failed(self, error_message: str) -> None:
        """Called when extraction fails"""
        from ui.dialogs import UserErrorDialog  # Lazy import to avoid cross-UI coupling

        self.toolbar_manager.set_extract_enabled(True)
        self.status_bar_manager.show_message("Extraction failed")

        UserErrorDialog.display_error(
            self,
            error_message,
            error_message  # Pass full error as technical details
        )

        # Emit signal for controller/test communication
        self.extraction_error_occurred.emit(error_message)

    # Session restore/save now handled by SessionCoordinator

    # Session save now handled by SessionCoordinator

    @override
    def closeEvent(self, a0: QCloseEvent | None) -> None:
        """Handle window close event"""
        self.session_coordinator.save_session()
        if a0:
            super().closeEvent(a0)

    @override
    def keyPressEvent(self, a0: QKeyEvent | None) -> None:
        """Handle keyboard shortcuts"""
        if not a0:
            return

        # Delegate to keyboard handler
        if self.keyboard_handler.handle_key_press_event(a0):
            return

        super().keyPressEvent(a0)

    # Property delegation to managers for test compatibility
    @property
    def extract_button(self):
        """Delegate to toolbar manager"""
        if hasattr(self, "toolbar_manager"):
            return self.toolbar_manager.extract_button
        return None

    @property
    def open_editor_button(self):
        """Delegate to toolbar manager"""
        if hasattr(self, "toolbar_manager"):
            return self.toolbar_manager.open_editor_button
        return None

    @property
    def arrange_button(self):
        """Delegate to toolbar manager (consolidated arrange button)"""
        if hasattr(self, "toolbar_manager"):
            return self.toolbar_manager.arrange_button
        return None

    # Legacy compatibility properties - delegate to consolidated arrange_button
    @property
    def arrange_rows_button(self):
        """Legacy: delegate to consolidated arrange button for compatibility"""
        return self.arrange_button

    @property
    def arrange_grid_button(self):
        """Legacy: delegate to consolidated arrange button for compatibility"""
        return self.arrange_button

    @property
    def inject_button(self):
        """Delegate to toolbar manager"""
        if hasattr(self, "toolbar_manager"):
            return self.toolbar_manager.inject_button
        return None

    @property
    def output_name_edit(self):
        """Delegate to output settings manager"""
        if hasattr(self, "output_settings_manager"):
            return self.output_settings_manager.output_name_edit
        return None

    @property
    def grayscale_check(self):
        """Delegate to output settings manager"""
        if hasattr(self, "output_settings_manager"):
            return self.output_settings_manager.grayscale_check
        return None

    @property
    def metadata_check(self):
        """Delegate to output settings manager"""
        if hasattr(self, "output_settings_manager"):
            return self.output_settings_manager.metadata_check
        return None

    @property
    def controller(self) -> ExtractionController:
        """Lazy initialization of controller to break circular dependency.

        This allows tests to create MainWindow without hanging, as the controller
        is only created when actually needed (not during __init__).
        """
        if self._controller is None:
            # Import here to avoid circular dependency at module level
            from core.controller import ExtractionController
            from core.di_container import inject
            from core.protocols.dialog_protocols import DialogFactoryProtocol
            from core.protocols.manager_protocols import (
                ApplicationStateManagerProtocol,
                ExtractionManagerProtocol,
                InjectionManagerProtocol,
            )

            self._controller = ExtractionController(
                self,
                extraction_manager=inject(ExtractionManagerProtocol),
                session_manager=inject(ApplicationStateManagerProtocol),
                injection_manager=inject(InjectionManagerProtocol),
                settings_manager=self.settings_manager,
                dialog_factory=inject(DialogFactoryProtocol),
            )
            # Connect controller output signals for decoupled UI updates
            self._connect_controller_signals(self._controller)
        return self._controller

    def _connect_controller_signals(self, ctrl: ExtractionController) -> None:
        """Connect controller output signals to MainWindow slots.

        This enables fully decoupled communication where the controller
        emits signals instead of calling MainWindow methods directly.
        """
        # Status messages
        ctrl.status_message_changed.connect(self.status_bar.showMessage)

        # Preview updates
        ctrl.preview_ready.connect(self._on_controller_preview_ready)
        ctrl.grayscale_image_ready.connect(self._on_controller_grayscale_ready)

        # Palette updates
        ctrl.palettes_ready.connect(self._on_controller_palettes_ready)
        ctrl.active_palettes_ready.connect(self._on_controller_active_palettes_ready)

        # Extraction completion
        ctrl.extraction_completed.connect(self.extraction_complete)
        ctrl.extraction_error.connect(self.extraction_failed)

        # Cache badge operations
        ctrl.cache_badge_show.connect(self.show_cache_operation_badge)
        ctrl.cache_badge_hide.connect(self.hide_cache_operation_badge)

    def _on_controller_preview_ready(self, result: object, tile_count: int) -> None:
        """Handle preview ready signal from controller."""
        self.sprite_preview.set_preview(result, tile_count)

    def _on_controller_grayscale_ready(self, image: object) -> None:
        """Handle grayscale image ready signal from controller."""
        self.sprite_preview.set_grayscale_image(image)

    def _on_controller_palettes_ready(self, palettes: object) -> None:
        """Handle palettes ready signal from controller."""
        if hasattr(self, "palette_preview") and self.palette_preview:
            self.palette_preview.set_all_palettes(palettes)  # type: ignore[arg-type]

    def _on_controller_active_palettes_ready(self, palettes: object) -> None:
        """Handle active palettes highlight signal from controller."""
        if hasattr(self, "palette_preview") and self.palette_preview:
            self.palette_preview.highlight_active_palettes(palettes)  # type: ignore[arg-type]

    @controller.setter
    def controller(self, value: ExtractionController) -> None:
        """Allow setting controller for testing purposes."""
        self._controller = value
