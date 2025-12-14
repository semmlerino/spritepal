"""
Row Arrangement Dialog for SpritePal
Intuitive drag-and-drop interface for arranging sprite rows
"""
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from utils.logging_config import get_logger

logger = get_logger(__name__)

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QKeyEvent, QPixmap
from PySide6.QtWidgets import (
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
)
from typing_extensions import override

from ui.styles.theme import COLORS

from .components import SplitterDialog
from .row_arrangement import (
    ArrangementManager,
    PaletteColorizer,
    PreviewGenerator,
    RowImageProcessor,
)
from .widgets.row_widgets import DragDropListWidget, RowPreviewWidget

if TYPE_CHECKING:
    from PIL import Image

class RowArrangementDialog(SplitterDialog):
    """Dialog for arranging sprite rows with intuitive drag-and-drop interface"""

    def __init__(self, sprite_path: str, tiles_per_row: int = 16, parent: Any | None = None) -> None:
        # Step 1: Declare instance variables BEFORE super().__init__()
        self.sprite_path: str | None = sprite_path
        self.tiles_per_row: int = tiles_per_row
        self.original_image: Image.Image | None = None
        self.tile_rows: list[dict[str, Any]] = []
        self.output_path: str | None = None
        self.tile_width: int | None = None  # Will be calculated based on image width
        self.tile_height: int | None = None  # Will be calculated based on tile width

        # Initialize components
        self.image_processor: RowImageProcessor = RowImageProcessor()
        self.arrangement_manager: ArrangementManager = ArrangementManager()
        self.colorizer: PaletteColorizer = PaletteColorizer()
        self.preview_generator: PreviewGenerator = PreviewGenerator(self.colorizer)

        # Initialize UI components that will be created in _setup_ui
        self.available_list: DragDropListWidget | None = None
        self.arranged_list: DragDropListWidget | None = None

        # Load sprite data before creating UI
        self._load_sprite_data()

        # Step 2: Call parent init (this will call _setup_ui)
        super().__init__(
            parent=parent,
            title="Arrange Sprite Rows - Grayscale",
            modal=True,
            size=(1400, 800),
            with_status_bar=True,
            orientation=Qt.Orientation.Vertical,
            splitter_handle_width=8,
        )

        # Connect signals after UI is created
        self.arrangement_manager.arrangement_changed.connect(
            self._on_arrangement_changed
        )
        self.colorizer.palette_mode_changed.connect(self._on_palette_mode_changed)
        self.colorizer.palette_index_changed.connect(self._on_palette_index_changed)

        self._update_panel_titles()

        # Update status based on whether sprite loading was successful
        if self.original_image is not None and self.tile_rows:
            self.update_status(
                "Drag rows from left to right to arrange them | Press C to toggle palette, P to cycle palettes"
            )
        else:
            self.update_status("Error: Unable to load sprite file. Dialog opened in error state.")

    def _load_sprite_data(self):
        """Load sprite image and extract rows"""
        if self.sprite_path is None:
            return
        try:
            # Use image processor to load and extract rows
            self.original_image, self.tile_rows = (
                self.image_processor.process_sprite_sheet(
                    self.sprite_path, self.tiles_per_row
                )
            )

            # Get tile dimensions from processor
            self.tile_width = self.image_processor.tile_width
            self.tile_height = self.image_processor.tile_height

        except (OSError, ValueError, RuntimeError) as e:
            # CRITICAL FIX FOR BUG #21: Show error dialog and set up minimal state to prevent crashes
            _ = QMessageBox.critical(
                self, "Error Loading Sprite", f"Failed to load sprite file:\n{e!s}"
            )
            # Set up minimal state to prevent crashes
            self.original_image = None
            self.tile_rows = []
            self.tile_width = 8  # Default tile width
            self.tile_height = 8  # Default tile height
            # Log the error for debugging
            logger.exception("Error loading sprite data: %s", e)
            # Don't return here - continue with dialog setup but in error state

    @override
    def _setup_ui(self):
        """Set up the dialog UI using SplitterDialog panels"""
        # Call parent _setup_ui first to initialize the main splitter
        super()._setup_ui()

        # Create horizontal content splitter for Available/Arranged panels
        content_splitter = self.add_horizontal_splitter(handle_width=8)

        # Left panel - Available rows
        self.left_panel: QGroupBox = QGroupBox("Available Rows")
        self.left_panel.setMinimumWidth(
            380
        )  # Increased to accommodate wider thumbnails
        left_layout = QVBoxLayout(self.left_panel)

        # Available rows list
        self.available_list = DragDropListWidget(accept_external_drops=False)
        self.available_list.itemDoubleClicked.connect(self._add_row_to_arrangement)
        _ = self.available_list.itemSelectionChanged.connect(
            self._on_available_selection_changed
        )
        # Add spacing between list items
        self.available_list.setSpacing(6)
        left_layout.addWidget(self.available_list)

        # Populate available rows
        self._populate_available_rows()

        # Quick action buttons
        buttons_layout = QHBoxLayout()

        self.add_all_btn: QPushButton = QPushButton("Add All →")
        _ = self.add_all_btn.clicked.connect(self._add_all_rows)
        buttons_layout.addWidget(self.add_all_btn)

        self.add_selected_btn: QPushButton = QPushButton("Add Selected →")
        _ = self.add_selected_btn.clicked.connect(self._add_selected_rows)
        buttons_layout.addWidget(self.add_selected_btn)

        left_layout.addLayout(buttons_layout)

        # Right panel - Arranged rows
        self.right_panel: QGroupBox = QGroupBox("Arranged Rows")
        self.right_panel.setMinimumWidth(
            380
        )  # Increased to accommodate wider thumbnails
        right_layout = QVBoxLayout(self.right_panel)

        # Arranged rows list
        self.arranged_list = DragDropListWidget(accept_external_drops=True)
        self.arranged_list.external_drop.connect(self._add_row_to_arrangement)
        self.arranged_list.item_dropped.connect(self._refresh_arrangement)
        self.arranged_list.itemDoubleClicked.connect(self._remove_row_from_arrangement)
        _ = self.arranged_list.itemSelectionChanged.connect(
            self._on_arranged_selection_changed
        )
        # Add spacing between list items
        self.arranged_list.setSpacing(6)
        right_layout.addWidget(self.arranged_list)

        # Arrangement controls
        controls_layout = QHBoxLayout()

        self.clear_btn: QPushButton = QPushButton("Clear All")
        _ = self.clear_btn.clicked.connect(self._clear_arrangement)
        controls_layout.addWidget(self.clear_btn)

        self.remove_selected_btn: QPushButton = QPushButton("← Remove Selected")
        _ = self.remove_selected_btn.clicked.connect(self._remove_selected_rows)
        controls_layout.addWidget(self.remove_selected_btn)

        right_layout.addLayout(controls_layout)

        # Add panels to horizontal content splitter
        content_splitter.addWidget(self.left_panel)
        content_splitter.addWidget(self.right_panel)
        content_splitter.setStretchFactor(0, 1)
        content_splitter.setStretchFactor(1, 1)

        # Preview area
        preview_group = QGroupBox("Preview")
        preview_group.setMinimumHeight(150)
        preview_layout = QVBoxLayout(preview_group)

        # Preview scroll area (now resizable)
        scroll_area = QScrollArea(self)
        self.preview_label: QLabel = QLabel(self)
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        if self.preview_label:
            self.preview_label.setStyleSheet(
            f"background-color: {COLORS['background']}; border: 1px solid {COLORS['border']};"
        )
        scroll_area.setWidget(self.preview_label)
        scroll_area.setWidgetResizable(True)
        # Removed setMaximumHeight to allow resizing
        preview_layout.addWidget(scroll_area)

        # Add content and preview to main vertical splitter
        # Main splitter is already created by SplitterDialog in vertical orientation
        self.add_panel(content_splitter, stretch_factor=7)  # 70% for content
        self.add_panel(preview_group, stretch_factor=3)     # 30% for preview

        # Add custom buttons using SplitterDialog's button system
        self.export_btn: QPushButton = self.add_button("Export Arranged", callback=self._export_arranged)
        if self.export_btn:
            self.export_btn.setEnabled(False)

        # Initial preview
        self._update_preview()

    def _populate_available_rows(self):
        """Populate the available rows list"""
        if self.available_list:
            self.available_list.clear()

        for row_data in self.tile_rows:
            row_index = row_data["index"]
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, row_index)

            # Get the appropriate display image (grayscale or colorized)
            display_image = self._get_display_image_for_row(row_index)
            if display_image is None:
                continue

            # Create enhanced thumbnail widget
            # (selection state will be updated by selection handler)
            thumbnail = RowPreviewWidget(
                row_index,
                display_image,
                row_data["tiles"],
                False,  # Initial state, will be updated by selection handler
            )

            item.setSizeHint(thumbnail.sizeHint())
            if self.available_list:
                self.available_list.addItem(item)
                self.available_list.setItemWidget(item, thumbnail)

    def _populate_arranged_rows(self):
        """Populate the arranged rows list"""
        if self.arranged_list:
            self.arranged_list.clear()

        for row_index in self.arrangement_manager.get_arranged_indices():
            if row_index < len(self.tile_rows):
                row_data = self.tile_rows[row_index]
                item = QListWidgetItem()
                item.setData(Qt.ItemDataRole.UserRole, row_index)

                # Get the appropriate display image (grayscale or colorized)
                display_image = self._get_display_image_for_row(row_index)
                if display_image is None:
                    continue

                # Create thumbnail widget
                # (selection state will be updated by selection handler)
                thumbnail = RowPreviewWidget(
                    row_index,
                    display_image,
                    row_data["tiles"],
                    False,  # Initial state, will be updated by selection handler
                )

                item.setSizeHint(thumbnail.sizeHint())
                if self.arranged_list:
                    self.arranged_list.addItem(item)
                    self.arranged_list.setItemWidget(item, thumbnail)

    def _on_available_selection_changed(self):
        """Handle selection change in available rows list"""
        if self.available_list:
            self._update_row_selection_state(self.available_list)

    def _on_arranged_selection_changed(self):
        """Handle selection change in arranged rows list"""
        if self.arranged_list:
            self._update_row_selection_state(self.arranged_list)

    def _update_row_selection_state(self, list_widget: DragDropListWidget) -> None:
        """Update the visual selection state of row preview widgets"""
        for i in range(list_widget.count()):
            item = list_widget.item(i)
            widget = list_widget.itemWidget(item)
            if widget and isinstance(widget, RowPreviewWidget):
                is_selected = item.isSelected()
                widget.set_selected(is_selected)

    def _add_row_to_arrangement(self, row_index: int | QListWidgetItem) -> None:
        """Add a row to the arrangement"""
        actual_row_index: int
        if isinstance(row_index, QListWidgetItem):
            # Handle double-click from available list
            actual_row_index = row_index.data(Qt.ItemDataRole.UserRole)
        else:
            actual_row_index = row_index

        if self.arrangement_manager.add_row(actual_row_index):
            self._refresh_ui()
            self._update_status(
                f"Added row {actual_row_index} to arrangement ({self.arrangement_manager.get_arranged_count()} total)"
            )

    def _remove_row_from_arrangement(self, item: QListWidgetItem) -> None:
        """Remove a row from the arrangement"""
        row_index = item.data(Qt.ItemDataRole.UserRole)
        if self.arrangement_manager.remove_row(row_index):
            self._refresh_ui()
            self._update_status(
                f"Removed row {row_index} from arrangement ({self.arrangement_manager.get_arranged_count()} remaining)"
            )

    def _add_all_rows(self):
        """Add all rows to arrangement"""
        row_indices = [row_data["index"] for row_data in self.tile_rows]
        self.arrangement_manager.add_multiple_rows(row_indices)
        self._refresh_ui()
        self._update_status(
            f"Added all rows to arrangement ({self.arrangement_manager.get_arranged_count()} total)"
        )

    def _add_selected_rows(self):
        """Add selected rows to arrangement"""
        if self.available_list is None:
            return
        selected_items = self.available_list.selectedItems()
        row_indices = [item.data(Qt.ItemDataRole.UserRole) for item in selected_items]

        added_count = self.arrangement_manager.add_multiple_rows(row_indices)

        if added_count > 0:
            self._refresh_ui()
            self._update_status(f"Added {added_count} selected rows to arrangement")

    def _remove_selected_rows(self):
        """Remove selected rows from arrangement"""
        if self.arranged_list is None:
            return
        selected_items = self.arranged_list.selectedItems()
        row_indices = [item.data(Qt.ItemDataRole.UserRole) for item in selected_items]

        removed_count = self.arrangement_manager.remove_multiple_rows(row_indices)

        if removed_count > 0:
            self._refresh_ui()
            self._update_status(
                f"Removed {removed_count} selected rows from arrangement"
            )

    def _clear_arrangement(self):
        """Clear all arranged rows"""
        if self.arrangement_manager:
            self.arrangement_manager.clear()
        self._refresh_ui()
        self._update_status("Cleared all arranged rows")

    def _refresh_arrangement(self):
        """Refresh arrangement after internal reordering"""
        if self.arranged_list is None:
            return
        # Get current order from the list widget
        new_order = []
        for i in range(self.arranged_list.count()):
            item = self.arranged_list.item(i)
            row_index = item.data(Qt.ItemDataRole.UserRole)
            new_order.append(row_index)

        self.arrangement_manager.reorder_rows(new_order)
        self._update_preview()
        self._update_status("Reordered rows")

    def _refresh_ui(self):
        """Refresh both lists and preview"""
        self._populate_available_rows()
        self._populate_arranged_rows()
        self._update_preview()
        self._update_panel_titles()

        # Update export button state
        if self.export_btn:
            self.export_btn.setEnabled(self.arrangement_manager.get_arranged_count() > 0)

    def _update_preview(self):
        """Update the preview with current arrangement"""
        if self.arrangement_manager.get_arranged_count() == 0:
            self._show_original_preview()
            return

        # Create arranged image
        arranged_image = self._create_arranged_image()

        if arranged_image:
            # Convert to QPixmap
            if arranged_image.mode == "RGBA":
                # For RGBA images, use appropriate format
                qimage = QImage(
                    arranged_image.tobytes(),
                    arranged_image.width,
                    arranged_image.height,
                    arranged_image.width * 4,  # 4 bytes per pixel for RGBA
                    QImage.Format.Format_RGBA8888,
                )
            elif arranged_image.mode == "P":
                img_rgb = arranged_image.convert("L")
                qimage = QImage(
                    img_rgb.tobytes(),
                    img_rgb.width,
                    img_rgb.height,
                    img_rgb.width,
                    QImage.Format.Format_Grayscale8,
                )
            else:
                qimage = QImage(
                    arranged_image.tobytes(),
                    arranged_image.width,
                    arranged_image.height,
                    arranged_image.width,
                    QImage.Format.Format_Grayscale8,
                )

            pixmap = QPixmap.fromImage(qimage)

            # Scale for preview
            scaled_pixmap = pixmap.scaled(
                pixmap.width() * 3,
                pixmap.height() * 3,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.FastTransformation,
            )

            if self.preview_label:
                self.preview_label.setPixmap(scaled_pixmap)

    def _show_original_preview(self):
        """Show original sprite sheet in preview"""
        if self.original_image:
            # Apply palette to original image if enabled
            display_image = self.original_image
            if self.colorizer.is_palette_mode():
                colorized = self.preview_generator.apply_palette_to_full_image(
                    self.original_image
                )
                if colorized:
                    display_image = colorized

            # Convert to QPixmap
            if display_image.mode == "RGBA":
                # For RGBA images, use appropriate format
                qimage = QImage(
                    display_image.tobytes(),
                    display_image.width,
                    display_image.height,
                    display_image.width * 4,  # 4 bytes per pixel for RGBA
                    QImage.Format.Format_RGBA8888,
                )
            elif display_image.mode == "P":
                img_rgb = display_image.convert("L")
                qimage = QImage(
                    img_rgb.tobytes(),
                    img_rgb.width,
                    img_rgb.height,
                    img_rgb.width,
                    QImage.Format.Format_Grayscale8,
                )
            else:
                qimage = QImage(
                    display_image.tobytes(),
                    display_image.width,
                    display_image.height,
                    display_image.width,
                    QImage.Format.Format_Grayscale8,
                )

            pixmap = QPixmap.fromImage(qimage)

            # Scale for preview
            scaled_pixmap = pixmap.scaled(
                pixmap.width() * 3,
                pixmap.height() * 3,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.FastTransformation,
            )

            if self.preview_label:
                self.preview_label.setPixmap(scaled_pixmap)

    def _create_arranged_image(self):
        """Create image with arranged rows"""
        # ADDITIONAL SAFETY CHECK FOR BUG #21: Handle error state gracefully
        if self.original_image is None or not self.tile_rows:
            return None

        arranged_indices = self.arrangement_manager.get_arranged_indices()
        if not arranged_indices:
            return None

        # Use preview generator to create arranged image
        if self.tile_height is None:
            return None
        return self.preview_generator.create_arranged_image(
            self.original_image, self.tile_rows, arranged_indices, self.tile_height
        )

    def _export_arranged(self):
        """Export the arranged sprite sheet"""
        if self.arrangement_manager.get_arranged_count() == 0:
            return

        # Create arranged image
        arranged_image = self._create_arranged_image()

        if arranged_image:
            # Use preview generator to export
            if self.sprite_path:
                self.output_path = self.preview_generator.export_arranged_image(
                    self.sprite_path,
                    arranged_image,
                    self.arrangement_manager.get_arranged_count(),
                )

            if self.output_path:
                self._update_status(
                    f"Exported {self.arrangement_manager.get_arranged_count()} rows to "
                    f"{Path(self.output_path).name}"
                )

            # Accept dialog
            self.accept()

    def _update_status(self, message: str) -> None:
        """Update the status bar message"""
        self.update_status(message)

    def _update_existing_row_images(self):
        """Update the display images of existing row widgets without repopulating lists"""
        # Update available rows list
        if self.available_list is not None:
            for i in range(self.available_list.count()):
                item = self.available_list.item(i)
                widget = self.available_list.itemWidget(item)
                if widget and isinstance(widget, RowPreviewWidget):
                    row_index = item.data(Qt.ItemDataRole.UserRole)
                    # Get the appropriate display image (grayscale or colorized)
                    display_image = self._get_display_image_for_row(row_index)
                    if display_image:
                        widget.update_image(display_image)

        # Update arranged rows list
        if self.arranged_list is not None:
            for i in range(self.arranged_list.count()):
                item = self.arranged_list.item(i)
                widget = self.arranged_list.itemWidget(item)
                if widget and isinstance(widget, RowPreviewWidget):
                    row_index = item.data(Qt.ItemDataRole.UserRole)
                    # Get the appropriate display image (grayscale or colorized)
                    display_image = self._get_display_image_for_row(row_index)
                    if display_image:
                        widget.update_image(display_image)

    def _update_panel_titles(self):
        """Update panel titles with item counts"""
        arranged_count = self.arrangement_manager.get_arranged_count()
        available_count = len(self.tile_rows) - arranged_count

        self.left_panel.setTitle(f"Available Rows ({available_count})")
        self.right_panel.setTitle(f"Arranged Rows ({arranged_count})")

    def get_arranged_path(self):
        """Get the path to the arranged sprite sheet"""
        return self.output_path

    def _on_arrangement_changed(self):
        """Handle arrangement change signal from manager"""
        # Already handled by individual add/remove methods

    def _on_palette_mode_changed(self, enabled: bool) -> None:
        """Handle palette mode change signal"""
        # Already handled in toggle_palette_application

    def _on_palette_index_changed(self, index: int) -> None:
        """Handle palette index change signal"""
        # Already handled in _cycle_palette

    def set_palettes(self, palettes_dict: dict[int, list[tuple[int, int, int]]]) -> None:
        """Set the available palettes for colorization"""
        self.colorizer.set_palettes(palettes_dict)

        # Update display if palette is currently applied
        if self.colorizer.is_palette_mode():
            self._refresh_ui()

    def toggle_palette_application(self):
        """Toggle between grayscale and colorized display"""
        palette_enabled = self.colorizer.toggle_palette_mode()

        # Update displays without resetting scroll position
        self._update_existing_row_images()
        self._update_preview()

        # Update window title and status message
        if palette_enabled:
            palette_idx = self.colorizer.get_selected_palette_index()
            self.setWindowTitle(f"Arrange Sprite Rows - Palette {palette_idx}")
            self._update_status(
                f"Palette mode: Palette {palette_idx} applied | Press C to toggle, P to cycle"
            )
        else:
            self.setWindowTitle("Arrange Sprite Rows - Grayscale")
            self._update_status(
                "Grayscale mode: Original sprite colors | Press C to toggle palette"
            )

    def _get_display_image_for_row(self, row_index: int) -> Image.Image | None:
        """Get the appropriate display image for a row (grayscale or colorized)"""
        if row_index >= len(self.tile_rows):
            return None

        row_data = self.tile_rows[row_index]
        grayscale_image = row_data["image"]

        # Use colorizer to get display image
        return self.colorizer.get_display_image(row_index, grayscale_image)

    def _cycle_palette(self):
        """Cycle through available palettes (8-15)"""
        new_palette_idx = self.colorizer.cycle_palette()

        # Update displays without resetting scroll position
        self._update_existing_row_images()
        self._update_preview()

        # Update status and title
        self.setWindowTitle(f"Arrange Sprite Rows - Palette {new_palette_idx}")
        self._update_status(
            f"Palette mode: Palette {new_palette_idx} applied | Press C to toggle, P to cycle"
        )

    @override
    def keyPressEvent(self, a0: QKeyEvent | None) -> None:
        """Handle keyboard shortcuts"""
        if a0 and a0.key() == Qt.Key.Key_Delete:
            # Delete selected rows from arrangement
            self._remove_selected_rows()
        elif a0 and (
            a0.key() == Qt.Key.Key_A
            and a0.modifiers() == Qt.KeyboardModifier.ControlModifier
        ):
            # Ctrl+A: Add all rows
            self._add_all_rows()
        elif a0 and a0.key() == Qt.Key.Key_Escape:
            # Escape: Clear arrangement
            self._clear_arrangement()
        elif a0 and a0.key() == Qt.Key.Key_C:
            # C: Toggle palette application
            self.toggle_palette_application()
        elif a0 and a0.key() == Qt.Key.Key_P and self.colorizer.is_palette_mode():
            # P: Cycle through palettes (only when palette mode is active)
            self._cycle_palette()
        elif a0:
            super().keyPressEvent(a0)
