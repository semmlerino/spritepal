"""
Unified Manual Offset Dialog - Integrated Implementation

A consolidated implementation that combines the working UI from the archived
simplified dialog with proper tab integration and signal coordination.

This dialog provides:
- Working slider that updates offset
- Preview widget display
- Three functional tabs (Browse, Smart, History)
- Proper signals (offset_changed, sprite_found)
- Methods needed by ROM extraction panel
"""

from __future__ import annotations

import contextlib
import time
from pathlib import Path
from typing import TYPE_CHECKING, cast, override

with contextlib.suppress(ImportError):
    pass

if TYPE_CHECKING:
    from core.managers.application_state_manager import ApplicationStateManager
    from core.managers.core_operations_manager import CoreOperationsManager
    from core.rom_extractor import ROMExtractor
    from core.services.rom_cache import ROMCache

from PySide6.QtCore import (
    QMutex,
    QMutexLocker,
    QPoint,
    Qt,
    QThread,
    QTimer,
    Signal,
)

if TYPE_CHECKING:
    from PySide6.QtGui import QCloseEvent, QHideEvent, QKeyEvent, QMoveEvent, QResizeEvent, QShowEvent
else:
    from PySide6.QtGui import QCloseEvent, QHideEvent, QKeyEvent, QMoveEvent, QResizeEvent, QShowEvent
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFrame,
    QInputDialog,
    QLabel,
    QPushButton,
    QSizePolicy,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ui.common import SpriteSearchCoordinator, WorkerManager
from ui.common.collapsible_group_box import CollapsibleGroupBox
from ui.common.smart_preview_coordinator import SmartPreviewCoordinator
from ui.common.spacing_constants import SPACING_SMALL, SPACING_STANDARD
from ui.styles.theme import COLORS


def get_main_thread() -> QThread | None:
    """Get main thread safely."""
    app = QApplication.instance()
    return app.thread() if app else None


from ui.components.base.cleanup_dialog import CleanupDialog
from ui.components.panels import StatusPanel
from ui.components.visualization.rom_map_widget import ROMMapWidget
from ui.dialogs.services import BookmarkManager, CacheStatusController, ViewStateManager
from ui.rom_extraction.workers import SpritePreviewWorker
from ui.tabs.sprite_gallery_tab import SpriteGalleryTab
from ui.widgets.sprite_preview_widget import SpritePreviewWidget
from utils.constants import ROM_SIZE_2MB, ROM_SIZE_4MB, normalize_address, parse_address_string
from utils.logging_config import get_logger

logger = get_logger(__name__)

# Layout constants (formerly in DialogLayoutManager)
_MAX_MINI_MAP_HEIGHT = 60
_MIN_MINI_MAP_HEIGHT = 40


# Signal utilities imported from shared module
from ui.common.signal_utils import is_valid_qt as _is_valid_qt, safe_disconnect as _safe_disconnect

# Import tab widgets from the new module
from ui.tabs.manual_offset import SimpleBrowseTab, SimpleHistoryTab, SimpleSmartTab


class UnifiedManualOffsetDialog(CleanupDialog):
    """
    Unified Manual Offset Dialog combining simplified architecture with tab-based navigation.

    This dialog consolidates functionality from the archived simplified dialog while
    providing a clean, working interface with proper signal coordination.
    Now accepts injected dependencies for ROM cache, settings, and managers.
    """

    # Define signals directly on the dialog for compatibility
    offset_changed = Signal(int)  # Emitted when offset changes
    sprite_found = Signal(int, str)  # Emitted when sprite is found (offset, name)

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        rom_cache: ROMCache,
        settings_manager: ApplicationStateManager,
        extraction_manager: CoreOperationsManager,
        rom_extractor: ROMExtractor | None = None,
    ) -> None:
        # Debug logging for singleton tracking
        logger.debug(
            f"Creating UnifiedManualOffsetDialog instance (parent: {parent.__class__.__name__ if parent else 'None'})"
        )

        # UI Components - declare BEFORE super().__init__()
        self.tab_widget: QTabWidget | None = None
        self.browse_tab: SimpleBrowseTab | None = None
        self.smart_tab: SimpleSmartTab | None = None
        self.history_tab: SimpleHistoryTab | None = None
        self.gallery_tab: SpriteGalleryTab | None = None
        self.preview_widget: SpritePreviewWidget | None = None
        self.status_panel: StatusPanel | None = None
        self.status_collapsible: CollapsibleGroupBox | None = None
        self.apply_btn: QPushButton | None = None
        self.mini_rom_map: ROMMapWidget | None = None
        self._bookmark_manager: BookmarkManager | None = None
        self._cache_controller: CacheStatusController | None = None
        self._search_coordinator: SpriteSearchCoordinator | None = None
        self._advanced_search_dialog: QDialog | None = None

        # Business logic state
        self.rom_path: str = ""
        self.rom_size: int = ROM_SIZE_4MB
        self._last_offset_processed: int | None = None  # Re-entrancy guard

        # Manager references with thread safety
        self._manager_mutex = QMutex()
        self._preview_update_mutex = QMutex()  # Mutex for serializing preview widget updates

        # Store injected dependencies
        self.extraction_manager = extraction_manager
        self.rom_cache = rom_cache
        self.settings_manager = settings_manager

        # rom_extractor can be obtained from extraction_manager if not provided
        if rom_extractor is None:
            self.rom_extractor: ROMExtractor | None = cast(
                "ROMExtractor | None", self.extraction_manager.get_rom_extractor()
            )
        else:
            self.rom_extractor = rom_extractor

        # Note: _cache_controller and _search_coordinator are created after super().__init__() below

        # Worker references (preview worker still managed here)
        self.preview_worker: SpritePreviewWorker | None = None
        # Note: search_worker, _sprite_scan_worker, _scan_progress_dialog now managed by SpriteSearchCoordinator

        # Preview coordinator handles preview generation (created in _setup_smart_preview_coordinator)
        self._smart_preview_coordinator: SmartPreviewCoordinator | None = None

        # Preview update timer (legacy - kept for compatibility)
        self._preview_timer: QTimer | None = None

        # Debug ID for tracking
        self._debug_id = f"dialog_{int(time.time() * 1000)}"
        logger.debug(f"Dialog debug ID: {self._debug_id}")

        super().__init__(
            parent=parent,
            title="Manual Offset Control - SpritePal",
            modal=False,
            size=(900, 600),  # More compact size
            min_size=(800, 500),  # Smaller minimum
            with_status_bar=False,
            orientation=Qt.Orientation.Horizontal,
            splitter_handle_width=8,  # Thinner splitter handle
        )

        # Initialize view state manager with injected settings_manager
        self.view_state_manager = ViewStateManager(self, self, settings_manager=self.settings_manager)

        # Initialize bookmark manager
        self._bookmark_manager = BookmarkManager(self, self)
        self._bookmark_manager.bookmark_selected.connect(self.set_offset)
        self._bookmark_manager.status_message.connect(self._update_status)

        # Initialize cache controller
        self._cache_controller = CacheStatusController(self.rom_cache, self, self)
        self._cache_controller.status_updated.connect(self._update_status)

        # Initialize sprite search coordinator
        self._search_coordinator = SpriteSearchCoordinator(self, self.rom_cache, self)
        self._search_coordinator.sprite_found.connect(self._on_search_sprite_found)
        self._search_coordinator.search_complete.connect(self._on_search_complete)
        self._search_coordinator.status_message.connect(self._update_status)
        self._search_coordinator.offset_requested.connect(self.set_offset)

        # Note: _setup_ui() is called by DialogBase.__init__() automatically
        self._setup_smart_preview_coordinator()
        self._setup_preview_timer()
        self._connect_signals()

    @override
    def _setup_ui(self) -> None:
        """Set up the dialog UI."""
        try:
            logger.debug("Starting _setup_ui")

            # Create left and right panels
            left_panel = self._create_left_panel()
            right_panel = self._create_right_panel()

            # Add panels to splitter with better proportions
            # Left panel should be wider for controls, right panel narrower for preview
            self.add_panel(left_panel, stretch_factor=3)
            self.add_panel(right_panel, stretch_factor=2)

            logger.debug("_setup_ui completed successfully")

        except Exception as e:
            logger.error(f"Error in _setup_ui: {e}")
            import traceback

            logger.error(f"Traceback: {traceback.format_exc()}")
            # Don't re-raise - this might be causing the dialog deletion
            logger.error("Continuing despite _setup_ui error to avoid dialog deletion")

        # Set up custom buttons
        self._setup_custom_buttons()

    def _create_left_panel(self) -> QWidget:
        """Create the left panel with tabs and collapsible status."""
        panel = QWidget()
        layout = QVBoxLayout(panel)

        # Apply compact layout configuration
        layout.setSpacing(SPACING_SMALL)
        layout.setContentsMargins(SPACING_SMALL, SPACING_SMALL, SPACING_SMALL, SPACING_SMALL)

        # Tab widget
        self.tab_widget = QTabWidget()

        # Create and add tabs
        self.browse_tab = SimpleBrowseTab()
        self.smart_tab = SimpleSmartTab()
        self.history_tab = SimpleHistoryTab()
        self.gallery_tab = SpriteGalleryTab()

        self.tab_widget.addTab(self.browse_tab, "Browse")
        self.tab_widget.addTab(self.smart_tab, "Smart")
        self.tab_widget.addTab(self.history_tab, "History")
        self.tab_widget.addTab(self.gallery_tab, "Gallery")

        # Add tab widget with stretch to fill available space
        layout.addWidget(self.tab_widget, 1)  # Give it stretch value to expand

        # Status panel - expanded by default for better visibility
        self.status_collapsible = CollapsibleGroupBox("Status", collapsed=False)
        self.status_panel = StatusPanel(settings_manager=self.settings_manager, rom_cache=self.rom_cache)
        self.status_collapsible.add_widget(self.status_panel)

        # Add context menu for cache management
        self._setup_cache_context_menu()

        layout.addWidget(self.status_collapsible, 0)  # No stretch - fixed size

        # Mini ROM map for position context with flexible height
        self.mini_rom_map = ROMMapWidget()
        self.mini_rom_map.setMaximumHeight(_MAX_MINI_MAP_HEIGHT)
        self.mini_rom_map.setMinimumHeight(_MIN_MINI_MAP_HEIGHT)
        self.mini_rom_map.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        layout.addWidget(self.mini_rom_map, 0)  # No stretch - fixed height
        # The tab widget with stretch=1 will expand to fill available space

        return panel

    def _create_right_panel(self) -> QWidget:
        """Create the right panel with preview."""
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setSpacing(SPACING_SMALL)
        layout.setContentsMargins(SPACING_STANDARD, SPACING_STANDARD, SPACING_STANDARD, SPACING_STANDARD)

        # Title with better styling
        title = QLabel("Sprite Preview")
        title.setStyleSheet(f"font-size: 14px; font-weight: bold; color: {COLORS['highlight']};")
        layout.addWidget(title, 0)  # No stretch for title

        # Preview widget with frame for better visibility
        preview_frame = QFrame()
        preview_frame.setFrameStyle(QFrame.Shape.StyledPanel)
        preview_frame.setStyleSheet(f"""
            QFrame {{
                background-color: {COLORS["input_background"]};
                border: 1px solid {COLORS["panel_background"]};
                border-radius: 6px;
            }}
        """)
        preview_layout = QVBoxLayout(preview_frame)
        preview_layout.setContentsMargins(SPACING_SMALL, SPACING_SMALL, SPACING_SMALL, SPACING_SMALL)

        # Preview widget configured to expand within frame
        self.preview_widget = SpritePreviewWidget()
        self.preview_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.preview_widget.similarity_search_requested.connect(self._on_similarity_search_requested)
        preview_layout.addWidget(self.preview_widget)

        layout.addWidget(preview_frame, 1)  # Give frame all the stretch

        # No controls section needed - preview widget handles its own controls

        return panel

    def _setup_custom_buttons(self) -> None:
        """Set up custom dialog buttons with improved layout."""
        if self.button_box is None:
            return

        # Clear default buttons and create a more organized button layout
        self.button_box.clear()

        # Primary action buttons (left side)
        self.apply_btn = QPushButton("Apply Offset")
        self.apply_btn.setToolTip("Apply the current offset to the extraction")
        self.apply_btn.clicked.connect(self._apply_offset)
        self.button_box.addButton(self.apply_btn, self.button_box.ButtonRole.AcceptRole)

        # Bookmark management buttons (center)
        bookmark_btn = QPushButton("Add Bookmark")
        bookmark_btn.setToolTip("Save current offset to bookmarks (Ctrl+D)")
        bookmark_btn.clicked.connect(
            lambda: self._bookmark_manager.add_bookmark(self.get_current_offset()) if self._bookmark_manager else None
        )
        self.button_box.addButton(bookmark_btn, self.button_box.ButtonRole.ActionRole)

        bookmarks_menu_btn = QPushButton("Bookmarks ▼")
        bookmarks_menu_btn.setToolTip("Show saved bookmarks (Ctrl+B)")
        if self._bookmark_manager:
            bookmarks_menu_btn.setMenu(self._bookmark_manager.create_menu())
        self.button_box.addButton(bookmarks_menu_btn, self.button_box.ButtonRole.ActionRole)

        # Standard dialog buttons (right side)
        close_btn = QPushButton("Close")
        close_btn.setToolTip("Close this dialog")
        close_btn.clicked.connect(self.hide)
        self.button_box.addButton(close_btn, self.button_box.ButtonRole.RejectRole)

        # Apply consistent spacing to button box
        self.button_box.setStyleSheet("""
            QDialogButtonBox {
                padding: 8px;
                spacing: 8px;
            }
            QPushButton {
                min-width: 90px;
                padding: 4px 12px;
            }
        """)

    def _setup_smart_preview_coordinator(self) -> None:
        """Set up SmartPreviewCoordinator for efficient preview generation."""
        # Create coordinator owned by this dialog
        self._smart_preview_coordinator = SmartPreviewCoordinator(self)
        logger.debug("Created SmartPreviewCoordinator")

        # Connect preview signals
        self._smart_preview_coordinator.preview_ready.connect(self._on_smart_preview_ready)
        self._smart_preview_coordinator.preview_cached.connect(self._on_smart_preview_cached)
        self._smart_preview_coordinator.preview_error.connect(self._on_smart_preview_error)

        # Setup ROM data provider (dialog provides rom_path and extractor)
        self._smart_preview_coordinator.set_rom_data_provider(self._get_rom_data_for_preview)

        # Connect cache-related signals
        self._smart_preview_coordinator.preview_ready.connect(self._on_cache_miss)
        self._smart_preview_coordinator.preview_cached.connect(self._on_cache_hit)

        logger.debug("Smart preview coordinator setup complete")

    def _setup_preview_timer(self) -> None:
        """Set up preview update timer."""
        self._preview_timer = QTimer(self)
        self._preview_timer.setSingleShot(True)
        self._preview_timer.timeout.connect(self._update_preview)

    def _connect_signals(self) -> None:
        """Connect internal signals."""
        if self.browse_tab is None or self.smart_tab is None or self.history_tab is None or self.gallery_tab is None:
            return

        # Browse tab signals
        self.browse_tab.offset_changed.connect(self._on_offset_changed)
        self.browse_tab.find_next_clicked.connect(self._find_next_sprite)
        self.browse_tab.find_prev_clicked.connect(self._find_prev_sprite)
        self.browse_tab.find_sprites_requested.connect(self._scan_for_sprites)

        # Connect smart preview coordinator to browse tab
        if self._smart_preview_coordinator:
            self.browse_tab.connect_smart_preview_coordinator(self._smart_preview_coordinator)

        # Smart tab signals
        self.smart_tab.smart_mode_changed.connect(self._on_smart_mode_changed)
        self.smart_tab.region_changed.connect(self._on_region_changed)
        self.smart_tab.offset_requested.connect(self._on_offset_requested)

        # History tab signals
        self.history_tab.sprite_selected.connect(self._on_sprite_selected)

        # Gallery tab signals - uses same handler as history (both navigate to browse tab)
        self.gallery_tab.sprite_selected.connect(self._on_sprite_selected)

    def _on_offset_changed(self, offset: int) -> None:
        """Handle offset changes from browse tab."""
        # Prevent re-entrant calls for the same offset
        if self._last_offset_processed == offset:
            return
        self._last_offset_processed = offset

        # Update cache stats
        if self._cache_controller:
            self._cache_controller.increment_total_requests()

        # Update UI elements
        if self.mini_rom_map is not None:
            self.mini_rom_map.set_current_offset(offset)
        if self.preview_widget is not None:
            self.preview_widget.set_current_offset(offset)

        # Emit signal for external listeners
        self._emit_offset_changed(offset)

        # Request preview
        if self._smart_preview_coordinator is not None:
            try:
                self._smart_preview_coordinator.request_manual_preview(offset)
            except Exception as e:
                logger.exception(f"Failed to request manual preview: {e}")

        # Schedule predictive preloading for adjacent offsets
        self._schedule_adjacent_preloading(offset)

    def _emit_offset_changed(self, offset: int) -> None:
        """Emit offset changed signal safely.

        Handles the case where the dialog is being destroyed during emission.
        """
        try:
            self.offset_changed.emit(offset)
        except RuntimeError as e:
            # Dialog deleted during emit - normal during shutdown
            if "deleted" in str(e).lower():
                logger.debug(f"Signal source deleted during offset emit: {e}")
            else:
                raise

    def _on_offset_requested(self, offset: int) -> None:
        """Handle offset request from smart tab."""
        if self.browse_tab is not None:
            self.browse_tab.set_offset(offset)

    def _navigate_to_browse_tab(self, offset: int) -> None:
        """Set offset and switch to browse tab."""
        if self.browse_tab is not None:
            self.browse_tab.set_offset(offset)
        if self.tab_widget is not None:
            self.tab_widget.setCurrentIndex(0)

    def _on_sprite_selected(self, offset: int) -> None:
        """Handle sprite selection from history or gallery - navigate to browse tab."""
        self._navigate_to_browse_tab(offset)

    def _on_smart_mode_changed(self, enabled: bool) -> None:
        """Handle smart mode toggle."""
        # Could implement smart mode behavior here

    def _on_region_changed(self, region_index: int) -> None:
        """Handle region change."""
        # Could implement region-specific behavior here

    def _find_next_sprite(self) -> None:
        """Find next sprite with region awareness."""
        self._find_sprite(forward=True)

    def _find_prev_sprite(self) -> None:
        """Find previous sprite with region awareness."""
        self._find_sprite(forward=False)

    def _find_sprite(self, forward: bool) -> None:
        """Find next or previous sprite.

        Args:
            forward: True to search forward, False to search backward.
        """
        if not self.browse_tab or not self._has_rom_data():
            return

        current_offset = self.browse_tab.get_current_offset()

        if self._search_coordinator is not None:
            self._search_coordinator.find_sprite(current_offset, forward)

    def _jump_to_sprite(self, offset: int) -> None:
        """Jump to a specific sprite offset.

        Args:
            offset: The ROM offset to jump to.
        """
        self.set_offset(offset)

    def _request_preview_update(self, delay_ms: int = 100) -> None:
        """Request preview update with debouncing."""
        if self._preview_timer is not None:
            self._preview_timer.stop()
            self._preview_timer.start(delay_ms)

    def _update_preview(self) -> None:
        """Update sprite preview."""
        if not self._has_rom_data() or self.browse_tab is None:
            return

        current_offset = self.browse_tab.get_current_offset()
        self._update_status(f"Loading preview for 0x{current_offset:06X}...")

        # Clean up existing preview worker
        WorkerManager.cleanup_worker_attr(self, "preview_worker", timeout=1000)

        # Create new preview worker
        with QMutexLocker(self._manager_mutex):
            extractor = self.rom_extractor
            if extractor is not None:
                sprite_name = f"manual_0x{current_offset:X}"
                self.preview_worker = SpritePreviewWorker(
                    self.rom_path, current_offset, sprite_name, extractor, None, parent=self
                )
                self.preview_worker.preview_ready.connect(self._on_preview_ready)
                self.preview_worker.preview_error.connect(self._on_preview_error)
                self.preview_worker.start()

    def _on_preview_ready(
        self, tile_data: bytes, width: int, height: int, sprite_name: str, compressed_size: int
    ) -> None:
        """Handle preview ready."""
        if self.preview_widget is not None:
            self.preview_widget.load_sprite_from_4bpp(tile_data, width, height, sprite_name)

        current_offset = self.get_current_offset()
        self._update_status(f"Sprite found at 0x{current_offset:06X} (size: {compressed_size} bytes)")

    def _on_preview_error(self, error_msg: str) -> None:
        """Handle preview error."""
        # Don't clear the preview widget on errors - keep the last valid preview visible
        # This prevents black flashing when rapidly moving the slider
        if self.preview_widget is not None and self.preview_widget.info_label:
            self.preview_widget.info_label.setText("No sprite found")

        current_offset = self.get_current_offset()
        self._update_status(f"No sprite at 0x{current_offset:06X}")

    def _apply_offset(self) -> None:
        """Apply current offset and close dialog."""
        offset = self.get_current_offset()
        sprite_name = f"manual_0x{offset:X}"
        # Emit signal directly
        self.sprite_found.emit(offset, sprite_name)
        self.hide()

    def _update_status(self, message: str) -> None:
        """Update status message."""
        if self.status_panel is not None:
            self.status_panel.update_status(message)

            # Add cache performance tooltip if available
            tooltip = self._build_cache_tooltip()
            self.status_panel.detection_info.setToolTip(tooltip)

    def _has_rom_data(self) -> bool:
        """Check if ROM data is available."""
        return bool(self.rom_path and self.rom_size > 0)

    @override
    def _cleanup_workers(self) -> None:
        """Clean up worker threads."""
        WorkerManager.cleanup_worker_attr(self, "preview_worker", timeout=2000)

        # Search workers now managed by SpriteSearchCoordinator
        if self._search_coordinator is not None:
            self._search_coordinator.cleanup()

        if self._preview_timer is not None:
            self._preview_timer.stop()

        # Clean up preview coordinator (we always own it)
        if self._smart_preview_coordinator is not None:
            self._smart_preview_coordinator.cleanup()

        # Cleanup cache controller
        if self._cache_controller is not None:
            self._cache_controller.cleanup()

    def _block_child_widget_signals(self, block: bool) -> None:
        """Block or unblock signals on child widgets.

        Args:
            block: True to block signals, False to unblock
        """
        widgets: list[QWidget | None] = [
            self.browse_tab,
            self.smart_tab,
            self.history_tab,
            self.gallery_tab,
            self.preview_widget,
        ]
        for widget in widgets:
            if widget is not None and _is_valid_qt(widget):
                widget.blockSignals(block)

        # Also handle coordinator (not a QWidget but has blockSignals)
        if isinstance(self._smart_preview_coordinator, SmartPreviewCoordinator):
            self._smart_preview_coordinator.blockSignals(block)

    def cleanup(self) -> None:
        """Clean up resources to prevent memory leaks."""
        logger.debug(f"Cleaning up UnifiedManualOffsetDialog {self._debug_id}")

        # CRITICAL: Block signals FIRST to prevent race conditions
        # Workers may still emit signals during cleanup
        self.blockSignals(True)

        # Block signals on child widgets that might emit during cleanup
        self._block_child_widget_signals(True)

        # Stop and clean up workers BEFORE disconnecting signals
        # Workers are now blocked from emitting to this dialog
        self._cleanup_workers()

        # Now safe to disconnect signals (workers have stopped)
        # Disconnect tab signals using safe helper to avoid RuntimeWarning
        if self.browse_tab is not None and _is_valid_qt(self.browse_tab):
            _safe_disconnect(self.browse_tab.offset_changed)
            _safe_disconnect(self.browse_tab.find_next_clicked)
            _safe_disconnect(self.browse_tab.find_prev_clicked)
            _safe_disconnect(self.browse_tab.find_sprites_requested)

        if self.smart_tab is not None and _is_valid_qt(self.smart_tab):
            _safe_disconnect(self.smart_tab.smart_mode_changed)
            _safe_disconnect(self.smart_tab.region_changed)
            _safe_disconnect(self.smart_tab.offset_requested)

        if self.history_tab is not None and _is_valid_qt(self.history_tab):
            _safe_disconnect(self.history_tab.sprite_selected)

        if self.gallery_tab is not None and _is_valid_qt(self.gallery_tab):
            _safe_disconnect(self.gallery_tab.sprite_selected)

        # Disconnect preview widget signals
        if self.preview_widget is not None and _is_valid_qt(self.preview_widget):
            _safe_disconnect(self.preview_widget.similarity_search_requested)

        # Disconnect smart preview coordinator
        if isinstance(self._smart_preview_coordinator, SmartPreviewCoordinator):
            _safe_disconnect(self._smart_preview_coordinator.preview_ready)
            _safe_disconnect(self._smart_preview_coordinator.preview_cached)
            _safe_disconnect(self._smart_preview_coordinator.preview_error)

        # Clear references
        self.extraction_manager = None
        self.rom_extractor = None

        # Clean up cache controller
        if self._cache_controller is not None:
            self._cache_controller.cleanup()
            self._cache_controller = None

        # Clean up search coordinator
        if self._search_coordinator is not None:
            self._search_coordinator.cleanup()
            self._search_coordinator = None

        # Clean up bookmark manager
        if self._bookmark_manager:
            self._bookmark_manager.cleanup()
            self._bookmark_manager = None

        # Clear preview pixmaps
        if self.preview_widget is not None:
            self.preview_widget.clear()

        # Clear advanced search dialog reference
        if self._advanced_search_dialog is not None:
            self._advanced_search_dialog.close()
            self._advanced_search_dialog = None

    # Public interface methods required by ROM extraction panel

    def set_rom_data(self, rom_path: str, rom_size: int, extraction_manager: CoreOperationsManager) -> None:
        """Set ROM data for the dialog."""
        with QMutexLocker(self._manager_mutex):
            self.rom_path = rom_path
            self.rom_size = rom_size
            self.extraction_manager = extraction_manager
            self.rom_extractor = cast("ROMExtractor | None", extraction_manager.get_rom_extractor())

        # Update tabs with new ROM data
        if self.browse_tab is not None:
            self.browse_tab.set_rom_size(rom_size)
            self.browse_tab.set_rom_path(rom_path)

            # Set header offset and mapping type for accurate copy/paste
            if self.rom_extractor:
                try:
                    header = self.rom_extractor.read_rom_header(rom_path)
                    self.browse_tab.set_header_offset(header.header_offset)
                    self.browse_tab.set_mapping_type(header.mapping_type)
                except Exception as e:
                    logger.warning(f"Failed to read ROM header for offset config: {e}")

        # Update gallery tab with ROM data
        if self.gallery_tab is not None and self.rom_extractor is not None:
            self.gallery_tab.set_rom_data(rom_path, rom_size, self.rom_extractor)

        # Update mini ROM map
        if self.mini_rom_map is not None:
            self.mini_rom_map.set_rom_size(rom_size)

        # Update window title
        self.view_state_manager.update_title_with_rom(rom_path)

        # Update search coordinator with ROM data
        if self._search_coordinator is not None:
            self._search_coordinator.set_rom_data(rom_path, rom_size, self.rom_extractor)

        logger.debug(f"ROM data updated: {Path(rom_path).name} ({rom_size} bytes)")

        # Initialize cache for this ROM
        self._initialize_rom_cache(rom_path)

        # Update cache status display
        self._update_cache_status_display()

        # Load any cached sprites for visualization
        self._load_cached_sprites_for_map()

    def _scan_for_sprites(self) -> None:
        """Scan ROM for HAL-compressed sprites using a background worker."""
        if self._search_coordinator is not None:
            self._search_coordinator.scan_for_sprites()

    def _cancel_sprite_scan(self) -> None:
        """Cancel the sprite scan operation."""
        if self._search_coordinator is not None:
            self._search_coordinator.cancel_scan()

    # Note: _on_sprite_scan_progress, _on_sprite_scan_complete, _on_sprite_scan_error,
    # _show_sprite_scan_results, _jump_to_sprite, _jump_to_selected_sprite
    # are now handled internally by SpriteSearchCoordinator

    def _get_rom_data_for_preview(self) -> tuple[str, object] | None:
        """Provide ROM data for smart preview coordinator."""
        with QMutexLocker(self._manager_mutex):
            if not self.rom_path or not self.rom_extractor:
                return None
            return (self.rom_path, self.rom_extractor)

    def _on_smart_preview_ready(
        self,
        tile_data: bytes,
        width: int,
        height: int,
        sprite_name: str,
        compressed_size: int,
        slack_size: int = 0,
        actual_offset: int = -1,
        hal_succeeded: bool = True,
    ) -> None:
        """Handle preview ready from smart coordinator with guaranteed UI updates."""
        logger.info("[PREVIEW_READY] ========== START ===========")
        logger.info(
            f"[PREVIEW_READY] data_len={len(tile_data) if tile_data else 0}, {width}x{height}, name={sprite_name}, compressed_size={compressed_size}, actual_offset=0x{actual_offset:06X}"
        )
        logger.debug(f"[PREVIEW_READY] tile_data first 20 bytes: {tile_data[:20].hex() if tile_data else 'None'}")

        # CRITICAL: Verify we're on main thread before calling widget methods
        current_thread = QThread.currentThread()
        main_thread = get_main_thread()
        logger.debug(
            f"[THREAD_CHECK] Current thread: {current_thread}, Main thread: {main_thread}, Same: {current_thread == main_thread}"
        )

        if current_thread != main_thread:
            logger.error("[THREAD_SAFETY] _on_smart_preview_ready called from worker thread!")
            return

        if self.preview_widget is not None:
            logger.info("[PREVIEW_READY] Preview widget exists")
            logger.debug(f"[PREVIEW_READY] Preview widget type: {type(self.preview_widget)}")
            logger.debug(f"[PREVIEW_READY] Preview widget visible: {self.preview_widget.isVisible()}")

            # Use mutex to prevent concurrent preview updates
            logger.debug("[PREVIEW_READY] Acquiring mutex...")
            try:
                with QMutexLocker(self._preview_update_mutex):
                    logger.info("[PREVIEW_READY] Calling load_sprite_from_4bpp...")
                    self.preview_widget.load_sprite_from_4bpp(tile_data, width, height, sprite_name)
                    logger.info("[PREVIEW_READY] load_sprite_from_4bpp returned successfully")

                    # Force immediate widget update
                    logger.debug("[PREVIEW_READY] Calling widget.update()...")
                    self.preview_widget.update()
                    logger.debug("[PREVIEW_READY] widget.update() completed")
            except Exception as e:
                logger.exception(f"[PREVIEW_READY] EXCEPTION in preview update: {e}")
                raise

            logger.info("[PREVIEW_READY] Mutex released, updates completed")

            # Log pixmap state after loading for debugging
            try:
                if hasattr(self.preview_widget, "preview_label") and self.preview_widget.preview_label:
                    pixmap = self.preview_widget.preview_label.pixmap()
                    # QLabel.pixmap() always returns a QPixmap, check if it's null/empty instead
                    logger.info(f"[PREVIEW_READY] Final pixmap state: null={pixmap.isNull()}")
                    if not pixmap.isNull():
                        logger.debug(f"[PREVIEW_READY] Pixmap size: {pixmap.width()}x{pixmap.height()}")
            except Exception as e:
                logger.error(f"[PREVIEW_READY] Error checking pixmap state: {e}")
        else:
            logger.error("[PREVIEW_READY] preview_widget is None!")

        try:
            current_offset = self.get_current_offset()

            # Use actual_offset if provided and valid
            display_offset = actual_offset if actual_offset != -1 else current_offset

            # Sync browse tab if offset was adjusted during alignment
            if actual_offset not in (-1, current_offset):
                logger.info(f"[PREVIEW_READY] Offset adjusted from 0x{current_offset:06X} to 0x{actual_offset:06X}")
                self.set_offset(actual_offset)

            cache_status = self._get_cache_status_text()
            self._update_status(f"High-quality preview at 0x{display_offset:06X} {cache_status}")
        except Exception as e:
            logger.error(f"[PREVIEW_READY] Error updating status: {e}")

        logger.info("[PREVIEW_READY] ========== END ===========")

    def _on_smart_preview_cached(
        self, tile_data: bytes, width: int, height: int, sprite_name: str, compressed_size: int
    ) -> None:
        """Handle cached preview from smart coordinator."""
        logger.debug(
            f"[SIGNAL_RECEIVED] _on_smart_preview_cached called: data_len={len(tile_data) if tile_data else 0}, {width}x{height}, name={sprite_name}, compressed_size={compressed_size}"
        )
        logger.debug(
            f"[SIGNAL_RECEIVED] cached tile_data first 20 bytes: {tile_data[:20].hex() if tile_data else 'None'}"
        )

        # CRITICAL: Verify we're on main thread before calling widget methods
        if QThread.currentThread() != get_main_thread():
            logger.warning("[THREAD_SAFETY] _on_smart_preview_cached called from worker thread!")
            return

        if self.preview_widget is not None:
            logger.debug("[DEBUG] Calling preview_widget.load_sprite_from_4bpp (from cache)")

            # Use mutex to prevent concurrent preview updates
            with QMutexLocker(self._preview_update_mutex):
                self.preview_widget.load_sprite_from_4bpp(tile_data, width, height, sprite_name)

                # Force immediate widget update
                logger.debug("[SPRITE_DISPLAY] Forcing widget updates after cached load_sprite_from_4bpp")
                self.preview_widget.update()

            # Let Qt's event loop handle updates naturally
            # processEvents causes crashes and re-entrancy issues
        else:
            logger.error("[DEBUG] preview_widget is None!")

        try:
            current_offset = self.get_current_offset()
            cache_status = self._get_cache_status_text()
            self._update_status(f"Cached preview at 0x{current_offset:06X} {cache_status}")
        except Exception as e:
            logger.error(f"[PREVIEW_CACHED] Error updating status: {e}")

        logger.info("[PREVIEW_CACHED] ========== END ===========")

    def _on_smart_preview_error(self, error_msg: str) -> None:
        """Handle preview error from smart coordinator."""
        logger.warning("[PREVIEW_ERROR] ========== START ===========")
        logger.warning(f"[PREVIEW_ERROR] Error message: {error_msg}")

        # CRITICAL: Verify we're on main thread before calling widget methods
        current_thread = QThread.currentThread()
        main_thread = get_main_thread()
        logger.debug(
            f"[THREAD_CHECK] Current thread: {current_thread}, Main thread: {main_thread}, Same: {current_thread == main_thread}"
        )

        if current_thread != main_thread:
            logger.error("[THREAD_SAFETY] _on_smart_preview_error called from worker thread!")
            return

        if self.preview_widget is not None:
            logger.info("[PREVIEW_ERROR] Updating info label only (not clearing preview)")
            try:
                # Don't clear - keep last valid preview visible to prevent black flashing
                if self.preview_widget.info_label:
                    self.preview_widget.info_label.setText("No sprite found")

                # Force widget updates
                logger.debug("[PREVIEW_ERROR] Calling widget.update()...")
                self.preview_widget.update()
                self.preview_widget.repaint()
                logger.debug("[PREVIEW_ERROR] widget.update() completed")
            except Exception as e:
                logger.exception(f"[PREVIEW_ERROR] EXCEPTION updating widget: {e}")
        else:
            logger.error("[PREVIEW_ERROR] preview_widget is None!")

        logger.warning("[PREVIEW_ERROR] ========== END ===========")

        current_offset = self.get_current_offset()
        self._update_status(f"No sprite at 0x{current_offset:06X}: {error_msg}")

    def set_offset(self, offset: int) -> bool:
        """Set current offset."""
        logger.debug("ManualOffsetDialog.set_offset called: 0x%06X", offset)
        if self.browse_tab is not None:
            self.browse_tab.set_offset(offset)
            # The browse_tab.set_offset now emits offset_changed signal
            # No need to manually call _on_offset_changed to avoid duplicates
            return True
        return False

    def get_current_offset(self) -> int:
        """Get current offset."""
        if self.browse_tab is not None:
            return self.browse_tab.get_current_offset()
        return ROM_SIZE_2MB

    def add_found_sprite(self, offset: int, quality: float = 1.0) -> None:
        """Add found sprite to history."""
        if self.history_tab is not None:
            self.history_tab.add_sprite(offset, quality)

            # Update tab title with count
            count = self.history_tab.get_sprite_count()
            if self.tab_widget is not None:
                self.tab_widget.setTabText(2, f"History ({count})")

    # ROM Cache Integration Methods

    def _initialize_rom_cache(self, rom_path: str) -> None:
        """Initialize ROM cache for the current ROM."""
        if self._cache_controller is not None:
            self._cache_controller.initialize_for_rom(rom_path)

    def _schedule_adjacent_preloading(self, current_offset: int) -> None:
        """Schedule preloading of adjacent offsets for smooth navigation."""
        if not self.rom_cache.cache_enabled or self._cache_controller is None:
            return

        try:
            # Calculate adjacent offsets based on typical step sizes
            step_sizes = [0x100, 0x1000, 0x2000]  # Common alignment boundaries
            adjacent_offsets_to_preload = []
            cached_offsets = self._cache_controller.adjacent_offsets_cache

            for step in step_sizes:
                # Previous and next offsets
                prev_offset = max(0, current_offset - step)
                next_offset = min(self.rom_size, current_offset + step)

                # Only preload if not already cached
                if prev_offset not in cached_offsets:
                    adjacent_offsets_to_preload.append(prev_offset)
                if next_offset not in cached_offsets:
                    adjacent_offsets_to_preload.append(next_offset)

            # Limit preloading to avoid overwhelming the system
            adjacent_offsets_to_preload = adjacent_offsets_to_preload[:6]  # Max 6 adjacent offsets

            # Schedule preloading with low priority
            for offset in adjacent_offsets_to_preload:
                self._preload_offset(offset)
                cached_offsets.add(offset)

        except Exception as e:
            logger.debug(f"Error scheduling adjacent preloading: {e}")

    def _preload_offset(self, offset: int) -> None:
        """Preload a specific offset using the worker pool."""
        if not self._smart_preview_coordinator:
            return

        # Check if we have ROM data available
        rom_data = self._get_rom_data_for_preview()
        if not rom_data or not rom_data[0]:  # No ROM path available
            return

        try:
            # Use background preload to avoid updating current offset
            self._smart_preview_coordinator.request_background_preload(offset)

        except Exception as e:
            logger.debug(f"Error preloading offset 0x{offset:06X}: {e}")

    def _on_cache_hit(self, *args: object) -> None:
        """Handle cache hit event."""
        if self._cache_controller is not None:
            self._cache_controller.record_cache_hit()

    def _on_cache_miss(self, *args: object) -> None:
        """Handle cache miss event."""
        if self._cache_controller is not None:
            self._cache_controller.record_cache_miss()

    def _get_cache_status_text(self) -> str:
        """Get cache status text for display."""
        if self._cache_controller is not None:
            return self._cache_controller.get_status_text()
        return "[Cache: Disabled]"

    def _build_cache_tooltip(self) -> str:
        """Build detailed cache tooltip."""
        if self._cache_controller is not None:
            return self._cache_controller.build_tooltip()
        return "ROM caching is disabled"

    def _update_cache_status_display(self) -> None:
        """Update cache status in the UI."""
        if self._cache_controller is not None:
            self._cache_controller.update_status_display()

    def _setup_cache_context_menu(self) -> None:
        """Set up context menu for cache management."""
        if self._cache_controller is not None and self.status_collapsible is not None:
            self._cache_controller.set_status_widget(self.status_collapsible)

    def _show_cache_context_menu(self, position: QPoint) -> None:
        """Show cache management context menu."""
        # Delegated to cache controller via set_status_widget connection
        pass

    def _show_cache_statistics(self) -> None:
        """Show detailed cache statistics dialog."""
        if self._cache_controller is not None:
            self._cache_controller.show_statistics_dialog()

    def _clear_cache_with_confirmation(self) -> None:
        """Clear cache with user confirmation."""
        if self._cache_controller is not None:
            self._cache_controller.clear_with_confirmation()

    # Event handlers

    @override
    def keyPressEvent(self, event: QKeyEvent | None) -> None:
        """Handle keyboard shortcuts."""
        if event:
            if event.key() == Qt.Key.Key_Escape:
                if self.view_state_manager.handle_escape_key():
                    event.accept()
                else:
                    self.hide()
                    event.accept()
            elif event.key() == Qt.Key.Key_F11:
                self.view_state_manager.toggle_fullscreen()
                event.accept()
            elif event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                self._apply_offset()
                event.accept()
            elif event.key() == Qt.Key.Key_G and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
                # Ctrl+G - Go to offset
                self._show_goto_dialog()
                event.accept()
            elif event.key() == Qt.Key.Key_D and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
                # Ctrl+D - Add bookmark
                if self._bookmark_manager:
                    self._bookmark_manager.add_bookmark(self.get_current_offset())
                event.accept()
            elif event.key() == Qt.Key.Key_B and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
                # Ctrl+B - Show bookmarks menu
                if self._bookmark_manager:
                    menu = self._bookmark_manager.create_menu()
                    menu.exec(self.mapToGlobal(self.rect().center()))
                event.accept()

        if event is not None:
            super().keyPressEvent(event)

    @override
    def closeEvent(self, event: QCloseEvent | None) -> None:
        """Handle close event."""
        logger.debug(f"Dialog {self._debug_id} closing")
        self.cleanup()
        if event:
            super().closeEvent(event)

    @override
    def hideEvent(self, event: QHideEvent | None) -> None:
        """Handle hide event."""
        logger.debug(f"Dialog {self._debug_id} hiding")
        # Only cleanup workers on hide, not full cleanup (dialog may be shown again)
        self._cleanup_workers()
        self.view_state_manager.handle_hide_event()
        if event:
            super().hideEvent(event)

    @override
    def showEvent(self, event: QShowEvent) -> None:
        """Handle show event - set up initial splitter sizes here."""
        logger.debug(f"Dialog {self._debug_id} showing")
        super().showEvent(event)
        self.view_state_manager.handle_show_event()

    @override
    def resizeEvent(self, event: QResizeEvent) -> None:
        """Handle resize event."""
        super().resizeEvent(event)

    @override
    def moveEvent(self, event: QMoveEvent) -> None:
        """Handle dialog move event - constrain to screen bounds."""
        super().moveEvent(event)

        if not self.isVisible():
            return

        try:
            self._constrain_to_screen_bounds(event.pos())
        except (AttributeError, TypeError):
            # Skip validation if event/geometry objects are mocks
            pass

    def _constrain_to_screen_bounds(self, pos: QPoint) -> None:
        """Constrain dialog position to screen bounds."""
        from PySide6.QtGui import QGuiApplication

        screen = QGuiApplication.primaryScreen()
        if not screen:
            return

        available = screen.availableGeometry()
        x, y = pos.x(), pos.y()
        margin = 50

        min_x = available.x() - self.width() + margin
        max_x = available.x() + available.width() - margin
        min_y = available.y() - self.height() + margin
        max_y = available.y() + available.height() - margin

        constrained_x = max(min_x, min(x, max_x))
        constrained_y = max(min_y, min(y, max_y))

        if constrained_x != x or constrained_y != y:
            self.move(constrained_x, constrained_y)

    def _on_search_sprite_found(self, offset: int, quality: float) -> None:
        """Handle sprite found during navigation search"""
        if self.browse_tab is not None:
            self.browse_tab.set_offset(offset)

        # Add to history
        self.add_found_sprite(offset, quality)

        self._update_status(f"Found sprite at 0x{offset:06X} (quality: {quality:.2f})")

    def _on_search_complete(self, found: bool) -> None:
        """Handle search completion"""
        if not found:
            self._update_status("No sprites found in search direction")

    # Bookmark methods have been extracted to BookmarkManager
    # See: ui/dialogs/services/bookmark_manager.py

    def _on_similarity_search_requested(self, target_offset: int) -> None:
        """Handle similarity search request from preview widget."""
        logger.info(f"Similarity search requested for offset 0x{target_offset:06X}")

        # Navigate to the selected similar sprite
        self.set_offset(target_offset)
        self._update_status(f"Navigated to similar sprite at 0x{target_offset:06X}")

    def _show_goto_dialog(self) -> None:
        """Show go to offset dialog.

        Supports multiple address formats:
        - SNES bank:offset: $98:8000 or 98:8000 (auto-converted to file offset)
        - SNES combined: $988000
        - Hex: 0x0C3000 or 0C3000
        - Decimal: 123456
        """
        current = self.get_current_offset()
        text, ok = QInputDialog.getText(
            self,
            "Go to Offset",
            "Enter offset (hex, decimal, or SNES $bank:addr):",
            text=f"0x{current:06X}",
        )

        if ok and text:
            try:
                # Parse address in various formats
                raw_value, fmt = parse_address_string(text)

                # Normalize SNES addresses to file offsets
                offset = normalize_address(raw_value, self.rom_size)

                # Show conversion feedback for SNES addresses
                if fmt.startswith("snes"):
                    self._update_status(f"SNES ${raw_value:06X} → File 0x{offset:06X}")

                # Validate bounds (offset must be < rom_size since 0-indexed)
                if 0 <= offset < self.rom_size:
                    self.set_offset(offset)
                else:
                    self._update_status(f"Offset out of range: 0x{offset:06X}")
            except ValueError as e:
                self._update_status(f"Invalid offset: {e}")

    def _load_cached_sprites_for_map(self) -> None:
        """Load cached sprites for mini ROM map visualization"""
        if not self.rom_path or not self.mini_rom_map:
            return

        try:
            cached_locations = self.rom_cache.get_sprite_locations(self.rom_path)
            if cached_locations:
                sprites = []
                for info in cached_locations.values():
                    if isinstance(info, dict) and "offset" in info:
                        offset = info["offset"]
                        quality = info.get("quality", 1.0)
                        sprites.append((offset, quality))

                if sprites:
                    self.mini_rom_map.add_found_sprites_batch(sprites)
                    logger.debug(f"Loaded {len(sprites)} sprites to mini map")

        except Exception as e:
            logger.warning(f"Failed to load sprites for mini map: {e}")
