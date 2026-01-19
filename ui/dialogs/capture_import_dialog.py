"""Dialog for configuring Mesen 2 capture import options."""

from __future__ import annotations

from typing import TYPE_CHECKING, override

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from ui.components.base.dialog_base import DialogBase

if TYPE_CHECKING:
    from PIL import Image

    from core.mesen_integration.capture_to_arrangement import SpriteCluster
    from core.mesen_integration.click_extractor import CaptureResult


class CaptureImportDialog(DialogBase):
    """Dialog for configuring Mesen capture import settings."""

    def __init__(
        self,
        capture: CaptureResult,
        parent: QWidget | None = None,
    ) -> None:
        """Initialize the capture import dialog.

        Args:
            capture: Mesen 2 capture result to import
            parent: Parent widget
        """
        # Store capture before super().__init__ (DialogBase pattern)
        self._capture = capture

        # Get sprite clusters for selection
        from core.mesen_integration.capture_to_arrangement import CaptureToArrangementConverter
        self._converter = CaptureToArrangementConverter()
        self._clusters = self._converter.get_sprite_clusters(capture)

        # Properties set on accept
        self._selected_palettes: set[int] = set()
        self._selected_clusters: list[SpriteCluster] = []
        self._filter_garbage_tiles: bool = True

        # UI components
        self._palette_checkboxes: dict[int, QCheckBox] = {}
        self._cluster_list: QListWidget | None = None
        self._preview_label: QLabel | None = None

        super().__init__(
            parent,
            title="Import Mesen Capture",
            min_size=(600, 500),
            with_button_box=True,
        )

        # Customize button box
        if self.button_box:
            ok_button = self.button_box.button(self.button_box.StandardButton.Ok)
            if ok_button:
                ok_button.setText("Import")

    @property
    def selected_palettes(self) -> set[int]:
        """Get the selected palette indices."""
        return self._selected_palettes

    @property
    def selected_clusters(self) -> list[SpriteCluster]:
        """Get the selected sprite clusters."""
        return self._selected_clusters

    @property
    def filter_garbage_tiles(self) -> bool:
        """Whether to filter garbage tiles."""
        return self._filter_garbage_tiles

    @override
    def _setup_ui(self) -> None:
        """Set up the dialog UI."""
        layout = QVBoxLayout()
        layout.setSpacing(12)

        # Capture info section
        info_group = self._create_info_section()
        layout.addWidget(info_group)

        # Create splitter for cluster list and preview
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Sprite cluster selection section (left side)
        cluster_group = self._create_cluster_section()
        splitter.addWidget(cluster_group)

        # Preview section (right side)
        preview_group = self._create_preview_section()
        splitter.addWidget(preview_group)

        # Set initial splitter sizes (60% list, 40% preview)
        splitter.setSizes([300, 200])
        layout.addWidget(splitter, stretch=1)

        # Options section
        options_group = self._create_options_section()
        layout.addWidget(options_group)

        self.set_content_layout(layout)

    def _create_info_section(self) -> QGroupBox:
        """Create capture info display section."""
        group = QGroupBox("Capture Information")
        layout = QVBoxLayout(group)

        # Count palettes used
        palette_set = {c.palette_index for c in self._clusters}

        info_text = (
            f"Frame: {self._capture.frame} | "
            f"OAM entries: {len(self._capture.entries)} | "
            f"Sprite clusters: {len(self._clusters)} | "
            f"Palettes: {sorted(palette_set)}"
        )
        info_label = QLabel(info_text)
        info_label.setWordWrap(True)
        layout.addWidget(info_label)

        return group

    def _create_cluster_section(self) -> QGroupBox:
        """Create sprite cluster selection section."""
        group = QGroupBox("Select Sprites to Import")
        layout = QVBoxLayout(group)

        # Instruction
        instruction = QLabel("Click a sprite cluster to select it for import:")
        layout.addWidget(instruction)

        # Create list widget for clusters
        self._cluster_list = QListWidget()
        self._cluster_list.setSelectionMode(QListWidget.SelectionMode.MultiSelection)

        # Add clusters to list
        for cluster in self._clusters:
            item = QListWidgetItem(
                f"Sprite {cluster.id}: {cluster.width}x{cluster.height}px "
                f"at ({cluster.min_x}, {cluster.min_y}) "
                f"[Palette {cluster.palette_index}, {cluster.entry_count} OAM]"
            )
            item.setData(Qt.ItemDataRole.UserRole, cluster.id)
            self._cluster_list.addItem(item)

        # Select first cluster by default if any exist
        if self._cluster_list.count() > 0:
            self._cluster_list.item(0).setSelected(True)

        _ = self._cluster_list.itemSelectionChanged.connect(self._on_cluster_selection_changed)
        layout.addWidget(self._cluster_list)

        # Select all/none buttons
        btn_layout = QHBoxLayout()
        from PySide6.QtWidgets import QPushButton

        select_all_btn = QPushButton("Select All")
        _ = select_all_btn.clicked.connect(self._select_all_clusters)
        btn_layout.addWidget(select_all_btn)

        select_none_btn = QPushButton("Select None")
        _ = select_none_btn.clicked.connect(self._select_no_clusters)
        btn_layout.addWidget(select_none_btn)

        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        return group

    def _create_options_section(self) -> QGroupBox:
        """Create options section."""
        group = QGroupBox("Options")
        layout = QVBoxLayout(group)

        # Filter garbage tiles checkbox
        self._garbage_checkbox = QCheckBox("Filter common garbage tiles (0x03, 0x04)")
        self._garbage_checkbox.setChecked(True)
        self._garbage_checkbox.setToolTip("Remove tiles that commonly contain VRAM remnants in Kirby games")
        layout.addWidget(self._garbage_checkbox)

        return group

    def _create_preview_section(self) -> QGroupBox:
        """Create preview section showing rendered composite."""
        group = QGroupBox("Preview")
        layout = QVBoxLayout(group)

        self._preview_label = QLabel()
        self._preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._preview_label.setMinimumHeight(100)
        layout.addWidget(self._preview_label)

        self._update_preview()

        return group

    def _on_cluster_selection_changed(self) -> None:
        """Handle cluster selection change."""
        self._update_preview()

    def _select_all_clusters(self) -> None:
        """Select all clusters."""
        if self._cluster_list:
            self._cluster_list.selectAll()

    def _select_no_clusters(self) -> None:
        """Deselect all clusters."""
        if self._cluster_list:
            self._cluster_list.clearSelection()

    def _update_preview(self) -> None:
        """Update the preview image showing selected cluster(s)."""
        if self._preview_label is None:
            return

        # Get selected cluster IDs from list
        if self._cluster_list is None:
            self._preview_label.setText("No clusters available")
            return

        selected_items = self._cluster_list.selectedItems()
        if not selected_items:
            self._preview_label.setText("Select a sprite to preview")
            return

        selected_ids = {item.data(Qt.ItemDataRole.UserRole) for item in selected_items}
        selected_clusters = [c for c in self._clusters if c.id in selected_ids]

        if not selected_clusters:
            self._preview_label.setText("No clusters selected")
            return

        # Collect all entries from selected clusters
        entries = []
        for cluster in selected_clusters:
            entries.extend(cluster.entries)

        if not entries:
            self._preview_label.setText("No sprites in selection")
            return

        # Render preview using CaptureRenderer (colorized for preview)
        try:
            from PIL import Image as PILImage

            from core.mesen_integration.capture_renderer import CaptureRenderer

            renderer = CaptureRenderer(self._capture)

            # Normalize x positions for SNES wrap-around
            def normalize_x(x: int) -> int:
                return x if x >= 0 else x + 256

            # Calculate bounding box for selected entries
            norm_positions = [(normalize_x(e.x), e.y, e.width, e.height) for e in entries]
            min_x = min(p[0] for p in norm_positions)
            min_y = min(p[1] for p in norm_positions)
            max_x = max(p[0] + p[2] for p in norm_positions)
            max_y = max(p[1] + p[3] for p in norm_positions)
            width = max_x - min_x
            height = max_y - min_y

            # Create composite canvas
            composite = PILImage.new("RGBA", (width, height), (64, 64, 64, 255))

            # Render each entry at offset positions (colorized for preview)
            for entry in entries:
                entry_img = renderer.render_entry(entry, transparent_bg=True)
                x = normalize_x(entry.x) - min_x
                y = entry.y - min_y
                composite.paste(entry_img, (x, y), entry_img)

            # Scale for preview if needed
            max_size = 180
            if composite.width > max_size or composite.height > max_size:
                scale = max_size / max(composite.width, composite.height)
                new_width = max(1, int(composite.width * scale))
                new_height = max(1, int(composite.height * scale))
                composite = composite.resize((new_width, new_height), PILImage.Resampling.NEAREST)
            elif composite.width < 64 and composite.height < 64:
                # Scale up small sprites for visibility
                scale = min(4, 64 // max(composite.width, composite.height))
                new_width = composite.width * scale
                new_height = composite.height * scale
                composite = composite.resize((new_width, new_height), PILImage.Resampling.NEAREST)

            # Convert to QPixmap
            pixmap = self._pil_to_qpixmap(composite)
            self._preview_label.setPixmap(pixmap)

        except Exception as e:
            self._preview_label.setText(f"Preview error: {e}")

    def _pil_to_qpixmap(self, image: Image.Image) -> QPixmap:
        """Convert PIL Image to QPixmap."""
        if image.mode != "RGBA":
            image = image.convert("RGBA")

        data = image.tobytes("raw", "RGBA")
        qimage = QImage(
            data,
            image.width,
            image.height,
            image.width * 4,
            QImage.Format.Format_RGBA8888,
        )
        return QPixmap.fromImage(qimage)

    @override
    def accept(self) -> None:
        """Handle dialog accept - store selections and close."""
        # Collect selected clusters
        if self._cluster_list:
            selected_items = self._cluster_list.selectedItems()
            selected_ids = {item.data(Qt.ItemDataRole.UserRole) for item in selected_items}
            self._selected_clusters = [c for c in self._clusters if c.id in selected_ids]
            # Also collect palette indices from selected clusters
            self._selected_palettes = {c.palette_index for c in self._selected_clusters}
        else:
            self._selected_clusters = []
            self._selected_palettes = set()

        # Get garbage filter setting
        self._filter_garbage_tiles = self._garbage_checkbox.isChecked()

        super().accept()
