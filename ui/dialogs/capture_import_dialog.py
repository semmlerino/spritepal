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
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ui.components.base.dialog_base import DialogBase

if TYPE_CHECKING:
    from PIL import Image

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

        # Properties set on accept
        self._selected_palettes: set[int] = set()
        self._filter_garbage_tiles: bool = True

        # UI components
        self._palette_checkboxes: dict[int, QCheckBox] = {}
        self._preview_label: QLabel | None = None

        super().__init__(
            parent,
            title="Import Mesen Capture",
            min_size=(500, 400),
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

        # Palette selection section
        palette_group = self._create_palette_section()
        layout.addWidget(palette_group)

        # Options section
        options_group = self._create_options_section()
        layout.addWidget(options_group)

        # Preview section
        preview_group = self._create_preview_section()
        layout.addWidget(preview_group)

        layout.addStretch()
        self.set_content_layout(layout)

    def _create_info_section(self) -> QGroupBox:
        """Create capture info display section."""
        group = QGroupBox("Capture Information")
        layout = QVBoxLayout(group)

        info_text = (
            f"Frame: {self._capture.frame}\n"
            f"Sprite entries: {len(self._capture.entries)}\n"
            f"OBSEL: 0x{self._capture.obsel.raw:02X}"
        )
        info_label = QLabel(info_text)
        layout.addWidget(info_label)

        return group

    def _create_palette_section(self) -> QGroupBox:
        """Create palette selection section with checkboxes."""
        group = QGroupBox("Palettes to Import")
        layout = QVBoxLayout(group)

        # Instruction
        instruction = QLabel("Select which sprite palettes to include:")
        layout.addWidget(instruction)

        # Create scrollable area for palette checkboxes
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setMaximumHeight(150)

        scroll_widget = QWidget()
        scroll_layout = QVBoxLayout(scroll_widget)
        scroll_layout.setSpacing(4)

        # Group entries by palette and count them
        palette_counts: dict[int, int] = {}
        for entry in self._capture.entries:
            palette_counts[entry.palette] = palette_counts.get(entry.palette, 0) + 1

        # Create checkbox for each palette
        for palette_idx in sorted(palette_counts.keys()):
            count = palette_counts[palette_idx]
            checkbox = QCheckBox(f"Palette {palette_idx} ({count} sprites)")
            checkbox.setChecked(True)  # Default all selected
            _ = checkbox.stateChanged.connect(self._on_palette_selection_changed)
            scroll_layout.addWidget(checkbox)
            self._palette_checkboxes[palette_idx] = checkbox

        scroll_layout.addStretch()
        scroll.setWidget(scroll_widget)
        layout.addWidget(scroll)

        # Select all/none buttons
        btn_layout = QHBoxLayout()
        from PySide6.QtWidgets import QPushButton

        select_all_btn = QPushButton("Select All")
        _ = select_all_btn.clicked.connect(self._select_all_palettes)
        btn_layout.addWidget(select_all_btn)

        select_none_btn = QPushButton("Select None")
        _ = select_none_btn.clicked.connect(self._select_no_palettes)
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

    def _on_palette_selection_changed(self) -> None:
        """Handle palette checkbox state change."""
        self._update_preview()

    def _select_all_palettes(self) -> None:
        """Select all palette checkboxes."""
        for checkbox in self._palette_checkboxes.values():
            checkbox.setChecked(True)

    def _select_no_palettes(self) -> None:
        """Deselect all palette checkboxes."""
        for checkbox in self._palette_checkboxes.values():
            checkbox.setChecked(False)

    def _update_preview(self) -> None:
        """Update the preview image."""
        if self._preview_label is None:
            return

        # Get selected palettes
        selected = {idx for idx, cb in self._palette_checkboxes.items() if cb.isChecked()}

        if not selected:
            self._preview_label.setText("No palettes selected")
            return

        # Filter entries by selected palettes
        entries = [e for e in self._capture.entries if e.palette in selected]

        if not entries:
            self._preview_label.setText("No sprites in selected palettes")
            return

        # Render preview using CaptureRenderer
        try:
            from PIL import Image as PILImage

            from core.mesen_integration.capture_renderer import CaptureRenderer

            renderer = CaptureRenderer(self._capture)

            # Calculate bounding box for selected entries
            min_x = min(e.x for e in entries)
            min_y = min(e.y for e in entries)
            max_x = max(e.x + e.width for e in entries)
            max_y = max(e.y + e.height for e in entries)
            width = max_x - min_x
            height = max_y - min_y

            # Create composite canvas
            composite = PILImage.new("RGBA", (width, height), (0, 0, 0, 0))

            # Render each entry at offset positions
            for entry in entries:
                entry_img = renderer.render_entry(entry, transparent_bg=True)
                x = entry.x - min_x
                y = entry.y - min_y
                composite.paste(entry_img, (x, y), entry_img)

            # Scale for preview if large
            max_size = 200
            if composite.width > max_size or composite.height > max_size:
                scale = max_size / max(composite.width, composite.height)
                new_width = int(composite.width * scale)
                new_height = int(composite.height * scale)
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
        # Collect selected palettes
        self._selected_palettes = {idx for idx, cb in self._palette_checkboxes.items() if cb.isChecked()}

        # Get garbage filter setting
        self._filter_garbage_tiles = self._garbage_checkbox.isChecked()

        super().accept()
