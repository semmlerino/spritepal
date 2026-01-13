"""
Grid Arrangement Dialog for SpritePal
Flexible sprite arrangement supporting rows, columns, and custom tile groups
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, override

if TYPE_CHECKING:
    from ui.sprite_editor.services.arrangement_bridge import ArrangementBridge

from PIL import Image
from PySide6.QtCore import QObject, Qt
from PySide6.QtGui import (
    QCloseEvent,
    QKeyEvent,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import (
    QDialogButtonBox,
    QFrame,
    QGraphicsPixmapItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from core.apply_operation import ApplyOperation, ApplyResult, ApplyWarning, WarningType
from core.services.image_utils import pil_to_qimage
from ui.common.signal_utils import safe_disconnect
from ui.common.spacing_constants import SPACING_COMPACT_SMALL
from ui.components.visualization import GridGraphicsView, ScrollablePreviewGroup, SelectionMode
from ui.widgets.segmented_toggle import SegmentedToggle

from .components import SplitterDialog
from .row_arrangement import OverlayControls, OverlayLayer, PaletteColorizer
from .row_arrangement.grid_arrangement_manager import (
    ArrangementType,
    GridArrangementManager,
    TileGroup,
    TilePosition,
)
from .row_arrangement.grid_image_processor import GridImageProcessor
from .row_arrangement.grid_preview_generator import GridPreviewGenerator
from .row_arrangement.undo_redo import (
    AddGroupCommand,
    AddMultipleTilesCommand,
    ApplyOverlayCommand,
    CanvasMoveItemsCommand,
    CanvasPlaceItemsCommand,
    CanvasRemoveMultipleItemsCommand,
    ClearGridCommand,
    RestoreGridStateCommand,
    UndoRedoStack,
)
from .utils.accessibility import AccessibilityHelper


@dataclass
class ArrangementResult:
    """Result from GridArrangementDialog when accepted with arrangement.

    Contains everything needed to use the arrangement in the editing workflow.
    """

    bridge: ArrangementBridge
    metadata: dict[str, object]
    logical_width: int  # Tiles per row in arranged view
    modified_tiles: dict[TilePosition, Image.Image] | None = None


# GridGraphicsView and SelectionMode are now imported from ui.components.visualization


class GridArrangementDialog(SplitterDialog):
    """Dialog for grid-based sprite arrangement with row and column support"""

    def __init__(self, sprite_path: str, tiles_per_row: int = 16, parent: QWidget | None = None) -> None:
        # Step 1: Declare instance variables BEFORE super().__init__()
        self.sprite_path = sprite_path
        self.tiles_per_row = tiles_per_row
        self.output_path = None

        # Initialize components
        self.processor = GridImageProcessor()
        self.colorizer = PaletteColorizer()
        self.preview_generator = GridPreviewGenerator(self.colorizer)

        # Initialize UI components that will be created in _setup_ui
        self.source_grid: QWidget | None = None
        self.arranged_grid: QWidget | None = None
        self.original_image: Image.Image | None = None
        self.tiles: dict[TilePosition, Image.Image] = {}

        # Load and process sprite before UI setup
        try:
            self.original_image, self.tiles = self.processor.process_sprite_sheet_as_grid(sprite_path, tiles_per_row)
        except (OSError, ValueError, RuntimeError) as e:
            # Show error dialog and close
            _ = QMessageBox.critical(parent, "Error Loading Sprite", f"Failed to load sprite file:\n{e!s}")
            # Set up minimal state to prevent crashes
            self.original_image = None
            self.tiles = {}
            self.processor.grid_rows = 1
            self.processor.grid_cols = 1
            # Don't return here - continue with dialog setup but in error state

        # Create arrangement manager
        self.arrangement_manager = GridArrangementManager(self.processor.grid_rows, self.processor.grid_cols)

        # Create undo/redo stack
        self.undo_stack = UndoRedoStack()

        # Create overlay layer for reference images
        self.overlay_layer = OverlayLayer()

        # Apply operation result (set by _apply_overlay())
        self._apply_result: ApplyResult | None = None

        # Step 2: Call parent init (this will call _setup_ui)
        super().__init__(
            parent=parent,
            title="Grid-Based Sprite Arrangement",
            modal=True,
            size=(1600, 900),
            with_status_bar=True,
            # Don't use automatic splitter creation - create explicitly in _setup_ui
            orientation=None,  # type: ignore[arg-type]
            splitter_handle_width=8,
        )

        # Connect signals after UI is created
        self.arrangement_manager.arrangement_changed.connect(self._on_arrangement_changed)
        self.colorizer.palette_mode_changed.connect(self._on_palette_mode_changed)

        # Connect selection mode toggle
        self.mode_toggle.selection_changed.connect(self._on_mode_changed)

        # Connect overlay signals to update canvas when overlay changes
        self.overlay_layer.position_changed.connect(self._on_overlay_changed)
        self.overlay_layer.opacity_changed.connect(self._on_overlay_changed)
        self.overlay_layer.visibility_changed.connect(self._on_overlay_changed)
        self.overlay_layer.image_changed.connect(self._on_overlay_changed)

        # Initial update (only if we have valid data)
        if self.original_image is not None:
            self._update_displays()
            self.update_status("Select tiles, rows, or columns to arrange. Wheel to zoom, F to fit.")
        else:
            self.update_status("Error: Unable to load sprite file")

    @override
    def _setup_ui(self):
        """Set up the dialog UI using SplitterDialog panels"""
        # Call parent _setup_ui first to initialize the main splitter
        super()._setup_ui()

        # Apply accessibility enhancements
        self._apply_accessibility_enhancements()

        # Create horizontal splitter for left and right panels
        self.main_splitter = self.add_horizontal_splitter(handle_width=8)

        # Create left and right panels
        left_widget = self._create_left_panel()
        right_widget = self._create_right_panel()

        # Add panels to main horizontal splitter
        self.main_splitter.addWidget(left_widget)
        self.main_splitter.setStretchFactor(0, 2)  # 67% for left panel
        self.main_splitter.addWidget(right_widget)
        self.main_splitter.setStretchFactor(1, 1)  # 33% for right panel

        # Add custom buttons using SplitterDialog's button system
        self.export_btn = self.add_button("Export Arrangement", callback=self._export_arrangement)
        if self.export_btn:
            self.export_btn.setEnabled(False)
            # Add to button box with ActionRole so it appears on the left or appropriate spot
            if self.button_box:
                self.button_box.addButton(self.export_btn, QDialogButtonBox.ButtonRole.ActionRole)

        AccessibilityHelper.make_accessible(
            self.export_btn, "Export Arrangement", "Export the arranged sprites to a new file", "Ctrl+E"
        )

    def _create_left_panel(self) -> QWidget:
        """Create the left panel containing grid view and controls.

        Returns:
            QWidget: The configured left panel widget
        """
        left_widget = QWidget(self)
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(SPACING_COMPACT_SMALL)

        # Add selection mode controls
        mode_group = self._create_selection_mode_group(left_widget)
        left_layout.addWidget(mode_group)

        # Add grid view
        grid_group = self._create_grid_view_group(left_widget)
        left_layout.addWidget(grid_group, 1)

        # Add action buttons
        actions_group = self._create_actions_group(left_widget)
        left_layout.addWidget(actions_group)

        return left_widget

    def _create_right_panel(self) -> QWidget:
        """Create the right panel containing arrangement grid, overlay controls, and preview.

        Returns:
            QWidget: The configured right panel widget
        """
        right_widget = QWidget(self)
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(SPACING_COMPACT_SMALL)

        # Add arrangement grid
        grid_group = self._create_arrangement_grid_group(right_widget)
        right_layout.addWidget(grid_group, 2)  # Give more stretch to canvas

        # Add overlay controls and Apply button
        overlay_group = QGroupBox("Overlay Reference", right_widget)
        overlay_layout = QVBoxLayout(overlay_group)

        self.overlay_controls = OverlayControls(self.overlay_layer, overlay_group)
        self.overlay_controls.setContentsMargins(0, 0, 0, 0)
        self.overlay_controls.setTitle("")  # Hide redundant title
        overlay_layout.addWidget(self.overlay_controls)

        self.apply_overlay_btn = QPushButton("Apply Overlay to Arranged Tiles", overlay_group)
        self.apply_overlay_btn.setToolTip(
            "Sample overlay image and write pixels to tiles currently placed on the canvas (Undoable)"
        )
        self.apply_overlay_btn.setStyleSheet("font-weight: bold; padding: 5px;")
        _ = self.apply_overlay_btn.clicked.connect(self._apply_overlay)
        overlay_layout.addWidget(self.apply_overlay_btn)

        right_layout.addWidget(overlay_group)

        # Add preview
        preview_group = self._create_preview_group(right_widget)
        right_layout.addWidget(preview_group, 1)

        return right_widget

    def _create_arrangement_grid_group(self, parent: QWidget) -> QGroupBox:
        """Create the arrangement grid group.

        Args:
            parent: Parent widget for the group

        Returns:
            QGroupBox: The configured arrangement grid group
        """
        grid_group = QGroupBox("Current Arrangement", parent)
        grid_layout = QVBoxLayout()

        # Create arrangement scene and view
        self.arrangement_scene = QGraphicsScene(self)
        self.arrangement_grid = GridGraphicsView(self)
        self.arrangement_grid.setScene(self.arrangement_scene)

        # Configure arrangement grid
        width = self.width_spin.value() if hasattr(self, "width_spin") else 16
        self.arrangement_grid.set_grid_dimensions(
            width,
            32,  # Large enough height to start
            self.processor.tile_width,
            self.processor.tile_height,
        )

        # Connect arrangement grid signals
        self.arrangement_grid.tiles_dropped.connect(self._on_tiles_dropped_on_canvas)
        self.arrangement_grid.tile_clicked.connect(self._on_arrangement_tile_clicked)

        grid_layout.addWidget(self.arrangement_grid)
        grid_group.setLayout(grid_layout)
        return grid_group

    def _apply_accessibility_enhancements(self) -> None:
        """Apply comprehensive accessibility enhancements to the dialog"""
        # Set dialog accessible name and description
        AccessibilityHelper.make_accessible(
            self, "Grid Arrangement Dialog", "Arrange sprites in a grid layout with row and column support"
        )

        # Add focus indicators
        AccessibilityHelper.add_focus_indicators(self)

        # Add keyboard shortcuts (Ctrl+Z, Ctrl+Y, Delete handled via keyPressEvent)
        from PySide6.QtGui import QKeySequence, QShortcut

        # Ctrl+E for export (not duplicated in keyPressEvent)
        export_shortcut = QShortcut(QKeySequence("Ctrl+E"), self)
        export_shortcut.activated.connect(self._export_arrangement)

    def _create_selection_mode_group(self, parent: QWidget) -> QGroupBox:
        """Create the selection mode controls group.

        Args:
            parent: Parent widget for the group

        Returns:
            QGroupBox: The configured selection mode group
        """
        mode_group = QGroupBox("&Selection Mode", parent)
        AccessibilityHelper.add_group_box_navigation(mode_group)
        mode_layout = QHBoxLayout()

        self.mode_toggle = SegmentedToggle(mode_group)

        # Create buttons with mnemonics and accessibility
        mode_options = [
            (SelectionMode.TILE, "Tile", "T", "Select individual tiles [T]"),
            (SelectionMode.ROW, "Row", "R", "Select entire rows [R]"),
            (SelectionMode.COLUMN, "Column", "C", "Select entire columns [C]"),
            (SelectionMode.RECTANGLE, "Marquee", "M", "Select rectangular regions [M]"),
        ]

        for mode, label, _, tooltip in mode_options:
            self.mode_toggle.add_option(label, mode, checked=(mode == SelectionMode.TILE))
            self.mode_toggle.set_tooltip(mode, tooltip)
        mode_layout.addWidget(self.mode_toggle)
        mode_layout.addStretch()

        mode_group.setLayout(mode_layout)
        return mode_group

    def _create_grid_view_group(self, parent: QWidget) -> QGroupBox:
        """Create the grid view group with graphics scene.

        Args:
            parent: Parent widget for the group

        Returns:
            QGroupBox: The configured grid view group
        """
        grid_group = QGroupBox("Sprite Grid", parent)
        grid_layout = QVBoxLayout()

        # Create graphics scene and view
        self.scene = QGraphicsScene(self)
        self.grid_view = GridGraphicsView(self)
        self.grid_view.setScene(self.scene)
        self.grid_view.setAcceptDrops(False)  # Disable drops on source grid

        # Initialize grid view
        self._initialize_grid_view()

        # Connect grid view signals
        self._connect_grid_view_signals()

        grid_layout.addWidget(self.grid_view)
        grid_group.setLayout(grid_layout)
        return grid_group

    def _initialize_grid_view(self):
        """Initialize the grid view with image data if available."""
        if self.original_image is not None:
            pixmap = self._create_pixmap_from_image(self.original_image)
            self.pixmap_item = self.scene.addPixmap(pixmap)
            self.grid_view.set_grid_dimensions(
                self.processor.grid_cols,
                self.processor.grid_rows,
                self.processor.tile_width,
                self.processor.tile_height,
            )
        else:
            # Create placeholder for error state
            self.pixmap_item = None

    def _connect_grid_view_signals(self):
        """Connect all grid view signals."""
        self.grid_view.tile_clicked.connect(self._on_tile_clicked)
        self.grid_view.tiles_selected.connect(self._on_tiles_selected)
        self.grid_view.zoom_changed.connect(self._on_zoom_changed)
        self.grid_view.tiles_dropped.connect(self._on_tiles_dropped_on_canvas)
        self._update_zoom_level_display()

    def _create_actions_group(self, parent: QWidget) -> QGroupBox:
        """Create the actions group with buttons and zoom controls.

        Args:
            parent: Parent widget for the group

        Returns:
            QGroupBox: The configured actions group
        """
        actions_group = QGroupBox("Actions", parent)
        actions_layout = QHBoxLayout()

        # Add action buttons
        self._add_action_buttons(actions_layout)

        # Add separator
        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.VLine)
        separator.setFrameShadow(QFrame.Shadow.Sunken)
        actions_layout.addWidget(separator)

        # Add zoom controls
        self._add_zoom_controls(actions_layout)

        actions_group.setLayout(actions_layout)
        return actions_group

    def _add_action_buttons(self, layout: QHBoxLayout):
        """Add action buttons to the given layout.

        Args:
            layout: Layout to add buttons to
        """
        self.add_btn = QPushButton("Add Selection", self)
        self.add_btn.setToolTip("Add selected tiles to canvas [Enter]")
        _ = self.add_btn.clicked.connect(self._add_selection)
        layout.addWidget(self.add_btn)

        self.add_all_btn = QPushButton("Add All", self)
        _ = self.add_all_btn.clicked.connect(self._add_all_tiles)
        layout.addWidget(self.add_all_btn)

        self.magic_wand_btn = QPushButton("Magic Wand", self)
        _ = self.magic_wand_btn.clicked.connect(self._magic_wand_selection)
        self.magic_wand_btn.setToolTip("Select all non-empty tiles")
        layout.addWidget(self.magic_wand_btn)

        self.remove_btn = QPushButton("Remove Selection", self)
        self.remove_btn.setToolTip("Remove selection from source or canvas [Delete]")
        _ = self.remove_btn.clicked.connect(self._remove_selection)
        layout.addWidget(self.remove_btn)

        self.create_group_btn = QPushButton("Create Group", self)
        _ = self.create_group_btn.clicked.connect(self._create_group)
        layout.addWidget(self.create_group_btn)

        self.clear_btn = QPushButton("Clear All", self)
        self.clear_btn.setToolTip("Clear the entire arrangement [Esc]")
        _ = self.clear_btn.clicked.connect(self._clear_arrangement)
        layout.addWidget(self.clear_btn)

        # Add separator before Reset
        sep2 = QFrame()
        sep2.setFrameShape(QFrame.Shape.VLine)
        sep2.setFrameShadow(QFrame.Shadow.Sunken)
        layout.addWidget(sep2)

        self.reset_layout_btn = QPushButton("Reset to 1:1", self)
        self.reset_layout_btn.setToolTip("Reset all tiles to their original positions (1:1 mapping)")
        _ = self.reset_layout_btn.clicked.connect(self._reset_layout)
        layout.addWidget(self.reset_layout_btn)

        layout.addStretch()

        # Add collapsible shortcut legend
        self._add_shortcut_legend(layout)

    def _add_shortcut_legend(self, layout: QHBoxLayout):
        """Add a collapsible shortcut legend to the given layout."""
        # Container for the toggle button and legend content
        legend_container = QFrame()
        legend_layout = QVBoxLayout(legend_container)
        legend_layout.setContentsMargins(0, 0, 0, 0)
        legend_layout.setSpacing(2)

        # Toggle button with arrow indicator
        self._legend_toggle_btn = QToolButton()
        self._legend_toggle_btn.setCheckable(True)
        self._legend_toggle_btn.setChecked(True)  # Start expanded
        self._legend_toggle_btn.setArrowType(Qt.ArrowType.DownArrow)
        self._legend_toggle_btn.setText(" Shortcuts")
        self._legend_toggle_btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self._legend_toggle_btn.setStyleSheet("QToolButton { border: none; color: #888888; }")
        self._legend_toggle_btn.toggled.connect(self._on_legend_toggled)
        legend_layout.addWidget(self._legend_toggle_btn)

        # Legend content (multi-line, comprehensive)
        self._legend_content = QLabel(
            "<font color='#888888'>"
            "<b>Modes:</b> [T] Tile [R] Row [C] Column [M] Marquee<br>"
            "<b>Actions:</b> [Enter] Add [Del] Remove [Esc] Clear [Ctrl+E] Export<br>"
            "<b>Mouse:</b> Ctrl+Click select | Drag to arrange | Wheel zoom | Middle-drag pan<br>"
            "<b>Undo:</b> [Ctrl+Z] Undo [Ctrl+Y] Redo"
            "</font>"
        )
        self._legend_content.setWordWrap(True)
        legend_layout.addWidget(self._legend_content)

        layout.addWidget(legend_container)

    def _on_legend_toggled(self, expanded: bool):
        """Handle legend toggle button state change."""
        self._legend_content.setVisible(expanded)
        arrow = Qt.ArrowType.DownArrow if expanded else Qt.ArrowType.RightArrow
        self._legend_toggle_btn.setArrowType(arrow)

    def _add_zoom_controls(self, layout: QHBoxLayout):
        """Add zoom control buttons to the given layout.

        Args:
            layout: Layout to add zoom controls to
        """
        # Target Sheet Width
        layout.addWidget(QLabel("Target Sheet Width:"))
        self.width_spin = QSpinBox(self)
        self.width_spin.setRange(1, 64)
        self.width_spin.setValue(min(16, self.processor.grid_cols))
        self.width_spin.setToolTip("Number of tiles per row in the final exported sprite sheet")
        self.width_spin.valueChanged.connect(self._on_arrangement_width_changed)
        layout.addWidget(self.width_spin)

        # Separator
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setFrameShadow(QFrame.Shadow.Sunken)
        layout.addWidget(sep)

        self.zoom_out_btn = QPushButton("-", self)
        _ = self.zoom_out_btn.clicked.connect(self.grid_view.zoom_out)
        self.zoom_out_btn.setMaximumWidth(30)
        self.zoom_out_btn.setToolTip("Zoom out [Ctrl+-]")
        layout.addWidget(self.zoom_out_btn)

        self.zoom_level_label = QLabel("100%", self)
        self.zoom_level_label.setMinimumWidth(50)
        self.zoom_level_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.zoom_level_label)

        self.zoom_in_btn = QPushButton("+", self)
        _ = self.zoom_in_btn.clicked.connect(self.grid_view.zoom_in)
        self.zoom_in_btn.setMaximumWidth(30)
        self.zoom_in_btn.setToolTip("Zoom in [Ctrl++]")
        layout.addWidget(self.zoom_in_btn)

        self.zoom_fit_btn = QPushButton("Fit", self)
        _ = self.zoom_fit_btn.clicked.connect(self.grid_view.zoom_to_fit)
        self.zoom_fit_btn.setMaximumWidth(40)
        self.zoom_fit_btn.setToolTip("Zoom to fit [F]")
        layout.addWidget(self.zoom_fit_btn)

        self.zoom_reset_btn = QPushButton("1:1", self)
        _ = self.zoom_reset_btn.clicked.connect(self.grid_view.reset_zoom)
        self.zoom_reset_btn.setMaximumWidth(40)
        self.zoom_reset_btn.setToolTip("Reset zoom to 1:1 [Ctrl+0]")
        layout.addWidget(self.zoom_reset_btn)

    def _create_preview_group(self, parent: QWidget) -> ScrollablePreviewGroup:
        """Create the preview group with scrollable area.

        Args:
            parent: Parent widget for the group

        Returns:
            ScrollablePreviewGroup: The configured preview group
        """
        preview_group = ScrollablePreviewGroup(
            title="Arrangement Preview",
            with_styling=True,
            parent=parent,
        )
        self.preview_label = preview_group.preview_label
        return preview_group

    def _on_arrangement_width_changed(self, value: int):
        """Handle arrangement width change"""
        # Update the arrangement manager's target width for auto-placement FIRST
        # (before UI updates that may fail in test environments)
        if self.arrangement_manager:
            self.arrangement_manager.set_target_width(value)
        if hasattr(self, "arrangement_grid"):
            try:
                self.arrangement_grid.set_grid_dimensions(
                    value, 32, self.processor.tile_width, self.processor.tile_height
                )
            except RuntimeError:
                # Grid items may be deleted during shutdown/test teardown
                pass
        self._update_preview()

    def _add_all_tiles(self):
        """Add all tiles from the grid to the arrangement"""
        tiles_to_add = []
        for row in range(self.grid_view.grid_rows):
            for col in range(self.grid_view.grid_cols):
                pos = TilePosition(row, col)
                if not self.arrangement_manager.is_tile_arranged(pos):
                    tiles_to_add.append(pos)

        if tiles_to_add:
            command = AddMultipleTilesCommand(
                manager=self.arrangement_manager,
                tiles=tiles_to_add,
            )
            self.undo_stack.push(command)

    def _magic_wand_selection(self):
        """Select all non-empty tiles (with any non-zero pixels)"""
        non_empty_tiles = []
        for pos, img in self.tiles.items():
            # Check if image has any non-transparent/non-zero pixels
            # For Kirby/HAL sprites, index 0 is usually transparent.
            # But let's check bounding box of non-zero pixels.
            if img.getbbox():
                non_empty_tiles.append(pos)

        if non_empty_tiles:
            # Sort them by row then col
            non_empty_tiles.sort(key=lambda p: (p.row, p.col))

            # Filter out already arranged
            tiles_to_add = [t for t in non_empty_tiles if not self.arrangement_manager.is_tile_arranged(t)]

            if tiles_to_add:
                command = AddMultipleTilesCommand(
                    manager=self.arrangement_manager,
                    tiles=tiles_to_add,
                )
                self.undo_stack.push(command)
                self._update_status(f"Magic Wand: Added {len(tiles_to_add)} non-empty tiles")
            else:
                self._update_status("Magic Wand: No new non-empty tiles to add")
        else:
            self._update_status("Magic Wand: No non-empty tiles found")

    def _on_undo(self) -> None:
        """Handle undo shortcut."""
        description = self.undo_stack.undo()
        if description:
            self._update_displays()
            self._update_status(f"Undo: {description}")

    def _on_redo(self) -> None:
        """Handle redo shortcut."""
        description = self.undo_stack.redo()
        if description:
            self._update_displays()
            self._update_status(f"Redo: {description}")

    def _on_mode_changed(self, mode: SelectionMode) -> None:
        """Handle selection mode change"""
        self.grid_view.set_selection_mode(mode)

        guidance = {
            SelectionMode.TILE: "Click tiles to select. Drag from Source to Canvas to place.",
            SelectionMode.ROW: "Click a tile to select its entire row.",
            SelectionMode.COLUMN: "Click a tile to select its entire column.",
            SelectionMode.RECTANGLE: "Click and drag on Source to select a rectangular region [M].",
        }
        self._update_status(f"Selection mode: {mode.value.title()}. {guidance.get(mode, '')}")

    def _on_tile_clicked(self, tile_pos: TilePosition) -> None:
        """Handle single tile click in source grid"""
        mode = self.grid_view.selection_mode

        # In tile mode, immediately add/remove the tile
        if mode == SelectionMode.TILE:
            if self.arrangement_manager.is_tile_arranged(tile_pos):
                # Find where it is and remove it
                mapping = self.arrangement_manager.get_grid_mapping()
                items_to_remove = []
                for (tr, tc), (arr_type, key) in mapping.items():
                    if arr_type == ArrangementType.TILE and key == f"{tile_pos.row},{tile_pos.col}":
                        items_to_remove.append((tr, tc))

                if items_to_remove:
                    command = CanvasRemoveMultipleItemsCommand(
                        manager=self.arrangement_manager,
                        items_to_remove=items_to_remove,
                    )
                    self.undo_stack.push(command)
            else:
                # Add to next available slot using command
                command = AddMultipleTilesCommand(
                    manager=self.arrangement_manager,
                    tiles=[tile_pos],
                )
                self.undo_stack.push(command)

        # In ROW mode, add/remove the entire row
        elif mode == SelectionMode.ROW:
            row_tiles = self.arrangement_manager.get_row_tiles(tile_pos.row)
            self._toggle_tiles_arrangement(row_tiles, f"row {tile_pos.row}")

        # In COLUMN mode, add/remove the entire column
        elif mode == SelectionMode.COLUMN:
            col_tiles = self.arrangement_manager.get_column_tiles(tile_pos.col)
            self._toggle_tiles_arrangement(col_tiles, f"column {tile_pos.col}")

        # RECTANGLE mode: no click-to-add, only marquee selection

    def _toggle_tiles_arrangement(self, tiles: list[TilePosition], description: str) -> None:
        """Toggle a group of tiles between arranged/unarranged state.

        Args:
            tiles: List of tile positions to toggle
            description: Human-readable description for status message (e.g., "row 0", "column 3")
        """
        # Check if ALL tiles are already arranged
        all_arranged = all(self.arrangement_manager.is_tile_arranged(t) for t in tiles)

        if all_arranged:
            # Remove all - find their canvas positions
            mapping = self.arrangement_manager.get_grid_mapping()
            items_to_remove = []
            for tile in tiles:
                key = f"{tile.row},{tile.col}"
                for (tr, tc), (arr_type, k) in mapping.items():
                    if arr_type == ArrangementType.TILE and k == key:
                        items_to_remove.append((tr, tc))

            if items_to_remove:
                command = CanvasRemoveMultipleItemsCommand(
                    manager=self.arrangement_manager,
                    items_to_remove=items_to_remove,
                )
                self.undo_stack.push(command)
                self._update_status(f"Removed {description}")
        else:
            # Add unarranged tiles
            tiles_to_add = [t for t in tiles if not self.arrangement_manager.is_tile_arranged(t)]
            if tiles_to_add:
                command = AddMultipleTilesCommand(
                    manager=self.arrangement_manager,
                    tiles=tiles_to_add,
                )
                self.undo_stack.push(command)
                self._update_status(f"Added {description}")

    def _on_tiles_selected(self, tiles: list[TilePosition]) -> None:
        """Handle tile selection"""
        self._update_status(f"Selected {len(tiles)} tiles")

    def _add_selection(self):
        """Add current selection to arrangement canvas (next available slots)"""
        selection = list(self.grid_view.current_selection)

        if not selection:
            return

        # Sort selection to add in a sensible order
        selection.sort(key=lambda t: (t.row, t.col))

        # Filter out already arranged if desired?
        # Usually adding selection adds duplicates if allowed, or skips.
        # GridArrangementManager.add_tile usually allows duplicates if not checked.
        # But _add_tile_no_history checks is_tile_arranged? No, it just finds a slot.
        # Let's filter to avoid duplicates if that's the desired behavior.
        # The original code did: `if not self.arrangement_manager.is_tile_arranged(tile): self.arrangement_manager.add_tile(tile)`

        tiles_to_add = [t for t in selection if not self.arrangement_manager.is_tile_arranged(t)]

        if tiles_to_add:
            command = AddMultipleTilesCommand(
                manager=self.arrangement_manager,
                tiles=tiles_to_add,
            )
            self.undo_stack.push(command)
            self.grid_view.clear_selection()
            self._update_displays()
        else:
            self._update_status("Selected tiles are already arranged")

    def _remove_selection(self):
        """Remove current selection from arrangement grid mapping"""
        # 1. Check arrangement grid selection first (direct canvas deletion)
        if hasattr(self, "arrangement_grid"):
            canvas_selection = list(self.arrangement_grid.current_selection)
            if canvas_selection:
                items_to_remove = [(t.row, t.col) for t in canvas_selection]

                command = CanvasRemoveMultipleItemsCommand(
                    manager=self.arrangement_manager,
                    items_to_remove=items_to_remove,
                )
                self.undo_stack.push(command)

                self.arrangement_grid.clear_selection()
                self._update_displays()
                self._update_status(f"Removed {len(items_to_remove)} items from canvas")
                return

        # 2. Check source grid selection (remove instances of these source tiles from canvas)
        selection = list(self.grid_view.current_selection)

        if not selection:
            return

        # Find tiles in grid mapping that match these source tiles
        mapping = self.arrangement_manager.get_grid_mapping()
        to_remove = []
        for (tr, tc), (arr_type, key) in mapping.items():
            if arr_type == ArrangementType.TILE:
                try:
                    row, col = map(int, key.split(","))
                    if TilePosition(row, col) in selection:
                        to_remove.append((tr, tc))
                except ValueError:
                    continue

        if to_remove:
            command = CanvasRemoveMultipleItemsCommand(
                manager=self.arrangement_manager,
                items_to_remove=to_remove,
            )
            self.undo_stack.push(command)
            self._update_status(f"Removed {len(to_remove)} instances of selected source tiles")

        self.grid_view.clear_selection()
        self._update_displays()

    def _create_group(self):
        """Create a group from current selection"""
        selection = list(self.grid_view.current_selection)

        if len(selection) < 2:
            self._update_status("Select at least 2 tiles to create a group")
            return

        # Check if any tile is already arranged
        for tile in selection:
            if self.arrangement_manager.is_tile_arranged(tile):
                self._update_status("Some tiles are already arranged")
                return

        # Generate group ID
        group_id = f"group_{len(self.arrangement_manager.get_groups())}"
        group_name = f"Custom Group {len(self.arrangement_manager.get_groups()) + 1}"

        # Calculate bounding box
        min_row = min(t.row for t in selection)
        max_row = max(t.row for t in selection)
        min_col = min(t.col for t in selection)
        max_col = max(t.col for t in selection)

        width = max_col - min_col + 1
        height = max_row - min_row + 1

        # Create group
        group = TileGroup(
            id=group_id,
            tiles=selection,
            width=width,
            height=height,
            name=group_name,
        )

        command = AddGroupCommand(
            manager=self.arrangement_manager,
            group=group,
        )
        self.undo_stack.push(command)

        self._update_status(f"Created group with {len(selection)} tiles")
        self.grid_view.clear_selection()

    def _clear_arrangement(self):
        """Clear all arrangements"""
        if not self.arrangement_manager:
            return

        # Check if there's anything to clear
        if not self.arrangement_manager.get_arranged_tiles():
            self._update_status("Nothing to clear")
            return

        # Capture current state for undo
        tiles, groups, tile_to_group, order, grid_mapping = self.arrangement_manager.get_state_snapshot()

        command = ClearGridCommand(
            manager=self.arrangement_manager,
            previous_tiles=tiles,
            previous_groups=groups,
            previous_tile_to_group=tile_to_group,
            previous_order=order,
            previous_grid_mapping=grid_mapping,
        )
        self.undo_stack.push(command)

        self.grid_view.clear_selection()
        self._update_status("Cleared all arrangements")

    def _reset_layout(self) -> None:
        """Reset tiles to original extracted positions (1:1 mapping)."""
        if not self.arrangement_manager:
            return

        # Ask for confirmation
        result = QMessageBox.question(
            self,
            "Reset to 1:1",
            "Reset all tiles to their original extracted positions?\n\n"
            "This will create a 1:1 mapping from the source grid to the canvas and can be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if result != QMessageBox.StandardButton.Yes:
            return

        # Generate 1:1 state
        new_tiles = []
        new_grid_mapping = {}
        new_order = []

        for r in range(self.grid_view.grid_rows):
            for c in range(self.grid_view.grid_cols):
                pos = TilePosition(r, c)
                new_tiles.append(pos)
                item = (ArrangementType.TILE, f"{r},{c}")
                new_grid_mapping[(r, c)] = item
                new_order.append(item)

        command = RestoreGridStateCommand(
            manager=self.arrangement_manager,
            new_tiles=new_tiles,
            new_groups={},
            new_tile_to_group={},
            new_order=new_order,
            new_grid_mapping=new_grid_mapping,
        )
        self.undo_stack.push(command)

        # Sync width_spin to source grid columns for consistent 1:1 mapping
        source_cols = self.grid_view.grid_cols
        self.width_spin.setValue(source_cols)

        self.grid_view.clear_selection()
        self._update_status("Reset layout to 1:1 mapping")

    def _apply_overlay(self) -> None:
        """Apply overlay image to tiles, sampling and quantizing pixels."""
        if not self.overlay_layer.has_image():
            _ = QMessageBox.warning(
                self,
                "No Overlay",
                "Please import an overlay image first.\n\n"
                "The overlay image provides the new pixel data that will be "
                "written to each tile at its current canvas position.",
            )
            return

        if not self.arrangement_manager.get_arranged_tiles():
            _ = QMessageBox.warning(
                self,
                "No Tiles Placed",
                "Please arrange some tiles on the canvas first.\n\n"
                "Drag tiles from the source grid to the canvas to position them.",
            )
            return

        # Get palette for quantization (if palette mode is enabled)
        palette: list[tuple[int, int, int]] | None = None
        if self.colorizer.is_palette_mode() and self.colorizer.has_palettes():
            palette_idx = self.colorizer.get_selected_palette_index()
            palettes = self.colorizer.get_palettes()
            if palette_idx in palettes:
                palette = palettes[palette_idx]

        # Create ApplyOperation
        operation = ApplyOperation(
            overlay=self.overlay_layer,
            grid_mapping=self.arrangement_manager.get_grid_mapping(),
            tiles=self.tiles,
            tile_width=self.processor.tile_width,
            tile_height=self.processor.tile_height,
            palette=palette,
        )

        # Validate first
        warnings = operation.validate()

        if warnings:
            # Show warning dialog with details
            if not self._show_apply_warnings_dialog(warnings):
                return  # User cancelled

        # Execute Apply operation
        result = operation.execute(force=True)

        if not result.success:
            _ = QMessageBox.critical(
                self,
                "Apply Failed",
                f"Failed to apply overlay:\n\n{result.error_message}",
            )
            return

        # Store the result for retrieval
        self._apply_result = result

        # Use undoable command to update tiles
        command = ApplyOverlayCommand(
            tiles=self.tiles,
            modified_tiles=result.modified_tiles,
            callback=self._update_displays,
        )
        self.undo_stack.push(command)

        # Update status with result summary
        num_modified = len(result.modified_tiles)
        warning_count = len(result.warnings)
        status = f"Applied overlay to {num_modified} tile(s)"
        if warning_count > 0:
            status += f" ({warning_count} warning(s))"
        self._update_status(status)

        # Show success message
        _ = QMessageBox.information(
            self,
            "Apply Complete",
            f"Successfully applied overlay to {num_modified} tile(s).\n\n"
            "The modified tile data is available for export.",
        )

    def _show_apply_warnings_dialog(self, warnings: list[ApplyWarning]) -> bool:
        """Show warning dialog for Apply operation.

        Args:
            warnings: List of ApplyWarning objects

        Returns:
            True if user wants to proceed, False to cancel
        """
        # Build warning message
        lines = ["The following issues were detected:\n"]
        for warning in warnings:
            if warning.type == WarningType.UNCOVERED:
                lines.append(f"• {warning.message}")
                lines.append("  Uncovered tiles will be skipped.\n")
            elif warning.type == WarningType.UNPLACED:
                lines.append(f"• {warning.message}")
                lines.append("  Unplaced tiles will not be modified.\n")
            elif warning.type == WarningType.PALETTE_MISMATCH:
                lines.append(f"• {warning.message}")
                lines.append("  Some colors may be approximated.\n")

        lines.append("\nDo you want to proceed anyway?")

        result = QMessageBox.warning(
            self,
            "Apply Warnings",
            "\n".join(lines),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return result == QMessageBox.StandardButton.Yes

    def _on_arrangement_changed(self):
        """Handle arrangement change"""
        self._update_displays()
        if self.export_btn:
            self.export_btn.setEnabled(self.arrangement_manager.get_arranged_count() > 0)

    def _on_overlay_changed(self, *_: object) -> None:
        """Handle overlay property changes (position, opacity, visibility, image)."""
        self._update_arrangement_canvas()

    def _on_palette_mode_changed(self, enabled: bool):
        """Handle palette mode change"""
        self._update_displays()

    def toggle_palette_application(self) -> None:
        """Toggle between grayscale and colorized display."""
        palette_enabled = self.colorizer.toggle_palette_mode()
        # Signal handler _on_palette_mode_changed already calls _update_displays()

        if palette_enabled:
            palette_idx = self.colorizer.get_selected_palette_index()
            self.setWindowTitle(f"Arrange Sprite Grid - Palette {palette_idx}")
            self._update_status(f"Palette mode: Palette {palette_idx} applied | Press C to toggle, P to cycle")
        else:
            self.setWindowTitle("Arrange Sprite Grid - Grayscale")
            self._update_status("Grayscale mode: Original sprite colors | Press C to toggle palette")

    def _cycle_palette(self) -> None:
        """Cycle through available palettes."""
        new_palette_idx = self.colorizer.cycle_palette()
        self.setWindowTitle(f"Arrange Sprite Grid - Palette {new_palette_idx}")
        self._update_status(f"Palette mode: Palette {new_palette_idx} applied | Press C to toggle, P to cycle")

    def _get_item_preview(self, arr_type: ArrangementType, key: str) -> QPixmap:
        """Generate a preview pixmap for an arrangement item"""
        preview_img = None

        if arr_type == ArrangementType.TILE:
            row, col = map(int, key.split(","))
            pos = TilePosition(row, col)
            tile_img = self.tiles.get(pos)
            if tile_img:
                if self.colorizer.is_palette_mode():
                    preview_img = self.colorizer.get_display_image(row, tile_img)
                else:
                    preview_img = tile_img

        elif arr_type == ArrangementType.ROW:
            row_idx = int(key)
            if self.original_image:
                tw = self.processor.tile_width
                th = self.processor.tile_height
                # Crop the row from original image
                crop_rect = (0, row_idx * th, self.original_image.width, (row_idx + 1) * th)
                row_img = self.original_image.crop(crop_rect)
                if self.colorizer.is_palette_mode():
                    preview_img = self.colorizer.get_display_image(row_idx, row_img)
                else:
                    preview_img = row_img

        elif arr_type == ArrangementType.COLUMN:
            col_idx = int(key)
            if self.original_image:
                tw = self.processor.tile_width
                th = self.processor.tile_height
                # Crop the column
                crop_rect = (col_idx * tw, 0, (col_idx + 1) * tw, self.original_image.height)
                col_img = self.original_image.crop(crop_rect)
                # For columns, palette is tricky as it spans rows. Use row 0 for preview.
                if self.colorizer.is_palette_mode():
                    preview_img = self.colorizer.get_display_image(0, col_img)
                else:
                    preview_img = col_img

        elif arr_type == ArrangementType.GROUP:
            group = self.arrangement_manager.get_groups().get(key)
            if group:
                # Use preview generator to create a small image for the group
                preview_img = self.preview_generator._create_arranged_image_with_spacing(
                    [(t, self.tiles[t]) for t in group.tiles],
                    self.processor.tile_width,
                    self.processor.tile_height,
                    group.width,
                    0,
                )

        if preview_img:
            pixmap = self._create_pixmap_from_image(preview_img)
            # Scale to icon size (64x64)
            return pixmap.scaled(64, 64, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.FastTransformation)

        # Return empty pixmap if failed
        empty = QPixmap(64, 64)
        empty.fill(Qt.GlobalColor.transparent)
        return empty

    def _on_tiles_dropped_on_canvas(
        self,
        source_tiles: list[TilePosition],
        anchor: TilePosition,
        target_anchor: TilePosition,
        source_widget: QObject,
    ):
        """Handle tiles dropped on the arrangement canvas"""

        # Calculate offset from anchor for each tile
        # target_tile = target_anchor + (tile - anchor)

        # Check source
        is_internal = source_widget == self.arrangement_grid

        if is_internal:
            # MOVE tiles within canvas
            # Moving multiple tiles is complex if they overlap.
            # Strategy: Collect all moves, execute them.
            # For Undo: We need a CompositeCommand or just push multiple commands.
            # But pushing multiple fills the stack.
            # Better: One command that moves multiple?
            # For now, let's just handle them one by one.

            # To prevent overwriting ourselves during the move (e.g. shift right),
            # we should process based on direction, or remove all first then add.
            # Remove all first is safer.

            # Actually, `CanvasMoveItemsCommand` handles one item.
            # Let's iterate.

            for src_tile in source_tiles:
                # Calculate target
                dr = src_tile.row - anchor.row
                dc = src_tile.col - anchor.col
                target_r = target_anchor.row + dr
                target_c = target_anchor.col + dc

                # Check bounds
                if not (0 <= target_r < 32 and 0 <= target_c < self.arrangement_grid.grid_cols):  # Use dynamic height?
                    continue

                src_pos = (src_tile.row, src_tile.col)
                tgt_pos = (target_r, target_c)

                if src_pos == tgt_pos:
                    continue

                # Skip if src not in mapping (shouldn't happen)
                if not self.arrangement_manager.get_item_at(*src_pos):
                    continue

                command = CanvasMoveItemsCommand(
                    manager=self.arrangement_manager, source_pos=src_pos, target_pos=tgt_pos
                )
                self.undo_stack.push(command)

        else:
            # ADD tiles from source grid
            for src_tile in source_tiles:
                # Calculate target
                dr = src_tile.row - anchor.row
                dc = src_tile.col - anchor.col
                target_r = target_anchor.row + dr
                target_c = target_anchor.col + dc

                # Check bounds
                # We used 32 as fixed height in _create_arrangement_grid_group,
                # but we should probably allow expansion or check against limits.
                # GridGraphicsView has grid_rows/cols.
                if not (
                    0 <= target_r < self.arrangement_grid.grid_rows and 0 <= target_c < self.arrangement_grid.grid_cols
                ):
                    continue

                # Create Place Command
                # We need to know what we are placing.
                # From source grid, it's always TILE type for now.
                # (unless we support dragging rows/groups from source list - but that's gone)

                item_key = f"{src_tile.row},{src_tile.col}"

                command = CanvasPlaceItemsCommand(
                    manager=self.arrangement_manager,
                    target_pos=(target_r, target_c),
                    item_type=ArrangementType.TILE,
                    item_key=item_key,
                )
                self.undo_stack.push(command)

        self._update_displays()

    def _on_arrangement_tile_clicked(self, tile_pos: TilePosition) -> None:
        """Handle click in arrangement canvas (selection/focus)"""
        # Instead of removing, we just ensure it's selected if not already
        if self.arrangement_manager.get_item_at(tile_pos.row, tile_pos.col):
            # In TILE mode, clicking can select the tile on canvas
            if tile_pos not in self.arrangement_grid.current_selection:
                # Use shift to add to selection if desired, or just select single
                # For now, let's just make it select single tile to avoid confusion
                self.arrangement_grid.current_selection.add(tile_pos)
                self.arrangement_grid._update_selection_display()

            self._update_status(f"Canvas item selected at ({tile_pos.row}, {tile_pos.col})")
        else:
            self.arrangement_grid.clear_selection()

    def _update_displays(self):
        """Update all display elements"""
        # Update source grid view (highlights/dimming)
        arranged_tiles = self.arrangement_manager.get_arranged_tiles()
        self.grid_view.highlight_arranged_tiles(arranged_tiles, manager=self.arrangement_manager)

        # Update arrangement canvas
        self._update_arrangement_canvas()

        # Update preview
        self._update_preview()

    def _update_arrangement_canvas(self):
        """Update the arrangement canvas view"""
        if not hasattr(self, "arrangement_grid"):
            return

        scene = self.arrangement_scene
        scene.clear()

        # Re-add background grid or placeholder if needed
        # (GridGraphicsView handles its own grid lines)

        mapping = self.arrangement_manager.get_grid_mapping()

        for (r, c), (arr_type, key) in mapping.items():
            # Get the image for this item
            pixmap = self._get_item_preview_full(arr_type, key)
            if pixmap:
                item = QGraphicsPixmapItem(pixmap)
                item.setPos(c * self.processor.tile_width, r * self.processor.tile_height)
                scene.addItem(item)

                # Add a border or highlight
                rect = QGraphicsRectItem(
                    c * self.processor.tile_width,
                    r * self.processor.tile_height,
                    self.processor.tile_width,
                    self.processor.tile_height,
                )
                rect.setPen(QPen(self.grid_view.arranged_color, 1))
                scene.addItem(rect)

        # Render overlay if visible and has image
        if self.overlay_layer.visible and self.overlay_layer.has_image():
            overlay_image = self.overlay_layer.image
            if overlay_image is not None:
                # Convert PIL Image to QPixmap
                overlay_pixmap = self._create_pixmap_from_image(overlay_image)
                if overlay_pixmap:
                    overlay_item = QGraphicsPixmapItem(overlay_pixmap)
                    overlay_item.setPos(self.overlay_layer.x, self.overlay_layer.y)
                    overlay_item.setOpacity(self.overlay_layer.opacity)
                    scene.addItem(overlay_item)

    def _get_item_preview_full(self, arr_type: ArrangementType, key: str) -> QPixmap | None:
        """Get the full-size preview pixmap for an arrangement item"""
        img = None
        if arr_type == ArrangementType.TILE:
            row, col = map(int, key.split(","))
            pos = TilePosition(row, col)
            img = self.tiles.get(pos)
            if img and self.colorizer.is_palette_mode():
                img = self.colorizer.get_display_image(row, img)
        # Support for ROW/COLUMN could be added here if needed for canvas placement

        if img:
            return self._create_pixmap_from_image(img)
        return None

    def _update_preview(self):
        """Update the arrangement preview"""
        width = self.width_spin.value() if hasattr(self, "width_spin") else min(16, self.processor.grid_cols)

        # Get all arranged tiles with their images
        arranged_tiles = self.arrangement_manager.get_arranged_tiles()
        tiles_with_images = []
        for t in arranged_tiles:
            if t in self.tiles:
                tiles_with_images.append((t, self.tiles[t]))

        arranged_image = self.preview_generator._create_arranged_image_with_spacing(
            tiles_with_images,
            self.processor.tile_width,
            self.processor.tile_height,
            width,
            spacing=2,
        )

        if arranged_image:
            pixmap = self._create_pixmap_from_image(arranged_image)
            # Scale for preview
            scaled = pixmap.scaled(
                pixmap.width() * 2,
                pixmap.height() * 2,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.FastTransformation,
            )
            if self.preview_label:
                self.preview_label.setPixmap(scaled)
        else:
            if self.preview_label:
                self.preview_label.clear()
            if self.preview_label:
                self.preview_label.setText("No arrangement")

    def _create_pixmap_from_image(self, image: Image.Image) -> QPixmap:
        """Convert PIL Image to QPixmap using centralized utility."""
        qimage = pil_to_qimage(image)
        return QPixmap.fromImage(qimage)

    def _export_arrangement(self) -> None:
        """Export the current arrangement."""
        if self.arrangement_manager.get_arranged_count() == 0:
            self._update_status("No tiles arranged for export")
            return

        # Check if we have valid data
        if self.original_image is None:
            self._update_status("Cannot export: No valid sprite data")
            return

        try:
            # Create arranged image
            width = self.width_spin.value() if hasattr(self, "width_spin") else min(16, self.processor.grid_cols)
            arranged_image = self.preview_generator.create_grid_arranged_image(
                self.processor, self.arrangement_manager, width=width
            )

            if arranged_image:
                self.output_path = self.preview_generator.export_grid_arrangement(
                    self.sprite_path, arranged_image, "grid"
                )

                # Store arrangement result before accepting
                self._arrangement_result = self.get_arrangement_result()

                self._update_status(f"Exported to {Path(self.output_path).name}")
                self.accept()
            else:
                self._update_status("Error: Failed to create arranged image")

        except (OSError, ValueError, RuntimeError) as e:
            self._update_status(f"Export failed: {e!s}")
            _ = QMessageBox.warning(self, "Export Error", f"Failed to export arrangement:\n{e!s}")

    def _update_status(self, message: str):
        """Update status bar message"""
        self.update_status(message)

    def _update_zoom_level_display(self):
        """Update the zoom level display"""
        if hasattr(self, "zoom_level_label"):
            zoom_percent = int(self.grid_view.get_zoom_level() * 100)
            if self.zoom_level_label:
                self.zoom_level_label.setText(f"{zoom_percent}%")

    def _on_zoom_changed(self, zoom_level: int):
        """Handle zoom level change"""
        self._update_zoom_level_display()

    @override
    def keyPressEvent(self, a0: QKeyEvent | None):
        """Handle keyboard shortcuts"""
        if not a0:
            return

        modifiers = a0.modifiers()
        key = a0.key()

        # Undo/Redo shortcuts
        if modifiers == Qt.KeyboardModifier.ControlModifier:
            if key == Qt.Key.Key_Z:
                self._on_undo()
                return
            elif key == Qt.Key.Key_Y:
                self._on_redo()
                return
        elif modifiers == (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier):
            if key == Qt.Key.Key_Z:
                self._on_redo()
                return

        # Overlay nudging with arrow keys (only if overlay has image)
        if self.overlay_layer.has_image():
            # Determine nudge amount: 10px with Shift, 1px without
            nudge_amount = 10 if modifiers & Qt.KeyboardModifier.ShiftModifier else 1

            if key == Qt.Key.Key_Left:
                self.overlay_layer.nudge(-nudge_amount, 0)
                return
            elif key == Qt.Key.Key_Right:
                self.overlay_layer.nudge(nudge_amount, 0)
                return
            elif key == Qt.Key.Key_Up:
                self.overlay_layer.nudge(0, -nudge_amount)
                return
            elif key == Qt.Key.Key_Down:
                self.overlay_layer.nudge(0, nudge_amount)
                return

        # Selection Mode Shortcuts
        if key == Qt.Key.Key_T:
            self.mode_toggle.set_current_data(SelectionMode.TILE)
        elif key == Qt.Key.Key_R:
            self.mode_toggle.set_current_data(SelectionMode.ROW)
        elif key == Qt.Key.Key_C:
            self.mode_toggle.set_current_data(SelectionMode.COLUMN)
        elif key == Qt.Key.Key_M:
            self.mode_toggle.set_current_data(SelectionMode.RECTANGLE)

        # Other shortcuts
        elif key == Qt.Key.Key_G:
            # Toggle grid (already handled by view)
            pass
        elif key == Qt.Key.Key_O:
            # Toggle palette (O for colorize On/Off)
            self.toggle_palette_application()
        elif key == Qt.Key.Key_P and self.colorizer.is_palette_mode():
            # Cycle palette
            self._cycle_palette()
        elif key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            # Add selection (advertised in legend/tooltip)
            self._add_selection()
        elif key == Qt.Key.Key_Delete:
            # Remove selection
            self._remove_selection()
        elif key == Qt.Key.Key_Escape:
            # Clear selection
            self.grid_view.clear_selection()
        else:
            # Let the grid view handle zoom shortcuts
            self.grid_view.keyPressEvent(a0)
            self._update_zoom_level_display()
            super().keyPressEvent(a0)

    def set_palettes(self, palettes_dict: dict[int, Any]):  # pyright: ignore[reportExplicitAny] - palette data
        """Set available palettes for colorization"""
        self.colorizer.set_palettes(palettes_dict)
        self._update_displays()

    def get_arranged_path(self) -> str | None:
        """Get the path to the exported arrangement."""
        return self.output_path

    def get_arrangement_result(self) -> ArrangementResult | None:
        """Get the arrangement result for workflow integration.

        Returns:
            ArrangementResult containing bridge and metadata, or None if no arrangement.
        """
        if self.arrangement_manager.get_arranged_count() == 0:
            return None

        # Import here to avoid circular dependency
        from ui.sprite_editor.services.arrangement_bridge import ArrangementBridge

        bridge = ArrangementBridge(self.arrangement_manager, self.processor)
        metadata = self.preview_generator.create_arrangement_preview_data(self.arrangement_manager, self.processor)

        # Include modified tiles if any Apply operation was performed
        # self.tiles contains the current pixel state (potentially modified by ApplyOverlayCommand)
        modified_tiles = self.tiles.copy() if self._apply_result else None

        return ArrangementResult(
            bridge=bridge,
            metadata=metadata,
            logical_width=self.width_spin.value() if hasattr(self, "width_spin") else min(16, self.processor.grid_cols),
            modified_tiles=modified_tiles,
        )

    @property
    def arrangement_result(self) -> ArrangementResult | None:
        """Access stored arrangement result after dialog closes."""
        return getattr(self, "_arrangement_result", None)

    @property
    def apply_result(self) -> ApplyResult | None:
        """Access the Apply operation result (modified tiles) after Apply is executed.

        Returns:
            ApplyResult containing modified tiles, or None if Apply wasn't executed.
        """
        return self._apply_result

    @override
    def closeEvent(self, a0: QCloseEvent | None) -> None:
        """Handle dialog close event with proper cleanup"""
        self._cleanup_resources()
        if a0:
            super().closeEvent(a0)

    def _disconnect_signals(self) -> None:
        """Disconnect all signals to prevent memory leaks."""
        # Disconnect arrangement manager signals
        if self.arrangement_manager:
            safe_disconnect(self.arrangement_manager.arrangement_changed)

        # Disconnect colorizer signals
        safe_disconnect(self.colorizer.palette_mode_changed)

        # Disconnect mode toggle signals
        safe_disconnect(self.mode_toggle.selection_changed)

        # Disconnect grid view signals
        safe_disconnect(self.grid_view.tile_clicked)
        safe_disconnect(self.grid_view.tiles_selected)
        safe_disconnect(self.grid_view.zoom_changed)

        # Disconnect button signals
        for btn_name in (
            "add_btn",
            "remove_btn",
            "create_group_btn",
            "clear_btn",
            "zoom_out_btn",
            "zoom_in_btn",
            "zoom_fit_btn",
            "zoom_reset_btn",
        ):
            safe_disconnect(getattr(self, btn_name).clicked)

    def _cleanup_resources(self) -> None:
        """Clean up resources to prevent memory leaks"""
        # Disconnect signals first
        self._disconnect_signals()

        # Clear colorizer cache
        self.colorizer.clear_cache()

        # Clear grid view selections BEFORE clearing scene (to avoid double deletion)
        self.grid_view.clear_selection()
        self.grid_view.selection_rects.clear()

        # Clear graphics scene items
        if self.scene:
            self.scene.clear()

        # Clear processor data
        self.processor.tiles.clear()
        self.processor.original_image = None

        # Clear arrangement manager
        if self.arrangement_manager:
            self.arrangement_manager.clear()
