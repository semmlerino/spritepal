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
from functools import partial
from pathlib import Path
from typing import TYPE_CHECKING, Any

with contextlib.suppress(ImportError):
    pass

if TYPE_CHECKING:
    from core.protocols.manager_protocols import (
        ExtractionManagerProtocol,
        ROMCacheProtocol,
        ROMExtractorProtocol,
        SettingsManagerProtocol,
    )

from PySide6.QtCore import (
    QEventLoop,
    QMutex,
    QMutexLocker,
    Qt,
    QThread,
    QTimer,
    Signal,
)

if TYPE_CHECKING:
    from PySide6.QtGui import QAction, QCloseEvent, QHideEvent, QKeyEvent
else:
    from PySide6.QtGui import QAction, QCloseEvent, QHideEvent, QKeyEvent
# Preview coordinator selection - SmartPreviewCoordinator re-enabled after signal lifecycle fixes
# Set SPRITEPAL_USE_SIMPLE_PREVIEW=1 to fall back to SimplePreviewCoordinator if issues occur
import os

from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QProgressDialog,
    QPushButton,
    QSizePolicy,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from core.sprite_finder import SpriteFinder
from ui.common import WorkerManager
from ui.common.collapsible_group_box import CollapsibleGroupBox

_use_simple_preview = os.environ.get('SPRITEPAL_USE_SIMPLE_PREVIEW', '0').lower() in ('1', 'true', 'yes')

if _use_simple_preview:
    from ui.common.simple_preview_coordinator import SimplePreviewCoordinator as PreviewCoordinator
else:
    from ui.common.smart_preview_coordinator import SmartPreviewCoordinator as PreviewCoordinator


def get_main_thread():
    """Get main thread safely."""
    app = QApplication.instance()
    return app.thread() if app else None

# Smart DialogBase selection based on environment
def _get_dialog_base_class():
    """Get the appropriate DialogBase class based on environment settings."""
    import os

    flag_value = os.environ.get('SPRITEPAL_USE_COMPOSED_DIALOGS', '0').lower()
    use_composed = flag_value in ('1', 'true', 'yes', 'on')


    if use_composed:
        try:
            from ui.components.base.composed.migration_adapter import (
                DialogBaseMigrationAdapter,
            )
            return DialogBaseMigrationAdapter
        except Exception:
            # Fallback to legacy on any import error
            from ui.components import DialogBase
            return DialogBase
    else:
        from ui.components import DialogBase
        return DialogBase

DialogBase = _get_dialog_base_class()
from ui.components.panels import StatusPanel
from ui.components.visualization.rom_map_widget import ROMMapWidget
from ui.dialogs.services import ViewStateManager
from ui.rom_extraction.workers import SpritePreviewWorker, SpriteSearchWorker
from ui.tabs.sprite_gallery_tab import SpriteGalleryTab
from ui.widgets.sprite_preview_widget import SpritePreviewWidget
from utils.logging_config import get_logger

# from utils.rom_cache import get_rom_cache # Removed due to DI

logger = get_logger(__name__)

# Import tab widgets from the new module
from ui.tabs.manual_offset import SimpleBrowseTab, SimpleHistoryTab, SimpleSmartTab

# SmartPreviewCoordinator re-enabled with signal lifecycle fixes (QueuedConnection, blockSignals)

# SimpleBrowseTab, SimpleSmartTab, SimpleHistoryTab removed - now imported from ui.tabs.manual_offset

class UnifiedManualOffsetDialog(DialogBase):  # type: ignore[misc]
    """
    Unified Manual Offset Dialog combining simplified architecture with tab-based navigation.

    This dialog consolidates functionality from the archived simplified dialog while
    providing a clean, working interface with proper signal coordination.
    Now accepts injected dependencies for ROM cache, settings, and managers.
    """

    # Define signals directly on the dialog for compatibility
    offset_changed = Signal(int)  # Emitted when offset changes
    sprite_found = Signal(int, str)  # Emitted when sprite is found (offset, name)

    def __init__(self, parent: QWidget | None = None,
                 rom_cache: ROMCacheProtocol | None = None,
                 settings_manager: SettingsManagerProtocol | None = None,
                 extraction_manager: ExtractionManagerProtocol | None = None,
                 rom_extractor: ROMExtractorProtocol | None = None) -> None:
        # Debug logging for singleton tracking
        logger.debug(f"Creating UnifiedManualOffsetDialog instance (parent: {parent.__class__.__name__ if parent else 'None'})")

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
        self.bookmarks_menu: QMenu | None = None
        self.bookmarks: list[tuple[int, str]] = []  # (offset, name) pairs

        # Business logic state
        self.rom_path: str = ""
        self.rom_size: int = 0x400000

        # Manager references with thread safety
        self._manager_mutex = QMutex()
        self._preview_update_mutex = QMutex()  # Mutex for serializing preview widget updates

        # Inject dependencies or use fallbacks
        if extraction_manager is None:
            from core.di_container import inject
            from core.protocols.manager_protocols import ExtractionManagerProtocol
            self.extraction_manager = inject(ExtractionManagerProtocol)
        else:
            self.extraction_manager = extraction_manager

        # rom_extractor can be obtained from extraction_manager
        if rom_extractor is None:
            self.rom_extractor = self.extraction_manager.get_rom_extractor()
        else:
            self.rom_extractor = rom_extractor

        if rom_cache is None:
            from core.di_container import inject
            from core.protocols.manager_protocols import ROMCacheProtocol
            self.rom_cache = inject(ROMCacheProtocol)
        else:
            self.rom_cache = rom_cache

        if settings_manager is None:
            from core.di_container import inject
            from core.protocols.manager_protocols import SettingsManagerProtocol
            self.settings_manager = inject(SettingsManagerProtocol)
        else:
            self.settings_manager = settings_manager

        self._cache_stats = {"hits": 0, "misses": 0, "total_requests": 0}
        self._adjacent_offsets_cache = set()  # Track preloaded offsets

        # Worker references
        self.preview_worker: SpritePreviewWorker | None = None
        self.search_worker: SpriteSearchWorker | None = None

        # Preview coordinator handles preview generation (Smart or Simple based on env flag)
        self._smart_preview_coordinator: PreviewCoordinator | None = None

        # Preview update timer (legacy - kept for compatibility)
        self._preview_timer: QTimer | None = None

        # Debug ID for tracking
        self._debug_id = f"dialog_{int(time.time()*1000)}"
        logger.debug(f"Dialog debug ID: {self._debug_id}")

        # TEMPORARILY DISABLE LayoutManagerComponent to isolate the issue

        # Create minimal fallback object to prevent attribute errors
        class MinimalLayoutManager:
            MAX_MINI_MAP_HEIGHT = 60
            MIN_MINI_MAP_HEIGHT = 40
            def configure_splitter(self, *args: Any) -> None: pass
            def fix_empty_space_issue(self) -> None: pass
            def apply_standard_layout(self, layout: Any, spacing_type: str = 'normal') -> None:
                layout.setSpacing(8)
                layout.setContentsMargins(8, 8, 8, 8)
            def remove_all_stretches(self, layout: Any) -> None: pass
            def create_section_title(self, title: str, subtitle: str = "") -> Any:
                from PySide6.QtWidgets import QLabel
                label = QLabel(title)
                label.setStyleSheet("font-weight: bold; font-size: 12px; color: #333;")
                return label
            def on_dialog_show(self) -> None: pass
            def update_for_tab(self, index: int, width: int) -> None: pass
            def handle_resize(self, event: Any) -> None: pass  # Add missing method

        self.layout_manager = MinimalLayoutManager()
        logger.debug("Using minimal layout manager for debugging")

        super().__init__(
            parent=parent,
            title="Manual Offset Control - SpritePal",
            modal=False,
            size=(900, 600),  # More compact size
            min_size=(800, 500),  # Smaller minimum
            with_status_bar=False,
            orientation=Qt.Orientation.Horizontal,
            splitter_handle_width=8  # Thinner splitter handle
        )

        # Initialize view state manager with injected settings_manager
        self.view_state_manager = ViewStateManager(self, self, settings_manager=self.settings_manager)

        # Note: _setup_ui() is called by DialogBase.__init__() automatically
        self._setup_smart_preview_coordinator()
        self._setup_preview_timer()
        self._connect_signals()

        # DialogSignalManager handles custom signals to avoid Qt metaclass issues


    def __del__(self):
        """Destructor for tracking dialog destruction."""
        with contextlib.suppress(BaseException):
            logger.debug(f"Dialog {self._debug_id} being destroyed")

    def _setup_ui(self) -> None:
        """Set up the dialog UI."""
        try:
            logger.debug("Starting _setup_ui")

            # Create left and right panels
            left_panel = self._create_left_panel()
            right_panel = self._create_right_panel()

            # Use layout manager to configure splitter (if available)
            if self.layout_manager and hasattr(self, 'main_splitter') and self.main_splitter:
                self.layout_manager.configure_splitter(self.main_splitter, left_panel, right_panel)
            else:
                logger.debug("Main splitter not available during setup, panels will be added directly")

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

        # Connect tab change signal for dynamic sizing
        if self.tab_widget:
            self.tab_widget.currentChanged.connect(self._on_tab_changed)

        # Fix empty space issue after everything is set up
        if self.layout_manager:
            self.layout_manager.fix_empty_space_issue()

    def _create_left_panel(self) -> QWidget:
        """Create the left panel with tabs and collapsible status."""
        panel = QWidget()
        layout = QVBoxLayout(panel)

        # Use layout manager to apply standard layout configuration
        if self.layout_manager:
            self.layout_manager.apply_standard_layout(layout, spacing_type='compact')

        # Tab widget - will be configured by layout manager
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
        self.status_panel = StatusPanel()
        self.status_collapsible.add_widget(self.status_panel)

        # Add context menu for cache management
        self._setup_cache_context_menu()

        layout.addWidget(self.status_collapsible, 0)  # No stretch - fixed size

        # Mini ROM map for position context with flexible height
        self.mini_rom_map = ROMMapWidget()
        self.mini_rom_map.setMaximumHeight(self.layout_manager.MAX_MINI_MAP_HEIGHT)
        self.mini_rom_map.setMinimumHeight(self.layout_manager.MIN_MINI_MAP_HEIGHT)
        self.mini_rom_map.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        layout.addWidget(self.mini_rom_map, 0)  # No stretch - fixed height

        # Use layout manager to ensure no unwanted stretches
        self.layout_manager.remove_all_stretches(layout)
        # The tab widget with stretch=1 will expand to fill available space

        return panel

    def _create_right_panel(self) -> QWidget:
        """Create the right panel with preview."""
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setSpacing(8)
        layout.setContentsMargins(12, 12, 12, 12)

        # Title with better styling
        title = QLabel("Sprite Preview")
        title.setStyleSheet("font-size: 14px; font-weight: bold; color: #4488dd;")
        layout.addWidget(title, 0)  # No stretch for title

        # Preview widget with frame for better visibility
        preview_frame = QFrame()
        preview_frame.setFrameStyle(QFrame.Shape.StyledPanel)
        preview_frame.setStyleSheet("""
            QFrame {
                background-color: #2b2b2b;
                border: 1px solid #3c3c3c;
                border-radius: 6px;
            }
        """)
        preview_layout = QVBoxLayout(preview_frame)
        preview_layout.setContentsMargins(8, 8, 8, 8)

        # Preview widget configured to expand within frame
        self.preview_widget = SpritePreviewWidget()
        self.preview_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.preview_widget.similarity_search_requested.connect(self._on_similarity_search_requested)
        preview_layout.addWidget(self.preview_widget)

        layout.addWidget(preview_frame, 1)  # Give frame all the stretch

        # No controls section needed - preview widget handles its own controls

        return panel

    def _setup_custom_buttons(self):
        """Set up custom dialog buttons with improved layout."""
        # Clear default buttons and create a more organized button layout
        if self.button_box:
            self.button_box.clear()

        # Primary action buttons (left side)
        self.apply_btn = QPushButton("Apply Offset")
        self.apply_btn.setToolTip("Apply the current offset to the extraction")
        self.apply_btn.clicked.connect(self._apply_offset)
        self.button_box.addButton(self.apply_btn, self.button_box.ButtonRole.AcceptRole)

        # Bookmark management buttons (center)
        bookmark_btn = QPushButton("Add Bookmark")
        bookmark_btn.setToolTip("Save current offset to bookmarks (Ctrl+D)")
        bookmark_btn.clicked.connect(self._add_bookmark)
        self.button_box.addButton(bookmark_btn, self.button_box.ButtonRole.ActionRole)

        bookmarks_menu_btn = QPushButton("Bookmarks ▼")
        bookmarks_menu_btn.setToolTip("Show saved bookmarks (Ctrl+B)")
        self.bookmarks_menu = QMenu(self)
        self._update_bookmarks_menu()
        bookmarks_menu_btn.setMenu(self.bookmarks_menu)
        self.button_box.addButton(bookmarks_menu_btn, self.button_box.ButtonRole.ActionRole)

        # Standard dialog buttons (right side)
        close_btn = QPushButton("Close")
        close_btn.setToolTip("Close this dialog")
        close_btn.clicked.connect(self.hide)
        self.button_box.addButton(close_btn, self.button_box.ButtonRole.RejectRole)

        # Apply consistent spacing to button box
        if self.button_box:
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

    # _setup_signal_coordinator removed - SmartPreviewCoordinator handles all coordination

    def _setup_smart_preview_coordinator(self):
        """Set up preview coordination (Smart or Simple based on env flag)."""
        self._smart_preview_coordinator = PreviewCoordinator(self, rom_cache=self.rom_cache)  # type: ignore[arg-type]

        # Use AutoConnection (default) to let Qt choose the best connection type
        # This will use DirectConnection when called from main thread (avoiding queue delays)
        # and QueuedConnection when called from worker threads (for thread safety)
        self._smart_preview_coordinator.preview_ready.connect(
            self._on_smart_preview_ready
        )
        self._smart_preview_coordinator.preview_cached.connect(
            self._on_smart_preview_cached
        )
        self._smart_preview_coordinator.preview_error.connect(
            self._on_smart_preview_error
        )

        # Setup ROM data provider with cache support
        self._smart_preview_coordinator.set_rom_data_provider(self._get_rom_data_for_preview)

        # Connect cache-related signals
        self._smart_preview_coordinator.preview_ready.connect(self._on_cache_miss)
        self._smart_preview_coordinator.preview_cached.connect(self._on_cache_hit)

        logger.debug("Smart preview coordinator setup complete with ROM cache integration")

    def _setup_preview_timer(self):
        """Set up preview update timer."""
        self._preview_timer = QTimer(self)
        self._preview_timer.setSingleShot(True)
        self._preview_timer.timeout.connect(self._update_preview)

    def _connect_signals(self):
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
            self.browse_tab.connect_smart_preview_coordinator(self._smart_preview_coordinator)  # type: ignore[arg-type]

        # Smart tab signals
        self.smart_tab.smart_mode_changed.connect(self._on_smart_mode_changed)
        self.smart_tab.region_changed.connect(self._on_region_changed)
        self.smart_tab.offset_requested.connect(self._on_offset_requested)

        # History tab signals
        self.history_tab.sprite_selected.connect(self._on_sprite_selected)

        # Gallery tab signals
        self.gallery_tab.sprite_selected.connect(self._on_gallery_sprite_selected)

    def _on_offset_changed(self, offset: int):
        """Handle offset changes from browse tab."""
        # CRITICAL: Prevent re-entrant calls for the same offset
        # This prevents crashes from duplicate signals
        if hasattr(self, '_last_offset_processed') and self._last_offset_processed == offset:
            logger.debug(f"[OFFSET_CHANGED] Skipping duplicate offset: 0x{offset:06X}")
            return

        logger.info(f"[OFFSET_CHANGED] ========== START: 0x{offset:06X} ===========")
        self._last_offset_processed = offset

        # Update cache stats
        self._cache_stats["total_requests"] += 1
        logger.debug(f"[OFFSET_CHANGED] Cache stats updated: total_requests={self._cache_stats['total_requests']}")

        # Update mini ROM map
        if self.mini_rom_map is not None:
            self.mini_rom_map.set_current_offset(offset)
            logger.debug(f"[OFFSET_CHANGED] Updated mini ROM map to offset: 0x{offset:06X}")

        # Update preview widget with current offset for similarity search
        if self.preview_widget is not None:
            self.preview_widget.set_current_offset(offset)
            logger.debug("[OFFSET_CHANGED] Updated preview widget offset")

        # Emit signal immediately for external listeners (with robust safety checks)
        try:
            # Check if dialog and signal are still valid before emitting
            if not hasattr(self, 'offset_changed'):
                logger.warning("[OFFSET_CHANGED] Signal attribute missing, skipping emit")
                return

            # Check if the underlying Qt object is still valid
            try:
                # Additional check for Qt object validity
                if hasattr(self, 'isWidgetType') and not self.isWidgetType():
                    logger.warning("[OFFSET_CHANGED] Dialog widget type invalid, skipping emit")
                    return

            except Exception as validity_check_error:
                logger.warning(f"[OFFSET_CHANGED] Validity check failed: {validity_check_error}, skipping emit")
                return

            logger.debug(f"[OFFSET_CHANGED] About to emit offset_changed signal for offset 0x{offset:06X}")

            # Emit signal with additional safety wrapper
            self.offset_changed.emit(offset)
            logger.debug("[OFFSET_CHANGED] Successfully emitted offset_changed signal")
        except RuntimeError as e:
            if "Signal source has been deleted" in str(e) or "deleted" in str(e).lower():
                logger.error(f"[OFFSET_CHANGED] CRITICAL: Signal source deleted during emit: {e}")
                logger.error(f"[OFFSET_CHANGED] Dialog state - type: {type(self)}")
                logger.warning("[OFFSET_CHANGED] Skipping signal emit to prevent crash")
            else:
                logger.error(f"[OFFSET_CHANGED] Unexpected RuntimeError during signal emit: {e}")
                raise
        except Exception as e:
            logger.error(f"[OFFSET_CHANGED] Unexpected error during signal emit: {e}")
            # Don't re-raise to prevent crashes, just log the error

        # CRITICAL FIX: Request preview when offset changes!
        # Use request_manual_preview for immediate response without debounce
        if self._smart_preview_coordinator is not None:
            logger.info(f"[OFFSET_CHANGED] Requesting manual preview for offset 0x{offset:06X}")
            try:
                self._smart_preview_coordinator.request_manual_preview(offset)
                logger.info("[OFFSET_CHANGED] request_manual_preview() returned successfully")
            except Exception as e:
                logger.exception(f"[OFFSET_CHANGED] EXCEPTION calling request_manual_preview: {e}")
        else:
            logger.error("[OFFSET_CHANGED] No smart preview coordinator available!")

        # Schedule predictive preloading for adjacent offsets
        self._schedule_adjacent_preloading(offset)

        logger.info(f"[OFFSET_CHANGED] ========== END: 0x{offset:06X} ===========")

    def _on_offset_requested(self, offset: int):
        """Handle offset request from smart tab."""
        if self.browse_tab is not None:
            self.browse_tab.set_offset(offset)

    def _on_sprite_selected(self, offset: int):
        """Handle sprite selection from history."""
        if self.browse_tab is not None:
            self.browse_tab.set_offset(offset)
        # Switch to browse tab
        if self.tab_widget is not None:
            self.tab_widget.setCurrentIndex(0)

    def _on_gallery_sprite_selected(self, offset: int):
        """Handle sprite selection from gallery - navigate to selected sprite."""
        if self.browse_tab is not None:
            self.browse_tab.set_offset(offset)
        # Switch to browse tab to show the selected sprite
        if self.tab_widget is not None:
            self.tab_widget.setCurrentIndex(0)

    def _on_smart_mode_changed(self, enabled: bool):
        """Handle smart mode toggle."""
        # Could implement smart mode behavior here

    def _on_region_changed(self, region_index: int):
        """Handle region change."""
        # Could implement region-specific behavior here

    def _find_next_sprite(self):
        """Find next sprite with region awareness."""
        if not self.browse_tab or not self._has_rom_data():
            return

        current_offset = self.browse_tab.get_current_offset()

        # Clean up existing search worker
        if self.search_worker is not None:
            WorkerManager.cleanup_worker(self.search_worker)
            self.search_worker = None

        # Create search worker for forward search
        with QMutexLocker(self._manager_mutex):
            if self.rom_extractor is not None:
                self.search_worker = SpriteSearchWorker(
                    self.rom_path,
                    current_offset,
                    self.rom_size,
                    1,  # Forward direction
                    self.rom_extractor,
                    parent=self
                )
                self.search_worker.sprite_found.connect(self._on_search_sprite_found)
                self.search_worker.search_complete.connect(self._on_search_complete)
                self.search_worker.start()

                self._update_status("Searching for next sprite...")

    def _find_prev_sprite(self):
        """Find previous sprite with region awareness."""
        if not self.browse_tab or not self._has_rom_data():
            return

        current_offset = self.browse_tab.get_current_offset()

        # Clean up existing search worker
        if self.search_worker is not None:
            WorkerManager.cleanup_worker(self.search_worker)
            self.search_worker = None

        # Create search worker for backward search
        with QMutexLocker(self._manager_mutex):
            if self.rom_extractor is not None:
                self.search_worker = SpriteSearchWorker(
                    self.rom_path,
                    current_offset,
                    0,  # Search back to start
                    -1,  # Backward direction
                    self.rom_extractor,
                    parent=self
                )
                self.search_worker.sprite_found.connect(self._on_search_sprite_found)
                self.search_worker.search_complete.connect(self._on_search_complete)
                self.search_worker.start()

                self._update_status("Searching for previous sprite...")

    def _request_preview_update(self, delay_ms: int = 100):
        """Request preview update with debouncing."""
        if self._preview_timer is not None:
            self._preview_timer.stop()
            self._preview_timer.start(delay_ms)

    def _update_preview(self):
        """Update sprite preview."""
        if not self._has_rom_data() or self.browse_tab is None:
            return

        current_offset = self.browse_tab.get_current_offset()
        self._update_status(f"Loading preview for 0x{current_offset:06X}...")

        # Clean up existing preview worker
        if self.preview_worker is not None:
            WorkerManager.cleanup_worker(self.preview_worker, timeout=1000)
            self.preview_worker = None

        # Create new preview worker
        with QMutexLocker(self._manager_mutex):
            if self.rom_extractor is not None:
                sprite_name = f"manual_0x{current_offset:X}"
                self.preview_worker = SpritePreviewWorker(
                    self.rom_path, current_offset, sprite_name, self.rom_extractor, None, parent=self
                )
                self.preview_worker.preview_ready.connect(self._on_preview_ready)
                self.preview_worker.preview_error.connect(self._on_preview_error)
                self.preview_worker.start()

    def _on_preview_ready(self, tile_data: bytes, width: int, height: int, sprite_name: str):
        """Handle preview ready."""
        if self.preview_widget is not None:
            self.preview_widget.load_sprite_from_4bpp(tile_data, width, height, sprite_name)

        current_offset = self.get_current_offset()
        self._update_status(f"Sprite found at 0x{current_offset:06X}")

    def _on_preview_error(self, error_msg: str):
        """Handle preview error."""
        # Don't clear the preview widget on errors - keep the last valid preview visible
        # This prevents black flashing when rapidly moving the slider
        if self.preview_widget is not None and self.preview_widget.info_label:
            self.preview_widget.info_label.setText("No sprite found")

        current_offset = self.get_current_offset()
        self._update_status(f"No sprite at 0x{current_offset:06X}")

    def _apply_offset(self):
        """Apply current offset and close dialog."""
        offset = self.get_current_offset()
        sprite_name = f"manual_0x{offset:X}"
        # Emit signal directly
        self.sprite_found.emit(offset, sprite_name)
        self.hide()

    def _update_status(self, message: str):
        """Update status message."""
        if self.status_panel is not None:
            self.status_panel.update_status(message)

            # Add cache performance tooltip if available
            if hasattr(self.status_panel, "status_label"):
                tooltip = self._build_cache_tooltip()
                self.status_panel.status_label.setToolTip(tooltip)  # type: ignore[attr-defined]

    def _has_rom_data(self) -> bool:
        """Check if ROM data is available."""
        return bool(self.rom_path and self.rom_size > 0)

    def _cleanup_workers(self):
        """Clean up worker threads."""
        WorkerManager.cleanup_worker(self.preview_worker, timeout=2000)
        self.preview_worker = None

        WorkerManager.cleanup_worker(self.search_worker, timeout=2000)
        self.search_worker = None

        if self._preview_timer is not None:
            self._preview_timer.stop()

        # Signal coordinator cleanup handled by SmartPreviewCoordinator

        if self._smart_preview_coordinator is not None:
            self._smart_preview_coordinator.cleanup()

        # Reset cache stats
        self._cache_stats = {"hits": 0, "misses": 0, "total_requests": 0}
        if self._adjacent_offsets_cache:
            self._adjacent_offsets_cache.clear()

    def cleanup(self):
        """Clean up resources to prevent memory leaks."""
        logger.debug(f"Cleaning up UnifiedManualOffsetDialog {self._debug_id}")

        # Disconnect signals
        try:
            # Disconnect tab signals
            if self.browse_tab is not None:
                self.browse_tab.offset_changed.disconnect()
                self.browse_tab.find_next_clicked.disconnect()
                self.browse_tab.find_prev_clicked.disconnect()

            if self.smart_tab is not None:
                self.smart_tab.smart_mode_changed.disconnect()
                self.smart_tab.region_changed.disconnect()
                self.smart_tab.offset_requested.disconnect()

            if self.history_tab is not None:
                self.history_tab.sprite_selected.disconnect()

            # Disconnect preview widget signals
            if self.preview_widget is not None:
                self.preview_widget.similarity_search_requested.disconnect()

            # Disconnect smart preview coordinator
            if self._smart_preview_coordinator is not None:
                self._smart_preview_coordinator.preview_ready.disconnect()
                self._smart_preview_coordinator.preview_cached.disconnect()
                self._smart_preview_coordinator.preview_error.disconnect()
        except TypeError:
            pass  # Already disconnected

        # Clean up workers
        self._cleanup_workers()

        # Clear references
        self.extraction_manager = None
        self.rom_extractor = None

        # Clear cache references
        if self._adjacent_offsets_cache:
            self._adjacent_offsets_cache.clear()

        # Clear bookmarks to prevent reference leaks
        if self.bookmarks:
            self.bookmarks.clear()

        # Clear preview pixmaps
        if self.preview_widget is not None:
            self.preview_widget.clear()

        # Clear advanced search dialog reference
        if hasattr(self, "_advanced_search_dialog") and self._advanced_search_dialog is not None:
            self._advanced_search_dialog.close()
            self._advanced_search_dialog = None

    # Public interface methods required by ROM extraction panel

    def set_rom_data(self, rom_path: str, rom_size: int, extraction_manager: ExtractionManagerProtocol) -> None:
        """Set ROM data for the dialog."""
        with QMutexLocker(self._manager_mutex):
            self.rom_path = rom_path
            self.rom_size = rom_size
            self.extraction_manager = extraction_manager
            self.rom_extractor = extraction_manager.get_rom_extractor()

        # Update tabs with new ROM data
        if self.browse_tab is not None:
            self.browse_tab.set_rom_size(rom_size)
            self.browse_tab.set_rom_path(rom_path)

        # Update gallery tab with ROM data
        if self.gallery_tab is not None:
            self.gallery_tab.set_rom_data(rom_path, rom_size, self.rom_extractor)

        # Update mini ROM map
        if self.mini_rom_map is not None:
            self.mini_rom_map.set_rom_size(rom_size)

        # Update window title
        self.view_state_manager.update_title_with_rom(rom_path)

        logger.debug(f"ROM data updated: {Path(rom_path).name} ({rom_size} bytes)")

        # Initialize cache for this ROM
        self._initialize_rom_cache(rom_path)

        # Update cache status display
        self._update_cache_status_display()

        # Load any cached sprites for visualization
        self._load_cached_sprites_for_map()

    def _scan_for_sprites(self):
        """Scan ROM for HAL-compressed sprites and show results."""
        logger.info(f"_scan_for_sprites called, rom_path={self.rom_path}")

        if not self.rom_path:
            logger.warning("No ROM loaded for sprite scanning")
            QMessageBox.warning(self, "No ROM", "Please load a ROM first.")
            return

        logger.info(f"Starting sprite scan for ROM: {self.rom_path}")

        # Create progress dialog
        progress = QProgressDialog("Scanning ROM for sprites...", "Cancel", 0, 100, self)
        progress.setWindowTitle("Sprite Scanner")
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setMinimumDuration(0)
        progress.show()

        try:
            # Create sprite finder
            finder = SpriteFinder()

            # Read ROM data
            with Path(self.rom_path).open("rb") as f:
                rom_data = f.read()

            # Track found sprites
            found_sprites = []

            # Scan through ROM in chunks to show progress
            rom_size = len(rom_data)
            step = 0x1000  # 4KB steps

            for offset in range(0, rom_size, step):
                # Check for cancel
                if progress.wasCanceled():
                    break

                # Update progress
                progress_value = int((offset / rom_size) * 100)
                progress.setValue(progress_value)
                # Use ExcludeUserInputEvents to prevent reentrancy issues
                QApplication.processEvents(QEventLoop.ProcessEventsFlag.ExcludeUserInputEvents)

                # Try to find sprite at this offset
                sprite_info = finder.find_sprite_at_offset(rom_data, offset)
                if sprite_info:
                    found_sprites.append(sprite_info)
                    logger.info(f"Found sprite at 0x{offset:X}: {sprite_info['tile_count']} tiles")

            progress.close()

            # Show results
            if found_sprites:
                self._show_sprite_scan_results(found_sprites)
            else:
                QMessageBox.information(self, "No Sprites Found",
                                       "No HAL-compressed sprites were found in the ROM.")

        except Exception as e:
            progress.close()
            logger.error(f"Error scanning for sprites: {e}")
            QMessageBox.critical(self, "Scan Error", f"Error scanning ROM: {e!s}")

    def _show_sprite_scan_results(self, sprites: list[dict[str, Any]]) -> None:
        """Show sprite scan results in a dialog."""
        # Create results dialog
        dialog = QDialog(self)
        dialog.setWindowTitle(f"Found {len(sprites)} Sprites")
        dialog.setMinimumSize(600, 400)

        layout = QVBoxLayout(dialog)

        # Info label
        info_label = QLabel(f"Found {len(sprites)} HAL-compressed sprites in the ROM:")
        layout.addWidget(info_label)

        # Create list widget for results
        list_widget = QListWidget()

        for sprite in sprites:
            offset = sprite['offset']
            tile_count = sprite['tile_count']
            size = sprite['decompressed_size']
            quality = sprite.get('quality', 0)

            # Create item text
            text = f"0x{offset:06X} - {tile_count} tiles ({size} bytes) - Quality: {quality:.1%}"
            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, offset)
            list_widget.addItem(item)

        list_widget.itemDoubleClicked.connect(lambda item: self._jump_to_sprite(item.data(Qt.ItemDataRole.UserRole)))
        layout.addWidget(list_widget)

        # Buttons
        button_box = QDialogButtonBox()

        jump_button = QPushButton("Jump to Selected")
        jump_button.clicked.connect(lambda: self._jump_to_selected_sprite(list_widget))
        button_box.addButton(jump_button, QDialogButtonBox.ButtonRole.ActionRole)

        close_button = button_box.addButton(QDialogButtonBox.StandardButton.Close)
        close_button.clicked.connect(dialog.close)

        layout.addWidget(button_box)

        dialog.exec()

    def _jump_to_sprite(self, offset: int) -> None:
        """Jump to a specific sprite offset."""
        logger.info(f"Jumping to sprite at 0x{offset:06X}")
        self.set_offset(offset)

    def _jump_to_selected_sprite(self, list_widget: QListWidget) -> None:
        """Jump to the selected sprite in the list."""
        item = list_widget.currentItem()
        if item:
            offset = item.data(Qt.ItemDataRole.UserRole)
            self._jump_to_sprite(offset)

    def _get_rom_data_for_preview(self):
        """Provide ROM data with cache support for smart preview coordinator."""
        with QMutexLocker(self._manager_mutex):
            result = (self.rom_path, self.rom_extractor, self.rom_cache)
            logger.debug(f"[DEBUG] _get_rom_data_for_preview returning: (rom_path={bool(result[0])}, extractor={bool(result[1])}, cache={bool(result[2])})")
            return result

    def _on_smart_preview_ready(self, tile_data: bytes, width: int, height: int, sprite_name: str):
        """Handle preview ready from smart coordinator with guaranteed UI updates."""
        logger.info("[PREVIEW_READY] ========== START ===========")
        logger.info(f"[PREVIEW_READY] data_len={len(tile_data) if tile_data else 0}, {width}x{height}, name={sprite_name}")
        logger.debug(f"[PREVIEW_READY] tile_data first 20 bytes: {tile_data[:20].hex() if tile_data else 'None'}")

        # CRITICAL: Verify we're on main thread before calling widget methods
        current_thread = QThread.currentThread()
        main_thread = get_main_thread()
        logger.debug(f"[THREAD_CHECK] Current thread: {current_thread}, Main thread: {main_thread}, Same: {current_thread == main_thread}")

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
                if hasattr(self.preview_widget, 'preview_label') and self.preview_widget.preview_label:
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
            cache_status = self._get_cache_status_text()
            self._update_status(f"High-quality preview at 0x{current_offset:06X} {cache_status}")
        except Exception as e:
            logger.error(f"[PREVIEW_READY] Error updating status: {e}")

        logger.info("[PREVIEW_READY] ========== END ===========")

    def _on_smart_preview_cached(self, tile_data: bytes, width: int, height: int, sprite_name: str):
        """Handle cached preview from smart coordinator."""
        logger.debug(f"[SIGNAL_RECEIVED] _on_smart_preview_cached called: data_len={len(tile_data) if tile_data else 0}, {width}x{height}, name={sprite_name}")
        logger.debug(f"[SIGNAL_RECEIVED] cached tile_data first 20 bytes: {tile_data[:20].hex() if tile_data else 'None'}")

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

    def _on_smart_preview_error(self, error_msg: str):
        """Handle preview error from smart coordinator."""
        logger.warning("[PREVIEW_ERROR] ========== START ===========")
        logger.warning(f"[PREVIEW_ERROR] Error message: {error_msg}")

        # CRITICAL: Verify we're on main thread before calling widget methods
        current_thread = QThread.currentThread()
        main_thread = get_main_thread()
        logger.debug(f"[THREAD_CHECK] Current thread: {current_thread}, Main thread: {main_thread}, Same: {current_thread == main_thread}")

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
        return 0x200000

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
        try:
            # Reset cache stats for new ROM
            self._cache_stats = {"hits": 0, "misses": 0, "total_requests": 0}
            if self._adjacent_offsets_cache:
                self._adjacent_offsets_cache.clear()

            # Log cache status
            if self.rom_cache.cache_enabled:
                logger.debug(f"ROM cache initialized for {Path(rom_path).name}")
            else:
                logger.debug("ROM cache is disabled")

        except Exception as e:
            logger.warning(f"Error initializing ROM cache: {e}")

    def _schedule_adjacent_preloading(self, current_offset: int) -> None:
        """Schedule preloading of adjacent offsets for smooth navigation."""
        if not self.rom_cache.cache_enabled:
            return

        try:
            # Calculate adjacent offsets based on typical step sizes
            step_sizes = [0x100, 0x1000, 0x2000]  # Common alignment boundaries
            adjacent_offsets = []

            for step in step_sizes:
                # Previous and next offsets
                prev_offset = max(0, current_offset - step)
                next_offset = min(self.rom_size, current_offset + step)

                # Only preload if not already cached
                if prev_offset not in self._adjacent_offsets_cache:
                    adjacent_offsets.append(prev_offset)
                if next_offset not in self._adjacent_offsets_cache:
                    adjacent_offsets.append(next_offset)

            # Limit preloading to avoid overwhelming the system
            adjacent_offsets = adjacent_offsets[:6]  # Max 6 adjacent offsets

            # Schedule preloading with low priority
            for offset in adjacent_offsets:
                self._preload_offset(offset)
                self._adjacent_offsets_cache.add(offset)

        except Exception as e:
            logger.debug(f"Error scheduling adjacent preloading: {e}")

    def _preload_offset(self, offset: int) -> None:
        """Preload a specific offset using the worker pool."""
        if not self._smart_preview_coordinator:
            return

        # Check if we have ROM data available
        if not hasattr(self, '_get_rom_data_for_preview'):
            return

        rom_data = self._get_rom_data_for_preview()
        if not rom_data or not rom_data[0]:  # No ROM path available
            return

        try:
            # Use SmartPreviewCoordinator's worker pool for background preloading
            # Request with very low priority so it doesn't interfere with user actions
            self._smart_preview_coordinator.request_preview(offset, priority=-1)

        except Exception as e:
            logger.debug(f"Error preloading offset 0x{offset:06X}: {e}")

    def _on_cache_hit(self, *args: Any) -> None:
        """Handle cache hit event."""
        self._cache_stats["hits"] += 1

    def _on_cache_miss(self, *args: Any) -> None:
        """Handle cache miss event."""
        self._cache_stats["misses"] += 1

    def _get_cache_status_text(self) -> str:
        """Get cache status text for display."""
        if not self.rom_cache.cache_enabled:
            return "[Cache: Disabled]"

        total = self._cache_stats["total_requests"]
        hits = self._cache_stats["hits"]

        if total > 0:
            hit_rate = (hits / total) * 100
            return f"[Cache: {hit_rate:.0f}% hit rate]"

        return "[Cache: Ready]"

    def _build_cache_tooltip(self) -> str:
        """Build detailed cache tooltip."""
        if not self.rom_cache.cache_enabled:
            return "ROM caching is disabled"

        try:
            stats = self.rom_cache.get_cache_stats()
            cache_info = [
                f"Cache Directory: {stats.get('cache_dir', 'Unknown')}",
                f"Total Cache Files: {stats.get('total_files', 0)}",
                f"Cache Size: {stats.get('total_size_bytes', 0)} bytes",
                "",
                "Session Stats:",
                f"  Total Requests: {self._cache_stats['total_requests']}",
                f"  Cache Hits: {self._cache_stats['hits']}",
                f"  Cache Misses: {self._cache_stats['misses']}",
            ]

            if self._cache_stats["total_requests"] > 0:
                hit_rate = (self._cache_stats["hits"] / self._cache_stats["total_requests"]) * 100
                cache_info.append(f"  Hit Rate: {hit_rate:.1f}%")

            return "\n".join(cache_info)

        except Exception as e:
            return f"Cache tooltip error: {e}"

    def _update_cache_status_display(self) -> None:
        """Update cache status in the UI."""
        try:
            cache_status = self._get_cache_status_text()

            # Update status panel if collapsed box exists
            if self.status_collapsible and self.rom_cache.cache_enabled:
                # Update collapsible title to show cache status
                current_title = self.status_collapsible.title()
                if "[Cache:" not in current_title:
                    new_title = f"{current_title} {cache_status}"
                    # setTitle is available on CollapsibleGroupBox
                    self.status_collapsible.setTitle(new_title)  # type: ignore[attr-defined]

        except Exception as e:
            logger.debug(f"Error updating cache status display: {e}")

    def _setup_cache_context_menu(self) -> None:
        """Set up context menu for cache management."""
        if self.status_collapsible is None:
            return

        try:
            # Enable context menu on the status collapsible widget
            self.status_collapsible.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            self.status_collapsible.customContextMenuRequested.connect(self._show_cache_context_menu)

        except Exception as e:
            logger.debug(f"Error setting up cache context menu: {e}")

    def _show_cache_context_menu(self, position: Any) -> None:
        """Show cache management context menu."""
        if not self.rom_cache.cache_enabled:
            return

        try:
            menu = QMenu(self)

            # Cache statistics action
            stats_action = QAction("Show Cache Statistics", self)
            stats_action.triggered.connect(self._show_cache_statistics)
            menu.addAction(stats_action)

            # Clear cache action
            clear_action = QAction("Clear Cache", self)
            clear_action.triggered.connect(self._clear_cache_with_confirmation)
            menu.addAction(clear_action)

            # Show at cursor position
            global_pos = self.status_collapsible.mapToGlobal(position) if self.status_collapsible else self.mapToGlobal(position)
            menu.exec(global_pos)

        except Exception as e:
            logger.debug(f"Error showing cache context menu: {e}")

    def _show_cache_statistics(self) -> None:
        """Show detailed cache statistics dialog."""
        try:
            stats = self.rom_cache.get_cache_stats()
            session_stats = self._cache_stats

            # Format cache size
            size_bytes = stats.get("total_size_bytes", 0)
            if size_bytes > 1024 * 1024:
                size_str = f"{size_bytes / (1024 * 1024):.1f} MB"
            elif size_bytes > 1024:
                size_str = f"{size_bytes / 1024:.1f} KB"
            else:
                size_str = f"{size_bytes} bytes"

            message = f"""Cache Statistics:

Directory: {stats.get('cache_dir', 'Unknown')}
Total Files: {stats.get('total_files', 0)}
Total Size: {size_str}
Sprite Location Caches: {stats.get('sprite_location_caches', 0)}
ROM Info Caches: {stats.get('rom_info_caches', 0)}
Scan Progress Caches: {stats.get('scan_progress_caches', 0)}

Session Statistics:
Total Requests: {session_stats['total_requests']}
Cache Hits: {session_stats['hits']}
Cache Misses: {session_stats['misses']}"""

            if session_stats["total_requests"] > 0:
                hit_rate = (session_stats["hits"] / session_stats["total_requests"]) * 100
                message += f"\nHit Rate: {hit_rate:.1f}%"

            QMessageBox.information(self, "ROM Cache Statistics", message)

        except Exception as e:
            QMessageBox.warning(self, "Error", f"Failed to retrieve cache statistics: {e}")

    def _clear_cache_with_confirmation(self) -> None:
        """Clear cache with user confirmation."""
        try:
            reply = QMessageBox.question(
                self,
                "Clear Cache",
                "Are you sure you want to clear the ROM cache?\n\nThis will remove all cached data and may slow down future operations.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )

            if reply == QMessageBox.StandardButton.Yes:
                removed_count = self.rom_cache.clear_cache()
                QMessageBox.information(
                    self,
                    "Cache Cleared",
                    f"Successfully cleared {removed_count} cache files."
                )

                # Reset session stats
                self._cache_stats = {"hits": 0, "misses": 0, "total_requests": 0}
                if self._adjacent_offsets_cache:
                    self._adjacent_offsets_cache.clear()

                # Update status display
                self._update_cache_status_display()

        except Exception as e:
            QMessageBox.warning(self, "Error", f"Failed to clear cache: {e}")

    # Event handlers

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
                self._add_bookmark()
                event.accept()
            elif event.key() == Qt.Key.Key_B and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
                # Ctrl+B - Show bookmarks menu
                if self.bookmarks_menu is not None:
                    self.bookmarks_menu.exec(self.mapToGlobal(self.rect().center()))
                event.accept()

        super().keyPressEvent(event)

    def closeEvent(self, event: QCloseEvent | None) -> None:
        """Handle close event."""
        logger.debug(f"Dialog {self._debug_id} closing")
        self.cleanup()
        if event:
            super().closeEvent(event)

    def hideEvent(self, event: QHideEvent | None) -> None:
        """Handle hide event."""
        logger.debug(f"Dialog {self._debug_id} hiding")
        # Only cleanup workers on hide, not full cleanup (dialog may be shown again)
        self._cleanup_workers()
        self.view_state_manager.handle_hide_event()
        if event:
            super().hideEvent(event)

    def showEvent(self, event: Any) -> None:
        """Handle show event - set up initial splitter sizes here."""
        logger.debug(f"Dialog {self._debug_id} showing")
        super().showEvent(event)
        self.view_state_manager.handle_show_event()

        # Let layout manager handle all initial setup including splitter configuration
        self.layout_manager.on_dialog_show()

        # Set initial splitter sizes based on current tab
        self._update_splitter_for_tab()

    def _on_tab_changed(self, index: int) -> None:
        """Handle tab change - adjust splitter ratio based on tab."""
        self.layout_manager.update_for_tab(index, self.width())

    def _update_splitter_for_tab(self, index: int | None = None) -> None:
        """Update splitter sizes based on active tab - delegated to layout manager."""
        if index is None and self.tab_widget:
            index = self.tab_widget.currentIndex()
        if index is not None:
            self.layout_manager.update_for_tab(index, self.width())

    def _create_section_title(self, text: str) -> QLabel:
        """Create a styled section title label - delegated to layout manager."""
        return self.layout_manager.create_section_title(text)

    def resizeEvent(self, event: Any) -> None:
        """Handle resize event - adjust splitter proportionally."""
        super().resizeEvent(event)

        # Delegate all resize handling to layout manager
        if self.isVisible():
            self.layout_manager.handle_resize(event.size().width())

    def moveEvent(self, event: Any) -> None:
        """Handle dialog move event - constrain to screen bounds"""
        super().moveEvent(event)

        # Skip validation during initialization or if dialog is not visible
        if not self.isVisible():
            return

        from PySide6.QtGui import QGuiApplication

        # Defensive check for test environments with mock objects
        try:
            new_pos = event.pos()
            x, y = new_pos.x(), new_pos.y()
        except (AttributeError, TypeError):
            # In test environment with mocks, skip geometry validation
            return

        # Get available screen geometry
        screen = QGuiApplication.primaryScreen()
        if screen:
            available = screen.availableGeometry()

            # Defensive check for mock geometry objects in tests
            try:
                available_x = available.x()
                available_y = available.y()
                available_width = available.width()
                available_height = available.height()
                dialog_width = self.width()
                dialog_height = self.height()

                # Verify all values are numeric before arithmetic
                if not all(isinstance(v, (int, float)) for v in
                          [available_x, available_y, available_width, available_height,
                           dialog_width, dialog_height]):
                    # Skip validation if any values are not numeric (likely mocks)
                    return

                # Ensure dialog stays within screen bounds with small margin
                margin = 50  # Allow some overlap with screen edge
                min_x = available_x - dialog_width + margin
                max_x = available_x + available_width - margin
                min_y = available_y - dialog_height + margin
                max_y = available_y + available_height - margin

                # Constrain position
                constrained_x = max(min_x, min(x, max_x))
                constrained_y = max(min_y, min(y, max_y))

                # Move back if position was adjusted
                if constrained_x != x or constrained_y != y:
                    logger.debug(f"Constraining dialog position from ({x},{y}) to ({constrained_x},{constrained_y})")
                    self.move(constrained_x, constrained_y)

            except (AttributeError, TypeError):
                # In test environment with mocks, skip geometry validation
                return

    def _on_search_sprite_found(self, offset: int, quality: float):
        """Handle sprite found during navigation search"""
        if self.browse_tab is not None:
            self.browse_tab.set_offset(offset)

        # Add to history
        self.add_found_sprite(offset, quality)

        self._update_status(f"Found sprite at 0x{offset:06X} (quality: {quality:.2f})")

    def _on_search_complete(self, found: bool):
        """Handle search completion"""
        if not found:
            self._update_status("No sprites found in search direction")

    def _add_bookmark(self):
        """Add current offset to bookmarks"""
        offset = self.get_current_offset()

        # Check if already bookmarked
        for existing_offset, _ in self.bookmarks:
            if existing_offset == offset:
                self._update_status("Offset already bookmarked")
                return

        # Add bookmark with descriptive name
        name, ok = QInputDialog.getText(
            self, "Add Bookmark",
            f"Name for bookmark at 0x{offset:06X}:",
            text=f"Sprite at 0x{offset:06X}"
        )

        if ok and name:
            self.bookmarks.append((offset, name))
            self._update_bookmarks_menu()
            self._update_status(f"Bookmarked: {name}")

    def _update_bookmarks_menu(self):
        """Update bookmarks menu"""
        if self.bookmarks_menu is None:
            return

        if self.bookmarks_menu:
            self.bookmarks_menu.clear()

        if not self.bookmarks:
            action = self.bookmarks_menu.addAction("No bookmarks")
            action.setEnabled(False)
        else:
            for offset, name in self.bookmarks:
                action = self.bookmarks_menu.addAction(f"{name} (0x{offset:06X})")
                # Use functools.partial to avoid lambda closure
                action.triggered.connect(partial(self._go_to_bookmark, offset))

            self.bookmarks_menu.addSeparator()
            clear_action = self.bookmarks_menu.addAction("Clear All Bookmarks")
            clear_action.triggered.connect(self._clear_bookmarks)

    def _go_to_bookmark(self, offset: int):
        """Go to a bookmarked offset."""
        self.set_offset(offset)

    def _clear_bookmarks(self):
        """Clear all bookmarks"""
        if self.bookmarks:
            self.bookmarks.clear()
        self._update_bookmarks_menu()
        self._update_status("Bookmarks cleared")

    def _on_similarity_search_requested(self, target_offset: int):
        """Handle similarity search request from preview widget."""
        logger.info(f"Similarity search requested for offset 0x{target_offset:06X}")

        # Navigate to the selected similar sprite
        self.set_offset(target_offset)
        self._update_status(f"Navigated to similar sprite at 0x{target_offset:06X}")

    def _show_goto_dialog(self):
        """Show go to offset dialog"""

        current = self.get_current_offset()
        text, ok = QInputDialog.getText(
            self, "Go to Offset",
            "Enter offset (hex or decimal):",
            text=f"0x{current:06X}"
        )

        if ok and text:
            try:
                # Parse hex or decimal
                offset = int(text, 16) if text.startswith(("0x", "0X")) else int(text)

                # Validate bounds
                if 0 <= offset <= self.rom_size:
                    self.set_offset(offset)
                else:
                    self._update_status(f"Offset out of range: 0x{offset:06X}")
            except ValueError:
                self._update_status(f"Invalid offset: {text}")

    def _load_cached_sprites_for_map(self):
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

def create_manual_offset_dialog(parent: QWidget | None = None) -> UnifiedManualOffsetDialog:
    """Factory function for creating manual offset dialog."""
    return UnifiedManualOffsetDialog(parent)
