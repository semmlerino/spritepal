"""
Main window for SpritePal application
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from core.managers.application_state_manager import ApplicationStateManager
    from core.services.rom_cache import ROMCache
    from ui.extraction_controller import ExtractionController

from typing import override

from PySide6.QtCore import Qt, Signal

if TYPE_CHECKING:
    from PySide6.QtGui import QCloseEvent, QKeyEvent
else:
    from PySide6.QtGui import QCloseEvent, QKeyEvent
from PySide6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QMainWindow,
    QMessageBox,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QStackedWidget,
    QStatusBar,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

# Session manager accessed via get_app_context().application_state_manager
# Dialog imports moved to lazy imports in methods that use them (see show_settings, extraction_failed)
from core.types import VRAMExtractionParams
from ui.common import ErrorHandler
from ui.common.spacing_constants import (
    MIN_PANEL_WIDTH,
    SPACING_COMPACT_SMALL,
    SPACING_SMALL,
)
from ui.extraction_panel import ExtractionPanel
from ui.managers import (
    KeyboardShortcutManager,
    OutputSettingsManager,
    StatusBarManager,
    ToolbarManager,
    UICoordinator,
)
from ui.palette_preview import PalettePreviewWidget
from ui.rom_extraction_panel import ROMExtractionPanel
from ui.workspaces import ExtractionWorkspace, SpriteEditorWorkspace
from ui.zoomable_preview import PreviewPanel
from utils.logging_config import get_logger

logger = get_logger(__name__)

# Layout constants for consistent sizing and spacing
MAIN_WINDOW_MIN_SIZE = (1000, 700)  # Expanded for embedded editor
DEFAULT_SPLITTER_RATIO = 0.40  # Give more space to preview panel
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
    extraction_error_occurred = Signal(str)  # error message

    def __init__(
        self,
        settings_manager: ApplicationStateManager,
        rom_cache: ROMCache,
        session_manager: ApplicationStateManager,
    ) -> None:
        super().__init__()
        # Declare instance variables with type hints
        self._output_path: str
        self._extracted_files: list[str]
        self._controller: ExtractionController | None
        self._error_handler: ErrorHandler
        self.left_panel: QWidget
        self.extraction_tabs: QTabWidget
        self.rom_extraction_panel: ROMExtractionPanel
        self.extraction_panel: ExtractionPanel
        self.sprite_preview: PreviewPanel
        self.palette_preview: PalettePreviewWidget

        # Create error handler (owned by MainWindow)
        self._error_handler = ErrorHandler(parent=self)

        # Store injected dependencies
        self.settings_manager = settings_manager
        self.rom_cache = rom_cache
        self.session_manager = session_manager

        # Manager instances
        self.toolbar_manager: ToolbarManager
        self.status_bar_manager: StatusBarManager
        self.output_settings_manager: OutputSettingsManager
        self.ui_coordinator: UICoordinator
        self.keyboard_shortcut_manager: KeyboardShortcutManager

        self._output_path = ""
        self._extracted_files = []
        self._controller = None  # Lazy initialization to break circular dependency

        self._setup_ui()
        self._setup_managers()  # This creates all UI widgets via managers
        self._connect_signals()

        # Controller will be created on first access via property
        # This breaks the circular dependency: tests can create MainWindow without hanging

        # Restore session after UI is set up
        self.ui_coordinator.restore_session()

        # Update initial UI state (after managers are fully set up)
        self._update_initial_ui_state()

    def _setup_ui(self) -> None:
        """Initialize the user interface"""
        self.setWindowTitle("SpritePal - Sprite Extraction Tool")
        self.setMinimumSize(*MAIN_WINDOW_MIN_SIZE)

        # Create central widget
        central_widget = QWidget(self)
        central_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setCentralWidget(central_widget)

        # Main horizontal splitter (stored as instance for session persistence)
        self.main_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.main_splitter.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(LAYOUT_MARGINS, LAYOUT_MARGINS, LAYOUT_MARGINS, LAYOUT_MARGINS)
        main_layout.setSpacing(0)  # Splitter handles spacing
        main_layout.addWidget(self.main_splitter, 1)

        # Left panel - Input and controls
        self.left_panel = self._create_left_panel()

        # Right panel - Previews (will be created by UICoordinator)
        self.sprite_preview = PreviewPanel()
        self.palette_preview = PalettePreviewWidget()

        # Add panels to main splitter (right panel created by manager)
        self.main_splitter.addWidget(self.left_panel)
        # Right panel will be added by UICoordinator, sizing configured there

        # Set minimum sizes for panels
        self.left_panel.setMinimumWidth(MIN_PANEL_WIDTH)

        # Status bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Ready to extract sprites")

    def _create_left_panel(self) -> QWidget:
        """Create the left panel with stacked workspaces.

        Structure:
        - QStackedWidget containing:
          - ExtractionWorkspace (index 0): ROM/VRAM extraction tabs + action zone
          - SpriteEditorWorkspace (index 1): Full sprite editing experience

        Keyboard shortcuts:
        - Ctrl+1: ROM Extraction tab (in ExtractionWorkspace)
        - Ctrl+2: VRAM Extraction tab (in ExtractionWorkspace)
        - Ctrl+3: Switch to SpriteEditorWorkspace
        """
        from core.app_context import get_app_context
        from ui.rom_extraction.modules import Mesen2Module

        left_panel = QWidget(self)
        left_panel.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        main_layout = QVBoxLayout(left_panel)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Create workspace stack
        self._workspace_stack = QStackedWidget()
        self._workspace_stack.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        # Get dependencies from app context
        extraction_manager = get_app_context().core_operations_manager
        log_watcher = get_app_context().log_watcher
        mesen2_module = Mesen2Module(log_watcher=log_watcher, parent=self)

        # ExtractionWorkspace (index 0)
        self._extraction_workspace = ExtractionWorkspace(
            parent=self,
            extraction_manager=extraction_manager,
            state_manager=self.settings_manager,
            rom_cache=self.rom_cache,
            mesen2_module=mesen2_module,
        )
        self._workspace_stack.addWidget(self._extraction_workspace)

        # SpriteEditorWorkspace (index 1)
        self._sprite_editor_workspace = SpriteEditorWorkspace(
            parent=self,
            settings_manager=self.settings_manager,
        )
        self._workspace_stack.addWidget(self._sprite_editor_workspace)

        # Connect workspace signals
        self._extraction_workspace.tab_changed.connect(self._on_extraction_tab_changed)
        self._sprite_editor_workspace.status_message.connect(self._on_status_message)

        main_layout.addWidget(self._workspace_stack, 1)

        # Backward compatibility: expose panels that other code might reference
        self.extraction_tabs = self._extraction_workspace.extraction_tabs
        self.rom_extraction_panel = self._extraction_workspace.rom_extraction_panel
        self.extraction_panel = self._extraction_workspace.extraction_panel
        self.action_zone = self._extraction_workspace.action_zone
        self.sprite_edit_tab = self._sprite_editor_workspace  # Type changed but API similar

        return left_panel

    def _on_extraction_tab_changed(self, index: int) -> None:
        """Handle extraction tab changes within ExtractionWorkspace."""
        # Action zone is part of ExtractionWorkspace, so no visibility toggle needed
        pass

    def _on_status_message(self, message: str) -> None:
        """Handle status messages from sprite editor."""
        self.status_bar_manager.show_message(message)

    def _on_tab_changed(self, index: int) -> None:
        """Handle legacy tab changes (now unused with workspace architecture).

        With the new workspace architecture, tabs are within ExtractionWorkspace
        and don't need action zone visibility toggling.

        Args:
            index: Tab index (unused)
        """
        # Action zone is now part of ExtractionWorkspace, always visible
        pass

    def switch_to_workspace(self, workspace_index: int, tab_index: int | None = None) -> None:
        """Switch to a specific workspace and optionally a tab within it.

        Args:
            workspace_index: 0 for Extraction, 1 for Sprite Editor
            tab_index: Optional tab index within the workspace
        """
        self._workspace_stack.setCurrentIndex(workspace_index)

        if tab_index is not None and workspace_index == 0:
            # Switch tab within ExtractionWorkspace
            self._extraction_workspace.set_current_tab(tab_index)

    def handle_tab_switch(self, index: int) -> None:
        """Handle tab switch requests from keyboard shortcuts.

        Ctrl+1: ROM Extraction (extraction workspace, tab 0)
        Ctrl+2: VRAM Extraction (extraction workspace, tab 1)
        Ctrl+3: Sprite Editor workspace

        Args:
            index: Requested tab index (0-2)
        """
        if index == 0:
            self.switch_to_workspace(0, 0)  # Extraction workspace, ROM tab
        elif index == 1:
            self.switch_to_workspace(0, 1)  # Extraction workspace, VRAM tab
        elif index == 2:
            self.switch_to_workspace(1)  # Sprite Editor workspace

    def _setup_managers(self) -> None:
        """Set up all UI managers"""
        # Create managers in dependency order
        self.status_bar_manager = StatusBarManager(
            self.status_bar, settings_manager=self.settings_manager, rom_cache=self.rom_cache
        )
        self.output_settings_manager = OutputSettingsManager(self, self)

        # Connect ROM panel to shared output name via signals (decoupled communication)
        self.output_settings_manager.output_name_changed.connect(self.rom_extraction_panel.set_output_name)
        # Set provider for ROM panel to read current output name from OutputSettingsManager
        self.rom_extraction_panel.set_output_name_provider(self.output_settings_manager.get_output_name)
        # Initialize with current value
        self.rom_extraction_panel.set_output_name(self.output_settings_manager.get_output_name())

        self.toolbar_manager = ToolbarManager(self, self)

        # Keyboard shortcut manager
        self.keyboard_shortcut_manager = KeyboardShortcutManager(self)

        # Consolidated UI coordinator handles preview, session, and tab operations
        self.ui_coordinator = UICoordinator(
            sprite_preview=self.sprite_preview,
            palette_preview=self.palette_preview,
            main_window=self,
            extraction_panel=self.extraction_panel,
            output_settings_manager=self.output_settings_manager,
            session_manager=self.session_manager,
            extraction_tabs=self.extraction_tabs,
            rom_extraction_panel=self.rom_extraction_panel,
            toolbar_manager=self.toolbar_manager,
            actions_handler=self,
        )

        # Backward compatibility: expose preview_info for existing code/tests
        self.preview_info = self.ui_coordinator.preview_info

        # Initialize manager UIs
        self._create_menus()
        self.status_bar_manager.setup_status_bar_indicators()

        # Add action buttons to the pinned action zone
        # Note: Output settings moved to dialog (shown on Extract click)
        action_zone_layout = self.action_zone.layout()
        if action_zone_layout is not None and isinstance(action_zone_layout, QVBoxLayout):
            # Add toolbar buttons
            button_layout = QGridLayout()
            button_layout.setContentsMargins(0, LAYOUT_SPACING, 0, 0)
            button_layout.setSpacing(LAYOUT_SPACING)
            self.toolbar_manager.create_action_buttons(button_layout)
            action_zone_layout.addLayout(button_layout)

        # Add preview panel to main splitter
        right_panel = self.ui_coordinator.create_preview_panel(self)
        self.main_splitter.addWidget(right_panel)
        right_panel.setMinimumWidth(MIN_PANEL_WIDTH)
        # Ensure right panel has proper size policy
        from PySide6.QtWidgets import QSizePolicy

        right_panel.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        # Configure splitter now that both panels exist
        total_width = MAIN_WINDOW_MIN_SIZE[0] - (2 * LAYOUT_MARGINS)
        left_width = int(total_width * DEFAULT_SPLITTER_RATIO)
        right_width = total_width - left_width
        self.main_splitter.setSizes([left_width, right_width])
        self.main_splitter.setStretchFactor(0, 1)  # Left: lower stretch priority
        self.main_splitter.setStretchFactor(1, 3)  # Right: higher stretch priority

    def _update_initial_ui_state(self) -> None:
        """Update initial UI state after setup"""
        # Update extraction mode (for VRAM panel)
        self._on_extraction_mode_changed(self.extraction_panel.mode_combo.currentIndex())

        # Sync action_zone visibility with current tab
        self._on_tab_changed(self.extraction_tabs.currentIndex())

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
        self.ui_coordinator.clear_previews()
        self.toolbar_manager.reset_buttons()
        self._output_path = ""
        self._extracted_files = []
        self.status_bar_manager.show_message("Ready to extract sprites")

        # Clear session data
        self.ui_coordinator.clear_session()

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

    def show_presets(self) -> None:
        """Show the sprite presets management dialog"""
        from ui.dialogs.sprite_preset_dialog import SpritePresetDialog

        dialog = SpritePresetDialog(parent=self)
        dialog.exec()

    def clear_all_caches(self) -> None:
        """Clear all ROM caches with confirmation"""
        rom_cache = self.rom_cache
        try:
            removed_count = rom_cache.clear_cache()

            self.status_bar_manager.show_message(f"Cleared {removed_count} cache files")

            QMessageBox.information(self, "Cache Cleared", f"Successfully removed {removed_count} cache files.")
        except (OSError, PermissionError) as e:
            QMessageBox.critical(self, "File Error", f"Cannot access cache files: {e}")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to clear cache: {e!s}")

    def on_extract_clicked(self) -> None:
        """Handle extract button click"""
        from ui.dialogs import OutputSettingsDialog

        # Determine if we're in ROM mode (affects dialog options)
        is_rom_mode = self.ui_coordinator.is_rom_tab_active()

        # Get suggested output name from the current state
        suggested_name = self.output_settings_manager.get_output_name()

        # Get default directory for browse
        default_dir = self.get_current_vram_path() or str(Path.cwd())

        # Show output settings dialog
        settings = OutputSettingsDialog.get_output_settings(
            parent=self,
            suggested_name=suggested_name,
            is_rom_mode=is_rom_mode,
            default_directory=default_dir,
        )

        # User cancelled
        if settings is None:
            return

        # Validate output name
        if not settings.output_name:
            QMessageBox.warning(self, "Missing Output Name", "Please enter an output name for the extracted sprites.")
            return

        # Proceed with extraction
        if is_rom_mode:
            self._handle_rom_extraction(settings.output_name)
        else:
            self._handle_vram_extraction(settings.output_name, settings.export_palette_files, settings.include_metadata)

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

    def get_current_vram_path(self) -> str:
        """Get current VRAM path for browse dialog default directory"""
        current_files = self.extraction_panel.get_session_data()
        vram_path = current_files.get("vram_path", "")
        return str(vram_path) if vram_path else ""

    def get_rom_extraction_params(self) -> dict[str, Any] | None:  # pyright: ignore[reportExplicitAny] - Extraction configuration
        """Get ROM extraction parameters"""
        return self.rom_extraction_panel.get_extraction_params()

    def is_vram_extraction_ready(self) -> bool:
        """Check if VRAM extraction is ready"""
        if self.extraction_panel.is_grayscale_mode():
            return self.extraction_panel.has_vram()
        return self.extraction_panel.has_vram() and self.extraction_panel.has_cgram()

    def is_grayscale_mode(self) -> bool:
        """Check if in grayscale mode"""
        return self.extraction_panel.is_grayscale_mode()

    def get_extraction_mode_index(self) -> int:
        """Get current extraction mode index"""
        return self.extraction_panel.mode_combo.currentIndex()

    # KeyboardActionsProtocol
    def can_open_manual_offset_dialog(self) -> bool:
        """Check if manual offset dialog can be opened"""
        return self.ui_coordinator.is_rom_tab_active() and bool(self.rom_extraction_panel.rom_path)

    def open_manual_offset_dialog(self) -> None:
        """Open manual offset dialog"""
        self.rom_extraction_panel.open_manual_offset_dialog()

    def _handle_rom_extraction(self, output_name: str) -> None:
        """Handle ROM extraction

        Args:
            output_name: Output filename (without extension) from dialog
        """
        params = self.rom_extraction_panel.get_extraction_params()
        if params:
            # Use the output name from dialog
            params["output_base"] = output_name

            # Validate parameters using extraction manager
            # Delayed import to avoid initialization order issues
            from core.app_context import get_app_context

            try:
                extraction_manager = get_app_context().core_operations_manager
                extraction_manager.validate_extraction_params(params)
            except (ValueError, TypeError) as e:
                QMessageBox.warning(self, "Validation Error", f"Invalid extraction parameters: {e}")
                return
            except Exception as e:
                QMessageBox.warning(self, "Validation Error", str(e))
                return

            self._output_path = params["output_base"]
            self.status_bar_manager.show_message("Extracting sprites from ROM...")
            self.toolbar_manager.set_extract_enabled(False)
            self.controller.start_rom_extraction(params)

    def _handle_vram_extraction(
        self,
        output_name: str,
        export_palette_files: bool,
        include_metadata: bool,
    ) -> None:
        """Handle VRAM extraction

        Args:
            output_name: Output filename (without extension) from dialog
            export_palette_files: Whether to export palette files
            include_metadata: Whether to include metadata
        """
        # Store settings for use in get_vram_extraction_params
        self._vram_output_name = output_name
        self._vram_export_palettes = export_palette_files
        self._vram_include_metadata = include_metadata

        self._output_path = output_name
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

    # Menu creation inlined from MenuBarManager

    def _create_menus(self) -> None:
        """Create application menus"""
        from PySide6.QtGui import QAction

        menubar = self.menuBar()
        if not menubar:
            return

        # File menu
        file_menu = menubar.addMenu("File")
        if file_menu:
            new_action = QAction("New Extraction", self)
            new_action.setShortcut("Ctrl+N")
            new_action.triggered.connect(self.new_extraction)
            file_menu.addAction(new_action)
            file_menu.addSeparator()

            exit_action = QAction("Exit", self)
            exit_action.setShortcut("Ctrl+Q")
            exit_action.triggered.connect(self.close)
            file_menu.addAction(exit_action)

        # Tools menu
        tools_menu = menubar.addMenu("Tools")
        if tools_menu:
            settings_action = QAction("Settings...", self)
            settings_action.setShortcut("Ctrl+,")
            settings_action.triggered.connect(self.show_settings)
            tools_menu.addAction(settings_action)

            presets_action = QAction("Manage Presets...", self)
            presets_action.setShortcut("Ctrl+P")
            presets_action.triggered.connect(self.show_presets)
            tools_menu.addAction(presets_action)
            tools_menu.addSeparator()

            cache_manager_action = QAction("Cache Manager...", self)
            cache_manager_action.triggered.connect(self.show_cache_manager)
            tools_menu.addAction(cache_manager_action)
            tools_menu.addSeparator()

            clear_cache_action = QAction("Clear All Caches", self)
            clear_cache_action.triggered.connect(self.clear_all_caches)
            tools_menu.addAction(clear_cache_action)

        # Help menu
        help_menu = menubar.addMenu("Help")
        if help_menu:
            shortcuts_action = QAction("Keyboard Shortcuts", self)
            shortcuts_action.setShortcut("F1")
            shortcuts_action.triggered.connect(self._show_keyboard_shortcuts)
            help_menu.addAction(shortcuts_action)
            help_menu.addSeparator()

            about_action = QAction("About SpritePal", self)
            about_action.triggered.connect(self._show_about)
            help_menu.addAction(about_action)

    def _show_about(self) -> None:
        """Show about dialog"""
        QMessageBox.about(
            self,
            "About SpritePal",
            "<h2>SpritePal</h2>"
            "<p>Version 1.0.0</p>"
            "<p>A modern sprite extraction tool for SNES games.</p>"
            "<p>Simplifies sprite extraction with automatic palette association.</p>"
            "<br>"
            "<p>Part of the Kirby Super Star sprite editing toolkit.</p>",
        )

    def _show_keyboard_shortcuts(self) -> None:
        """Show keyboard shortcuts dialog"""
        shortcuts_text = """
        <h3>Main Actions</h3>
        <table>
        <tr><td><b>Ctrl+E / F5</b></td><td>Extract sprites</td></tr>
        <tr><td><b>Ctrl+O</b></td><td>Open in editor</td></tr>
        <tr><td><b>Ctrl+R</b></td><td>Arrange rows</td></tr>
        <tr><td><b>Ctrl+G</b></td><td>Grid arrange</td></tr>
        <tr><td><b>Ctrl+I</b></td><td>Inject sprites</td></tr>
        <tr><td><b>Ctrl+N</b></td><td>New extraction</td></tr>
        <tr><td><b>Ctrl+Q</b></td><td>Exit application</td></tr>
        </table>

        <h3>Navigation</h3>
        <table>
        <tr><td><b>Ctrl+Tab</b></td><td>Next tab</td></tr>
        <tr><td><b>Ctrl+Shift+Tab</b></td><td>Previous tab</td></tr>
        <tr><td><b>Alt+N</b></td><td>Focus output name field</td></tr>
        <tr><td><b>Ctrl+F</b></td><td>Find Sprites in ROM</td></tr>
        <tr><td><b>F1</b></td><td>Show this help</td></tr>
        </table>

        <h3>ROM Manual Offset Mode</h3>
        <table>
        <tr><td><b>Ctrl+M</b></td><td>Open Manual Offset Control window</td></tr>
        <tr><td><b>Alt+Left</b></td><td>Find previous sprite (in dialog)</td></tr>
        <tr><td><b>Alt+Right</b></td><td>Find next sprite (in dialog)</td></tr>
        <tr><td><b>Page Up</b></td><td>Jump backward 64KB (in dialog)</td></tr>
        <tr><td><b>Page Down</b></td><td>Jump forward 64KB (in dialog)</td></tr>
        </table>

        <h3>Preview Window</h3>
        <table>
        <tr><td><b>G</b></td><td>Toggle grid</td></tr>
        <tr><td><b>F</b></td><td>Zoom to fit</td></tr>
        <tr><td><b>Ctrl+0</b></td><td>Reset zoom to 4x</td></tr>
        <tr><td><b>C</b></td><td>Toggle palette</td></tr>
        <tr><td><b>Mouse Wheel</b></td><td>Zoom in/out</td></tr>
        </table>
        """
        QMessageBox.information(self, "Keyboard Shortcuts", shortcuts_text)

    def _connect_signals(self) -> None:
        """Connect internal signals"""
        # Connect extraction panel signals
        self.extraction_panel.files_changed.connect(self._on_files_changed)
        self.extraction_panel.extraction_ready.connect(self._on_vram_extraction_ready)
        self.extraction_panel.mode_changed.connect(self._on_extraction_mode_changed)

        # Connect ROM extraction panel signals
        self.rom_extraction_panel.files_changed.connect(self._on_rom_files_changed)
        self.rom_extraction_panel.extraction_ready.connect(self._on_rom_extraction_ready)
        self.rom_extraction_panel.output_name_changed.connect(self._on_rom_output_name_changed)

        # Connect sprite editor status messages to main status bar
        self._sprite_editor_workspace.status_message.connect(lambda msg: self.status_bar_manager.show_message(msg, 3000))

        # Connect ROM panel's "open in sprite editor" signal
        self.rom_extraction_panel.open_in_sprite_editor.connect(self._on_open_in_sprite_editor)

        # Sync ROM path to sprite editor
        self.rom_extraction_panel.rom_loaded.connect(self._sprite_editor_workspace.load_rom)

        # Connect ROM panel's Mesen2 watching status to status bar
        self.rom_extraction_panel.mesen2_watching_changed.connect(self.status_bar_manager.set_mesen2_watching)

        # Connect keyboard shortcut manager signals
        self.keyboard_shortcut_manager.tab_switch_requested.connect(self._on_tab_switch_requested)
        self.keyboard_shortcut_manager.tab_next_requested.connect(self._navigate_to_next_tab)
        self.keyboard_shortcut_manager.tab_previous_requested.connect(self._navigate_to_previous_tab)
        self.keyboard_shortcut_manager.extract_requested.connect(self._on_extract_shortcut)
        self.keyboard_shortcut_manager.mesen_capture_requested.connect(self._on_mesen_capture_shortcut)
        self.keyboard_shortcut_manager.manual_offset_requested.connect(self._on_manual_offset_shortcut)
        self.keyboard_shortcut_manager.focus_output_requested.connect(self._on_focus_output_shortcut)

        # Note: Output settings are now shown in a dialog on Extract click
        # The output_settings_manager just tracks the suggested output name

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
        self.ui_coordinator.save_session()

    def _on_vram_extraction_ready(self, ready: bool, reason: str = "") -> None:
        """Handle VRAM extraction ready state change"""
        # Only enable if VRAM tab is active
        if self.ui_coordinator.is_vram_tab_active():
            self.toolbar_manager.set_extract_enabled(ready, reason)

    def _on_extraction_mode_changed(self, mode_index: int) -> None:
        """Handle extraction mode change"""
        # Mode change just affects VRAM panel UI - output settings are in dialog now
        # The dialog will handle grayscale mode options when shown
        pass

    def _on_rom_extraction_ready(self, ready: bool, reason: str = "") -> None:
        """Handle ROM extraction ready state change"""
        # Only enable if ROM tab is active
        if self.ui_coordinator.is_rom_tab_active():
            self.toolbar_manager.set_extract_enabled(ready, reason)

    def _on_rom_files_changed(self) -> None:
        """Handle when ROM extraction files change"""
        # ROM extraction handles its own output naming

    def _on_rom_output_name_changed(self, text: str) -> None:
        """Handle ROM panel output name change"""
        # Update main output field without triggering sync back
        self.output_settings_manager.set_output_name(text)

    def _on_open_in_sprite_editor(self, offset: int) -> None:
        """Handle request to open offset in sprite editor.

        Called when user double-clicks a Mesen2 capture offset.

        Args:
            offset: ROM offset to open in sprite editor
        """
        logger.info("Opening offset 0x%06X in sprite editor", offset)
        if self.rom_extraction_panel.rom_path:
            self._sprite_editor_workspace.load_rom(self.rom_extraction_panel.rom_path)
        # Switch to sprite editor workspace
        self._workspace_stack.setCurrentWidget(self._sprite_editor_workspace)
        # Jump to offset in sprite editor
        self._sprite_editor_workspace.jump_to_offset(offset)

    # Tab change handling now managed by UICoordinator

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
            if (
                not hasattr(self.status_bar_manager, "cache_status_widget")
                or self.status_bar_manager.cache_status_widget is None
            ):
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
        # Use settings from dialog (stored in _handle_vram_extraction)
        return {
            "vram_path": self.extraction_panel.get_vram_path(),
            "cgram_path": self.extraction_panel.get_cgram_path()
            if not self.extraction_panel.is_grayscale_mode()
            else "",
            "oam_path": self.extraction_panel.get_oam_path(),
            "vram_offset": self.extraction_panel.get_vram_offset(),
            "output_base": getattr(self, "_vram_output_name", ""),
            "create_grayscale": getattr(self, "_vram_export_palettes", True),
            "create_metadata": getattr(self, "_vram_include_metadata", True),
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
            self.ui_coordinator.update_preview_info(f"Extracted {len(extracted_files)} files")
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
            error_message,  # Pass full error as technical details
        )

        # Emit signal for controller/test communication
        self.extraction_error_occurred.emit(error_message)

    # Session restore/save now handled by UICoordinator

    # Session save now handled by UICoordinator

    @override
    def closeEvent(self, a0: QCloseEvent | None) -> None:
        """Handle window close event."""
        self.ui_coordinator.save_session()
        self._cleanup_managers()
        if a0:
            super().closeEvent(a0)

    def _cleanup_managers(self) -> None:
        """Clean up signal connections in all UI managers and panels.

        Prevents memory leaks from orphaned signal handlers when the window closes.
        Child widget closeEvent is NOT called when parent closes, so we must
        explicitly clean up panels here.
        """
        # Clean up managers (not all have cleanup methods yet)
        managers: list[object] = [
            self.status_bar_manager,
            self.output_settings_manager,
            self.toolbar_manager,
            self.ui_coordinator,
        ]
        for manager in managers:
            cleanup_fn = getattr(manager, "cleanup", None)
            if callable(cleanup_fn):
                cleanup_fn()

        # Clean up panels (their closeEvent won't be called automatically)
        panels: list[object] = [
            self.rom_extraction_panel,
            self.extraction_panel,
            self.sprite_edit_tab,
        ]
        for panel in panels:
            cleanup_fn = getattr(panel, "cleanup", None)
            if callable(cleanup_fn):
                cleanup_fn()

    # Keyboard shortcut handlers (called by KeyboardShortcutManager signals)

    def _on_tab_switch_requested(self, index: int) -> None:
        """Handle request to switch to specific tab.

        Args:
            index: Tab index (0=ROM, 1=VRAM, 2=Sprite Editor)
        """
        self.extraction_tabs.setCurrentIndex(index)

    def _on_extract_shortcut(self) -> None:
        """Handle F5 extract shortcut."""
        if self.toolbar_manager.extract_button.isEnabled():
            self.on_extract_clicked()

    def _on_mesen_capture_shortcut(self) -> None:
        """Handle F6 Mesen capture shortcut."""
        offset = self.rom_extraction_panel.get_last_mesen_offset()
        if offset is not None:
            self._on_open_in_sprite_editor(offset)

    def _on_manual_offset_shortcut(self) -> None:
        """Handle Ctrl+M manual offset shortcut."""
        if self.can_open_manual_offset_dialog():
            self.open_manual_offset_dialog()

    def _on_focus_output_shortcut(self) -> None:
        """Handle Alt+N focus output name shortcut."""
        # Try active panel's output field first
        active_widget = self.extraction_tabs.currentWidget()

        # Check if wrapped in ScrollArea (new structure)
        if isinstance(active_widget, QScrollArea):
            active_panel = active_widget.widget()
        else:
            active_panel = active_widget

        output_edit = getattr(active_panel, "output_name_edit", None)

        # Fallback to output settings manager (legacy/shared)
        if output_edit is None:
            output_edit = getattr(self.output_settings_manager, "output_name_edit", None)

        if output_edit is not None:
            output_edit.setFocus()
            if hasattr(output_edit, "selectAll"):
                output_edit.selectAll()

    @override
    def keyPressEvent(self, event: QKeyEvent | None) -> None:
        """Handle keyboard shortcuts via KeyboardShortcutManager."""
        if not event:
            return

        # Delegate to keyboard shortcut manager
        if self.keyboard_shortcut_manager.handle_key_press(event):
            event.accept()
            return

        super().keyPressEvent(event)

    def _navigate_to_next_tab(self) -> None:
        """Navigate to next tab"""
        current = self.ui_coordinator.get_current_tab_index()
        tab_count = self.extraction_tabs.count()
        next_tab = (current + 1) % tab_count
        self.extraction_tabs.setCurrentIndex(next_tab)

    def _navigate_to_previous_tab(self) -> None:
        """Navigate to previous tab"""
        current = self.ui_coordinator.get_current_tab_index()
        tab_count = self.extraction_tabs.count()
        prev_tab = (current - 1) % tab_count
        self.extraction_tabs.setCurrentIndex(prev_tab)

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

    @property
    def inject_button(self):
        """Delegate to toolbar manager"""
        if hasattr(self, "toolbar_manager"):
            return self.toolbar_manager.inject_button
        return None

    @property
    def output_name_edit(self):
        """Delegate to output settings manager (returns None if inline UI not created)"""
        if hasattr(self, "output_settings_manager"):
            return getattr(self.output_settings_manager, "output_name_edit", None)
        return None

    @property
    def grayscale_check(self):
        """Delegate to output settings manager (returns None if inline UI not created)"""
        if hasattr(self, "output_settings_manager"):
            return getattr(self.output_settings_manager, "grayscale_check", None)
        return None

    @property
    def metadata_check(self):
        """Delegate to output settings manager (returns None if inline UI not created)"""
        if hasattr(self, "output_settings_manager"):
            return getattr(self.output_settings_manager, "metadata_check", None)
        return None

    @property
    def controller(self) -> ExtractionController:
        """Lazy initialization of controller to break circular dependency.

        This allows tests to create MainWindow without hanging, as the controller
        is only created when actually needed (not during __init__).
        """
        if self._controller is None:
            # Import here to avoid circular dependency at module level
            from core.app_context import get_app_context
            from ui.extraction_controller import ExtractionController

            context = get_app_context()
            self._controller = ExtractionController(
                self,
                extraction_manager=context.core_operations_manager,
                session_manager=context.application_state_manager,
                injection_manager=context.core_operations_manager,
                settings_manager=self.settings_manager,
                preview_generator=context.preview_generator,
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
        from typing import cast

        from PySide6.QtGui import QPixmap

        self.sprite_preview.set_preview(cast(QPixmap, result), tile_count)

    def _on_controller_grayscale_ready(self, image: object) -> None:
        """Handle grayscale image ready signal from controller."""
        from typing import cast

        from PIL.Image import Image as PILImage

        self.sprite_preview.set_grayscale_image(cast(PILImage, image))

    def _on_controller_palettes_ready(self, palettes: object) -> None:
        """Handle palettes ready signal from controller."""
        if hasattr(self, "palette_preview") and self.palette_preview:
            normalized = self._normalize_palettes(palettes)
            if normalized is not None:
                self.palette_preview.set_all_palettes(normalized)

    def _on_controller_active_palettes_ready(self, palettes: object) -> None:
        """Handle active palettes highlight signal from controller."""
        if hasattr(self, "palette_preview") and self.palette_preview:
            active_indices = self._normalize_active_palettes(palettes)
            if active_indices is not None:
                self.palette_preview.highlight_active_palettes(active_indices)

    @staticmethod
    def _normalize_palettes(palettes: object) -> dict[int, list[tuple[int, int, int]]] | None:
        """Normalize palette data into palette_index -> list[(r, g, b)]."""
        if not isinstance(palettes, Mapping):
            logger.warning("Palettes payload is not a mapping: %s", type(palettes).__name__)
            return None

        normalized: dict[int, list[tuple[int, int, int]]] = {}
        for key, colors in palettes.items():
            try:
                palette_index = int(key)
            except (TypeError, ValueError):
                logger.warning("Skipping palette with non-numeric key: %r", key)
                continue

            if not isinstance(colors, Sequence):
                logger.warning("Palette %s colors are not a sequence", palette_index)
                continue

            converted: list[tuple[int, int, int]] = []
            for color in colors:
                if not isinstance(color, Sequence) or len(color) != 3:
                    logger.warning("Palette %s has invalid color entry: %r", palette_index, color)
                    continue
                try:
                    r, g, b = (int(channel) for channel in color)
                except (TypeError, ValueError):
                    logger.warning("Palette %s has non-numeric color: %r", palette_index, color)
                    continue
                converted.append((r, g, b))

            if converted:
                normalized[palette_index] = converted

        return normalized

    @staticmethod
    def _normalize_active_palettes(active_palettes: object) -> list[int] | None:
        """Normalize active palette indices to a list of ints."""
        if not isinstance(active_palettes, Sequence) or isinstance(active_palettes, str | bytes):
            logger.warning("Active palettes payload is not a sequence: %s", type(active_palettes).__name__)
            return None

        normalized: list[int] = []
        for value in active_palettes:
            try:
                normalized.append(int(value))
            except (TypeError, ValueError):
                logger.warning("Skipping invalid active palette index: %r", value)
                continue

        return normalized

    @controller.setter
    def controller(self, value: ExtractionController) -> None:
        """Allow setting controller for testing purposes."""
        self._controller = value

    @property
    def error_handler(self) -> ErrorHandler:
        """Get the application error handler (owned by MainWindow)."""
        return self._error_handler
