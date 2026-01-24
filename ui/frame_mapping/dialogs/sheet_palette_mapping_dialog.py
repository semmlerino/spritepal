"""Dialog for editing sheet-level palette and color mappings."""

from __future__ import annotations

from typing import override

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from core.frame_mapping_project import SheetPalette
from ui.components.base.dialog_base import DialogBase
from ui.dialogs.color_mapping_dialog import (
    _find_nearest_palette_index,
    quantize_colors_to_palette,
)
from utils.color_distance import detect_rare_important_colors, perceptual_distance
from utils.logging_config import get_logger

logger = get_logger(__name__)


class PaletteSlotWidget(QWidget):
    """Clickable palette slot showing color and index."""

    clicked = Signal(int)  # Emits slot index when clicked

    def __init__(
        self,
        index: int,
        color: tuple[int, int, int],
        size: int = 28,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._index = index
        self._color = color
        self._selected = False
        self.setFixedSize(size, size)
        self._update_tooltip()

    def _update_tooltip(self) -> None:
        """Update tooltip with color info."""
        label = "(transparent)" if self._index == 0 else ""
        self.setToolTip(f"[{self._index}] RGB({self._color[0]}, {self._color[1]}, {self._color[2]}) {label}")

    def set_color(self, color: tuple[int, int, int]) -> None:
        """Update the displayed color."""
        self._color = color
        self._update_tooltip()
        self.update()

    def get_color(self) -> tuple[int, int, int]:
        """Get the current color."""
        return self._color

    def set_selected(self, selected: bool) -> None:
        """Set selection state."""
        self._selected = selected
        self.update()

    @override
    def paintEvent(self, event: object) -> None:
        """Draw the color slot."""
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(*self._color))

        # Draw border (highlighted if selected)
        if self._selected:
            painter.setPen(Qt.GlobalColor.blue)
            painter.drawRect(0, 0, self.width() - 1, self.height() - 1)
            painter.drawRect(1, 1, self.width() - 3, self.height() - 3)
        else:
            painter.setPen(Qt.GlobalColor.darkGray)
            painter.drawRect(0, 0, self.width() - 1, self.height() - 1)

        # Draw index number
        painter.setPen(Qt.GlobalColor.white if sum(self._color) < 384 else Qt.GlobalColor.black)
        painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, str(self._index))

        # Draw X for transparency slot
        if self._index == 0:
            painter.setPen(Qt.GlobalColor.red)
            painter.drawLine(2, 2, self.width() - 3, self.height() - 3)

        painter.end()

    @override
    def mousePressEvent(self, event: object) -> None:
        """Handle click."""
        self.clicked.emit(self._index)


class ColorMappingRowWidget(QWidget):
    """A row showing: AI color swatch -> palette index dropdown."""

    mapping_changed = Signal(tuple, int)  # (rgb_color, new_palette_index)

    def __init__(
        self,
        rgb_color: tuple[int, int, int],
        pixel_count: int,
        palette: list[tuple[int, int, int]],
        initial_index: int,
        is_rare_important: bool = False,
        distinctness: float = 0.0,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._rgb_color = rgb_color
        self._palette = palette
        self._is_rare_important = is_rare_important
        self._distinctness = distinctness
        self._protected = False

        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 2)

        # Protection indicator (★ for rare important colors)
        self._protect_label = QLabel("")
        self._protect_label.setFixedWidth(16)
        self._protect_label.setStyleSheet("font-size: 12px; color: #f0a030;")
        layout.addWidget(self._protect_label)

        # AI color swatch
        self._color_swatch = QWidget()
        self._color_swatch.setFixedSize(24, 24)
        self._color_swatch.setStyleSheet(
            f"background-color: rgb({rgb_color[0]}, {rgb_color[1]}, {rgb_color[2]}); border: 1px solid #888;"
        )
        layout.addWidget(self._color_swatch)

        # Color info label
        info_text = f"RGB({rgb_color[0]}, {rgb_color[1]}, {rgb_color[2]})  [{pixel_count} px]"
        if is_rare_important:
            info_text += f"  ⚠ rare (ΔE={distinctness:.1f})"
        info_label = QLabel(info_text)
        info_label.setMinimumWidth(220)
        info_label.setStyleSheet("font-size: 11px;")
        if is_rare_important:
            info_label.setStyleSheet("font-size: 11px; color: #e08030;")
        layout.addWidget(info_label)

        # Arrow
        arrow = QLabel("\u2192")  # →
        arrow.setStyleSheet("font-size: 14px; font-weight: bold;")
        layout.addWidget(arrow)

        # Palette dropdown
        self._combo = QComboBox()
        self._combo.setMinimumWidth(180)
        self._populate_combo(initial_index)
        self._combo.currentIndexChanged.connect(self._on_combo_changed)
        layout.addWidget(self._combo)

        # Target color swatch
        self._target_swatch = QWidget()
        self._target_swatch.setFixedSize(24, 24)
        self._update_target_swatch(initial_index)
        layout.addWidget(self._target_swatch)

        layout.addStretch()

        # Show initial protection status if rare
        if is_rare_important:
            self._update_protection_indicator()

    def _populate_combo(self, selected_index: int) -> None:
        """Populate the palette dropdown."""
        for idx, color in enumerate(self._palette):
            pixmap = QPixmap(16, 16)
            pixmap.fill(QColor(*color))
            label = f"[{idx}] RGB({color[0]}, {color[1]}, {color[2]})"
            if idx == 0:
                label += " (transparent)"
            self._combo.addItem(label)
            self._combo.setItemIcon(idx, pixmap)
        self._combo.setCurrentIndex(selected_index)

    def _update_target_swatch(self, index: int) -> None:
        """Update target color swatch."""
        if 0 <= index < len(self._palette):
            color = self._palette[index]
            self._target_swatch.setStyleSheet(
                f"background-color: rgb({color[0]}, {color[1]}, {color[2]}); border: 1px solid #888;"
            )

    def _on_combo_changed(self, index: int) -> None:
        """Handle palette selection change."""
        self._update_target_swatch(index)
        self._update_protection_indicator()
        self.mapping_changed.emit(self._rgb_color, index)

    def _update_protection_indicator(self) -> None:
        """Update the protection indicator based on mapping quality."""
        if not self._is_rare_important:
            self._protect_label.setText("")
            return

        # Check if current mapping is good (low perceptual distance to target)
        current_idx = self._combo.currentIndex()
        if 0 <= current_idx < len(self._palette):
            target_color = self._palette[current_idx]
            distance = perceptual_distance(self._rgb_color, target_color)
            # Good mapping if distance < 15 (reasonable threshold)
            if distance < 15:
                self._protect_label.setText("★")
                self._protect_label.setToolTip(f"Protected: good match (ΔE={distance:.1f})")
                self._protected = True
            else:
                self._protect_label.setText("⚠")
                self._protect_label.setToolTip(f"Warning: poor match (ΔE={distance:.1f}), consider adjusting")
                self._protected = False
        else:
            self._protect_label.setText("⚠")
            self._protected = False

    def set_protected(self, protected: bool) -> None:
        """Manually set protection status."""
        self._protected = protected
        if protected:
            self._protect_label.setText("★")
            self._protect_label.setToolTip("Manually protected")
        elif self._is_rare_important:
            self._update_protection_indicator()
        else:
            self._protect_label.setText("")

    def is_protected(self) -> bool:
        """Check if this mapping is protected."""
        return self._protected

    def is_rare_important(self) -> bool:
        """Check if this is a rare important color."""
        return self._is_rare_important

    def get_mapping(self) -> tuple[tuple[int, int, int], int]:
        """Get current mapping."""
        return (self._rgb_color, self._combo.currentIndex())


class SheetPaletteMappingDialog(DialogBase):
    """Dialog for editing sheet palette and color mappings.

    Provides:
    - 16-slot palette editor with clickable slots
    - Scrollable list of extracted AI colors with palette index dropdowns
    - Auto-Map (nearest color), Extract Palette, Copy Game Palette buttons
    """

    def __init__(
        self,
        sheet_colors: dict[tuple[int, int, int], int],  # RGB -> pixel count
        current_palette: SheetPalette | None,
        game_palettes: dict[str, list[tuple[int, int, int]]],  # game_frame_id -> palette
        parent: QWidget | None = None,
    ) -> None:
        """Initialize the dialog.

        Args:
            sheet_colors: Dict of unique RGB colors from AI sheet to pixel counts
            current_palette: Current SheetPalette or None
            game_palettes: Available game palettes to copy from (id -> colors)
            parent: Parent widget
        """
        # Store before super().__init__ (DialogBase pattern)
        self._sheet_colors = sheet_colors
        self._game_palettes = game_palettes

        # Initialize palette (copy current or create default)
        if current_palette is not None:
            self._palette_colors = list(current_palette.colors)
            self._color_mappings = dict(current_palette.color_mappings)
        else:
            self._palette_colors = [(0, 0, 0)] * 16
            self._color_mappings: dict[tuple[int, int, int], int] = {}

        # Detect rare important colors (e.g., eye whites, small highlights)
        self._rare_important_colors = detect_rare_important_colors(
            sheet_colors,
            rarity_threshold=0.01,  # < 1% of pixels
            distinctness_threshold=20.0,  # LAB delta > 20
            max_candidates=10,
        )
        # Create lookup: color -> distinctness
        self._rare_color_lookup: dict[tuple[int, int, int], float] = {
            color: dist for color, _count, dist in self._rare_important_colors
        }

        # Compute initial mappings for unmapped colors
        for color in sheet_colors:
            if color not in self._color_mappings:
                self._color_mappings[color] = _find_nearest_palette_index(color, self._palette_colors)

        # UI state
        self._palette_slots: list[PaletteSlotWidget] = []
        self._mapping_rows: list[ColorMappingRowWidget] = []
        self._selected_slot_index: int | None = None
        self._protect_rare_enabled = True  # Default: protect rare colors

        super().__init__(
            parent,
            title="Edit Sheet Palette",
            min_size=(650, 550),
            with_button_box=True,
        )

        # Customize button box
        if self.button_box:
            ok_button = self.button_box.button(self.button_box.StandardButton.Ok)
            if ok_button:
                ok_button.setText("Apply")

    def get_result(self) -> SheetPalette:
        """Get the resulting SheetPalette."""
        return SheetPalette(
            colors=list(self._palette_colors),
            color_mappings=dict(self._color_mappings),
        )

    @override
    def _setup_ui(self) -> None:
        """Set up the dialog UI."""
        content_layout = QVBoxLayout()
        content_layout.setSpacing(8)

        # Header
        header = QLabel(
            "<b>Sheet Palette Editor</b><br>"
            "Define a consistent palette for all AI frames. "
            "Map AI colors to palette slots below."
        )
        header.setWordWrap(True)
        content_layout.addWidget(header)

        # Rare color warning (if any detected)
        if self._rare_important_colors:
            warning_frame = QFrame()
            warning_frame.setStyleSheet(
                "QFrame { background-color: #fff8e0; border: 1px solid #f0a030; border-radius: 4px; }"
            )
            warning_layout = QHBoxLayout(warning_frame)
            warning_layout.setContentsMargins(8, 4, 8, 4)

            warning_icon = QLabel("⚠")
            warning_icon.setStyleSheet("font-size: 16px; color: #e08030;")
            warning_layout.addWidget(warning_icon)

            rare_count = len(self._rare_important_colors)
            warning_text = QLabel(
                f"<b>{rare_count} rare important color(s) detected</b> (e.g., eye whites, highlights). "
                "These are marked below with ⚠. Review their mappings carefully."
            )
            warning_text.setWordWrap(True)
            warning_text.setStyleSheet("color: #604000;")
            warning_layout.addWidget(warning_text, 1)

            content_layout.addWidget(warning_frame)

        # Palette slots section
        palette_group = QWidget()
        palette_layout = QVBoxLayout(palette_group)
        palette_layout.setContentsMargins(0, 0, 0, 0)
        palette_layout.setSpacing(4)

        palette_label = QLabel("Palette (16 colors):")
        palette_label.setStyleSheet("font-weight: bold;")
        palette_layout.addWidget(palette_label)

        # Palette slots row
        slots_layout = QHBoxLayout()
        slots_layout.setSpacing(2)
        for i in range(16):
            slot = PaletteSlotWidget(i, self._palette_colors[i])
            slot.clicked.connect(self._on_slot_clicked)
            self._palette_slots.append(slot)
            slots_layout.addWidget(slot)
        slots_layout.addStretch()
        palette_layout.addLayout(slots_layout)

        content_layout.addWidget(palette_group)

        # Action buttons
        actions_layout = QHBoxLayout()
        actions_layout.setSpacing(8)

        extract_btn = QPushButton("Extract Palette")
        extract_btn.setToolTip("Generate 16-color palette from AI sheet colors")
        extract_btn.clicked.connect(self._on_extract_palette)
        actions_layout.addWidget(extract_btn)

        auto_map_btn = QPushButton("Auto-Map Colors")
        auto_map_btn.setToolTip("Map all AI colors to nearest palette colors (perceptual distance)")
        auto_map_btn.clicked.connect(self._on_auto_map)
        actions_layout.addWidget(auto_map_btn)

        # Protect rare colors checkbox
        self._protect_checkbox = QCheckBox("Protect Rare")
        self._protect_checkbox.setChecked(self._protect_rare_enabled)
        self._protect_checkbox.setToolTip("When enabled, rare important colors (★) are preserved during Auto-Map")
        self._protect_checkbox.stateChanged.connect(self._on_protect_toggle)
        actions_layout.addWidget(self._protect_checkbox)

        # Game palette dropdown (if available)
        if self._game_palettes:
            copy_label = QLabel("Copy from:")
            actions_layout.addWidget(copy_label)

            self._game_palette_combo = QComboBox()
            self._game_palette_combo.setMinimumWidth(120)
            for frame_id in sorted(self._game_palettes.keys()):
                self._game_palette_combo.addItem(frame_id)
            actions_layout.addWidget(self._game_palette_combo)

            copy_btn = QPushButton("Copy")
            copy_btn.setToolTip("Copy palette from selected game frame")
            copy_btn.clicked.connect(self._on_copy_game_palette)
            actions_layout.addWidget(copy_btn)

        actions_layout.addStretch()
        content_layout.addLayout(actions_layout)

        # Color mappings section
        mappings_header_layout = QHBoxLayout()
        mappings_label = QLabel("Color Mappings:")
        mappings_label.setStyleSheet("font-weight: bold;")
        mappings_header_layout.addWidget(mappings_label)

        legend_label = QLabel("★ = protected  ⚠ = needs review")
        legend_label.setStyleSheet("font-size: 10px; color: #808080;")
        mappings_header_layout.addWidget(legend_label)
        mappings_header_layout.addStretch()
        content_layout.addLayout(mappings_header_layout)

        # Scrollable mapping rows
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        scroll_content = QWidget()
        scroll_layout = QVBoxLayout(scroll_content)
        scroll_layout.setSpacing(2)

        # Sort colors: rare important colors first, then by pixel count
        sorted_colors = sorted(
            self._sheet_colors.items(),
            key=lambda x: (x[0] not in self._rare_color_lookup, -x[1]),  # rare first, then by count
        )

        # Limit displayed colors
        max_displayed = 50
        displayed_colors = sorted_colors[:max_displayed]
        hidden_count = len(sorted_colors) - len(displayed_colors)

        for color, pixel_count in displayed_colors:
            initial_idx = self._color_mappings.get(color, 1)
            is_rare = color in self._rare_color_lookup
            distinctness = self._rare_color_lookup.get(color, 0.0)
            row = ColorMappingRowWidget(
                color,
                pixel_count,
                self._palette_colors,
                initial_idx,
                is_rare_important=is_rare,
                distinctness=distinctness,
            )
            row.mapping_changed.connect(self._on_mapping_changed)
            self._mapping_rows.append(row)
            scroll_layout.addWidget(row)

        scroll_layout.addStretch()
        scroll.setWidget(scroll_content)
        content_layout.addWidget(scroll, 1)

        # Summary
        total_colors = len(self._sheet_colors)
        total_pixels = sum(self._sheet_colors.values())
        rare_count = len(self._rare_important_colors)
        if hidden_count > 0:
            summary = QLabel(
                f"Showing top {max_displayed} of {total_colors} unique colors "
                f"({total_pixels} total pixels, {rare_count} rare)\n"
                f"Note: {hidden_count} minor colors will use nearest-color matching."
            )
        else:
            summary = QLabel(f"Total: {total_colors} unique colors, {total_pixels} pixels, {rare_count} rare important")
        content_layout.addWidget(summary)

        self.set_content_layout(content_layout)

    def _on_slot_clicked(self, index: int) -> None:
        """Handle palette slot click."""
        # Deselect previous
        if self._selected_slot_index is not None:
            self._palette_slots[self._selected_slot_index].set_selected(False)

        # Select new (or deselect if same)
        if self._selected_slot_index == index:
            self._selected_slot_index = None
        else:
            self._selected_slot_index = index
            self._palette_slots[index].set_selected(True)

    def _on_extract_palette(self) -> None:
        """Extract 16-color palette from AI sheet colors."""
        # Use the quantization utility
        extracted = quantize_colors_to_palette(self._sheet_colors, max_colors=16, snap_to_snes=True)

        # Update palette slots
        self._palette_colors = extracted
        for i, slot in enumerate(self._palette_slots):
            slot.set_color(extracted[i])

        # Re-map all colors to new palette
        self._on_auto_map()

        logger.info("Extracted 16-color palette from %d sheet colors", len(self._sheet_colors))

    def _on_protect_toggle(self, state: int) -> None:
        """Handle protect checkbox toggle."""
        self._protect_rare_enabled = state == Qt.CheckState.Checked.value
        logger.debug("Protect rare colors: %s", self._protect_rare_enabled)

    def _on_auto_map(self) -> None:
        """Auto-map all colors to nearest palette colors (perceptual distance).

        If "Protect Rare" is enabled, protected mappings are preserved.
        """
        protected_count = 0

        for color in self._sheet_colors:
            # Skip protected colors if protection is enabled
            if self._protect_rare_enabled and color in self._rare_color_lookup:
                # Check if current mapping is good enough to protect
                current_idx = self._color_mappings.get(color, 1)
                if 0 <= current_idx < len(self._palette_colors):
                    target_color = self._palette_colors[current_idx]
                    distance = perceptual_distance(color, target_color)
                    if distance < 15:  # Good match - keep it
                        protected_count += 1
                        continue

            # Auto-map to nearest perceptual match
            nearest_idx = _find_nearest_palette_index(color, self._palette_colors)
            self._color_mappings[color] = nearest_idx

        # Update UI rows
        for row in self._mapping_rows:
            rgb, _ = row.get_mapping()
            new_idx = self._color_mappings.get(rgb, 1)
            row._combo.blockSignals(True)
            row._combo.setCurrentIndex(new_idx)
            row._update_target_swatch(new_idx)
            row._combo.blockSignals(False)
            # Update protection indicator
            if row.is_rare_important():
                row._update_protection_indicator()

        if protected_count > 0:
            logger.info(
                "Auto-mapped %d colors (perceptual LAB), preserved %d protected mappings",
                len(self._sheet_colors) - protected_count,
                protected_count,
            )
        else:
            logger.info("Auto-mapped %d colors to nearest palette colors (perceptual LAB)", len(self._sheet_colors))

    def _on_copy_game_palette(self) -> None:
        """Copy palette from selected game frame."""
        if not hasattr(self, "_game_palette_combo"):
            return

        frame_id = self._game_palette_combo.currentText()
        if frame_id not in self._game_palettes:
            return

        game_palette = self._game_palettes[frame_id]

        # Copy colors (ensure 16 colors)
        self._palette_colors = list(game_palette[:16])
        while len(self._palette_colors) < 16:
            self._palette_colors.append((0, 0, 0))

        # Update slots
        for i, slot in enumerate(self._palette_slots):
            slot.set_color(self._palette_colors[i])

        # Re-map to new palette
        self._on_auto_map()

        logger.info("Copied palette from game frame %s", frame_id)

    def _on_mapping_changed(self, rgb_color: tuple[int, int, int], palette_index: int) -> None:
        """Handle mapping change from a row."""
        self._color_mappings[rgb_color] = palette_index
