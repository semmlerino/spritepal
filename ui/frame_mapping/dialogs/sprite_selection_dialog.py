"""Dialog for selecting which OAM entries to include when importing a capture."""

from __future__ import annotations

from typing import TYPE_CHECKING, override

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSplitter,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ui.components.base.dialog_base import DialogBase
from ui.frame_mapping.utils.signal_utils import block_signals

if TYPE_CHECKING:
    from PIL import Image

    from core.mesen_integration.capture_to_arrangement import SpriteCluster
    from core.mesen_integration.click_extractor import CaptureResult, OAMEntry


# Data role constants for tree items
ROLE_ENTRY_ID = Qt.ItemDataRole.UserRole
ROLE_CLUSTER_ID = Qt.ItemDataRole.UserRole + 1
ROLE_IS_GROUP = Qt.ItemDataRole.UserRole + 2


class SpriteSelectionDialog(DialogBase):
    """Dialog for selecting which OAM entries to include when importing a capture."""

    def __init__(
        self,
        capture: CaptureResult,
        parent: QWidget | None = None,
    ) -> None:
        """Initialize the sprite selection dialog.

        Args:
            capture: Mesen 2 capture result containing OAM entries
            parent: Parent widget
        """
        # Store capture before super().__init__() per DialogBase pattern
        self._capture = capture
        self._selected_entries: list[OAMEntry] = []

        # UI components (initialized later)
        self._sprite_tree: QTreeWidget | None = None
        self._preview_label: QLabel | None = None
        self._palette_filter: QComboBox | None = None
        self._info_label: QLabel | None = None

        # Clustering state
        self._clusters: list[SpriteCluster] = []

        super().__init__(
            parent,
            title="Select Sprites to Import",
            min_size=(700, 500),
            with_button_box=True,
        )

        # Customize button box
        if self.button_box:
            ok_button = self.button_box.button(self.button_box.StandardButton.Ok)
            if ok_button:
                ok_button.setText("Import Selected")

        # Pre-select all visible sprites
        self._select_all_sprites()

    @property
    def selected_entries(self) -> list[OAMEntry]:
        """Return user's selected OAM entries."""
        return self._selected_entries

    @property
    def selected_palette(self) -> int:
        """Return the selected palette filter value, or -1 if All Palettes."""
        if self._palette_filter is None:
            return -1
        data = self._palette_filter.currentData()
        return data if data is not None else -1

    @override
    def _setup_ui(self) -> None:
        """Set up the dialog UI."""
        layout = QVBoxLayout()
        layout.setSpacing(12)

        # Info bar showing frame, entry count, palettes
        info_group = self._create_info_section()
        layout.addWidget(info_group)

        # Create splitter for sprite list and preview
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Sprite list section (left side)
        sprite_group = self._create_sprite_list_section()
        splitter.addWidget(sprite_group)

        # Preview section (right side)
        preview_group = self._create_preview_section()
        splitter.addWidget(preview_group)

        # Set initial splitter sizes (55% list, 45% preview)
        splitter.setSizes([385, 315])
        layout.addWidget(splitter, stretch=1)

        self.set_content_layout(layout)

    def _create_info_section(self) -> QGroupBox:
        """Create capture info display section."""
        group = QGroupBox("Capture Information")
        layout = QVBoxLayout(group)

        # Get unique palettes
        palette_set = {e.palette for e in self._capture.entries}

        info_text = (
            f"Frame {self._capture.frame} | "
            f"{len(self._capture.entries)} OAM Entries | "
            f"Palettes: {', '.join(str(p) for p in sorted(palette_set))}"
        )
        self._info_label = QLabel(info_text)
        self._info_label.setWordWrap(True)
        layout.addWidget(self._info_label)

        return group

    def _create_sprite_list_section(self) -> QGroupBox:
        """Create sprite list section with checkable items."""
        group = QGroupBox("Sprite List")
        layout = QVBoxLayout(group)

        # Filter controls
        filter_layout = QHBoxLayout()
        filter_label = QLabel("Filter by palette:")
        self._palette_filter = QComboBox()
        self._palette_filter.addItem("All Palettes", -1)

        # Add palette options
        palette_set = sorted({e.palette for e in self._capture.entries})
        for pal in palette_set:
            count = sum(1 for e in self._capture.entries if e.palette == pal)
            self._palette_filter.addItem(f"Palette {pal} ({count} sprites)", pal)

        _ = self._palette_filter.currentIndexChanged.connect(self._on_filter_changed)
        filter_layout.addWidget(filter_label)
        filter_layout.addWidget(self._palette_filter)
        filter_layout.addStretch()
        layout.addLayout(filter_layout)

        # Create tree widget with checkboxes
        self._sprite_tree = QTreeWidget()
        self._sprite_tree.setHeaderHidden(True)
        self._sprite_tree.setColumnCount(1)

        # Initial population (ungrouped - "All Palettes" is selected)
        self._populate_tree_ungrouped()

        _ = self._sprite_tree.itemChanged.connect(self._on_item_changed)
        layout.addWidget(self._sprite_tree)

        # Selection buttons
        btn_layout = QHBoxLayout()

        select_all_btn = QPushButton("Select All")
        _ = select_all_btn.clicked.connect(self._select_all_sprites)
        btn_layout.addWidget(select_all_btn)

        select_none_btn = QPushButton("Select None")
        _ = select_none_btn.clicked.connect(self._select_no_sprites)
        btn_layout.addWidget(select_none_btn)

        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        return group

    def _populate_tree_ungrouped(self) -> None:
        """Populate tree with individual entries (All Palettes mode)."""
        if self._sprite_tree is None:
            return

        with block_signals(self._sprite_tree):
            self._sprite_tree.clear()
            self._clusters = []

            # Add all entries as top-level items
            for entry in self._capture.entries:
                item = self._create_entry_item(entry)
                self._sprite_tree.addTopLevelItem(item)

    def _populate_tree_grouped(self, palette_index: int) -> None:
        """Populate tree with clusters for specific palette.

        Args:
            palette_index: Palette index to filter and cluster by
        """
        if self._sprite_tree is None:
            return

        from core.mesen_integration.capture_to_arrangement import (
            CaptureToArrangementConverter,
        )

        # Get clusters for this palette
        converter = CaptureToArrangementConverter()
        all_clusters = converter.get_sprite_clusters(
            self._capture,
            filter_garbage_tiles=False,  # Don't filter - user should see all
        )

        # Filter to only clusters matching the palette
        self._clusters = [c for c in all_clusters if c.palette_index == palette_index]

        with block_signals(self._sprite_tree):
            self._sprite_tree.clear()

            # Create items for each cluster
            for cluster in self._clusters:
                if cluster.entry_count == 1:
                    # Single entry - show as flat item
                    item = self._create_entry_item(cluster.entries[0])
                    item.setData(0, ROLE_CLUSTER_ID, cluster.id)
                    self._sprite_tree.addTopLevelItem(item)
                else:
                    # Multiple entries - create group item with children
                    group_item = self._create_group_item(cluster)
                    self._sprite_tree.addTopLevelItem(group_item)
                    group_item.setExpanded(True)

    def _create_group_item(self, cluster: SpriteCluster) -> QTreeWidgetItem:
        """Create expandable group item for a cluster.

        Args:
            cluster: Sprite cluster to create group for

        Returns:
            QTreeWidgetItem configured as tri-state parent
        """
        # Format: "Group A: N tiles @ (minX-maxX, minY-maxY)"
        # Convert cluster ID to letter (0=A, 1=B, etc.)
        letter = chr(ord("A") + (cluster.id % 26))
        max_x = cluster.min_x + cluster.width
        max_y = cluster.min_y + cluster.height
        text = f"Group {letter}: {cluster.entry_count} tiles @ ({cluster.min_x}-{max_x}, {cluster.min_y}-{max_y})"

        item = QTreeWidgetItem([text])
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsAutoTristate)
        item.setCheckState(0, Qt.CheckState.Unchecked)
        item.setData(0, ROLE_CLUSTER_ID, cluster.id)
        item.setData(0, ROLE_IS_GROUP, True)

        # Add child items for each entry
        for entry in cluster.entries:
            child_item = self._create_entry_item(entry)
            item.addChild(child_item)

        return item

    def _create_entry_item(self, entry: OAMEntry) -> QTreeWidgetItem:
        """Create a tree item for an OAM entry.

        Args:
            entry: OAM entry to create item for

        Returns:
            Configured QTreeWidgetItem
        """
        # Format: "#ID: WxH @(X,Y) Pal P, Pri N"
        text = (
            f"#{entry.id}: {entry.width}x{entry.height} @({entry.x},{entry.y}) Pal {entry.palette}, P{entry.priority}"
        )
        item = QTreeWidgetItem([text])
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
        item.setCheckState(0, Qt.CheckState.Unchecked)
        item.setData(0, ROLE_ENTRY_ID, entry.id)
        item.setData(0, ROLE_IS_GROUP, False)
        return item

    def _create_preview_section(self) -> QGroupBox:
        """Create preview section showing rendered composite of selected sprites."""
        group = QGroupBox("Preview")
        layout = QVBoxLayout(group)

        self._preview_label = QLabel()
        self._preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._preview_label.setMinimumHeight(200)
        self._preview_label.setStyleSheet("background-color: #404040;")
        layout.addWidget(self._preview_label, stretch=1)

        return group

    def _on_filter_changed(self, _index: int) -> None:
        """Handle palette filter change."""
        if self._sprite_tree is None or self._palette_filter is None:
            return

        selected_palette = self._palette_filter.currentData()

        if selected_palette == -1:
            # "All Palettes" - show ungrouped flat list
            self._populate_tree_ungrouped()
        else:
            # Specific palette - show grouped by spatial proximity
            self._populate_tree_grouped(selected_palette)

        # Auto-select all items after repopulating
        self._select_all_sprites()

    def _on_item_changed(self, item: QTreeWidgetItem, _column: int) -> None:
        """Handle tree item check state change.

        For group items with ItemIsAutoTristate, Qt handles propagation automatically.
        """
        self._update_preview()

    def _select_all_sprites(self) -> None:
        """Select all visible sprites."""
        if self._sprite_tree is None:
            return

        # Block signals to avoid multiple preview updates
        with block_signals(self._sprite_tree):
            # Iterate all top-level items
            for i in range(self._sprite_tree.topLevelItemCount()):
                item = self._sprite_tree.topLevelItem(i)
                if item is not None:
                    item.setCheckState(0, Qt.CheckState.Checked)

        self._update_preview()

    def _select_no_sprites(self) -> None:
        """Deselect all sprites."""
        if self._sprite_tree is None:
            return

        # Block signals to avoid multiple preview updates
        with block_signals(self._sprite_tree):
            # Iterate all top-level items
            for i in range(self._sprite_tree.topLevelItemCount()):
                item = self._sprite_tree.topLevelItem(i)
                if item is not None:
                    item.setCheckState(0, Qt.CheckState.Unchecked)

        self._update_preview()

    def _get_entry_by_id(self, entry_id: int) -> OAMEntry | None:
        """Get OAM entry by ID.

        Args:
            entry_id: Entry ID to look up

        Returns:
            OAMEntry or None if not found
        """
        for entry in self._capture.entries:
            if entry.id == entry_id:
                return entry
        return None

    def _get_selected_ids(self) -> set[int]:
        """Get IDs of all checked entries.

        Traverses tree structure, collecting entry IDs from both top-level
        items and children of group items.

        Returns:
            Set of selected entry IDs
        """
        if self._sprite_tree is None:
            return set()

        selected_ids: set[int] = set()

        def collect_from_item(item: QTreeWidgetItem) -> None:
            """Recursively collect checked entry IDs."""
            is_group = item.data(0, ROLE_IS_GROUP)

            if is_group:
                # Group item - collect from children
                for i in range(item.childCount()):
                    child = item.child(i)
                    # child() can return None despite stubs saying otherwise
                    if child is not None:  # pyright: ignore[reportUnnecessaryComparison]
                        collect_from_item(child)
            # Entry item - check if selected
            elif item.checkState(0) == Qt.CheckState.Checked:
                entry_id = item.data(0, ROLE_ENTRY_ID)
                if entry_id is not None:
                    selected_ids.add(entry_id)

        # Traverse all top-level items
        for i in range(self._sprite_tree.topLevelItemCount()):
            item = self._sprite_tree.topLevelItem(i)
            if item is not None:
                collect_from_item(item)

        return selected_ids

    def _update_preview(self) -> None:
        """Update the preview image showing selected sprites."""
        if self._preview_label is None:
            return

        selected_ids = self._get_selected_ids()

        if not selected_ids:
            # Clear pixmap first, then set text (setPixmap clears text)
            self._preview_label.setPixmap(QPixmap())
            self._preview_label.setText("Select sprites to preview")
            return

        # Filter entries to selected ones
        selected_entries = [e for e in self._capture.entries if e.id in selected_ids]

        if not selected_entries:
            self._preview_label.setText("No sprites selected")
            return

        try:
            from core.mesen_integration.capture_renderer import CaptureRenderer
            from core.mesen_integration.click_extractor import CaptureResult

            # Create filtered capture result for rendering
            filtered_capture = CaptureResult(
                frame=self._capture.frame,
                visible_count=len(selected_entries),
                obsel=self._capture.obsel,
                entries=selected_entries,
                palettes=self._capture.palettes,
                timestamp=self._capture.timestamp,
            )

            # Render composite
            renderer = CaptureRenderer(filtered_capture)
            preview_img = renderer.render_composite()

            # Crop to content bounds
            preview_img = self._crop_to_content(preview_img, selected_entries)

            # Scale for preview (fit in available space)
            preview_img = self._scale_for_preview(preview_img)

            # Convert to QPixmap and display
            pixmap = self._pil_to_qpixmap(preview_img)
            self._preview_label.setPixmap(pixmap)
            self._preview_label.setText("")

        except Exception as e:
            self._preview_label.setText(f"Preview error: {e}")

    def _crop_to_content(self, img: Image.Image, entries: list[OAMEntry]) -> Image.Image:
        """Crop image to bounding box of entries.

        Args:
            img: Full canvas image
            entries: OAM entries to calculate bounds from

        Returns:
            Cropped image
        """
        if not entries:
            return img

        # Calculate bounding box
        min_x = min(max(0, e.x) for e in entries)
        min_y = min(max(0, e.y) for e in entries)
        max_x = max(min(img.width, e.x + e.width) for e in entries)
        max_y = max(min(img.height, e.y + e.height) for e in entries)

        # Add small padding
        padding = 4
        min_x = max(0, min_x - padding)
        min_y = max(0, min_y - padding)
        max_x = min(img.width, max_x + padding)
        max_y = min(img.height, max_y + padding)

        if max_x <= min_x or max_y <= min_y:
            return img

        return img.crop((min_x, min_y, max_x, max_y))

    def _scale_for_preview(self, img: Image.Image) -> Image.Image:
        """Scale image to fit preview area.

        Args:
            img: Image to scale

        Returns:
            Scaled image
        """
        from PIL import Image as PILImage

        max_size = 280

        # Scale down if too large
        if img.width > max_size or img.height > max_size:
            scale = max_size / max(img.width, img.height)
            new_width = max(1, int(img.width * scale))
            new_height = max(1, int(img.height * scale))
            return img.resize((new_width, new_height), PILImage.Resampling.NEAREST)

        # Scale up if too small
        if img.width < 64 and img.height < 64:
            scale = min(4, 64 // max(img.width, img.height, 1))
            if scale > 1:
                new_width = img.width * scale
                new_height = img.height * scale
                return img.resize((new_width, new_height), PILImage.Resampling.NEAREST)

        return img

    def _pil_to_qpixmap(self, image: Image.Image) -> QPixmap:
        """Convert PIL Image to QPixmap.

        Args:
            image: PIL Image to convert

        Returns:
            QPixmap
        """
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
        # Collect selected entries
        selected_ids = self._get_selected_ids()
        self._selected_entries = [e for e in self._capture.entries if e.id in selected_ids]

        super().accept()
