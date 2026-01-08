"""
Main window for SpritePal application
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Any

from PIL import Image

if TYPE_CHECKING:
    from core.managers.application_state_manager import ApplicationStateManager
    from core.services.rom_cache import ROMCache
    from core.workers import ROMExtractionWorker, VRAMExtractionWorker
    from ui.extraction_controller import ExtractionController
    from ui.injection_dialog import InjectionDialog
    from ui.services.dialog_coordinator import DialogCoordinator

from typing import override

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAction, QCloseEvent, QKeyEvent, QKeySequence
from PySide6.QtWidgets import (
    QApplication,
    QDockWidget,
    QGridLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QStatusBar,
    QStyle,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

# Session manager accessed via get_app_context().application_state_manager
# Dialog imports moved to lazy imports in methods that use them (see show_settings, extraction_failed)
from core.services.image_utils import pil_to_qpixmap
from core.types import VRAMExtractionParams
from ui.common import ErrorHandler
from ui.common.spacing_constants import (
    SPACING_MEDIUM,
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
from ui.sprite_editor.views.widgets.offset_line_edit import OffsetLineEdit
from ui.workspaces import ExtractionWorkspace, SpriteEditorWorkspace
from ui.zoomable_preview import PreviewPanel
from utils.constants import VRAM_SPRITE_OFFSET
from utils.file_validator import FileValidator
from utils.logging_config import get_logger

logger = get_logger(__name__)

# Layout constants for consistent sizing and spacing
MAIN_WINDOW_MIN_SIZE = (1000, 700)  # Expanded for embedded editor
DEFAULT_SPLITTER_RATIO = 0.40  # Give more space to preview panel
LAYOUT_MARGINS = SPACING_MEDIUM  # 16px - standard margins
LAYOUT_SPACING = SPACING_SMALL  # 8px - standard spacing


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
        self._dialog_coordinator: DialogCoordinator | None
        self._error_handler: ErrorHandler
        self.left_dock: QDockWidget
        self.center_stack: QStackedWidget
        self.undo_action: QAction
        self.redo_action: QAction
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
        self._dialog_coordinator = None  # Lazy initialization for dialog service
        self._last_undo_state = (False, False)

        # Worker management (Phase 4d: direct extraction orchestration)
        self._vram_worker: VRAMExtractionWorker | None = None
        self._rom_worker: ROMExtractionWorker | None = None
        self._manager_connections: list[object] = []
        # Extraction result storage
        self._extracted_palettes: dict[int, list[list[int]]] = {}
        self._active_palettes: list[int] = []
        # Injection state (Phase 4e)
        self._current_injection_dialog: InjectionDialog | None = None

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

        # Create main toolbar
        self._create_main_toolbar()

        # Center Stack (replaces Splitter)
        self.center_stack = QStackedWidget()
        self.setCentralWidget(self.center_stack)

        # Left Dock
        self.left_dock = QDockWidget("Controls", self)
        self.left_dock.setAllowedAreas(Qt.DockWidgetArea.LeftDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea)
        self.left_dock.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetMovable | QDockWidget.DockWidgetFeature.DockWidgetFloatable
        )
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self.left_dock)

        # Pre-create preview widgets (needed for UI Coordinator)
        self.sprite_preview = PreviewPanel()
        self.palette_preview = PalettePreviewWidget()

        # Create workspaces
        self._create_workspaces()

        # Status bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Ready to extract sprites")

    def _create_main_toolbar(self) -> None:
        """Create the main toolbar with global actions."""
        toolbar = self.addToolBar("Main Toolbar")
        toolbar.setMovable(False)
        toolbar.setFloatable(False)

        style = QApplication.style()

        # Undo
        self.undo_action = QAction("Undo", self)
        self.undo_action.setIcon(style.standardIcon(QStyle.StandardPixmap.SP_ArrowBack))
        self.undo_action.setShortcut(QKeySequence.StandardKey.Undo)
        self.undo_action.setEnabled(False)
        self.undo_action.triggered.connect(self._on_undo)
        toolbar.addAction(self.undo_action)

        # Redo
        self.redo_action = QAction("Redo", self)
        self.redo_action.setIcon(style.standardIcon(QStyle.StandardPixmap.SP_ArrowForward))
        self.redo_action.setShortcut(QKeySequence.StandardKey.Redo)
        self.redo_action.setEnabled(False)
        self.redo_action.triggered.connect(self._on_redo)
        toolbar.addAction(self.redo_action)

        # Spacer
        empty = QWidget()
        empty.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        toolbar.addWidget(empty)

        # Offset Input
        toolbar.addWidget(QLabel("Go to: 0x"))
        self.toolbar_offset_edit = OffsetLineEdit()
        self.toolbar_offset_edit.setMaximumWidth(100)
        self.toolbar_offset_edit.offset_changed.connect(self._on_global_offset_changed)
        toolbar.addWidget(self.toolbar_offset_edit)

    def _on_global_offset_changed(self, offset: int) -> None:
        """Handle global offset change from toolbar."""
        # Check active mode
        if self.center_stack.currentIndex() == 1:
            # Editor Mode
            self._sprite_editor_workspace.jump_to_offset(offset)
        else:
            # Extraction Mode
            # Switch to ROM tab if not active (assuming ROM offset)
            if not self.ui_coordinator.is_rom_tab_active():
                self.ui_coordinator.switch_to_rom_tab()

            # Set offset in ROM panel
            if hasattr(self.rom_extraction_panel, "set_manual_offset"):
                self.rom_extraction_panel.set_manual_offset(offset)

    def _create_workspaces(self) -> None:
        """Create workspace widgets."""
        from core.app_context import get_app_context
        from ui.rom_extraction.modules import Mesen2Module

        # Get dependencies
        extraction_manager = get_app_context().core_operations_manager
        log_watcher = get_app_context().log_watcher
        mesen2_module = Mesen2Module(log_watcher=log_watcher, parent=self)

        # 1. Extraction Workspace (Dock Content)
        self._extraction_workspace = ExtractionWorkspace(
            parent=self,
            extraction_manager=extraction_manager,
            state_manager=self.settings_manager,
            rom_cache=self.rom_cache,
            mesen2_module=mesen2_module,
        )
        self._extraction_workspace.tab_changed.connect(self._on_extraction_tab_changed)
        # Connect manual offset changed from ROM panel
        self._extraction_workspace.rom_extraction_panel.manual_offset_changed.connect(
            self.toolbar_offset_edit.set_offset
        )
        self.left_dock.setWidget(self._extraction_workspace)

        # 2. Sprite Editor Workspace (Center Content)
        self._sprite_editor_workspace = SpriteEditorWorkspace(
            parent=self,
            settings_manager=self.settings_manager,
        )
        self._sprite_editor_workspace.status_message.connect(self._on_status_message)
        self._sprite_editor_workspace.undo_state_changed.connect(self._update_undo_redo_state)
        self._sprite_editor_workspace.offset_changed.connect(self.toolbar_offset_edit.set_offset)

        self.center_stack.addWidget(self._sprite_editor_workspace)

        # Backward compatibility aliases
        self.extraction_tabs = self._extraction_workspace.extraction_tabs
        self.rom_extraction_panel = self._extraction_workspace.rom_extraction_panel
        self.extraction_panel = self._extraction_workspace.extraction_panel
        self.action_zone = self._extraction_workspace.action_zone
        self.sprite_edit_tab = self._sprite_editor_workspace

    def _on_extraction_tab_changed(self, index: int) -> None:
        """Handle extraction tab changes within ExtractionWorkspace."""
        if index == 2:  # Sprite Editor tab
            self.switch_to_workspace(1)
        else:
            self.switch_to_workspace(0)

    def _on_status_message(self, message: str) -> None:
        """Handle status messages from sprite editor."""
        self.status_bar_manager.show_message(message)

    def _on_undo(self) -> None:
        """Handle undo action."""
        self._sprite_editor_workspace.undo()

    def _on_redo(self) -> None:
        """Handle redo action."""
        self._sprite_editor_workspace.redo()

    def _update_undo_redo_state(self, can_undo: bool, can_redo: bool) -> None:
        """Update undo/redo action state."""
        self._last_undo_state = (can_undo, can_redo)
        # Only update buttons if sprite editor is active (Index 1)
        if hasattr(self, "center_stack") and self.center_stack.currentIndex() == 1:
            self.undo_action.setEnabled(can_undo)
            self.redo_action.setEnabled(can_redo)

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
        if workspace_index == 0:
            # Extraction Mode
            self.center_stack.setCurrentIndex(0)  # Preview
            self.left_dock.show()
            self._update_undo_redo_state(False, False)  # Disable undo
        elif workspace_index == 1:
            # Sprite Editor Mode
            self.center_stack.setCurrentIndex(1)  # Editor
            self.left_dock.hide()
            # Restore last undo state
            can_undo, can_redo = self._last_undo_state
            self._update_undo_redo_state(can_undo, can_redo)

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

        # Add preview panel to center stack (for Extraction mode)
        # Note: create_preview_panel returns a splitter containing preview/palette.
        # This acts as the Central Widget content for index 0.
        right_panel = self.ui_coordinator.create_preview_panel(self)
        # Insert at index 0 (pushing Editor to 1)
        self.center_stack.insertWidget(0, right_panel)

        # Initial State: Extraction Mode (Index 0)
        self.center_stack.setCurrentIndex(0)

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
        """Handle open in editor button click."""
        if self._output_path:
            sprite_file = f"{self._output_path}.png"
            # Use DialogCoordinator directly (Phase 4b: controller removal)
            self.dialog_coordinator.open_in_editor(
                sprite_file,
                status_callback=self.status_bar.showMessage,
            )
            # Keep signal for backwards compatibility during transition
            self.open_in_editor_requested.emit(sprite_file)

    def on_arrange_rows_clicked(self) -> None:
        """Handle arrange rows button click."""
        if self._output_path:
            sprite_file = f"{self._output_path}.png"
            # Get palettes from sprite preview if available
            palettes = self._get_palettes_for_dialog()
            # Get tiles per row from sprite preview if available
            tiles_per_row = self._get_tiles_per_row_for_dialog()

            # Use DialogCoordinator directly (Phase 4b: controller removal)
            def _open_arranged_rows(path: str) -> None:
                self.dialog_coordinator.open_in_editor(path, status_callback=self.status_bar.showMessage)

            self.dialog_coordinator.open_row_arrangement(
                sprite_file,
                palettes=palettes,
                tiles_per_row=tiles_per_row,
                status_callback=self.status_bar.showMessage,
                on_success=_open_arranged_rows,
            )
            # Keep signal for backwards compatibility during transition
            self.arrange_rows_requested.emit(sprite_file)

    def on_arrange_grid_clicked(self) -> None:
        """Handle arrange grid button click."""
        if self._output_path:
            sprite_file = f"{self._output_path}.png"
            # Get palettes from sprite preview if available
            palettes = self._get_palettes_for_dialog()
            # Get tiles per row from sprite preview if available
            tiles_per_row = self._get_tiles_per_row_for_dialog()

            # Use DialogCoordinator directly (Phase 4b: controller removal)
            def _open_arranged_grid(path: str) -> None:
                self.dialog_coordinator.open_in_editor(path, status_callback=self.status_bar.showMessage)

            self.dialog_coordinator.open_grid_arrangement(
                sprite_file,
                palettes=palettes,
                tiles_per_row=tiles_per_row,
                status_callback=self.status_bar.showMessage,
                on_success=_open_arranged_grid,
            )
            # Keep signal for backwards compatibility during transition
            self.arrange_grid_requested.emit(sprite_file)

    def _get_palettes_for_dialog(self) -> dict[int, list[tuple[int, int, int]]] | None:
        """Get palette data from sprite preview for dialogs.

        Returns:
            Palette dict if available, None otherwise.
        """
        if hasattr(self, "sprite_preview") and self.sprite_preview:
            if hasattr(self.sprite_preview, "get_palettes"):
                try:
                    palettes = self.sprite_preview.get_palettes()
                    if palettes:
                        return palettes
                except Exception as e:
                    logger.warning(f"Failed to get palettes for dialog: {e}")
        return None

    def _get_tiles_per_row_for_dialog(self) -> int | None:
        """Get tiles per row from sprite preview for dialogs.

        Returns:
            Tiles per row if available, None to let DialogCoordinator calculate.
        """
        if hasattr(self, "sprite_preview") and self.sprite_preview:
            try:
                _, tiles_per_row = self.sprite_preview.get_tile_info()
                if tiles_per_row > 0:
                    return tiles_per_row
            except (AttributeError, TypeError):
                pass
        return None

    def _update_preview_with_offset(self, offset: int) -> None:
        """Update preview with new VRAM offset without full extraction.

        Handles real-time preview updates when user moves the offset slider.
        Uses PreviewGenerator service for preview generation.

        Note: This method is connected to extraction_panel.offset_changed.
        CRITICAL: PIL→QPixmap conversion happens in main thread (Bug #26 fix).
        """
        logger.debug(f"Updating preview with offset: 0x{offset:04X} ({offset})")

        try:
            # Check if we have VRAM loaded
            has_vram = self.extraction_panel.has_vram()
            if not has_vram:
                logger.debug("No VRAM loaded, skipping preview update")
                return

            # Get VRAM path
            vram_path = self.extraction_panel.get_vram_path()
            if not vram_path:
                logger.warning("VRAM path is empty or None")
                self.status_bar.showMessage("VRAM path not available")
                return

            # Get PreviewGenerator from app context
            from core.app_context import get_app_context
            from core.services.preview_generator import create_vram_preview_request

            preview_generator = get_app_context().preview_generator

            # Create preview request
            preview_request = create_vram_preview_request(
                vram_path=vram_path,
                offset=offset,
                sprite_name=f"vram_0x{offset:06X}",
                size=(self.sprite_preview.width(), self.sprite_preview.height()),
            )

            # Generate preview with progress tracking
            def progress_callback(percent: int, message: str) -> None:
                progress_msg = f"{message} ({percent}%)"
                self.status_bar.showMessage(progress_msg)

            result = preview_generator.generate_preview(preview_request, progress_callback)

            if result is None:
                logger.error("Preview generation failed")
                self.status_bar.showMessage("Preview generation failed")
                return

            logger.debug(f"Generated preview with {result.tile_count} tiles, cached: {result.cached}")

            # Update preview without resetting view (for real-time slider updates)
            # CRITICAL: result.pixmap is already QPixmap from PreviewGenerator (main thread safe)
            self.sprite_preview.update_preview(result.pixmap, result.tile_count)

            # Update status bar with preview info
            info_text = f"Tiles: {result.tile_count} (Offset: 0x{offset:04X})"
            self.status_bar.showMessage(info_text)

            # Update grayscale image for palette application
            self.sprite_preview.set_grayscale_image(result.pil_image)

            logger.debug("Preview update completed successfully")

        except Exception as e:
            error_msg = f"Preview update failed: {e!s}"
            logger.exception("Error in preview update with offset 0x%04X", offset)

            # Show error in status bar
            self.status_bar.showMessage(error_msg)
            self.sprite_preview.clear()

    def on_inject_clicked(self) -> None:
        """Handle inject to VRAM button click"""
        if self._output_path:
            # Start injection directly (Phase 4e: controller removal)
            self._start_injection()

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

        # Start extraction directly (Phase 4d: controller removal)
        self._start_vram_extraction()

    # ═══════════════════════════════════════════════════════════════════════════
    # VRAM EXTRACTION ORCHESTRATION (Phase 4d: moved from ExtractionController)
    # ═══════════════════════════════════════════════════════════════════════════

    def _start_vram_extraction(self) -> None:
        """Start the VRAM extraction process.

        Validates parameters, creates worker, and connects signals.
        Handles PIL→QPixmap conversion in main thread (Bug #26 fix).
        """
        from core.app_context import get_app_context
        from core.workers import VRAMExtractionWorker

        # Get parameters from UI
        params = self.get_extraction_params()

        # Get extraction manager from app context
        context = get_app_context()
        extraction_manager = context.core_operations_manager

        # PARAMETER VALIDATION: Check requirements first for better UX
        try:
            extraction_manager.validate_extraction_params(params)
        except (ValueError, TypeError) as e:
            self.extraction_failed(str(e))
            return
        except Exception as e:
            logger.exception("Unexpected error during extraction parameter validation")
            self.extraction_failed(f"Validation error: {e}")
            return

        # DEFENSIVE VALIDATION: Validate files that exist
        vram_path = params.get("vram_path", "")
        if vram_path:
            vram_result = FileValidator.validate_vram_file(vram_path)
            if not vram_result.is_valid:
                self.extraction_failed(vram_result.error_message or "VRAM file validation failed")
                return
            for warning in vram_result.warnings:
                logger.warning(f"VRAM file warning: {warning}")

        cgram_path = params.get("cgram_path", "")
        grayscale_mode = params.get("grayscale_mode", False)
        if cgram_path and not grayscale_mode:
            cgram_result = FileValidator.validate_cgram_file(cgram_path)
            if not cgram_result.is_valid:
                self.extraction_failed(cgram_result.error_message or "CGRAM file validation failed")
                return
            for warning in cgram_result.warnings:
                logger.warning(f"CGRAM file warning: {warning}")

        oam_path = params.get("oam_path", "")
        if oam_path:
            oam_result = FileValidator.validate_oam_file(oam_path)
            if not oam_result.is_valid:
                self.extraction_failed(oam_result.error_message or "OAM file validation failed")
                return
            for warning in oam_result.warnings:
                logger.warning(f"OAM file warning: {warning}")

        # Create extraction parameters TypedDict
        extraction_params: VRAMExtractionParams = {
            "vram_path": params["vram_path"],
            "cgram_path": params.get("cgram_path") or None,
            "oam_path": params.get("oam_path") or None,
            "vram_offset": params.get("vram_offset", VRAM_SPRITE_OFFSET),
            "output_base": params["output_base"],
            "create_grayscale": params.get("create_grayscale", True),
            "create_metadata": params.get("create_metadata", True),
            "grayscale_mode": params.get("grayscale_mode", False),
        }

        # Create and start worker
        worker = VRAMExtractionWorker(extraction_params, extraction_manager=extraction_manager)
        self._vram_worker = worker

        # Worker-owned signals
        _ = worker.progress.connect(self._on_vram_progress)
        _ = worker.extraction_finished.connect(self._on_vram_extraction_finished)
        _ = worker.error.connect(self._on_vram_extraction_error)

        # Connect directly to manager signals for data (1 hop instead of 3)
        self._manager_connections = [
            extraction_manager.preview_generated.connect(self._on_vram_preview_ready),
            extraction_manager.palettes_extracted.connect(self._on_vram_palettes_ready),
            extraction_manager.active_palettes_found.connect(self._on_vram_active_palettes_ready),
        ]

        worker.start()

    def _on_vram_progress(self, percent: int, message: str) -> None:
        """Handle progress updates from worker."""
        self.status_bar_manager.show_message(message)

    def _on_vram_preview_ready(self, pil_image: Image.Image, tile_count: int) -> None:
        """Handle preview ready - convert PIL Image to QPixmap in main thread.

        CRITICAL FIX FOR BUG #26: This MUST run in the main thread.
        Manager emits PIL Image to avoid Qt threading violations.
        """
        pixmap = pil_to_qpixmap(pil_image)
        if pixmap is not None:
            self.sprite_preview.set_preview(pixmap, tile_count)
            self.status_bar_manager.show_message(f"Preview updated: {tile_count} tiles")
        else:
            logger.error("Failed to convert PIL image to QPixmap for preview")

    def _on_vram_palettes_ready(self, palettes: dict[int, list[list[int]]]) -> None:
        """Handle palettes ready from extraction."""
        # Store for dialog use
        self._extracted_palettes = palettes
        # Update palette preview widget with normalized data
        if hasattr(self, "palette_preview") and self.palette_preview:
            normalized = self._normalize_palettes(palettes)
            if normalized is not None:
                self.palette_preview.set_all_palettes(normalized)

    def _on_vram_active_palettes_ready(self, active_palettes: list[int]) -> None:
        """Handle active palettes ready."""
        # Store for dialog use
        self._active_palettes = active_palettes

    def _on_vram_extraction_finished(self, extracted_files: list[str]) -> None:
        """Handle extraction finished."""
        self._cleanup_vram_worker()
        self._extracted_files = extracted_files
        self.toolbar_manager.set_extract_enabled(True)

        if extracted_files:
            self.status_bar_manager.show_message(f"Extraction complete: {len(extracted_files)} file(s)")
            # Emit for external listeners
            self.extraction_completed.emit(extracted_files)
        else:
            self.status_bar_manager.show_message("Extraction complete (no files)")

    def _on_vram_extraction_error(self, error_message: str, exception: Exception | None = None) -> None:
        """Handle extraction error."""
        self._cleanup_vram_worker()
        self.extraction_failed(error_message)

    def _cleanup_vram_worker(self) -> None:
        """Safely cleanup VRAM worker thread and manager signal connections."""
        from core.services.worker_lifecycle import WorkerManager

        # Disconnect manager signals (connected per-operation)
        self._disconnect_manager_signals()

        if self._vram_worker is not None:
            WorkerManager.cleanup_worker(self._vram_worker, timeout=3000)
            self._vram_worker = None

    def _disconnect_manager_signals(self) -> None:
        """Disconnect manager signal connections."""
        from PySide6.QtCore import QObject

        for connection in self._manager_connections:
            try:
                QObject.disconnect(connection)  # type: ignore[arg-type]
            except (RuntimeError, TypeError):
                # Signal may already be disconnected
                pass
        self._manager_connections.clear()

    # ═══════════════════════════════════════════════════════════════════════════
    # INJECTION ORCHESTRATION (Phase 4e: moved from ExtractionController)
    # ═══════════════════════════════════════════════════════════════════════════

    def _start_injection(self) -> None:
        """Start the injection process using InjectionManager."""

        from core.app_context import get_app_context

        # Get sprite path and metadata path
        output_base = self.get_output_path()
        if not output_base:
            self.status_bar.showMessage("No extraction to inject")
            return

        sprite_path = f"{output_base}.png"
        metadata_path = f"{output_base}.metadata.json"

        # Validate sprite file exists before creating dialog
        sprite_result = FileValidator.validate_file_existence(sprite_path, "Sprite file")
        if not sprite_result.is_valid:
            self.status_bar.showMessage(sprite_result.error_message or f"Sprite file not found: {sprite_path}")
            return

        # Get managers from app context
        context = get_app_context()
        injection_manager = context.core_operations_manager
        settings_mgr = context.application_state_manager

        # Get smart input VRAM suggestion using injection manager
        suggested_input_vram = injection_manager.get_smart_vram_suggestion(
            sprite_path, metadata_path if Path(metadata_path).exists() else ""
        )

        # Show injection dialog directly
        from ui.injection_dialog import InjectionDialog

        dialog = InjectionDialog(
            parent=self,
            sprite_path=sprite_path,
            metadata_path=metadata_path if Path(metadata_path).exists() else "",
            input_vram=suggested_input_vram,
            injection_manager=injection_manager,
            settings_manager=settings_mgr,
        )

        if dialog.exec():
            params = dialog.get_parameters()
            if params:
                # Store dialog reference for saving on success
                self._current_injection_dialog = dialog
                settings_mgr.set("workflow", "current_injection_params", params)

                # Connect injection manager signals before starting
                self._injection_progress_connection = injection_manager.injection_progress.connect(
                    self._on_injection_progress
                )
                self._injection_finished_connection = injection_manager.injection_finished.connect(
                    self._on_injection_finished
                )

                # Start injection using manager
                success = injection_manager.start_injection(params)
                if not success:
                    self.status_bar.showMessage("Failed to start injection")
                    self._cleanup_injection_connections()

    def _on_injection_progress(self, message: str) -> None:
        """Handle injection progress updates."""
        self.status_bar.showMessage(message)

    def _on_injection_finished(self, success: bool, message: str) -> None:
        """Handle injection completion."""

        from core.app_context import get_app_context

        context = get_app_context()
        settings_mgr = context.application_state_manager

        if success:
            success_msg = f"Injection successful: {message}"
            self.status_bar.showMessage(success_msg)

            # Save injection parameters for future use if it was a ROM injection
            current_injection_params = settings_mgr.get("workflow", "current_injection_params")

            if (
                current_injection_params
                and isinstance(current_injection_params, Mapping)
                and current_injection_params.get("mode") == "rom"
                and self._current_injection_dialog
            ):
                try:
                    self._current_injection_dialog.save_rom_injection_parameters()
                except Exception as e:
                    logger.warning(f"Could not save ROM injection parameters: {e}")
        else:
            fail_msg = f"Injection failed: {message}"
            self.status_bar.showMessage(fail_msg)

        # Clean up
        self._current_injection_dialog = None
        settings_mgr.set("workflow", "current_injection_params", None)
        self._cleanup_injection_connections()

    def _cleanup_injection_connections(self) -> None:
        """Cleanup injection signal connections."""
        from PySide6.QtCore import QObject

        if hasattr(self, "_injection_progress_connection"):
            try:
                QObject.disconnect(self._injection_progress_connection)
            except (RuntimeError, TypeError):
                pass
            delattr(self, "_injection_progress_connection")

        if hasattr(self, "_injection_finished_connection"):
            try:
                QObject.disconnect(self._injection_finished_connection)
            except (RuntimeError, TypeError):
                pass
            delattr(self, "_injection_finished_connection")

    # ═══════════════════════════════════════════════════════════════════════════

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
        # Direct preview update handling (Phase 4c: controller removal)
        self.extraction_panel.offset_changed.connect(self._update_preview_with_offset)

        # Connect ROM extraction panel signals
        self.rom_extraction_panel.files_changed.connect(self._on_rom_files_changed)
        self.rom_extraction_panel.extraction_ready.connect(self._on_rom_extraction_ready)
        self.rom_extraction_panel.output_name_changed.connect(self._on_rom_output_name_changed)

        # Connect sprite editor status messages to main status bar
        self._sprite_editor_workspace.status_message.connect(
            lambda msg: self.status_bar_manager.show_message(msg, 3000)
        )

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
        self.switch_to_workspace(1)
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

        # Cache badge connections removed in Phase 2 simplification

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
    def dialog_coordinator(self) -> DialogCoordinator:
        """Lazy initialization of dialog coordinator.

        DialogCoordinator handles dialog-related operations (open in editor,
        row/grid arrangement) that were previously in ExtractionController.
        """
        if self._dialog_coordinator is None:
            from ui.services.dialog_coordinator import DialogCoordinator

            self._dialog_coordinator = DialogCoordinator(parent=self)
        return self._dialog_coordinator

    @property
    def error_handler(self) -> ErrorHandler:
        """Get the application error handler (owned by MainWindow)."""
        return self._error_handler
